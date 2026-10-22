"""Check and publish course folders (see docs/courses.md).

  python scripts/courses.py validate [folder ...]   check courses; exit 1 and list every problem
  python scripts/courses.py list                    one line per course
  python scripts/courses.py publish "reason"        save the checked courses as a new config version

With no folder, `validate` checks every course under content/courses and the catalogue as a
whole (prerequisites, a way up for everyone). A course is added by adding a folder; no code changes.
"""

import sys
from pathlib import Path

from isd.config_loader import CONFIG_DIR
from isd.course_format import CourseFormatError
from isd.courses_loader import COURSES_DIR, assemble, load_course_folder, load_courses


def _settings() -> tuple[dict, set[str]]:
    import yaml

    settings = yaml.safe_load((CONFIG_DIR / "courses.yaml").read_text())
    points = yaml.safe_load((CONFIG_DIR / "points.yaml").read_text())
    return settings, set(points["events"])


def validate(folders: list[str]) -> int:
    try:
        if folders:
            for f in folders:
                load_course_folder(Path(f))
            print(f"{len(folders)} course folder(s) are well formed.")
        else:
            settings, kinds = _settings()
            courses = load_courses(COURSES_DIR)
            assemble(settings, courses, kinds)
            print(f"{len(courses)} courses are well formed and fit together.")
    except CourseFormatError as e:
        print(f"{len(e.problems)} problem(s):", file=sys.stderr)
        for p in e.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    return 0


def list_courses() -> int:
    for c in load_courses(COURSES_DIR):
        reqs = ", ".join(c["prerequisites"]) or "none"
        langs = "/".join(c["languages"])
        print(
            f"{c['code']:12} {c['level']:9} {langs:6} {len(c['lessons'])} lessons, "
            f"{len(c['quiz']['bank'])} questions; needs: {reqs}; {c['title']['en']}"
        )
    return 0


def publish(reason: str) -> int:
    from datetime import UTC, datetime  # noqa: F401

    from isd import settings as app_settings
    from isd.services.audit import SYSTEM
    from isd.services.config_store import set_config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    cfg, kinds = _settings()
    try:
        payload = assemble(cfg, load_courses(COURSES_DIR), kinds)
    except CourseFormatError as e:
        print("\n".join(e.problems), file=sys.stderr)
        return 1
    with Session(create_engine(app_settings.MIGRATION_DATABASE_URL)) as s, s.begin():
        row = set_config(s, SYSTEM, "courses", payload, reason)
    print(f"published courses config version {row.version}")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("validate", "list", "publish"):
        print(__doc__)
        return 2
    if argv[0] == "validate":
        return validate(argv[1:])
    if argv[0] == "publish":
        return (
            publish(" ".join(argv[1:]) or "course update")
            if len(argv) > 1
            else _need_reason()
        )
    return list_courses()


def _need_reason() -> int:
    print("publish needs a reason, for the audit log", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
