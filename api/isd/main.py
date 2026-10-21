from fastapi import FastAPI

from isd.routers import audit, auth, config

app = FastAPI(title="ISD v1 API")
app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(config.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
