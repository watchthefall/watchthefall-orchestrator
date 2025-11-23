"""
WatchTheFall Portal - Flask Application
"""
from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import uuid
from werkzeug.utils import secure_filename
import subprocess
import tempfile
try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None

from .config import (
    SECRET_KEY, PORTAL_AUTH_KEY, OUTPUT_DIR,
    MAX_UPLOAD_SIZE, BRANDS_DIR
)
from .database import log_event

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static',
            static_url_path='/portal/static')
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE

# ============================================================================
# FRONTEND ROUTES
# ============================================================================

@app.route('/portal/')
def dashboard():
    """Main portal dashboard"""
    return render_template('dashboard.html')

@app.route('/portal/test')
def test_page():
    """Test page to verify portal is online"""
    return jsonify({
        'status': 'online',
        'message': 'WatchTheFall Portal is running',
        'endpoints': [
            '/portal/',
            '/api/videos/fetch',
            '/api/videos/download/<filename>',
            '/api/videos/convert-watermark'
        ]
    })

# ============================================================================
# API: VIDEO PROCESSING
# ============================================================================

# Upload endpoint removed - using client-side device upload with blob URLs

@app.route('/api/videos/fetch', methods=['POST'])
def fetch_videos_from_urls():
    """Download videos from URLs (TikTok, Instagram, X) - up to 5 at a time"""
    try:
        if not YoutubeDL:
            return jsonify({'success': False, 'error': 'yt-dlp not installed'}), 500
        
        data = request.get_json(force=True) or {}
        urls = data.get('urls') or []
        
        if not isinstance(urls, list) or len(urls) == 0:
            return jsonify({'success': False, 'error': 'Provide JSON: {"urls": ["url1", "url2", ...]}'}), 400
        
        if len(urls) > 5:
            return jsonify({'success': False, 'error': 'Maximum 5 URLs at a time (Render free tier limit)'}), 400
        
        print(f"[FETCH] Downloading {len(urls)} videos from URLs")
        log_event('info', None, f'Fetching {len(urls)} URLs')
        
        def download_one(url_input):
            try:
                ydl_opts = {
                    'outtmpl': os.path.join(OUTPUT_DIR, '%(id)s.%(ext)s'),
                    'merge_output_format': 'mp4',
                    'format': 'mp4/best',
                    'noplaylist': True,
                    'quiet': True,
                    'no_warnings': True,
                }
                
                with YoutubeDL(ydl_opts) as ydl:
                    print(f"[FETCH] Downloading: {url_input[:50]}...")
                    info = ydl.extract_info(url_input, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    # Ensure .mp4 extension
                    if not filename.endswith('.mp4'):
                        base, _ = os.path.splitext(filename)
                        filename = base + '.mp4'
                    
                    name = os.path.basename(filename)
                    file_size_mb = os.path.getsize(filename) / (1024 * 1024) if os.path.exists(filename) else 0
                    
                    print(f"[FETCH] Success: {name} ({file_size_mb:.2f}MB)")
                    return {
                        'url': url_input,
                        'filename': name,
                        'download_url': f'/api/videos/download/{name}',
                        'size_mb': round(file_size_mb, 2),
                        'success': True
                    }
            except Exception as e:
                print(f"[FETCH ERROR] {url_input}: {str(e)}")
                return {
                    'url': url_input,
                    'error': str(e),
                    'success': False
                }
        
        # Download sequentially to keep memory low
        results = []
        for url in urls:
            results.append(download_one(url))
        
        success_count = sum(1 for r in results if r.get('success'))
        log_event('info', None, f'Fetch complete: {success_count}/{len(urls)} successful')
        
        return jsonify({
            'success': True,
            'total': len(urls),
            'successful': success_count,
            'results': results
        })
        
    except Exception as e:
        import traceback
        print(f"[FETCH EXCEPTION]:")
        traceback.print_exc()
        log_event('error', None, f'Fetch failed: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

# Process endpoint removed - using client-side Canvas watermarking only

# Status endpoint removed - no server-side job queue

@app.route('/api/videos/download/<filename>', methods=['GET'])
def download_video(filename):
    """Download processed video"""
    try:
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        # Check if file exists
        if not os.path.exists(filepath):
            print(f"[DOWNLOAD ERROR] File not found: {filepath}")
            return jsonify({'error': 'File not found', 'path': filepath}), 404
        
        file_size = os.path.getsize(filepath)
        print(f"[DOWNLOAD] Serving file: {filename} ({file_size} bytes)")
        
        # Send file with proper headers for downloads folder
        response = send_from_directory(OUTPUT_DIR, filename, as_attachment=True)
        
        # Add Content-Disposition header to suggest Downloads folder
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Mobile-friendly headers
        response.headers['Content-Type'] = 'video/mp4'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        print(f"[DOWNLOAD] Headers set for {filename}")
        return response
    except Exception as e:
        print(f"[DOWNLOAD EXCEPTION] {filename}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'File not found', 'details': str(e)}), 404

# Recent videos endpoint removed - using localStorage history only

# ============================================================================
# API: BRANDS (Static JSON)
# ============================================================================
# Templates endpoint removed - frontend loads brands.json directly

# ============================================================================
# API: WATERMARK CONVERSION (WebM to MP4)
# ============================================================================

@app.route('/api/videos/convert-watermark', methods=['POST'])
def convert_watermark():
    """Convert client-side watermarked WebM video to MP4 for Instagram compatibility"""
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
        
        file = request.files['video']
        
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        # Save WebM file temporarily
        webm_filename = secure_filename(file.filename)
        temp_webm = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}_{webm_filename}")
        file.save(temp_webm)
        
        # Generate output MP4 filename
        mp4_filename = webm_filename.replace('.webm', '.mp4')
        if not mp4_filename.endswith('.mp4'):
            mp4_filename = os.path.splitext(mp4_filename)[0] + '.mp4'
        
        output_path = os.path.join(OUTPUT_DIR, mp4_filename)
        
        print(f"[CONVERT] Converting {webm_filename} to MP4...")
        log_event('info', None, f'Converting watermarked video: {webm_filename}')
        
        # FFmpeg command: Convert WebM to MP4 with H.264 codec (Instagram compatible)
        # -c:v libx264: H.264 video codec
        # -preset fast: Encoding speed
        # -crf 23: Quality (18-28, lower = better quality)
        # -profile:v baseline: Compatibility profile for all devices
        # -level 3.0: H.264 level for mobile compatibility
        # -pix_fmt yuv420p: Pixel format (required for compatibility)
        # -c:a aac: AAC audio codec
        # -b:a 128k: Audio bitrate
        # -ar 44100: Audio sample rate
        # -movflags +faststart: Optimize for web streaming
        # -max_muxing_queue_size 1024: Prevent muxing errors
        cmd = [
            'ffmpeg',
            '-i', temp_webm,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-profile:v', 'baseline',
            '-level', '3.0',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-movflags', '+faststart',
            '-max_muxing_queue_size', '1024',
            '-y',  # Overwrite output file
            output_path
        ]
        
        # Run FFmpeg conversion
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300  # 5 minute timeout
        )
        
        # Clean up temp file
        try:
            os.remove(temp_webm)
        except:
            pass
        
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='ignore')
            print(f"[CONVERT ERROR] FFmpeg failed: {error_msg}")
            log_event('error', None, f'Conversion failed: {error_msg[:200]}')
            return jsonify({'error': f'Conversion failed: {error_msg[:200]}'}), 500
        
        # Get file size
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        
        print(f"[CONVERT] Success: {mp4_filename} ({file_size_mb:.2f}MB)")
        log_event('info', None, f'Conversion complete: {mp4_filename} ({file_size_mb:.2f}MB)')
        
        return jsonify({
            'success': True,
            'filename': mp4_filename,
            'download_url': f'/api/videos/download/{mp4_filename}',
            'size_mb': round(file_size_mb, 2),
            'message': 'Video converted to MP4 successfully'
        })
        
    except subprocess.TimeoutExpired:
        log_event('error', None, 'Conversion timeout (>5min)')
        return jsonify({'error': 'Conversion timeout. Video may be too long.'}), 500
    except Exception as e:
        import traceback
        print(f"[CONVERT EXCEPTION]: {traceback.format_exc()}")
        log_event('error', None, f'Conversion exception: {str(e)}')
        return jsonify({'error': str(e)}), 500

# Stub endpoints removed - focus on core watermarking functionality

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
