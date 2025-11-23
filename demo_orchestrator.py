"""
Demo script to test the complete WTF Orchestrator pipeline
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.orchestrator import orchestrate
from app.brand_loader import get_brands

def main():
    print("=" * 70)
    print("WATCHTHEFALL ORCHESTRATOR V2 - DEMO")
    print("=" * 70)
    
    # Show available brands
    print("\n[1/5] Loading available brands...")
    brands = get_brands()
    print(f"✓ Found {len(brands)} brands:")
    for i, brand in enumerate(brands, 1):
        print(f"  {i:2d}. {brand.get('display_name', brand.get('name'))}")
    
    # Demo configuration
    print("\n[2/5] Demo Configuration:")
    print("  • This demo would process a video through:")
    print("    1. Crop Stage (pinch-to-zoom UI)")
    print("    2. Logo Editor (drag & position)")
    print("    3. Multi-brand Export (adaptive watermarks)")
    
    # Example brands to export
    demo_brands = ['ScotlandWTF', 'EnglandWTF', 'AIWTF']
    print(f"\n[3/5] Selected brands for export: {', '.join(demo_brands)}")
    
    # Pipeline stages
    print("\n[4/5] Pipeline Stages:")
    print("  ✓ CROP MODULE")
    print("    - Pinch-to-zoom gesture support")
    print("    - Drag to reposition")
    print("    - Aspect ratios: 9:16, 1:1, 4:5, 16:9")
    print("    - Optional rotation (0°, 90°, 180°, 270°)")
    
    print("\n  ✓ LOGO EDITOR")
    print("    - Pinch-to-resize logo")
    print("    - Drag to position")
    print("    - 5% safe zone enforcement")
    print("    - Background-removed circular logos (logos_clean/)")
    
    print("\n  ✓ VIDEO PROCESSOR")
    print("    - Apply universal template (1080x1920)")
    print("    - Overlay brand-specific logo")
    print("    - Adaptive watermark opacity (10-20%)")
    print("      • Bright videos → 10% opacity")
    print("      • Dark videos → 20% opacity")
    print("    - Safe zone margins (5%)")
    
    print("\n  ✓ MULTI-BRAND EXPORT")
    print("    - One master crop → N branded outputs")
    print("    - Exports to: exports/<brand>/<video_id>.mp4")
    print("    - Gallery-ready for phone automation")
    
    # Show processed logos
    print("\n[5/5] Background-Removed Logos:")
    logos_clean_dir = os.path.join('imports', 'brands', 'wtf_orchestrator', 'logos_clean')
    if os.path.exists(logos_clean_dir):
        cleaned_logos = [f for f in os.listdir(logos_clean_dir) if f.endswith('.png')]
        print(f"  ✓ {len(cleaned_logos)} logos cleaned and ready")
        print(f"  Location: {logos_clean_dir}")
    else:
        print("  ⚠ Run: python -m scripts.logo_background_cleaner")
    
    print("\n" + "=" * 70)
    print("USAGE EXAMPLE:")
    print("=" * 70)
    print("""
from app.orchestrator import orchestrate

# Process a video
results = orchestrate(
    video_path='path/to/downloaded_video.mp4',
    selected_brands=['ScotlandWTF', 'EnglandWTF', 'AIWTF'],
    aspect_ratio='9:16',
    video_id='demo_video_001'
)

# Check results
if results['success']:
    print(f"Exported {len(results['outputs'])} videos")
    for path in results['outputs']:
        print(f"  • {path}")
""")
    
    print("=" * 70)
    print("READY FOR PHONE AUTOMATION!")
    print("=" * 70)
    print("""
Next Steps:
1. Download video via yt-dlp
2. Open crop UI on phone (crop_editor.html)
3. Open logo editor on phone (logo_editor.html)
4. Export to multiple brands automatically
5. Videos saved to phone gallery
""")
    print("=" * 70)

if __name__ == '__main__':
    main()
