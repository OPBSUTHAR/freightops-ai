"""Application entrypoint. Run: uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router, store
from .config import settings
from .seed import ensure_seed

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_seed(store)
    yield
    await store.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        f"Multi-agent freight operations control tower. Built by {settings.developer}. "
        "Planner, executor, reviewer and domain agents over quote, book, track, documents and exceptions."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# On Vercel the console is a separate service and the API must not shadow it.
if FRONTEND_DIST.exists() and not os.getenv("VERCEL"):
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="console")
