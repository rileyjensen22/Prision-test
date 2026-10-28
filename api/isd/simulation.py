"""A deterministic week of synthetic activity, run through the real services with an injected
clock, followed by checks of the system's invariants (CLAUDE.md section 13, phase 8).

It is a test of the whole system rather than of any one rule: residents work, call, text and shop;
officers record infractions; supervisors confirm, reject and review; the daily job runs each night.
Rule refusals (a locked feature, a spent allowance, an officer at the weekly cap) are expected and
counted. Anything else that goes wrong fails the run.
"""

import json
import random
import tempfile
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from isd import providers
from isd.analytics import service as outcome_service
from isd.auth import hash_password
from isd.config_loader import load_config
from isd.engine.authority import AuthorityError, Evidence
from isd.engine.calls import CallDenied
from isd.engine.commissary import OrderError
from isd.engine.contacts import ContactInvalid
from isd.engine.features import BASELINE_FEATURES, NON_BASELINE_FEATURES
from isd.engine.sandbox import SandboxOverrides, SandboxSanction
from isd.interfaces.messaging import MessagingService
from isd.interfaces.telephony import TelephonyService
from isd.interfaces.video import VideoService
from isd.mocks.messaging import MockMessagingProvider
from isd.mocks.telephony import MockTelephonyProvider
from isd.mocks.video import MockVideoProvider
from isd.models import (
    Appeal,
    AuditLog,
    Base,
    CallRecord,
    Cell,
    ChessGame,
    ChessMove,
    Contact,
    Device,
    DeviceAssignment,
    JobEnrollment,
    JobTask,
    KeepSeparate,
    Message,
    MessageFlag,
    OffenseFlag,
    OutOfCellLog,
    PointEvent,
    QuizSession,
    Resident,
    Sanction,
    Staff,
    TierHistory,
    TrustLedger,
    WelfareFlag,
)
from isd.seed_db import ensure_reference_data
from isd.services import (
    calls,
    chess,
    commissary,
    daily,
    education,
    facility,
    jobs,
    mirror,
    monitoring,
    movement,
    out_of_cell,
    points,
    public_log,
    reading,
    rec,
    reconcile,
    reentry,
    sanctions,
    schedule,
    staff_requests,
    texting,
    video_bookings,
    welfare,
    work_tasks,
)
from isd.services import contacts as contact_service
from isd.services import intake as intake_service
from isd.services.audit import SYSTEM, Actor, verify_chain
from isd.services.config_store import get_current, set_config
from isd.services.entitlement_service import get_entitlements, load_engine_config
from isd.services.intake import IntakeContact, IntakeRequest
from isd.services.resident_view import build_resident_view

# Refusals the rules are supposed to make. Anything not listed here is a bug and stops the run.
EXPECTED = (
    intake_service.IntakeError,
    reentry.ReentryError,
    outcome_service.OutcomeError,
    AuthorityError,
    CallDenied,
    OrderError,
    texting.TextDenied,
    movement.MovementError,
    welfare.WelfareError,
    schedule.ScheduleError,
    ContactInvalid,
    education.EducationError,
    chess.ChessDenied,
    reading.ReadingDenied,
    jobs.JobError,
    rec.RecDenied,
)
SAMPLE_HOURS = (8, 10, 12, 14, 16, 19)
DEFAULT_START = datetime(2026, 3, 2, tzinfo=UTC)  # a Monday
OFFICER_CODES = [
    ("DISRUPT", 35),
    ("CELL_MESS", 25),
    ("STAFF_DISRESPECT", 12),
    ("CAM_BLOCK", 10),
    ("DEVICE_DAMAGE", 5),
]
ACTIONS = [
    ("education", 12),
    ("call", 25),
    ("text", 15),
    ("order", 12),
    ("deposit", 2),
    ("reading", 8),
    ("chess", 6),
    ("rec", 8),
    ("job", 10),
    ("video", 14),
    ("video_book", 16),
    ("contact_request", 3),
    ("request", 4),
]


@dataclass
class SimConfig:
    seed: int = 1
    residents: int = 24
    days: int = 7
    start: datetime = DEFAULT_START
    officers: int = 5
    supervisors: int = 3


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    counts: Counter = field(default_factory=Counter)
    denied: Counter = field(default_factory=Counter)
    checks: list[Check] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "actions": dict(sorted(self.counts.items())),
            "refusals": dict(sorted(self.denied.items())),
            "summary": self.summary,
            "checks": [c.__dict__ for c in self.checks],
        }


def fingerprints(engine: Engine, skip: tuple[str, ...] = ()) -> dict[str, str]:
    """A checksum of every table's contents; any insert, update or delete changes it."""
    out = {}
    with engine.connect() as c:
        for t in Base.metadata.sorted_tables:
            if t.name in skip:
                continue
            sql = (
                "SELECT md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
                f'FROM "{t.name}" x'
            )
            out[t.name] = c.execute(text(sql)).scalar()
    return out


