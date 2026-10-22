from collections.abc import Iterator

from fastapi.routing import APIRoute


def iter_api_routes(app) -> Iterator[APIRoute]:
    """Every real route, including those inside included routers (which FastAPI wraps lazily)."""
    for r in app.routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from iter_api_routes(r.original_router)


def operations(app) -> set[tuple[str, str]]:
    """(METHOD, path) for every route found by iter_api_routes."""
    return {
        (m, r.path) for r in iter_api_routes(app) for m in r.methods if m not in ("HEAD", "OPTIONS")
    }


def documented_operations(app) -> set[tuple[str, str]]:
    """(METHOD, path) according to the OpenAPI document, an independent source of the same list."""
    return {
        (m.upper(), path)
        for path, item in app.openapi()["paths"].items()
        for m in item
        if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE")
    }


def quiz_answers(session, paper_id: int, code: str, *, correct: bool = True) -> list[int]:
    """The displayed choice numbers that are right (or all wrong) for a drawn quiz paper."""
    from isd.models import QuizSession
    from isd.services import education

    paper = session.get(QuizSession, paper_id)
    bank = {q["id"]: q for q in education._course(session, code)["quiz"]["bank"]}
    out = []
    for q in paper.questions:
        right = q["order"].index(bank[q["id"]]["answer"])
        out.append(right if correct else (right + 1) % len(q["order"]))
    return out


def take_quiz(session, resident_id: int, code: str, now, *, correct: bool = True, rng=None):
    """Starts a paper and hands it in. Returns the result of submit_quiz."""
    from isd.services import education

    paper = education.start_quiz(session, resident_id, code, now, rng)
    answers = quiz_answers(session, paper["quiz_id"], code, correct=correct)
    return education.submit_quiz(session, resident_id, code, paper["quiz_id"], answers, now)
