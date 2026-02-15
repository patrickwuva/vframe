# AGENT.md — Raspberry Pi 5 Digital Frame (Flask + Blueprints)

## Project Summary
A Raspberry Pi 5 runs a local web app used to upload/manage photos & videos stored on local NVMe filesystem storage, organize them into albums, and play them on a 7" HDMI-connected display as a slideshow with transitions and video playback.

Primary goals:
- Simple local admin website (LAN-only by default)
- Media stored on local filesystem (source of truth)
- Albums (orderable playlists)
- Fullscreen player page for kiosk display
- Automatic video normalization for reliable HTML5 playback (MP4/H.264/AAC)
- Minimal dependencies and easy to run as a service on Raspberry Pi OS

---

## Tech Stack
- **Backend:** Python 3 + Flask
- **Structure:** Flask **Blueprints** (modular routes)
- **DB:** SQLite (metadata: albums, ordering, settings)
- **Frontend:** Server-rendered templates (Jinja2) + minimal JS (HTMX optional)
- **Player:** `/player` page (HTML/CSS transitions + HTML5 `<video>`)
- **Media processing:** `ffmpeg` (thumbnails + video conversion)
- **Reverse proxy (optional):** Caddy or nginx
- **Runtime:** systemd service (preferred) or Docker Compose

---

---

## Storage Model
Media root is a local directory on Pi OS storage (NVMe):

- `MEDIA_ROOT=/home/pi/frame-media`

Suggested subfolders (created automatically):
- `/home/pi/frame-media/library/` (normalized “playable” media)
- `/home/pi/frame-media/incoming/` (raw uploads)
- `/home/pi/frame-media/.thumbs/` (thumbnails + poster frames)
- `/home/pi/frame-media/.meta/` (optional sidecars)

Rules:
- The web app writes uploads to `incoming/`
- A background job normalizes into `library/`
- The app references files by a stable `media_id` and stores final path in SQLite

---

## Supported Media Formats
Player page should only play “normalized” formats:
- Photos: `.jpg`, `.png`
- Videos: `.mp4` (H.264 video + AAC audio, yuv420p)

Transcode target:
- 720p or screen-native resolution
- 30 fps
- `-movflags +faststart` for quick start

---

## Flask Blueprints
### 1) `admin` blueprint
Purpose: clean admin UI
Routes (suggested):
- `GET /` -> redirect `/admin`
- `GET /admin` -> dashboard (active album, storage stats)
- `GET /admin/upload` -> upload form
- `POST /admin/upload` -> upload handler (stores in incoming/)
- `GET /admin/library` -> list all media (with thumbs)
- `GET /admin/albums` -> albums list
- `POST /admin/albums` -> create album
- `GET /admin/albums/<album_id>` -> edit album (ordering, duration, transitions)
- `POST /admin/albums/<album_id>/items` -> add/remove/reorder items
- `POST /admin/settings` -> global settings (shuffle, default duration, etc.)

UI constraints:
- Must look clean and minimal
- Mobile-friendly (upload from phone)
- Avoid heavy JS frameworks unless needed

### 2) `api` blueprint
Purpose: player & admin AJAX endpoints (JSON)
Routes (suggested):
- `GET /api/status` -> active album + player state
- `POST /api/active-album` -> set active album
- `GET /api/albums/<album_id>/playlist` -> ordered playlist items + settings
- `POST /api/transcode/<media_id>` -> enqueue transcode (or run immediate)
- `GET /api/library/scan` -> scan media root, reconcile DB

### 3) `player` blueprint
Purpose: fullscreen playback view for kiosk
Routes:
- `GET /player` -> fullscreen player UI
Player behavior:
- Fetch active playlist from API
- Preload next image
- Apply transitions (fade/slide/zoom)
- Play videos inline with `<video>` or skip unsupported formats

### 4) `health` blueprint
Purpose: monitoring / uptime
Routes:
- `GET /healthz` -> 200 OK + basic info

---

## Database Schema (SQLite)
Minimum tables:
- `media`:
  - `id` (uuid or int)
  - `original_path`
  - `normalized_path`
  - `type` ("photo"|"video")
  - `created_at`
  - `duration_seconds` (nullable)
  - `width`, `height` (nullable)
  - `thumb_path` (nullable)
  - `status` ("ready"|"processing"|"failed")

- `albums`:
  - `id`
  - `name`
  - `created_at`

- `album_items`:
  - `album_id`
  - `media_id`
  - `sort_index` (int)

- `settings` (key/value):
  - `key`
  - `value`

- `player_state`:
  - `active_album_id`
  - `updated_at`

---

## Background Jobs
Avoid big frameworks; keep it simple:
- A lightweight worker thread/process triggered by:
  - upload completion
  - periodic scan
  - manual “normalize now” button

Jobs:
- Generate thumbnails for photos
- Extract poster frame thumbnail for videos
- Transcode raw videos to normalized MP4 format
- Validate normalized media exists + repair DB

If you do add a queue later:
- Use `rq` + Redis (optional), but default is “no Redis required”.

---

## Kiosk Mode
Pi boots into fullscreen playback:
- Start X + Chromium kiosk at `http://localhost/player`
- Hide cursor, disable screen blanking

Systemd units (planned):
- `frameapp.service` -> starts Flask (gunicorn recommended)
- `kiosk.service` -> launches Chromium in kiosk mode

---

## Security / Access
Default: LAN-only.
- Bind Flask/gunicorn to `0.0.0.0:5000` only on local network OR `127.0.0.1` behind reverse proxy.
- Optional basic auth for admin pages.
- Upload size limits enforced (Flask config).
- Restrict allowed file types; sniff MIME types.

---

## Development Rules
- Keep code readable and modular; blueprints must remain isolated
- No large frontend frameworks unless necessary
- Prefer server-rendered templates + small JS modules
- Every user action should be recoverable (no “silent fail” uploads)
- Media processing must not block the request thread (use background job)

---

## Definition of Done
- Upload photos/videos from phone on LAN
- Videos are normalized automatically and play reliably in `/player`
- Albums can be created and reordered
- Player runs fullscreen and loops indefinitely
- System survives reboot and continues playback
- Local filesystem is the source of truth; DB can be rebuilt by scanning

---

## Quick Start (Dev)
1. Install deps:
   - `sudo apt-get install -y ffmpeg`
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`

2. Set env:
   - `export MEDIA_ROOT=/home/pi/frame-media`
   - `export FLASK_ENV=development`
   - `export SECRET_KEY=dev`

3. Init DB:
   - `python scripts/init_db.py`

4. Run:
   - `python app.py`

---

## Notes for Agents / Contributors
- The player must only use normalized media paths
- Any new endpoints must be placed in the correct blueprint
- Avoid adding heavyweight services (Redis, Postgres) unless clearly justified
- Keep transitions simple and performant (Pi-friendly)
