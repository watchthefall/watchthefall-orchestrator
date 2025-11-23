import os

# Resolve project paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(APP_DIR, '..'))

IMPORTS_BRANDS_DIR = os.path.join(PROJECT_ROOT, 'imports', 'brands')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
UI_DIR = os.path.join(APP_DIR, 'ui')

# FFmpeg/FFprobe binaries (override with environment variables if needed)
FFMPEG_BIN = os.environ.get('FFMPEG_PATH', 'ffmpeg')
FFPROBE_BIN = os.environ.get('FFPROBE_PATH', 'ffprobe')

# Ensure necessary directories exist at runtime
os.makedirs(IMPORTS_BRANDS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