class Simulation:
    def __init__(self, engine: Engine, cfg: SimConfig):
        self.engine, self.cfg = engine, cfg
        self.rng = random.Random(cfg.seed)
        self.s = Session(engine)
        self.report = Report()
        self.tick = 0
        self.officers: list[Actor] = []
        self.supervisors: list[Actor] = []
        self.admin = self.auditor = None
        self.residents: list[int] = []
        self.contacts: dict[int, list[Contact]] = {}
        self.names: set[str] = set()
        self.admitted: list[int] = []
        self.course = None

    # ---------- helpers ----------
    def attempt(self, label: str, fn, *args, **kw):
        try:
            with self.s.begin_nested():
                result = fn(*args, **kw)
        except EXPECTED as e:
            self.report.denied[f"{label}:{getattr(e, 'code', type(e).__name__)}"] += 1
            return None
        self.report.counts[label] += 1
        return result

    def pick(self, weighted):
        return self.rng.choices([w[0] for w in weighted], [w[1] for w in weighted])[0]

    def stamp(self, base: datetime) -> datetime:
        self.tick += 1
        return base + timedelta(seconds=self.tick)

    # ---------- setup ----------
    def setup(self) -> None:
        s, rng, cfg = self.s, self.rng, self.cfg
        providers.set_telephony(TelephonyService(MockTelephonyProvider()))
        from isd.providers import set_messaging

        set_messaging(MessagingService(MockMessagingProvider()))
        providers.set_video(VideoService(MockVideoProvider()))
        before = cfg.start - timedelta(days=30)
        for name, payload in load_config().items():
            if (
                name == "compliance"
            ):  # recording on, so "attorney video is never recorded" is tested
                payload = {**payload, "video_recording_enabled": True}
            set_config(s, SYSTEM, name, payload, "simulation seed")
        ensure_reference_data(s)
        pw = hash_password("simulation-only-password")

        def staff(prefix, role, n):
            out = []
            for i in range(1, n + 1):
                st = Staff(username=f"sim_{prefix}{i}", role=role, password_hash=pw)
                s.add(st)
                s.flush()
                self.names.add(st.username)
                out.append(Actor(st.id, role))
            return out

        self.officers = staff("officer", "officer", cfg.officers)
        self.supervisors = staff("supervisor", "supervisor", cfg.supervisors)
        self.admin = staff("admin", "admin", 1)[0]
        self.auditor = staff("auditor", "auditor", 1)[0]

        self.course = next(
            c for c in get_current(s, "courses").payload["courses"] if c["level"] == "basic"
        )
        offense_cats = list(get_current(s, "offenses").payload["offense_restrictions"])
        for i in range(1, cfg.residents + 1):
            code = f"SIM-{i:03d}"
            r = Resident(
                code=code,
                display_name=f"Synthetic Person {i}",
                language=rng.choice(["en", "es"]),
                prior_returns=rng.choice([0, 0, 0, 1, 2, 4, 7]),
            )
            cell, dev = (
                Cell(code=f"SIM-CELL-{i:03d}", line_code=f"L{i % 4}"),
                Device(code=f"SIM-DEV-{i:03d}"),
            )
            s.add_all([r, cell, dev])
            s.flush()
            s.add(
                DeviceAssignment(
                    device_id=dev.id, cell_id=cell.id, resident_id=r.id, assigned_at=before
                )
            )
            self.names |= {r.display_name, code, cell.code, dev.code}
            start_pts = rng.choice([0, 0, 40, 120, 300, 520, 800, 1100, 1500, 2600])
            if start_pts:
                points.record_points(
                    s, SYSTEM, r.id, "seed_adjustment", start_pts, "system", before
                )
                points.evaluate_tier(s, r.id, before)
            kinds = ["family", "friend"] + (["attorney"] if rng.random() < 0.7 else [])
            self.contacts[r.id] = []
            for k, kind in enumerate(kinds):
                c = Contact(
                    resident_id=r.id,
                    name=f"Synthetic Contact {code}-{k}",
                    type=kind,
                    phone_ref=f"555-{i:03d}{k}",
                    blocked=(kind == "friend" and rng.random() < 0.1),
                )
                s.add(c)
                self.contacts[r.id].append(c)
                self.names.add(c.name)
            s.flush()
            commissary.deposit(
                s, SYSTEM, r.id, rng.choice([3000, 5000, 8000]), "family", f"sim-seed-{i}", before
            )
            if offense_cats and i % 8 == 0:
                s.add(
                    OffenseFlag(
                        resident_id=r.id,
                        offense_category=offense_cats[0]["offense_category"],
                        added_at=before,
                    )
                )
            self.residents.append(r.id)
        s.commit()

    def do_work(self, rid: int, listing_id: int, now: datetime) -> None:
        """Takes a task and hands it in, usually correctly."""
        s, rng = self.s, self.rng
        view = self.attempt("work_task", work_tasks.next_task, s, rid, listing_id, now)
        if not view:
            return
        spec = s.get(JobTask, view["task_id"]).spec
        if rng.random() < 0.8:
            answer = spec.get("expected") or f"someone with a {spec['keywords'][0]} nearby"
        else:
            answer = "no idea at all"
        self.attempt("work_submit", work_tasks.submit, s, rid, view["task_id"], answer, now)

    # ---------- resident actions ----------
    def resident_action(self, rid: int, now: datetime) -> None:
        s, rng = self.s, self.rng
        what = self.pick(ACTIONS)
        contacts = self.contacts[rid]
        if what == "education":
            c = self.course
            for le in c["lessons"]:
                self.attempt("lesson", education.complete_lesson, s, rid, c["code"], le["id"], now)
            paper = self.attempt("quiz_start", education.start_quiz, s, rid, c["code"], now)
            if paper:
                bank = {q["id"]: q for q in c["quiz"]["bank"]}
                drawn = s.get(QuizSession, paper["quiz_id"]).questions
                answers = []
                for q in drawn:
                    right = q["order"].index(bank[q["id"]]["answer"])
                    answers.append(right if rng.random() < 0.8 else rng.randrange(len(q["order"])))
                self.attempt(
                    "quiz", education.submit_quiz, s, rid, c["code"], paper["quiz_id"], answers, now
                )
        elif what in ("call", "video"):
            contact = rng.choice(contacts)
            call = self.attempt(
                what,
                calls.start_call,
                s,
                rid,
                contact.id,
                now,
                medium="video" if what == "video" else "voice",
            )
            if call:
                if what == "video" and rng.random() < 0.15:
                    self.attempt(
                        "video_tamper",
                        calls.report_video_tamper,
                        s,
                        rid,
                        call.id,
                        now + timedelta(minutes=2),
                    )
                else:
                    length = rng.randint(30, call.max_seconds + 120)
                    calls.end_call(s, rid, call.id, now + timedelta(seconds=length))
        elif what == "text":
            self.attempt(
                "text",
                texting.send_text,
                s,
                rid,
                rng.choice(contacts).id,
                rng.choice(
                    [
                        f"Hello from the unit {rng.randint(1, 999)}",
                        "we talked about demo contraband",
                    ]
                ),
                now,
            )
        elif what == "video_book":
            when = (now + timedelta(days=rng.randint(1, 3))).replace(
                hour=rng.choice([9, 10, 14]),
                minute=rng.choice([0, 15, 30]),
                second=0,
                microsecond=0,
            )
            self.attempt(
                "video_book",
                video_bookings.book,
                s,
                rid,
                rng.choice(contacts).id,
                when,
                rng.choice([15, 30]),
                now,
            )
        elif what == "contact_request":
            req = self.attempt(
                "contact_request",
                contact_service.request_contact,
                s,
                rid,
                f"Synthetic Visitor {rng.randint(1, 9999)}",
                rng.choice(["family", "friend", "attorney"]),
                f"555-{rng.randint(1000000, 9999999)}",
                now,
            )
            if req:
                self.attempt(
                    "contact_review",
                    contact_service.review_contact,
                    s,
                    rng.choice(self.supervisors),
                    req.id,
                    rng.random() < 0.8,
                    "does not check out",
                    now,
                )
        elif what == "order":
            items = rng.sample(
                [i["code"] for i in get_current(s, "commissary").payload["items"]],
                rng.randint(1, 3),
            )
            self.attempt(
                "order",
                commissary.place_order,
                s,
                rid,
                {c: rng.randint(1, 2) for c in items},
                f"sim-order-{uuid.UUID(int=rng.getrandbits(128))}",
                now,
            )
        elif what == "deposit":
            self.attempt(
                "deposit",
                commissary.deposit,
                s,
                SYSTEM,
                rid,
                rng.choice([1000, 2500]),
                "family",
                f"sim-dep-{uuid.UUID(int=rng.getrandbits(128))}",
                now,
            )
        elif what == "reading":
            text = rng.choice(
                [
                    "tortoise-hare",
                    "lion-mouse",
                    "preamble",
                    "gettysburg",
                    "psalm-23",
                    "bill-of-rights-selected",
                ]
            )
            if self.attempt("reading", reading.read_item, s, rid, text, now):
                self.attempt("reading", reading.save_progress, s, rid, text, rng.randrange(4), now)
        elif what == "chess":
            if rng.random() < 0.5:
                game = self.attempt("chess_game", chess.new_engine_game, s, rid, 1, now)
                if game:
                    self.attempt(
                        "chess_move",
                        chess.finish_engine_game,
                        s,
                        rid,
                        game.id,
                        rng.choice(["white", "black", "draw"]),
                        "resigned",
                        now,
                    )
            else:
                game = self.attempt("chess_game", chess.find_match, s, rid, now)
                if game and game.status == "active":
                    mine_white = game.resident_id == rid
                    first = "e2e4" if mine_white else "e7e5"
                    played = self.attempt(
                        "chess_move", chess.play_move, s, rid, game.id, first, now
                    )
                    if played and rng.random() < 0.5:
                        self.attempt("chess_move", chess.leave, s, rid, game.id, now)
        elif what == "rec":
            cfg = get_current(s, "rec").payload
            self.attempt(
                "rec",
                rec.book,
                s,
                rid,
                now.date(),
                rng.choice(cfg["indoor_slots"] + cfg["outdoor_slots"]),
                now,
            )
        elif what == "job":
            listing = rng.choice(jobs.list_listings(s, rid))
            if listing["enrolled"] and rng.random() < 0.7:
                for _ in range(rng.randint(1, 3)):
                    self.do_work(rid, listing["id"], now)
            elif listing["enrolled"]:
                self.attempt("job_leave", jobs.leave, s, rid, listing["id"], now)
            else:
                self.attempt("job_join", jobs.opt_in, s, rid, listing["id"], now)
        elif what == "request":
            self.attempt(
                "staff_request",
                staff_requests.create,
                s,
                rid,
                rng.choice(["staff", "medical", "mental_health"]),
                f"sim-req-{uuid.UUID(int=rng.getrandbits(128))}",
                now,
            )

    # ---------- staff actions ----------
    def staff_actions(self, now: datetime) -> None:
        s, rng = self.s, self.rng
        everyone = [a.id for a in (*self.officers, *self.supervisors)]
        for officer in self.officers:
            if rng.random() < 0.45:
                code = self.pick(OFFICER_CODES)
                target = rng.choice(self.residents)
                reporter = rng.choice([i for i in everyone if i != officer.id])
                ev = (
                    Evidence("second_staff_report", reporter_id=reporter)
                    if code not in ("DISRUPT", "CELL_MESS")
                    else None
                )
                self.attempt(
                    "sanction_issue", sanctions.issue_sanction, s, officer, target, code, now, ev
                )
        if rng.random() < 0.08:  # a supervisor records one and then tries to confirm it themselves
            sup = rng.choice(self.supervisors)
            reporter = rng.choice([a.id for a in self.officers])
            sanc = self.attempt(
                "sanction_issue",
                sanctions.issue_sanction,
                s,
                sup,
                rng.choice(self.residents),
                "DEVICE_DAMAGE",
                now,
                Evidence("second_staff_report", reporter_id=reporter),
            )
            if sanc:
                self.attempt("self_confirm", sanctions.confirm_sanction, s, sup, sanc.id, now)
        if rng.random() < 0.5:  # officers walk a few residents out and bring them back
            officer = rng.choice(self.officers)
            ids = rng.sample(self.residents, 3)
            activity = rng.choice(["indoor", "outdoor", "program"])
            self.attempt("movement_out", movement.bulk_out, s, officer, ids, activity, now)
            back = now + timedelta(minutes=rng.randint(20, 70))
            self.attempt("movement_in", movement.bulk_in, s, officer, ids, back)
        if rng.random() < 0.3:  # staff handle some welfare flags; the rest wait and escalate
            for row in welfare.all_flags(s, now)[:2]:
                flag = row["flags"][0]
                who = rng.choice([*self.officers, *self.supervisors])
                self.attempt(
                    "welfare_ack",
                    welfare.acknowledge,
                    s,
                    who,
                    row["resident_id"],
                    flag["type"],
                    "checked in on the resident",
                    now,
                    "checked_in",
                )
        if rng.random() < 0.3:  # a supervisor works the monitoring queue (flags are review items)
            sup = rng.choice(self.supervisors)
            for row in monitoring.queue(s, flagged_only=True, limit=3):
                self.attempt(
                    "monitor_read",
                    monitoring.read_message,
                    s,
                    sup,
                    row["message_id"],
                    "reviewing a keyword flag",
                    now,
                )
                for flag in row["flags"]:
                    if flag["status"] == "open":
                        self.attempt(
                            "flag_review",
                            monitoring.review_flag,
                            s,
                            sup,
                            flag["id"],
                            rng.choice(["no_action", "referred"]),
                            "looked at the message",
                            now,
                        )
        if rng.random() < 0.1:  # a facility camera event
            n = rng.randint(1, self.cfg.residents)
            self.attempt(
                "camera_event",
                facility.ingest,
                s,
                __import__("isd.interfaces.facility", fromlist=["x"]).FacilityEventIn(
                    f"sim-cam-{uuid.UUID(int=rng.getrandbits(128))}",
                    "camera_obstruction",
                    {"cell": f"SIM-CELL-{n:03d}"},
                ),
                now,
            )

        pending = (
            s.execute(
                select(Sanction).where(Sanction.status == "pending").order_by(Sanction.id).limit(4)
            )
            .scalars()
            .all()
        )
        for sanc in pending:
            sup = rng.choice(self.supervisors)
            if rng.random() < 0.75:
                self.attempt("sanction_confirm", sanctions.confirm_sanction, s, sup, sanc.id, now)
            else:
                self.attempt(
                    "sanction_reject",
                    sanctions.reject_sanction,
                    s,
                    sup,
                    sanc.id,
                    "not enough evidence",
                    now,
                )

        open_ids = set(
            s.execute(select(Appeal.sanction_id).where(Appeal.status == "open")).scalars()
        )
        live = (
            s.execute(select(Sanction).where(Sanction.status == "active", Sanction.ends_at > now))
            .scalars()
            .all()
        )
        for sanc in live:
            if sanc.id not in open_ids and rng.random() < 0.25:
                self.attempt("appeal_file", sanctions.file_appeal, s, sanc.id, now)
        for appeal in (
            s.execute(select(Appeal).where(Appeal.status == "open").limit(3)).scalars().all()
        ):
            sup = rng.choice(self.supervisors)
            self.attempt(
                "appeal_review",
                sanctions.review_appeal,
                s,
                sup,
                appeal.id,
                rng.choice(["upheld", "overturned"]),
                "reviewed against the evidence",
                now,
            )

    def end_of_day(self, day: date, now: datetime) -> None:
        s, rng = self.s, self.rng
        for rid in self.residents:
            roll = rng.random()
            if roll < 0.05:
                continue  # nobody entered a number for this resident today
            minutes = rng.randint(20, 55) if roll < 0.15 else rng.randint(60, 150)
            self.attempt(
                "out_of_cell",
                out_of_cell.record,
                s,
                self.officers[0],
                rid,
                day,
                minutes,
                "facility",
                now,
            )
        result = daily.run_daily(s, now, for_day=day)
        self.report.counts["daily_clean_days"] += result["clean_days_awarded"]
        again = daily.run_daily(s, now + timedelta(minutes=1), for_day=day)  # must change nothing
        if again["clean_days_awarded"]:
            self.report.checks.append(
                Check(
                    "daily job is repeat-safe",
                    False,
                    f"awarded {again['clean_days_awarded']} twice on {day}",
                )
            )
        s.commit()

    # ---------- the week ----------
    def run(self) -> Report:
        self.setup()
        cfg, rng = self.cfg, self.rng
        for d in range(cfg.days):
            day_start = cfg.start + timedelta(days=d)
            for hour in SAMPLE_HOURS:
                now = day_start + timedelta(hours=hour)
                order = self.residents[:]
                rng.shuffle(order)
                for rid in order:
                    for _ in range(rng.choice([0, 1, 1, 2])):
                        self.resident_action(rid, self.stamp(now))
                self.staff_actions(self.stamp(now))
                self.s.commit()
            if d == 2:
                self.admissions_and_reentry(day_start + timedelta(hours=18))
            if d == 3:
                self.sandbox_and_mirror(day_start + timedelta(hours=20))
            self.end_of_day(day_start.date(), day_start + timedelta(hours=23, minutes=30))
        self.verify(cfg.start + timedelta(days=cfg.days))
        return self.report

    # ---------- intake, reentry and outcomes ----------
    def admissions_and_reentry(self, now: datetime) -> None:
        s = self.s
        rng = random.Random(self.cfg.seed + 15)  # its own stream: other phases stay reproducible
        sup = self.supervisors[0]
        for n in range(2):
            tag = uuid.uuid4().hex[:6]
            cell, dev = Cell(code=f"SIM-C{tag}"), Device(code=f"SIM-D{tag}")
            s.add_all([cell, dev])
            s.flush()
            req = IntakeRequest(
                display_name=f"Synthetic Admit {tag}",
                cell_code=cell.code,
                device_code=dev.code,
                reason="simulated admission",
                prior_returns=n,
                prior_returns_source="simulation" if n else None,
                release_date=(now + timedelta(days=30 + n)).date(),
                offense_categories=["PLACEHOLDER_CATEGORY_A"] if n else [],
                contacts=[IntakeContact(f"Synthetic Kin {tag}", "family", "555-0150")],
                keep_separate=[(s.get(Resident, rng.choice(self.residents)).code, "simulated")]
                if n
                else [],
            )
            resident = self.attempt("intake", intake_service.intake, s, sup, req, now)
            if resident is not None:
                self.admitted.append(resident.id)
                self.names |= {resident.display_name, resident.code, cell.code, dev.code}
        for rid in rng.sample(self.residents, min(6, len(self.residents))):
            item = rng.choice(["ID_DOCUMENTS", "HOUSING", "EMPLOYMENT"])
            status = rng.choice(["in_progress", "done", "not_needed"])
            self.attempt(
                "reentry_item",
                reentry.record_item,
                s,
                rng.choice(self.officers),
                rid,
                item,
                status,
                None,
                now,
            )
        for rid in rng.sample(self.residents, min(3, len(self.residents))):
            self.attempt(
                "release_date",
                reentry.set_release_date,
                s,
                sup,
                rid,
                (now + timedelta(days=60)).date(),
                "simulated",
                now,
            )
        for rid in rng.sample(self.residents, min(10, len(self.residents))):
            outcome = rng.choice(["no_return", "returned", "unknown"])
            code = s.get(Resident, rid).code
            self.attempt(
                "outcome",
                outcome_service.record_outcome,
                s,
                self.admin,
                code,
                6,
                outcome,
                "simulated record",
                now,
            )
        s.commit()

    # ---------- sandbox and mirror ----------
    def sandbox_and_mirror(self, now: datetime) -> None:
        self.s.commit()
        before = fingerprints(self.engine)
        with Session(self.engine) as ro:
            ro.execute(text("SET TRANSACTION READ ONLY"))
            for rid in self.residents[:4]:
                for ov in (
                    SandboxOverrides(tier=9),
                    SandboxOverrides(
                        add_sanctions=(SandboxSanction("CAM_BLOCK", 5),), language="es"
                    ),
                    SandboxOverrides(clear_sanctions=True, prior_returns=12),
                ):
                    build_resident_view(
                        ro, rid, now + timedelta(days=2), simulation=True, overrides=ov
                    )
            ro.rollback()
        same = before == fingerprints(self.engine)
        self.report.checks.append(
            Check(
                "sandbox wrote nothing",
                same,
                "every table identical before and after 12 simulated views",
            )
        )
        sup = self.supervisors[0]
        m = mirror.start(self.s, sup, self.residents[0], "simulation: checking the mirror", now)
        dev = self.s.execute(select(Device).where(Device.id == m.device_id)).scalar()
        mirror.record_screen(self.s, dev, "/resident/feature/legal_materials", now)
        redacted = mirror.frame(self.s, sup, m.id, now)["redacted"] == "PRIVATE_SCREEN"
        mirror.record_screen(self.s, dev, "/resident/tier", now)
        shown = mirror.frame(self.s, sup, m.id, now)["redacted"] is None
        mirror.end(self.s, sup, m.id, now)
        self.s.commit()
        self.report.checks.append(
            Check("mirror redacts private screens and is logged", redacted and shown)
        )

    # ---------- the checks ----------
    def verify_chess(self) -> None:
        """Invariant 13 over the simulated week: nobody was paired with a keep-separate partner or
        a resident on the same line, and no chat-like column exists."""
        s = self.s
        line = {
            rid: ln
            for rid, ln in s.execute(
                select(DeviceAssignment.resident_id, Cell.line_code).join(
                    Cell, Cell.id == DeviceAssignment.cell_id
                )
            ).all()
        }
        sep = {
            (a, b)
            for a, b in s.execute(select(KeepSeparate.resident_a_id, KeepSeparate.resident_b_id))
        }
        bad = []
        paired = 0
        for g in s.execute(
            select(ChessGame).where(ChessGame.black_resident_id.isnot(None))
        ).scalars():
            paired += 1
            a, b = sorted((g.resident_id, g.black_resident_id))
            if (a, b) in sep or not line.get(a) or line.get(a) == line.get(b):
                bad.append(g.id)
        add = self.report.checks.append
        add(
            Check(
                "chess never paired kept-apart or same-line residents", not bad, f"{paired} matches"
            )
        )
        cols = {c.name for t in (ChessGame, ChessMove) for c in t.__table__.columns}
        banned = ("chat", "message", "text", "note", "comment", "stake", "wager", "bet", "item")
        add(
            Check(
                "chess tables hold no chat or stake column",
                not any(w in c for c in cols for w in banned),
            )
        )

    def verify_phase15(self, end: datetime) -> None:
        s, add = self.s, self.report.checks.append
        trail = {a for a in s.execute(select(AuditLog.action)).scalars()}
        wanted = {"resident_intake", "device_assignment", "contact_added", "release_date_set"}
        add(Check("intake leaves an audit trail", wanted <= trail and bool(self.admitted)))
        homed = [r for r in self.admitted if build_resident_view(s, r, end).reentry is not None]
        add(
            Check(
                "an admitted resident sees their release countdown",
                len(homed) == len(self.admitted),
            )
        )
        before = {
            "sanctions": s.execute(select(func.count()).select_from(Sanction)).scalar(),
            "tier_history": s.execute(select(func.count()).select_from(TierHistory)).scalar(),
            "points": s.execute(select(func.count()).select_from(PointEvent)).scalar(),
        }
        set_config(
            s,
            SYSTEM,
            "compliance",
            {**get_current(s, "compliance").payload, "researcher_export_enabled": True},
            "simulation: enable the researcher export",
        )
        outcome_service.dashboard(s, end)
        data = outcome_service.export(s, self.admin, "simulation check", "sim-research-salt", end)
        blob = repr(data["rows"])
        codes = {r.code for r in s.execute(select(Resident)).scalars()}
        leaked = sorted(n for n in (self.names | codes) if n in blob)
        add(
            Check(
                "researcher export contains no names or codes",
                not leaked and len(data["rows"]) >= len(self.residents),
                f"{len(data['rows'])} rows" if not leaked else str(leaked[:5]),
            )
        )
        after = {
            "sanctions": s.execute(select(func.count()).select_from(Sanction)).scalar(),
            "tier_history": s.execute(select(func.count()).select_from(TierHistory)).scalar(),
            "points": s.execute(select(func.count()).select_from(PointEvent)).scalar(),
        }
        add(Check("analytics changed no tier, point or sanction", before == after))

    def verify(self, end: datetime) -> None:
        s, add = self.s, self.report.checks.append
        s.commit()

        chain = verify_chain(s)
        add(
            Check(
                "audit chain verifies",
                chain.ok,
                f"{chain.entries} entries"
                if chain.ok
                else f"{chain.problem} at {chain.first_bad_seq}",
            )
        )
        problems = commissary.verify_ledgers(s)
        add(
            Check(
                "trust ledgers are consistent",
                not problems,
                f"{len(problems)} problems" if problems else "every balance and order adds up",
            )
        )
        low = s.execute(
            select(func.count()).select_from(TrustLedger).where(TrustLedger.balance_after_cents < 0)
        ).scalar()
        add(Check("no negative balances", low == 0))

        # baseline never locked, and every lock is explained, at every sample moment
        bad = []
        cfg = load_engine_config(s)
        for d in range(self.cfg.days):
            when = self.cfg.start + timedelta(days=d, hours=12)
            for rid in self.residents:
                ent = get_entitlements(s, rid, when, cfg)
                for f in BASELINE_FEATURES:
                    if not ent.features[f].allowed or ent.features[f].reasons:
                        bad.append((rid, d, f))
                for f in NON_BASELINE_FEATURES:
                    fe = ent.features[f]
                    if (
                        not fe.allowed
                        and not all(r.code and r.how_to_appeal for r in fe.reasons)
                        or (not fe.allowed and not fe.reasons)
                    ):
                        bad.append((rid, d, f))
        add(
            Check(
                "protected baseline never locked; every lock has a reason and a way to appeal",
                not bad,
                f"{len(self.residents) * self.cfg.days} resident-days sampled"
                if not bad
                else str(bad[:3]),
            )
        )

        # legal and religious texts stay readable for everyone, whatever sanctions are active
        shut = []
        for d in range(self.cfg.days):
            when = self.cfg.start + timedelta(days=d, hours=12)
            for rid in self.residents:
                shut += [
                    (rid, d, i["id"])
                    for i in reading.list_items(s, rid, when)
                    if i["catalog"] in ("legal", "religious") and not i["allowed"]
                ]
        add(
            Check(
                "legal and religious texts readable by everyone on every sampled day",
                not shut,
                "ok" if not shut else str(shut[:3]),
            )
        )

        # tier drops: one level at a time, at least seven days apart
        drops_bad = []
        for rid in self.residents:
            hist = (
                s.execute(
                    select(TierHistory)
                    .where(TierHistory.resident_id == rid)
                    .order_by(TierHistory.at, TierHistory.id)
                )
                .scalars()
                .all()
            )
            drops = [h for h in hist if h.to_tier < h.from_tier]
            drops_bad += [rid for h in drops if h.from_tier - h.to_tier != 1]
            drops_bad += [
                rid
                for a, b in zip(drops, drops[1:], strict=False)
                if b.at - a.at < timedelta(days=7)
            ]
        add(
            Check(
                "tier drops are one level and a week apart",
                not drops_bad,
                str(drops_bad[:3]) if drops_bad else "",
            )
        )

        # authority rules
        sanc = s.execute(select(Sanction)).scalars().all()
        cfgs = cfg.infractions
        wrong = [x.id for x in sanc if x.confirmed_by is not None and x.confirmed_by == x.issued_by]
        wrong += [
            x.id
            for x in sanc
            if x.status == "active" and not x.applied_immediately and x.confirmed_by is None
        ]
        wrong += [
            x.id
            for x in sanc
            if x.applied_immediately
            and (
                cfgs[x.infraction_code].confirmation != "officer_immediate"
                or cfgs[x.infraction_code].duration_hours > 24
            )
        ]
        wrong += [x.id for x in sanc if x.status == "pending" and x.starts_at is not None]
        add(
            Check(
                "significant sanctions need a different supervisor than the issuer",
                not wrong,
                f"{len(sanc)} sanctions" if not wrong else str(wrong[:5]),
            )
        )
        cap_bad = []
        for o in self.officers:
            mine = sorted(
                x.issued_at for x in sanc if x.issued_by == o.id and x.applied_immediately
            )
            for t in mine:
                if (
                    len([u for u in mine if t - timedelta(days=7) < u <= t])
                    > cfg.officer_weekly_cap
                ):
                    cap_bad.append(o.id)
        add(Check("officers never exceed the weekly immediate-sanction cap", not cap_bad))
        appeals = s.execute(
            select(Appeal, Sanction.issued_by).join(Sanction, Sanction.id == Appeal.sanction_id)
        ).all()
        add(
            Check(
                "appeals are reviewed by someone other than the issuer",
                all(
                    a.status == "open" or (a.reviewer_id is not None and a.reviewer_id != issuer)
                    for a, issuer in appeals
                ),
                f"{len(appeals)} appeals",
            )
        )

        # privacy of attorney communications, at scale
        calls_all = s.execute(select(CallRecord)).scalars().all()
        priv = [c for c in calls_all if c.privileged]
        add(
            Check(
                "attorney calls: no monitoring data anywhere",
                all(c.monitor_ref is None and not c.monitored for c in priv),
                f"{len(priv)} attorney calls, {len(calls_all) - len(priv)} monitored",
            )
        )
        provider = providers.get_telephony()._p
        monitored = [c for c in calls_all if c.monitored and c.medium == "voice"]
        add(
            Check(
                "only monitored calls were ever recorded by the provider",
                provider.recordings_created == len(monitored),
                f"{provider.recordings_created} recordings for {len(monitored)} monitored calls",
            )
        )
        video_provider = providers.get_video()._p
        video_all = [c for c in calls_all if c.medium == "video"]
        recorded = [c for c in video_all if c.monitor_ref]
        add(
            Check(
                "attorney video is never recorded, even with recording switched on",
                all(c.monitor_ref is None for c in video_all if c.privileged)
                and all(
                    rec["recording"] is None
                    for ref, rec in video_provider.sessions.items()
                    if any(c.provider_ref == ref and c.privileged for c in video_all)
                ),
                f"{len(video_all)} video calls, {len(recorded)} recorded",
            )
        )
        texts = s.execute(select(Message)).scalars().all()
        priv_msgs = [m for m in texts if m.privileged]
        readable = []
        for m in priv_msgs:
            for role, actor in (
                ("supervisor", self.supervisors[0]),
                ("officer", self.officers[0]),
                ("admin", self.admin),
                ("auditor", Actor(self.admin.id, "auditor")),
            ):
                try:
                    monitoring.read_message(s, actor, m.id, "simulation attempt to read", end)
                    readable.append((m.id, role))
                except monitoring.MonitoringDenied:
                    pass
        add(
            Check(
                "no role can read an attorney message, and none appear in the monitoring queue",
                not readable
                and all(
                    r["message_id"] not in {m.id for m in priv_msgs}
                    for r in monitoring.queue(s, limit=10_000)
                ),
                f"{len(priv_msgs)} attorney messages tried by four roles",
            )
        )
        flags = s.execute(select(MessageFlag)).scalars().all()
        add(
            Check(
                "keyword flags are review items only: none was acted on without a person",
                all(f.status == "open" or (f.reviewed_by and f.review_reason) for f in flags),
                f"{len(flags)} flags, {sum(f.status != 'open' for f in flags)} reviewed by people",
            )
        )
        pending_left = [
            c for c in s.execute(select(Contact)).scalars() if c.requested_by == "resident"
        ]
        add(
            Check(
                "every reviewed contact request has a reviewer and a matching approval flag",
                all(
                    c.approved == (c.status == "approved")
                    and (c.status == "pending" or c.reviewed_by is not None)
                    for c in pending_left
                ),
                f"{len(pending_left)} resident-requested contacts",
            )
        )
        add(
            Check(
                "attorney messages: no text stored",
                all(m.body is None and not m.monitored for m in texts if m.privileged),
                f"{sum(m.privileged for m in texts)} attorney messages",
            )
        )
        add(
            Check(
                "every call ended within its cap",
                all(
                    c.duration_seconds is None or c.duration_seconds <= c.max_seconds
                    for c in calls_all
                ),
            )
        )

        # welfare: a flag nobody handled in time went to a supervisor, and only they handled it
        window = timedelta(minutes=get_current(s, "welfare").payload["escalate_after_minutes"])
        stored = s.execute(select(WelfareFlag)).scalars().all()
        senior = {a.id for a in (*self.supervisors, self.admin)}
        late = [f for f in stored if f.status == "open" and f.raised_at <= end - window]
        wrong = [
            f
            for f in stored
            if f.escalated_at and f.status == "acknowledged" and f.acknowledged_by not in senior
        ]
        add(
            Check(
                "unacknowledged welfare flags escalate on time; escalated ones go to a supervisor",
                not any(f.escalated_at is None for f in late) and not wrong,
                f"{len(stored)} flags, {sum(f.escalated_at is not None for f in stored)} escalated",
            )
        )

        # money: work earnings and the trust ledger reconcile, every night and now
        from isd.models import ReconciliationRun

        nightly = s.execute(select(ReconciliationRun)).scalars().all()
        checked, problems = reconcile.run_checks(s)
        add(
            Check(
                "earnings and trust ledgers reconcile (nightly job and a final check)",
                not problems and bool(nightly) and all(r.ok for r in nightly),
                f"{len(nightly)} nightly runs; {checked['earnings_entries']} earnings entries, "
                f"{checked['trust_entries']} trust entries",
            )
        )

        # jobs and points
        add(
            Check(
                "jobs created no points or sanctions",
                not s.execute(select(PointEvent).where(PointEvent.kind.ilike("%job%"))).first()
                and s.execute(select(func.count()).select_from(JobEnrollment)).scalar() > 0,
                f"{s.execute(select(func.count()).select_from(JobEnrollment)).scalar()} enrolments",
            )
        )
        dupes = s.execute(
            select(PointEvent.resident_id, PointEvent.reason, func.count())
            .where(PointEvent.kind == "clean_day")
            .group_by(PointEvent.resident_id, PointEvent.reason)
            .having(func.count() > 1)
        ).all()
        add(Check("no clean day awarded twice", not dupes))

        # append-only tables refuse changes
        refused = True
        for stmt in (
            "UPDATE out_of_cell_log SET minutes = 0",
            "UPDATE audit_log SET action = 'x'",
            "UPDATE trust_ledger SET memo = 'x'",
            "UPDATE reentry_events SET status = 'todo'",
            "UPDATE outcome_records SET outcome = 'unknown'",
        ):
            try:
                with s.begin_nested():
                    s.execute(text(stmt))
                refused = False
            except Exception:  # noqa: BLE001 - the database is supposed to refuse
                pass
        add(Check("append-only tables refuse updates", refused))

        # the public export
        set_config(
            s,
            SYSTEM,
            "compliance",
            {**get_current(s, "compliance").payload, "public_log_enabled": True},
            "simulation: enable the public log",
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = public_log.export(s, end, "simulation-salt", Path(tmp))
            blob = "\n".join(p.read_text() for p in sorted(Path(tmp).iterdir()))
        leaked = sorted(n for n in self.names if n in blob)
        add(
            Check(
                "public export contains no names, codes or staff",
                not leaked,
                f"{result['records']} records" if not leaked else str(leaked[:5]),
            )
        )
        s.commit()
        add(Check("audit chain still verifies after the export", verify_chain(s).ok))

        self.verify_phase15(end)
        self.verify_chess()
        s.commit()

        # summary
        required = [
            "lesson",
            "quiz",
            "call",
            "text",
            "video_book",
            "contact_request",
            "contact_review",
            "monitor_read",
            "flag_review",
            "order",
            "deposit",
            "reading",
            "rec",
            "job_join",
            "job_leave",
            "work_submit",
            "movement_out",
            "welfare_ack",
            "staff_request",
            "sanction_issue",
            "sanction_confirm",
            "sanction_reject",
            "appeal_file",
            "appeal_review",
            "out_of_cell",
            "camera_event",
            "daily_clean_days",
            "intake",
            "reentry_item",
            "release_date",
            "outcome",
        ]
        denied = self.report.denied

        def attempted(label: str) -> bool:  # done, or tried and refused by a rule
            return bool(self.report.counts[label]) or any(k.startswith(f"{label}:") for k in denied)

        not_exercised = [r for r in required if not attempted(r)]
        tiers = Counter(get_entitlements(s, r, end, cfg).effective_tier for r in self.residents)
        self.report.summary = {
            "not_exercised": not_exercised,
            "days": self.cfg.days,
            "residents": len(self.residents),
            "audit_entries": s.execute(select(func.count()).select_from(AuditLog)).scalar(),
            "sanctions": dict(Counter(x.status for x in sanc)),
            "appeals": dict(Counter(a.status for a, _ in appeals)),
            "calls": {"monitored": len(monitored), "attorney": len(priv)},
            "ledger": {
                "deposits_cents": s.execute(
                    select(func.coalesce(func.sum(TrustLedger.amount_cents), 0)).where(
                        TrustLedger.entry_type == "deposit"
                    )
                ).scalar(),
                "purchases_cents": -s.execute(
                    select(func.coalesce(func.sum(TrustLedger.amount_cents), 0)).where(
                        TrustLedger.entry_type == "purchase"
                    )
                ).scalar(),
            },
            "final_tiers": {int(k): v for k, v in sorted(tiers.items())},
            "out_of_cell_entries": s.execute(
                select(func.count()).select_from(OutOfCellLog)
            ).scalar(),
            "welfare_flagged_residents": len(welfare.all_flags(s, end)),
        }


def run_simulation(engine: Engine, cfg: SimConfig | None = None) -> Report:
    sim = Simulation(engine, cfg or SimConfig())
    try:
        return sim.run()
    finally:
        sim.s.close()


def write_report(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True))
