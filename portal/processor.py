"""  
Video processor - applies WTF templates to videos
"""
import os
import subprocess
import uuid
try:
    import psutil
except ImportError:
    psutil = None
from .config import FFMPEG_BIN, TEMPLATE_DIR, OUTPUT_DIR, TEMP_DIR
from .database import update_job_status, log_event

def process_video(job_id, video_path, template_name, aspect_ratio='9:16'):
    """
    Process video with WTF template
    
    Args:
        job_id: Job ID
        video_path: Path to input video
        template_name: Brand template (e.g., 'ScotlandWTF')
        aspect_ratio: Output aspect ratio (9:16, 1:1, 16:9)
    
    Returns:
        Path to output video or None on failure
    """
    try:
        # RAM guard for Render free tier (512MB limit)
        if psutil:
            available_mb = psutil.virtual_memory().available / (1024 * 1024)
            print(f"[RAM CHECK] Job {job_id}: {available_mb:.1f}MB available")
            if psutil.virtual_memory().available < 100 * 1024 * 1024:
                raise MemoryError("Not enough RAM for safe processing on Render free tier (< 100MB available)")
        
        print(f"[PROCESSOR] Starting job {job_id}")
        update_job_status(job_id, 'processing')
        log_event('info', job_id, f'Starting video processing: {template_name}')
        
        # Get template and watermark paths
        template_path = os.path.join(TEMPLATE_DIR, 'template.png')
        
        # Find watermark for this brand
        watermark_path = None
        if template_name:
            watermark_dir = os.path.join(TEMPLATE_DIR, 'watermarks')
            # Try to find matching watermark
            for wm_file in os.listdir(watermark_dir):
                if template_name.lower().replace('wtf', '') in wm_file.lower():
                    watermark_path = os.path.join(watermark_dir, wm_file)
                    break
        
        # Output filename
        output_filename = f"{template_name}_{job_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        print(f"[PROCESSOR] Job {job_id}: Output will be {output_path}")
        
        # Calculate target dimensions based on aspect ratio
        if aspect_ratio == '9:16':
            target_w, target_h = 1080, 1920
        elif aspect_ratio == '1:1':
            target_w, target_h = 1080, 1080
        elif aspect_ratio == '16:9':
            target_w, target_h = 1920, 1080
        else:
            target_w, target_h = 1080, 1920
        
        # Build ffmpeg filter for low-memory streaming mode
        filters = []
        
        # Scale video to target size
        filters.append(f'scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black')
        
        # Overlay template
        if os.path.exists(template_path):
            filters.append(f"movie='{template_path}',scale={target_w}:{target_h}[template];[0:v][template]overlay=0:0")
        
        # Overlay watermark if found
        if watermark_path and os.path.exists(watermark_path):
            wm_width = int(target_w * 0.25)
            wm_x = target_w - wm_width - int(target_w * 0.05)
            wm_y = target_h - int(target_w * 0.05)
            filters.append(f"movie='{watermark_path}',scale={wm_width}:-1,format=rgba,colorchannelmixer=aa=0.15[wm];[0:v][wm]overlay={wm_x}:H-h-{int(target_h*0.05)}")
        
        filter_complex = ';'.join(filters) if filters else f'scale={target_w}:{target_h}'
        
        # LOW-MEMORY FFmpeg command for Render free tier
        cmd = [
            FFMPEG_BIN, '-y',
            '-hwaccel', 'auto',              # Hardware acceleration if available
            '-threads', '1',                  # Single thread to reduce memory
            '-buffer_size', '1M',             # Small buffer size
            '-max_muxing_queue_size', '256',  # Limit queue size
            '-i', video_path,
            '-filter_complex', filter_complex,
            '-c:v', 'libx264',
            '-preset', 'veryfast',            # Fast preset for low CPU/memory
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            output_path
        ]
        
        print(f"[FFMPEG COMMAND] Job {job_id}:")
        print(f"  {' '.join(cmd)}")
        
        log_event('info', job_id, f'Running ffmpeg (low-memory mode): {" ".join(cmd[:5])}...')
        
        # Run FFmpeg with streaming stderr monitoring (low memory)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Stream stderr to only log errors (avoid memory buildup)
        stderr_errors = []
        for line in process.stderr:
            if 'error' in line.lower() or 'failed' in line.lower():
                print(f"[FFMPEG ERROR] {line.strip()}")
                stderr_errors.append(line.strip())
        
        # Wait for process to complete
        process.wait(timeout=600)
        
        if process.returncode != 0:
            print(f"[FFMPEG ERROR] Job {job_id}: Return code {process.returncode}")
            error_msg = '\n'.join(stderr_errors[:5]) if stderr_errors else 'FFmpeg failed'
            print(f"  stderr: {error_msg}")
            raise Exception(f'FFmpeg failed: {error_msg[:200]}')
        
        if not os.path.exists(output_path):
            print(f"[FFMPEG ERROR] Job {job_id}: Output file not created at {output_path}")
            raise Exception('Output file not created')
        
        print(f"[PROCESSOR] Job {job_id}: Processing complete, output file: {output_filename}")
        log_event('info', job_id, f'Processing complete: {output_filename}')
        update_job_status(job_id, 'completed', output_path=output_filename)
        
        return output_filename
        
    except Exception as e:
        import traceback
        print(f"[PROCESSOR ERROR] Job {job_id}:")
        traceback.print_exc()
        error_msg = str(e)
        log_event('error', job_id, f'Processing failed: {error_msg}')
        update_job_status(job_id, 'failed', error_message=error_msg)
        return None

def get_video_dimensions(video_path):
    """Get video dimensions using ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        w, h = result.stdout.strip().split(',')
        return int(w), int(h)
    except:
        return 1080, 1920
