"""Rauch-Tung-Striebel smoothing on top of the EKF.

A Kalman filter is causal: at time *k* it may only use measurements up to *k*.
Once the run is over (or with a fixed lag), the whole stored trajectory can be
processed backwards, which typically removes a further 30-60% of the horizontal
error without a single extra sensor.

The smoother needs, for every step ``k`` of the forward pass:

* the filtered estimate ``x_k|k`` and covariance ``P_k|k``
* the transition Jacobian ``F_k`` that propagated ``k-1 -> k``
* the predicted estimate ``x_k|k-1`` and covariance ``P_k|k-1``

Backward recursion (with ``C_k = P_k|k F_k^T (P_k|k-1)^-1``):

    x_k|N = x_k|k + C_k (x_k+1|N - x_k+1|k)
    P_k|N = P_k|k + C_k (P_k+1|N - P_k+1|k) C_k^T

It is used in two places:

* ``smooth_window`` -- fixed-lag smoothing on the live stream, so the dashboard
  can show a retrospective track with a known delay;
* ``smooth_series``  -- full-batch smoothing of a completed run for scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

from app.algorithms.ekf import I_E, I_N, I_PSI, N_STATE
from app.core.coordinate_utils import wrap_angle


@dataclass
class SmoothedPoint:
    step: int
    t: float
    east: float
    north: float
    speed: float
    heading: float
    sigma_m: float


def _safe_solve(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Solve A X = B with a pseudo-inverse fallback (numerical safety)."""
    try:
        return np.linalg.solve(A, B)
    except np.linalg.LinAlgError:  # pragma: no cover
        return np.linalg.pinv(A) @ B


