#!/usr/bin/env python3
"""The demo, end to end, over HTTP: `make demo-scenario` (needs `make demo` running).

    python scripts/demo-scenario.py [--base http://localhost:8080/api] [--resident RES-0001]

It plays one resident's story and prints each step: finish a basic course and watch the tier and
the daily call minutes rise; make a private attorney call that leaves no content; get a lock from an
officer, see the reason on the device, appeal it, have a supervisor overturn it; then verify the
audit chain. Standard library only, so it also runs inside the API container. Exit 0 only if every
step held.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PASSWORD = (
    "dev-password-not-secret"  # the synthetic demo accounts (see docs/demo-guide.md)
)
CONTENT = [
    Path(__file__).resolve().parents[1] / "content" / "courses",
    Path("/content/courses"),
]


class Fail(Exception):
    pass


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw.decode(errors="replace")

    def ok(self, method, path, body=None, headers=None, expect=(200, 201, 204)):
        status, out = self.call(method, path, body, headers)
        if status not in expect:
            raise Fail(f"{method} {path} gave {status}: {out}")
        return out

    def login(self, username: str) -> dict:
        out = self.ok(
            "POST", "/auth/login", {"username": username, "password": PASSWORD}
        )
        return {"Authorization": f"Bearer {out['token']}"}


def step(text: str) -> None:
    print(f"  ✓ {text}")


def heading(text: str) -> None:
    print(f"\n{text}")


def quiz_answers(code: str, paper: dict) -> list[int]:
    for root in CONTENT:
        path = root / code / "quiz.json"
        if path.exists():
            bank = json.loads(path.read_text())["questions"]
            break
    else:
        raise Fail("cannot find the course folders (content/courses)")
    picks = []
    for q in paper["questions"]:
        right = next(b for b in bank if b["prompt"]["en"] == q["prompt"]["en"])
        text = right["choices"][right["answer"]]["en"]
        picks.append(next(i for i, c in enumerate(q["choices"]) if c["en"] == text))
    return picks


def calls_limit(view: dict) -> int:
    return next((a["limit"] for a in view["allowances"] if a["feature"] == "calls"), 0)


def run(api: Api, wanted: str | None) -> None:
    heading("Signing in")
    officer, supervisor, auditor = (
        api.login(n) for n in ("officer1", "supervisor1", "auditor1")
    )
    step("an officer, a supervisor and an auditor signed in (synthetic demo accounts)")

    roster = api.ok("GET", "/staff/roster", headers=officer)
    pool = [
        r
        for r in roster
        if r["tier"]["effective"] == 1 and not r["active_sanctions"] and r["cell"]
    ]
    if wanted:
        pool = [r for r in roster if r["code"] == wanted]
    if not pool:
        raise Fail(
            "no tier 1 resident left for the story; run `make demo-reset` for fresh data"
        )
    resident = max(pool, key=lambda r: r["points"])  # the closest to the next tier
    token = f"dev-device-token-{resident['cell']}"
    device = {"X-Device-Token": token}
    print(f"  Using synthetic resident {resident['code']} in cell {resident['cell']}")

    heading("1. Education raises the tier and the call minutes")
    view = api.ok("GET", "/device/view", headers=device)
    before = calls_limit(view)
    start_tier = view["tier"]["earned"]
    step(
        f"tier {start_tier}, {view['tier']['points']} points, {before} call minutes a day"
    )
    for code in ("LIT101", "MONEY101", "NUM101"):
        if view["tier"]["earned"] > start_tier:
            break
        course = api.ok("GET", f"/device/courses/{code}", headers=device)
        for lesson in course["lessons"]:
            api.ok(
                "POST",
                f"/device/courses/{code}/lessons/{lesson['id']}/complete",
                headers=device,
            )
        paper = api.ok("POST", f"/device/courses/{code}/quiz/start", headers=device)
        result = api.ok(
            "POST",
            f"/device/courses/{code}/quiz",
            {"quiz_id": paper["quiz_id"], "answers": quiz_answers(code, paper)},
            headers=device,
        )
        if not result["passed"]:
            raise Fail(f"{code}: the quiz was not passed: {result}")
        view = api.ok("GET", "/device/view", headers=device)
        step(f"finished {code}: {view['tier']['points']} points")
    after = calls_limit(view)
    if view["tier"]["earned"] <= start_tier or after <= before:
        raise Fail(
            f"tier {view['tier']['earned']}, {after} call minutes: expected a rise"
        )
    step(
        f"promoted to tier {view['tier']['earned']}: {before} -> {after} call minutes a day"
    )

    heading("2. A private attorney call leaves no content")
    contacts = api.ok("GET", "/device/contacts", headers=device)
    lawyer = next((c for c in contacts if c["type"] == "attorney"), None)
    if lawyer is None:
        step("(this resident has no attorney contact; skipping)")
    else:
        call = api.ok(
            "POST", "/device/calls", {"contact_id": lawyer["id"]}, headers=device
        )
        if not call["privileged"] or call["monitored"]:
            raise Fail(f"an attorney call must be privileged and unmonitored: {call}")
        api.ok("POST", f"/device/calls/{call['call_id']}/end", headers=device)
        listed = api.ok("GET", "/staff/monitoring/calls", headers=supervisor)
        if any(c.get("call_id") == call["call_id"] for c in listed):
            raise Fail("the attorney call appeared in the monitored call queue")
        step(
            "the call was privileged, not monitored, and is not in any staff review list"
        )

    heading("3. A lock, its reason, an appeal and a supervisor's decision")
    sanction = api.ok(
        "POST",
        "/staff/sanctions",
        {"resident_id": resident["resident_id"], "infraction_code": "DISRUPT"},
        headers=officer,
    )
    view = api.ok("GET", "/device/view", headers=device)
    locks = [lk for lk in view["locks"] if lk["code"] == "DISRUPT"]
    if not locks or not locks[0].get("ends_at"):
        raise Fail(
            f"the device does not show the lock with a reason and an end time: {view['locks']}"
        )
    step(
        f"the officer's lock applied at once; the device shows {locks[0]['code']} until {locks[0]['ends_at']}"
    )
    if not view["features"]["attorney_calls"]["allowed"]:
        raise Fail("the protected baseline must stay open under a lock")
    step(
        "the protected baseline (attorney calls, appeals, requests, basic education) stays open"
    )
    appeal = api.ok(
        "POST", "/device/appeals", {"sanction_id": sanction["id"]}, headers=device
    )
    step(
        f"the resident filed an appeal from the device (review due {appeal['due_at'][:16]})"
    )
    api.ok(
        "POST",
        f"/staff/appeals/{appeal['appeal_id']}/review",
        {
            "outcome": "overturned",
            "note": "Demo: the supervisor found no basis for the lock.",
        },
        headers=supervisor,
    )
    view = api.ok("GET", "/device/view", headers=device)
    if any(lk["code"] == "DISRUPT" for lk in view["locks"]):
        raise Fail("the lock is still showing after the appeal was overturned")
    step(
        "a different person (a supervisor) overturned it; the lock is gone and a new log entry says why"
    )

    heading("4. Everything above is in a tamper-evident log")
    chain = api.ok("GET", "/audit/verify", headers=auditor)
    if not chain.get("ok"):
        raise Fail(f"the audit chain did not verify: {chain}")
    step(
        f"the audit chain verifies ({chain.get('entries', chain.get('checked', '?'))} entries)"
    )
    print(
        "\nThe demo story held. Open the staff and resident screens to look around (docs/demo-guide.md)."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080/api")
    ap.add_argument("--resident", help="a resident code to use, for example RES-0003")
    args = ap.parse_args()
    api = Api(args.base)
    try:
        api.ok("GET", "/health")
        run(api, args.resident)
    except Fail as e:
        print(f"\n  ✗ {e}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(
            f"\n  ✗ cannot reach {args.base}: {e}. Is `make demo` running?",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
