"""Navigation data endpoints (current frame, history, route, map match)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.simulation_service import simulation_service

router = APIRouter(prefix="/navigation", tags=["navigation"])


@router.get("/current")
def current() -> dict:
    """Latest synchronised navigation frame (all values backend-computed)."""
    run = simulation_service.run
    if run is None or not run.engine.frames:
        return {"available": False, "frame": None, "message": "no simulation data"}
    frame = run.engine.frames[-1]
    return {
        "available": True,
        "run_id": run.run_id,
        "session_id": run.session_id,
        "state": run.state.value,
        "frame": frame.to_api(),
        "summary": __import__(
            "app.services.analytics_service", fromlist=["live_summary"]
        ).live_summary(run.engine.frames[-300:]),
    }


@router.get("/history")
def history(limit: int = Query(600, ge=1, le=5000), stride: int = Query(1, ge=1, le=200)) -> dict:
    """Down-sampled history of the active (or most recent) run."""
    run = simulation_service.run
    if run is None or not run.engine.frames:
        return {"run_id": None, "count": 0, "samples": []}
    frames = run.engine.frames[::stride]
    frames = frames[-limit:]
    return {
        "run_id": run.run_id,
        "count": len(frames),
        "samples": [f.to_api() for f in frames],
    }


@router.get("/route")
def route() -> dict:
    """Planned route polyline (lat/lon) plus origin for map display."""
    run = simulation_service.run
    if run is None:
        raise HTTPException(status_code=404, detail="no simulation has been started")
    cfg = run.config
    engine = run.engine
    return {
        "origin": {"lat": cfg.origin_lat, "lon": cfg.origin_lon},
        "map_source": engine.map_source,
        "osm": engine.osm_info,
        "route": run.engine.route_geodetic(),
        "outage_window": run.engine.outage_window(),
        "duration_s": cfg.duration_s,
        "rate_hz": cfg.rate_hz,
    }


@router.get("/anomalies")
def anomalies(limit: int = Query(200, ge=1, le=2000)) -> dict:
    """Discrete anomaly events detected in the active run."""
    run = simulation_service.run
    if run is None:
        return {"run_id": None, "count": 0, "events": []}
    events = run.engine.anomaly_events
    return {"run_id": run.run_id, "count": len(events), "events": events[-limit:]}


@router.get("/modules")
def modules() -> dict:
    """Operational status of every navigation module."""
    run = simulation_service.run
    if run is None or not run.engine.frames:
        return {"modules": {}, "available": False}
    f = run.engine.frames[-1]
    return {"available": True, "modules": f.modules, "map_match": f.map_match}
