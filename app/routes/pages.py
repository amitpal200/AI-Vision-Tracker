"""HTML page routes for the portfolio web interface."""

from flask import Blueprint, render_template


pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def home():
    """Render the animated project landing page."""
    return render_template("home.html", title="Home")


@pages_bp.get("/about")
def about():
    """Render project explanation and architecture notes."""
    return render_template("about.html", title="About")


@pages_bp.get("/live")
def live_camera():
    """Render the live webcam detection page."""
    return render_template("live.html", title="Live Camera Detection")


@pages_bp.get("/upload")
def upload():
    """Render the video upload page."""
    return render_template("upload.html", title="Upload Video")


@pages_bp.get("/results")
def results():
    """Render detection results and job progress page."""
    return render_template("results.html", title="Detection Results")


@pages_bp.get("/dashboard")
def dashboard():
    """Render Chart.js analytics dashboard."""
    return render_template("dashboard.html", title="Analytics Dashboard")


@pages_bp.get("/contact")
def contact():
    """Render contact and portfolio call-to-action page."""
    return render_template("contact.html", title="Contact")
