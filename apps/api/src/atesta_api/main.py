"""FastAPI entry point."""

from fastapi import FastAPI

app = FastAPI(title="Atesta API", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
