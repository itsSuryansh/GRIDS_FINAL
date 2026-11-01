"""Batch runs: execute several simulation scenarios back to back and score them.

The dashboard drives one live vehicle. This module is the other half: a
*headless sweep* that steps the same `NavigationEngine` through a list of
scenarios (optionally repeated with different seeds), scores every run with the
same ground-truth comparison the UI uses, and returns two views of the result:

* `runs`   - one row per completed run, for diagnosis
* `byKind` - aggregated per scenario, for a fair "which fault is hardest" table

Everything runs on the event loop in small yielded chunks so the API stays
responsive while a sweep is in flight, and the whole sweep is cancellable.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict, List, Optional

import numpy as np

from app.core.scenarios import default_config_for, default_route_for
from app.core.state_manager import StateManager
from app.models.schemas import SimulatorConfig
from app.services.analytics_service import compare_report
from app.utils.logging import get_logger

log = get_logger("grids.batch")

# Guard rails: a sweep is CPU work on the request's event loop, so cap it.
MAX_RUNS = 40
MAX_DURATION_S = 300.0
MIN_DURATION_S = 5.0

_ALGOS = ("gnss", "dead_reckoning", "ekf_nomap", "ekf", "rts_smoothed", "ekf_ml")


class BatchBusy(RuntimeError):
    """Raised when a sweep is already running."""


class BatchService:
    """Owns at most one active sweep."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._cancel = False
        self._state: Dict[str, object] = self._idle()

    # ------------------------------------------------------------- helpers ---
    @staticmethod
    def _idle() -> Dict[str, object]:
        return {
            "batch_id": None,
            "state": "idle",          # idle | running | completed | cancelled | error
            "total": 0,
            "completed": 0,
            "current": None,
            "started_at": None,
            "finished_at": None,
            "runs": [],
            "byKind": {},
            "error": None,
        }

    @property
    def busy(self) -> bool:
        return self._state["state"] == "running"

    def status(self) -> Dict[str, object]:
        st = dict(self._state)
        st["runs"] = list(self._state.get("runs") or [])
        total = st.get("total") or 0
        done = st.get("completed") or 0
        st["progress"] = round(done / total, 4) if total else 0.0
        return st

    # ------------------------------------------------------------- control ---
    async def cancel(self) -> Dict[str, object]:
        if self.busy:
            self._cancel = True
            self._state["state"] = "cancelled"
        return self.status()

    async def start(
        self,
        scenarios: List[str],
        durations: Optional[List[float]] = None,
        seeds: Optional[List[int]] = None,
        rate_hz: float = 10.0,
        base_config: Optional[SimulatorConfig] = None,
        label_by_kind: bool = True,
    ) -> Dict[str, object]:
        if self.busy:
            raise BatchBusy("a batch is already running")

        kinds = [s.strip() for s in scenarios if s and s.strip()]
        if not kinds:
            raise ValueError("at least one scenario is required")

        durations = durations or [60.0]
        seeds = seeds or [42]

        # Build the run list: every (scenario, seed) pair, durations cycling.
        plan: List[Dict[str, object]] = []
        i = 0
        for kind in kinds:
            for seed in seeds:
                if len(plan) >= MAX_RUNS:
                    break
                plan.append(
                    {
                        "scenario": kind,
                        "seed": int(seed),
                        "duration_s": float(min(MAX_DURATION_S, max(MIN_DURATION_S, durations[i % len(durations)]))),
                    }
                )
                i += 1

        self._cancel = False
        self._state = self._idle()
        self._state.update(
            {
                "batch_id": uuid.uuid4().hex[:10],
                "state": "running",
                "total": len(plan),
                "started_at": time.time(),
            }
        )
        self._task = asyncio.create_task(
            self._run_plan(plan, rate_hz, base_config, label_by_kind)
        )
        log.info("batch started id=%s runs=%d", self._state["batch_id"], len(plan))
        return self.status()

    # ---------------------------------------------------------------- loop ---
    async def _run_plan(
        self,
        plan: List[Dict[str, object]],
        rate_hz: float,
        base_config: Optional[SimulatorConfig],
        label_by_kind: bool,
    ) -> None:
        runs: List[Dict[str, object]] = []
        try:
            for item in plan:
                if self._cancel:
                    break
                self._state["current"] = {
                    "scenario": item["scenario"],
                    "seed": item["seed"],
                    "duration_s": item["duration_s"],
                }
                row = await self._run_one(
                    str(item["scenario"]), int(item["seed"]), float(item["duration_s"]),
                    rate_hz, base_config,
                )
                runs.append(row)
                self._state["runs"] = runs
                self._state["completed"] = len(runs)
                self._state["byKind"] = _aggregate(runs, label_by_kind)
                await asyncio.sleep(0)          # let the API breathe

            if self._cancel:
                self._state["state"] = "cancelled"
            else:
                self._state["state"] = "completed"
                self._state["current"] = None
            self._state["finished_at"] = time.time()
            log.info(
                "batch %s %s (%d/%d runs)",
                self._state["batch_id"], self._state["state"],
                self._state["completed"], self._state["total"],
            )
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            self._state["state"] = "cancelled"
            raise
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("batch failed: %s", exc)
            self._state["state"] = "error"
            self._state["error"] = str(exc)
        finally:
            self._state["finished_at"] = self._state["finished_at"] or time.time()
            self._task = None

    async def _run_one(
        self,
        scenario: str,
        seed: int,
        duration_s: float,
        rate_hz: float,
        base_config: Optional[SimulatorConfig],
    ) -> Dict[str, object]:
        """Step one scenario headlessly and score it."""
        base = base_config.model_dump() if base_config is not None else SimulatorConfig().model_dump()
        base["duration_s"] = duration_s
        base["rate_hz"] = rate_hz
        base["route_pattern"] = default_route_for(scenario)
        # Each scenario carries its own fault parameters from the catalogue, so a
        # sweep compares the scenarios as the UI defines them -- not a shared
        # fault config that would silently make e.g. "spoofing" identical to
        # "normal".
        base["scenario"] = default_config_for(scenario).model_dump()
        cfg = SimulatorConfig.model_validate(base)

        # A private registry keeps batch runs out of the live/active run slot and
        # out of the dashboard's history.
        registry = StateManager(max_runs=1)
        run = registry.create_run(cfg, seed=seed)
        engine = run.engine

        n_steps = max(1, int(round(duration_s * rate_hz)))
        dt = 1.0 / rate_hz
        started = time.perf_counter()
        for step in range(n_steps):
            if self._cancel:
                break
            engine.step()
            run.steps = step + 1
            # yield every ~40 steps: keeps the loop responsive without the
            # overhead of an await per step (a 60 s run at 10 Hz is 600 steps)
            if step % 40 == 0:
                await asyncio.sleep(0)
        wall = time.perf_counter() - started

        report = compare_report(
            engine.frames,
            scenario=scenario,
            session_id=None,
            run_id=run.run_id,
            outage=engine.outage_window(),
        )
        metrics = {
            a: {
                "rmse_m": round(float(report["algorithms"][a]["rmse_m"]), 3),
                "p95_m": round(float(report["algorithms"][a]["p95_m"]), 3),
                "samples": int(report["algorithms"][a]["samples"]),
            }
            for a in _ALGOS
            if a in report["algorithms"]
        }
        return {
            "run_id": run.run_id,
            "scenario": scenario,
            "seed": seed,
            "duration_s": duration_s,
            "frames": len(engine.frames),
            "wall_s": round(wall, 2),
            "metrics": metrics,
            "deltas": report.get("deltas", {}),
            "availability_pct": report.get("availability_pct"),
            "anomalies": report.get("anomalies", {}),
            "recovery": report.get("recovery"),
        }


