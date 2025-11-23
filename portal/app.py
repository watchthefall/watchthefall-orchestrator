"""
WatchTheFall Portal - Flask Application
"""
from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import uuid
from werkzeug.utils import secure_filename
import subprocess
import tempfile
import threading
import time
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

# Global conversion lock - only one FFmpeg process at a time (Render free tier 512MB RAM)
conversion_lock = threading.Lock()
conversion_in_progress = {'active': False, 'start_time': None}

# Job status dictionary for async watermark conversions
watermark_jobs = {}

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
            '/api/videos/convert-watermark',
            '/api/videos/convert-status/<job_id>'
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
    """Queue a watermark conversion job (async, non-blocking)"""
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided', 'reason': 'no_file'}), 400
        
        file = request.files['video']
        
        if file.filename == '':
            return jsonify({'error': 'Empty filename', 'reason': 'empty_filename'}), 400
        
        # Generate job ID
        job_id = uuid.uuid4().hex
        
        # Save WebM file temporarily
        webm_filename = secure_filename(file.filename)
        temp_webm = os.path.join(tempfile.gettempdir(), f"{job_id}_{webm_filename}")
        file.save(temp_webm)
        
        # Generate output MP4 filename
        mp4_filename = webm_filename.replace('.webm', '.mp4')
        if not mp4_filename.endswith('.mp4'):
            mp4_filename = os.path.splitext(mp4_filename)[0] + '.mp4'
        
        output_path = os.path.join(OUTPUT_DIR, mp4_filename)
        
        # Initialize job status
        watermark_jobs[job_id] = {
            'status': 'queued',
            'filename': mp4_filename,
            'webm_path': temp_webm,
            'output_path': output_path,
            'created_at': time.time(),
            'message': 'Waiting for conversion worker...'
        }
        
        print(f"[CONVERT] Job {job_id[:8]} queued: {webm_filename} → {mp4_filename}")
        log_event('info', None, f'Watermark conversion queued: {job_id[:8]} - {webm_filename}')
        
        # Start background conversion thread
        thread = threading.Thread(
            target=_watermark_conversion_worker,
            args=(job_id, temp_webm, output_path, mp4_filename),
            daemon=True
        )
        thread.start()
        
        # Return immediately with job ID
        return jsonify({
            'success': True,
            'job_id': job_id,
            'status': 'queued',
            'filename': mp4_filename,
            'message': 'Conversion job queued. Poll /api/videos/convert-status/<job_id> for progress.'
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[CONVERT QUEUE EXCEPTION]: {error_trace}")
        log_event('error', None, f'Conversion queue error: {str(e)}')
        return jsonify({
            'error': str(e),
            'reason': 'exception',
            'message': f'Failed to queue conversion: {str(e)}'
        }), 500


def _watermark_conversion_worker(job_id, temp_webm, output_path, mp4_filename):
    """Background worker for FFmpeg watermark conversion (runs in separate thread)"""
    try:
        # Update status to processing
        watermark_jobs[job_id]['status'] = 'processing'
        watermark_jobs[job_id]['message'] = 'Converting WebM to MP4...'
        watermark_jobs[job_id]['started_at'] = time.time()
        
        print(f"[CONVERT] Job {job_id[:8]} started: {mp4_filename}")
        
        # FFmpeg command: Optimized for Render free tier (512MB RAM)
        cmd = [
            'ffmpeg',
            '-analyzeduration', '1000000',
            '-probesize', '1048576',
            '-i', temp_webm,
            '-map', '0:v:0',
            '-map', '0:a?',
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-threads', '1',
            '-crf', '23',
            '-profile:v', 'baseline',
            '-level', '3.0',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-shortest',
            '-fflags', '+genpts',
            '-movflags', '+faststart',
            '-max_muxing_queue_size', '1024',
            '-y',
            output_path
        ]
        
        # Run FFmpeg conversion (background thread won't block Gunicorn worker)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300  # 5 minute timeout
        )
        
        # Clean up temp WebM
        try:
            os.remove(temp_webm)
        except:
            pass
        
        if result.returncode != 0:
            stderr_output = result.stderr.decode('utf-8', errors='ignore')
            error_preview = stderr_output[:500] if len(stderr_output) > 500 else stderr_output
            print(f"[CONVERT] Job {job_id[:8]} FAILED (exit {result.returncode}): {error_preview}")
            
            watermark_jobs[job_id]['status'] = 'failed'
            watermark_jobs[job_id]['error'] = 'FFmpeg conversion failed'
            watermark_jobs[job_id]['stderr_preview'] = error_preview
            watermark_jobs[job_id]['exit_code'] = result.returncode
            watermark_jobs[job_id]['message'] = 'Video conversion failed. Try a shorter video.'
            log_event('error', None, f'Conversion {job_id[:8]} failed: {error_preview[:100]}')
            return
        
        # Success
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        elapsed = time.time() - watermark_jobs[job_id]['started_at']
        
        watermark_jobs[job_id]['status'] = 'completed'
        watermark_jobs[job_id]['download_url'] = f'/api/videos/download/{mp4_filename}'
        watermark_jobs[job_id]['size_mb'] = round(file_size_mb, 2)
        watermark_jobs[job_id]['conversion_time'] = round(elapsed, 1)
        watermark_jobs[job_id]['message'] = 'Video converted to MP4 successfully'
        watermark_jobs[job_id]['completed_at'] = time.time()
        
        print(f"[CONVERT] Job {job_id[:8]} SUCCESS: {mp4_filename} ({file_size_mb:.2f}MB) in {elapsed:.1f}s")
        log_event('info', None, f'Conversion {job_id[:8]} complete: {mp4_filename} ({file_size_mb:.2f}MB, {elapsed:.1f}s)')
        
    except subprocess.TimeoutExpired:
        print(f"[CONVERT] Job {job_id[:8]} TIMEOUT (>5min)")
        watermark_jobs[job_id]['status'] = 'failed'
        watermark_jobs[job_id]['error'] = 'Conversion timeout'
        watermark_jobs[job_id]['message'] = 'Video took too long to convert (>5min). Try a shorter video.'
        log_event('error', None, f'Conversion {job_id[:8]} timeout')
        
        # Clean up
        try:
            os.remove(temp_webm)
        except:
            pass
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[CONVERT] Job {job_id[:8]} EXCEPTION: {error_trace}")
        
        watermark_jobs[job_id]['status'] = 'failed'
        watermark_jobs[job_id]['error'] = str(e)
        watermark_jobs[job_id]['message'] = f'Unexpected error: {str(e)}'
        log_event('error', None, f'Conversion {job_id[:8]} exception: {str(e)}')
        
        # Clean up
        try:
            os.remove(temp_webm)
        except:
            pass


@app.route('/api/videos/convert-status/<job_id>', methods=['GET'])
def get_conversion_status(job_id):
    """Poll conversion job status (non-blocking)"""
    if job_id not in watermark_jobs:
        return jsonify({
            'error': 'Job not found',
            'job_id': job_id,
            'message': 'Invalid job ID or job expired.'
        }), 404
    
    job = watermark_jobs[job_id]
    
    # Build response based on status
    response = {
        'job_id': job_id,
        'status': job['status'],
        'filename': job['filename'],
        'message': job.get('message', '')
    }
    
    if job['status'] == 'completed':
        response['download_url'] = job['download_url']
        response['size_mb'] = job['size_mb']
        response['conversion_time'] = job['conversion_time']
    elif job['status'] == 'failed':
        response['error'] = job.get('error', 'Unknown error')
        if 'stderr_preview' in job:
            response['stderr_preview'] = job['stderr_preview']
        if 'exit_code' in job:
            response['exit_code'] = job['exit_code']
    
    return jsonify(response)

# Stub endpoints removed - focus on core watermarking functionality

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
