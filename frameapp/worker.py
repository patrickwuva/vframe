from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
from pathlib import Path
from queue import Queue

from flask import current_app

from frameapp import store


logger = logging.getLogger(__name__)

_worker = None
_worker_lock = threading.Lock()


class MediaWorker(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.jobs: Queue[str] = Queue()

    def enqueue(self, media_id: str) -> None:
        self.jobs.put(media_id)

    def run(self) -> None:
        with self.app.app_context():
            while True:
                media_id = self.jobs.get()
                try:
                    process_media(media_id)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed processing media %s", media_id)
                    store.mark_media_failed(media_id, str(exc))
                finally:
                    self.jobs.task_done()


def start_worker(app) -> None:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = MediaWorker(app)
            _worker.start()


def enqueue_media(media_id: str) -> bool:
    if _worker is None:
        return False
    _worker.enqueue(media_id)
    return True


def ffmpeg_exists() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe_media(path: Path) -> tuple[float | None, int | None, int | None]:
    if not ffmpeg_exists():
        return (None, None, None)
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    output = run_cmd(cmd)
    data = json.loads(output.stdout or "{}")

    duration = None
    fmt = data.get("format") or {}
    if fmt.get("duration") is not None:
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None

    width = None
    height = None
    for stream in data.get("streams", []):
        if stream.get("width") and stream.get("height"):
            width = int(stream["width"])
            height = int(stream["height"])
            break

    return (duration, width, height)


def make_thumb(input_path: Path, thumb_path: Path, is_video: bool) -> None:
    if not ffmpeg_exists():
        return
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
    ]
    if is_video:
        cmd.extend(["-ss", "00:00:01"])
    cmd.extend(["-i", str(input_path), "-frames:v", "1", "-vf", "scale=320:-1", str(thumb_path)])
    run_cmd(cmd)


def transcode_video(input_path: Path, output_path: Path) -> None:
    if not ffmpeg_exists():
        raise RuntimeError("ffmpeg/ffprobe not found; cannot transcode video")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "scale='min(1280,iw)':-2,fps=30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    run_cmd(cmd)


def process_media(media_id: str) -> None:
    media = store.get_media(media_id)
    if media is None:
        return

    store.set_media_processing(media_id)

    media_root = Path(current_app.config["MEDIA_ROOT"])
    library_dir = Path(current_app.config["LIBRARY_DIR"])
    thumbs_dir = Path(current_app.config["THUMBS_DIR"])

    source_path = media_root / media["original_path"]
    if not source_path.exists():
        raise FileNotFoundError(f"Missing source media: {source_path}")

    if media["type"] == "photo":
        suffix = source_path.suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png"}:
            suffix = ".jpg"
        normalized_rel = Path("library") / f"{media_id}{suffix}"
        normalized_path = library_dir / f"{media_id}{suffix}"
        normalized_path.parent.mkdir(parents=True, exist_ok=True)

        if source_path != normalized_path:
            shutil.copy2(source_path, normalized_path)

        thumb_rel = Path(".thumbs") / f"{media_id}.jpg"
        thumb_path = thumbs_dir / f"{media_id}.jpg"
        try:
            make_thumb(normalized_path, thumb_path, is_video=False)
            thumb_rel_value = str(thumb_rel)
        except Exception:  # noqa: BLE001
            thumb_rel_value = None

        duration, width, height = probe_media(normalized_path)
        store.mark_media_ready(
            media_id,
            str(normalized_rel),
            thumb_rel_value,
            duration,
            width,
            height,
        )
        return

    normalized_rel = Path("library") / f"{media_id}.mp4"
    normalized_path = library_dir / f"{media_id}.mp4"
    transcode_video(source_path, normalized_path)

    thumb_rel = Path(".thumbs") / f"{media_id}.jpg"
    thumb_path = thumbs_dir / f"{media_id}.jpg"
    make_thumb(normalized_path, thumb_path, is_video=True)

    duration, width, height = probe_media(normalized_path)
    store.mark_media_ready(
        media_id,
        str(normalized_rel),
        str(thumb_rel),
        duration,
        width,
        height,
    )
