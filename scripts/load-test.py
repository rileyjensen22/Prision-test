"""Load test: many simulated kiosks and a few staff screens against a real API process.

    python scripts/load-test.py [--devices 500] [--seconds 60] [--speed 5] [--workers 4]

Builds a throwaway database (isd_load) with synthetic residents, starts uvicorn on port 8002, then
runs one asyncio task per device: every poll interval it fetches its resident view, and on the
heartbeat interval it reports health; some devices also list courses or file a staff request.
`--speed 5` runs the intervals five times faster than a real kiosk (30 s view poll, 60 s heartbeat),
so 500 devices at speed 5 is the load of 2,500 devices. Staff screens poll the roster and the
dashboard. Exit code 0 only if there were no errors and the latency limits held.
"""

import argparse
import asyncio
import json
import os
import random
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from isd import settings
from isd.auth import hash_device_token, hash_password, make_token
from isd.config_loader import load_config
from isd.models import Cell, Device, DeviceAssignment, Resident, Staff
from isd.services.audit import SYSTEM
from isd.services.config_store import set_config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
DB = "isd_load"
PORT = 8002
VIEW_POLL, HEARTBEAT = 30.0, 60.0  # a real kiosk, in seconds


def build_database(
    devices: int, scale: str | None = None, occupancy: float = 0.9
) -> tuple[str, dict[str, str], dict[str, str]]:
    owner = make_url(settings.MIGRATION_DATABASE_URL)
    admin = create_engine(owner.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {DB}"))
    admin.dispose()
    url = owner.set(database=DB).render_as_string(False)
    cfg = Config(str(ROOT / "api" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "api" / "alembic"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    tokens: dict[str, str] = {}
    with Session(create_engine(url)) as s, s.begin():
        for name, payload in load_config().items():
            set_config(s, SYSTEM, name, payload, "load test")
        staff = Staff(
            username="load_admin", role="admin", password_hash=hash_password("x")
        )
        s.add(staff)
        s.flush()
        if scale:  # the facility model at a named scale, a device in each occupied cell
            from isd.services import facility_model
            from isd.synthetic import populate

            tokens.update(
                populate(
                    s,
                    facility_model.scale_named(s, scale),
                    occupancy=occupancy,
                    now=datetime.now(UTC),
                    token_for=lambda cell: f"load-token-{cell}",
                )
            )
            devices = 0
        for i in range(devices):
            r = Resident(code=f"LOAD-{i:04d}", display_name=f"Synthetic {i}")
            c = Cell(code=f"LC-{i:04d}", unit="AB"[i % 2])
            d = Device(code=f"LD-{i:04d}")
            tokens[d.code] = f"load-token-{i:04d}"
            d.token_hash = hash_device_token(tokens[d.code])
            s.add_all([r, c, d])
            s.flush()
            s.add(DeviceAssignment(device_id=d.id, cell_id=c.id, resident_id=r.id))
        admin_headers = {"Authorization": f"Bearer {make_token(staff.id)}"}
    # A fresh database has no statistics yet; real ones get them from autovacuum within a minute.
    with create_engine(url, isolation_level="AUTOCOMMIT").connect() as c:
        c.execute(text("ANALYZE"))
    return url, tokens, admin_headers


class Stats:
    """Latencies per endpoint. Samples before `measure_from` (a time.monotonic() value) are the
    warm-up (cold caches, the first connections) and are not counted."""

    def __init__(self, measure_from: float = 0.0) -> None:
        self.times: dict[str, list[float]] = {}
        self.errors: dict[str, int] = {}
        self.statuses: dict[int, int] = {}
        self.measure_from = measure_from

    def add(self, name: str, seconds: float, status: int) -> None:
        if time.monotonic() < self.measure_from:
            return
        self.times.setdefault(name, []).append(seconds * 1000)
        self.statuses[status] = self.statuses.get(status, 0) + 1
        if status >= 400:
            self.errors[name] = self.errors.get(name, 0) + 1


async def call(client, stats, name, method, path, **kw):
    started = time.perf_counter()
    try:
        r = await client.request(method, path, **kw)
        status = r.status_code
    except httpx.HTTPError:
        status = 599
    stats.add(name, time.perf_counter() - started, status)


async def device_loop(client, stats, token, stop_at, speed, rng):
    headers = {"X-Device-Token": token}
    hb = {"storage_used_mb": 20, "storage_quota_mb": 4000, "camera": "ok", "microphone": "ok",
          "app_version": "load", "queue_pending": 0, "online": True}  # fmt: skip
    await asyncio.sleep(
        rng.random() * VIEW_POLL / speed
    )  # devices do not all start together
    next_hb = time.monotonic()
    while time.monotonic() < stop_at:
        await call(client, stats, "device view", "GET", "/device/view", headers=headers)
        if time.monotonic() >= next_hb:
            await call(
                client,
                stats,
                "heartbeat",
                "POST",
                "/device/heartbeat",
                headers=headers,
                json=hb,
            )
            next_hb = time.monotonic() + HEARTBEAT / speed
        roll = rng.random()
        if roll < 0.10:
            await call(
                client, stats, "courses", "GET", "/device/courses", headers=headers
            )
        elif roll < 0.13:
            await call(client, stats, "staff request", "POST", "/device/requests", headers=headers,
                       json={"kind": "staff", "client_id": f"load-{rng.getrandbits(48):x}"})  # fmt: skip
        await asyncio.sleep(VIEW_POLL / speed * (0.9 + 0.2 * rng.random()))


async def staff_loop(client, stats, headers, stop_at, speed, rng, grouped):
    """What the staff screens poll. A facility build is browsed by hub (one page of the roster at a
    time); the legacy flat build loads the whole roster."""
    while time.monotonic() < stop_at:
        if grouped:
            hub = f"H{rng.randrange(1, grouped + 1)}"
            steps = (("staff roster", f"/staff/roster/page?hub={hub}&limit=100"),
                     ("staff overview", "/staff/facility/overview"),
                     ("staff summary", "/staff/summary"),
                     ("staff devices", "/staff/devices?limit=100"))  # fmt: skip
        else:
            steps = (("staff roster", "/staff/roster"), ("staff summary", "/staff/summary"),
                     ("staff devices", "/staff/devices"))  # fmt: skip
        for name, path in steps:
            await call(client, stats, name, "GET", path, headers=headers)
        await asyncio.sleep(10.0 / speed)


async def run(tokens, admin_headers, seconds, speed, base, grouped=0, warmup=0.0):
    stats, rng = Stats(time.monotonic() + warmup), random.Random(7)
    stop_at = time.monotonic() + warmup + seconds
    limits = httpx.Limits(max_connections=800, max_keepalive_connections=800)
    async with httpx.AsyncClient(base_url=base, timeout=30, limits=limits) as client:
        tasks = [
            device_loop(client, stats, t, stop_at, speed, rng) for t in tokens.values()
        ]
        tasks += [
            staff_loop(client, stats, admin_headers, stop_at, speed, rng, grouped)
            for _ in range(5)
        ]
        await asyncio.gather(*tasks)
    return stats


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))]


