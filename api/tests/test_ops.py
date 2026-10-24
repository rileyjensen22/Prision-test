"""Operations: structured logs that leak nothing, and a rate limit on every route."""

import json
import logging

import pytest

from isd import limits
from isd.logging_config import JsonFormatter, configure_logging
from isd.main import app
from tests.helpers import iter_api_routes

pytestmark = pytest.mark.usefixtures("committed_config")


@pytest.fixture
def request_lines(caplog):
    caplog.set_level(logging.INFO, logger="isd.request")
    logging.getLogger("isd").propagate = True  # let caplog see it
    yield lambda: [r for r in caplog.records if r.name == "isd.request"]
    logging.getLogger("isd").propagate = False


def test_a_request_line_has_the_expected_fields_and_a_request_id_header(client, request_lines):
    r = client.get("/health")
    rec = request_lines()[-1]
    assert (rec.method, rec.route, rec.status, rec.caller) == ("GET", "/health", 200, "anonymous")
    assert rec.request_id == r.headers["x-request-id"]
    assert rec.duration_ms >= 0


def test_logs_never_contain_tokens_query_strings_or_bodies(client, staff_tokens, request_lines):
    needle = "leak-probe-" + "d3v1ce-v4lue"
    client.get("/device/view?probe=SENSITIVE-QUERY", headers={"X-Device-Token": needle})
    client.post("/auth/login", json={"username": "someone", "password": "hunter2-body-text"})
    client.get("/audit", headers=staff_tokens["admin"])
    formatter = JsonFormatter()
    text = "\n".join(formatter.format(r) for r in request_lines())
    for leaked in (needle, "SENSITIVE-QUERY", "hunter2-body-text", "someone", "Bearer"):
        assert leaked not in text
    kinds = {json.loads(line)["caller"] for line in text.splitlines()}
    assert {"device", "staff", "anonymous"} <= kinds


def test_paths_are_logged_as_templates_not_real_ids(client, staff_tokens, request_lines):
    client.get("/staff/residents/987654", headers=staff_tokens["admin"])
    rec = request_lines()[-1]
    assert "987654" not in rec.route and rec.route == "/staff/residents/{resident_id}"


def test_each_line_is_valid_json_and_errors_log_only_the_type():
    try:
        raise ValueError("a message that holds a resident name")
    except ValueError:
        import sys

        rec = logging.LogRecord("isd.x", logging.ERROR, __file__, 1, "boom", (), sys.exc_info())
    line = json.loads(JsonFormatter().format(rec))
    assert line["error_type"] == "ValueError" and "resident name" not in json.dumps(line)


def test_configure_logging_is_idempotent():
    configure_logging()
    configure_logging()
    handlers = [h for h in logging.getLogger("isd").handlers if getattr(h, "_isd_json", False)]
    assert len(handlers) == 1


# ---------------- rate limiting everywhere ----------------
def test_every_route_is_limited_per_address(client, rate_limits_on):
    """The limiter runs before auth and validation, so any request shows it. Hit each route twice
    with a limit of one: the second must be refused with 429, whatever the route is."""
    routes = [(m, r.path) for r in iter_api_routes(app) for m in r.methods if m != "HEAD"]
    assert len(routes) > 100
    not_limited = []
    for method, path in routes:
        limits.configure("ip", 1, 60)
        concrete = path.replace("{", "").replace("}", "") if "{" in path else path
        for part in ("resident_id", "device_code", "serial", "code", "sanction_id", "appeal_id"):
            concrete = concrete.replace(part, "1")
        client.request(method, concrete)
        if client.request(method, concrete).status_code != 429:
            not_limited.append((method, path))
    assert not_limited == []


def test_public_routes_are_limited_over_http(client, rate_limits_on):
    limits.configure("ip", 5, 60)
    codes = [client.get("/health").status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and set(codes[5:]) == {429}
    assert client.get("/health").headers["retry-after"]


def test_pairing_attempts_are_limited_tighter(client, rate_limits_on):
    limits.configure("pairing", 3, 60)
    codes = [client.post("/device/pair", json={"code": "WRONGCODE"}).status_code for _ in range(5)]
    assert codes == [400, 400, 400, 429, 429]


# ---------------- backup and restore ----------------
def test_the_backup_and_restore_drill_passes_on_the_test_database(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    from tests.conftest import TEST_DB

    report = tmp_path / "drill.md"
    done = subprocess.run(
        [sys.executable, str(root / "scripts/backup-restore-drill.py"), "--source-db", TEST_DB,
         "--scratch-db", "isd_restore_drill_test", "--report", str(report)],
        capture_output=True, text=True, cwd=root,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    assert "DRILL PASSED" in done.stdout and "**PASS**" in report.read_text()


def test_backups_are_private_checksummed_and_pruned(tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import backup

    from tests.conftest import TEST_DB

    files = [backup.dump(tmp_path, TEST_DB, stamp=f"2026010{i}T000000Z")[0] for i in range(1, 5)]
    assert all(f.stat().st_mode & 0o077 == 0 for f in files)  # owner only
    assert all(backup.verify_checksum(f) for f in files)
    files[0].write_bytes(b"corrupted")
    assert not backup.verify_checksum(files[0])
    gone = backup.prune(tmp_path, keep=2)
    assert [g.name for g in gone] == [files[0].name, files[1].name]
    assert sorted(p.name for p in tmp_path.glob("*.dump")) == [files[2].name, files[3].name]
