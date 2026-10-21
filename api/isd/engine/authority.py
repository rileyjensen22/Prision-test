"""Guard-abuse containment rules (CLAUDE.md section 6). Pure decisions; services persist them."""

from dataclasses import dataclass

from isd.engine.config import EngineConfig, InfractionRule

IMMEDIATE_MAX_HOURS = 24
ISSUER_ROLES = ("officer", "supervisor", "system")
CONFIRMER_ROLE = "supervisor"
APPEAL_REVIEWER_ROLE = "supervisor"


class AuthorityError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Evidence:
    type: str  # system_event | second_staff_report
    reporter_id: int | None = None
    ref: str | None = None


@dataclass(frozen=True)
class IssueDecision:
    status: str  # active (applied immediately) | pending (needs supervisor confirmation)
    applied_immediately: bool
    note: str = ""


def needs_supervisor(rule: InfractionRule) -> bool:
    return rule.confirmation != "officer_immediate" or rule.duration_hours > IMMEDIATE_MAX_HOURS


def _check_evidence(rule: InfractionRule, issuer_id: int | None, ev: Evidence | None) -> None:
    if ev is None:
        raise AuthorityError("EVIDENCE_REQUIRED", f"{rule.code} needs evidence")
    if ev.type == "system_event":
        if not ev.ref:
            raise AuthorityError("EVIDENCE_REQUIRED", "system event reference is required")
    elif ev.type == "second_staff_report":
        if rule.confirmation == "system_event_supervisor":
            raise AuthorityError("EVIDENCE_REQUIRED", f"{rule.code} needs a system-detected event")
        if ev.reporter_id is None or ev.reporter_id == issuer_id:
            raise AuthorityError("EVIDENCE_REQUIRED", "report must come from a second staff member")
    else:
        raise AuthorityError("EVIDENCE_REQUIRED", f"unknown evidence type {ev.type!r}")


def decide_issue(
    rule: InfractionRule,
    issuer_role: str,
    issuer_id: int | None,
    evidence: Evidence | None,
    immediate_count_this_week: int,
    cfg: EngineConfig,
) -> IssueDecision:
    if issuer_role not in ISSUER_ROLES:
        raise AuthorityError("ROLE_NOT_PERMITTED", f"{issuer_role} cannot issue sanctions")
    if issuer_role == "system" and (evidence is None or evidence.type != "system_event"):
        raise AuthorityError("EVIDENCE_REQUIRED", "system-issued sanctions need a system event")
    if needs_supervisor(rule):
        _check_evidence(rule, issuer_id, evidence)
        return IssueDecision("pending", False, "supervisor confirmation required")
    if immediate_count_this_week >= cfg.officer_weekly_cap:
        return IssueDecision("pending", False, "weekly immediate-sanction cap reached")
    return IssueDecision("active", True)


def check_confirm(
    status: str, issuer_id: int | None, confirmer_role: str, confirmer_id: int
) -> None:
    if status != "pending":
        raise AuthorityError("NOT_PENDING", "only pending sanctions can be confirmed")
    if confirmer_role != CONFIRMER_ROLE:
        raise AuthorityError("ROLE_NOT_PERMITTED", "only a supervisor can confirm")
    if issuer_id is not None and confirmer_id == issuer_id:
        raise AuthorityError("SAME_PERSON", "issuer and confirmer must be different people")


def check_appeal_review(issuer_id: int | None, reviewer_role: str, reviewer_id: int) -> None:
    if reviewer_role != APPEAL_REVIEWER_ROLE:
        raise AuthorityError("ROLE_NOT_PERMITTED", "only a supervisor can review appeals")
    if issuer_id is not None and reviewer_id == issuer_id:
        raise AuthorityError("SAME_PERSON", "appeal reviewer cannot be the issuer")
