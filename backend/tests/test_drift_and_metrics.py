"""Drift monitoring/correction, map matching and metric maths."""
import numpy as np
import pytest

from app.algorithms.drift_correction import DriftCorrector, DriftMonitor
from app.algorithms.map_matching import MapMatcher, RoadNetwork, RoadSegment
from app.utils.metrics import cep95, error_stats, outage_recovery_metrics


# ------------------------------------------------------------------ drift ---
def test_drift_monitor_tracks_separation_and_rate():
    mon = DriftMonitor(window=10)
    for i in range(40):
        mon.record(
            t=i * 0.1,
            dr_en=(0.0, i * 0.1),          # DR drifts away from EKF
            ekf_en=(0.0, 0.0),
            truth_en=(0.0, 0.0),
            accepted_residual=1.0,
        )
    last = mon.last
    assert last.dr_vs_ekf_m == pytest.approx(3.9, abs=0.2)
    assert last.drift_rate_ms > 0.5
    assert mon.estimated_drift_m() > 1.0


def test_corrector_is_bounded_and_blocked_without_trust():
    corr = DriftCorrector(gain=1.0, max_correction_m=2.0, trust_ekf_coast=False)
    de, dn, applied = corr.compute((0.0, 0.0), (0.0, 100.0), gnss_trusted=False)
    assert not applied and de == 0.0 and dn == 0.0

    de, dn, applied = corr.compute((0.0, 0.0), (0.0, 100.0), gnss_trusted=True)
    assert applied
    assert np.hypot(de, dn) == pytest.approx(2.0)  # clamped


def test_corrector_gain_is_partial():
    corr = DriftCorrector(gain=0.1, max_correction_m=100.0)
    de, dn, _ = corr.compute((0.0, 0.0), (10.0, 0.0), gnss_trusted=True)
    assert de == pytest.approx(1.0)


# ------------------------------------------------------------ map matching ---
def test_segment_projection():
    seg = RoadSegment((0.0, 0.0), (100.0, 0.0))
    cp, dist, t = seg.project((50.0, 10.0))
    assert cp == pytest.approx((50.0, 0.0))
    assert dist == pytest.approx(10.0)
    assert t == pytest.approx(0.5)


def test_matcher_snaps_within_gate_and_refuses_beyond():
    net = RoadNetwork([RoadSegment((0.0, 0.0), (100.0, 0.0), "main")])
    mm = MapMatcher(net, max_snap_distance_m=20.0)
    out = mm.match((50.0, 5.0))
    assert out["matched"] and out["offset_m"] == pytest.approx(5.0)
    out = mm.match((50.0, 60.0))
    assert not out["matched"]


def test_network_from_polyline_builds_segments():
    pts = [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0)]
    net = RoadNetwork.from_polyline(pts, simplify_m=10.0)
    assert len(net) >= 2
    mm = MapMatcher(net, max_snap_distance_m=30.0)
    assert mm.match((2.0, 50.0))["matched"]


def test_matcher_works_without_any_map():
    mm = MapMatcher(RoadNetwork([]))
    out = mm.match((0.0, 0.0))
    assert not out["matched"]
    assert "no road network" in out["reason"]


# ---------------------------------------------------------------- metrics ---
def test_error_stats_values():
    errs = [1.0, 2.0, 3.0, 4.0]
    st = error_stats(errs)
    assert st.mae_m == pytest.approx(2.5)
    assert st.rmse_m == pytest.approx(np.sqrt((1 + 4 + 9 + 16) / 4))
    assert st.max_m == pytest.approx(4.0)
    assert st.samples == 4


def test_error_stats_ignores_none_and_empty():
    assert error_stats([]).samples == 0
    assert error_stats([None, 2.0, float("nan")]).samples == 1


def test_outage_recovery_metrics():
    times = np.arange(0, 60, 0.5)
    errors = np.where((times > 10) & (times < 20), 5 + (times - 10) * 2.0, 1.0)
    out = outage_recovery_metrics(
        times=times,
        ekf_errors=errors,
        outage_start=10.0,
        outage_end=20.0,
        gnss_available=[True] * len(times),
    )
    assert out["peak_error_during_outage_m"] == pytest.approx(24.5, abs=1.0)
    assert out["drift_rate_during_outage_ms"] == pytest.approx(2.0, abs=0.5)
    assert out["recovery_time_s"] is not None


def test_outage_metrics_empty_without_outage():
    assert outage_recovery_metrics([0, 1], [1, 1], None, None, [True, True]) == {}


def test_absolute_metrics_compare_identically_aligned_samples():
    a = error_stats([1.0, 2.0, 3.0])
    b = error_stats([1.0, 2.0, 3.0])
    assert a.rmse_m == b.rmse_m
    c = error_stats([10.0, 20.0, 30.0])
    assert c.rmse_m > a.rmse_m
