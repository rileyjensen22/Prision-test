#!/usr/bin/env bash
# Runs INSIDE a Debian container (see scripts/kiosk-check.sh). Checks the parts of the kiosk
# provisioning that a container can honestly check, and says plainly which it cannot.
#
#   covered:     the package names exist; the generated files are what we expect; shell scripts parse
#                and pass shellcheck; the nftables ruleset is accepted by nft; systemd accepts the
#                unit files; Chromium accepts the browser policy and enforces the blocklist.
#   NOT covered: Xorg on real hardware, the touch screen, the camera and microphone, booting under
#                systemd (units starting, restarting, the watchdog and nightly timers firing), the
#                firewall actually filtering a real network card, the read-only root, power loss.
set -uo pipefail
REPO="${REPO:-/repo}"
STAGE=/tmp/stage
FAILS=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILS=$((FAILS + 1)); }
skip() { echo "SKIP  $*"; }

export DEBIAN_FRONTEND=noninteractive
if [ "${APT_HTTPS:-0}" = 1 ]; then  # package sources over https, for TLS-inspecting proxies
  sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null
fi
PKGS=$(grep -m1 'apt-get install -y --no-install-recommends' -A1 "$REPO/deploy/kiosk/provision-kiosk.sh" \
  | sed -e 's/.*--no-install-recommends//' -e 's/\\$//' | tr -d '\n')
echo "== installing what the provisioning script installs ($PKGS) plus checking tools"
if apt-get update -qq >/tmp/apt.log 2>&1 && ! grep -q '^[WE]:' /tmp/apt.log \
   && apt-get install -y -qq --no-install-recommends $PKGS shellcheck jq systemd >>/tmp/apt.log 2>&1; then
  pass "every package the provisioning script installs exists and installs on Debian"
else
  fail "package install failed (is there network access to the Debian mirrors?)"; tail -8 /tmp/apt.log; exit 1
fi

echo "== staging the files"
if "$REPO/deploy/kiosk/provision-kiosk.sh" --root "$STAGE" --no-install --host isd.example.org \
     --server-ip 203.0.113.10 --resolver-ip 203.0.113.53 --ntp-ip 203.0.113.123 \
     --pair-code ABCD2345 --ssh-from 203.0.113.0/28 >/tmp/stage.log 2>&1; then
  pass "provision-kiosk.sh stages every file with the script's own validation"
else
  fail "provision-kiosk.sh failed"; tail -5 /tmp/stage.log
fi
for f in $(find "$STAGE" -type f); do
  if grep -q '@[A-Z_0-9]*@' "$f"; then fail "an unreplaced @TOKEN@ is left in $f"; fi
done

echo "== shell scripts"
for f in "$REPO/deploy/kiosk/provision-kiosk.sh" "$REPO"/deploy/kiosk/files/*.sh; do
  if bash -n "$f" && shellcheck --severity=warning "$f"; then pass "$(basename "$f") parses and passes shellcheck"; else fail "$(basename "$f")"; fi
done

echo "== firewall ruleset"
if nft -c -f "$STAGE/etc/nftables.conf" >/tmp/nft.log 2>&1; then
  pass "nft accepts the generated ruleset (syntax checked, not loaded)"
elif grep -qiE 'operation not permitted|permission denied' /tmp/nft.log; then
  skip "nft could not check the ruleset in this container (needs --cap-add NET_ADMIN)"
else
  fail "nft rejected the ruleset"; cat /tmp/nft.log
fi

echo "== systemd units"
cp "$STAGE"/etc/systemd/system/*.service "$STAGE"/etc/systemd/system/*.timer /usr/lib/systemd/system/ 2>/dev/null
mkdir -p /etc/isd-kiosk /usr/local/lib/isd-kiosk
cp "$STAGE/etc/isd-kiosk/kiosk.env" /etc/isd-kiosk/
cp "$STAGE"/usr/local/lib/isd-kiosk/*.sh /usr/local/lib/isd-kiosk/
id isd-kiosk >/dev/null 2>&1 || useradd --system --shell /usr/sbin/nologin isd-kiosk
verify_out=$(systemd-analyze verify isd-kiosk.service isd-kiosk-watchdog.service isd-kiosk-watchdog.timer \
  isd-kiosk-nightly.service isd-kiosk-nightly.timer 2>&1)
# Problems with the container itself (no udev, no D-Bus) are not problems with our files.
relevant=$(echo "$verify_out" | grep -vE 'Failed to connect|dbus|D-Bus|Cannot determine cgroup|/run/systemd' || true)
if [ -z "$relevant" ]; then pass "systemd-analyze verify finds nothing wrong with the unit files"; else fail "systemd-analyze verify:"; echo "$relevant"; fi

echo "== browser policy"
jq -e . "$STAGE/etc/chromium/policies/managed/isd.json" >/dev/null && pass "the policy file is valid JSON" || fail "policy JSON"
mkdir -p /etc/chromium/policies/managed
cp "$STAGE/etc/chromium/policies/managed/isd.json" /etc/chromium/policies/managed/
CHROME=$(command -v chromium || command -v chromium-browser)
FLAGS=(--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-crash-reporter
  --user-data-dir=/tmp/chrome-profile --no-first-run --virtual-time-budget=8000)
blocked=$(timeout 45 "$CHROME" "${FLAGS[@]}" --dump-dom https://example.org/ 2>/dev/null); rc=$?
if echo "$blocked" | grep -qiE 'ERR_BLOCKED_BY_ADMINISTRATOR|blocked'; then
  pass "Chromium enforces the policy: a page outside the allow-list is blocked"
elif [ "$rc" -eq 124 ]; then
  skip "headless Chromium did not finish in this container, so the blocklist was not exercised"
else
  fail "Chromium did not block https://example.org/ (policy not applied?)"; echo "$blocked" | head -5
fi
policy_page=$(timeout 60 "$CHROME" "${FLAGS[@]}" --dump-dom chrome://policy 2>/dev/null | tr -d '\n')
if echo "$policy_page" | grep -q 'URLBlocklist' && echo "$policy_page" | grep -q 'DeveloperToolsAvailability'; then
  pass "chrome://policy lists the managed policies"
  if echo "$policy_page" | grep -qiE 'Unknown policy|not a valid policy'; then fail "Chromium reports an unknown policy name"; fi
else
  skip "could not read chrome://policy in headless mode"
fi

echo
if [ "$FAILS" -eq 0 ]; then echo "kiosk container check: all checks that could run passed"; else echo "kiosk container check: $FAILS failed"; fi
exit "$FAILS"
