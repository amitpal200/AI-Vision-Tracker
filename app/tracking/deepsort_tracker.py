"""Deep SORT adapter with a lightweight fallback for missing dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class TrackResult:
    """Normalized track output used by the drawing and logging pipeline."""

    track_id: str
    bbox: tuple[int, int, int, int]
    class_name: str
    confidence: float


class SimpleIoUTracker:
    """Small fallback tracker that preserves IDs by matching boxes with IoU."""

    def __init__(self, max_age: int = 30, iou_threshold: float = 0.3) -> None:
        """Initialize fallback track memory."""
        self.max_age = max_age
        self.iou_threshold = iou_threshold
        self.next_id = 1
        self.tracks: dict[str, dict] = {}

    def update(self, detections: list[dict], frame=None) -> list[TrackResult]:
        """Assign stable IDs to detections using class-aware IoU matching."""
        for track in self.tracks.values():
            track["age"] += 1
        results: list[TrackResult] = []
        for detection in detections:
            best_id = None
            best_iou = 0.0
            for track_id, track in self.tracks.items():
                if track["class_name"] != detection["class_name"]:
                    continue
                score = self._iou(track["bbox"], detection["bbox"])
                if score > best_iou:
                    best_iou = score
                    best_id = track_id
            if best_id and best_iou >= self.iou_threshold:
                track_id = best_id
            else:
                track_id = str(self.next_id)
                self.next_id += 1
            self.tracks[track_id] = {
                "bbox": detection["bbox"],
                "class_name": detection["class_name"],
                "confidence": detection["confidence"],
                "age": 0,
            }
            results.append(
                TrackResult(
                    track_id=track_id,
                    bbox=detection["bbox"],
                    class_name=detection["class_name"],
                    confidence=detection["confidence"],
                )
            )
        self.tracks = {
            track_id: track
            for track_id, track in self.tracks.items()
            if track["age"] <= self.max_age
        }
        return results

    @staticmethod
    def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        """Compute intersection-over-union for two xyxy boxes."""
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        area_a = max(1, ax2 - ax1) * max(1, ay2 - ay1)
        area_b = max(1, bx2 - bx1) * max(1, by2 - by1)
        return intersection / float(area_a + area_b - intersection)


class ObjectTracker:
    """Wrap Deep SORT and expose a stable update method for the app."""

    def __init__(self, max_age: int = 30) -> None:
        """Create a Deep SORT tracker, falling back to IoU tracking if unavailable."""
        try:
            from deep_sort_realtime.deepsort_tracker import DeepSort

            self.backend = "Deep SORT"
            self.tracker = DeepSort(max_age=max_age, n_init=3, max_cosine_distance=0.4)
        except Exception:
            self.backend = "Simple IoU fallback"
            self.tracker = SimpleIoUTracker(max_age=max_age)

    def update(self, detections: list[dict], frame) -> List[TrackResult]:
        """Return confirmed tracks for current frame detections."""
        if self.backend != "Deep SORT":
            return self.tracker.update(detections, frame=frame)
        formatted = []
        class_lookup = {}
        for index, detection in enumerate(detections):
            x1, y1, x2, y2 = detection["bbox"]
            formatted.append(([x1, y1, x2 - x1, y2 - y1], detection["confidence"], detection["class_name"]))
            class_lookup[index] = detection
        tracks = self.tracker.update_tracks(formatted, frame=frame)
        results = []
        for track in tracks:
            if not track.is_confirmed():
                continue
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            class_name = self._track_value(track, "get_det_class", "det_class", "object")
            confidence = float(self._track_value(track, "get_det_conf", "det_conf", 0.0) or 0.0)
            results.append(
                TrackResult(
                    track_id=str(track.track_id),
                    bbox=(x1, y1, x2, y2),
                    class_name=class_name,
                    confidence=confidence,
                )
            )
        return results

    @staticmethod
    def _track_value(track, method_name: str, attribute_name: str, default):
        """Read class/confidence values across different deep-sort-realtime versions."""
        method = getattr(track, method_name, None)
        if callable(method):
            value = method()
            return default if value is None else value
        value = getattr(track, attribute_name, default)
        return default if value is None else value
