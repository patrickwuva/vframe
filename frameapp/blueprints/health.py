from datetime import datetime, timezone

from flask import Blueprint, jsonify


bp = Blueprint("health", __name__)


@bp.get("/healthz")
def healthz():
    return jsonify(
        {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
