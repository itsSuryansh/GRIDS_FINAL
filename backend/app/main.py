"""GRIDS backend entrypoint (FastAPI).

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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

# ---------------------------------------------------------------------------
# Dashboard hosting.
#
# The API is the canonical port, so if a production bundle has been built
# (`npm run build` -> frontend/dist) it is served from here as well: one origin,
# no proxy required, relative /api calls keep working. During development the
# Vite dev server on :5173 proxies /api to this process instead.
# ---------------------------------------------------------------------------
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_INDEX = _DIST / "index.html"

@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    """Serve the built single-page app (falls back to a hint if not built)."""
    if _INDEX.is_file():
        return FileResponse(_INDEX)
    return JSONResponse(
        status_code=404,
        content={
            "error": "dashboard bundle not found",
            "build": "cd frontend && npm run build",
            "dev_server": "http://localhost:5173",
        },
    )


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "name": settings.app_name,
        "full_name": settings.app_full_name,
        "version": settings.version,
        "docs": "/docs",
        "api": settings.api_prefix,
        "dashboard": "/dashboard" if _INDEX.is_file() else None,
        "data_source": "simulated",
    }


# Registered last on purpose: a mount on "/" is matched in definition order, so
# it must come after every API, docs and page route. html=False keeps unknown
# paths a plain 404 instead of silently answering with the SPA shell.
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=False), name="dashboard-assets")
