# Raspberry Pi Digital Frame (Flask)

Flask-based local admin + player app for a Raspberry Pi digital frame.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MEDIA_ROOT=/home/pi/frame-media
export SECRET_KEY=dev
python scripts/init_db.py
python app.py
```

Open:
- Admin: `http://localhost:5000/admin`
- Player: `http://localhost:5000/player`

## Notes

- Uploads are saved to `incoming/` and normalized into `library/`.
- By default media lives on local disk at `/home/pi/frame-media` (same NVMe as Pi OS).
- The background worker uses `ffmpeg` + `ffprobe` for video normalization and thumbnails.
- SQLite metadata is stored at `instance/frame.db` by default.
