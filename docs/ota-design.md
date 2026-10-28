# Over-the-air updates: design (not built)

v1 kiosks are a browser pointing at the web app, so most "updates" are a new web build on the server.
This document covers the two kinds of update that do need care: the **web app** and the **kiosk
image** (browser, policy files, OS packages). Nothing here is implemented; it is the plan a first
pilot should follow, so each rule can be tested before devices are in cells.

## What updates and how

| Layer | Updated by | Notes |
|---|---|---|
| API and database | Operator deploy (`docker compose` or the facility's process) | Migrations are forward-only and run as the schema owner. Rollback = restore the pre-deploy backup; see below. |
| Web app (`/resident`, `/staff`) | Served from the server; the kiosk loads it on each start | The app version is reported in every heartbeat (`app_version`), so staff see which devices run which build. |
| Kiosk config (policy JSON, nftables, systemd units) | Signed package, below | Rewritten idempotently by `deploy/kiosk/provision-kiosk.sh`. |
| Browser and OS packages | Signed package from the facility's own mirror | Unattended security updates only from that mirror. |

## Staged rollout

1. **Build and sign.** CI builds the web app and the kiosk package, then signs the manifest
   (`manifest.json`: version, file hashes, minimum compatible API version, rollback version). The
   signing key lives offline or in the operator's secrets store, never on a kiosk or in the repository.
2. **Canary.** A staff user (admin) marks a small set of devices (for example 2 devices, in a unit
   chosen for easy physical access) as the canary ring. They fetch the new version first.
3. **Soak.** The canary must run for a set time (default 24 h) with healthy heartbeats: no crash
   loops, no stale views, `queue_pending` draining, a successful test call on a test device.
4. **Waves.** Promote to one hub, then the rest, in waves capped at 10 percent of the fleet per hour.
   Waves skip any device that is on a call or has `queue_pending` above zero, and never run during a
   scheduled video visit window.
5. **Stop rule.** If more than 2 percent of a wave fail their health check, the rollout pauses itself
   and alerts staff. A person decides to continue or roll back.

## Signed updates

- The device holds only the **public** verification key (installed at provisioning).
- A package is accepted only if the manifest signature verifies, the file hashes match, the version is
  newer than the installed one, and it is not on a revocation list the server publishes.
- Updates are downloaded over the same HTTPS host as the app, never from another origin (the kiosk
  firewall allows only the app server, resolver and time server).
- Device tokens are never inside a package. A package cannot change who the device is assigned to.

## Rollback

- Each device keeps the **previous** version installed beside the new one (two slots, A and B).
  Switching slots is a symlink change plus a browser restart; no download needed.
- Automatic rollback: after an update the device must report a healthy heartbeat and load `/resident`
  within 5 minutes. If not, it boots the previous slot and reports `update_failed` with the reason.
- Manual rollback: staff push a `rollback` command (the existing `device_commands` mechanism carries
  `restart` today; `rollback` and `update` are new kinds). Commands are audited like other staff actions.
- API rollback: restore the backup taken at deploy time (`docs/backup-drill.md`). Because migrations
  are forward-only, **a rollback that goes past a migration means a restore**, which is why the
  rollout never promotes devices past the API version they are compatible with.

## A device that is offline during an update

- Cached locks keep applying until `valid_until`; then the device fails closed to protected baseline.
  An update never makes an offline device less restrictive, and never removes baseline access.
- The device fetches its target version on reconnect. If it has been offline for several versions it
  jumps to the current signed version (packages carry a minimum-from version so a very old device
  installs a bridge version first).
- A device stale for longer than `offline_alert_minutes` is already shown to staff; an update that
  cannot reach it adds `update_pending` to the same alert.
- Residents' queued appeals and staff requests stay in local storage and are sent when the connection
  returns; an update restart does not clear that queue (it lives in the persistent browser profile).
- A device that never comes back is a hardware problem; the runbook in `docs/admin-guide.md` covers
  replacing it and re-pairing.

## Safety rules that apply to every update

1. Never update a device during an active call (a call ends on a restart).
2. Never ship a change that alters protected baseline behaviour without the tests for invariant 1 passing on the exact build.
3. Record every update as an audit entry: who approved it, the version, the ring and the result.
4. Keep the kiosk firewall allow-list and the browser policy file under version control; a package may update them but a reviewer must see the diff.

## What is needed to build this

A signing key and process, an update agent on the kiosk (a small systemd service), two new device
command kinds, an admin screen for rings and waves, and a staging fleet. **Needs real hardware to
verify**; the pieces that do not (manifest signing and verification, wave selection, stop rule) can be
unit tested first.
