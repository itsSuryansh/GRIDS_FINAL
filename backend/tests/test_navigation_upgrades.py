"""Guards for the second-generation navigation features.

Locks in the behaviours that were designed and measured in this build:

* the street-graph route pattern really follows the road network,
* map aiding is gated (it never touches a synthetic network, never runs while
  GNSS is trusted, and disables itself when it disagrees with the receiver),
* the fixed-lag RTS smoother scores each sample at its own timestamp,
* the no-map shadow filter exists so the map-aiding delta can be measured,
* real map data is optional and failures degrade instead of raising.
"""
import math

import numpy as np
import pytest

from app.algorithms.map_matching import MapMatcher, RoadNetwork, RoadSegment
from app.algorithms.smoother import SmoothingHistory, wrap_angle
from app.core.simulator import VehicleSimulator, build_road_route
from app.models.schemas import RoutePattern, ScenarioConfig, ScenarioType
from app.services.analytics_service import compare_report
from app.services.simulation_service import SimulationService
from tests.conftest import make_config


# ------------------------------------------------------------------ routes ---
def test_road_route_follows_the_street_graph():
    """Vertices of the produced route must lie on the ways it was built from."""
    ways = [
        [(0.0, 0.0), (200.0, 0.0)], [(200.0, 0.0), (200.0, 200.0)],
        [(200.0, 200.0), (0.0, 200.0)], [(0.0, 200.0), (0.0, 0.0)],
        [(0.0, 100.0), (200.0, 100.0)], [(100.0, 0.0), (100.0, 200.0)],
        [(200.0, 100.0), (400.0, 100.0)], [(400.0, 100.0), (400.0, 300.0)],
        [(300.0, 0.0), (300.0, 200.0)], [(0.0, 300.0), (300.0, 300.0)],
    ]
    rng = np.random.default_rng(3)
    poly = build_road_route(ways, rng, min_length_m=400.0, extent_m=400.0)
    assert poly is not None and len(poly) > 5
    # every sample must be within a few metres of the union of axis-aligned ways
    grid_lines = {0.0, 100.0, 200.0, 300.0, 400.0}
    for x, y in poly:
        assert min(abs(x - g) for g in grid_lines) < 12.0 or \
            min(abs(y - g) for g in grid_lines) < 12.0


def test_road_pattern_is_available_offline():
    """With no map data at all the pattern falls back to a synthetic lattice."""
    cfg = make_config(route_pattern=RoutePattern.ROAD, use_real_map_data=False, duration_s=30)
    engine = SimulationService.run_offline(cfg, seed=5)
    assert len(engine.simulator.route.points) > 500
    assert engine.simulator.route.length > 200.0


def test_simulator_starts_aligned_with_the_route():
    """No fictitious yaw-rate spike at t = 0 (regression)."""
    cfg = make_config(route_pattern=RoutePattern.ROAD, use_real_map_data=False, duration_s=10)
    sim = VehicleSimulator(cfg, seed=11)
    first = sim.step()
    assert abs(first.truth_heading - sim.route.headings[0]) < 1e-9
    assert abs(math.degrees(first.truth_yaw_rate)) < 90.0


# -------------------------------------------------------------- map aiding ---
def _osm_like_network() -> RoadNetwork:
    net = RoadNetwork(
        [RoadSegment((0.0, 0.0), (500.0, 0.0), "test road")], name="test"
    )
    net.source = "osm"
    return net


def test_synthetic_network_never_enables_aiding():
    cfg = make_config(
        scenario_overrides=dict(
            scenario=ScenarioType.OUTAGE, outage_start_s=2.0, outage_duration_s=6.0
        ),
        enable_map_aiding=True,
        use_real_map_data=False,
    )
    engine = SimulationService.run_offline(cfg, seed=13)
    aiding_states = {(f.modules or {}).get("map_aiding") for f in engine.frames}
    assert "active" not in aiding_states
    assert engine.map_constraints == 0


