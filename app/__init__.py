"""Flask application factory and project bootstrap logic."""

from pathlib import Path

from flask import Flask

from app.config import Config
from app.routes.pages import pages_bp
from app.routes.api import api_bp
from app.utils.database import init_db


def create_app() -> Flask:
    """Create, configure, and return the Flask application instance."""
    app = Flask(
        __name__,
        template_folder=str(Config.BASE_DIR / "templates"),
        static_folder=str(Config.BASE_DIR / "static"),
    )
    app.config.from_object(Config)
    ensure_directories()
    init_db(Config.DATABASE_PATH)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    return app


def ensure_directories() -> None:
    """Create runtime directories needed for uploads, outputs, logs, and data."""
    for directory in Config.REQUIRED_DIRS:
        Path(directory).mkdir(parents=True, exist_ok=True)
