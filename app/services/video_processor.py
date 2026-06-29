"""Video upload processing, output writing, screenshots, and logs."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import psutil

from app.config import Config
from app.services.detector import DetectionService
from app.utils.database import log_detections, update_job
from app.utils.files import output_video_name


class VideoProcessor:
    """Process uploaded video files in a background thread."""

    def __init__(self, detector: DetectionService) -> None:
        """Store the shared detector used for upload processing."""
        self.detector = detector

    def process_async(self, job_id: int, input_path: Path) -> None:
        """Start processing without blocking the Flask request thread."""
        thread = threading.Thread(target=self.process_video, args=(job_id, input_path), daemon=True)
        thread.start()

    def process_video(self, job_id: int, input_path: Path) -> None:
        """Read a video, annotate each frame, save output, and update job progress."""
        start = time.perf_counter()
        output_name = output_video_name(input_path.name)
        output_path = Config.PROCESSED_FOLDER / output_name
        events_buffer = []
        try:
            if psutil.virtual_memory().available < 300 * 1024 * 1024:
                raise MemoryError("Low memory: at least 300 MB of free RAM is recommended.")
            capture = cv2.VideoCapture(str(input_path))
            if not capture.isOpened():
                raise ValueError("OpenCV could not read this file. It may be corrupted or unsupported.")
            fps = capture.get(cv2.CAP_PROP_FPS) or 25
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            writer = cv2.VideoWriter(
                str(output_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                fps,
                (width, height),
            )
            update_job(
                Config.DATABASE_PATH,
                job_id,
                status="processing",
                message="Processing frames",
                output_file=output_name,
                total_frames=total_frames,
            )
            frame_number = 0
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                annotated, events, stats = self.detector.detect_and_track(frame)
                for event in events:
                    event.update(
                        {
                            "source_type": "upload",
                            "file_name": input_path.name,
                            "frame_number": frame_number,
                        }
                    )
                events_buffer.extend(events)
                if len(events_buffer) >= 100:
                    log_detections(Config.DATABASE_PATH, events_buffer)
                    events_buffer.clear()
                writer.write(annotated)
                frame_number += 1
                if frame_number % 10 == 0:
                    update_job(
                        Config.DATABASE_PATH,
                        job_id,
                        processed_frames=frame_number,
                        fps=stats["fps"],
                        processing_time=round(time.perf_counter() - start, 2),
                    )
            if events_buffer:
                log_detections(Config.DATABASE_PATH, events_buffer)
            capture.release()
            writer.release()
            update_job(
                Config.DATABASE_PATH,
                job_id,
                status="completed",
                message="Processing completed",
                processed_frames=frame_number,
                processing_time=round(time.perf_counter() - start, 2),
            )
        except MemoryError as exc:
            update_job(Config.DATABASE_PATH, job_id, status="failed", message=str(exc))
        except Exception as exc:
            update_job(Config.DATABASE_PATH, job_id, status="failed", message=str(exc))
