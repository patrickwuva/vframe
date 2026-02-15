# Raspberry Pi Digital Frame (Flask)

Flask-based local admin + player app for a Raspberry Pi digital frame.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MEDIA_ROOT=/home/<user>/frame-media
export SECRET_KEY=dev
python scripts/init_db.py
python app.py
```

Open:
- Admin: `http://localhost:5000/admin`
- Player: `http://localhost:5000/player`

## Notes

- Uploads are saved to `incoming/` and normalized into `library/`.
- By default media lives on local disk at `~/frame-media` (same NVMe as Pi OS).
- The background worker uses `ffmpeg` + `ffprobe` for video normalization and thumbnails.
- SQLite metadata is stored at `instance/frame.db` by default.
- In Admin -> Albums, use `Play on Pi` to switch the active album immediately.

## Auto-start on boot (Pi HDMI player)

Install and enable the system services:

```bash
sudo cp systemd/frameapp.service /etc/systemd/system/frameapp.service
sudo cp systemd/kiosk.service /etc/systemd/system/kiosk.service
sudo systemctl daemon-reload
sudo systemctl enable frameapp.service kiosk.service
sudo systemctl restart frameapp.service kiosk.service
```

Check status/logs:

```bash
sudo systemctl status frameapp.service kiosk.service
journalctl -u frameapp.service -u kiosk.service -f
```

Important:
- `systemd/frameapp.service` and `systemd/kiosk.service` currently use user/path `pw` and `/home/pw/vframe`; edit those if your username/path differs.
- Set a real secret in `systemd/frameapp.service` (`Environment=SECRET_KEY=...`) before long-term use.
