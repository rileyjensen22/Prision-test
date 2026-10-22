from contextlib import asynccontextmanager

from fastapi import FastAPI

from isd import settings
from isd.middleware import BodyLimit, SecurityHeaders
from isd.routers import (
    audit,
    auth,
    config,
    device,
    device_extras,
    device_features,
    mock,
    staff_comms,
    staff_extras,
    staff_ops,
    staff_residents,
    view_as,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = settings.validate_for_env()
    if problems:  # refuse to run production with development defaults
        raise RuntimeError("unsafe production settings: " + "; ".join(problems))
    yield


app = FastAPI(title="ISD v1 API", lifespan=lifespan)
app.add_middleware(BodyLimit, max_bytes=settings.MAX_BODY_BYTES)
app.add_middleware(SecurityHeaders)  # added last, so it wraps everything (including 413s)
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
app.include_router(staff_comms.router)
app.include_router(view_as.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
