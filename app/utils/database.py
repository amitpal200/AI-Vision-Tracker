"""SQLite persistence helpers for detection history, jobs, and analytics."""

import csv
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS detection_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source_type TEXT NOT NULL,
    file_name TEXT,
    frame_number INTEGER,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    track_id TEXT,
    bbox_x INTEGER,
    bbox_y INTEGER,
    bbox_w INTEGER,
    bbox_h INTEGER
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source_file TEXT NOT NULL,
    output_file TEXT,
    status TEXT NOT NULL,
    message TEXT,
    fps REAL DEFAULT 0,
    total_frames INTEGER DEFAULT 0,
    processed_frames INTEGER DEFAULT 0,
    processing_time REAL DEFAULT 0
);
"""


@contextmanager
def connect(db_path: Path):
    """Open a SQLite connection and commit changes when the block succeeds."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(db_path: Path) -> None:
    """Create database tables if the project is running for the first time."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)


def log_detection(db_path: Path, event: dict) -> None:
    """Insert one tracked detection into the history table."""
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO detection_events (
                timestamp, source_type, file_name, frame_number, class_name,
                confidence, track_id, bbox_x, bbox_y, bbox_w, bbox_h
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("timestamp", datetime.utcnow().isoformat()),
                event.get("source_type", "unknown"),
                event.get("file_name"),
                event.get("frame_number", 0),
                event.get("class_name", "object"),
                float(event.get("confidence", 0)),
                str(event.get("track_id", "")),
                int(event.get("bbox_x", 0)),
                int(event.get("bbox_y", 0)),
                int(event.get("bbox_w", 0)),
                int(event.get("bbox_h", 0)),
            ),
        )


def log_detections(db_path: Path, events: Iterable[dict]) -> None:
    """Insert many detection events efficiently in a single transaction."""
    rows = []
    for event in events:
        rows.append(
            (
                event.get("timestamp", datetime.utcnow().isoformat()),
                event.get("source_type", "unknown"),
                event.get("file_name"),
                event.get("frame_number", 0),
                event.get("class_name", "object"),
                float(event.get("confidence", 0)),
                str(event.get("track_id", "")),
                int(event.get("bbox_x", 0)),
                int(event.get("bbox_y", 0)),
                int(event.get("bbox_w", 0)),
                int(event.get("bbox_h", 0)),
            )
        )
    if not rows:
        return
    with connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO detection_events (
                timestamp, source_type, file_name, frame_number, class_name,
                confidence, track_id, bbox_x, bbox_y, bbox_w, bbox_h
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def create_job(db_path: Path, source_file: str) -> int:
    """Create a processing job and return its database identifier."""
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO processing_jobs (created_at, source_file, status, message)
            VALUES (?, ?, ?, ?)
            """,
            (datetime.utcnow().isoformat(), source_file, "queued", "Waiting to start"),
        )
        return int(cursor.lastrowid)


def update_job(db_path: Path, job_id: int, **fields) -> None:
    """Patch selected columns for a processing job."""
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [job_id]
    with connect(db_path) as connection:
        connection.execute(f"UPDATE processing_jobs SET {columns} WHERE id = ?", values)


def get_job(db_path: Path, job_id: int) -> dict | None:
    """Return one processing job as a dictionary."""
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_jobs(db_path: Path, limit: int = 50) -> list[dict]:
    """Return recent upload processing jobs for the results page."""
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM processing_jobs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_history(db_path: Path, limit: int = 200) -> list[dict]:
    """Return recent detection events for the history table and API."""
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM detection_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_analytics(db_path: Path) -> dict:
    """Aggregate database statistics for dashboard charts and counters."""
    history = get_history(db_path, limit=5000)
    counts = Counter(row["class_name"] for row in history)
    unique_tracks = {row["track_id"] for row in history if row["track_id"]}
    average_confidence = (
        sum(float(row["confidence"]) for row in history) / len(history) if history else 0
    )
    return {
        "total_detected_objects": len(history),
        "class_counts": dict(counts),
        "active_tracked_objects": len(unique_tracks),
        "overall_detection_accuracy": round(average_confidence * 100, 2),
        "recent_events": history[:25],
    }


def export_history_csv(db_path: Path, output_path: Path) -> Path:
    """Write the detection history to a CSV file and return the generated path."""
    rows = get_history(db_path, limit=100000)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "id",
            "timestamp",
            "source_type",
            "file_name",
            "frame_number",
            "class_name",
            "confidence",
            "track_id",
            "bbox_x",
            "bbox_y",
            "bbox_w",
            "bbox_h",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path
