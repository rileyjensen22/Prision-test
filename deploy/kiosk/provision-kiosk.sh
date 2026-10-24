#!/usr/bin/env bash
# Turns a fresh Debian/Ubuntu machine into an ISD resident kiosk. Run as root.
#
#   provision-kiosk.sh --host isd.example.org --server-ip 203.0.113.10 \
#       --resolver-ip 203.0.113.53 --ntp-ip 203.0.113.123 [--pair-code ABCD2345] \
#       [--ssh-from 203.0.113.0/28] [--readonly-root --data-dir /mnt/isd-data] [--no-install]
#
#   --root DIR   write every file under DIR and do nothing to the running system (used by tests)
#   --dry-run    print what would be done
#
# Safe to run again: files are rewritten, nothing is duplicated. UNTESTED ON A REAL MACHINE; see
# docs/kiosk.md for the checks to make on the first device.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES="$HERE/files"

HOST="" SERVER_IPS="" RESOLVER_IPS="" NTP_IPS="" PAIR_CODE="" SSH_FROM=""
ROOT="" DRY=0 INSTALL=1 READONLY=0 DATA_DIR="/var/lib/isd-kiosk"

die() { echo "error: $*" >&2; exit 2; }
log() { echo "[provision] $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:-}"; shift 2 ;;
    --server-ip) SERVER_IPS="${2:-}"; shift 2 ;;
    --resolver-ip) RESOLVER_IPS="${2:-}"; shift 2 ;;
    --ntp-ip) NTP_IPS="${2:-}"; shift 2 ;;
    --pair-code) PAIR_CODE="${2:-}"; shift 2 ;;
    --ssh-from) SSH_FROM="${2:-}"; shift 2 ;;
    --data-dir) DATA_DIR="${2:-}"; shift 2 ;;
    --readonly-root) READONLY=1; shift ;;
    --no-install) INSTALL=0; shift ;;
    --root) ROOT="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

# ---- validate everything that ends up in a config file --------------------------------------
[[ "$HOST" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:[0-9]{1,5})?$ ]] || die "--host must be a plain host name (and optional port)"
ipv4='^([0-9]{1,3}\.){3}[0-9]{1,3}$'
check_ips() { # name value
  [ -n "$2" ] || die "$1 is required"
  for ip in ${2//,/ }; do
    [[ "$ip" =~ $ipv4 ]] || die "$1: '$ip' is not an IPv4 address"
    IFS=. read -r a b c d <<<"$ip"
    for o in $a $b $c $d; do [ "$o" -le 255 ] || die "$1: '$ip' is not an IPv4 address"; done
  done
}
check_ips --server-ip "$SERVER_IPS"
check_ips --resolver-ip "$RESOLVER_IPS"
check_ips --ntp-ip "$NTP_IPS"
[ -z "$PAIR_CODE" ] || [[ "$PAIR_CODE" =~ ^[A-Za-z2-9]{6,16}$ ]] || die "--pair-code looks wrong"
[ -z "$SSH_FROM" ] || [[ "$SSH_FROM" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2})?$ ]] || die "--ssh-from must be an IPv4 address or CIDR"
if [ "$READONLY" = 1 ]; then
  [ "$DATA_DIR" != "/var/lib/isd-kiosk" ] || die "--readonly-root needs --data-dir on a separate writable disk or partition: the browser profile holds the device token and must survive a reboot"
fi
[[ "$DATA_DIR" =~ ^/[A-Za-z0-9_./-]+$ ]] || die "--data-dir must be an absolute path"

if [ -z "$ROOT" ] && [ "$DRY" = 0 ] && [ "$(id -u)" -ne 0 ]; then die "run as root"; fi
R="$ROOT"                       # prefix for every path we write ("" = the real system)
live() { [ -z "$ROOT" ] && [ "$DRY" = 0 ]; }   # only touch the running system when really provisioning

run() { if [ "$DRY" = 1 ]; then echo "+ $*"; else "$@"; fi; }

csv_to_nft() { echo "${1//,/, }"; }

render() { # src dst mode  (replaces @TOKENS@ from the variables validated above)
  local src="$1" dst="$2" mode="$3"
  log "write $dst"
  [ "$DRY" = 1 ] && return 0
  mkdir -p "$(dirname "$R$dst")"
  local ssh_rule=""
  [ -z "$SSH_FROM" ] || ssh_rule="    ip saddr $SSH_FROM tcp dport 22 accept"
  sed -e "s|@ISD_HOST@|$HOST|g" \
      -e "s|@SERVER_V4@|$(csv_to_nft "$SERVER_IPS")|g" \
      -e "s|@RESOLVER_V4@|$(csv_to_nft "$RESOLVER_IPS")|g" \
      -e "s|@NTP_V4@|$(csv_to_nft "$NTP_IPS")|g" \
      -e "s|@SSH_RULE@|$ssh_rule|g" "$src" > "$R$dst.tmp"
  chmod "$mode" "$R$dst.tmp"
  mv "$R$dst.tmp" "$R$dst"
}

