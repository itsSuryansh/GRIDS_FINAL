"""Pydantic schemas: request validation + API response models."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ScenarioType(str, Enum):
    NORMAL = "normal"
    OUTAGE = "outage"
    DRIFT = "drift"
    SPOOFING = "spoofing"
    COMPLEX = "complex"


class RoutePattern(str, Enum):
    STRAIGHT = "straight"
    LEFT_TURN = "left_turn"
    RIGHT_TURN = "right_turn"
    CURVED = "curved"
    RANDOM = "random"
    CUSTOM = "custom"


class GnssStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    SUSPICIOUS = "suspicious"


class SimulationState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class Waypoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class NoiseConfig(BaseModel):
    """1-sigma sensor noise levels."""

    gnss_position_sigma_m: float = Field(2.5, ge=0.0, le=100.0)
    speed_sigma_ms: float = Field(0.08, ge=0.0, le=20.0)
    heading_sigma_deg: float = Field(0.35, ge=0.0, le=90.0)
    accel_sigma_ms2: float = Field(0.06, ge=0.0, le=10.0)
    gyro_sigma_dps: float = Field(0.12, ge=0.0, le=50.0)


class ScenarioConfig(BaseModel):
    """How GNSS behaves during the run."""

    scenario: ScenarioType = ScenarioType.NORMAL
    outage_start_s: float = Field(20.0, ge=0.0, le=3600.0)
    outage_duration_s: float = Field(30.0, ge=0.0, le=3600.0)
    drift_onset_s: float = Field(15.0, ge=0.0, le=3600.0)
    drift_rate_ms: float = Field(0.6, ge=0.0, le=50.0)  # m/s of accumulated bias
    drift_max_m: float = Field(120.0, ge=0.0, le=5000.0)
    spoof_onset_s: float = Field(18.0, ge=0.0, le=3600.0)
    spoof_jump_m: float = Field(60.0, ge=0.0, le=5000.0)
    spoof_drift_ms: float = Field(0.8, ge=0.0, le=50.0)
    spoof_heading_bias_deg: float = Field(25.0, ge=-180.0, le=180.0)

    @model_validator(mode="after")
    def _check(self) -> "ScenarioConfig":
        if self.scenario == ScenarioType.OUTAGE and self.outage_duration_s <= 0:
            raise ValueError("outage_duration_s must be > 0 for the outage scenario")
        return self


class SimulatorConfig(BaseModel):
    """Full simulation configuration sent by the dashboard."""

    scenario: ScenarioConfig = Field(default_factory=ScenarioConfig)
    noise: NoiseConfig = Field(default_factory=NoiseConfig)

    duration_s: float = Field(120.0, ge=1.0, le=1800.0)
    rate_hz: float = Field(10.0, ge=1.0, le=50.0)
    speed_ms: float = Field(12.0, ge=0.0, le=80.0)  # ~43 km/h
    route_pattern: RoutePattern = RoutePattern.CURVED
    route_seed: Optional[int] = Field(7, ge=0, le=10_000_000)
    custom_waypoints: Optional[List[Waypoint]] = None

    origin_lat: float = Field(26.9124, ge=-90, le=90)   # default: Jaipur
    origin_lon: float = Field(75.7873, ge=-180, le=180)

    initial_heading_deg: float = Field(0.0, ge=-360.0, le=360.0)
    accel_bias_ms2: float = Field(0.035, ge=-2.0, le=2.0)   # true IMU accel bias
    gyro_bias_dps: float = Field(0.09, ge=-20.0, le=20.0)   # true IMU gyro bias

    enable_map_matching: bool = True
    enable_ml_correction: bool = False

    @field_validator("custom_waypoints")
    @classmethod
    def _wp(cls, v: Optional[List[Waypoint]], info):
        return v

    @model_validator(mode="after")
    def _validate(self) -> "SimulatorConfig":
        if self.route_pattern == RoutePattern.CUSTOM:
            if not self.custom_waypoints or len(self.custom_waypoints) < 2:
                raise ValueError(
                    "route_pattern='custom' requires at least 2 custom_waypoints"
                )
        return self


# ---------------------------------------------------------------- responses ---
class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    uptime_s: float
    active_simulations: int


class NavigationSample(BaseModel):
    """One synchronised navigation output frame (all quantities backend-derived)."""

    t: float
    timestamp: float
    # geodetic
    truth_lat: float
    truth_lon: float
    gnss_lat: Optional[float] = None
    gnss_lon: Optional[float] = None
    dr_lat: float
    dr_lon: float
    ekf_lat: float
    ekf_lon: float
    ml_lat: Optional[float] = None
    ml_lon: Optional[float] = None

    # vehicle truth state
    speed_ms: float
    heading_deg: float
    accel_ms2: float
    yaw_rate_dps: float

    # GNSS channel
    gnss_status: GnssStatus
    gnss_available: bool
    gnss_residual_m: Optional[float] = None
    gnss_accepted: bool = False
    rejected_count: int = 0

    # anomaly channel
    anomaly: bool
    anomaly_score: float
    anomaly_reason: Optional[str] = None
    nis: Optional[float] = None

    # error / drift
    ekf_error_m: float
    dr_error_m: float
    gnss_error_m: Optional[float] = None
    drift_estimate_m: float
    uncertainty_m: float  # sqrt(trace(P[0:2,0:2])) - NOT a probability radius
    position_sigma_m: float  # 1-sigma radial from covariance

    # module health
    modules: Dict[str, str]
    map_match: Optional[Dict[str, object]] = None


class SimulationStatus(BaseModel):
    state: SimulationState
    session_id: Optional[int] = None
    run_id: Optional[str] = None
    config: Optional[SimulatorConfig] = None
    step: int = 0
    sim_time: float = 0.0
    duration_s: float = 0.0
    progress: float = 0.0
    finished: bool = False
    message: Optional[str] = None


class StartResponse(BaseModel):
    ok: bool
    run_id: str
    session_id: Optional[int]
    state: SimulationState
    message: str


class ScenarioInfo(BaseModel):
    id: ScenarioType
    name: str
    description: str
    expected: str
    default_config: ScenarioConfig


class SessionSummary(BaseModel):
    id: int
    name: str
    scenario: str
    route_pattern: str
    created_at: str
    duration_s: float
    status: str
    notes: Optional[str] = None
    metrics: Optional[Dict[str, Dict[str, float]]] = None


class HistoryResponse(BaseModel):
    run_id: Optional[str]
    count: int
    samples: List[NavigationSample]


class AnomalyEventOut(BaseModel):
    t: float
    timestamp: float
    anomaly_type: str
    score: float
    reason: str
    residual_m: float
    rejected: bool


class MetricsBlock(BaseModel):
    mae_m: float
    rmse_m: float
    max_m: float
    p95_m: float
    mean_m: float
    samples: int


class CompareResponse(BaseModel):
    session_id: Optional[int]
    run_id: Optional[str]
    scenario: str
    ground_truth_samples: int
    algorithms: Dict[str, MetricsBlock]
    outage: Dict[str, Optional[float]]
    anomalies: Dict[str, int]
    recovery: Optional[Dict[str, float]] = None
    notes: List[str] = Field(default_factory=list)
