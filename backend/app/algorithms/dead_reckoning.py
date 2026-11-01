"""Dead-reckoning integrator.

Propagates a pose in the local East-North frame from IMU (specific force +
yaw rate) and odometry. It is deliberately kept separate from the EKF so that
the dashboard can show an unfiltered, drift-accumulating baseline.

Motion model (discrete, body frame aligned with heading):

    v_{k+1}   = v_k + (a_m - b_a) * dt
    psi_{k+1} = psi_k + (w_m - b_g) * dt
    e_{k+1}   = e_k + v_{k+1} * sin(psi_{k+1}) * dt
    n_{k+1}   = n_k + v_{k+1} * cos(psi_{k+1}) * dt

Heading is measured clockwise from north, matching compass/vehicle convention.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.core.coordinate_utils import LocalTangentPlane, wrap_angle


@dataclass
class DrState:
    east: float
    north: float
    speed: float
    heading: float  # rad
    dr_e: float
    dr_n: float
    distance_travelled: float


class DeadReckoningEngine:
    def __init__(
        self,
        plane: LocalTangentPlane,
        initial_e: float = 0.0,
        initial_n: float = 0.0,
        speed: float = 0.0,
        heading: float = 0.0,
        accel_bias: float = 0.0,
        gyro_bias: float = 0.0,
        use_odometry: bool = True,
        odometry_weight: float = 0.5,
    ) -> None:
        self.plane = plane
        self.e = float(initial_e)
        self.n = float(initial_n)
        self.v = float(speed)
        self.psi = float(heading)
        self.b_a = float(accel_bias)
        self.b_g = float(gyro_bias)
        self.use_odometry = use_odometry
        self.odom_weight = float(np.clip(odometry_weight, 0.0, 0.9))
        self.travelled = 0.0

    def reset(self, e: float, n: float, speed: float = 0.0, heading: float = 0.0) -> None:
        self.e, self.n, self.v, self.psi = float(e), float(n), float(speed), float(heading)
        self.travelled = 0.0

    def step(
        self,
        dt: float,
        accel_meas: float,
        yaw_rate_meas: float,
        odom_speed: Optional[float] = None,
    ) -> DrState:
        """Propagate one step using measured accel, yaw rate and (optionally) speed."""
        a = accel_meas - self.b_a
        w = yaw_rate_meas - self.b_g

        v_pred = self.v + a * dt
        if self.use_odometry and odom_speed is not None:
            # complementary blend of integrated accel and odometry: this mirrors
            # a real system where wheel speed bounds the accelerometer drift
            v_pred = (1.0 - self.odom_weight) * v_pred + self.odom_weight * odom_speed
        v_pred = float(max(0.0, v_pred))

        psi_pred = wrap_angle(self.psi + w * dt)
        e_new = self.e + v_pred * np.sin(psi_pred) * dt
        n_new = self.n + v_pred * np.cos(psi_pred) * dt
        self.travelled += float(np.hypot(e_new - self.e, n_new - self.n))

        self.v, self.psi, self.e, self.n = v_pred, psi_pred, float(e_new), float(n_new)
        return DrState(self.e, self.n, self.v, self.psi, self.e, self.n, self.travelled)

    def correct(self, de: float, dn: float, alpha: float = 1.0) -> None:
        """Apply an external (trusted) correction to the DR pose."""
        self.e += alpha * de
        self.n += alpha * dn

    def geodetic(self) -> tuple[float, float]:
        """Current pose as (lat, lon) degrees."""
        return self.plane.to_geodetic(self.e, self.n)

    @property
    def position(self) -> tuple[float, float]:
        return self.e, self.n

    @property
    def heading_deg(self) -> float:
        return float(np.degrees(self.psi) % 360.0)
