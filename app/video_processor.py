"""
Video Processor - Apply template, logo, and watermark with adaptive opacity
Handles multi-brand export with safe zones and brightness-based watermark adjustment
"""
import os
import subprocess
import json
from typing import Dict, List, Optional
from PIL import Image
import numpy as np
from .config import FFMPEG_BIN, FFPROBE_BIN, PROJECT_ROOT

class VideoProcessor:
    """
    Process videos with brand overlays: template, logo, and adaptive watermark
    """
    
    SAFE_ZONE_PERCENT = 0.05  # 5% padding from edges
    WATERMARK_OPACITY_MIN = 0.10  # 10% for bright videos
    WATERMARK_OPACITY_MAX = 0.20  # 20% for dark videos
    
    def __init__(self, video_path: str, output_dir: str = 'exports'):
        self.video_path = video_path
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        self.video_info = self._probe_video()
        self.brightness = None  # Lazy loaded
    
    def _probe_video(self) -> Dict:
        """Get video properties"""
        try:
            cmd = [
                FFPROBE_BIN, '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,duration',
                '-of', 'json',
                self.video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            stream = data['streams'][0]
            
            return {
                'width': int(stream['width']),
                'height': int(stream['height']),
                'duration': float(stream.get('duration', 0))
            }
        except:
            return {'width': 1080, 'height': 1920, 'duration': 0}
    
    def calculate_video_brightness(self) -> float:
        """
        Calculate average brightness of video
        Returns value between 0 (dark) and 1 (bright)
        """
        if self.brightness is not None:
            return self.brightness
        
        try:
            # Extract a frame from middle of video
            temp_frame = os.path.join(self.output_dir, 'temp_brightness_frame.png')
            
            cmd = [
                FFMPEG_BIN, '-y',
                '-ss', '1',  # 1 second in
                '-i', self.video_path,
                '-vframes', '1',
                '-vf', 'scale=320:240',  # Small size for speed
                temp_frame
            ]
            
            subprocess.run(cmd, capture_output=True, check=True)
            
            # Analyze frame brightness
            img = Image.open(temp_frame).convert('L')  # Grayscale
            pixels = np.array(img)
            brightness = np.mean(pixels) / 255.0
            
            # Cleanup
            if os.path.exists(temp_frame):
                os.remove(temp_frame)
            
            self.brightness = brightness
            return brightness
            
        except Exception as e:
            # Default to mid-brightness
            self.brightness = 0.5
            return 0.5
    
    def calculate_adaptive_watermark_opacity(self) -> float:
        """
        Calculate watermark opacity based on video brightness
        Bright video = darker watermark (10%)
        Dark video = lighter watermark (20%)
        """
        brightness = self.calculate_video_brightness()
        
        # Inverse relationship: bright video needs less opacity
        # Linear interpolation between min and max
        opacity = self.WATERMARK_OPACITY_MAX - (brightness * (self.WATERMARK_OPACITY_MAX - self.WATERMARK_OPACITY_MIN))
        
        # Clamp to range
        opacity = max(self.WATERMARK_OPACITY_MIN, min(self.WATERMARK_OPACITY_MAX, opacity))
        
        return opacity
    
    def build_filter_complex(self, brand_config: Dict, logo_settings: Optional[Dict] = None) -> str:
        """
        Build ffmpeg filter_complex for overlays
        
        Order:
        1. Scale template to video size
        2. Overlay template
        3. Overlay logo (if settings provided)
        4. Overlay watermark with adaptive opacity
        """
        assets = brand_config.get('assets', {})
        options = brand_config.get('options', {})
        
        width = self.video_info['width']
        height = self.video_info['height']
        
        filters = []
        inputs = ['0:v']  # Start with video input
        
        # 1. Load and scale template
        template_path = os.path.join(PROJECT_ROOT, 'imports', 'brands', assets.get('template', ''))
        if os.path.exists(template_path):
            filters.append(f"movie='{template_path}',scale={width}:{height}[template]")
            filters.append(f"[{inputs[-1]}][template]overlay=0:0[v1]")
            inputs.append('v1')
        
        # 2. Overlay logo (if settings provided)
        if logo_settings and logo_settings.get('logo_path'):
            logo_path = logo_settings['logo_path']
            if os.path.exists(logo_path):
                logo_x = logo_settings['logo_settings']['x']
                logo_y = logo_settings['logo_settings']['y']
                logo_w = logo_settings['logo_settings']['width']
                logo_h = logo_settings['logo_settings']['height']
                
                filters.append(f"movie='{logo_path}',scale={logo_w}:{logo_h}[logo]")
                filters.append(f"[{inputs[-1]}][logo]overlay={logo_x}:{logo_y}[v2]")
                inputs.append('v2')
        
        # 3. Overlay watermark with adaptive opacity
        watermark_path = os.path.join(PROJECT_ROOT, 'imports', 'brands', assets.get('watermark', ''))
        if os.path.exists(watermark_path):
            opacity = self.calculate_adaptive_watermark_opacity()
            wm_scale = options.get('watermark_scale', 0.25)
            wm_width = int(width * wm_scale)
            
            # Calculate position (bottom-right with safe zone)
            safe_margin = int(width * self.SAFE_ZONE_PERCENT)
            wm_position = options.get('watermark_position', 'bottom-right')
            
            if wm_position == 'bottom-right':
                wm_x = f"W-w-{safe_margin}"
                wm_y = f"H-h-{safe_margin}"
            elif wm_position == 'bottom-left':
                wm_x = safe_margin
                wm_y = f"H-h-{safe_margin}"
            elif wm_position == 'top-right':
                wm_x = f"W-w-{safe_margin}"
                wm_y = safe_margin
            elif wm_position == 'top-left':
                wm_x = safe_margin
                wm_y = safe_margin
            else:
                wm_x = f"W-w-{safe_margin}"
                wm_y = f"H-h-{safe_margin}"
            
            filters.append(f"movie='{watermark_path}',scale={wm_width}:-1,format=rgba,colorchannelmixer=aa={opacity}[watermark]")
            filters.append(f"[{inputs[-1]}][watermark]overlay={wm_x}:{wm_y}")
        
        return ';'.join(filters) if filters else None
    
    def process_brand(self, brand_config: Dict, logo_settings: Optional[Dict] = None, 
                     video_id: str = 'video') -> str:
        """
        Process video with brand overlays
        
        Args:
            brand_config: Brand configuration from brands.yml
            logo_settings: Logo position and size settings (optional)
            video_id: Identifier for output filename
        
        Returns:
            Path to processed video
        """
        brand_name = brand_config.get('name', 'brand')
        output_filename = f"{brand_name}_{video_id}.mp4"
        output_path = os.path.join(self.output_dir, brand_name, output_filename)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Build filter complex
        filter_complex = self.build_filter_complex(brand_config, logo_settings)
        
        if not filter_complex:
            # No overlays - just copy
            import shutil
            shutil.copy2(self.video_path, output_path)
            return output_path
        
        # Run ffmpeg
        cmd = [
            FFMPEG_BIN, '-y',
            '-i', self.video_path,
            '-filter_complex', filter_complex,
            '-c:v', 'libx264',
            '-crf', '18',
            '-preset', 'medium',
            '-c:a', 'copy',
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error: {e.stderr.decode()}")
            raise
    
    def process_multiple_brands(self, brands: List[Dict], logo_settings: Optional[Dict] = None,
                               video_id: str = 'video') -> List[str]:
        """
        Process video for multiple brands
        
        Args:
            brands: List of brand configurations
            logo_settings: Logo settings (same for all brands if provided)
            video_id: Identifier for output filenames
        
        Returns:
            List of output video paths
        """
        output_paths = []
        
        for brand in brands:
            brand_name = brand.get('display_name', brand.get('name', 'Unknown'))
            print(f"  Processing {brand_name}...")
            
            try:
                output_path = self.process_brand(brand, logo_settings, video_id)
                output_paths.append(output_path)
                print(f"    ✓ Exported to {output_path}")
            except Exception as e:
                print(f"    ✗ Failed: {e}")
        
        return output_paths


def process_video(video_path: str, brands: List[Dict], logo_settings: Optional[Dict] = None,
                 output_dir: str = 'exports', video_id: str = 'video') -> List[str]:
    """
    Convenience function to process video for multiple brands
    
    Args:
        video_path: Path to cropped video
        brands: List of brand configurations
        logo_settings: Logo position/size settings
        output_dir: Output directory
        video_id: Video identifier
    
    Returns:
        List of output video paths
    """
    processor = VideoProcessor(video_path, output_dir)
    return processor.process_multiple_brands(brands, logo_settings, video_id)
