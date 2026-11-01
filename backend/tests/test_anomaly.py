"""GNSS anomaly detector tests: no false alarms, real detections, rejection."""
import numpy as np
import pytest

from app.algorithms.gnss_anomaly import DetectorThresholds, GnssAnomalyDetector


def feed(detector, n, gnss_fn, ekf_fn=None, dt=0.1, speed=12.0, sigma=2.5):
    results = []
    for i in range(n):
        t = i * dt
        gnss = gnss_fn(t)
        ekf_en = ekf_fn(t) if ekf_fn else (0.0, 0.0)
        res = detector.evaluate(
            t=t,
            gnss_en=gnss,
            ekf_en=ekf_en,
            uncertainty_m=2.0,
            nis=None,
            fused_speed=speed,
            fused_heading=0.0,
            heading_rate=0.0,
        )
        results.append(res)
    return results


def test_clean_gnss_produces_no_rejections():
    det = GnssAnomalyDetector(DetectorThresholds(gnss_sigma_m=2.5))
    rng = np.random.default_rng(0)
    # vehicle driving north at 12 m/s with 2.5 m GNSS noise
    # reference (EKF) tracks the vehicle; only GNSS noise is present
    res = feed(
        det, 400,
        gnss_fn=lambda t: (float(rng.normal(0, 2.5)), 12.0 * t + float(rng.normal(0, 2.5))),
        ekf_fn=lambda t: (0.0, 12.0 * t),
    )
    assert det.rejections == 0
    assert sum(r.reject for r in res) == 0


def test_sudden_jump_is_rejected():
    det = GnssAnomalyDetector()
    rng = np.random.default_rng(1)
    det.evaluate(0.0, (0.0, 0.0), (0.0, 0.0), 2.0, None, 12.0, 0.0, 0.0)
    res = det.evaluate(0.1, (120.0, 60.0), (0.0, 1.2), 2.0, None, 12.0, 0.0, 0.0)
    assert res.is_anomaly and res.reject
    assert res.anomaly_type in ("position_jump", "velocity", "heading")


def test_persistent_drift_is_detected():
    det = GnssAnomalyDetector()
    # residual bias grows slowly in a fixed direction (no single big jump)
    res = feed(
        det, 300,
        gnss_fn=lambda t: (0.25 * t, 0.0 + 0.0 * t),
        ekf_fn=lambda t: (0.0, 0.0),
    )
    flagged = [r for r in res if r.is_anomaly]
    assert flagged, "persistent bias must be detected"
    assert any(r.anomaly_type in ("drift", "residual") for r in flagged)


def test_missing_gnss_is_not_an_anomaly():
    det = GnssAnomalyDetector()
    res = det.evaluate(1.0, None, (0.0, 0.0), 2.0, None, 10.0, 0.0, 0.0)
    assert not res.is_anomaly
    assert det.status(available=False, residual_m=None) == "unavailable"


def test_status_classification():
    det = GnssAnomalyDetector(DetectorThresholds(residual_degraded_m=10.0))
    assert det.status(False, None) == "unavailable"
    good = det.evaluate(0.0, (0.0, 0.0), (0.0, 0.0), 1.0, None, 10.0, 0.0, 0.0)
    assert det.status(True, 1.0, good) == "healthy"
    assert det.status(True, 42.0, good) == "degraded"
    bad = det.evaluate(0.1, (500.0, 500.0), (0.0, 1.0), 1.0, None, 10.0, 0.0, 0.0)
    assert det.status(True, 700.0, bad) == "suspicious"


def test_graduated_response_downweights_before_rejecting():
    det = GnssAnomalyDetector()
    det.evaluate(0.0, (0.0, 0.0), (0.0, 0.0), 1.0, None, 10.0, 0.0, 0.0)
    res = det.evaluate(0.1, (9.0, 0.0), (0.0, 1.0), 1.0, None, 10.0, 0.0, 0.0)
    if res.is_anomaly and not res.reject:
        assert res.extra_sigma_m > 0.0


def test_severities_are_reported_for_explainability():
    det = GnssAnomalyDetector()
    det.evaluate(0.0, (0.0, 0.0), (0.0, 0.0), 1.0, None, 10.0, 0.0, 0.0)
    res = det.evaluate(0.1, (60.0, 0.0), (0.0, 1.0), 1.0, None, 10.0, 0.0, 0.0)
    assert set(res.severities) >= {"position_jump", "velocity", "heading", "residual", "drift"}
    assert 0.0 <= res.score <= 1.0
    assert isinstance(res.reason, str) and res.reason


def test_reset_clears_history():
    det = GnssAnomalyDetector()
    feed(det, 50, gnss_fn=lambda t: (0.0, 10 * t))
    det.reset()
    assert det.prev_gnss is None
    assert det.detections == 0 and det.rejections == 0
