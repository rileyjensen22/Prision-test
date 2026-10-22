"""Record real kiosk API responses (from the e2e stack on :8001) into web/src/demo/fixtures.json.

Synthetic data only. The phone demo replays these; nothing is sent anywhere."""

import json
import sys
import urllib.request
from pathlib import Path

BASE = "http://localhost:8001"
OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "demo" / "fixtures.json"
ANSWERS = [0, 1, 0, 1, 0]  # sample course MONEY101


def call(token, path, method="GET", body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "X-Device-Token": f"e2e-token-{token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"__error": e.code, "body": json.load(e)}


def snapshot(token):
    snap = {}
    for p in (
        "/device/view",
        "/device/contacts",
        "/device/commissary",
        "/device/courses",
        "/device/courses/MONEY101",
        "/device/jobs",
        "/device/rec",
        "/device/reading",
    ):
        snap[p] = call(token, p)
    for item in (
        snap["/device/reading"] if isinstance(snap["/device/reading"], list) else []
    ):
        snap[f"/device/reading/{item['id']}"] = call(
            token, f"/device/reading/{item['id']}"
        )
    for c in (
        snap["/device/contacts"] if isinstance(snap["/device/contacts"], list) else []
    ):
        snap[f"/device/messages?contact_id={c['id']}"] = call(
            token, f"/device/messages?contact_id={c['id']}"
        )
    return snap


out = {"scenarios": {}}
for token, label in (("alice", "locked"), ("gina", "loop"), ("tess", "tier4")):
    out["scenarios"][token] = {"label": label, "before": snapshot(token)}

# the demo loop: finish the sample course as gina, then record what changed
for lesson in ("budget", "saving", "debt"):
    r = call("gina", f"/device/courses/MONEY101/lessons/{lesson}/complete", "POST")
    out.setdefault("lesson_responses", {})[lesson] = r
quiz = call("gina", "/device/courses/MONEY101/quiz", "POST", {"answers": ANSWERS})
out["quiz_response"] = quiz
out["scenarios"]["gina"]["after"] = snapshot("gina")

# one real call as tess (family contact), for the call screen shape
fam = next(
    (
        c
        for c in out["scenarios"]["tess"]["before"]["/device/contacts"]
        if c["type"] == "family"
    ),
    None,
)
if fam:
    started = call("tess", "/device/calls", "POST", {"contact_id": fam["id"]})
    out["call_started"] = started
    if "call_id" in started:
        out["call_ended"] = call(
            "tess", f"/device/calls/{started['call_id']}/end", "POST"
        )

OUT.write_text(json.dumps(out, indent=1))
print("wrote", OUT, OUT.stat().st_size, "bytes", file=sys.stderr)