def _state_delta(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Difference of two states with the heading component wrapped to (-pi, pi].

    Without this an RTS pass produces spurious jumps every time the vehicle
    heading crosses the +/-pi branch cut (a 2*pi discontinuity in the state
    vector would be amplified by the gain into a large position correction).
    """
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    d[I_PSI] = wrap_angle(float(d[I_PSI]))
    return d


def rts_smooth(
    filt_x: Sequence[np.ndarray],
    filt_P: Sequence[np.ndarray],
    trans_F: Sequence[np.ndarray],
    pred_x: Sequence[np.ndarray],
    pred_P: Sequence[np.ndarray],
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Full backward RTS pass over N stored steps.

    ``trans_F[k]`` / ``pred_x[k]`` / ``pred_P[k]`` describe the transition into
    step ``k`` (index 0 has no predecessor and is kept as-is).
    """
    n = len(filt_x)
    if n == 0:
        return [], []
    xs = [np.asarray(x, dtype=float).copy() for x in filt_x]
    Ps = [np.asarray(P, dtype=float).copy() for P in filt_P]
    xs_s = [x.copy() for x in xs]
    Ps_s = [P.copy() for P in Ps]

    for k in range(n - 2, -1, -1):
        F = trans_F[k + 1]
        P_pred_next = pred_P[k + 1]
        # C = P_k F^T (P_k+1|k)^-1  -- solved rather than inverted
        C = _safe_solve(P_pred_next.T, (Ps[k] @ F.T).T).T
        dx = _state_delta(xs_s[k + 1], pred_x[k + 1])
        xs_s[k] = xs[k] + C @ dx
        xs_s[k][I_PSI] = wrap_angle(float(xs_s[k][I_PSI]))
        xs_s[k][I_E] = float(xs_s[k][I_E])
        xs_s[k][I_N] = float(xs_s[k][I_N])
        Ps_s[k] = Ps[k] + C @ (Ps_s[k + 1] - P_pred_next) @ C.T
        Ps_s[k] = 0.5 * (Ps_s[k] + Ps_s[k].T)
    return xs_s, Ps_s


class SmoothingHistory:
    """Bounded ring buffer of forward-pass data for fixed-lag smoothing."""

    def __init__(self, max_len: int = 240) -> None:
        self.max_len = int(max_len)
        self.steps: List[int] = []
        self.times: List[float] = []
        self.filt_x: List[np.ndarray] = []
        self.filt_P: List[np.ndarray] = []
        self.trans_F: List[np.ndarray] = []
        self.pred_x: List[np.ndarray] = []
        self.pred_P: List[np.ndarray] = []

    def __len__(self) -> int:
        return len(self.steps)

    def clear(self) -> None:
        self.__init__(self.max_len)  # type: ignore[misc]

    def push(
        self,
        step: int,
        t: float,
        filt_x: np.ndarray,
        filt_P: np.ndarray,
        F: np.ndarray,
        pred_x: np.ndarray,
        pred_P: np.ndarray,
    ) -> None:
        self.steps.append(int(step))
        self.times.append(float(t))
        self.filt_x.append(np.asarray(filt_x, dtype=float).copy())
        self.filt_P.append(np.asarray(filt_P, dtype=float).copy())
        self.trans_F.append(np.asarray(F, dtype=float).copy())
        self.pred_x.append(np.asarray(pred_x, dtype=float).copy())
        self.pred_P.append(np.asarray(pred_P, dtype=float).copy())
        if len(self.steps) > self.max_len:
            for buf in (self.steps, self.times, self.filt_x, self.filt_P,
                        self.trans_F, self.pred_x, self.pred_P):
                del buf[0]

    def smooth(self) -> List[SmoothedPoint]:
        """RTS over the current window (returns points in time order)."""
        xs_s, Ps_s = rts_smooth(self.filt_x, self.filt_P, self.trans_F, self.pred_x, self.pred_P)
        out: List[SmoothedPoint] = []
        for i, x in enumerate(xs_s):
            sigma = float(np.sqrt(max(float(np.max(np.linalg.eigvalsh(Ps_s[i][:2, :2]))), 1e-12)))
            out.append(
                SmoothedPoint(
                    step=self.steps[i],
                    t=self.times[i],
                    east=float(x[I_E]),
                    north=float(x[I_N]),
                    speed=float(max(x[2], 0.0)),
                    heading=float(x[I_PSI]),
                    sigma_m=sigma,
                )
            )
        return out

    def value_at(self, step: int) -> SmoothedPoint | None:
        """Smoothed point for a specific step if it is inside the window."""
        if not self.steps:
            return None
        for p in self.smooth():
            if p.step == step:
                return p
        return None

    def lagged_point(self, lag_steps: int) -> "SmoothedPoint | None":
        """RTS-smoothed state ``lag_steps`` behind the newest sample.

        Only the backward recursion from the newest sample down to the target
        index is executed, which keeps the live cost O(lag) instead of O(window)
        and gives a fixed-lag smoother with a known latency.
        """
        n = len(self.steps)
        if n < 3:
            return None
        target = max(0, n - 1 - int(max(1, lag_steps)))
        if target >= n - 1:
            return None

        # backward pass from the last sample down to `target`
        x_next_s = self.filt_x[-1].copy()
        P_next_s = self.filt_P[-1].copy()
        for k in range(n - 2, target - 1, -1):
            F = self.trans_F[k + 1]
            P_pred_next = self.pred_P[k + 1]
            C = _safe_solve(P_pred_next.T, (self.filt_P[k] @ F.T).T).T
            x_s = self.filt_x[k] + C @ _state_delta(x_next_s, self.pred_x[k + 1])
            x_s[I_PSI] = wrap_angle(float(x_s[I_PSI]))
            P_s = self.filt_P[k] + C @ (P_next_s - P_pred_next) @ C.T
            P_s = 0.5 * (P_s + P_s.T)
            x_next_s, P_next_s = x_s, P_s

        sigma = float(np.sqrt(max(float(np.max(np.linalg.eigvalsh(P_next_s[:2, :2]))), 1e-12)))
        return SmoothedPoint(
            step=self.steps[target],
            t=self.times[target],
            east=float(x_next_s[I_E]),
            north=float(x_next_s[I_N]),
            speed=float(max(x_next_s[2], 0.0)),
            heading=float(x_next_s[I_PSI]),
            sigma_m=sigma,
        )
