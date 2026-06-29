"""Central configuration values used by Flask, detection, tracking, and storage."""

from pathlib import Path


class Config:
    """Application settings kept in one place for easy deployment changes."""

    BASE_DIR = Path(__file__).resolve().parent.parent
    SECRET_KEY = "change-this-secret-key-before-deployment"
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024

    UPLOAD_FOLDER = BASE_DIR / "uploads"
    PROCESSED_FOLDER = BASE_DIR / "processed"
    DATABASE_FOLDER = BASE_DIR / "database"
    LOG_FOLDER = BASE_DIR / "logs"
    MODEL_FOLDER = BASE_DIR / "models"
    SCREENSHOT_FOLDER = PROCESSED_FOLDER / "screenshots"

    DATABASE_PATH = DATABASE_FOLDER / "detections.db"
    ROOT_MODEL_PATH = BASE_DIR / "yolov8n.pt"
    MODEL_PATH = MODEL_FOLDER / "yolov8n.pt"
    DEFAULT_MODEL_PATH = MODEL_PATH if MODEL_PATH.exists() else ROOT_MODEL_PATH

    ALLOWED_EXTENSIONS = {"mp4", "avi", "mov"}
    CONFIDENCE_THRESHOLD = 0.35
    IOU_THRESHOLD = 0.45
    IMAGE_SIZE = 640
    CAMERA_INDEX = 0

    REQUIRED_DIRS = [
        UPLOAD_FOLDER,
        PROCESSED_FOLDER,
        DATABASE_FOLDER,
        LOG_FOLDER,
        MODEL_FOLDER,
        SCREENSHOT_FOLDER,
    ]
