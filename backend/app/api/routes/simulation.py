"""Simulation lifecycle + scenario catalogue endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    RoutePattern,
    ScenarioInfo,
    ScenarioType,
    SimulationState,
    SimulatorConfig,
    StartResponse,
)
from app.core.scenarios import SCENARIOS
from app.services.simulation_service import simulation_service

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/scenarios", response_model=List[ScenarioInfo])
def list_scenarios() -> List[ScenarioInfo]:
    """Ready-to-run scenarios with their default configuration."""
    return SCENARIOS


@router.get("/patterns")
def list_patterns() -> dict:
    """Available vehicle movement patterns."""
    return {
        "patterns": [p.value for p in RoutePattern],
        "default": RoutePattern.ROAD.value,
        "recommended": [RoutePattern.ROAD.value, RoutePattern.CURVED.value,
                        RoutePattern.RANDOM.value],
        "description": "Movement patterns available to the vehicle simulator. "
                       "'road' follows the street network (OpenStreetMap when "
                       "reachable, a synthetic lattice otherwise).",
    }


@router.get("/status")
def status() -> dict:
    """Current simulation state, kept consistent with the backend loop."""
    return simulation_service.status()


@router.post("/start", response_model=StartResponse)
async def start(config: Optional[SimulatorConfig] = None, seed: Optional[int] = Query(None, ge=0)) -> StartResponse:
    """Start a new simulation run with the supplied configuration."""
    cfg = config or SimulatorConfig()
    if cfg.scenario.scenario == ScenarioType.COMPLEX:
        cfg.route_pattern = RoutePattern.RANDOM
    try:
        run = await simulation_service.start(cfg, seed=seed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"could not start simulation: {exc}") from exc
    return StartResponse(
        ok=True,
        run_id=run.run_id,
        session_id=run.session_id,
        state=run.state,
        message=run.message,
    )


@router.post("/pause")
async def pause() -> dict:
    st = await simulation_service.pause()
    if st["state"] != SimulationState.PAUSED.value:
        raise HTTPException(status_code=409, detail=f"cannot pause in state '{st['state']}'")
    return {"ok": True, "status": st}


@router.post("/resume")
async def resume() -> dict:
    st = await simulation_service.resume()
    if st["state"] != SimulationState.RUNNING.value:
        raise HTTPException(status_code=409, detail=f"cannot resume in state '{st['state']}'")
    return {"ok": True, "status": st}


@router.post("/stop")
async def stop() -> dict:
    st = await simulation_service.stop()
    return {"ok": True, "status": st}


@router.post("/reset")
async def reset() -> dict:
    st = await simulation_service.reset()
    return {"ok": True, "status": st}
