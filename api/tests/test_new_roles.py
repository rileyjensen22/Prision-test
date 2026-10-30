"""Tests for the three new staff roles and their queue endpoints."""

import pytest


# ---------------------------------------------------------------------------
# Role-permission matrix for new queue routes
# ---------------------------------------------------------------------------

_HEALTH_ROUTES = ["/staff/health-requests"]
_GRIEF_ROUTES = ["/staff/grievances"]
_ATTORNEY_ROUTES = ["/staff/attorney-calls"]
_COMMISSARY_ROUTES = ["/staff/commissary/orders", "/staff/commissary/deposits"]
_VIDEO_ROUTES = ["/staff/video/sessions"]


@pytest.mark.parametrize("path", _HEALTH_ROUTES)
@pytest.mark.parametrize(
    "role,expected",
    [
        ("officer", 403),
        ("health_staff", 200),
        ("supervisor", 200),
        ("admin", 200),
        ("auditor", 200),
        ("legal_liaison", 403),
        ("commissary_clerk", 403),
    ],
)
def test_health_requests_rbac(client, staff_tokens, path, role, expected):
    r = client.get(path, headers=staff_tokens[role])
    assert r.status_code == expected, f"{role} on {path}"


@pytest.mark.parametrize("path", _GRIEF_ROUTES)
@pytest.mark.parametrize(
    "role,expected",
    [
        ("officer", 403),
        ("health_staff", 403),
        ("supervisor", 200),
        ("admin", 200),
        ("auditor", 200),
        ("legal_liaison", 403),
        ("commissary_clerk", 403),
    ],
)
def test_grievances_rbac(client, staff_tokens, path, role, expected):
    r = client.get(path, headers=staff_tokens[role])
    assert r.status_code == expected, f"{role} on {path}"


@pytest.mark.parametrize("path", _ATTORNEY_ROUTES)
@pytest.mark.parametrize(
    "role,expected",
    [
        ("officer", 403),
        ("health_staff", 403),
        ("supervisor", 200),
        ("admin", 200),
        ("auditor", 200),
        ("legal_liaison", 200),
        ("commissary_clerk", 403),
    ],
)
def test_attorney_calls_rbac(client, staff_tokens, path, role, expected):
    r = client.get(path, headers=staff_tokens[role])
    assert r.status_code == expected, f"{role} on {path}"


@pytest.mark.parametrize("path", _COMMISSARY_ROUTES)
@pytest.mark.parametrize(
    "role,expected",
    [
        ("officer", 403),
        ("health_staff", 403),
        ("supervisor", 200),
        ("admin", 200),
        ("auditor", 200),
        ("legal_liaison", 403),
        ("commissary_clerk", 200),
    ],
)
def test_commissary_rbac(client, staff_tokens, path, role, expected):
    r = client.get(path, headers=staff_tokens[role])
    assert r.status_code == expected, f"{role} on {path}"


@pytest.mark.parametrize("path", _VIDEO_ROUTES)
@pytest.mark.parametrize(
    "role,expected",
    [
        ("officer", 403),
        ("health_staff", 403),
        ("supervisor", 200),
        ("admin", 200),
        ("auditor", 200),
        ("legal_liaison", 403),
        ("commissary_clerk", 403),
    ],
)
def test_video_rbac(client, staff_tokens, path, role, expected):
    r = client.get(path, headers=staff_tokens[role])
    assert r.status_code == expected, f"{role} on {path}"


# ---------------------------------------------------------------------------
# Library: uploader cannot approve their own item (invariant: two-person approval)
# ---------------------------------------------------------------------------

