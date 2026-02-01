import os
from pathlib import Path
from typing import Iterable

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm"}


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def is_media(path: Path) -> bool:
    return is_image(path) or is_video(path)


def iter_media_files(folder: Path) -> Iterable[Path]:
    if not folder.exists():
        return
    for root, _, files in os.walk(folder):
        root_path = Path(root)
        for name in files:
            path = root_path / name
            if is_media(path):
                yield path


def list_library(media_roots: dict[str, Path]):
    folders = []
    files = []
    for root_name, media_root in media_roots.items():
        if not media_root.exists():
            continue
        for root, dirnames, filenames in os.walk(media_root):
            root_path = Path(root)
            for dirname in dirnames:
                folder = root_path / dirname
                rel = folder.relative_to(media_root).as_posix()
                folders.append({
                    "root": root_name,
                    "path": rel,
                    "name": dirname,
                })
            for filename in filenames:
                file_path = root_path / filename
                if not is_media(file_path):
                    continue
                rel = file_path.relative_to(media_root).as_posix()
                stat = file_path.stat()
                files.append({
                    "root": root_name,
                    "path": rel,
                    "name": filename,
                    "type": "image" if is_image(file_path) else "video",
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                })

    folders.sort(key=lambda item: (item["root"], item["path"].lower()))
    files.sort(key=lambda item: (item["root"], item["path"].lower()))
    return {"folders": folders, "files": files}
