from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, send_from_directory

from frameapp.blueprints.admin import bp as admin_bp
from frameapp.blueprints.api import bp as api_bp
from frameapp.blueprints.health import bp as health_bp
from frameapp.blueprints.player import bp as player_bp
from frameapp.config import Config
from frameapp.db import init_app as init_db_app
from frameapp.db import init_db
from frameapp.worker import start_worker


def create_app(config_object=Config, start_background_worker: bool = True) -> Flask:
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )
    app.config.from_object(config_object)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    for key in ("MEDIA_ROOT", "INCOMING_DIR", "LIBRARY_DIR", "THUMBS_DIR", "META_DIR"):
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)

    init_db_app(app)

    with app.app_context():
        init_db()

    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(player_bp)
    app.register_blueprint(health_bp)

    @app.get("/media/<path:path>")
    def serve_media(path: str):
        media_root = Path(app.config["MEDIA_ROOT"])
        target = media_root / path
        if not target.exists() or not target.is_file():
            abort(404)
        return send_from_directory(media_root, path)

    @app.get("/thumbs/<path:filename>")
    def serve_thumbs(filename: str):
        thumbs_dir = Path(app.config["THUMBS_DIR"])
        target = thumbs_dir / filename
        if not target.exists() or not target.is_file():
            abort(404)
        return send_from_directory(thumbs_dir, filename)

    if start_background_worker:
        start_worker(app)

    return app
