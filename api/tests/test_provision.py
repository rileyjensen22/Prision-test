"""The kiosk provisioning script, staged into a temporary root (nothing touches this machine)."""

import json
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

KIOSK = Path(__file__).resolve().parents[2] / "deploy" / "kiosk"
SCRIPT = KIOSK / "provision-kiosk.sh"
ARGS = [
    "--host", "isd.example.org",
    "--server-ip", "203.0.113.10",
    "--resolver-ip", "203.0.113.53",
    "--ntp-ip", "203.0.113.123",
    "--no-install",
]  # fmt: skip


def run(root, *extra, args=ARGS):
    return subprocess.run(
        [str(SCRIPT), "--root", str(root), *args, *extra], capture_output=True, text=True
    )


@pytest.fixture
def staged(tmp_path):
    r = run(tmp_path, "--pair-code", "ABCD2345", "--ssh-from", "203.0.113.0/28")
    assert r.returncode == 0, r.stderr
    return tmp_path


def test_every_script_is_valid_bash():
    for path in [SCRIPT, *(KIOSK / "files").glob("*.sh")]:
        assert subprocess.run(["bash", "-n", str(path)]).returncode == 0, path


def test_expected_files_are_written_with_safe_modes(staged):
    expected = {
        "etc/isd-kiosk/kiosk.env": 0o644,
        "etc/nftables.conf": 0o600,
        "etc/chromium/policies/managed/isd.json": 0o644,
        "etc/systemd/system/isd-kiosk.service": 0o644,
        "etc/systemd/system/isd-kiosk-watchdog.timer": 0o644,
        "etc/systemd/system/isd-kiosk-nightly.timer": 0o644,
        "etc/systemd/logind.conf.d/isd-kiosk.conf": 0o644,
        "etc/X11/xorg.conf.d/10-isd-kiosk.conf": 0o644,
        "usr/local/lib/isd-kiosk/session.sh": 0o755,
        "usr/local/lib/isd-kiosk/watchdog.sh": 0o755,
        "var/lib/isd-kiosk/first-boot-url": 0o600,
    }
    for rel, mode in expected.items():
        path = staged / rel
        assert path.exists(), rel
        assert stat.S_IMODE(path.stat().st_mode) == mode, rel
    assert not list(staged.rglob("*.tmp"))


def test_no_template_markers_are_left_in_any_file(staged):
    for path in staged.rglob("*"):
        if path.is_file():
            assert not re.search(r"@[A-Z0-9_]+@", path.read_text()), path


def test_browser_policy_is_json_that_allows_only_our_host(staged):
    policy = json.loads((staged / "etc/chromium/policies/managed/isd.json").read_text())
    assert policy["URLBlocklist"] == ["*"]
    assert all(u.startswith("https://isd.example.org/") for u in policy["URLAllowlist"])
    assert not any(
        "/staff" in u for u in policy["URLAllowlist"]
    )  # the kiosk cannot open staff pages
    assert policy["IncognitoModeAvailability"] == 1  # incognito would erase the saved device token
    assert policy["DeveloperToolsAvailability"] == 2
    assert policy["VideoCaptureAllowedUrls"] == ["https://isd.example.org"]


def test_firewall_allows_only_the_named_addresses(staged):
    rules = (staged / "etc/nftables.conf").read_text()
    assert rules.count("policy drop") == 3
    for ip in ("203.0.113.10", "203.0.113.53", "203.0.113.123"):
        assert ip in rules
    assert "ip saddr 203.0.113.0/28 tcp dport 22 accept" in rules
    assert "dport 80" not in rules
    if shutil.which("nft"):
        check = subprocess.run(
            ["nft", "-c", "-f", str(staged / "etc/nftables.conf")], capture_output=True, text=True
        )
        if "Operation not permitted" in check.stderr:
            pytest.skip("nft needs root to check a ruleset here (the kiosk check runs it as root)")
        assert check.returncode == 0, check.stderr


def test_no_ssh_rule_unless_asked(tmp_path):
    assert run(tmp_path).returncode == 0
    assert "dport 22" not in (tmp_path / "etc/nftables.conf").read_text()


