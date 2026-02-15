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

Install runtime packages (Desktop mode):

```bash
sudo apt update
sudo apt install -y git ffmpeg mpv python3 python3-venv python3-pip
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
- Admin includes iPhone-friendly PWA support (safe-area layout, bottom nav, install hint, offline shell cache).

## Auto-start on boot (Pi HDMI player, native mpv)

Use Raspberry Pi OS with Desktop for simplest kiosk setup.

Set desktop auto-login and graphical boot target:

```bash
sudo raspi-config nonint do_boot_behaviour B4
sudo systemctl set-default graphical.target
```

Install and enable the system services:

```bash
sudo cp systemd/frameapp.service /etc/systemd/system/frameapp.service
sudo cp systemd/player-native.service /etc/systemd/system/player-native.service
sudo systemctl daemon-reload
sudo systemctl disable --now kiosk.service || true
sudo systemctl enable frameapp.service player-native.service
sudo systemctl restart frameapp.service player-native.service
```

Check status/logs:

```bash
sudo systemctl status frameapp.service player-native.service
journalctl -u frameapp.service -u player-native.service -f
```

Important:
- `systemd/frameapp.service` and `systemd/player-native.service` currently use user/path `pw` and `/home/pw/vframe`; edit those if your username/path differs.
- Set a real secret in `systemd/frameapp.service` (`Environment=SECRET_KEY=...`) before long-term use.
- If you choose browser mode instead of native, you can still use `systemd/kiosk.service`.
