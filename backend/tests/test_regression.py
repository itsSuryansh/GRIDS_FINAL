"""Regression guards for behaviours that were explicitly designed and measured.

These lock in the *policy* decisions documented in the README so a future change
cannot silently flip them (e.g. the ML layer becoming enabled by default without
evidence, or the detector rejecting healthy fixes).
"""
import numpy as np

from app.ml.inference import get_model
from app.models.schemas import RoutePattern, ScenarioConfig, ScenarioType
from app.services.analytics_service import compare_report
from app.services.simulation_service import SimulationService
from tests.conftest import make_config


def test_ml_layer_is_opt_in_only():
    """The ML layer is never active unless the operator explicitly enables it."""
    default_cfg = make_config(duration_s=10)
    assert default_cfg.enable_ml_correction is False
    engine = SimulationService.run_offline(default_cfg, seed=3)
    assert engine.ml_enabled is False
    assert all(f.ml_lat is None for f in engine.frames)

    # an explicit opt-in is honoured, but only if a trained model exists
    model = get_model()
    cfg = make_config(enable_ml_correction=True, duration_s=10)
    engine2 = SimulationService.run_offline(cfg, seed=3)
    assert engine2.ml_enabled is model.available


def test_ml_evaluation_report_is_honest():
    """If the report exists it must contain a measured baseline vs corrected pair."""
    report = get_model().report or {}
    if not report:
        return
    assert {"baseline_ekf", "corrected", "test_samples", "recommended_default"} <= set(report)
    delta = report["baseline_ekf"]["rmse_m"] - report["corrected"]["rmse_m"]
    assert abs(delta - report["rmse_improvement_m"]) < 0.02
    # the recommendation must follow the measured sign, not an assumption
    assert report["recommended_default"] == (report["rmse_improvement_m"] > 0.05)


def test_normal_run_has_zero_rejected_fixes():
    cfg = make_config(duration_s=60)
    engine = SimulationService.run_offline(cfg, seed=21)
    assert engine.frames[-1].rejected_count == 0
    assert sum(1 for f in engine.frames if f.gnss_status == "suspicious") <= 2


def test_ekf_beats_raw_gnss_and_covariance_stays_finite():
    cfg = make_config(duration_s=60)
    engine = SimulationService.run_offline(cfg, seed=21)
    rep = compare_report(engine.frames, scenario="normal")
    assert rep["algorithms"]["ekf"]["rmse_m"] < rep["algorithms"]["gnss"]["rmse_m"]
    for f in engine.frames:
        assert np.isfinite(f.uncertainty_m) and f.uncertainty_m < 1e4


def test_outage_frames_have_no_gnss_coordinates():
    cfg = make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.OUTAGE, outage_start_s=5.0, outage_duration_s=5.0
        ),
        duration_s=20,
    )
    engine = SimulationService.run_offline(cfg, seed=8)
    during = [f for f in engine.frames if f.gnss_status == "unavailable"]
    assert during
    assert all(f.gnss_lat is None and f.gnss_lon is None for f in during)


def test_drift_correction_is_suspended_when_gnss_is_untrusted():
    cfg = make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.OUTAGE, outage_start_s=3.0, outage_duration_s=6.0
        ),
        duration_s=15,
    )
    engine = SimulationService.run_offline(cfg, seed=4)
    during = [f for f in engine.frames if f.gnss_status == "unavailable"]
    assert all("suspended" in f.modules["drift_correction"] for f in during)


def test_reported_metrics_are_reproducible_across_runs():
    """Same config + seed must give byte-identical metric blocks."""
    cfg = make_config(duration_s=30, route_pattern=RoutePattern.RANDOM)
    a = compare_report(SimulationService.run_offline(cfg, seed=99).frames, scenario="x")
    b = compare_report(SimulationService.run_offline(cfg, seed=99).frames, scenario="x")
    assert a["algorithms"] == b["algorithms"]
    assert a["anomalies"] == b["anomalies"]
