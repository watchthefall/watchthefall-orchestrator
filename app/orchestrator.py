"""
Main Orchestrator - Coordinates the complete video processing pipeline
Download → Crop → Logo Edit → Multi-Brand Export
"""
import os
from typing import List, Dict, Optional
from .brand_loader import get_brands
from .crop_module import launch_crop_ui
from .logo_editor import launch_logo_editor
from .video_processor import process_video

class WTFOrchestrator:
    """
    Main orchestrator for WatchTheFall video processing
    
    Pipeline:
    1. Download video (external - yt-dlp)
    2. Crop video with pinch-to-zoom UI
    3. Position logo with interactive editor
    4. Export to multiple brands with adaptive watermarks
    """
    
    def __init__(self, temp_dir: str = 'temp', output_dir: str = 'exports'):
        self.temp_dir = temp_dir
        self.output_dir = output_dir
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
    
    def process_video(self, video_path: str, selected_brands: Optional[List[str]] = None,
                     aspect_ratio: str = '9:16', video_id: str = 'video') -> Dict:
        """
        Process a downloaded video through the complete pipeline
        
        Args:
            video_path: Path to downloaded video
            selected_brands: List of brand names to export (None = all brands)
            aspect_ratio: Target aspect ratio for crop (9:16, 1:1, 4:5, 16:9)
            video_id: Identifier for this video
        
        Returns:
            Dictionary with results and output paths
        """
        results = {
            'success': False,
            'stages': {},
            'outputs': [],
            'errors': []
        }
        
        try:
            # STAGE 1: Crop
            print("\n[STAGE 1/4] Cropping video...")
            crop_dir = os.path.join(self.temp_dir, 'crop')
            cropped_path, crop_metadata = launch_crop_ui(
                video_path, 
                temp_dir=crop_dir,
                aspect_ratio=aspect_ratio
            )
            results['stages']['crop'] = {
                'path': cropped_path,
                'metadata': crop_metadata
            }
            print(f"  ✓ Cropped to {aspect_ratio}: {cropped_path}")
            
            # STAGE 2: Load brands
            print("\n[STAGE 2/4] Loading brand configurations...")
            all_brands = get_brands()
            
            # Filter by selected brands
            if selected_brands:
                brands = [b for b in all_brands if b.get('name') in selected_brands or b.get('display_name') in selected_brands]
            else:
                brands = all_brands
            
            if not brands:
                raise ValueError(f"No brands found. Selected: {selected_brands}")
            
            results['stages']['brands'] = {
                'total': len(all_brands),
                'selected': len(brands),
                'names': [b.get('display_name', b.get('name')) for b in brands]
            }
            print(f"  ✓ Loaded {len(brands)} brand(s): {', '.join(results['stages']['brands']['names'])}")
            
            # STAGE 3: Logo editor (use first brand as reference)
            print("\n[STAGE 3/4] Setting logo position...")
            logo_settings = launch_logo_editor(
                cropped_path,
                brands[0],  # Use first brand for logo positioning
                crop_metadata
            )
            results['stages']['logo'] = logo_settings
            print(f"  ✓ Logo positioned at ({logo_settings['logo_settings']['x']}, {logo_settings['logo_settings']['y']})")
            print(f"    Size: {logo_settings['logo_settings']['width']}x{logo_settings['logo_settings']['height']}")
            print(f"    Safe zones enforced: 5% margin")
            
            # STAGE 4: Multi-brand export
            print(f"\n[STAGE 4/4] Exporting to {len(brands)} brand(s)...")
            output_paths = process_video(
                cropped_path,
                brands,
                logo_settings,
                self.output_dir,
                video_id
            )
            results['outputs'] = output_paths
            print(f"  ✓ Exported {len(output_paths)} video(s)")
            
            results['success'] = True
            
        except Exception as e:
            results['errors'].append(str(e))
            print(f"\n✗ Error: {e}")
        
        return results
    
    def get_available_brands(self) -> List[Dict]:
        """Get list of all available brands"""
        return get_brands()
    
    def print_summary(self, results: Dict):
        """Print processing summary"""
        print("\n" + "=" * 60)
        print("ORCHESTRATOR SUMMARY")
        print("=" * 60)
        
        if results['success']:
            print("✓ Status: SUCCESS")
        else:
            print("✗ Status: FAILED")
        
        print("\nStages:")
        for stage_name, stage_data in results.get('stages', {}).items():
            print(f"  • {stage_name.upper()}: ✓")
            if isinstance(stage_data, dict) and 'path' in stage_data:
                print(f"    Path: {stage_data['path']}")
        
        if results.get('outputs'):
            print(f"\nOutputs ({len(results['outputs'])}):")
            for path in results['outputs']:
                print(f"  • {path}")
        
        if results.get('errors'):
            print(f"\nErrors ({len(results['errors'])}):")
            for error in results['errors']:
                print(f"  • {error}")
        
        print("=" * 60)


def orchestrate(video_path: str, selected_brands: Optional[List[str]] = None,
                aspect_ratio: str = '9:16', video_id: str = 'video',
                temp_dir: str = 'temp', output_dir: str = 'exports') -> Dict:
    """
    Convenience function to run the complete orchestration pipeline
    
    Args:
        video_path: Path to downloaded video
        selected_brands: List of brand names to export (None = all)
        aspect_ratio: Target aspect ratio (9:16, 1:1, 4:5, 16:9)
        video_id: Video identifier
        temp_dir: Temporary files directory
        output_dir: Output directory
    
    Returns:
        Results dictionary
    """
    orch = WTFOrchestrator(temp_dir, output_dir)
    results = orch.process_video(video_path, selected_brands, aspect_ratio, video_id)
    orch.print_summary(results)
    return results
