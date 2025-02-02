import os
import logging
from logging.handlers import RotatingFileHandler

# Base directory of the application
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Directory configurations
STATIC_DIR = os.path.join(BASE_DIR, "static")
CONVERTED_DIR = os.path.join(STATIC_DIR, "converted")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Create necessary directories
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(CONVERTED_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Logging configuration
LOG_FILE = os.path.join(LOGS_DIR, "app.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

handler = RotatingFileHandler(LOG_FILE, maxBytes=10000000, backupCount=5)
handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
))

logger = logging.getLogger(__name__)
logger.addHandler(handler)

# Disable PIL debug logging
logging.getLogger("PIL").setLevel(logging.WARNING)

# Application configurations
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-production'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'svg'}