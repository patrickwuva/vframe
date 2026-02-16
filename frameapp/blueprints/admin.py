from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from frameapp import store
from frameapp.media import allowed_extension, detect_media_type
from frameapp.worker import enqueue_media


bp = Blueprint("admin", __name__)


@bp.get("/")
def index():
    return redirect(url_for("admin.dashboard"))


@bp.get("/admin")
def dashboard():
    counts = store.get_counts()
    active_album_id = store.get_active_album_id()
    albums = store.list_albums()
    settings = store.get_settings()

    media_root = Path(current_app.config["MEDIA_ROOT"])
    usage = None
    try:
        stats = shutil.disk_usage(media_root)
        usage = {
            "total_gb": round(stats.total / (1024**3), 2),
            "used_gb": round(stats.used / (1024**3), 2),
            "free_gb": round(stats.free / (1024**3), 2),
        }
    except FileNotFoundError:
        usage = None

    return render_template(
        "admin/dashboard.html",
        counts=counts,
        albums=albums,
        active_album_id=active_album_id,
        settings=settings,
        usage=usage,
    )


@bp.route("/admin/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        files = request.files.getlist("files")
        target_album_id = (request.form.get("target_album_id") or "").strip() or None
        if not files:
            flash("No files selected", "error")
            return redirect(url_for("admin.upload"))

        if target_album_id and store.get_album(target_album_id) is None:
            flash("Selected album was not found", "error")
            return redirect(url_for("admin.upload"))

        incoming_dir = Path(current_app.config["INCOMING_DIR"])
        incoming_dir.mkdir(parents=True, exist_ok=True)
        allowed = current_app.config["ALLOWED_EXTENSIONS"]

        accepted = 0
        rejected = 0
        queued = 0
        added_to_album = 0

        for file in files:
            if not file or not file.filename:
                continue
            if not allowed_extension(file.filename, allowed):
                rejected += 1
                continue

            media_type = detect_media_type(file.filename)
            if media_type is None:
                rejected += 1
                continue

            safe_name = secure_filename(file.filename)
            prefix = uuid4().hex[:8]
            dest_name = f"{prefix}-{safe_name}"
            dest_path = incoming_dir / dest_name
            file.save(dest_path)

            rel_path = str(Path("incoming") / dest_name)
            media_id = store.create_media(rel_path, media_type)
            accepted += 1
            if target_album_id:
                store.add_media_to_album(target_album_id, media_id)
                added_to_album += 1

            if enqueue_media(media_id):
                queued += 1

        message = f"Uploaded {accepted} file(s), rejected {rejected}. Queued for processing: {queued}."
        if target_album_id:
            message += f" Added to album: {added_to_album}."
        flash(message, "success")
        return redirect(url_for("admin.library"))

    return render_template("admin/upload.html", albums=store.list_albums())


@bp.get("/admin/library")
def library():
    media_items = store.list_media()
    return render_template(
        "admin/library.html",
        media_items=media_items,
        albums=store.list_albums(),
        active_album_id=store.get_active_album_id(),
    )


@bp.post("/admin/library/add-to-album")
def library_add_to_album():
    album_id = (request.form.get("album_id") or "").strip()
    media_ids = request.form.getlist("media_ids")
    if not album_id:
        flash("Pick an album first", "error")
        return redirect(url_for("admin.library"))

    album = store.get_album(album_id)
    if album is None:
        flash("Album not found", "error")
        return redirect(url_for("admin.library"))

    if not media_ids:
        flash("No media selected", "error")
        return redirect(url_for("admin.library"))

    added = 0
    seen: set[str] = set()
    for media_id in media_ids:
        if not media_id or media_id in seen:
            continue
        seen.add(media_id)
        store.add_media_to_album(album_id, media_id)
        added += 1

    flash(f"Added {added} item(s) to album '{album['name']}'", "success")
    return redirect(url_for("admin.library"))


@bp.route("/admin/albums", methods=["GET", "POST"])
def albums():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Album name is required", "error")
            return redirect(url_for("admin.albums"))

        album_id = store.create_album(name)
        flash("Album created", "success")
        return redirect(url_for("admin.edit_album", album_id=album_id))

    all_albums = store.list_albums()
    active_album_id = store.get_active_album_id()
    return render_template(
        "admin/albums.html",
        albums=all_albums,
        active_album_id=active_album_id,
    )


@bp.get("/admin/albums/<album_id>")
def edit_album(album_id: str):
    album = store.get_album(album_id)
    if album is None:
        flash("Album not found", "error")
        return redirect(url_for("admin.albums"))

    items = store.get_album_items(album_id)
    ready_media = store.list_ready_media()
    active_album_id = store.get_active_album_id()
    return render_template(
        "admin/album_edit.html",
        album=album,
        items=items,
        ready_media=ready_media,
        active_album_id=active_album_id,
    )


@bp.post("/admin/albums/<album_id>/items")
def update_album_items(album_id: str):
    action = request.form.get("action")

    if action == "add":
        selected = request.form.getlist("media_ids")
        for media_id in selected:
            store.add_media_to_album(album_id, media_id)
        flash(f"Added {len(selected)} item(s)", "success")

    elif action == "remove":
        media_id = request.form.get("media_id")
        if media_id:
            store.remove_media_from_album(album_id, media_id)
            flash("Removed item", "success")

    elif action in {"move_up", "move_down"}:
        media_id = request.form.get("media_id")
        direction = "up" if action == "move_up" else "down"
        if media_id:
            store.move_media_in_album(album_id, media_id, direction)

    elif action == "reorder_positions":
        items = store.get_album_items(album_id)
        if not items:
            return redirect(url_for("admin.edit_album", album_id=album_id))

        scored: list[tuple[int, int, str]] = []
        for idx, item in enumerate(items):
            media_id = item["media_id"]
            raw = (request.form.get(f"sort_{media_id}") or "").strip()
            try:
                value = int(raw)
            except ValueError:
                value = idx + 1
            scored.append((value, idx, media_id))

        scored.sort(key=lambda x: (x[0], x[1]))
        ordered_ids = [x[2] for x in scored]
        store.reorder_album_items(album_id, ordered_ids)
        flash("Album order updated", "success")

    return redirect(url_for("admin.edit_album", album_id=album_id))


@bp.post("/admin/albums/<album_id>/activate")
def activate_album(album_id: str):
    album = store.get_album(album_id)
    if album is None:
        flash("Album not found", "error")
        return redirect(url_for("admin.albums"))

    store.set_active_album(album_id)
    flash(f"Now playing: {album['name']}", "success")

    next_url = request.form.get("next")
    if next_url:
        return redirect(next_url)
    return redirect(url_for("admin.albums"))


@bp.post("/admin/settings")
def update_settings():
    default_duration = request.form.get("default_duration", "8").strip()
    transition = request.form.get("transition", "fade").strip() or "fade"
    shuffle = "1" if request.form.get("shuffle") == "1" else "0"
    active_album_id = request.form.get("active_album_id") or None

    if not default_duration.isdigit():
        flash("Default duration must be a number", "error")
        return redirect(url_for("admin.dashboard"))

    store.set_setting("default_duration", default_duration)
    store.set_setting("transition", transition)
    store.set_setting("shuffle", shuffle)
    store.set_active_album(active_album_id)

    flash("Settings saved", "success")
    return redirect(url_for("admin.dashboard"))
