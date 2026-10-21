from fastapi import FastAPI

from isd.routers import (
    audit,
    auth,
    config,
    device,
    device_extras,
    device_features,
    mock,
    staff_extras,
    staff_ops,
    staff_residents,
    view_as,
)

app = FastAPI(title="ISD v1 API")
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
app.include_router(view_as.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
