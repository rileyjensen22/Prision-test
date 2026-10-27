#!/usr/bin/env bash
# `make kiosk-check`: checks the kiosk provisioning in a throwaway Debian container (needs Docker).
# What it can and cannot prove is written at the top of deploy/kiosk/container-check.sh and in
# docs/kiosk.md. Behind a proxy it passes the usual proxy variables to apt.
set -euo pipefail
cd "$(dirname "$0")/.."
args=()
for v in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
  [ -z "${!v:-}" ] || args+=(-e "$v=${!v}")
done
# Behind a proxy on this machine's loopback (some build sandboxes), the container must share the
# host network, and a TLS-inspecting proxy needs its certificate authority and https package sources:
#   KIOSK_CHECK_HOST_NETWORK=1 ISD_EXTRA_CA=/path/to/ca.pem make kiosk-check
[ "${KIOSK_CHECK_HOST_NETWORK:-0}" != 1 ] || args+=(--network host)
if [ -n "${ISD_EXTRA_CA:-}" ]; then
  args+=(-v "$ISD_EXTRA_CA":/etc/ssl/certs/ca-certificates.crt:ro -e APT_HTTPS=1)
fi
exec docker run --rm --cap-add NET_ADMIN "${args[@]}" -v "$PWD":/repo:ro \
  "${KIOSK_CHECK_IMAGE:-debian:bookworm}" bash /repo/deploy/kiosk/container-check.sh
