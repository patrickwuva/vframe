#!/usr/bin/env bash
set -eu

export DISPLAY=:0
export XAUTHORITY=${XAUTHORITY:-/home/pw/.Xauthority}

xset -dpms || true
xset s off || true
xset s noblank || true

CHROME_BIN=""
if command -v chromium-browser >/dev/null 2>&1; then
  CHROME_BIN="chromium-browser"
elif command -v chromium >/dev/null 2>&1; then
  CHROME_BIN="chromium"
else
  echo "Chromium not found" >&2
  exit 1
fi

exec "$CHROME_BIN" \
  --kiosk \
  --incognito \
  --noerrdialogs \
  --disable-infobars \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  http://127.0.0.1:5000/player