# ---- packages ---------------------------------------------------------------------------------
if live && [ "$INSTALL" = 1 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends chromium xserver-xorg-core xserver-xorg-input-libinput \
    xinit x11-xserver-utils nftables curl ca-certificates systemd-timesyncd
  [ "$READONLY" = 0 ] || apt-get install -y overlayroot
fi

# ---- the locked-down user ---------------------------------------------------------------------
if live; then
  id isd-kiosk >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --create-home \
      --shell /usr/sbin/nologin --groups video,audio,render,input isd-kiosk
  passwd -l isd-kiosk >/dev/null
fi
log "data directory $R$DATA_DIR"
run mkdir -p "$R$DATA_DIR/profile"
if live; then chown -R isd-kiosk:isd-kiosk "$DATA_DIR"; chmod 0700 "$DATA_DIR"; fi

# ---- files ------------------------------------------------------------------------------------
if [ "$DRY" = 0 ]; then mkdir -p "$R/etc/isd-kiosk"; fi
log "write /etc/isd-kiosk/kiosk.env"
[ "$DRY" = 1 ] || { printf 'ISD_HOST=%s\n' "$HOST" > "$R/etc/isd-kiosk/kiosk.env"; chmod 0644 "$R/etc/isd-kiosk/kiosk.env"; }

render "$FILES/session.sh" /usr/local/lib/isd-kiosk/session.sh 0755
render "$FILES/watchdog.sh" /usr/local/lib/isd-kiosk/watchdog.sh 0755
render "$FILES/isd-kiosk.service" /etc/systemd/system/isd-kiosk.service 0644
render "$FILES/isd-kiosk-watchdog.service" /etc/systemd/system/isd-kiosk-watchdog.service 0644
render "$FILES/isd-kiosk-watchdog.timer" /etc/systemd/system/isd-kiosk-watchdog.timer 0644
render "$FILES/isd-kiosk-nightly.service" /etc/systemd/system/isd-kiosk-nightly.service 0644
render "$FILES/isd-kiosk-nightly.timer" /etc/systemd/system/isd-kiosk-nightly.timer 0644
render "$FILES/chromium-policy.json" /etc/chromium/policies/managed/isd.json 0644
render "$FILES/nftables.conf" /etc/nftables.conf 0600
render "$FILES/logind-isd.conf" /etc/systemd/logind.conf.d/isd-kiosk.conf 0644
render "$FILES/xorg-kiosk.conf" /etc/X11/xorg.conf.d/10-isd-kiosk.conf 0644
render "$FILES/sysctl-isd.conf" /etc/sysctl.d/90-isd-kiosk.conf 0644
render "$FILES/modprobe-isd.conf" /etc/modprobe.d/isd-kiosk.conf 0644

# The one-time pairing link. The code works once and expires, but keep it private anyway.
if [ -n "$PAIR_CODE" ] && [ "$DRY" = 0 ]; then
  log "write first-boot pairing link (single use, removed at first start)"
  printf 'https://%s/resident#pair=%s\n' "$HOST" "$PAIR_CODE" > "$R$DATA_DIR/first-boot-url"
  chmod 0600 "$R$DATA_DIR/first-boot-url"
  live && chown isd-kiosk:isd-kiosk "$DATA_DIR/first-boot-url"
fi

# ---- read-only root (optional) ----------------------------------------------------------------
if [ "$READONLY" = 1 ] && [ "$DRY" = 0 ]; then
  log "read-only root: overlayroot in memory, browser profile on $DATA_DIR"
  mkdir -p "$R/etc"
  printf 'overlayroot="tmpfs:recurse=0"\n' > "$R/etc/overlayroot.local.conf"
fi

# ---- switch it on -----------------------------------------------------------------------------
if live; then
  sysctl --system >/dev/null
  systemctl daemon-reload
  systemctl set-default graphical.target
  for n in 2 3 4 5 6; do systemctl mask "getty@tty$n.service" "autovt@tty$n.service"; done
  systemctl mask ctrl-alt-del.target
  systemctl enable nftables.service systemd-timesyncd.service
  nft -c -f /etc/nftables.conf && systemctl restart nftables.service
  systemctl enable isd-kiosk.service isd-kiosk-watchdog.timer isd-kiosk-nightly.timer
  log "done. Reboot to start the kiosk."
else
  log "staged under '${ROOT:-<dry run>}'; the running system was not changed"
fi
