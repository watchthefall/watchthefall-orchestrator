"""
WatchTheFall Portal - Flask Application
"""
from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import uuid
from werkzeug.utils import secure_filename
from functools import wraps

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
            static_folder='static')
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
        
        log_event('info', None, f'File uploaded: {filename}')
        
        return jsonify({
            'success': True,
            'filename': unique_filename,
            'message': 'Video uploaded successfully'
        })
        
    except Exception as e:
        log_event('error', None, f'Upload failed: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/videos/process', methods=['POST'])
def process_video_endpoint():
    """Process video with template"""
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
        
        print(f"[PROCESS STARTED] Job ID: {job_id}, Template: {template}, Aspect: {aspect_ratio}")
        
        # Process immediately (in production, this would be queued)
        try:
            output_file = process_video(job_id, video_path, template, aspect_ratio)
            
            # Guard clause: check if output_file is valid
            if not output_file or output_file is None:
                print(f"[PROCESS ERROR] Job {job_id}: process_video returned None or empty")
                log_event('error', job_id, 'Processing returned no output file')
                return jsonify({
                    'success': False,
                    'error': 'Video processing failed: no output file generated',
                    'job_id': job_id
                }), 500
            
            print(f"[PROCESS COMPLETED] Job ID: {job_id}, Output: {output_file}")
            
            return jsonify({
                'success': True,
                'job_id': job_id,
                'message': 'Processing completed',
                'output_file': output_file,
                'status_url': f'/api/videos/status/{job_id}'
            })
        except Exception as proc_error:
            import traceback
            print(f"[PROCESS EXCEPTION] Job {job_id}:")
            traceback.print_exc()
            log_event('error', job_id, f'Processing failed: {str(proc_error)}')
            return jsonify({
                'success': False,
                'error': str(proc_error),
                'job_id': job_id
            }), 500
        
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
        return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)
    except Exception as e:
        return jsonify({'error': 'File not found'}), 404

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
