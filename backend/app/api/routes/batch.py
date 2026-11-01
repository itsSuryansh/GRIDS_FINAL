"""Batch simulation endpoints: run several scenarios and compare them."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.schemas import ScenarioType
from app.services.batch_service import MAX_DURATION_S, MAX_RUNS, BatchBusy, batch_service

router = APIRouter(prefix="/batch", tags=["batch"])


class BatchRequest(BaseModel):
    scenarios: List[ScenarioType] = Field(
        default_factory=lambda: list(ScenarioType),
        description="Scenarios to run, in order. Defaults to all five.",
    )
    durations_s: List[float] = Field(
        default=[60.0],
        description="Run durations; cycled across scenarios. Each is clamped to "
                    f"5..{int(MAX_DURATION_S)} s.",
    )
    seeds: List[int] = Field(
        default=[42],
        description="Seeds to repeat each scenario with (mean ± spread is reported).",
    )
    rate_hz: float = Field(default=10.0, ge=1.0, le=50.0)
    label_by_kind: bool = True


@router.get("/status")
def status() -> dict:
    """Progress and results of the current or last sweep."""
    return batch_service.status()


@router.post("/cancel")
async def cancel() -> dict:
    """Ask the running sweep to stop after the run in flight."""
    return await batch_service.cancel()


@router.post("/run")
async def run_batch(req: Optional[BatchRequest] = None) -> dict:
    """Run several scenarios back to back and return the comparison table.

    This is a headless sweep: it never touches the live simulation, so the
    dashboard keeps streaming while a batch runs. Poll `/batch/status` for
    progress, or `/batch/run` with a small plan and read the result directly.
    """
    req = req or BatchRequest()
    combos = len({(s, seed) for s in req.scenarios for seed in req.seeds})
    if combos > MAX_RUNS:
        raise HTTPException(
            status_code=422,
            detail=f"{combos} runs requested; the cap is {MAX_RUNS} "
                   f"(reduce scenarios, seeds or split the sweep).",
        )
    try:
        return await batch_service.start(
            scenarios=[s.value for s in req.scenarios],
            durations=req.durations_s,
            seeds=req.seeds,
            rate_hz=req.rate_hz,
            label_by_kind=req.label_by_kind,
        )
    except BatchBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
