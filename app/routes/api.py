"""JSON and streaming API routes for detection, uploads, analytics, and exports."""

from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_from_directory

from app.config import Config
from app.services.camera import CameraStream
from app.services.detector import DetectionService, ModelLoadError
from app.services.video_processor import VideoProcessor
from app.utils.database import (
    clear_detection_history,
    create_job,
    export_history_csv,
    get_analytics,
    get_history,
    get_job,
    get_jobs,
)
from app.utils.files import allowed_file, unique_filename


api_bp = Blueprint("api", __name__)

try:
    detector = DetectionService()
    camera_stream = CameraStream(detector)
    video_processor = VideoProcessor(detector)
    startup_error = None
except ModelLoadError as exc:
    detector = None
    camera_stream = None
    video_processor = None
    startup_error = str(exc)


@api_bp.get("/health")
def health():
    """Return runtime readiness and selected inference device."""
    return jsonify(
        {
            "ready": startup_error is None,
            "error": startup_error,
            "device": detector.device if detector else None,
            "model": str(Config.DEFAULT_MODEL_PATH),
        }
    )


@api_bp.post("/upload")
def upload_video():
    """Accept an uploaded video, validate it, and enqueue background processing."""
    if startup_error:
        return jsonify({"error": startup_error}), 500
    if "video" not in request.files:
        return jsonify({"error": "No video file was provided."}), 400
    file = request.files["video"]
    if not file.filename:
        return jsonify({"error": "Choose a video before uploading."}), 400
    if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
        return jsonify({"error": "Unsupported format. Upload MP4, AVI, or MOV."}), 400
    filename = unique_filename(file)
    input_path = Config.UPLOAD_FOLDER / filename
    file.save(input_path)
    job_id = create_job(Config.DATABASE_PATH, filename)
    video_processor.process_async(job_id, input_path)
    return jsonify({"message": "Upload accepted", "job_id": job_id, "filename": filename})


@api_bp.get("/jobs/<int:job_id>")
def job_status(job_id: int):
    """Return processing progress for an uploaded video."""
    job = get_job(Config.DATABASE_PATH, job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    progress = 0
    if job["total_frames"]:
        progress = round((job["processed_frames"] / job["total_frames"]) * 100, 2)
    job["progress"] = progress
    return jsonify(job)


@api_bp.get("/jobs")
def jobs():
    """Return recent upload processing jobs."""
    limit = min(int(request.args.get("limit", 50)), 200)
    rows = get_jobs(Config.DATABASE_PATH, limit=limit)
    for job in rows:
        progress = 0
        if job["total_frames"]:
            progress = round((job["processed_frames"] / job["total_frames"]) * 100, 2)
        job["progress"] = progress
    return jsonify(rows)


@api_bp.get("/live_feed")
def live_feed():
    """Stream annotated webcam frames to the browser as MJPEG."""
    if startup_error:
        return jsonify({"error": startup_error}), 500
    return Response(camera_stream.generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@api_bp.post("/camera/stop")
def stop_camera():
    """Stop the webcam stream and release the camera."""
    if camera_stream:
        camera_stream.stop()
    return jsonify({"message": "Camera stopped"})


@api_bp.post("/screenshot")
def screenshot():
    """Capture and save a screenshot from the current webcam frame."""
    if not camera_stream:
        return jsonify({"error": startup_error or "Camera service is unavailable."}), 500
    filename = camera_stream.capture_screenshot()
    if not filename:
        return jsonify({"error": camera_stream.error or "No frame is available yet."}), 400
    return jsonify({"message": "Screenshot captured", "filename": filename})


@api_bp.get("/analytics")
def analytics():
    """Return database analytics merged with live detector statistics."""
    data = get_analytics(Config.DATABASE_PATH)
    if detector:
        data.update(
            {
                "fps": detector.stats["fps"],
                "processing_time_ms": detector.stats["processing_time_ms"],
                "device": detector.stats["device"],
                "tracker": detector.stats["tracker"],
            }
        )
    return jsonify(data)


@api_bp.post("/analytics/clear")
def clear_analytics():
    """Clear detection history used by the dashboard and history table."""
    removed = clear_detection_history(Config.DATABASE_PATH)
    if detector:
        detector.stats.update(
            {
                "total_detected_objects": 0,
                "class_counts": {},
                "active_tracked_objects": 0,
                "overall_detection_accuracy": 0.0,
            }
        )
    return jsonify({"message": "Dashboard data cleared", "removed": removed})


@api_bp.get("/history")
def history():
    """Return recent detection history rows."""
    limit = min(int(request.args.get("limit", 200)), 1000)
    return jsonify(get_history(Config.DATABASE_PATH, limit=limit))


@api_bp.get("/export/csv")
def export_csv():
    """Export detection history as a downloadable CSV file."""
    filename = f"detection_history_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    path = export_history_csv(Config.DATABASE_PATH, Config.LOG_FOLDER / filename)
    return send_from_directory(path.parent, path.name, as_attachment=True)


@api_bp.get("/download/<path:filename>")
def download_processed(filename: str):
    """Download a processed video from the output directory."""
    path = Path(filename).name
    if not (Config.PROCESSED_FOLDER / path).exists():
        return jsonify({"error": "Processed video not found."}), 404
    return send_from_directory(Config.PROCESSED_FOLDER, path, as_attachment=True)
