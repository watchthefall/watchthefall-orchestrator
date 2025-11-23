"""
Logo Background Cleaner - Remove square backgrounds and create circular transparent PNGs
Preprocesses brand logos for clean overlay on videos
"""
import os
import sys
from PIL import Image, ImageDraw, ImageChops
import glob

def detect_circular_region(img: Image.Image) -> tuple:
    """
    Detect the circular logo region in the image
    Returns (center_x, center_y, radius)
    """
    width, height = img.size
    
    # Assume logo is centered and takes up 80% of the smaller dimension
    min_dim = min(width, height)
    radius = int(min_dim * 0.4)
    
    center_x = width // 2
    center_y = height // 2
    
    return (center_x, center_y, radius)

def create_circular_mask(size: tuple, center: tuple, radius: int) -> Image.Image:
    """Create a circular alpha mask"""
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    
    center_x, center_y = center
    bbox = (
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius
    )
    
    draw.ellipse(bbox, fill=255)
    return mask

def clean_logo_background(input_path: str, output_path: str) -> bool:
    """
    Remove square background and create circular transparent PNG
    
    Args:
        input_path: Path to original logo
        output_path: Path for cleaned logo
    
    Returns:
        True if successful
    """
    try:
        # Open image
        img = Image.open(input_path)
        
        # Convert to RGBA if needed
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Detect circular region
        center_x, center_y, radius = detect_circular_region(img)
        
        # Create circular mask
        mask = create_circular_mask(img.size, (center_x, center_y), radius)
        
        # Apply mask to alpha channel
        img_data = img.getdata()
        mask_data = mask.getdata()
        
        new_data = []
        for i, pixel in enumerate(img_data):
            r, g, b, a = pixel
            # Apply circular mask
            new_alpha = min(a, mask_data[i])
            new_data.append((r, g, b, new_alpha))
        
        img.putdata(new_data)
        
        # Crop to circular bounds with some padding
        padding = int(radius * 0.1)
        crop_box = (
            max(0, center_x - radius - padding),
            max(0, center_y - radius - padding),
            min(img.width, center_x + radius + padding),
            min(img.height, center_y + radius + padding)
        )
        img = img.crop(crop_box)
        
        # Save as PNG with transparency
        img.save(output_path, 'PNG', optimize=True)
        
        return True
        
    except Exception as e:
        print(f"Error cleaning logo {input_path}: {e}")
        return False

def process_all_logos(logos_dir: str, output_dir: str):
    """
    Process all logos in directory
    
    Args:
        logos_dir: Directory containing original logos
        output_dir: Directory for cleaned logos
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Find all PNG logos
    logo_files = glob.glob(os.path.join(logos_dir, '*.png'))
    
    print(f"Found {len(logo_files)} logos to process")
    
    processed = 0
    skipped = 0
    
    for logo_path in logo_files:
        logo_name = os.path.basename(logo_path)
        output_path = os.path.join(output_dir, logo_name)
        
        # Skip if already processed
        if os.path.exists(output_path):
            print(f"  Skipping {logo_name} (already exists)")
            skipped += 1
            continue
        
        print(f"  Processing {logo_name}...")
        success = clean_logo_background(logo_path, output_path)
        
        if success:
            processed += 1
            print(f"    ✓ Saved to logos_clean/")
        else:
            skipped += 1
    
    print(f"\nComplete: {processed} processed, {skipped} skipped")

if __name__ == '__main__':
    # Determine project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    
    logos_dir = os.path.join(project_root, 'imports', 'brands', 'wtf_orchestrator', 'logos')
    output_dir = os.path.join(project_root, 'imports', 'brands', 'wtf_orchestrator', 'logos_clean')
    
    if not os.path.exists(logos_dir):
        print(f"Error: Logos directory not found: {logos_dir}")
        sys.exit(1)
    
    print("Logo Background Cleaner")
    print("=" * 50)
    print(f"Source: {logos_dir}")
    print(f"Output: {output_dir}")
    print("=" * 50)
    
    process_all_logos(logos_dir, output_dir)
