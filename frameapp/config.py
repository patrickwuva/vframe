import os
from pathlib import Path


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    BASE_DIR = Path(__file__).resolve().parents[1]

    # Default to a local directory on the Pi OS filesystem (NVMe root disk).
    MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/home/pi/frame-media"))
    INCOMING_DIR = MEDIA_ROOT / "incoming"
    LIBRARY_DIR = MEDIA_ROOT / "library"
    THUMBS_DIR = MEDIA_ROOT / ".thumbs"
    META_DIR = MEDIA_ROOT / ".meta"

    DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "instance" / "frame.db")))

    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "512")) * 1024 * 1024

    ALLOWED_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".mp4",
        ".mov",
        ".m4v",
        ".avi",
        ".mkv",
        ".webm",
    }

    DEFAULT_DURATION = int(os.getenv("DEFAULT_DURATION", "8"))
    DEFAULT_TRANSITION = os.getenv("DEFAULT_TRANSITION", "fade")
