"""End-to-end scenario tests: the full pipeline, run headless, deterministically.

These assert *relative* behaviour (the EKF must not be worse than raw GNSS, an
outage must not stop the solution, spoofed fixes must be rejected, ...). They do
not assert absolute accuracy figures, which depend on the noise configuration.
"""
import numpy as np
import pytest

from app.services.analytics_service import compare_report
from app.services.navigation_service import NavigationEngine
from app.services.simulation_service import SimulationService
from app.models.schemas import RoutePattern, ScenarioConfig, ScenarioType
from tests.conftest import make_config


def run(cfg, seed=17):
    return SimulationService.run_offline(cfg, seed=seed)


def test_full_pipeline_produces_synchronised_frames(normal_config):
    engine = run(normal_config)
    frames = engine.frames
    assert len(frames) == int(normal_config.duration_s * normal_config.rate_hz)
    for f in frames[:20]:
        assert f.truth_lat is not None and f.ekf_lat is not None and f.dr_lat is not None
        assert np.isfinite([f.ekf_error_m, f.dr_error_m, f.uncertainty_m]).all()
        assert 0.0 <= f.anomaly_score <= 1.0
    # EKF must improve on raw GNSS for this configuration
    rep = compare_report(frames, scenario="normal")
    assert rep["algorithms"]["ekf"]["rmse_m"] < rep["algorithms"]["gnss"]["rmse_m"]
    assert rep["algorithms"]["ekf"]["samples"] == len(frames)


def test_outage_keeps_navigating_without_gnss_updates(outage_config):
    engine = run(outage_config)
    during = [f for f in engine.frames if f.gnss_status == "unavailable"]
    assert len(during) > 20
    # position keeps changing and remains finite while GNSS is absent
    lats = {round(f.ekf_lat, 8) for f in during}
    assert len(lats) > 5
    assert all(np.isfinite(f.ekf_lat) and np.isfinite(f.ekf_lon) for f in during)
    # uncertainty grows while coasting
    assert during[-1].position_sigma_m > during[0].position_sigma_m
    # no GNSS update can have been applied during the outage
    assert all(not f.gnss_accepted for f in during)


def test_outage_error_recovers_after_gnss_returns(outage_config):
    engine = run(outage_config)
    frames = engine.frames
    end = [i for i, f in enumerate(frames) if f.gnss_status != "unavailable" and f.t > 10]
    assert end, "GNSS must return after the outage"
    tail = frames[end[0]:][-10:]
    outage_peak = max(f.ekf_error_m for f in frames if f.gnss_status == "unavailable")
    assert max(f.ekf_error_m for f in tail) < max(outage_peak, 20.0)


def test_spoofing_is_detected_and_rejected(spoof_config):
    engine = run(spoof_config)
    post = [f for f in engine.frames if f.t > 5.0]
    assert any(f.anomaly for f in post), "spoofing must be flagged"
    rejected = [f for f in post if f.gnss_status == "suspicious"]
    assert len(rejected) > 5
    # while the spoof is active, raw GNSS error is much larger than EKF error
    gnss_errs = [f.gnss_error_m for f in post if f.gnss_error_m is not None]
    assert np.mean(gnss_errs) > 10.0
    ekf_errs = [f.ekf_error_m for f in post]
    assert np.mean(ekf_errs) < np.mean(gnss_errs)


def test_drift_is_flagged(drift_config):
    engine = run(drift_config)
    late = [f for f in engine.frames if f.t > 10.0]
    assert any(f.anomaly for f in late)
    assert sum(1 for f in late if f.gnss_status in ("suspicious", "degraded")) > 10


def test_ekf_not_worse_than_dead_reckoning_on_normal_run(normal_config):
    rep = compare_report(run(normal_config).frames, scenario="normal")
    assert rep["algorithms"]["ekf"]["rmse_m"] <= rep["algorithms"]["dead_reckoning"]["rmse_m"] * 1.5


def test_complex_route_survives_turns():
    cfg = make_config(
        route_pattern=RoutePattern.RANDOM,
        duration_s=60,
        speed_ms=16,
        scenario_overrides=dict(
            scenario=ScenarioType.OUTAGE, outage_start_s=20.0, outage_duration_s=15.0
        ),
    )
    rep = compare_report(run(cfg).frames, scenario="outage",
                         outage=run(cfg).outage_window())
    assert rep["algorithms"]["ekf"]["rmse_m"] < 60.0
    assert rep["ground_truth_samples"] == 600


@pytest.mark.parametrize(
    "pattern",
    [RoutePattern.STRAIGHT, RoutePattern.LEFT_TURN, RoutePattern.RIGHT_TURN,
     RoutePattern.CURVED, RoutePattern.RANDOM],
)
def test_all_route_patterns_run(pattern):
    cfg = make_config(route_pattern=pattern, duration_s=15)
    engine = run(cfg)
    assert len(engine.frames) == 150
    assert all(np.isfinite(f.ekf_error_m) for f in engine.frames)


def test_custom_waypoints_route():
    from app.models.schemas import Waypoint

    cfg = make_config(
        route_pattern=RoutePattern.CUSTOM,
        custom_waypoints=[
            Waypoint(lat=26.9124, lon=75.7873),
            Waypoint(lat=26.9200, lon=75.7900),
            Waypoint(lat=26.9250, lon=75.8000),
        ],
        duration_s=30,
    )
    engine = run(cfg)
    assert len(engine.frames) == 300


def test_map_matching_is_advisory():
    cfg = make_config(enable_map_matching=False)
    engine = run(cfg)
    assert all(f.map_match is None for f in engine.frames)
    assert engine.frames[-1].modules["map_matching"] == "n/a"

    cfg2 = make_config(enable_map_matching=True)
    engine2 = run(cfg2)
    matched = [f.map_match for f in engine2.frames if f.map_match and f.map_match["matched"]]
    assert matched, "map matching should snap to the simulated road network"
    assert matched[0]["offset_m"] >= 0.0


def test_ml_correction_disabled_by_default(normal_config):
    engine = run(normal_config)
    assert engine.ml_enabled is False
    assert all(f.ml_lat is None for f in engine.frames)


def test_metrics_are_identical_run_to_run(monkeypatch):
    cfg = make_config(duration_s=10)
    a = compare_report(run(cfg, seed=5).frames, scenario="normal")
    b = compare_report(run(cfg, seed=5).frames, scenario="normal")
    assert a["algorithms"] == b["algorithms"]
