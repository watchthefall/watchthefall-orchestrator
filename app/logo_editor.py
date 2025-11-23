"""
Logo Editor - Interactive logo positioning and sizing with pinch-to-zoom
Allows brand logo placement with safe zones and touch gestures
"""
import os
import subprocess
import json
from typing import Tuple, Dict
from .config import FFMPEG_BIN, PROJECT_ROOT

class LogoEditor:
    """
    Interactive logo editor with pinch-to-zoom and drag support
    Enforces 5% safe zones from screen edges
    """
    
    SAFE_ZONE_PERCENT = 0.05  # 5% padding from edges
    DEFAULT_LOGO_SCALE = 0.15  # Logo is 15% of video width by default
    
    def __init__(self, video_path: str, brand_config: Dict, crop_metadata: Dict):
        self.video_path = video_path
        self.brand_config = brand_config
        self.crop_metadata = crop_metadata
        
        # Get video dimensions (after crop)
        self.width = crop_metadata['cropped_dimensions']['width']
        self.height = crop_metadata['cropped_dimensions']['height']
        
        # Calculate safe zone boundaries
        self.safe_x_min = int(self.width * self.SAFE_ZONE_PERCENT)
        self.safe_y_min = int(self.height * self.SAFE_ZONE_PERCENT)
        self.safe_x_max = int(self.width * (1 - self.SAFE_ZONE_PERCENT))
        self.safe_y_max = int(self.height * (1 - self.SAFE_ZONE_PERCENT))
        
        # Get logo path (prefer cleaned version)
        self.logo_path = self._get_logo_path()
    
    def _get_logo_path(self) -> str:
        """Get logo path, preferring cleaned version"""
        assets = self.brand_config.get('assets', {})
        logo = assets.get('logo', '')
        
        if not logo:
            return None
        
        # Check for cleaned logo first
        logo_name = os.path.basename(logo)
        cleaned_path = os.path.join(PROJECT_ROOT, 'imports', 'brands', 'wtf_orchestrator', 'logos_clean', logo_name)
        
        if os.path.exists(cleaned_path):
            return cleaned_path
        
        # Fall back to original
        original_path = os.path.join(PROJECT_ROOT, 'imports', 'brands', logo)
        return original_path if os.path.exists(original_path) else None
    
    def get_default_logo_settings(self) -> Dict:
        """
        Calculate default logo position and size
        Default: top-left with safe margins
        """
        # Logo size: 15% of video width
        logo_width = int(self.width * self.DEFAULT_LOGO_SCALE)
        logo_height = logo_width  # Assume square/circular logo
        
        # Position: top-left with safe zone
        logo_x = self.safe_x_min
        logo_y = self.safe_y_min
        
        return {
            'x': logo_x,
            'y': logo_y,
            'width': logo_width,
            'height': logo_height,
            'scale': self.DEFAULT_LOGO_SCALE,
            'opacity': 1.0
        }
    
    def enforce_safe_zones(self, logo_settings: Dict) -> Dict:
        """Ensure logo stays within safe zones"""
        x = logo_settings['x']
        y = logo_settings['y']
        w = logo_settings['width']
        h = logo_settings['height']
        
        # Clamp position to safe zones
        x = max(self.safe_x_min, min(x, self.safe_x_max - w))
        y = max(self.safe_y_min, min(y, self.safe_y_max - h))
        
        logo_settings['x'] = x
        logo_settings['y'] = y
        
        return logo_settings
    
    def launch(self) -> Dict:
        """
        Launch interactive logo editor UI
        
        In production: Opens web UI for mobile touch interaction
        For now: Returns default safe settings
        """
        settings = self.get_default_logo_settings()
        settings = self.enforce_safe_zones(settings)
        
        return {
            'logo_settings': settings,
            'logo_path': self.logo_path,
            'safe_zones': {
                'x_min': self.safe_x_min,
                'y_min': self.safe_y_min,
                'x_max': self.safe_x_max,
                'y_max': self.safe_y_max
            }
        }


def launch_logo_editor(video_path: str, brand_config: Dict, 
                       crop_metadata: Dict) -> Dict:
    """
    Convenience function to launch logo editor
    
    Args:
        video_path: Path to cropped video
        brand_config: Brand configuration from brands.yml
        crop_metadata: Metadata from crop stage
    
    Returns:
        Logo settings for downstream processing
    """
    editor = LogoEditor(video_path, brand_config, crop_metadata)
    return editor.launch()
