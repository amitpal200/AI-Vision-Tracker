"""File validation and naming utilities for uploaded and generated videos."""

from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


def allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    """Return True when a filename has one of the configured video extensions."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def unique_filename(file: FileStorage) -> str:
    """Build a safe unique filename while preserving the original extension."""
    original = secure_filename(file.filename or "video.mp4")
    suffix = Path(original).suffix.lower()
    stem = Path(original).stem or "upload"
    return f"{stem}_{uuid4().hex[:10]}{suffix}"


def output_video_name(input_name: str) -> str:
    """Generate a processed MP4 output filename for a source video."""
    return f"processed_{Path(input_name).stem}.mp4"
