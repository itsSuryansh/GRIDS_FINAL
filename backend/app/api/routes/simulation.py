"""Simulation lifecycle + scenario catalogue endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    ScenarioConfig,
    ScenarioInfo,
    ScenarioType,
    SimulatorConfig,
    SimulationState,
    StartResponse,
    RoutePattern,
)
from app.services.simulation_service import simulation_service

router = APIRouter(prefix="/simulation", tags=["simulation"])


SCENARIOS: List[ScenarioInfo] = [
    ScenarioInfo(
        id=ScenarioType.NORMAL,
        name="Normal navigation",
        description="GNSS available for the whole run with realistic noise; "
                    "EKF, dead reckoning and GNSS all track ground truth.",
        expected="All estimators follow the reference trajectory with small error; "
                 "EKF should be smoother than raw GNSS.",
        default_config=ScenarioConfig(scenario=ScenarioType.NORMAL),
    ),
    ScenarioInfo(
        id=ScenarioType.OUTAGE,
        name="GNSS outage",
        description="GNSS fixes stop completely for a configurable interval. "
                    "The EKF keeps predicting from IMU/odometry only.",
        expected="Dead reckoning and the EKF continue moving; position error grows "
                 "with sensor noise and biases, then recovers after GNSS returns.",
        default_config=ScenarioConfig(
            scenario=ScenarioType.OUTAGE, outage_start_s=20.0, outage_duration_s=30.0
        ),
    ),
    ScenarioInfo(
        id=ScenarioType.DRIFT,
        name="GNSS drift",
        description="GNSS errors accumulate slowly and persistently (multipath / "
                    "aiding-failure style), never producing a single large jump.",
        expected="The anomaly detector flags persistent residuals and the EKF "
                 "down-weights or rejects untrustworthy fixes.",
        default_config=ScenarioConfig(
            scenario=ScenarioType.DRIFT, drift_onset_s=15.0, drift_rate_ms=0.6,
            drift_max_m=120.0,
        ),
    ),
    ScenarioInfo(
        id=ScenarioType.SPOOFING,
        name="GNSS spoofing",
        description="A sudden coordinated position jump plus a continuous false "
                    "movement that is inconsistent with IMU/odometry.",
        expected="Jump/velocity/heading checks fire; the spoofed fixes are rejected "
                 "and the EKF coasts on inertial data instead of following the spoof.",
        default_config=ScenarioConfig(
            scenario=ScenarioType.SPOOFING, spoof_onset_s=18.0, spoof_jump_m=60.0,
            spoof_drift_ms=0.8, spoof_heading_bias_deg=25.0,
        ),
    ),
    ScenarioInfo(
        id=ScenarioType.COMPLEX,
        name="Complex movement",
        description="Randomised route with straights, accelerations, braking and "
                    "continuous turns plus a mid-run outage.",
        expected="All estimators survive high yaw-rate manoeuvres; EKF bounds the "
                 "dead-reckoning drift during the outage.",
        default_config=ScenarioConfig(
            scenario=ScenarioType.OUTAGE, outage_start_s=25.0, outage_duration_s=20.0
        ),
    ),
]


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