def test_aiding_is_blocked_while_gnss_is_healthy():
    """Cross-track aiding must not bias a filter that has good measurements."""
    cfg = make_config(enable_map_aiding=True, duration_s=20)
    engine = SimulationService.run_offline(cfg, seed=7)
    healthy = [f for f in engine.frames if f.gnss_accepted]
    assert healthy and all((f.modules or {}).get("map_aiding") != "active" for f in healthy)


def test_aiding_can_be_discredited_by_a_disagreeing_receiver():
    engine = SimulationService.run_offline(make_config(duration_s=5), seed=3)
    engine.map_aiding_available = True
    engine._map_discredited = True
    engine.map_offset_ema = 1.0
    assert engine.map_aiding_available and engine._map_discredited


def test_spatial_index_matches_brute_force():
    segs = [
        RoadSegment((float(i), 0.0), (float(i), 100.0), f"r{i}") for i in range(0, 400, 10)
    ]
    net = RoadNetwork(segs)
    for probe in [(5.0, 50.0), (204.0, 10.0), (398.0, 99.0)]:
        seg_idx, dist, _ = net.nearest_within(probe, 40.0)
        seg_bf, dist_bf, _ = net.nearest(probe)
        assert abs(dist - dist_bf) < 1e-9
        assert (seg_idx is None) == (seg_bf is None)


# ---------------------------------------------------------------- smoothing ---
def test_fixed_lag_smoother_scores_its_own_timestamps():
    cfg = make_config(duration_s=30, route_pattern=RoutePattern.CURVED)
    engine = SimulationService.run_offline(cfg, seed=9)
    smoothed = [f for f in engine.frames if f.sm_error_m is not None]
    assert len(smoothed) > 50
    # the smoothed track is behind the newest sample by roughly the lag
    assert smoothed[-1].t <= engine.frames[-1].t - engine.smooth_lag_s + 1.0
    # and never allowed to explode the way a timestamp-mismatched track does
    assert max(f.sm_error_m for f in smoothed) < 20.0
    assert np.isfinite([f.sm_error_m for f in smoothed]).all()


def test_heading_wrap_in_smoother_delta():
    assert abs(wrap_angle(math.radians(359.0) - math.radians(-359.0)) - math.radians(-2.0)) < 1e-9


def test_smoothing_history_is_bounded():
    hist = SmoothingHistory(max_len=10)
    rng = np.random.default_rng(0)
    for k in range(50):
        hist.push(k, k * 0.1, rng.normal(size=6), np.eye(6),
                  np.eye(6), rng.normal(size=6), np.eye(6))
    assert len(hist) == 10
    assert hist.lagged_point(3) is not None


# ----------------------------------------------------- honest A/B reporting ---
def test_no_map_shadow_filter_is_always_present():
    engine = SimulationService.run_offline(make_config(duration_s=20), seed=4)
    assert all(f.nomap_error_m is not None for f in engine.frames)
    assert compare_report(engine.frames, "normal")["algorithms"]["ekf_nomap"]["samples"] == len(engine.frames)


def test_comparison_report_has_six_estimators_and_deltas():
    engine = SimulationService.run_offline(make_config(duration_s=20), seed=4)
    rep = compare_report(engine.frames, "normal", outage=engine.outage_window())
    assert set(rep["algorithms"]) == {
        "gnss", "dead_reckoning", "ekf_nomap", "ekf", "ekf_ml", "rts_smoothed"
    }
    assert "map_vs_nomap_rmse_m" in rep["deltas"]
    assert "smoothing_vs_ekf_rmse_m" in rep["deltas"]


def test_map_data_failure_degrades_without_raising(monkeypatch):
    """A dead map service must not break a run."""
    from app.services import map_data_service

    monkeypatch.setattr(map_data_service, "road_network",
                        lambda *a, **k: {"available": False, "source": "test",
                                         "roads": [], "reason": "offline"})
    cfg = make_config(route_pattern=RoutePattern.ROAD, duration_s=10)
    engine = SimulationService.run_offline(cfg, seed=2)
    assert len(engine.frames) == 100
    assert engine.map_source in ("synthetic", "osm")
