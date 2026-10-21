# Kiosk (resident device)

The resident UI is the `/resident` route of the web app, shown fullscreen in a locked-down browser. No custom OS in v1.

## Identity

There is no resident login. A staff member provisions each device with a secret **device token** and assigns the device to a cell and resident (`POST /staff/device-assignments`, audit-logged). The kiosk sends the token as `X-Device-Token`; the API stores only its SHA-256 hash.

First launch passes the token once in the URL; the app saves it and removes it from the address bar:

    https://<host>/resident?device=<TOKEN>

Dev data from `make seed` uses `dev-device-token-<cell>` (for example `dev-device-token-A-01`). These are for synthetic data only. Assumption to revisit: a token in localStorage is only as safe as the kiosk's physical and browser lockdown.

## Launch command (draft; finalised in Phase 8)

    chromium --kiosk --incognito --noerrdialogs --disable-translate \
      --overscroll-history-navigation=0 --disable-pinch \
      "https://<host>/resident?device=<TOKEN>"

## Lockdown in the app

- **CSP** (production build): same-origin scripts, styles, images, and API calls only; no inline script, objects, framing of other origins, or form posts. Allowlisted content hosts get added to `KIOSK_CSP` in `web/vite.config.ts` when `approved_content_sources` is wired in. A Playwright test checks that inline script injection is blocked.
- No links leave the app; the context menu and drag-and-drop are disabled; the UI returns home after `inactivity_return_home_seconds` (config, default 90).
- Settings (language, text size, reading level, captions) come from the server and can only be changed by staff.

## Offline behavior

The device caches its last `ResidentView` with a `valid_until` time: the next sanction start or end, or the snapshot TTL (`entitlement_snapshot_ttl_minutes`, default 60), whichever is sooner.

- Before `valid_until`: cached locks still apply, and an "offline" banner is shown.
- After `valid_until` with no connection: the device **fails closed**. Only protected-baseline features stay open, and everything else shows "Paused until the connection returns".
- "Request staff" and appeals work offline. They are saved in a local queue with a client id and delivered in order when the connection returns (the API ignores duplicates).
- Expiry is judged against **server time**: the device records its clock offset on every successful fetch, so a wrong or drifting device clock cannot extend the cache.

## Screen reporting (for the staff live mirror)

On every screen change the kiosk sends only the route (for example `/resident/tier`) to `POST /device/screen`, best effort and silent if offline. The server never stores the route of private services (law library, grievances, medical, mental health); it stores `/resident/redacted` instead. No screen content, keystrokes, or images are sent.
