"""Release countdown, checklist state and validation of the reentry config. Pure functions."""

import re
from datetime import date

CHECKLIST_STATUSES = ("todo", "in_progress", "done", "not_needed")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
_SYNTHETIC_PHONE = re.compile(r"^555-01\d\d$")
_RESOURCE_KEYS = {"code", "category", "title", "description", "phone", "languages"}


def countdown(release: date | None, today: date) -> dict | None:
    """Days left to the release date; never negative, and None when no date is set."""
    if release is None:
        return None
    days = max(0, (release - today).days)
    return {"release_date": release.isoformat(), "days_left": days, "weeks_left": days // 7}


def latest_statuses(events: list[tuple[str, str]], items: list[dict]) -> dict[str, str]:
    """`events` are (item_code, status) oldest first; the last one for an item wins."""
    out = {i["code"]: "todo" for i in items}
    for code, status in events:
        if code in out and status in CHECKLIST_STATUSES:
            out[code] = status
    return out


def checklist_progress(statuses: dict[str, str]) -> dict[str, int]:
    values = list(statuses.values())
    return {
        "done": values.count("done"),
        "resolved": values.count("done") + values.count("not_needed"),
        "total": len(values),
    }


def _bilingual(value: object, where: str) -> None:
    if not (isinstance(value, dict) and value.get("en") and value.get("es")):
        raise ValueError(f"{where} needs english and spanish text")


def validate_reentry(payload: dict, course_codes: set[str] | None = None) -> None:
    checklist = payload.get("checklist") or []
    if not checklist:
        raise ValueError("reentry checklist cannot be empty")
    seen: set[str] = set()
    for item in checklist:
        code = item.get("code", "")
        if not _CODE.match(code):
            raise ValueError(f"bad checklist code: {code!r}")
        if code in seen:
            raise ValueError(f"duplicate checklist code: {code}")
        seen.add(code)
        _bilingual(item.get("title"), f"checklist {code} title")
        _bilingual(item.get("detail"), f"checklist {code} detail")
    for course in payload.get("courses") or []:
        if course_codes is not None and course not in course_codes:
            raise ValueError(f"reentry course {course} is not a known course")
    resource_codes: set[str] = set()
    for res in payload.get("resources") or []:
        if set(res) != _RESOURCE_KEYS:
            raise ValueError(f"resource {res.get('code')!r} needs exactly {sorted(_RESOURCE_KEYS)}")
        if res["code"] in resource_codes:
            raise ValueError(f"duplicate resource code: {res['code']}")
        resource_codes.add(res["code"])
        _bilingual(res["title"], f"resource {res['code']} title")
        _bilingual(res["description"], f"resource {res['code']} description")
        if not _SYNTHETIC_PHONE.match(res["phone"]):
            raise ValueError(f"resource {res['code']} phone must be a synthetic 555-01xx number")
