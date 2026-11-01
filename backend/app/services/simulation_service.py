"""Simulation orchestration + realtime broadcast + persistence.

* one asyncio task drives a single active run, so reconnecting WebSockets can
  never spawn a second loop (the loop is owned by the service, not the socket)
* frames are streamed to clients via a connection manager
* high-frequency data is buffered and flushed to SQLite in batches
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional, Set

import numpy as np
from fastapi import WebSocket

from app.config import settings
from app.core.state_manager import SimulationRun, state_manager
from app.models.database import (
    AnomalyEvent,
    NavigationResult,
    PerformanceMetric,
    SimulationSession,
)
from app.models.database_setup import session_scope
from app.models.schemas import SimulationState, SimulatorConfig
from app.services.analytics_service import compare_report, live_summary
from app.services.navigation_service import EngineFrame, NavigationEngine
from app.utils.logging import get_logger

log = get_logger("grids.sim")


class ConnectionManager:
    """Tracks live WebSocket clients and broadcasts simulation frames."""

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
            state_manager.connected_clients = len(self._clients)
        log.info("websocket connected (%d clients)", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
            state_manager.connected_clients = len(self._clients)

    @property
    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, message: dict) -> None:
        if not self._clients:
            return
        dead: List[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
                state_manager.connected_clients = len(self._clients)


manager = ConnectionManager()


class SimulationService:
    """Owns the single active run and its asyncio driver task."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._run: Optional[SimulationRun] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()          # set == running
        self._stop_flag = False
        self._step_lock = asyncio.Lock()
        self._flush_buffer: List[EngineFrame] = []
        self._batch_index = 0
        self._reported = False

    # ------------------------------------------------------------- lifecycle ---
    @property
    def run(self) -> Optional[SimulationRun]:
        return self._run

    def status(self) -> dict:
        run = self._run
        if run is None:
            return {
                "state": SimulationState.IDLE.value,
                "session_id": None,
                "run_id": None,
                "config": None,
                "step": 0,
                "sim_time": 0.0,
                "duration_s": 0.0,
                "progress": 0.0,
                "finished": False,
                "message": "No simulation has been started yet",
            }
        frames = run.engine.frames
        sim_time = frames[-1].t if frames else 0.0
        dur = run.config.duration_s
        return {
            "state": run.state.value,
            "session_id": run.session_id,
            "run_id": run.run_id,
            "config": run.config.model_dump(mode="json"),
            "step": run.steps,
            "sim_time": round(sim_time, 3),
            "duration_s": dur,
            "progress": round(min(1.0, sim_time / dur), 4) if dur else 0.0,
            "finished": run.state in (SimulationState.COMPLETED, SimulationState.STOPPED),
            "message": run.message,
        }

    async def start(self, config: SimulatorConfig, seed: Optional[int] = None) -> SimulationRun:
        async with self._step_lock:
            await self._halt_task()
            run = state_manager.create_run(config, seed=seed)
            self._run = run
            self._pause_event.set()
            self._stop_flag = False
            self._flush_buffer = []
            self._batch_index = 0
            self._reported = False

            session_id = await asyncio.to_thread(self._create_session, run)
            run.session_id = session_id
            run.state = SimulationState.RUNNING
            run.started_wall = time.time()
            run.message = f"Running scenario '{config.scenario.scenario.value}'"

        self._task = asyncio.create_task(self._loop(run))
        await manager.broadcast({"type": "state_change", "data": self.status()})
        log.info("simulation started run=%s session=%s", run.run_id, run.session_id)
        return run

    async def pause(self) -> dict:
        if self._run and self._run.state == SimulationState.RUNNING:
            self._pause_event.clear()
            self._run.state = SimulationState.PAUSED
            self._run.message = "Paused"
            await manager.broadcast({"type": "state_change", "data": self.status()})
        return self.status()

    async def resume(self) -> dict:
        if self._run and self._run.state == SimulationState.PAUSED:
            self._pause_event.set()
            self._run.state = SimulationState.RUNNING
            self._run.message = "Resumed"
            await manager.broadcast({"type": "state_change", "data": self.status()})
        return self.status()

    async def stop(self) -> dict:
        """Stop the loop, keep everything produced so far, compute the report."""
        if self._run is None:
            return self.status()
        self._stop_flag = True
        self._pause_event.set()  # unblock a paused loop so it can exit
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._task = None
        if self._run.state not in (SimulationState.COMPLETED,):
            self._run.state = SimulationState.STOPPED
            self._run.message = "Stopped by operator"
        await self._finalise(self._run)
        await manager.broadcast({"type": "state_change", "data": self.status()})
        return self.status()

    async def reset(self) -> dict:
        await self._halt_task()
        self._run = None
        self._flush_buffer = []
        self._batch_index = 0
        state_manager.clear_active()
        await manager.broadcast({"type": "state_change", "data": self.status()})
        return self.status()

    async def _halt_task(self) -> None:
        if self._task is not None:
            self._stop_flag = True
            self._pause_event.set()
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # ------------------------------------------------------------------ loop ---
    async def _loop(self, run: SimulationRun) -> None:
        engine = run.engine
        n_steps = int(round(run.config.duration_s * run.config.rate_hz))
        dt = 1.0 / run.config.rate_hz
        try:
            for _ in range(n_steps):
                if self._stop_flag:
                    break
                await self._pause_event.wait()
                if self._stop_flag:
                    break

                t_start = time.perf_counter()
                frame = engine.step()
                state_manager.append_frame(run, frame)
                self._flush_buffer.append(frame)

                await manager.broadcast(
                    {
                        "type": "navigation_update",
                        "data": frame.to_api(),
                        "status": {
                            "state": run.state.value,
                            "step": run.steps,
                            "sim_time": round(frame.t, 3),
                            "progress": round(min(1.0, frame.t / run.config.duration_s), 4),
                            "session_id": run.session_id,
                            "run_id": run.run_id,
                        },
                        "summary": live_summary(engine.frames[-200:]),
                    }
                )

                if len(self._flush_buffer) >= settings.result_flush_rows:
                    await self._flush(run)

                elapsed = time.perf_counter() - t_start
                await asyncio.sleep(max(0.0, dt - elapsed))

            if not self._stop_flag:
                run.state = SimulationState.COMPLETED
                run.message = "Simulation complete"
            await self._flush(run)
            await self._finalise(run)
            await manager.broadcast({"type": "state_change", "data": self.status()})
            if run.state == SimulationState.COMPLETED:
                report = compare_report(
                    engine.frames,
                    scenario=run.config.scenario.scenario.value,
                    session_id=run.session_id,
                    run_id=run.run_id,
                    outage=engine.outage_window(),
                )
                await manager.broadcast(
                    {"type": "simulation_complete", "data": report}
                )
        except asyncio.CancelledError:
            log.info("simulation task cancelled run=%s", run.run_id)
            raise
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("simulation loop error: %s", exc)
            run.state = SimulationState.STOPPED
            run.message = f"Error: {exc}"
            await manager.broadcast({"type": "error", "data": {"message": str(exc)}})

    # ----------------------------------------------------------- persistence ---
    def _create_session(self, run: SimulationRun) -> Optional[int]:
        try:
            with session_scope() as db:
                sess = SimulationSession(
                    name=f"{run.config.scenario.scenario.value} / {run.config.route_pattern.value}",
                    run_id=run.run_id,
                    scenario=run.config.scenario.scenario.value,
                    route_pattern=run.config.route_pattern.value,
                    config_json=run.config.model_dump_json(),
                    origin_lat=run.config.origin_lat,
                    origin_lon=run.config.origin_lon,
                    duration_s=run.config.duration_s,
                    status="running",
                )
                db.add(sess)
                db.flush()
                return int(sess.id)
        except Exception as exc:  # pragma: no cover
            log.error("failed to create session: %s", exc)
            return None

    FRAME_COLUMNS = (
        "t", "truth_lat", "truth_lon", "gnss_lat", "gnss_lon",
        "dr_lat", "dr_lon", "ekf_lat", "ekf_lon", "ml_lat", "ml_lon",
        "ekf_e", "ekf_n", "dr_e", "dr_n", "truth_e", "truth_n",
        "speed", "heading_deg", "gnss_status", "anomaly", "anomaly_score",
        "ekf_error_m", "dr_error_m", "gnss_error_m", "ml_error_m",
        "drift_estimate_m", "uncertainty_m", "gnss_residual_m",
    )

    async def _flush(self, run: SimulationRun) -> None:
        if not self._flush_buffer or run.session_id is None:
            self._flush_buffer = []
            return
        batch = self._flush_buffer
        self._flush_buffer = []
        await asyncio.to_thread(self._write_batch, run.session_id, batch, self._batch_index)
        self._batch_index += 1

    def _write_batch(self, session_id: int, batch: List[EngineFrame], index: int) -> None:
        try:
            cols: Dict[str, list] = {c: [] for c in self.FRAME_COLUMNS}
            for f in batch:
                for c in self.FRAME_COLUMNS:
                    v = getattr(f, c)
                    cols[c].append(v)
            with session_scope() as db:
                db.add(
                    NavigationResult(
                        session_id=session_id,
                        batch_index=index,
                        sample_count=len(batch),
                        t_start=batch[0].t,
                        t_end=batch[-1].t,
                        payload=json.dumps(cols, separators=(",", ":")),
                    )
                )
        except Exception as exc:  # pragma: no cover
            log.error("batch write failed: %s", exc)

    async def _finalise(self, run: SimulationRun) -> None:
        if self._reported or run.session_id is None:
            return
        self._reported = True
        report = compare_report(
            run.engine.frames,
            scenario=run.config.scenario.scenario.value,
            session_id=run.session_id,
            run_id=run.run_id,
            outage=run.engine.outage_window(),
        )
        events = run.engine.anomaly_events
        await asyncio.to_thread(self._persist_report, run, report, events)

    def _persist_report(self, run: SimulationRun, report: dict, events: List[dict]) -> None:
        try:
            with session_scope() as db:
                sess = db.get(SimulationSession, run.session_id)
                if sess is None:
                    return
                sess.status = run.state.value
                sess.steps = run.steps
                sess.sim_time_s = run.engine.frames[-1].t if run.engine.frames else 0.0
                sess.notes = (report.get("notes") or [""])[-1][:400]
                for algo, m in report["algorithms"].items():
                    db.add(
                        PerformanceMetric(
                            session_id=run.session_id,
                            algorithm=algo,
                            mae_m=m["mae_m"],
                            rmse_m=m["rmse_m"],
                            max_m=m["max_m"],
                            p95_m=m["p95_m"],
                            mean_m=m["mean_m"],
                            samples=m["samples"],
                            extras_json=json.dumps(
                                {
                                    "outage": report.get("outage"),
                                    "recovery": report.get("recovery"),
                                }
                            ),
                        )
                    )
                # keep anomaly rows bounded: at most 400 per session
                for ev in events[:400]:
                    db.add(
                        AnomalyEvent(
                            session_id=run.session_id,
                            t=ev["t"],
                            timestamp=ev["timestamp"],
                            anomaly_type=ev["anomaly_type"],
                            score=ev["score"],
                            reason=ev["reason"][:240],
                            residual_m=ev["residual_m"],
                            rejected=1 if ev["rejected"] else 0,
                        )
                    )
            log.info("session %s finalised (%d frames)", run.session_id, len(run.engine.frames))
        except Exception as exc:  # pragma: no cover
            log.error("finalise failed: %s", exc)

    # -------------------------------------------------------------- offline ---
    @staticmethod
    def run_offline(config: SimulatorConfig, seed: Optional[int] = None) -> NavigationEngine:
        """Headless full simulation (tests, CLI, ML dataset generation)."""
        engine = NavigationEngine(config, seed=seed)
        n_steps = int(round(config.duration_s * config.rate_hz))
        for _ in range(n_steps):
            engine.step()
        return engine

    @staticmethod
    def persist_offline(engine: NavigationEngine, config: SimulatorConfig,
                        name: Optional[str] = None) -> Optional[int]:
        """Run -> database without a live socket (used by the CLI)."""
        svc = SimulationService()
        run = SimulationRun(
            run_id=uuid.uuid4().hex[:12],
            engine=engine,
            config=config,
            state=SimulationState.COMPLETED,
            steps=len(engine.frames),
        )
        run.session_id = svc._create_session(run)
        if run.session_id is None:
            return None
        # batch write all frames
        buf: List[EngineFrame] = []
        idx = 0
        for f in engine.frames:
            buf.append(f)
            if len(buf) >= settings.result_flush_rows:
                svc._write_batch(run.session_id, buf, idx)
                idx += 1
                buf = []
        if buf:
            svc._write_batch(run.session_id, buf, idx)
        report = compare_report(
            engine.frames,
            scenario=config.scenario.scenario.value,
            session_id=run.session_id,
            run_id=run.run_id,
            outage=engine.outage_window(),
        )
        svc._persist_report(run, report, engine.anomaly_events)
        return run.session_id


simulation_service = SimulationService()
