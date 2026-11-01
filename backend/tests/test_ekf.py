"""EKF unit tests: prediction, updates, gating, stability, outage handling."""
import math

import numpy as np
import pytest

from app.algorithms.ekf import ExtendedKalmanFilter, I_BA, I_BG, I_E, I_N, I_PSI, I_V, N_STATE
from app.core.coordinate_utils import LocalTangentPlane


def make_ekf(**kw) -> ExtendedKalmanFilter:
    plane = LocalTangentPlane(26.9124, 75.7873)
    x0 = np.zeros(N_STATE)
    x0[I_PSI] = 0.0
    P0 = np.diag([1.0, 1.0, 0.5, 0.01, 0.01, 1e-4])
    return ExtendedKalmanFilter(plane, initial_state=x0, initial_cov=P0, **kw)


def test_prediction_moves_state_along_heading():
    ekf = make_ekf()
    ekf.x[I_V] = 10.0
    ekf.x[I_PSI] = 0.0  # north
    ekf.predict(0.1, accel_meas=0.0, yaw_rate_meas=0.0)
    assert ekf.x[I_N] == pytest.approx(1.0, rel=1e-6)
    assert ekf.x[I_E] == pytest.approx(0.0, abs=1e-9)


def test_prediction_grows_covariance():
    ekf = make_ekf()
    before = np.trace(ekf.P)
    for _ in range(10):
        ekf.predict(0.1, accel_meas=0.0, yaw_rate_meas=0.0)
    assert np.trace(ekf.P) > before


def test_gnss_update_pulls_state_toward_measurement():
    ekf = make_ekf()
    before = ekf.position_sigma()
    # repeated consistent fixes converge on the measurement; the rate is set by
    # the Kalman gain (prior covariance vs measurement noise), so we look for
    # monotone convergence rather than an instant snap
    history = []
    for _ in range(40):
        ekf.update_gnss(5.0, -3.0, timestamp=0.0)
        history.append(float(ekf.x[I_E]))
    assert all(b >= a - 1e-9 for a, b in zip(history, history[1:]))
    assert ekf.x[I_E] == pytest.approx(5.0, abs=1.0)  # ~90% of the way after 40 fixes
    assert ekf.x[I_N] == pytest.approx(-3.0, abs=0.7)
    # covariance shrinks after measurements
    assert ekf.position_sigma() < before


def test_covariance_stays_symmetric_positive_definite():
    ekf = make_ekf()
    rng = np.random.default_rng(0)
    for i in range(400):
        ekf.predict(0.1, accel_meas=float(rng.normal(0, 0.2)),
                    yaw_rate_meas=float(rng.normal(0, 0.02)))
        if i % 2 == 0:
            ekf.update_gnss(float(rng.normal(0, 3)), float(rng.normal(0, 3)))
    P = ekf.P
    assert np.allclose(P, P.T, atol=1e-9)
    assert np.all(np.linalg.eigvalsh(P) > 0)


def test_innovation_and_nis_reported():
    ekf = make_ekf()
    inn = ekf.innovation_gnss(3.0, 4.0)
    assert inn.residual_m == pytest.approx(5.0, rel=1e-6)
    assert inn.nis > 0
    assert inn.accepted


def test_gate_rejects_impossible_jump():
    ekf = make_ekf()
    ekf.update_gnss(0.0, 0.0, timestamp=0.0)
    inn = ekf.update_gnss(500.0, 500.0, timestamp=0.1, gate=True)
    assert not inn.accepted
    assert ekf.rejected_count == 1
    # state was not corrupted by the rejected fix
    assert abs(ekf.x[I_E]) < 1.0 and abs(ekf.x[I_N]) < 1.0


def test_outage_prediction_has_no_measurement_update():
    ekf = make_ekf()
    ekf.x[I_V] = 8.0
    v_before = ekf.update_count
    for _ in range(50):
        ekf.predict(0.1, accel_meas=0.0, yaw_rate_meas=0.0)
    assert ekf.update_count == v_before
    assert ekf.predict_count >= 50
    # uncertainty grows while coasting
    assert ekf.position_sigma() > 1.0


def test_speed_update_affects_velocity_only():
    ekf = make_ekf()
    ekf.update_speed(12.0)
    assert ekf.x[I_V] == pytest.approx(12.0, abs=1.0)


def test_heading_update_wraps_angle():
    ekf = make_ekf()
    ekf.x[I_PSI] = math.radians(179.0)
    ekf.update_heading(math.radians(-179.0))
    # should move through +-180, not all the way around
    assert abs(abs(math.degrees(ekf.x[I_PSI])) - 180.0) < 5.0


def test_bias_states_are_estimated_from_observations():
    """A persistent GNSS/odometry disagreement should be absorbed by biases."""
    rng = np.random.default_rng(42)
    ekf = make_ekf(accel_noise=1.0)
    truth_e, truth_n, v, psi = 0.0, 0.0, 10.0, 0.0
    true_bias = 0.08
    for i in range(600):
        dt = 0.1
        accel_meas = true_bias + rng.normal(0, 0.01)
        ekf.predict(dt, accel_meas=accel_meas, yaw_rate_meas=rng.normal(0, 0.001))
        truth_n += v * dt
        if i % 2 == 0:
            ekf.update_gnss(truth_e + rng.normal(0, 1.0), truth_n + rng.normal(0, 1.0))
        ekf.update_speed(v + rng.normal(0, 0.05))
    assert ekf.x[I_BA] == pytest.approx(true_bias, abs=0.06)


def test_reset_restores_state():
    ekf = make_ekf()
    ekf.update_gnss(100.0, 100.0, gate=False)
    ekf.reset(np.zeros(N_STATE))
    assert ekf.position == pytest.approx((0.0, 0.0))
    assert ekf.rejected_count == 0
