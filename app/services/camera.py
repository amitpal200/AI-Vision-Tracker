"""Threaded webcam capture and MJPEG streaming service."""

from __future__ import annotations

import threading
import time
from datetime import datetime

import cv2

from app.config import Config
from app.services.detector import DetectionService
from app.utils.database import log_detections


class CameraStream:
    """Capture webcam frames in a background thread and stream annotated output."""

    def __init__(self, detector: DetectionService) -> None:
        """Initialize camera state shared by Flask streaming responses."""
        self.detector = detector
        self.capture = None
        self.frame = None
        self.error = None
        self.running = False
        self.lock = threading.Lock()
        self.thread = None

    def start(self) -> None:
        """Open the webcam and start the capture loop if it is not running."""
        if self.running:
            return
        self.capture = cv2.VideoCapture(Config.CAMERA_INDEX)
        if not self.capture.isOpened():
            self.error = "Webcam access failed. Check permissions, camera index, or whether another app is using it."
            self.running = False
            return
        self.error = None
        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop reading frames and release the camera device."""
        self.running = False
        if self.capture:
            self.capture.release()
        self.capture = None

    def _reader(self) -> None:
        """Continuously read raw frames so the browser stream stays responsive."""
        while self.running and self.capture:
            ok, frame = self.capture.read()
            if not ok:
                self.error = "Unable to read from webcam."
                self.running = False
                break
            with self.lock:
                self.frame = frame
            time.sleep(0.005)

    def generate(self):
        """Yield annotated JPEG frames for Flask's multipart MJPEG response."""
        self.start()
        while self.running:
            with self.lock:
                frame = None if self.frame is None else self.frame.copy()
            if frame is None:
                time.sleep(0.05)
                continue
            annotated, events, _stats = self.detector.detect_and_track(frame)
            for event in events:
                event.update({"source_type": "webcam", "file_name": "live_camera", "frame_number": 0})
            log_detections(Config.DATABASE_PATH, events)
            ok, buffer = cv2.imencode(".jpg", annotated)
            if not ok:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"

    def capture_screenshot(self) -> str | None:
        """Save the latest raw camera frame as a screenshot and return its filename."""
        with self.lock:
            frame = None if self.frame is None else self.frame.copy()
        if frame is None:
            return None
        annotated, _events, _stats = self.detector.detect_and_track(frame)
        filename = f"screenshot_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jpg"
        path = Config.SCREENSHOT_FOLDER / filename
        cv2.imwrite(str(path), annotated)
        return filename
