# Demo guide

For someone who has never seen the system. About 20 minutes. Everything here is synthetic.

## 1. Start it

```
make demo
```

First run: it builds three containers (Postgres, the API, the web app) and loads demo data; allow a few
minutes. Later runs take about half a minute. When it finishes it prints the addresses. You need only a
browser.

Prefer to watch first? `make demo-scenario` (below) runs the main story and prints each step.

## 2. What you are looking at

- A **resident's screen** (`/resident`): what a person in a cell sees on the wall-mounted device. There is no
  login; the address after `#device=` is what pairs a screen with a resident, the way staff pair a real device.
- The **staff dashboard** (`/staff`): what officers, supervisors, administrators and auditors use.
- The **rules** that hold everywhere: some things never lock (legal materials, grievances and appeals,
  medical and mental-health requests, the Request staff button, attorney calls, basic education, reentry
  information, religious texts, the minimum out-of-cell time). Every lock shows a reason, an end time and how
  to appeal. Every staff decision is in an append-only, hash-chained audit log.

## 3. A walk through

**A resident's day** (open `http://localhost:8080/resident#device=dev-device-token-A-03`)

1. The home screen shows the current tier, points to the next tier, what each tier unlocks, daily and weekly
   allowances left, and any locks with their reason and end time. **Request staff** is always at the bottom.
2. Open **Basic education**, start a course, read the lessons and take the quiz. A pass earns points; enough
   points raise the tier, and the daily call minutes rise with it (check the allowance on the home screen).
3. Open **Chess** (the computer opens at tier 2; playing other residents at tier 5), pick a level and play. Playing the computer works with the network off, too.
4. Open **Calls** (cells A-01 to A-06 have contacts). A family call is *monitored*; an attorney call is
   *privileged* and nothing about its content is kept, by design.
5. Ask staff to change the language or text size: residents cannot change these themselves (staff do it from the
   resident's page).

**A staff day** (sign in as `supervisor1`, password `dev-password-not-secret`)

1. The **dashboard** shows what needs attention and the facility by hub, line and floor. Open a floor to see its
   residents on the **roster**.
2. Open a resident. **Record an infraction** (for example *Disruptive behavior*): minor ones apply at once;
   larger ones need a second person to confirm. The resident's screen now shows the lock, why, until when, and
   an **Appeal** button.
3. Sign in as another supervisor in a private window, open **Confirmations** or **Appeals**, and decide. The
   person who issued something cannot be the one who confirms or reviews it.
4. **Audit** shows every step with who, role, target and reason; the chain checks itself.
5. **View as resident** shows what a resident would see under any tier or lock without changing anything
   (a "SIMULATION" banner stays on). **Live mirror** shows a real device's current screen, read-only, and logs it.
6. **Monitoring**, **Keep separate**, **Welfare**, **Out of cell**, **Schedule**, **Config** and **Outcomes** are the
   rest of the working surface. **Config** changes are versioned and audit-logged.

## 4. The scripted story

`make demo-scenario` plays one resident's story over the API and prints each step:

1. an officer, a supervisor and an auditor sign in;
2. the resident finishes basic courses; their tier rises and daily call minutes go up (for example 15 to 20);
3. the resident makes a private attorney call; it is privileged, not monitored, and in no staff review list;
4. an officer locks the resident; the device shows the reason and end time while the protected baseline stays
   open; the resident appeals from the device; a different person (a supervisor) overturns it;
5. the audit chain verifies.

Run it again and it picks another resident. `make demo-reset` brings back fresh data. `make demo-smoke` opens the
resident and staff screens in a real browser and checks they load.

## 5. Stop and clean up

```
make demo-down     # stop, keep the data
make demo-reset    # stop and delete the data
make demo-logs     # watch the logs
```

## Troubleshooting

- **"Docker is installed but not running"**: start Docker Desktop (or `sudo systemctl start docker`).
- **Port 8080 is in use**: `ISD_WEB_PORT=8081 make demo` (and `ISD_WEB_PORT=8081 make demo-scenario`).
- **The build cannot reach the internet, with certificate errors**: your network probably inspects TLS. Give the
  build your organisation's certificate authority file: `ISD_EXTRA_CA=/path/to/ca.pem make demo`. It is used only
  while building the images (see `deploy/build-ca/README.md`).
- **It says no tier 1 resident is left**: the scripted story has used them up. `make demo-reset`.
- **Something looks wrong**: `make demo-logs`. The demo uses development passwords and secrets on purpose; never
  expose it to a network you do not control.

## What this demo is not

It is not a deployment. It has one database, development secrets, mock telephony, video, payments and chess
partners, no TLS, and the staff two-step sign-in is off. `docs/operations.md` and `docs/security.md` list what a
real deployment needs, and `docs/STATUS.md` lists what remains to be done and by whom.
