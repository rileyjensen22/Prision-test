"""Reads course folders from disk and checks them (see isd/course_format.py and docs/courses.md)."""

import json
from pathlib import Path

from isd.course_format import CourseFormatError, build_course, validate_course_set

COURSES_DIR = Path(__file__).resolve().parents[2] / "content" / "courses"


def _read_json(path: Path, problems: list[str]) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append(f"{path.parent.name}: missing {path.name}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        problems.append(f"{path.parent.name}/{path.name}: not valid JSON ({e})")
    else:
        if isinstance(data, dict):
            return data
        problems.append(f"{path.parent.name}/{path.name}: must hold a JSON object")
    return {}


def load_course_folder(folder: Path) -> dict:
    """One course, or CourseFormatError listing everything wrong with it."""
    problems: list[str] = []
    manifest = _read_json(folder / "course.json", problems)
    quiz = _read_json(folder / "quiz.json", problems)
    files = {}
    lessons_dir = folder / "lessons"
    if lessons_dir.is_dir():
        for f in sorted(lessons_dir.iterdir()):
            if f.is_file():
                try:
                    files[f"lessons/{f.name}"] = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    problems.append(f"{folder.name}/lessons/{f.name}: not UTF-8 text")
    else:
        problems.append(f"{folder.name}: missing lessons folder")
    if manifest and manifest.get("code") != folder.name:
        problems.append(f"{folder.name}: the folder name must match the code in course.json")
    if not manifest:
        raise CourseFormatError(problems or [f"{folder.name}: empty course.json"])
    try:
        # build even when a file was missing, so the author sees every problem at once
        course = build_course(manifest, files, quiz, folder.name)
    except CourseFormatError as e:
        problems = [*problems, *[p for p in e.problems if p not in problems]]
        raise CourseFormatError(problems) from e
    if problems:
        raise CourseFormatError(problems)
    return course


def load_courses(root: Path = COURSES_DIR) -> list[dict]:
    """Every course under `root`, or CourseFormatError with all the problems found."""
    folders = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    courses: list[dict] = []
    problems: list[str] = []
    for folder in folders:
        try:
            courses.append(load_course_folder(folder))
        except CourseFormatError as e:
            problems += e.problems
    if problems:
        raise CourseFormatError(problems)
    return courses


def assemble(
    settings: dict, courses: list[dict], known_point_kinds: set[str] | None = None
) -> dict:
    """The `courses` config section: shared settings plus every course. Validated."""
    payload = {**settings, "courses": courses}
    check = {**settings, "known_point_kinds": known_point_kinds} if known_point_kinds else settings
    validate_course_set(courses, check)
    return payload
