"""
WatchTheFall Portal - Flask Application
"""
from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import uuid
from werkzeug.utils import secure_filename
from functools import wraps
import threading
import subprocess
import tempfile
try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None

from .config import (
    SECRET_KEY, PORTAL_AUTH_KEY, UPLOAD_DIR, OUTPUT_DIR,
    ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, BRANDS_DIR
)
from .database import (
    create_job, get_job, get_recent_jobs, get_recent_logs,
    log_event
)
from .processor import process_video
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.brand_loader import get_brands

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static',
            static_url_path='/portal/static')
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE

def require_auth(f):
    """Authentication decorator"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_key = request.headers.get('WTF_PORTAL_KEY')
        if auth_key != PORTAL_AUTH_KEY:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
            '/api/videos/upload',
            '/api/videos/process',
            '/api/videos/status/<job_id>',
            '/api/system/logs',
            '/api/system/queue'
        ]
    })

# ============================================================================
# API: VIDEO PROCESSING
# ============================================================================

@app.route('/api/videos/upload', methods=['POST'])
def upload_video():
    """Upload video file"""
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
        
        file = request.files['video']
        
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed: mp4, mov, avi'}), 400
        
        # Save file
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(UPLOAD_DIR, unique_filename)
        file.save(filepath)
        
        # Check file size and warn if too large for Render free tier
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        size_warning = None
        if file_size_mb > 25:
            size_warning = f"Warning: File is {file_size_mb:.1f}MB. Render free tier may fail on files >25MB. Consider using a shorter clip."
            print(f"[UPLOAD WARNING] {size_warning}")
        
        log_event('info', None, f'File uploaded: {filename} ({file_size_mb:.2f}MB)')
        
        response = {
            'success': True,
            'filename': unique_filename,
            'message': 'Video uploaded successfully',
            'size_mb': round(file_size_mb, 2)
        }
        
        if size_warning:
            response['warning'] = size_warning
        
        return jsonify(response)
        
    except Exception as e:
        log_event('error', None, f'Upload failed: {str(e)}')
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/videos/process', methods=['POST'])
def process_video_endpoint():
    """Process video with template - async processing"""
    job_id = None
    try:
        data = request.json
        
        filename = data.get('filename')
        template = data.get('template', 'ScotlandWTF')
        aspect_ratio = data.get('aspect_ratio', '9:16')
        
        if not filename:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400
        
        video_path = os.path.join(UPLOAD_DIR, filename)
        
        if not os.path.exists(video_path):
            return jsonify({'success': False, 'error': 'Video file not found'}), 404
        
        # Create job
        job_id = uuid.uuid4().hex[:12]
        create_job(job_id, filename, template, aspect_ratio)
        
        print(f"[PROCESS QUEUED] Job ID: {job_id}, Template: {template}, Aspect: {aspect_ratio}")
        log_event('info', job_id, f'Job queued for processing')
        
        # Process in background thread to avoid blocking the API response
        def process_async():
            try:
                print(f"[ASYNC WORKER] Starting job {job_id}")
                output_file = process_video(job_id, video_path, template, aspect_ratio)
                if output_file:
                    print(f"[ASYNC WORKER] Job {job_id} completed: {output_file}")
                else:
                    print(f"[ASYNC WORKER] Job {job_id} failed: no output")
            except Exception as e:
                import traceback
                print(f"[ASYNC WORKER ERROR] Job {job_id}:")
                traceback.print_exc()
        
        # Start background processing
        thread = threading.Thread(target=process_async, daemon=True)
        thread.start()
        
        # Return immediately with job ID
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': 'Processing started in background',
            'status': 'processing',
            'status_url': f'/api/videos/status/{job_id}'
        })
        
    except Exception as e:
        import traceback
        print(f"[ENDPOINT EXCEPTION] Process endpoint error:")
        traceback.print_exc()
        log_event('error', job_id, f'Process request failed: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e),
            'job_id': job_id
        }), 500

@app.route('/api/videos/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get job status"""
    try:
        job = get_job(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        response = {
            'job_id': job['job_id'],
            'status': job['status'],
            'template': job['template'],
            'aspect_ratio': job['aspect_ratio'],
            'created_at': job['created_at']
        }
        
        if job['status'] == 'completed' and job['output_path']:
            response['download_url'] = f'/api/videos/download/{job["output_path"]}'
            response['output_file'] = job['output_path']
        
        if job['status'] == 'failed' and job['error_message']:
            response['error'] = job['error_message']
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/videos/recent', methods=['GET'])
def get_recent_videos():
    """Get recent jobs"""
    try:
        limit = request.args.get('limit', 20, type=int)
        jobs = get_recent_jobs(limit)
        return jsonify({'jobs': jobs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# API: TEMPLATES & BRANDS
# ============================================================================

@app.route('/api/templates', methods=['GET'])
def get_templates():
    """Get available templates/brands"""
    try:
        brands = get_brands()
        templates = [
            {
                'name': b.get('name'),
                'display_name': b.get('display_name', b.get('name'))
            }
            for b in brands
        ]
        return jsonify({'templates': templates})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# API: SYSTEM & LOGS
# ============================================================================

@app.route('/api/system/logs', methods=['GET'])
def get_logs():
    """Get system logs"""
    try:
        limit = request.args.get('limit', 50, type=int)
        logs = get_recent_logs(limit)
        return jsonify({'logs': logs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/system/queue', methods=['GET'])
def get_queue_status():
    """Get queue status"""
    try:
        jobs = get_recent_jobs(50)
        queued = [j for j in jobs if j['status'] == 'queued']
        processing = [j for j in jobs if j['status'] == 'processing']
        
        return jsonify({
            'queued': len(queued),
            'processing': len(processing),
            'jobs': queued + processing
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

# ============================================================================
# API: STUB ENDPOINTS (Future Features)
# ============================================================================

@app.route('/api/videos/post', methods=['POST'])
def auto_post_video():
    """Auto-post to social media (stub)"""
    return jsonify({'message': 'Feature coming soon', 'status': 'stub'}), 501

@app.route('/api/store/sync', methods=['POST'])
def sync_store():
    """Sync with store (stub)"""
    return jsonify({'message': 'Feature coming soon', 'status': 'stub'}), 501

@app.route('/api/store/list', methods=['GET'])
def list_store_products():
    """List store products (stub)"""
    return jsonify({'message': 'Feature coming soon', 'status': 'stub'}), 501

@app.route('/api/agent/ping', methods=['POST'])
def agent_ping():
    """Agent heartbeat (stub)"""
    return jsonify({'message': 'Agent system ready', 'status': 'stub'}), 200

@app.route('/api/hook/repurpose', methods=['POST'])
def repurpose_hook():
    """Content repurposing hook (stub)"""
    return jsonify({'message': 'Feature coming soon', 'status': 'stub'}), 501

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
