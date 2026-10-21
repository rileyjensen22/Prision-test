# Kiosk (resident device)

The resident UI is the `/resident` route of the web app, shown fullscreen in a locked-down browser. No custom OS in v1.

## Identity

There is no resident login. A staff member assigns each device to a cell and resident (`POST /staff/device-assignments`, audit-logged). The device proves who it is with a secret **device token**; the server keeps only its hash.

Give the kiosk its token in the URL **fragment**, never the query string:

    https://<host>/resident#device=<TOKEN>

A fragment is not sent to the web server, so the token does not appear in access logs or proxy logs. The app saves the token on the device and removes it from the address bar. A token in a query string (`?device=`) is ignored and removed. Issue or replace a token with `python scripts/rotate-device-token.py DEVICE_CODE` (shown once; the old one stops working).

Development data from `make seed` uses predictable tokens (`dev-device-token-<cell>`, for example `dev-device-token-A-01`) for synthetic data only. The seed refuses to run when `ISD_ENV=production`; issue real tokens with the rotate script.

## Launch (Chromium on Linux) — UNTESTED ON A REAL DEVICE IMAGE

    chromium --kiosk --noerrdialogs --disable-infobars --disable-translate \
      --disable-session-crashed-bubble --no-first-run --overscroll-history-navigation=0 \
      --disable-pinch --user-data-dir=/var/lib/isd-kiosk \
      "https://<host>/resident"

- Use a dedicated profile directory (`--user-data-dir`) that persists. **Do not use `--incognito`**: it would erase the saved device token at every restart.
- Provision the first run once with `…/resident#device=<TOKEN>`; afterwards the plain address is enough.

Browser policy file (for example `/etc/chromium/policies/managed/isd.json`); policy names are from Chromium's enterprise policy list and must be checked against the browser version you install:

    {
      "URLBlocklist": ["*"],
      "URLAllowlist": ["https://<host>/resident*"],
      "DeveloperToolsAvailability": 2,
      "DownloadRestrictions": 3,
      "PasswordManagerEnabled": false,
      "PrintingEnabled": false,
      "TranslateEnabled": false,
      "IncognitoModeAvailability": 1,
      "BrowserSignin": 0,
      "SyncDisabled": true,
      "DefaultPopupsSetting": 2,
      "ExtensionInstallBlocklist": ["*"]
    }

Start the browser from the system's kiosk session or a systemd service, restart it if it exits, and disable the desktop, keyboard shortcuts, USB storage and any other way to reach a shell. Those steps depend on the OS image and are outside this repository.

## What the app does to protect itself

- **CSP** (production build): same-origin scripts, styles, images, and API calls only; no inline script, plugins, framing of other origins, or form posts. A Playwright test checks that injected inline script is blocked. Allow-listed content hosts get added to `KIOSK_CSP` in `web/vite.config.ts` when `approved_content_sources` gains external sources.
- No links leave the app; the context menu and drag-and-drop are disabled; the UI returns home after `inactivity_return_home_seconds` (config, default 90).
- Settings (language, text size, reading level, captions) come from the server and can only be changed by staff.
- Serve the web app with the headers in `deploy/nginx.conf.example` (frame denial, HSTS, no sniffing, a permissions policy). The camera permission is off until the video feature is real.

## Offline behavior

The device caches its last `ResidentView` with a `valid_until` time: the next sanction start or end, or the snapshot TTL (`entitlement_snapshot_ttl_minutes`, default 60), whichever is sooner.

- Before `valid_until`: cached locks still apply, and an "offline" banner is shown.
- After `valid_until` with no connection: the device **fails closed**. Only protected-baseline features stay open, and everything else shows "Paused until the connection returns".
- "Request staff" and appeals work offline. They wait in a local queue with a client id and are delivered in order when the connection returns (the API ignores duplicates).
- Expiry is judged against **server time**: the device records its clock offset on every successful fetch, so a wrong or drifting device clock cannot extend the cache.

## Screen reporting (for the staff live mirror)

On every screen change the kiosk sends only the route (for example `/resident/tier`) to `POST /device/screen`, best effort and silent if offline. The server never stores the route of private services (law library, grievances, medical, mental health); it stores `/resident/redacted` instead. No screen content, keystrokes, or images are sent.
