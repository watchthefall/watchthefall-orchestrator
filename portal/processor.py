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
        # RAM guard for Render free tier (512MB limit) - ULTRA-LOW MEMORY MODE
        if psutil:
            available = psutil.virtual_memory().available
            available_mb = available / (1024 * 1024)
            print(f"[RAM CHECK] Job {job_id}: {available_mb:.1f}MB available")
            if available < 200 * 1024 * 1024:
                print(f"[RAM WARNING] Low memory detected: {available_mb:.1f}MB")
            if available < 100 * 1024 * 1024:
                raise MemoryError(f"Not enough RAM for safe processing on Render free tier ({available_mb:.1f}MB < 100MB)")
        
        print(f"[PROCESSOR] Starting job {job_id}")
        update_job_status(job_id, 'processing')
        log_event('info', job_id, f'Starting video processing: {template_name}')
        
        # Validate input video exists
        if not os.path.exists(video_path):
            raise Exception(f"Input video file not found: {video_path}")
        
        input_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        print(f"[PROCESSOR] Input video: {video_path} ({input_size_mb:.2f}MB)")
        
        # Output filename
        output_filename = f"{template_name}_{job_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        print(f"[PROCESSOR] Output will be: {output_path}")
        
        # Calculate target dimensions based on aspect ratio
        if aspect_ratio == '9:16':
            target_h = 1920
        elif aspect_ratio == '1:1':
            target_h = 1080
        elif aspect_ratio == '16:9':
            target_h = 1080
        else:
            target_h = 1920
        
        # ULTRA-SIMPLE FFmpeg command for Render free tier
        # Stripped down to absolute minimum to avoid compatibility issues
        ffmpeg_cmd = [
            FFMPEG_BIN,
            "-y",                              # Overwrite output
            "-i", video_path,                  # Input file
            "-vf", f"scale=-2:{target_h}",     # Scale video
            "-c:v", "mpeg4",                   # MPEG4 codec (universal)
            "-qscale:v", "5",                  # Quality setting
            "-an",                             # No audio (simplify for now)
            output_path
        ]
        
        print(f"[FFMPEG CMD] {' '.join(ffmpeg_cmd)}")
        print(f"[DEBUG] Input exists: {os.path.exists(video_path)}")
        print(f"[DEBUG] Output dir exists: {os.path.exists(os.path.dirname(output_path))}")
        print(f"[DEBUG] FFMPEG_BIN: {FFMPEG_BIN}")
        
        log_event('info', job_id, f'Running ffmpeg (ultra-low-memory mode): {" ".join(ffmpeg_cmd[:5])}...')
        
        # Run FFmpeg with full stderr capture for debugging
        print(f"[PROCESSOR] Executing FFmpeg...")
        process = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600
        )
        
        # Print ALL stderr for complete debugging visibility
        if process.stderr:
            print(f"[FFMPEG STDERR - FULL OUTPUT]:")
            for line in process.stderr.split('\n'):
                if line.strip():
                    print(f"  {line}")
        
        if process.returncode != 0:
            print(f"[FFMPEG ERROR] Return code: {process.returncode}")
            print(f"[FFMPEG ERROR] Full stderr:\n{process.stderr}")
            raise Exception(f'FFmpeg failed (code {process.returncode}): {process.stderr[:500]}')
        
        # FORCED OUTPUT VERIFICATION
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
            if not os.path.exists(output_path):
                raise Exception("FFmpeg produced no output — likely killed by low memory (file doesn't exist)")
            else:
                raise Exception(f"FFmpeg produced invalid output — likely killed by low memory (file size: {os.path.getsize(output_path)} bytes)")
        
        output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[PROCESSOR] Job {job_id}: Processing complete, output file: {output_filename} ({output_size_mb:.2f}MB)")
        log_event('info', job_id, f'Processing complete: {output_filename} ({output_size_mb:.2f}MB)')
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