def start_server(url: str, workers: int) -> subprocess.Popen:
    app_url = make_url(settings.DATABASE_URL).set(database=DB).render_as_string(False)
    env = {
        **os.environ,
        "DATABASE_URL": app_url,
        "IP_MAX_PER_MINUTE": "100000000",
        "DEVICE_MAX_PER_MINUTE": "1000000",
        "STAFF_MAX_PER_MINUTE": "1000000",
        "LOG_LEVEL": os.environ.get("LOAD_LOG_LEVEL", "WARNING"),
        # Postgres allows 100 connections by default: 4 workers x (15 + 5 + 4 for the limiter).
        "DB_POOL_SIZE": os.environ.get("LOAD_POOL", "15"),
        "DB_POOL_OVERFLOW": "5",
        "RATE_LIMIT_STORE": os.environ.get(
            "LOAD_RATE_STORE", "postgres"
        ),  # shared, as in production
    }
    log_path = os.environ.get(
        "LOAD_SERVER_LOG"
    )  # keep the server's log, for finding a slow request
    log_out = open(log_path, "w") if log_path else subprocess.DEVNULL  # noqa: SIM115
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "isd.main:app", "--port", str(PORT), "--workers", str(workers)],
        cwd=ROOT / "api", env=env,
        stdout=log_out, stderr=subprocess.STDOUT,
    )  # fmt: skip


