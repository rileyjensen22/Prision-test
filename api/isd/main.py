from fastapi import FastAPI

from isd.routers import audit, auth, config, device, staff_residents

app = FastAPI(title="ISD v1 API")
app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(config.router)
app.include_router(device.router)
app.include_router(staff_residents.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
