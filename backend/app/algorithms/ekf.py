"""Extended Kalman Filter for 2-D vehicle navigation.

State vector (6-D):

    x = [ east, north, speed, heading, accel_bias, gyro_bias ]^T

Units: metres, m/s, radians, m/s^2, rad/s. The frame is a local EN tangent
plane anchored at the trajectory origin (see ``coordinate_utils``).

Prediction (IMU driven, non-linear in heading):

    e'  = e + v * sin(psi) * dt
    n'  = n + v * cos(psi) * dt
    v'  = v + (a_m - b_a) * dt
    psi'= psi + (w_m - b_g) * dt
    b_a'= b_a
    b_g'= b_g

Measurement models:

    GNSS position      z = [e, n]^T     H = [I2 | 0]        R = sigma_gnss^2 I2
    Wheel speed        z = [v]          H = [0 0 1 0 0 0]  R = sigma_v^2
    (optional) compass z = [psi]        H = [0 0 0 1 0 0]  R = sigma_psi^2

Anomaly gating: every GNSS update computes the innovation ``y`` with covariance
``S = H P H^T + R`` and the normalised innovation squared
``NIS = y^T S^-1 y``. If NIS exceeds the chi-square gate for 2 degrees of
freedom the measurement is rejected (no state or covariance change), which is
what keeps a spoofed solution from corrupting the estimate.

Numerical stability: Joseph-form covariance update, explicit symmetrisation,
eigenvalue flooring, and heading kept wrapped to (-pi, pi].
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.core.coordinate_utils import LocalTangentPlane, wrap_angle

N_STATE = 6
I_E, I_N, I_V, I_PSI, I_BA, I_BG = range(N_STATE)


@dataclass
class EkfResult:
    east: float
    north: float
    speed: float
    heading: float
    accel_bias: float
    gyro_bias: float
    pos_sigma_m: float
    uncertainty_m: float
    trace_P: float


@dataclass
class Innovation:
    y: np.ndarray
    S: np.ndarray
    nis: float
    residual_m: float
    accepted: bool


class ExtendedKalmanFilter:
    """6-state EKF for GNSS/IMU/odometry fusion."""

    def __init__(
        self,
        plane: LocalTangentPlane,
        initial_state: Optional[np.ndarray] = None,
        initial_cov: Optional[np.ndarray] = None,
        gnss_sigma_m: float = 2.5,
        speed_sigma_ms: float = 0.15,
        heading_sigma_deg: float = 1.0,
        accel_noise: float = 0.35,
        gyro_noise_deg: float = 0.35,
        accel_bias_walk: float = 0.004,
        gyro_bias_walk_deg: float = 0.002,
        nis_gate: float = 16.27,
        use_compass: bool = False,
    ) -> None:
        self.plane = plane
        self.x = (
            np.zeros(N_STATE, dtype=float)
            if initial_state is None
            else np.asarray(initial_state, dtype=float).copy()
        )
        if initial_cov is None:
            P = np.diag([4.0, 4.0, 0.25, 0.02, 0.01, 1e-4]).astype(float)
        else:
            P = np.asarray(initial_cov, dtype=float).copy()
        self.P = self._stabilise(P)

        self.sig_gnss = float(gnss_sigma_m)
        self.sig_speed = float(speed_sigma_ms)
        self.sig_heading = float(np.radians(heading_sigma_deg))
        self.q_accel = float(accel_noise) ** 2
        self.q_gyro = float(np.radians(gyro_noise_deg)) ** 2
        self.q_ba = float(accel_bias_walk) ** 2
        self.q_bg = float(np.radians(gyro_bias_walk_deg)) ** 2
        self.nis_gate = float(nis_gate)
        self.use_compass = bool(use_compass)

        self.last_innovation: Optional[Innovation] = None
        self.last_gnss_update_t: Optional[float] = None
        self.rejected_count = 0
        self.update_count = 0
        self.predict_count = 0

    # ---------------------------------------------------------------- utils ---
    @staticmethod
    def _stabilise(P: np.ndarray) -> np.ndarray:
        P = 0.5 * (P + P.T)
        P = np.nan_to_num(P, nan=0.0, posinf=1e12, neginf=-1e12)
        try:
            w, V = np.linalg.eigh(P)
            w = np.clip(w, 1e-12, 1e9)
            P = V @ np.diag(w) @ V.T
            P = 0.5 * (P + P.T)
        except np.linalg.LinAlgError:  # pragma: no cover
            P = np.eye(N_STATE) * 1e3
        return P

    @property
    def position(self) -> tuple[float, float]:
        return float(self.x[I_E]), float(self.x[I_N])

    @property
    def geodetic(self) -> tuple[float, float]:
        return self.plane.to_geodetic(float(self.x[I_E]), float(self.x[I_N]))

    def position_sigma(self) -> float:
        """1-sigma radial position uncertainty from the 2x2 position block.

        For a 2-D isotropic Gaussian the radial 1-sigma is
        ``sqrt(trace(P_pos))`` *only* if variances are equal; here we return
        ``sqrt(lambda_max)`` of the position block, a conservative 1-sigma.
        """
        Ppos = self.P[:2, :2]
        w = np.linalg.eigvalsh(0.5 * (Ppos + Ppos.T))
        return float(np.sqrt(max(float(np.max(w)), 1e-12)))

    def uncertainty(self) -> float:
        """sqrt(trace(position covariance)) in metres (a scale, not a probability)."""
        return float(np.sqrt(max(float(np.trace(self.P[:2, :2])), 1e-12)))

    def result(self) -> EkfResult:
        return EkfResult(
            east=float(self.x[I_E]),
            north=float(self.x[I_N]),
            speed=float(self.x[I_V]),
            heading=float(self.x[I_PSI]),
            accel_bias=float(self.x[I_BA]),
            gyro_bias=float(self.x[I_BG]),
            pos_sigma_m=self.position_sigma(),
            uncertainty_m=self.uncertainty(),
            trace_P=float(np.trace(self.P)),
        )

    # ----------------------------------------------------------- prediction ---
    def predict(self, dt: float, accel_meas: float, yaw_rate_meas: float) -> np.ndarray:
        """IMU-driven EKF prediction step."""
        if dt <= 0:
            raise ValueError("dt must be positive")
        e, n, v, psi, ba, bg = self.x
        a_use = accel_meas - ba
        w_use = yaw_rate_meas - bg

        # propagate state
        v_new = max(0.0, v + a_use * dt)
        psi_new = wrap_angle(psi + w_use * dt)
        e_new = e + v_new * np.sin(psi_new) * dt
        n_new = n + v_new * np.cos(psi_new) * dt

        # Jacobian of the motion model wrt state
        F = np.eye(N_STATE)
        F[I_E, I_V] = np.sin(psi_new) * dt
        F[I_E, I_PSI] = v_new * np.cos(psi_new) * dt
        F[I_E, I_BA] = -np.sin(psi_new) * dt ** 2
        F[I_N, I_V] = np.cos(psi_new) * dt
        F[I_N, I_PSI] = -v_new * np.sin(psi_new) * dt
        F[I_N, I_BA] = -np.cos(psi_new) * dt ** 2
        F[I_V, I_BA] = -dt
        F[I_PSI, I_BG] = -dt

        # process noise (accel + gyro noise enter through the integral terms)
        q_v = self.q_accel * dt ** 2
        q_psi = self.q_gyro * dt ** 2
        Q = np.zeros((N_STATE, N_STATE))
        Q[I_E, I_E] = 0.25 * q_v * dt ** 2
        Q[I_N, I_N] = 0.25 * q_v * dt ** 2
        Q[I_V, I_V] = q_v
        Q[I_PSI, I_PSI] = q_psi
        Q[I_BA, I_BA] = self.q_ba * dt
        Q[I_BG, I_BG] = self.q_bg * dt
        # cross-correlation between velocity and position growth
        Q[I_E, I_V] = Q[I_V, I_E] = 0.5 * q_v * dt
        Q[I_N, I_V] = Q[I_V, I_N] = 0.5 * q_v * dt

        P_new = F @ self.P @ F.T + Q

        self.x = np.array([e_new, n_new, v_new, psi_new, ba, bg], dtype=float)
        self.P = self._stabilise(P_new)
        self.predict_count += 1
        return self.x.copy()

    # ------------------------------------------------------------ corrections ---
    def _innovation(self, z: np.ndarray, H: np.ndarray, R: np.ndarray) -> Innovation:
        y = np.asarray(z, dtype=float) - H @ self.x
        S = H @ self.P @ H.T + R
        S = 0.5 * (S + S.T)
        try:
            Sinv = np.linalg.inv(S)
            nis = float(y.T @ Sinv @ y)
        except np.linalg.LinAlgError:  # pragma: no cover
            Sinv = np.linalg.pinv(S)
            nis = float("inf")
        residual = float(np.linalg.norm(y))
        return Innovation(y=y, S=S, nis=nis, residual_m=residual, accepted=True)

    def _apply_update(self, z, H, R) -> Innovation:
        inn = self._innovation(z, H, R)
        Sinv = np.linalg.inv(inn.S)
        K = self.P @ H.T @ Sinv
        self.x = self.x + K @ inn.y
        self.x[I_PSI] = wrap_angle(float(self.x[I_PSI]))
        self.x[I_V] = max(0.0, float(self.x[I_V]))
        # Joseph form for numerical stability
        I_KH = np.eye(N_STATE) - K @ H
        P_new = I_KH @ self.P @ I_KH.T + K @ R @ K.T
        self.P = self._stabilise(P_new)
        self.update_count += 1
        return inn

    def update_gnss(
        self,
        east: float,
        north: float,
        timestamp: Optional[float] = None,
        gate: bool = True,
        extra_sigma_m: float = 0.0,
    ) -> Innovation:
        """GNSS position update with NIS innovation gating."""
        H = np.zeros((2, N_STATE))
        H[0, I_E] = 1.0
        H[1, I_N] = 1.0
        sigma = float(np.hypot(self.sig_gnss, extra_sigma_m))
        R = np.eye(2) * sigma ** 2
        z = np.array([east, north], dtype=float)

        inn = self._innovation(z, H, R)
        if gate and inn.nis > self.nis_gate:
            inn.accepted = False
            self.rejected_count += 1
            self.last_innovation = inn
            return inn

        inn = self._apply_update(z, H, R)
        self.last_innovation = inn
        self.last_gnss_update_t = timestamp
        return inn

    def innovation_gnss(self, east: float, north: float) -> Innovation:
        """GNSS innovation without applying the update (used for gating)."""
        H = np.zeros((2, N_STATE))
        H[0, I_E] = 1.0
        H[1, I_N] = 1.0
        R = np.eye(2) * self.sig_gnss ** 2
        return self._innovation(np.array([east, north], dtype=float), H, R)

    def update_speed(self, speed: float) -> Innovation:
        H = np.zeros((1, N_STATE))
        H[0, I_V] = 1.0
        R = np.array([[self.sig_speed ** 2]])
        return self._apply_update(np.array([speed]), H, R)

    def update_heading(self, heading: float) -> Innovation:
        """Optional compass/heading update (angle-wrapped innovation)."""
        H = np.zeros((1, N_STATE))
        H[0, I_PSI] = 1.0
        R = np.array([[self.sig_heading ** 2]])
        # unwrap the measurement next to the current estimate so the linear
        # update is applied to the shortest angular distance
        target = float(self.x[I_PSI]) + wrap_angle(heading - float(self.x[I_PSI]))
        return self._apply_update(np.array([target]), H, R)

    # ------------------------------------------------------------------ misc ---
    def state_dict(self) -> dict:
        r = self.result()
        return {
            "east": r.east,
            "north": r.north,
            "speed": r.speed,
            "heading_deg": float(np.degrees(r.heading) % 360.0),
            "accel_bias": r.accel_bias,
            "gyro_bias": r.gyro_bias,
            "pos_sigma_m": r.pos_sigma_m,
            "uncertainty_m": r.uncertainty_m,
            "rejected_count": self.rejected_count,
        }

    def reset(self, state: np.ndarray, cov: Optional[np.ndarray] = None) -> None:
        self.x = np.asarray(state, dtype=float).copy()
        self.P = self._stabilise(np.eye(N_STATE) * 10.0 if cov is None else cov)
        self.rejected_count = 0
        self.update_count = 0
        self.predict_count = 0
        self.last_innovation = None
