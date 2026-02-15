#!/usr/bin/env bash
set -eu

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/pw/.Xauthority}"

# Wait for the desktop X session to come up before launching Chromium.
for _ in $(seq 1 30); do
  if xset q >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

xset -dpms >/dev/null 2>&1 || true
xset s off >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true

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
  --no-first-run \
  --no-default-browser-check \
  --disable-sync \
  --password-store=basic \
  --user-data-dir=/home/pw/.config/vframe-kiosk \
  --noerrdialogs \
  --disable-infobars \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  http://127.0.0.1:5000/player
