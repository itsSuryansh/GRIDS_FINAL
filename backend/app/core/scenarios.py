"""Scenario catalogue: the five ready-to-run fault scenarios and their defaults.

Kept in one place because both the live simulation endpoint and the batch sweep
need the *same* interpretation of a scenario name (e.g. "complex" means a
randomised route with a mid-run outage, not an unfaulted run).
"""
from __future__ import annotations

from typing import Dict, List

from app.models.schemas import ScenarioConfig, ScenarioInfo, ScenarioType

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


def default_config_for(kind: str) -> ScenarioConfig:
    """The catalogue's default fault configuration for one scenario name."""
    for info in SCENARIOS:
        if info.id.value == kind:
            return info.default_config.model_copy(deep=True)
    return ScenarioConfig(scenario=ScenarioType(kind))


def default_route_for(kind: str) -> str:
    """'complex' is defined as a randomised route; everything else follows roads."""
    return "random" if kind == "complex" else "road"
