"""Phase 12: voluntary work, earnings, payouts and the nightly reconciliation."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from isd import providers
from isd.engine.authority import Evidence
from isd.models import (
    AuditLog,
    EarningsLedger,
    JobListing,
    JobTask,
    PointEvent,
    ReconciliationRun,
    Sanction,
    TaskSubmission,
    TrustLedger,
    WorkLog,
)
from isd.services import daily, earnings, jobs, ledger, reconcile, sanctions, work_tasks
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from isd.services.entitlement_service import get_entitlements
from tests.conftest import NOW
from tests.test_phase7_services import give

pytestmark = pytest.mark.usefixtures("reference_data")


def listing(owner, code="CAPTION"):
    return owner.execute(select(JobListing).where(JobListing.code == code)).scalar()


def correct_answer(owner, task_view):
    spec = owner.get(JobTask, task_view["task_id"]).spec
    kind = task_view["kind"]
    if kind == "transcription_public_domain":
        return spec["expected"]
    if kind == "captioning":
        return f"A scene with a {spec['keywords'][0]} in it"
    return spec["expected"]


def work_once(owner, rid, code, at, wrong=False):
    j = listing(owner, code)
    view = work_tasks.next_task(owner, rid, j.id, at)
    answer = "zzz qqq" if wrong else correct_answer(owner, view)
    return work_tasks.submit(owner, rid, view["task_id"], answer, at)


@pytest.fixture
def worker(owner, seeded, make_resident):
    rid = make_resident()
    jobs.opt_in(owner, rid, listing(owner, "CAPTION").id, NOW)
    return rid


def set_jobs(owner, **changes):
    payload = dict(get_current(owner, "jobs").payload)
    payload.update(changes)
    set_config(owner, SYSTEM, "jobs", payload, "test: work settings")


def counts(owner, rid):
    """Points, sanctions and audit entries: working must change none of them."""
    return (
        owner.execute(
            select(func.count(PointEvent.id)).where(PointEvent.resident_id == rid)
        ).scalar(),
        owner.execute(select(func.count(Sanction.id)).where(Sanction.resident_id == rid)).scalar(),
        owner.execute(select(func.count(AuditLog.seq))).scalar(),
    )


# ---------------- doing work and being paid ----------------
def test_an_accepted_task_pays_and_splits_the_money_a_refused_one_pays_nothing(owner, worker):
    done = work_once(owner, worker, "CAPTION", NOW)
    assert done == {"accepted": True, "reason": "ACCEPTED", "earned_cents": 12}  # 60% of 20c
    row = owner.execute(select(EarningsLedger).where(EarningsLedger.resident_id == worker)).scalar()
    assert (row.gross_cents, row.resident_cents, row.facility_cents, row.deductions_cents) == (
        20,
        12,
        6,
        2,
    )
    assert row.split == {"resident_pct": 60, "facility_pct": 30, "deductions_pct": 10}
    refused = work_once(owner, worker, "CAPTION", NOW + timedelta(minutes=1), wrong=True)
    assert refused["accepted"] is False and refused["earned_cents"] == 0
    sub = owner.execute(select(TaskSubmission).where(TaskSubmission.accepted.is_(False))).scalar()
    assert sub.answer is None and sub.pay_cents == 0  # nothing is kept from a refusal
    assert earnings.summary(owner, worker) == {
        "earned_cents": 12,
        "paid_cents": 0,
        "pending_cents": 12,
    }


def test_a_task_is_claimed_once_then_returned_the_same_until_handed_in(
    owner, seeded, make_resident
):
    a, b = make_resident(), make_resident()
    j = listing(owner)
    for rid in (a, b):
        jobs.opt_in(owner, rid, j.id, NOW)
    first = work_tasks.next_task(owner, a, j.id, NOW)
    assert work_tasks.next_task(owner, a, j.id, NOW)["task_id"] == first["task_id"]
    other = work_tasks.next_task(owner, b, j.id, NOW)
    assert other["task_id"] != first["task_id"]
    work_tasks.submit(owner, a, first["task_id"], "x y z coin", NOW)
    with pytest.raises(jobs.JobError) as e:
        work_tasks.submit(owner, a, first["task_id"], "x y z coin", NOW)
    assert e.value.code == "ALREADY_DONE"
    with pytest.raises(jobs.JobError) as e:  # someone else's task
        work_tasks.submit(owner, b, first["task_id"], "x y z coin", NOW)
    assert e.value.code == "NOT_FOUND"


def test_a_timed_out_claim_goes_back_to_the_pool(owner, seeded, make_resident):
    a, b = make_resident(), make_resident()
    j = listing(owner)
    for rid in (a, b):
        jobs.opt_in(owner, rid, j.id, NOW)
    first = work_tasks.next_task(owner, a, j.id, NOW)
    later = NOW + timedelta(minutes=31)
    with pytest.raises(jobs.JobError) as e:
        work_tasks.submit(owner, a, first["task_id"], "a coin here", later)
    assert e.value.code == "EXPIRED"
    assert work_tasks.next_task(owner, b, j.id, later)["task_id"] == first["task_id"]


def test_you_must_have_joined_and_there_is_a_daily_limit(owner, seeded, make_resident):
    rid = make_resident()
    j = listing(owner, "SENTENCES")
    with pytest.raises(jobs.JobError) as e:
        work_tasks.next_task(owner, rid, j.id, NOW)
    assert e.value.code == "NOT_JOINED"
    jobs.opt_in(owner, rid, j.id, NOW)
    set_jobs(owner, max_tasks_per_day=2)
    work_once(owner, rid, "SENTENCES", NOW)
    work_once(owner, rid, "SENTENCES", NOW + timedelta(seconds=5))
    with pytest.raises(jobs.JobError) as e:
        work_tasks.next_task(owner, rid, j.id, NOW + timedelta(seconds=10))
    assert e.value.code == "DAILY_CAP"
    work_tasks.next_task(owner, rid, j.id, NOW + timedelta(days=1))  # a new day


def test_the_device_never_sees_the_answer_or_keywords(owner, worker):
    for code in ("TRANSCRIBE", "CAPTION", "SENTENCES"):
        rid = worker
        jobs.opt_in(owner, rid, listing(owner, code).id, NOW) if code != "CAPTION" else None
        view = work_tasks.next_task(owner, rid, listing(owner, code).id, NOW)
        assert "expected" not in str(view) and "keywords" not in str(view)


def test_personal_data_in_an_answer_is_refused_and_not_kept(owner, worker):
    j = listing(owner)
    view = work_tasks.next_task(owner, worker, j.id, NOW)
    out = work_tasks.submit(owner, worker, view["task_id"], "coin pile call 404-555-0134", NOW)
    assert out["reason"] == "PERSONAL_DATA" and not out["accepted"]
    assert owner.execute(select(TaskSubmission.answer)).scalars().all() == [None]


def test_a_partner_that_sends_personal_data_is_refused_and_nothing_is_stored(
    owner, seeded, make_resident
):
    class BadPartner:
        code = "MOCK_PARTNER"
        name = "Bad"

        def fetch_tasks(self, kind, count, offset):
            return [
                {
                    "external_id": "bad-1",
                    "scene": "Call Pat Smith at 404-555-0134",
                    "keywords": ["call"],
                    "source": "oops",
                }
            ]

        def review(self, *a):
            raise AssertionError("unreachable")

    good = providers.get_job_partner("MOCK_PARTNER")
    providers.set_job_partner(BadPartner())
    try:
        rid = make_resident()
        j = listing(owner)
        jobs.opt_in(owner, rid, j.id, NOW)
        with pytest.raises(ValueError, match="personal"):
            work_tasks.next_task(owner, rid, j.id, NOW)
    finally:
        providers.set_job_partner(good)
    assert owner.execute(select(JobTask).where(JobTask.external_id == "bad-1")).first() is None


# ---------------- payouts into the trust account ----------------
def test_earnings_are_paid_into_the_trust_account_once_and_can_be_spent(owner, worker):
    for i in range(3):
        work_once(owner, worker, "CAPTION", NOW + timedelta(minutes=i))
    assert earnings.pending_cents(owner, worker) == 36
    assert ledger.balance_cents(owner, worker) == 0
    paid = earnings.pay_out(owner, worker, NOW + timedelta(hours=1))
    assert paid.resident_cents == -36
    assert ledger.balance_cents(owner, worker) == 36
    assert earnings.pay_out(owner, worker, NOW + timedelta(hours=2)) is None  # nothing new
    row = owner.execute(select(TrustLedger).where(TrustLedger.resident_id == worker)).scalar()
    assert (row.entry_type, row.amount_cents, row.balance_after_cents) == ("job_payout", 36, 36)
    assert earnings.summary(owner, worker) == {
        "earned_cents": 36,
        "paid_cents": 36,
        "pending_cents": 0,
    }
    work_once(owner, worker, "CAPTION", NOW + timedelta(hours=3))
    again = earnings.pay_out(owner, worker, NOW + timedelta(hours=4))
    assert again.resident_cents == -12 and ledger.balance_cents(owner, worker) == 48


def test_pay_out_all_and_the_daily_job_pay_everyone_and_then_reconcile(
    owner, seeded, make_resident
):
    rids = [make_resident() for _ in range(3)]
    for rid in rids:
        jobs.opt_in(owner, rid, listing(owner).id, NOW)
        work_once(owner, rid, "CAPTION", NOW)
    result = daily.run_daily(owner, NOW + timedelta(days=1, hours=1))
    assert result["work_payouts"] == 3
    assert result["reconciliation"] == {"ok": True, "problems": 0}
    assert all(ledger.balance_cents(owner, rid) == 12 for rid in rids)
    again = daily.run_daily(owner, NOW + timedelta(days=1, hours=2))
    assert again["work_payouts"] == 0  # repeat-safe


def test_a_change_to_the_split_applies_to_new_work_only(owner, worker):
    work_once(owner, worker, "CAPTION", NOW)
    set_jobs(owner, pay_split={"resident_pct": 50, "facility_pct": 40, "deductions_pct": 10})
    work_once(owner, worker, "CAPTION", NOW + timedelta(minutes=1))
    rows = owner.execute(
        select(EarningsLedger.resident_cents, EarningsLedger.facility_cents)
        .where(EarningsLedger.resident_id == worker)
        .order_by(EarningsLedger.id)
    ).all()
    assert [tuple(r) for r in rows] == [(12, 6), (10, 8)]
    assert reconcile.reconcile(owner, NOW)["ok"]


# ---------------- append-only money (invariant 15) ----------------
@pytest.mark.parametrize("table", ["earnings_ledger", "work_log", "task_submissions"])
def test_money_and_work_records_cannot_be_changed_or_deleted(owner, worker, table):
    work_once(owner, worker, "CAPTION", NOW)
    earnings.pay_out(owner, worker, NOW + timedelta(hours=1))
    for sql in (f"UPDATE {table} SET id = id", f"DELETE FROM {table}"):
        with pytest.raises(DBAPIError):
            with owner.begin_nested():
                owner.execute(text(sql))


def test_reconciliation_runs_are_append_only_too(owner, worker):
    reconcile.reconcile(owner, NOW)
    with pytest.raises(DBAPIError):
        with owner.begin_nested():
            owner.execute(text("DELETE FROM reconciliation_runs"))


def test_the_database_refuses_an_earning_that_does_not_add_up(owner, worker):
    work_once(owner, worker, "CAPTION", NOW)
    sub = owner.execute(select(TaskSubmission)).scalars().first()
    with pytest.raises(DBAPIError):
        with owner.begin_nested():
            owner.add(
                EarningsLedger(
                    resident_id=worker,
                    entry_type="earned",
                    submission_id=sub.id + 999,
                    gross_cents=10,
                    resident_cents=9,
                    facility_cents=0,
                    deductions_cents=0,
                    created_at=NOW,
                )
            )
            owner.flush()


# ---------------- nightly reconciliation ----------------
def test_a_clean_ledger_reconciles_and_raises_no_alert(owner, worker):
    for i in range(4):
        work_once(owner, worker, "CAPTION", NOW + timedelta(minutes=i))
    earnings.pay_out(owner, worker, NOW + timedelta(hours=1))
    alerts = owner.execute(
        select(func.count(AuditLog.seq)).where(AuditLog.action == "reconciliation_mismatch")
    ).scalar()
    out = reconcile.reconcile(owner, NOW + timedelta(days=1))
    assert out["ok"] and out["problems"] == []
    assert (
        owner.execute(select(ReconciliationRun).order_by(ReconciliationRun.id.desc())).scalar().ok
    )
    after = owner.execute(
        select(func.count(AuditLog.seq)).where(AuditLog.action == "reconciliation_mismatch")
    ).scalar()
    assert after == alerts


def test_a_balance_that_does_not_match_its_ledger_is_caught_and_alerted(owner, worker):
    work_once(owner, worker, "CAPTION", NOW)
    earnings.pay_out(owner, worker, NOW + timedelta(hours=1))
    # someone writes a trust entry whose balance does not follow from the entries before it
    owner.add(
        TrustLedger(
            resident_id=worker,
            entry_type="adjustment",
            amount_cents=100,
            balance_after_cents=999,
            created_at=NOW + timedelta(hours=2),
        )
    )
    owner.flush()
    out = reconcile.reconcile(owner, NOW + timedelta(days=1))
    assert not out["ok"]
    assert {p["check"] for p in out["problems"]} == {
        "trust balance is the running total of its entries"
    }
    assert out["problems"][0]["resident_id"] == worker
    alert = (
        owner.execute(select(AuditLog).where(AuditLog.action == "reconciliation_mismatch"))
        .scalars()
        .all()
    )
    assert alert and alert[-1].payload["problems"] == 1
    assert reconcile.latest_runs(owner)[0]["ok"] is False


def test_a_work_deposit_with_no_matching_payout_is_caught(owner, worker):
    owner.add(
        TrustLedger(
            resident_id=worker,
            entry_type="job_payout",
            amount_cents=50,
            balance_after_cents=50,
            created_at=NOW,
        )
    )
    owner.flush()
    out = reconcile.reconcile(owner, NOW)
    assert any("work deposit" in p["check"] for p in out["problems"])


def test_a_submission_paid_the_wrong_amount_is_caught(owner, worker):
    work_once(owner, worker, "CAPTION", NOW)
    # an accepted submission whose earning was never recorded
    j = listing(owner)
    task = JobTask(
        listing_id=j.id,
        external_id="orphan-1",
        kind="captioning",
        spec={},
        status="accepted",
        created_at=NOW,
    )
    owner.add(task)
    owner.flush()
    owner.add(
        TaskSubmission(
            task_id=task.id,
            resident_id=worker,
            listing_id=j.id,
            accepted=True,
            review_reason="ACCEPTED",
            pay_cents=20,
            submitted_at=NOW,
        )
    )
    owner.flush()
    out = reconcile.reconcile(owner, NOW)
    assert any("accepted task" in p["check"] for p in out["problems"])


# ---------------- independence from tier and sanctions (invariant 7) ----------------
def test_working_earning_and_leaving_change_nothing_about_points_sanctions_or_entitlements(
    owner, seeded, make_resident
):
    rid = make_resident()
    give(owner, rid, 450)
    before_counts = counts(owner, rid)
    before = get_entitlements(owner, rid, NOW)
    j = listing(owner)
    jobs.opt_in(owner, rid, j.id, NOW)
    for i in range(3):
        work_once(owner, rid, "CAPTION", NOW + timedelta(minutes=i), wrong=i == 1)
    earnings.pay_out(owner, rid, NOW + timedelta(hours=1))
    jobs.leave(owner, rid, j.id, NOW + timedelta(hours=2))
    after = get_entitlements(owner, rid, NOW + timedelta(hours=3))
    assert counts(owner, rid) == before_counts
    assert after.features == before.features and after.effective_tier == before.effective_tier
    assert owner.execute(select(PointEvent).where(PointEvent.kind.ilike("%job%"))).first() is None


def test_declining_or_quitting_is_logged_for_the_resident_only_and_creates_no_event(
    owner, seeded, make_resident
):
    rid = make_resident()
    before = counts(owner, rid)
    j = listing(owner)
    jobs.opt_in(owner, rid, j.id, NOW)
    jobs.leave(owner, rid, j.id, NOW + timedelta(minutes=5))
    jobs.opt_in(owner, rid, j.id, NOW + timedelta(minutes=6))
    jobs.leave(owner, rid, j.id, NOW + timedelta(minutes=7))
    assert counts(owner, rid) == before
    events = [w["event"] for w in work_tasks.work_log(owner, rid)]
    assert events == ["left", "joined", "left", "joined"]
    assert (
        owner.execute(select(func.count(WorkLog.id)).where(WorkLog.resident_id == rid)).scalar()
        == 4
    )


def lock_everything(owner, rid, make_staff):
    officer, sup, colleague = make_staff("officer"), make_staff("supervisor"), make_staff("officer")
    s = sanctions.issue_sanction(
        owner,
        officer,
        rid,
        "CAM_BLOCK",
        NOW,
        Evidence("second_staff_report", reporter_id=colleague.id),
    )
    sanctions.confirm_sanction(owner, sup, s.id, NOW + timedelta(minutes=1))
    return s, NOW + timedelta(hours=1)


def test_by_default_a_sanction_never_pauses_work(owner, worker, make_staff):
    _, later = lock_everything(owner, worker, make_staff)
    assert not get_entitlements(owner, worker, later).allowed("commissary")
    assert work_once(owner, worker, "CAPTION", later)["accepted"]  # still free to work


def test_when_the_operator_turns_it_on_a_sanction_pauses_new_work_with_a_reason_but_not_pay(
    owner, worker, make_staff
):
    work_once(owner, worker, "CAPTION", NOW)
    s, later = lock_everything(owner, worker, make_staff)
    set_jobs(owner, suspend_on_sanction=True)
    j = listing(owner)
    with pytest.raises(jobs.JobError) as e:
        work_tasks.next_task(owner, worker, j.id, later)
    assert e.value.code == "JOB_SUSPENDED"
    from isd.services import job_policy

    lock = job_policy.suspension(owner, worker, later)
    assert lock["code"] == "CAM_BLOCK" and lock["how_to_appeal"] == "appeal" and lock["ends_at"]
    assert earnings.pay_out(owner, worker, later) is not None  # earned pay is never withheld
    still = jobs.list_listings(owner, worker)
    assert any(x["enrolled"] for x in still)  # still enrolled; only new tasks pause
    after = later + timedelta(days=3)  # the 48h sanction has ended
    assert work_once(owner, worker, "CAPTION", after)["accepted"]
    assert s.id  # (the sanction itself was never touched)


def test_a_comms_only_sanction_does_not_pause_work_even_when_the_flag_is_on(
    owner, worker, make_staff
):
    officer = make_staff("officer")
    sanctions.issue_sanction(owner, officer, worker, "DISRUPT", NOW)  # communication scope
    set_jobs(owner, suspend_on_sanction=True)
    assert work_once(owner, worker, "CAPTION", NOW + timedelta(minutes=1))["accepted"]


def test_the_work_code_is_kept_apart_from_what_decides_entitlements():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "isd" / "services"
    for name in ("jobs.py", "work_tasks.py", "earnings.py", "reconcile.py", "ledger.py"):
        src = (root / name).read_text()
        for forbidden in ("points", "sanctions", "entitlement", "tier"):
            assert not re.search(rf"^\s*(from|import)\s+.*\b{forbidden}", src, re.M), (
                f"{name} imports {forbidden}"
            )
    # and only the policy module may read sanctions at all
    for path in root.glob("*.py"):
        if path.name in ("job_policy.py", "sanctions.py", "entitlement_service.py"):
            continue
        if path.name.startswith(("jobs", "work_", "earnings", "ledger", "reconcile")):
            assert "Sanction" not in path.read_text(), f"{path.name} reads sanctions"


def test_staff_only_ever_see_totals_never_who_is_working(owner, worker):
    work_once(owner, worker, "CAPTION", NOW)
    rows = earnings.partner_dashboard(owner)
    caption = next(r for r in rows if r["code"] == "CAPTION")
    assert caption["tasks_accepted"] == 1 and caption["payouts_owed_cents"] == 20
    assert caption["facility_share_cents"] == 6 and caption["deductions_cents"] == 2
    assert not any("resident" in key for row in rows for key in row)


# ---------------- over HTTP ----------------
def dh(token):
    return {"X-Device-Token": token}


@pytest.mark.usefixtures("committed_config", "committed_reference")
def test_work_routes_end_to_end(client, kiosk, owner_engine):
    import uuid

    from sqlalchemy.orm import Session

    from isd.auth import make_token
    from isd.models import Staff

    rid, token, _ = kiosk()
    dev = dh(token)
    assert client.get("/device/jobs/1/task").status_code == 401
    jobs_view = client.get("/device/jobs", headers=dev).json()
    assert jobs_view["earnings"] == {"earned_cents": 0, "paid_cents": 0, "pending_cents": 0}
    assert jobs_view["suspended"] is None
    caption = next(j for j in jobs_view["jobs"] if j["code"] == "CAPTION")
    assert caption["pay_per_task_cents"] == 20

    refused = client.get(f"/device/jobs/{caption['id']}/task", headers=dev)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_JOINED"
    assert client.post(f"/device/jobs/{caption['id']}/join", headers=dev).status_code == 201
    task = client.get(f"/device/jobs/{caption['id']}/task", headers=dev).json()
    assert task["pay_cents"] == 20 and "keywords" not in str(task) and "expected" not in str(task)
    with Session(owner_engine) as s:
        keyword = s.get(JobTask, task["task_id"]).spec["keywords"][0]
    url = f"/device/jobs/tasks/{task['task_id']}/submit"
    assert client.post(url, json={"answer": "x", "extra": 1}, headers=dev).status_code == 422
    assert client.post(url, json={"answer": ""}, headers=dev).status_code == 422
    done = client.post(url, json={"answer": f"someone looks at a {keyword} here"}, headers=dev)
    assert done.json() == {"accepted": True, "reason": "ACCEPTED", "earned_cents": 12}
    assert client.post(url, json={"answer": "again"}, headers=dev).status_code == 409
    after = client.get("/device/jobs", headers=dev).json()["earnings"]
    assert after["pending_cents"] == 12
    log = client.get("/device/jobs/work-log", headers=dev).json()
    assert [e["event"] for e in log] == ["task_accepted", "joined"]

    heads = {}
    with Session(owner_engine) as s, s.begin():
        for role in ("officer", "supervisor", "admin", "auditor"):
            st = Staff(username=f"{role}_{uuid.uuid4().hex[:8]}", role=role, password_hash="x")
            s.add(st)
            s.flush()
            heads[role] = {"Authorization": f"Bearer {make_token(st.id)}"}
    board = client.get("/staff/jobs/partners", headers=heads["officer"]).json()
    assert any(r["code"] == "CAPTION" and r["tasks_accepted"] >= 1 for r in board)
    assert not any("resident" in k for r in board for k in r)
    assert client.get("/staff/finance/reconciliation", headers=heads["officer"]).status_code == 403
    assert client.get("/staff/finance/reconciliation", headers=heads["auditor"]).status_code == 200
    assert client.post("/staff/finance/reconcile", headers=heads["supervisor"]).status_code == 403
    run = client.post("/staff/finance/reconcile", headers=heads["admin"]).json()
    assert run["ok"] is True and run["problems"] == []
