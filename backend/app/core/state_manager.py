"""In-memory registry of simulation runs.

Only one *active* run exists at a time (the dashboard drives one vehicle), but
finished runs stay in the registry until they are evicted, which makes the
comparison view and the API independent of the database writer.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.schemas import SimulationState, SimulatorConfig
from app.services.navigation_service import EngineFrame, NavigationEngine


@dataclass
class SimulationRun:
    run_id: str
    engine: NavigationEngine
    config: SimulatorConfig
    session_id: Optional[int] = None
    state: SimulationState = SimulationState.IDLE
    created_wall: float = field(default_factory=time.time)
    started_wall: Optional[float] = None
    message: str = ""
    steps: int = 0
    frames: List[EngineFrame] = field(default_factory=list)  # capped ring view
    version: int = 0

    def reset(self) -> None:
        self.steps = 0
        self.frames = []
        self.state = SimulationState.IDLE
        self.message = ""
        self.version += 1


class StateManager:
    """Thread-safe registry + latest-frame broadcasting state."""

    def __init__(self, max_runs: int = 12, max_live_frames: int = 4000) -> None:
        self._lock = threading.RLock()
        self._runs: Dict[str, SimulationRun] = {}
        self._order: List[str] = []
        self._active_run_id: Optional[str] = None
        self.max_runs = max_runs
        self.max_live_frames = max_live_frames
        self.connected_clients = 0
        self.started_at = time.time()

    # -------------------------------------------------------------- runs ---
    def create_run(self, config: SimulatorConfig, seed: Optional[int] = None) -> SimulationRun:
        engine = NavigationEngine(config, seed=seed)
        run = SimulationRun(run_id=uuid.uuid4().hex[:12], engine=engine, config=config)
        with self._lock:
            self._runs[run.run_id] = run
            self._order.append(run.run_id)
            while len(self._order) > self.max_runs:
                old = self._order.pop(0)
                if old != self._active_run_id:
                    self._runs.pop(old, None)
            self._active_run_id = run.run_id
        return run

    def get(self, run_id: str) -> Optional[SimulationRun]:
        with self._lock:
            return self._runs.get(run_id)

    @property
    def active_run(self) -> Optional[SimulationRun]:
        with self._lock:
            if self._active_run_id is None:
                return None
            return self._runs.get(self._active_run_id)

    def clear_active(self) -> None:
        with self._lock:
            self._active_run_id = None

    def append_frame(self, run: SimulationRun, frame: EngineFrame) -> None:
        with self._lock:
            run.steps = frame.step
            run.frames.append(frame)
            if len(run.frames) > self.max_live_frames:
                del run.frames[0 : len(run.frames) - self.max_live_frames]
            run.version += 1

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for r in self._runs.values() if r.state == SimulationState.RUNNING
            )


state_manager = StateManager()
