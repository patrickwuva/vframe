from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, url_for

from frameapp import store
from frameapp.media import allowed_extension, detect_media_type
from frameapp.worker import enqueue_media


bp = Blueprint("api", __name__, url_prefix="/api")


def _item_to_player_dict(item, default_duration: int, transition: str):
    duration = item["duration_seconds"]
    if item["type"] == "photo" or duration is None:
        duration = default_duration

    return {
        "media_id": item["media_id"],
        "type": item["type"],
        "duration_seconds": duration,
        "transition": transition,
        "normalized_path": item["normalized_path"],
        "normalized_url": url_for("serve_media", path=item["normalized_path"]),
        "thumb_url": url_for("serve_media", path=item["thumb_path"]) if item["thumb_path"] else None,
        "width": item["width"],
        "height": item["height"],
    }


@bp.get("/status")
def status():
    active_album_id = store.get_active_album_id()
    counts = store.get_counts()
    return jsonify(
        {
            "active_album_id": active_album_id,
            "counts": counts,
        }
    )


@bp.post("/active-album")
def set_active_album():
    data = request.get_json(silent=True) or request.form
    album_id = data.get("album_id")

    if album_id:
        album = store.get_album(album_id)
        if album is None:
            return jsonify({"ok": False, "error": "album not found"}), 404
        store.set_active_album(album_id)
    else:
        store.set_active_album(None)

    return jsonify({"ok": True, "active_album_id": album_id})


@bp.get("/albums/<album_id>/playlist")
def playlist(album_id: str):
    album = store.get_album(album_id)
    if album is None:
        return jsonify({"ok": False, "error": "album not found"}), 404

    settings = store.get_settings()
    default_duration = int(settings.get("default_duration") or current_app.config["DEFAULT_DURATION"])
    transition = settings.get("transition") or current_app.config["DEFAULT_TRANSITION"]

    items = store.get_album_items(album_id, only_ready=True)
    payload = [_item_to_player_dict(item, default_duration, transition) for item in items]

    return jsonify(
        {
            "ok": True,
            "album": {"id": album["id"], "name": album["name"]},
            "items": payload,
            "settings": {
                "default_duration": default_duration,
                "transition": transition,
                "shuffle": settings.get("shuffle", "0") == "1",
            },
        }
    )


@bp.post("/transcode/<media_id>")
def transcode(media_id: str):
    media = store.get_media(media_id)
    if media is None:
        return jsonify({"ok": False, "error": "media not found"}), 404

    queued = enqueue_media(media_id)
    return jsonify({"ok": queued, "queued": queued, "media_id": media_id})


@bp.get("/library/scan")
def scan_library():
    incoming_dir = Path(current_app.config["INCOMING_DIR"])
    media_root = Path(current_app.config["MEDIA_ROOT"])
    allowed = current_app.config["ALLOWED_EXTENSIONS"]

    incoming_dir.mkdir(parents=True, exist_ok=True)
    added = 0

    for path in incoming_dir.iterdir():
        if not path.is_file():
            continue
        if not allowed_extension(path.name, allowed):
            continue

        rel_path = str(path.relative_to(media_root))
        if store.get_media_by_original_path(rel_path):
            continue

        media_type = detect_media_type(path.name)
        if media_type is None:
            continue

        media_id = store.create_media(rel_path, media_type)
        enqueue_media(media_id)
        added += 1

    return jsonify({"ok": True, "added": added})
