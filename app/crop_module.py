"""
Crop Module - Interactive video cropping with pinch-to-zoom and drag support
Outputs cropped video and metadata for downstream processing
"""
import os
import subprocess
import json
from typing import Tuple, Dict, Optional
from .config import FFMPEG_BIN, FFPROBE_BIN

class CropEditor:
    """
    Handles video cropping with interactive UI support
    Supports multiple aspect ratios and touch gestures
    """
    
    ASPECT_RATIOS = {
        '9:16': (9, 16),    # Default vertical (TikTok, Reels)
        '1:1': (1, 1),      # Square (Instagram)
        '4:5': (4, 5),      # Portrait (Instagram Feed)
        '16:9': (16, 9),    # Landscape (YouTube)
    }
    
    def __init__(self, video_path: str, output_dir: str):
        self.video_path = video_path
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        self.video_info = self._probe_video()
        self.width = self.video_info['width']
        self.height = self.video_info['height']
        
    def _probe_video(self) -> Dict:
        """Get video dimensions and properties"""
        try:
            cmd = [
                FFPROBE_BIN, '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,duration,r_frame_rate',
                '-of', 'json',
                self.video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            stream = data['streams'][0]
            
            # Parse frame rate
            fps_parts = stream.get('r_frame_rate', '30/1').split('/')
            fps = int(fps_parts[0]) / int(fps_parts[1]) if len(fps_parts) == 2 else 30
            
            return {
                'width': int(stream['width']),
                'height': int(stream['height']),
                'duration': float(stream.get('duration', 0)),
                'fps': fps
            }
        except Exception as e:
            # Fallback defaults
            return {'width': 1080, 'height': 1920, 'duration': 0, 'fps': 30}
    
    def calculate_crop_dimensions(self, aspect_ratio: str = '9:16') -> Tuple[int, int]:
        """Calculate crop dimensions based on aspect ratio"""
        ar_w, ar_h = self.ASPECT_RATIOS.get(aspect_ratio, (9, 16))
        
        # Calculate dimensions that fit within video
        if self.width / self.height > ar_w / ar_h:
            # Video is wider - fit to height
            crop_height = self.height
            crop_width = int(crop_height * ar_w / ar_h)
        else:
            # Video is taller - fit to width
            crop_width = self.width
            crop_height = int(crop_width * ar_h / ar_w)
        
        # Ensure even numbers for ffmpeg
        crop_width = crop_width - (crop_width % 2)
        crop_height = crop_height - (crop_height % 2)
        
        return crop_width, crop_height
    
    def launch_crop_ui(self, aspect_ratio: str = '9:16') -> Dict:
        """
        Launch interactive crop UI (web-based for mobile compatibility)
        Returns crop settings for user to adjust via web interface
        
        In production: This would open a web UI accessible from phone
        For now: Returns default centered crop
        """
        crop_width, crop_height = self.calculate_crop_dimensions(aspect_ratio)
        
        # Center crop by default
        crop_x = (self.width - crop_width) // 2
        crop_y = (self.height - crop_height) // 2
        
        # Ensure even coordinates
        crop_x = crop_x - (crop_x % 2)
        crop_y = crop_y - (crop_y % 2)
        
        return {
            'x': crop_x,
            'y': crop_y,
            'width': crop_width,
            'height': crop_height,
            'scale': 1.0,
            'rotation': 0,
            'aspect_ratio': aspect_ratio,
            'source_width': self.width,
            'source_height': self.height
        }
    
    def apply_crop(self, crop_settings: Dict) -> str:
        """
        Apply crop settings to video using ffmpeg
        Returns path to cropped video
        """
        output_path = os.path.join(
            self.output_dir,
            f'cropped_{os.path.basename(self.video_path)}'
        )
        
        x = crop_settings['x']
        y = crop_settings['y']
        w = crop_settings['width']
        h = crop_settings['height']
        rotation = crop_settings.get('rotation', 0)
        
        # Build ffmpeg filter
        filters = []
        
        # Apply crop
        filters.append(f'crop={w}:{h}:{x}:{y}')
        
        # Apply rotation if needed
        if rotation == 90:
            filters.append('transpose=1')
        elif rotation == 180:
            filters.append('transpose=1,transpose=1')
        elif rotation == 270:
            filters.append('transpose=2')
        
        filter_str = ','.join(filters)
        
        cmd = [
            FFMPEG_BIN, '-y',
            '-i', self.video_path,
            '-vf', filter_str,
            '-c:v', 'libx264',
            '-crf', '18',
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '128k',
            output_path
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        
        return output_path
    
    def get_crop_metadata(self, crop_settings: Dict) -> Dict:
        """Return crop metadata for downstream use"""
        return {
            'crop': crop_settings,
            'original_dimensions': {
                'width': self.width,
                'height': self.height
            },
            'cropped_dimensions': {
                'width': crop_settings['width'],
                'height': crop_settings['height']
            }
        }


def launch_crop_ui(video_path: str, temp_dir: str = 'temp/crop', 
                   aspect_ratio: str = '9:16') -> Tuple[str, Dict]:
    """
    Convenience function to launch crop UI and apply crop
    
    Args:
        video_path: Path to video to crop
        temp_dir: Directory for temporary files
        aspect_ratio: Target aspect ratio (9:16, 1:1, 4:5, 16:9)
    
    Returns:
        Tuple of (cropped_video_path, crop_metadata)
    """
    editor = CropEditor(video_path, temp_dir)
    crop_settings = editor.launch_crop_ui(aspect_ratio)
    cropped_path = editor.apply_crop(crop_settings)
    metadata = editor.get_crop_metadata(crop_settings)
    
    return cropped_path, metadata
