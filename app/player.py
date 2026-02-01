import json
import os
import queue
import shlex
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from . import library


def _now():
    return time.monotonic()


@dataclass
class MediaItem:
    path: str
    kind: str
    root: str


class MPVClient:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self.proc = None
        self.sock = None
        self._recv_thread = None
        self._pending = {}
        self._pending_lock = threading.Lock()
        self._next_id = 1
        self._event_handlers: List[Callable[[dict], None]] = []
        self._running = False

    def start(self, args: Optional[List[str]] = None):
        if self.proc and self.proc.poll() is None:
            return
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass
        cmd = [
            "mpv",
            "--idle=yes",
            "--force-window=yes",
            "--fs",
            "--no-terminal",
            "--image-display-duration=inf",
            f"--input-ipc-server={self.socket_path}",
        ]
        if args:
            cmd.extend(args)
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_for_socket()
        self._connect_socket()
        self._running = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def stop(self):
        self._running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        if self.proc:
            self.proc.terminate()

    def on_event(self, handler: Callable[[dict], None]):
        self._event_handlers.append(handler)

    def command(self, *args, timeout=2.0):
        req_id = self._next_id
        self._next_id += 1
        payload = {"command": list(args), "request_id": req_id}
        response_queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[req_id] = response_queue
        self._send(payload)
        try:
            response = response_queue.get(timeout=timeout)
        except queue.Empty:
            response = {"error": "timeout"}
        finally:
            with self._pending_lock:
                self._pending.pop(req_id, None)
        return response

    def _wait_for_socket(self, timeout=3.0):
        deadline = _now() + timeout
        while _now() < deadline:
            if self.socket_path.exists():
                return
            time.sleep(0.05)
        raise RuntimeError("mpv ipc socket not available")

    def _connect_socket(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(self.socket_path))
        self.sock = sock

    def _send(self, payload: dict):
        if not self.sock:
            raise RuntimeError("mpv socket not connected")
        data = json.dumps(payload).encode("utf-8") + b"\n"
        self.sock.sendall(data)

    def _recv_loop(self):
        buffer = b""
        while self._running and self.sock:
            try:
                chunk = self.sock.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line:
                    continue
                try:
                    payload = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                self._dispatch(payload)

    def _dispatch(self, payload: dict):
        if "event" in payload:
            for handler in self._event_handlers:
                handler(payload)
            return
        req_id = payload.get("request_id")
        if req_id is None:
            return
        with self._pending_lock:
            response_queue = self._pending.get(req_id)
        if response_queue:
            response_queue.put(payload)


