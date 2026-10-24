#!/bin/sh
# Restarts the kiosk if the browser stops answering locally (hung, not just closed).
# Only looks at 127.0.0.1; a lost network connection is normal and must not cause restarts.
set -eu
STATE=/run/isd-kiosk-watchdog
mkdir -p "$STATE"
if curl -fsS --max-time 5 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo 0 > "$STATE/failures"
  exit 0
fi
n=$(( $(cat "$STATE/failures" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$STATE/failures"
if [ "$n" -ge 3 ]; then
  echo "browser not answering ($n checks); restarting kiosk" | systemd-cat -t isd-kiosk-watchdog -p warning
  echo 0 > "$STATE/failures"
  systemctl restart isd-kiosk.service
fi
