"""GRIDS backend entrypoint (FastAPI).

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.models.database_setup import init_db
from app.utils.logging import get_logger

log = get_logger("grids.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    log.info("%s backend ready (db=%s)", settings.app_name, settings.database_url)
    yield
    log.info("shutting down")


app = FastAPI(
    title=f"{settings.app_name} API",
    description=(
        f"{settings.app_full_name}\n\n"
        "Resilient positioning research platform: vehicle simulation, dead "
        "reckoning, EKF sensor fusion, GNSS anomaly detection, drift monitoring "
        "and map matching.\n\n"
        "**All data is simulated.** Simulated accuracy does not establish "
        "real-world performance."
    ),
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "name": settings.app_name,
        "full_name": settings.app_full_name,
        "version": settings.version,
        "docs": "/docs",
        "api": settings.api_prefix,
        "data_source": "simulated",
    }
