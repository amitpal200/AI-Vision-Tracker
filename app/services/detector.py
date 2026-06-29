"""YOLOv8 detection service, annotation helpers, and runtime statistics."""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from app.config import Config
from app.tracking.deepsort_tracker import ObjectTracker, TrackResult


class ModelLoadError(RuntimeError):
    """Raised when YOLO weights are missing or cannot be loaded."""


class DetectionService:
    """Run YOLOv8 detection, Deep SORT tracking, drawing, and metrics."""

    def __init__(self, model_path: Path | None = None) -> None:
        """Load the YOLO model once and prepare runtime counters."""
        self.model_path = Path(model_path or Config.DEFAULT_MODEL_PATH)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self._load_model()
        self.tracker = ObjectTracker(max_age=30)
        self.stats = {
            "total_detected_objects": 0,
            "class_counts": {},
            "fps": 0.0,
            "processing_time_ms": 0.0,
            "active_tracked_objects": 0,
            "overall_detection_accuracy": 0.0,
            "device": self.device,
            "tracker": self.tracker.backend,
            "last_updated": None,
        }

    def _load_model(self) -> YOLO:
        """Load YOLOv8 weights and move the model to CUDA when available."""
        if not self.model_path.exists():
            raise ModelLoadError(
                f"YOLO weights not found at {self.model_path}. Place yolov8n.pt in the project root or models folder."
            )
        try:
            model = YOLO(str(self.model_path))
            model.to(self.device)
            return model
        except Exception as exc:
            raise ModelLoadError(f"Unable to load YOLO model: {exc}") from exc

    def detect_and_track(self, frame: np.ndarray) -> tuple[np.ndarray, list[dict], dict]:
        """Detect objects, update tracks, annotate the frame, and return metrics."""
        start = time.perf_counter()
        detections = self._detect(frame)
        tracks = self.tracker.update(detections, frame)
        annotated = self._draw(frame.copy(), tracks)
        elapsed = time.perf_counter() - start
        frame_stats = self._update_stats(tracks, elapsed)
        return annotated, self._events_from_tracks(tracks), frame_stats

    def _detect(self, frame: np.ndarray) -> list[dict]:
        """Run YOLO inference and normalize bounding boxes for the tracker."""
        results = self.model.predict(
            source=frame,
            conf=Config.CONFIDENCE_THRESHOLD,
            iou=Config.IOU_THRESHOLD,
            imgsz=Config.IMAGE_SIZE,
            device=self.device,
            verbose=False,
        )
        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                class_name = self.model.names.get(class_id, str(class_id))
                detections.append(
                    {
                        "bbox": (x1, y1, x2, y2),
                        "confidence": confidence,
                        "class_name": class_name,
                    }
                )
        return detections

    def _draw(self, frame: np.ndarray, tracks: list[TrackResult]) -> np.ndarray:
        """Draw colored boxes, class labels, confidence, and tracking IDs."""
        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            color = self._color_for_id(track.track_id)
            label = f"ID {track.track_id} | {track.class_name} {track.confidence:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label_y = max(24, y1 - 8)
            cv2.rectangle(frame, (x1, label_y - 22), (x1 + min(360, len(label) * 12), label_y + 4), color, -1)
            cv2.putText(frame, label, (x1 + 6, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        return frame

    def _update_stats(self, tracks: list[TrackResult], elapsed: float) -> dict:
        """Update aggregate service statistics from one processed frame."""
        counts = Counter(track.class_name for track in tracks)
        total = sum(counts.values())
        avg_conf = sum(track.confidence for track in tracks) / total if total else 0
        self.stats.update(
            {
                "total_detected_objects": self.stats["total_detected_objects"] + total,
                "class_counts": dict(counts),
                "fps": round(1 / elapsed, 2) if elapsed > 0 else 0,
                "processing_time_ms": round(elapsed * 1000, 2),
                "active_tracked_objects": total,
                "overall_detection_accuracy": round(avg_conf * 100, 2),
                "device": self.device,
                "tracker": self.tracker.backend,
                "last_updated": datetime.utcnow().isoformat(),
            }
        )
        return dict(self.stats)

    def _events_from_tracks(self, tracks: list[TrackResult]) -> list[dict]:
        """Convert tracks to dictionaries suitable for database logging."""
        events = []
        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            events.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "class_name": track.class_name,
                    "confidence": track.confidence,
                    "track_id": track.track_id,
                    "bbox_x": x1,
                    "bbox_y": y1,
                    "bbox_w": x2 - x1,
                    "bbox_h": y2 - y1,
                }
            )
        return events

    @staticmethod
    def _color_for_id(track_id: str) -> tuple[int, int, int]:
        """Generate a repeatable BGR color for each tracking ID."""
        seed = sum(ord(char) for char in str(track_id))
        return ((37 * seed) % 255, (17 * seed + 80) % 255, (29 * seed + 160) % 255)
