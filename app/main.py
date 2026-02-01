import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import library
from .player import PlayerManager
from .state import StateStore

app = FastAPI(title="vframe")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = Jinja2Templates(directory=str(ROOT_DIR / "app" / "templates"))
STATIC_DIR = ROOT_DIR / "app" / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

state_store = StateStore()
player = PlayerManager(state_store)


@app.on_event("startup")
def on_startup():
    player.start()
    state_store.resolve_media_roots()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return TEMPLATES.TemplateResponse("index.html", {"request": request})


@app.get("/api/state")
def get_state():
    state = state_store.get_state()
    state["now_playing"] = player.now_playing()
    state["player_error"] = player.last_error
    return state


@app.get("/api/library")
def get_library():
    media_roots = state_store.resolve_media_roots()
    return library.list_library(media_roots)


def _sanitize_relpath(raw: str) -> str:
    raw = raw.replace("\\", "/")
    path = Path(raw)
    if path.is_absolute():
        raise ValueError("absolute paths not allowed")
    cleaned = Path()
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("invalid path segment")
        cleaned /= part
    return cleaned.as_posix()


@app.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    paths: Optional[List[str]] = Form(default=None),
):
    media_roots = state_store.resolve_media_roots()
    state = state_store.get_state()
    overflow_gb = state.get("storage", {}).get("overflow_threshold_gb", 10)
    primary_root = media_roots.get("primary")
    secondary_root = media_roots.get("secondary")
    saved = []
    for idx, upload in enumerate(files):
        rel_path = upload.filename
        if paths and idx < len(paths) and paths[idx]:
            rel_path = paths[idx]
        try:
            rel_path = _sanitize_relpath(rel_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        dest_root = _select_upload_root(primary_root, secondary_root, overflow_gb)
        if dest_root is None:
            raise HTTPException(status_code=500, detail="no media root available")
        dest = dest_root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        saved.append({"root": _root_name(dest_root, media_roots), "path": rel_path})
    return {"saved": saved}


@app.get("/media/{root}/{path:path}")
def get_media(root: str, path: str):
    media_roots = state_store.resolve_media_roots()
    try:
        safe_path = _sanitize_relpath(path)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid path")
    media_root = media_roots.get(root)
    if not media_root:
        raise HTTPException(status_code=404, detail="media root not found")
    abs_path = media_root / safe_path
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(abs_path)


@app.post("/api/albums")
async def create_album(request: Request):
    payload = await request.json()
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    album_id = uuid.uuid4().hex

    def updater(state):
        state["albums"].append({
            "id": album_id,
            "name": name,
            "sources": [],
            "shuffle": None,
        })
        return state

    state_store.update_state(updater)
    return {"id": album_id}


@app.put("/api/albums/{album_id}")
async def update_album(album_id: str, request: Request):
    payload = await request.json()
    state = state_store.get_state()
    if not any(a for a in state["albums"] if a["id"] == album_id):
        raise HTTPException(status_code=404, detail="album not found")

    def updater(state):
        album = next(a for a in state["albums"] if a["id"] == album_id)
        if "name" in payload:
            album["name"] = (payload.get("name") or album["name"]).strip()
        if "sources" in payload:
            album["sources"] = payload.get("sources") or []
        if "shuffle" in payload:
            album["shuffle"] = payload.get("shuffle")
        return state

    state_store.update_state(updater)
    return {"ok": True}


@app.delete("/api/albums/{album_id}")
def delete_album(album_id: str):
    state = state_store.get_state()
    was_current = state.get("current_album_id") == album_id

    def updater(state):
        state["albums"] = [a for a in state["albums"] if a["id"] != album_id]
        if state.get("current_album_id") == album_id:
            state["current_album_id"] = None
        return state

    state_store.update_state(updater)
    if was_current:
        player.stop()
    return {"ok": True}


@app.post("/api/play/{album_id}")
def play_album(album_id: str):
    ok = player.play_album(album_id)

    def updater(state):
        state["current_album_id"] = album_id if ok else None
        return state

    state_store.update_state(updater)
    if not ok:
        raise HTTPException(status_code=404, detail="album not found or empty")
    return {"ok": True}


@app.post("/api/stop")
def stop_playback():
    player.stop()

    def updater(state):
        state["current_album_id"] = None
        return state

    state_store.update_state(updater)
    return {"ok": True}


@app.post("/api/next")
def next_item():
    player.next()
    return {"ok": True}


@app.post("/api/prev")
def prev_item():
    player.prev()
    return {"ok": True}


@app.post("/api/settings")
async def update_settings(request: Request):
    payload = await request.json()

    def updater(state):
        settings = state.get("settings", {})
        for key, value in payload.items():
            settings[key] = value
        state["settings"] = settings
        return state

    state = state_store.update_state(updater)
    player.update_settings()
    return {"settings": state["settings"]}


@app.post("/api/storage")
async def update_storage(request: Request):
    payload = await request.json()
    primary = (payload.get("primary") or "").strip()
    secondary = (payload.get("secondary") or "").strip()
    threshold = payload.get("overflow_threshold_gb")
    def updater(state):
        if "media_roots" not in state:
            state["media_roots"] = {}
        if primary:
            state["media_roots"]["primary"] = primary
        if secondary:
            state["media_roots"]["secondary"] = secondary
        if "storage" not in state:
            state["storage"] = {}
        if threshold is not None:
            state["storage"]["overflow_threshold_gb"] = float(threshold)
        return state

    state_store.update_state(updater)
    state_store.resolve_media_roots()
    player.media_roots = state_store.resolve_media_roots()
    return {"ok": True}


@app.get("/api/now")
def get_now_playing():
    return player.now_playing()


def _root_name(root_path: Path, media_roots: dict) -> str:
    for name, path in media_roots.items():
        if path == root_path:
            return name
    return "primary"


def _select_upload_root(primary: Optional[Path], secondary: Optional[Path], threshold_gb: float) -> Optional[Path]:
    if primary is None and secondary is None:
        return None
    if primary is None:
        return secondary
    if not primary.exists():
        return secondary or primary
    # If disk is mounted but no space, fall through to secondary.
    try:
        import shutil

        usage = shutil.disk_usage(primary)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < threshold_gb and secondary is not None:
            return secondary
    except (FileNotFoundError, PermissionError, OSError):
        if secondary is not None:
            return secondary
    return primary
