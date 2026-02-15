#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

API_BASE = os.getenv("VFRAME_API_BASE", "http://127.0.0.1:5000").rstrip("/")
STATUS_URL = os.getenv("VFRAME_STATUS_URL", f"{API_BASE}/api/status")
POLL_SECONDS = float(os.getenv("VFRAME_POLL_SECONDS", "5"))
MPV_BIN = os.getenv("MPV_BIN", "mpv")

DISPLAY_ENV = os.getenv("DISPLAY", ":0")
XAUTHORITY_ENV = os.getenv("XAUTHORITY", str(Path.home() / ".Xauthority"))


def log(message: str) -> None:
    print(f"[native-player] {message}", flush=True)


def fetch_json(url: str, timeout: float = 4.0) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        log(f"request failed for {url}: {exc}")
        return None


def build_playlist_key(album_id: str, payload: dict[str, Any]) -> str:
    items = payload.get("items") or []
    settings = payload.get("settings") or {}
    item_key = "|".join(
        f"{item.get('media_id','')}:{item.get('type','')}:{item.get('normalized_url','')}"
        for item in items
    )
    return f"{album_id}|{settings.get('shuffle', False)}|{settings.get('default_duration', 8)}|{item_key}"


def resolve_urls(payload: dict[str, Any]) -> list[str]:
    items = payload.get("items") or []
    urls: list[str] = []
    for item in items:
        url = item.get("normalized_url")
        if isinstance(url, str) and url:
            urls.append(url)
    return urls


@dataclass
class MpvState:
    proc: subprocess.Popen | None = None
    playlist_path: Path | None = None
    playlist_key: str | None = None


class MpvController:
    def __init__(self) -> None:
        self.state = MpvState()

    def stop(self) -> None:
        proc = self.state.proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

        self.state.proc = None
        self.state.playlist_key = None

        if self.state.playlist_path and self.state.playlist_path.exists():
            try:
                self.state.playlist_path.unlink()
            except OSError:
                pass
        self.state.playlist_path = None

    def _write_playlist(self, urls: list[str]) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".m3u",
            prefix="vframe-",
            delete=False,
        ) as fp:
            fp.write("#EXTM3U\n")
            for url in urls:
                fp.write(f"{url}\n")
            return Path(fp.name)

    def _start_mpv(self, playlist_path: Path, image_duration: int) -> subprocess.Popen:
        cmd = [
            MPV_BIN,
            "--fs",
            "--no-border",
            "--keep-open=no",
            "--loop-playlist=inf",
            "--really-quiet",
            "--osd-level=0",
            "--no-osc",
            "--profile=sw-fast",
            "--video-sync=display-resample",
            "--hwdec=auto-safe",
            "--scale=bilinear",
            "--dscale=bilinear",
            "--tscale=oversample",
            f"--image-display-duration={max(1, image_duration)}",
            str(playlist_path),
        ]

        env = os.environ.copy()
        env["DISPLAY"] = DISPLAY_ENV
        env["XAUTHORITY"] = XAUTHORITY_ENV

        return subprocess.Popen(cmd, env=env)

    def ensure(self, playlist_key: str, urls: list[str], image_duration: int) -> None:
        proc = self.state.proc
        same_key = self.state.playlist_key == playlist_key
        alive = proc is not None and proc.poll() is None

        if same_key and alive:
            return

        self.stop()

        playlist_path = self._write_playlist(urls)
        log(f"starting mpv with {len(urls)} item(s)")
        proc = self._start_mpv(playlist_path, image_duration)
        self.state.proc = proc
        self.state.playlist_path = playlist_path
        self.state.playlist_key = playlist_key


_running = True


def _handle_signal(_sig: int, _frame: Any) -> None:
    global _running
    _running = False


def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    controller = MpvController()
    log("native mpv player started")

    try:
        while _running:
            status = fetch_json(STATUS_URL)
            if not status:
                time.sleep(POLL_SECONDS)
                continue

            active_album_id = status.get("active_album_id")
            if not active_album_id:
                if controller.state.proc is not None:
                    log("no active album; stopping mpv")
                controller.stop()
                time.sleep(POLL_SECONDS)
                continue

            payload = fetch_json(f"{API_BASE}/api/albums/{active_album_id}/playlist")
            if not payload or not payload.get("ok"):
                time.sleep(POLL_SECONDS)
                continue

            urls = resolve_urls(payload)
            if not urls:
                if controller.state.proc is not None:
                    log("active album has no ready media; stopping mpv")
                controller.stop()
                time.sleep(POLL_SECONDS)
                continue

            settings = payload.get("settings") or {}
            image_duration = int(settings.get("default_duration") or 8)
            playlist_key = build_playlist_key(active_album_id, payload)
            controller.ensure(playlist_key, urls, image_duration)

            time.sleep(POLL_SECONDS)
    finally:
        controller.stop()

    log("native mpv player stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