def _aggregate(runs: List[Dict[str, object]], label_by_kind: bool) -> Dict[str, object]:
    """Mean of each estimator per scenario, plus the spread across seeds."""
    if not runs:
        return {}
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in runs:
        grouped.setdefault(str(row["scenario"]), []).append(row)

    out: Dict[str, object] = {}
    for scenario, rows in grouped.items():
        entry: Dict[str, object] = {
            "scenario": scenario,
            "label": _label(scenario) if label_by_kind else scenario,
            "runs": len(rows),
            "seeds": [r["seed"] for r in rows],
            "duration_s": rows[0]["duration_s"],
            "availability_pct": _mean([r.get("availability_pct") for r in rows]),
            "anomalies": _mean([(r.get("anomalies") or {}).get("detected") for r in rows]),
            "estimators": {},
        }
        for algo in _ALGOS:
            values = [
                (r["metrics"].get(algo) or {}).get("rmse_m")
                for r in rows
            ]
            values = [v for v in values if v is not None]
            if not values:
                continue
            entry["estimators"][algo] = {
                "rmse_m": round(float(np.mean(values)), 3),
                "rmse_std_m": round(float(np.std(values)), 3) if len(values) > 1 else None,
                "samples": min(
                    (r["metrics"].get(algo) or {}).get("samples", 0) for r in rows
                ),
            }
        ekf = (entry["estimators"].get("ekf") or {}).get("rmse_m")
        gnss = (entry["estimators"].get("gnss") or {}).get("rmse_m")
        if ekf is not None and gnss:
            entry["ekf_vs_gnss_pct"] = round((gnss - ekf) / gnss * 100, 1)
        out[scenario] = entry
    return out


def _mean(values: List[object]) -> Optional[float]:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    return round(sum(nums) / len(nums), 3) if nums else None


_LABELS = {
    "normal": "Normal navigation",
    "outage": "GNSS outage",
    "drift": "GNSS drift",
    "spoofing": "GNSS spoofing",
    "complex": "Complex movement",
}


def _label(scenario: str) -> str:
    return _LABELS.get(scenario, scenario)


batch_service = BatchService()
