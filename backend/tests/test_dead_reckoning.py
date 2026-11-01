"""Dead-reckoning integration tests (error-free inputs must be accurate)."""
import math

import numpy as np
import pytest

from app.algorithms.dead_reckoning import DeadReckoningEngine
from app.core.coordinate_utils import LocalTangentPlane


def test_straight_line_noiseless_is_exact():
    plane = LocalTangentPlane(26.9124, 75.7873)
    dr = DeadReckoningEngine(plane, speed=10.0, heading=0.0, use_odometry=False)
    dt = 0.1
    for _ in range(100):  # 10 s at 10 m/s => 100 m north
        dr.step(dt, accel_meas=0.0, yaw_rate_meas=0.0, odom_speed=None)
    e, n = dr.position
    assert e == pytest.approx(0.0, abs=1e-6)
    assert n == pytest.approx(100.0, rel=0.02)


def test_constant_acceleration_integrates_correctly():
    plane = LocalTangentPlane(0.0, 0.0)
    dr = DeadReckoningEngine(plane, speed=0.0, heading=0.0, use_odometry=False)
    dt = 0.01
    for _ in range(1000):  # 10 s at 2 m/s^2
        dr.step(dt, accel_meas=2.0, yaw_rate_meas=0.0)
    assert dr.v == pytest.approx(20.0, rel=1e-6)
    # distance = 0.5*a*t^2 = 100 m
    assert dr.position[1] == pytest.approx(100.0, rel=0.02)


def test_turn_changes_heading_and_path():
    plane = LocalTangentPlane(0.0, 0.0)
    dr = DeadReckoningEngine(plane, speed=10.0, heading=0.0, use_odometry=False)
    dt = 0.05
    yaw = math.radians(20.0)  # 20 deg/s for 1 s => 20 deg to the right
    for _ in range(20):
        dr.step(dt, accel_meas=0.0, yaw_rate_meas=yaw)
    assert dr.heading_deg == pytest.approx(20.0, abs=0.5)
    e, n = dr.position
    assert e > 0.5  # turned east
    assert n > 5.0


def test_accel_bias_causes_expected_drift():
    """A 0.05 m/s^2 unmodelled bias over 30 s produces ~22 m of along-track drift."""
    plane = LocalTangentPlane(0.0, 0.0)
    dt = 0.1
    drift = []
    for bias in (0.0, 0.05):
        dr = DeadReckoningEngine(plane, speed=10.0, heading=0.0, use_odometry=False,
                                 accel_bias=bias)
        for _ in range(300):
            # the accelerometer reports bias + 0 true acceleration; a DR
            # integrator that knows the bias can remove it entirely
            dr.step(dt, accel_meas=bias, yaw_rate_meas=0.0)
        drift.append(dr.position[1])
    # bias compensated by the DR engine: both runs land on the same distance
    assert drift[1] == pytest.approx(drift[0], rel=1e-6)

    # and an uncompensated bias produces the expected quadratic drift
    dr = DeadReckoningEngine(plane, speed=10.0, heading=0.0, use_odometry=False,
                             accel_bias=0.0)
    for _ in range(300):
        dr.step(dt, accel_meas=0.05, yaw_rate_meas=0.0)
    assert dr.position[1] - drift[0] > 15.0


def test_odometry_blend_bounds_velocity_drift():
    plane = LocalTangentPlane(0.0, 0.0)
    dr = DeadReckoningEngine(plane, speed=10.0, heading=0.0, use_odometry=True,
                             odometry_weight=0.6)
    for _ in range(100):
        dr.step(0.1, accel_meas=1.0, yaw_rate_meas=0.0, odom_speed=10.0)
    # odometry keeps the speed near 10 m/s despite a false 1 m/s^2 reading
    assert dr.v == pytest.approx(10.0, rel=0.35)


def test_correction_shifts_position():
    plane = LocalTangentPlane(0.0, 0.0)
    dr = DeadReckoningEngine(plane, speed=0.0, heading=0.0)
    dr.correct(2.0, -3.0, alpha=0.5)
    assert dr.position == pytest.approx((1.0, -1.5))


def test_geodetic_round_trip():
    plane = LocalTangentPlane(26.9124, 75.7873)
    dr = DeadReckoningEngine(plane, speed=10.0, heading=math.pi / 2, use_odometry=False)
    for _ in range(10):
        dr.step(0.1, accel_meas=0.0, yaw_rate_meas=0.0)
    lat, lon = dr.geodetic()
    e, n = plane.to_local(lat, lon)
    assert (e, n) == pytest.approx(dr.position, abs=1e-6)