def test_systemd_units_have_no_unknown_keys(staged):
    if not shutil.which("systemd-analyze"):
        pytest.skip("systemd-analyze not installed")
    units = sorted(str(p.relative_to(staged)) for p in (staged / "etc/systemd/system").glob("*"))
    out = subprocess.run(
        ["systemd-analyze", "verify", f"--root={staged}", *[f"/{u}" for u in units]],
        capture_output=True,
        text=True,
    )
    problems = [
        line
        for line in (out.stdout + out.stderr).splitlines()
        # the staged tree has no Chromium or X installed, which is expected here
        if line.strip()
        and not any(x in line for x in ("not found", "not executable", "Failed to create"))
    ]
    assert problems == []


def test_kiosk_service_always_comes_back_and_tty_switching_is_off(staged):
    unit = (staged / "etc/systemd/system/isd-kiosk.service").read_text()
    assert "Restart=always" in unit and "StartLimitIntervalSec=0" in unit
    assert "User=isd-kiosk" in unit and "NoNewPrivileges=true" in unit
    xorg = (staged / "etc/X11/xorg.conf.d/10-isd-kiosk.conf").read_text()
    assert '"DontVTSwitch" "true"' in xorg and '"DontZap" "true"' in xorg
    logind = (staged / "etc/systemd/logind.conf.d/isd-kiosk.conf").read_text()
    assert "NAutoVTs=0" in logind and "ReserveVT=0" in logind
    assert "usb-storage" in (staged / "etc/modprobe.d/isd-kiosk.conf").read_text()
    assert "sysrq = 0" in (staged / "etc/sysctl.d/90-isd-kiosk.conf").read_text()


def test_session_script_never_uses_incognito_and_removes_the_one_time_link(staged):
    session = (staged / "usr/local/lib/isd-kiosk/session.sh").read_text()
    assert "--kiosk" in session and "incognito" not in session
    assert 'rm -f "$FIRST"' in session
    assert session.index('rm -f "$FIRST"') < session.index("exec /usr/bin/chromium")
    assert (staged / "var/lib/isd-kiosk/first-boot-url").read_text().strip() == (
        "https://isd.example.org/resident#pair=ABCD2345"
    )


def test_running_it_twice_changes_nothing(tmp_path):
    run(tmp_path, "--pair-code", "ABCD2345")
    first = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    run(tmp_path, "--pair-code", "ABCD2345")
    second = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert first == second


@pytest.mark.parametrize(
    "bad",
    [
        ["--host", "evil.com;rm -rf /"],
        ["--host", "a b"],
        ["--host", "https://isd.example.org"],
        ["--server-ip", "999.1.1.1"],
        ["--server-ip", "1.2.3.4; drop"],
        ["--resolver-ip", ""],
        ["--ntp-ip", "ntp.example.org"],
        ["--pair-code", "x y"],
        ["--ssh-from", "0.0.0.0/0; accept"],
        ["--data-dir", "relative/path"],
    ],
)
def test_bad_input_is_refused_before_anything_is_written(tmp_path, bad):
    args = list(ARGS)
    for i in range(0, len(bad), 2):
        key = bad[i]
        if key in args:
            args[args.index(key) + 1] = bad[i + 1]
        else:
            args += bad[i : i + 2]
    r = run(tmp_path, args=args)
    assert r.returncode == 2 and "error:" in r.stderr
    assert not any(tmp_path.iterdir())


def test_read_only_root_needs_a_separate_data_disk(tmp_path):
    refused = run(tmp_path, "--readonly-root")
    assert refused.returncode == 2 and "separate writable" in refused.stderr
    ok = run(tmp_path, "--readonly-root", "--data-dir", "/mnt/isd-data")
    assert ok.returncode == 0
    assert "overlayroot" in (tmp_path / "etc/overlayroot.local.conf").read_text()
    assert (tmp_path / "mnt/isd-data/profile").is_dir()


def test_dry_run_writes_nothing(tmp_path):
    r = run(tmp_path, "--dry-run")
    assert r.returncode == 0 and not any(tmp_path.iterdir())


def test_no_secrets_are_committed_in_the_deploy_files():
    text = "\n".join(p.read_text() for p in KIOSK.rglob("*") if p.is_file())
    assert "PRIVATE KEY" not in text
    assert not re.search(r"(password|secret|token)\s*[=:]\s*[\"']?[A-Za-z0-9]{6,}", text, re.I)
