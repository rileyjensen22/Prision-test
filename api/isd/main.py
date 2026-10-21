from fastapi import FastAPI

app = FastAPI(title="ISD v1 API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
