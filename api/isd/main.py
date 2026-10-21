from fastapi import FastAPI

from isd.routers import audit, auth, config, device, device_features, mock, staff_residents

app = FastAPI(title="ISD v1 API")
app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(config.router)
app.include_router(device.router)
app.include_router(device_features.router)
app.include_router(staff_residents.router)
app.include_router(mock.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
