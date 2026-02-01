# vframe

A Raspberry Pi 5 digital media display controller.

- Web UI to upload media, build albums, and control playback.
- Plays images and videos on boot via `mpv`.
- Fit mode with optional blurred background for images.

## Quick Start (development)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open the UI from another device on your LAN: `http://<pi-ip>:8000`.
In development, update Storage settings to a writable path (e.g. `./data/media`) if you cannot write to `/srv` or `/mnt`.

## Raspberry Pi OS Lite Setup

1. Install packages:

```bash
sudo apt update
sudo apt install -y python3-venv mpv
```

2. Mount your USB storage (example path):

```bash
sudo mkdir -p /mnt/vframe-media
sudo lsblk
sudo blkid
```

Add an `/etc/fstab` entry using your USB drive UUID:

```
UUID=XXXX-XXXX  /mnt/vframe-media  exfat  defaults,nofail  0  0
```

Create the primary media directory on the SD card:

```bash
sudo mkdir -p /srv/vframe-media
```

3. Clone the project and install dependencies:

```bash
git clone <your-repo> ~/vframe
cd ~/vframe
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

4. Run the server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

5. (Optional) Set mpv args if the default DRM output does not work:

```bash
export VFRAME_MPV_ARGS="--vo=gpu"
```

## Systemd Service (auto-start)

1. Copy the service file and edit paths if needed:

```bash
sudo cp systemd/vframe.service /etc/systemd/system/vframe.service
sudo systemctl daemon-reload
sudo systemctl enable vframe.service
sudo systemctl start vframe.service
```

2. Check status/logs:

```bash
sudo systemctl status vframe.service
journalctl -u vframe.service -f
```

## Notes

- The UI is LAN-only and has no authentication. Keep it on a trusted network.
- Uploads support folders (Chrome/Edge) using the folder picker.
- Fit + blur is applied to images (videos use the standard fit behavior).
- Set the display width/height in Settings to match your panel resolution.
- Storage defaults to `/srv/vframe-media` (primary) and `/mnt/vframe-media` (secondary), with a 10 GB overflow threshold. You can adjust these in Settings.
