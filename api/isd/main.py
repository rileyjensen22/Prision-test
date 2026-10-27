from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from isd import limits, settings
from isd.logging_config import RequestLog, configure_logging
from isd.middleware import BodyLimit, SecurityHeaders
from isd.routers import (
    audit,
    auth,
    config,
    device,
    device_extras,
    device_features,
    mock,
    staff_accounts,
    staff_chess,
    staff_comms,
    staff_extras,
    staff_fleet,
    staff_floor,
    staff_intake,
    staff_lifecycle,
    staff_ops,
    staff_outcomes,
    staff_residents,
    view_as,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = settings.validate_for_env()
    if problems:  # refuse to run production with development defaults
        raise RuntimeError("unsafe production settings: " + "; ".join(problems))
    yield


configure_logging()
app = FastAPI(title="ISD v1 API", lifespan=lifespan, dependencies=[Depends(limits.ip_limit)])
app.add_middleware(BodyLimit, max_bytes=settings.MAX_BODY_BYTES)
app.add_middleware(SecurityHeaders)  # wraps the body limit, so 413s get the headers too
# Added last, so it is outermost and logs every response, including 413s.
app.add_middleware(RequestLog)
app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(config.router)
app.include_router(device.router)
app.include_router(device_features.router)
app.include_router(device_extras.router)
app.include_router(staff_residents.router)
app.include_router(mock.router)
app.include_router(staff_ops.router)
app.include_router(staff_extras.router)
app.include_router(staff_floor.router)
app.include_router(staff_comms.router)
app.include_router(view_as.router)
app.include_router(staff_fleet.router)
app.include_router(staff_intake.router)
app.include_router(staff_accounts.router)
app.include_router(staff_chess.router)
app.include_router(staff_lifecycle.router)
app.include_router(staff_outcomes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
