#!/bin/sh
# Runs inside X as the kiosk user. Starts the browser fullscreen on the resident page.
set -eu
. /etc/isd-kiosk/kiosk.env
DATA=/var/lib/isd-kiosk
URL="https://${ISD_HOST}/resident"

xset s off -dpms s noblank            # never blank the screen
FIRST="$DATA/first-boot-url"          # one-time pairing link left by the provisioning script
if [ -f "$FIRST" ]; then
  URL="$(cat "$FIRST")"
  rm -f "$FIRST"                      # the code is single-use; do not keep it
fi

exec /usr/bin/chromium --kiosk --noerrdialogs --disable-infobars --disable-translate \
  --disable-session-crashed-bubble --no-first-run --overscroll-history-navigation=0 \
  --disable-pinch --check-for-update-interval=31536000 \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 \
  --user-data-dir="$DATA/profile" "$URL"
