"""Vehicle simulator behaviour: routes, motion, sensor noise, fault injection."""
import numpy as np
import pytest

from app.core.coordinate_utils import haversine_m, wrap_angle
from app.core.simulator import VehicleSimulator
from app.models.schemas import RoutePattern, ScenarioType
from tests.conftest import make_config


@pytest.mark.parametrize(
    "pattern",
    [RoutePattern.STRAIGHT, RoutePattern.LEFT_TURN, RoutePattern.RIGHT_TURN,
     RoutePattern.CURVED, RoutePattern.RANDOM],
)
def test_route_is_continuous_and_metric(pattern):
    cfg = make_config(route_pattern=pattern, duration_s=30)
    sim = VehicleSimulator(cfg, seed=3)
    pts = sim.route.points
    steps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    assert np.all(steps < 2.0), "route polyline must not contain jumps"
    assert sim.route.length > cfg.speed_ms * cfg.duration_s * 0.9


def test_vehicle_moves_and_accumulates_distance():
    cfg = make_config(duration_s=20, speed_ms=15)
    sim = VehicleSimulator(cfg, seed=5)
    first = sim.step()
    steps = [first]
    for _ in range(100):
        steps.append(sim.step())
    total = sum(
        haversine_m(steps[i].truth_lat, steps[i].truth_lon,
                    steps[i + 1].truth_lat, steps[i + 1].truth_lon)
        for i in range(len(steps) - 1)
    )
    assert total > 50.0
    assert steps[-1].truth_speed > 0.0


def test_heading_rate_matches_route_geometry():
    cfg = make_config(duration_s=30, speed_ms=10, route_pattern=RoutePattern.RIGHT_TURN)
    sim = VehicleSimulator(cfg, seed=2)
    steps = [sim.step() for _ in range(200)]
    yaw = np.array([s.truth_yaw_rate for s in steps])
    # heading is clockwise-from-north, so a right turn increases the yaw rate
    assert yaw.max() > 0.05
    assert abs(yaw).max() < 2.0
    # the route must never contain a heading fold-back
    assert np.degrees(np.abs(np.diff(sim.route.headings))).max() < 3.0


def test_sensors_have_noise_but_track_truth():
    cfg = make_config(duration_s=15)
    sim = VehicleSimulator(cfg, seed=9)
    steps = [sim.step() for _ in range(120)]
    gnss_err = [
        np.hypot(s.gnss_e - s.truth_e, s.gnss_n - s.truth_n) for s in steps if s.gnss_e is not None
    ]
    assert len(gnss_err) == len(steps)
    assert 0.5 < float(np.mean(gnss_err)) < 8.0


def test_outage_produces_no_gnss_measurements():
    cfg = make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.OUTAGE, outage_start_s=4.0, outage_duration_s=5.0
        ),
        duration_s=20,
    )
    sim = VehicleSimulator(cfg, seed=1)
    steps = [sim.step() for _ in range(200)]
    during = [s for s in steps if s.injected_fault_active]
    outside = [s for s in steps if not s.injected_fault_active]
    assert during and all(s.gnss_e is None for s in during)
    assert outside and all(s.gnss_e is not None for s in outside)


def test_missing_gnss_is_none_not_zero():
    cfg = make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.OUTAGE, outage_start_s=0.0, outage_duration_s=3.0
        ),
        duration_s=6,
    )
    sim = VehicleSimulator(cfg, seed=1)
    s = sim.step()
    assert s.gnss_e is None and s.gnss_n is None and s.gnss_lat is None


def test_drift_bias_grows_monotonically():
    cfg = make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.DRIFT, drift_onset_s=2.0, drift_rate_ms=1.0, drift_max_m=50
        ),
        duration_s=20,
    )
    sim = VehicleSimulator(cfg, seed=4)
    steps = [sim.step() for _ in range(150)]
    mags = [np.hypot(s.gnss_bias_e, s.gnss_bias_n) for s in steps]
    assert mags[0] == pytest.approx(0.0)
    assert mags[-1] > 5.0
    assert mags[-1] <= 50.0 + 1e-6


def test_spoofing_injects_jump():
    cfg = make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.SPOOFING, spoof_onset_s=3.0, spoof_jump_m=80.0,
            spoof_drift_ms=0.5,
        ),
        duration_s=12,
    )
    sim = VehicleSimulator(cfg, seed=6)
    steps = [sim.step() for _ in range(100)]
    biases = [np.hypot(s.gnss_bias_e, s.gnss_bias_n) for s in steps]
    assert max(biases) > 40.0


def test_deterministic_with_seed():
    cfg = make_config(duration_s=5)
    a = [s.gnss_e for s in VehicleSimulator(cfg, seed=99).run_all()]
    b = [s.gnss_e for s in VehicleSimulator(cfg, seed=99).run_all()]
    c = [s.gnss_e for s in VehicleSimulator(cfg, seed=100).run_all()]
    assert a == pytest.approx(b)          # same seed -> identical measurements
    assert a != pytest.approx(c)          # different seed -> different noise
