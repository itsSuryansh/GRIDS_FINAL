"""Drift monitoring and transparent correction.

The EKF is always the trusted baseline. Drift correction here is deliberately
*conservative and explainable*:

* ``DriftMonitor`` tracks three quantities continuously:
  - dead-reckoning drift vs ground truth (available because this is a
    simulation with a reference trajectory; used for evaluation and UI),
  - dead-reckoning drift vs the fused EKF solution (available in a real system),
  - the GNSS residual bias estimate from *accepted* measurements only.
* ``DriftCorrector`` nudges the dead-reckoning pose toward the EKF/trusted
  source using a bounded gain. It never overwrites the EKF state, and it never
  consumes measurements that anomaly detection has rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class DriftStats:
    t: float
    dr_vs_truth_m: float          # only computable in simulation
    dr_vs_ekf_m: float            # available in a real deployment
    ekf_vs_truth_m: float
    gnss_bias_estimate_m: float   # rolling mean residual of accepted GNSS fixes
    drift_rate_ms: float          # d(dr_vs_ekf)/dt, smoothed


class DriftMonitor:
    """Rolling drift estimator with a smoothed rate."""

    def __init__(self, window: int = 40) -> None:
        self.window = int(window)
        self._dr_vs_truth: list[float] = []
        self._dr_vs_ekf: list[float] = []
        self._ekf_vs_truth: list[float] = []
        self._accepted_residuals: list[float] = []
        self._last: Optional[DriftStats] = None
        self._rate = 0.0
        self._last_t: Optional[float] = None
        self._last_dr_ekf: Optional[float] = None

    def reset(self) -> None:
        self.__init__(self.window)  # type: ignore[misc]

    def record(
        self,
        t: float,
        dr_en: Tuple[float, float],
        ekf_en: Tuple[float, float],
        truth_en: Optional[Tuple[float, float]] = None,
        accepted_residual: Optional[float] = None,
    ) -> DriftStats:
        dr_vs_ekf = float(np.hypot(dr_en[0] - ekf_en[0], dr_en[1] - ekf_en[1]))
        dr_vs_truth = (
            float(np.hypot(dr_en[0] - truth_en[0], dr_en[1] - truth_en[1]))
            if truth_en is not None
            else dr_vs_ekf
        )
        ekf_vs_truth = (
            float(np.hypot(ekf_en[0] - truth_en[0], ekf_en[1] - truth_en[1]))
            if truth_en is not None
            else 0.0
        )

        self._dr_vs_truth.append(dr_vs_truth)
        self._dr_vs_ekf.append(dr_vs_ekf)
        self._ekf_vs_truth.append(ekf_vs_truth)
        if accepted_residual is not None:
            self._accepted_residuals.append(float(accepted_residual))

        for buf in (self._dr_vs_truth, self._dr_vs_ekf, self._ekf_vs_truth, self._accepted_residuals):
            if len(buf) > self.window:
                del buf[0 : len(buf) - self.window]

        if self._last_t is not None and t > self._last_t and self._last_dr_ekf is not None:
            inst = (dr_vs_ekf - self._last_dr_ekf) / (t - self._last_t)
            self._rate = 0.8 * self._rate + 0.2 * inst
        self._last_t, self._last_dr_ekf = t, dr_vs_ekf

        stats = DriftStats(
            t=float(t),
            dr_vs_truth_m=dr_vs_truth,
            dr_vs_ekf_m=dr_vs_ekf,
            ekf_vs_truth_m=ekf_vs_truth,
            gnss_bias_estimate_m=float(np.mean(self._accepted_residuals))
            if self._accepted_residuals
            else 0.0,
            drift_rate_ms=float(self._rate),
        )
        self._last = stats
        return stats

    @property
    def last(self) -> Optional[DriftStats]:
        return self._last

    def estimated_drift_m(self) -> float:
        return float(np.mean(self._dr_vs_ekf)) if self._dr_vs_ekf else 0.0


class DriftCorrector:
    """Bounded, transparent correction of the dead-reckoning branch.

    ``gain`` is the fraction of the DR/EKF separation removed per correction
    step. Corrections are skipped while GNSS is untrusted unless
    ``trust_ekf_coast`` is set, because during an outage the EKF itself is only
    coasting on IMU data.
    """

    def __init__(
        self,
        gain: float = 0.08,
        max_correction_m: float = 3.0,
        trust_ekf_coast: bool = False,
    ) -> None:
        self.gain = float(np.clip(gain, 0.0, 1.0))
        self.max_correction_m = float(max_correction_m)
        self.trust_ekf_coast = bool(trust_ekf_coast)
        self.total_correction_m = 0.0
        self.corrections_applied = 0
        self.active = False

    def reset(self) -> None:
        self.total_correction_m = 0.0
        self.corrections_applied = 0
        self.active = False

    def compute(
        self,
        dr_en: Tuple[float, float],
        ekf_en: Tuple[float, float],
        gnss_trusted: bool,
    ) -> Tuple[float, float, bool]:
        """Return (de, dn, applied)."""
        if not gnss_trusted and not self.trust_ekf_coast:
            return 0.0, 0.0, False
        de = (ekf_en[0] - dr_en[0]) * self.gain
        dn = (ekf_en[1] - dr_en[1]) * self.gain
        mag = float(np.hypot(de, dn))
        if mag > self.max_correction_m:
            scale = self.max_correction_m / mag
            de, dn = de * scale, dn * scale
        if mag < 1e-4:
            return 0.0, 0.0, False
        self.total_correction_m += float(np.hypot(de, dn))
        self.corrections_applied += 1
        self.active = True
        return de, dn, True