def test_library_self_approve_forbidden(client, staff_tokens):
    """Staff member who uploaded a library item cannot approve their own item."""
    headers = staff_tokens["admin"]

    # Upload an item
    upload = client.post(
        "/staff/library",
        json={
            "title": "Test Item",
            "description": "desc",
            "url": "https://example.com/test",
            "category": "general",
            "language": "en",
            "reading_level": 1,
        },
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    item_id = upload.json()["id"]

    # Same staff member tries to approve — must be rejected
    approve = client.post(f"/staff/library/{item_id}/approve", headers=headers)
    assert approve.status_code == 403, "Uploader should not be able to approve their own item"

    # A different staff member can approve
    other_headers = staff_tokens["supervisor"]
    approve2 = client.post(f"/staff/library/{item_id}/approve", headers=other_headers)
    assert approve2.status_code == 200, approve2.text


# ---------------------------------------------------------------------------
# Commissary refund posts to ledger (append-only, entry_type='refund')
# ---------------------------------------------------------------------------

def test_commissary_refund_creates_ledger_entry(client, staff_tokens, owner_engine):
    """Refunding an order adds a refund entry to the trust ledger."""
    from sqlalchemy.orm import Session
    from isd.models import CommissaryOrder, Resident, TrustLedger

    admin_h = staff_tokens["admin"]

    # Create a resident and an order directly in DB
    with Session(owner_engine) as s, s.begin():
        r = Resident(
            code="RES-REFUND-TEST",
            display_name="Refund Test",
            prior_returns=0,
        )
        s.add(r)
        s.flush()
        order = CommissaryOrder(
            resident_id=r.id,
            total_cents=500,
            status="new",
        )
        s.add(order)
        s.flush()
        resident_id = r.id
        order_id = order.id

    resp = client.patch(
        f"/staff/commissary/orders/{order_id}",
        json={"status": "refunded", "refund_reason": "Item out of stock"},
        headers=admin_h,
    )
    assert resp.status_code == 200, resp.text

    # Ledger must now have a refund entry
    with Session(owner_engine) as s:
        entry = (
            s.query(TrustLedger)
            .filter_by(resident_id=resident_id, entry_type="refund")
            .first()
        )
        assert entry is not None, "Expected a refund ledger entry"
        assert entry.amount_cents == 500


# ---------------------------------------------------------------------------
# Deposit import: CSV preview and apply
# ---------------------------------------------------------------------------

def _csv(rows: list[tuple[str, str]]) -> bytes:
    lines = ["resident_code,amount_cents"]
    for code, amt in rows:
        lines.append(f"{code},{amt}")
    return "\n".join(lines).encode()


def test_deposit_preview_valid(client, staff_tokens, owner_engine):
    """Preview endpoint returns parsed rows without writing."""
    from sqlalchemy.orm import Session
    from isd.models import Resident, TrustLedger

    with Session(owner_engine) as s, s.begin():
        r = Resident(code="RES-DEP-TEST", display_name="Dep Test", prior_returns=0)
        s.add(r)

    headers = staff_tokens["admin"]
    csv_data = _csv([("RES-DEP-TEST", "1000")])
    resp = client.post(
        "/staff/commissary/deposits/preview",
        content=csv_data,
        headers={**headers, "Content-Type": "text/csv"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["row_count"] >= 1

    # Preview must NOT have created any ledger entries
    with Session(owner_engine) as s:
        count = s.query(TrustLedger).filter_by(entry_type="deposit").count()
        assert count == 0


def test_deposit_over_limit_rejected(client, staff_tokens, owner_engine):
    """Single deposit row exceeding $500 is rejected."""
    from sqlalchemy.orm import Session
    from isd.models import Resident

    with Session(owner_engine) as s, s.begin():
        r = Resident(code="RES-OVERLIMIT", display_name="Over Limit", prior_returns=0)
        s.add(r)

    headers = staff_tokens["admin"]
    csv_data = _csv([("RES-OVERLIMIT", "50001")])  # $500.01
    resp = client.post(
        "/staff/commissary/deposits/preview",
        content=csv_data,
        headers={**headers, "Content-Type": "text/csv"},
    )
    # Expect validation error (400 or 422)
    assert resp.status_code in (400, 422), resp.text


# ---------------------------------------------------------------------------
# Points floor: total_points never goes below zero
# ---------------------------------------------------------------------------

def test_points_floor_at_zero(owner, seeded, make_resident):
    """Subtracting more points than a resident has never yields a negative total."""
    from datetime import UTC, datetime

    from isd.services.points import record_points, total_points
    from isd.services.audit import SYSTEM

    now = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
    rid = make_resident()

    record_points(owner, SYSTEM, rid, "confirmed_major_infraction", -100, "test", now)
    result = total_points(owner, rid, now)
    assert result == 0, f"Expected 0, got {result}"
