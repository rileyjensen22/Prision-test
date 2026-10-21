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
