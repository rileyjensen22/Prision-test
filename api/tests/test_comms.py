"""Phase 11: contact requests, texting delivery, keyword flags, and monitored-message review."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from isd.engine.contacts import ContactInvalid
from isd.interfaces.messaging import MessagingService
from isd.interfaces.telephony import PrivilegedCommunicationError
from isd.mocks.messaging import MockMessagingProvider
from isd.models import AuditLog, Contact, Message, MessageFlag, Sanction
from isd.services import contacts, monitoring, texting
from tests.conftest import NOW
from tests.test_phase7_services import give

FLAGGED = "we should demo contraband tonight"
ROLES = ("officer", "supervisor", "admin", "auditor")


def contact_for(owner, rid, kind="family", phone="555-0101", **kw):
    c = Contact(resident_id=rid, name="Synthetic Contact", type=kind, phone_ref=phone, **kw)
    owner.add(c)
    owner.flush()
    return c


@pytest.fixture
def staff(make_staff):
    return {r: make_staff(r) for r in ROLES}


# ---------------- contact requests ----------------
def test_a_requested_contact_is_unusable_until_staff_approve_it(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    give(owner, rid, 450)
    c = contacts.request_contact(owner, rid, " Sam  Rivera ", "friend", "(555) 010-0199", NOW)
    assert (c.status, c.approved, c.requested_by, c.name) == (
        "pending",
        False,
        "resident",
        "Sam Rivera",
    )
    with pytest.raises(texting.TextDenied) as e:
        texting.send_text(owner, rid, c.id, "hello", NOW)
    assert e.value.code == "CONTACT_UNAVAILABLE"
    done = contacts.review_contact(owner, staff["officer"], c.id, True, "", NOW)
    assert (done.status, done.approved, done.verification) == ("approved", True, "stub_verified")
    assert texting.send_text(owner, rid, c.id, "hello", NOW).delivery == "delivered"
    log = owner.execute(select(AuditLog.action).where(AuditLog.target_id == str(c.id))).scalars()
    assert {"contact_requested", "contact_approved"} <= set(log)


def test_refusing_a_request_needs_a_reason_and_a_request_is_reviewed_once(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    c = contacts.request_contact(owner, rid, "Pat Lee", "family", "555-0102", NOW)
    with pytest.raises(contacts.ContactReviewError) as e:
        contacts.review_contact(owner, staff["officer"], c.id, False, "", NOW)
    assert e.value.code == "REASON_REQUIRED"
    contacts.review_contact(owner, staff["officer"], c.id, False, "number not verified", NOW)
    with pytest.raises(contacts.ContactReviewError) as e:
        contacts.review_contact(owner, staff["supervisor"], c.id, True, "", NOW)
    assert e.value.code == "NOT_PENDING"
    assert owner.get(Contact, c.id).status == "rejected"
    assert not owner.get(Contact, c.id).approved


def test_attorney_contacts_need_a_supervisor_and_say_a_bar_check_is_still_needed(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    c = contacts.request_contact(owner, rid, "Dana Cole", "attorney", "555-0103", NOW)
    with pytest.raises(contacts.ContactReviewError) as e:
        contacts.review_contact(owner, staff["officer"], c.id, True, "", NOW)
    assert e.value.code == "NEEDS_SUPERVISOR"
    done = contacts.review_contact(owner, staff["supervisor"], c.id, True, "", NOW)
    assert done.verification == "stub_needs_bar_check"


def test_request_limits_and_bad_input(owner, seeded, make_resident):
    rid = make_resident()
    for n in range(3):
        contacts.request_contact(owner, rid, f"Person {n}", "friend", f"555-01{n}0", NOW)
    with pytest.raises(ContactInvalid) as e:
        contacts.request_contact(owner, rid, "Person 9", "friend", "555-0190", NOW)
    assert e.value.code == "TOO_MANY_PENDING"
    other = make_resident()
    contacts.request_contact(owner, other, "Person A", "friend", "555-0100", NOW)
    with pytest.raises(ContactInvalid) as e:
        contacts.request_contact(owner, other, "Person B", "family", "555-0100", NOW)
    assert e.value.code == "DUPLICATE"
    with pytest.raises(ContactInvalid):
        contacts.request_contact(owner, other, "X", "friend", "555-0111", NOW)


def test_the_database_keeps_approved_and_status_in_step(owner, seeded, make_resident):
    rid = make_resident()
    c = contact_for(owner, rid)
    with pytest.raises(IntegrityError):
        with owner.begin_nested():
            owner.execute(
                text("UPDATE contacts SET status = 'rejected' WHERE id = :i"), {"i": c.id}
            )


def test_a_no_contact_order_blocks_texts_and_never_an_attorney(owner, seeded, make_resident, staff):
    rid = make_resident()
    give(owner, rid, 450)
    fam, att = contact_for(owner, rid), contact_for(owner, rid, "attorney", "555-0104")
    contacts.set_blocked(owner, staff["supervisor"], fam.id, True, "court order", NOW)
    with pytest.raises(texting.TextDenied):
        texting.send_text(owner, rid, fam.id, "hi", NOW)
    with pytest.raises(contacts.ContactReviewError) as e:
        contacts.set_blocked(owner, staff["supervisor"], att.id, True, "court order", NOW)
    assert e.value.code == "PROTECTED"
    assert texting.send_text(owner, rid, att.id, "question", NOW).privileged


# ---------------- texting ----------------
def test_delivery_states_and_failed_messages_do_not_use_the_allowance(owner, seeded, make_resident):
    rid = make_resident()
    give(owner, rid, 450)
    ok = contact_for(owner, rid)
    bad = contact_for(owner, rid, phone="555-FAIL")
    assert texting.send_text(owner, rid, ok.id, "hi", NOW).delivery == "delivered"
    failed = texting.send_text(owner, rid, bad.id, "hi", NOW)
    assert failed.delivery == "failed"
    from isd.services.usage import messages_sent_today

    assert messages_sent_today(owner, rid, NOW) == 1
    replies = owner.execute(select(Message).where(Message.contact_id == bad.id)).scalars().all()
    assert [m.direction for m in replies] == ["out"]  # no reply to an undeliverable message


def test_message_length_limit_comes_from_config(owner, seeded, make_resident):
    rid = make_resident()
    give(owner, rid, 450)
    c = contact_for(owner, rid)
    with pytest.raises(texting.TextDenied) as e:
        texting.send_text(owner, rid, c.id, "x" * 501, NOW)
    assert e.value.code == "BAD_MESSAGE"
    texting.send_text(owner, rid, c.id, "x" * 500, NOW)


# ---------------- keyword flags (invariant 12) ----------------
def test_a_keyword_match_makes_a_review_item_and_never_a_sanction(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    give(owner, rid, 450)
    c = contact_for(owner, rid)
    sanctions_before = owner.execute(select(func.count(Sanction.id))).scalar()
    m = texting.send_text(owner, rid, c.id, FLAGGED, NOW)
    flags = owner.execute(select(MessageFlag).where(MessageFlag.message_id == m.id)).scalars().all()
    assert [(f.rule_id, f.status) for f in flags] == [("PLACEHOLDER_CONTRABAND", "open")]
    assert owner.execute(select(func.count(Sanction.id))).scalar() == sanctions_before
    # a person looks at it and decides; even a referral is not a sanction
    reviewed = monitoring.review_flag(
        owner, staff["supervisor"], flags[0].id, "referred", "pass to security staff", NOW
    )
    assert reviewed.status == "referred"
    assert owner.execute(select(func.count(Sanction.id))).scalar() == sanctions_before
    from isd.services.entitlement_service import get_entitlements

    assert get_entitlements(owner, rid, NOW + timedelta(hours=1)).allowed("texting")


def test_the_monitoring_and_texting_code_cannot_reach_the_sanction_service():
    import inspect

    from isd.services import monitoring as mod

    for module in (mod, texting):
        source = inspect.getsource(module)
        assert "issue_sanction" not in source
        assert "services.sanctions" not in source and "import sanctions" not in source


def test_flag_review_is_for_supervisors_and_admins_and_needs_a_reason(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    give(owner, rid, 450)
    m = texting.send_text(owner, rid, contact_for(owner, rid).id, FLAGGED, NOW)
    flag = owner.execute(select(MessageFlag).where(MessageFlag.message_id == m.id)).scalar()
    for role in ("officer", "auditor"):
        with pytest.raises(monitoring.MonitoringDenied) as e:
            monitoring.review_flag(owner, staff[role], flag.id, "no_action", "looked fine", NOW)
        assert e.value.code == "FORBIDDEN"
    for bad_reason in ("", "ok"):
        with pytest.raises(monitoring.MonitoringDenied) as e:
            monitoring.review_flag(owner, staff["admin"], flag.id, "no_action", bad_reason, NOW)
        assert e.value.code == "REASON_REQUIRED"
    with pytest.raises(monitoring.MonitoringDenied):
        monitoring.review_flag(
            owner, staff["admin"], flag.id, "sanction", "that is not allowed", NOW
        )


# ---------------- reading monitored messages (invariant 16) ----------------
def test_reading_a_monitored_message_needs_a_reason_a_reader_role_and_is_logged_without_the_text(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    give(owner, rid, 450)
    m = texting.send_text(owner, rid, contact_for(owner, rid).id, FLAGGED, NOW)
    with pytest.raises(monitoring.MonitoringDenied) as e:
        monitoring.read_message(owner, staff["officer"], m.id, "checking on a flag", NOW)
    assert e.value.code == "FORBIDDEN"
    with pytest.raises(monitoring.MonitoringDenied) as e:
        monitoring.read_message(owner, staff["supervisor"], m.id, "  ", NOW)
    assert e.value.code == "REASON_REQUIRED"
    before = owner.execute(select(func.count(AuditLog.seq))).scalar()
    for role in ("supervisor", "admin", "auditor"):
        got = monitoring.read_message(owner, staff[role], m.id, "checking on a flag", NOW)
        assert got["body"] == FLAGGED
    entries = (
        owner.execute(
            select(AuditLog).where(AuditLog.action == "monitoring_access", AuditLog.seq > before)
        )
        .scalars()
        .all()
    )
    assert len(entries) == 3
    assert all("contraband" not in str(e.payload) and e.payload["reason"] for e in entries)


def test_the_queue_lists_metadata_only_and_flagged_items_first(owner, seeded, make_resident, staff):
    rid = make_resident()
    give(owner, rid, 450)
    c = contact_for(owner, rid)
    texting.send_text(owner, rid, c.id, "plain message", NOW)
    texting.send_text(owner, rid, c.id, FLAGGED, NOW + timedelta(seconds=1))
    rows = monitoring.queue(owner)
    mine = [r for r in rows if r["resident_id"] == rid]
    assert mine[0]["flags"] and mine[0]["flags"][0]["label"].startswith("Possible contraband")
    assert all("body" not in r and "text" not in r for r in rows)
    assert all(FLAGGED not in str(r) for r in rows)
    assert [r for r in monitoring.queue(owner, flagged_only=True) if r["resident_id"] == rid]


# ---------------- attorney messages (invariant 6) ----------------
def test_attorney_messages_are_unreadable_by_every_role_and_never_queued(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    give(owner, rid, 450)
    att = contact_for(owner, rid, "attorney", "555-0105")
    secret = "demo contraband privileged strategy"
    m = texting.send_text(owner, rid, att.id, secret, NOW)
    assert m.privileged and not m.monitored and m.body is None
    assert owner.execute(select(MessageFlag).where(MessageFlag.message_id == m.id)).first() is None
    assert all(r["message_id"] != m.id for r in monitoring.queue(owner))
    for role in ROLES:
        with pytest.raises(monitoring.MonitoringDenied):
            monitoring.read_message(owner, staff[role], m.id, "trying to read it anyway", NOW)
    # nothing anywhere holds the words
    everything = owner.execute(text("SELECT row_to_json(t)::text FROM messages t")).scalars().all()
    audit = owner.execute(text("SELECT row_to_json(t)::text FROM audit_log t")).scalars().all()
    assert not any("privileged strategy" in row for row in everything + audit)
    # and the database refuses to store a body or a monitored flag on a privileged message
    for sql in (
        "UPDATE messages SET body = 'x' WHERE id = :i",
        "UPDATE messages SET monitored = true WHERE id = :i",
    ):
        with pytest.raises(IntegrityError):
            with owner.begin_nested():
                owner.execute(text(sql), {"i": m.id})


def test_a_provider_that_keeps_attorney_messages_is_caught(owner, seeded, make_resident):
    rid = make_resident()
    give(owner, rid, 450)
    att = contact_for(owner, rid, "attorney", "555-0106")
    leaky = MessagingService(MockMessagingProvider(ignore_no_retain=True))
    with pytest.raises(PrivilegedCommunicationError):
        texting.send_text(owner, rid, att.id, "hello", NOW, messaging=leaky)


# ---------------- over HTTP ----------------
@pytest.mark.usefixtures("committed_config", "committed_reference")
def test_contact_and_monitoring_routes_enforce_roles_and_hide_privileged_text(
    client, kiosk, owner_engine
):
    import uuid as _uuid

    from sqlalchemy.orm import Session

    from isd.auth import make_token
    from isd.models import Staff
    from isd.services import points
    from isd.services.audit import SYSTEM

    rid, token, _ = kiosk()
    with Session(owner_engine) as s, s.begin():
        points.record_points(
            s, SYSTEM, rid, "seed_adjustment", 450, "system", NOW - timedelta(days=1)
        )
        points.evaluate_tier(s, rid, NOW)
    heads = {}
    with Session(owner_engine) as s, s.begin():
        for role in ROLES:
            st = Staff(username=f"{role}_{_uuid.uuid4().hex[:8]}", role=role, password_hash="x")
            s.add(st)
            s.flush()
            heads[role] = {"Authorization": f"Bearer {make_token(st.id)}"}
    dev = {"X-Device-Token": token}

    # the resident asks; the request cannot be used yet
    req = client.post(
        "/device/contacts",
        json={"name": "Sam Rivera", "type": "friend", "phone": "555-0177"},
        headers=dev,
    )
    assert req.status_code == 201 and req.json()["status"] == "pending"
    assert (
        client.post(
            "/device/contacts",
            json={"name": "Sam", "type": "friend", "phone": "555-0177", "x": 1},
            headers=dev,
        ).status_code
        == 422
    )
    assert client.get("/device/contacts", headers=dev).json() == []
    assert client.get("/device/contacts/all", headers=dev).json()[0]["status"] == "pending"
    cid = req.json()["id"]
    assert client.get("/staff/contact-requests", headers=heads["auditor"]).status_code == 403
    queue = client.get("/staff/contact-requests", headers=heads["officer"]).json()
    assert any(q["id"] == cid for q in queue)
    ok = client.post(
        f"/staff/contact-requests/{cid}/review", json={"approve": True}, headers=heads["officer"]
    )
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert (
        client.post(
            f"/staff/contact-requests/{cid}/review",
            json={"approve": True},
            headers=heads["officer"],
        ).status_code
        == 409
    )

    # texts: one ordinary and flagged, one to an attorney
    att = client.post(
        "/device/contacts",
        json={"name": "Dana Cole", "type": "attorney", "phone": "555-0178"},
        headers=dev,
    ).json()["id"]
    assert (
        client.post(
            f"/staff/contact-requests/{att}/review",
            json={"approve": True},
            headers=heads["officer"],
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/staff/contact-requests/{att}/review",
            json={"approve": True},
            headers=heads["supervisor"],
        ).status_code
        == 200
    )
    plain = client.post(
        "/device/messages", json={"contact_id": cid, "body": FLAGGED}, headers=dev
    ).json()["id"]
    private = client.post(
        "/device/messages", json={"contact_id": att, "body": "attorney secret words"}, headers=dev
    ).json()["id"]

    assert client.get("/staff/monitoring/messages", headers=heads["officer"]).status_code == 403
    for role in ("supervisor", "admin", "auditor"):
        rows = client.get("/staff/monitoring/messages?flagged=true", headers=heads[role]).json()
        assert any(r["message_id"] == plain for r in rows)
        assert all(r["message_id"] != private for r in rows)
        assert "attorney secret words" not in str(rows) and FLAGGED not in str(rows)
    path = "/staff/monitoring/messages/{}/read"
    assert (
        client.post(
            path.format(plain), json={"reason": "flag"}, headers=heads["supervisor"]
        ).status_code
        == 409
    )
    got = client.post(
        path.format(plain), json={"reason": "checking a flag"}, headers=heads["supervisor"]
    )
    assert got.status_code == 200 and got.json()["body"] == FLAGGED
    assert (
        client.post(
            path.format(plain), json={"reason": "checking a flag"}, headers=heads["officer"]
        ).status_code
        == 403
    )
    for role in ROLES:
        r = client.post(
            path.format(private), json={"reason": "reading it anyway"}, headers=heads[role]
        )
        assert r.status_code in (403, 404) and "secret" not in r.text