class PlayerManager:
    def __init__(self, state_store):
        self.state_store = state_store
        self.media_roots = self.state_store.resolve_media_roots()
        self.socket_path = Path("/tmp/vframe-mpv.sock")
        self.mpv = MPVClient(self.socket_path)
        self.mpv.on_event(self._on_mpv_event)
        self.playlist: List[MediaItem] = []
        self.index = -1
        self.lock = threading.Lock()
        self.timer = None
        self.playing = False
        self.current_album_id = None
        self.current_item: Optional[MediaItem] = None
        self.last_error: Optional[str] = None

    def start(self):
        self.media_roots = self.state_store.resolve_media_roots()
        extra = os.environ.get("VFRAME_MPV_ARGS", "").strip()
        args = shlex.split(extra) if extra else ["--vo=drm"]
        try:
            self.mpv.start(args=args)
        except FileNotFoundError:
            self.last_error = "mpv not found"
        except RuntimeError as exc:
            self.last_error = str(exc)

    def stop(self):
        with self.lock:
            self.playing = False
            self.current_item = None
            self.current_album_id = None
            self._cancel_timer()
        self._command("stop")

    def play_album(self, album_id: str):
        state = self.state_store.get_state()
        album = next((a for a in state["albums"] if a["id"] == album_id), None)
        if not album:
            return False
        playlist = self._build_playlist(album)
        with self.lock:
            self.playlist = playlist
            self.index = 0 if playlist else -1
            self.playing = bool(playlist)
            self.current_album_id = album_id
        if not playlist:
            return False
        self._play_current()
        return True

    def next(self):
        with self.lock:
            if not self.playlist:
                return
            self.index = (self.index + 1) % len(self.playlist)
        self._play_current()

    def prev(self):
        with self.lock:
            if not self.playlist:
                return
            self.index = (self.index - 1) % len(self.playlist)
        self._play_current()

    def now_playing(self):
        with self.lock:
            item = self.current_item
            return {
                "playing": self.playing,
                "album_id": self.current_album_id,
                "item": None if item is None else {
                    "path": item.path,
                    "type": item.kind,
                    "root": item.root,
                },
            }

    def update_settings(self):
        state = self.state_store.get_state()
        settings = state["settings"]
        self._apply_audio(settings)
        return settings

    def _apply_audio(self, settings):
        self._command("set_property", "mute", settings.get("mute", False))

    def _build_playlist(self, album):
        state = self.state_store.get_state()
        settings = state["settings"]
        entries: List[MediaItem] = []
        for source in album.get("sources", []):
            source_type = source.get("type")
            rel_path = source.get("path")
            source_root = source.get("root")
            if not rel_path:
                continue
            if source_type == "folder":
                folder = self._resolve_source_path(source_root, rel_path, is_folder=True)
                if not folder:
                    continue
                for path in library.iter_media_files(folder):
                    entries.append(self._to_media_item(path, source_root or self._root_name_for_path(folder)))
            elif source_type == "file":
                path = self._resolve_source_path(source_root, rel_path, is_folder=False)
                if path.exists() and library.is_media(path):
                    entries.append(self._to_media_item(path, source_root or self._root_name_for_path(path)))
        shuffle = album.get("shuffle")
        if shuffle is None:
            shuffle = settings.get("shuffle", False)
        if shuffle:
            import random
            random.shuffle(entries)
        return entries

    def _to_media_item(self, path: Path, root: str) -> MediaItem:
        return MediaItem(
            path=self._relative_to_root(path, root),
            kind="image" if library.is_image(path) else "video",
            root=root,
        )

    def _play_current(self):
        with self.lock:
            if not self.playing or not self.playlist:
                return
            item = self.playlist[self.index]
            self.current_item = item
        state = self.state_store.get_state()
        settings = state["settings"]
        abs_path = self._resolve_root(item.root) / item.path
        self._apply_audio(settings)
        self._apply_filters(settings, item.kind == "image")
        self._cancel_timer()
        self._command("loadfile", str(abs_path), "replace")
        if item.kind == "image":
            duration = float(settings.get("slide_duration", 10))
            self._schedule_next(duration)

    def _apply_filters(self, settings, is_image: bool):
        width = int(settings.get("display_width", 1024))
        height = int(settings.get("display_height", 600))
        fit_mode = settings.get("fit_mode", "fit-blur")
        transition = settings.get("transition", "none")
        fade_dur = float(settings.get("transition_duration", 0.6))
        slide_dur = float(settings.get("slide_duration", 10))
        vf = build_vf(fit_mode, transition, fade_dur, slide_dur, is_image, width, height)
        self._command("set_property", "vf", vf)

    def _schedule_next(self, duration):
        def _advance():
            self.next()
        self.timer = threading.Timer(duration, _advance)
        self.timer.daemon = True
        self.timer.start()

    def _cancel_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def _on_mpv_event(self, payload):
        if payload.get("event") != "end-file":
            return
        with self.lock:
            if not self.playing:
                return
            if not self.current_item or self.current_item.kind != "video":
                return
        self.next()

    def _resolve_root(self, root_name: str) -> Path:
        return self.media_roots.get(root_name) or next(iter(self.media_roots.values()))

    def _root_name_for_path(self, path: Path) -> str:
        for name, root in self.media_roots.items():
            try:
                path.relative_to(root)
                return name
            except ValueError:
                continue
        return "primary"

    def _relative_to_root(self, path: Path, root_name: str) -> str:
        root = self._resolve_root(root_name)
        return path.relative_to(root).as_posix()

    def _resolve_source_path(self, root_name: Optional[str], rel_path: str, is_folder: bool) -> Optional[Path]:
        if root_name:
            root = self.media_roots.get(root_name)
            if not root:
                return None
            return root / rel_path
        primary = self.media_roots.get("primary")
        secondary = self.media_roots.get("secondary")
        if primary:
            candidate = primary / rel_path
            if candidate.exists():
                return candidate
        if secondary:
            candidate = secondary / rel_path
            if candidate.exists():
                return candidate
        if is_folder:
            return None
        return None

    def _command(self, *args):
        try:
            return self.mpv.command(*args)
        except Exception as exc:
            self.last_error = str(exc)
            return {"error": str(exc)}


def build_vf(fit_mode, transition, fade_dur, slide_dur, is_image, width, height):
    if fit_mode == "fill":
        base = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    elif fit_mode == "fit" or (fit_mode == "fit-blur" and not is_image):
        base = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    else:
        base = (
            "lavfi=[split=2[main][blur];"
            f"[blur]boxblur=20:1,scale={width}:{height}[bg];"
            f"[main]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
            "]"
        )
    if transition == "fade" and is_image:
        fade_in = f"fade=t=in:st=0:d={fade_dur}"
        fade_out_start = max(slide_dur - fade_dur, 0)
        fade_out = f"fade=t=out:st={fade_out_start}:d={fade_dur}"
        if base.startswith("lavfi="):
            base = base[:-1] + f",{fade_in},{fade_out}]"
        else:
            base = f"{base},{fade_in},{fade_out}"
    return base
