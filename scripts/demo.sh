#!/usr/bin/env bash
# `make demo`: start Postgres, the API and the web app in Docker with synthetic demo data, then print
# where to go and how to sign in. Needs Docker with the compose plugin. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${ISD_WEB_PORT:-8080}"
export ISD_WEB_PORT="$PORT"
# Behind a proxy that inspects TLS, the image builds need its certificate authority:
#   ISD_EXTRA_CA=/path/to/ca.pem make demo
if [ -n "${ISD_EXTRA_CA:-}" ]; then
  [ -r "$ISD_EXTRA_CA" ] || { echo "ISD_EXTRA_CA: cannot read $ISD_EXTRA_CA" >&2; exit 1; }
  cp "$ISD_EXTRA_CA" deploy/build-ca/extra-ca.pem
fi

command -v docker >/dev/null 2>&1 || { echo "Docker is needed: https://docs.docker.com/get-docker/" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose (the 'docker compose' command) is needed." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is installed but not running (start Docker Desktop or the docker service)." >&2; exit 1; }

echo "Building and starting the demo. The first run downloads images and can take several minutes."
if ! docker compose up -d --build; then
  echo "Starting failed. The last log lines:" >&2
  docker compose logs --tail=40 >&2 || true
  exit 1
fi

echo -n "Waiting for the app"
for _ in $(seq 1 90); do
  if curl -fsS "http://localhost:${PORT}/api/health" >/dev/null 2>&1; then ready=1; break; fi
  echo -n "."; sleep 2
done
echo
if [ "${ready:-0}" != 1 ]; then
  echo "The app did not come up in time. Logs:" >&2
  docker compose logs --tail=60 >&2 || true
  exit 1
fi

cat <<EOF

ISD demo is running  (development secrets and synthetic people only; not for real use)

  Staff dashboard   http://localhost:${PORT}/staff
  API documentation http://localhost:8000/docs      (this computer only)

Staff sign-in (password for all: dev-password-not-secret)
  officer1  supervisor1  supervisor2  admin1  auditor1

Resident screens (each opens a different synthetic resident, as a kiosk would)
  http://localhost:${PORT}/resident#device=dev-device-token-A-01
  http://localhost:${PORT}/resident#device=dev-device-token-A-02
  http://localhost:${PORT}/resident#device=dev-device-token-A-03
  (cells A-01 to A-12; the address after # is what pairs a screen with a resident)

Next:  make demo-scenario   plays the whole story for you
       docs/demo-guide.md   a walk through, step by step
       make demo-down       stops it (data is kept);  make demo-reset  also wipes the data
EOF
