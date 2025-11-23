"""
Portal Configuration
"""
import os

# Portal paths
PORTAL_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PORTAL_ROOT)

# Database
DB_PATH = os.path.join(PORTAL_ROOT, 'db', 'portal.db')

# Upload and output directories
UPLOAD_DIR = os.path.join(PORTAL_ROOT, 'uploads')
OUTPUT_DIR = os.path.join(PORTAL_ROOT, 'outputs')
TEMP_DIR = os.path.join(PORTAL_ROOT, 'temp')

# Logs
LOG_DIR = os.path.join(PORTAL_ROOT, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'portal.log')

# Brand assets
BRANDS_DIR = os.path.join(PROJECT_ROOT, 'imports', 'brands')
TEMPLATE_DIR = os.path.join(BRANDS_DIR, 'wtf_orchestrator')

# FFmpeg
FFMPEG_BIN = os.environ.get('FFMPEG_PATH', 'ffmpeg')
FFPROBE_BIN = os.environ.get('FFPROBE_PATH', 'ffprobe')

# Security
SECRET_KEY = os.environ.get('WTF_SECRET_KEY', 'dev-secret-key-change-in-production')
PORTAL_AUTH_KEY = os.environ.get('WTF_PORTAL_KEY', 'WTF_PORTAL_TEST')

# Job settings
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi'}
CLEANUP_TEMP_AFTER_HOURS = 24

# Ensure directories exist
for directory in [UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR, LOG_DIR, os.path.dirname(DB_PATH)]:
    os.makedirs(directory, exist_ok=True)
