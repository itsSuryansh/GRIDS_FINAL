"""Shared pytest fixtures: isolated temp database + deterministic seeds."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use a throw-away SQLite file for the whole test session (set before app import)
_TMP_DIR = tempfile.mkdtemp(prefix="grids-test-")
os.environ["GRIDS_DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"

from app.config import get_settings  # noqa: E402
from app.models.database import Base  # noqa: E402
from app.models.database_setup import engine, init_db  # noqa: E402
from app.models.schemas import (  # noqa: E402
    RoutePattern,
    ScenarioConfig,
    ScenarioType,
    SimulatorConfig,
)


@pytest.fixture(scope="session", autouse=True)
def _database():
    get_settings.cache_clear()
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


def make_config(**overrides) -> SimulatorConfig:
    """Deterministic base configuration for tests."""
    base = dict(
        scenario=ScenarioConfig(scenario=ScenarioType.NORMAL),
        duration_s=20.0,
        rate_hz=10.0,
        speed_ms=12.0,
        route_pattern=RoutePattern.CURVED,
        route_seed=11,
        origin_lat=26.9124,
        origin_lon=75.7873,
        initial_heading_deg=30.0,
        enable_map_matching=True,
    )
    scenario_overrides = overrides.pop("scenario_overrides", None)
    if scenario_overrides:
        base["scenario"] = ScenarioConfig(**{**base["scenario"].model_dump(), **scenario_overrides})
    base.update(overrides)
    return SimulatorConfig(**base)


@pytest.fixture
def config_factory():
    return make_config


@pytest.fixture
def normal_config():
    return make_config()


@pytest.fixture
def outage_config():
    return make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.OUTAGE, outage_start_s=4.0, outage_duration_s=6.0
        )
    )


@pytest.fixture
def spoof_config():
    return make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.SPOOFING, spoof_onset_s=4.0, spoof_jump_m=70.0,
            spoof_drift_ms=1.2,
        )
    )


@pytest.fixture
def drift_config():
    return make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.DRIFT, drift_onset_s=2.0, drift_rate_ms=2.0,
            drift_max_m=150.0,
        )
    )