def wait_for_server() -> None:
    for _ in range(60):
        try:
            if (
                httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=1).status_code
                == 200
            ):
                return
        except httpx.HTTPError:
            time.sleep(0.5)
    raise SystemExit("server did not start")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", type=int, default=500)
    ap.add_argument(
        "--scale", default=None, help="facility scale from config/facility.yaml (full)"
    )
    ap.add_argument("--occupancy", type=float, default=0.9)
    ap.add_argument(
        "--seconds", type=int, default=60, help="measured time, after the warm-up"
    )
    ap.add_argument(
        "--warmup", type=int, default=15, help="seconds before counting starts"
    )
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=4)
    # Budgets (docs/operations.md): what a kiosk waits for, and what a staff screen waits for.
    ap.add_argument("--device-p95-ms", type=float, default=250.0)
    ap.add_argument("--device-p99-ms", type=float, default=1000.0)
    ap.add_argument("--staff-p95-ms", type=float, default=1000.0)
    ap.add_argument("--staff-p99-ms", type=float, default=2500.0)
    ap.add_argument(
        "--report", type=Path, default=ROOT / "var" / "load-test-report.json"
    )
    args = ap.parse_args()

    print(f"building {args.scale or args.devices} synthetic devices...")
    url, tokens, admin_headers = build_database(
        args.devices, args.scale, args.occupancy
    )
    args.devices = len(tokens)
    grouped = 0
    if args.scale:
        from isd.services import facility_model  # noqa: F401  (only to name the hubs below)

        grouped = len(
            {t.split("-")[2] for t in tokens}
        )  # hubs: H1..Hn from the cell codes
    server = start_server(url, args.workers)
    try:
        wait_for_server()
        print(
            f"warming up {args.warmup}s, then measuring {args.seconds}s at speed x{args.speed} ({args.devices * args.speed:.0f} device-equivalents)"
        )
        started = time.time()
        stats = asyncio.run(
            run(
                tokens,
                admin_headers,
                args.seconds,
                args.speed,
                f"http://127.0.0.1:{PORT}",
                grouped,
                args.warmup,
            )
        )
        elapsed = time.time() - started
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()

    total = sum(len(v) for v in stats.times.values())
    rows, problems = {}, []
    print(
        f"\n{'endpoint':<18}{'count':>7}{'errors':>8}{'p50':>8}{'p95':>8}{'p99':>8}{'max':>8}  (ms)"
    )
    for name, vals in sorted(stats.times.items()):
        row = {"count": len(vals), "errors": stats.errors.get(name, 0), "p50": statistics.median(vals),
               "p95": pct(vals, 0.95), "p99": pct(vals, 0.99), "max": max(vals)}  # fmt: skip
        rows[name] = row
        print(
            f"{name:<18}{row['count']:>7}{row['errors']:>8}{row['p50']:>8.0f}{row['p95']:>8.0f}{row['p99']:>8.0f}{row['max']:>8.0f}"
        )
        if row["errors"]:
            problems.append(f"{name}: {row['errors']} errors")
        staff_side = name.startswith("staff ")
        p95_limit = args.staff_p95_ms if staff_side else args.device_p95_ms
        p99_limit = args.staff_p99_ms if staff_side else args.device_p99_ms
        if row["p95"] > p95_limit:
            problems.append(f"{name}: p95 {row['p95']:.0f} ms over {p95_limit:.0f}")
        if row["p99"] > p99_limit:
            problems.append(f"{name}: p99 {row['p99']:.0f} ms over {p99_limit:.0f}")
    print(
        f"\n{total} requests in {elapsed:.0f}s ({total / elapsed:.0f}/s); statuses {dict(sorted(stats.statuses.items()))}"
    )
    args.report.parent.mkdir(exist_ok=True)
    args.report.write_text(json.dumps({"when": datetime.now(UTC).isoformat(), "devices": args.devices,
        "seconds": args.seconds, "speed": args.speed, "workers": args.workers, "requests": total,
        "per_second": total / elapsed, "endpoints": rows, "problems": problems}, indent=2))  # fmt: skip
    print(
        "LOAD TEST PASSED"
        if not problems
        else "LOAD TEST FAILED: " + "; ".join(problems)
    )
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
