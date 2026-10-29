import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from seed import build_seed  # noqa: E402


def test_seed_is_synthetic_and_deterministic():
    a, b = build_seed(1), build_seed(1)
    assert [r["id"] for r in a["residents"]] == [r["id"] for r in b["residents"]]
    assert all(r["display_name"].startswith("Synthetic") for r in a["residents"])
    assert {s["role"] for s in a["staff"]} >= {"officer", "supervisor", "admin", "auditor"}
