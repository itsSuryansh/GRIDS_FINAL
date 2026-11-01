"""Explainable GNSS anomaly detection.

Design goals
------------
* **No false alarms in nominal conditions.** Every threshold is expressed in
  terms of the configured GNSS noise level, so a clean run stays clean.
* **Explainable.** Each detector reports its own severity and a human-readable
  sentence; the API exposes the dominant reason.
* **Graduated response.** The response is not binary:
    - score <  ``warn``   : accept the fix normally,
    - score >= ``warn``   : accept but *down-weight* it (inflate the measurement
      noise in the EKF) and flag the channel as suspicious/degraded,
    - score >= ``reject`` : hard-reject the fix.

Detectors
---------
1. ``position_jump``  geodesic step between consecutive fixes inconsistent with
   the distance the vehicle could physically have travelled.
2. ``velocity``       implied ground speed over a ~1 s baseline inconsistent with
   the fused speed (noise-aware, because per-sample GNSS noise dominates at
   high update rates).
3. ``heading``        implied course inconsistent with the fused heading, with a
   circular tolerance derived from the position noise.
4. ``residual``       normalised innovation squared (NIS) / raw innovation
   magnitude from the EKF.
5. ``drift``          a *persistent* same-direction residual bias over a rolling
   window — the signature of a slow corruption that never trips a jump test.

A small persistent bias is not distinguishable from filter divergence by
residual testing alone. For that reason slow drift leads to down-weighting
first; a hard rejection only happens once the persistent bias is many times
the warning threshold. This is a statistical detector for *simulated* faults,
not a certified anti-spoofing product.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple

import numpy as np

from app.core.coordinate_utils import wrap_angle


@dataclass
class AnomalyResult:
    is_anomaly: bool
    score: float
    anomaly_type: str
    reason: str
    residual_m: float
    nis: Optional[float]
    reject: bool
    extra_sigma_m: float = 0.0     # >0 => down-weight the GNSS update
    severities: dict = None        # per-detector severities (explainability)

    def __post_init__(self) -> None:
        if self.severities is None:
            self.severities = {}


@dataclass
class DetectorThresholds:
    # measurement-noise aware tolerances
    gnss_sigma_m: float = 2.5
    jump_m: float = 25.0
    jump_margin_ms: float = 20.0

    velocity_baseline_s: float = 1.0
    velocity_excess_ms: float = 8.0

    heading_max_dps: float = 60.0

    nis_warn: float = 16.27        # chi2(2 dof, 0.999)
    nis_hard: float = 60.0

    residual_degraded_m: float = 10.0

    drift_window_s: float = 10.0
    # statistical significance multiplier for the windowed mean residual: the
    # mean of N independent fixes has standard error sigma/sqrt(N), so a mean
    # residual of a few metres over a 10 s window is already significant even
    # though every individual fix looks plausible
    drift_significance: float = 5.0
    drift_warn_m: float = 3.0
    drift_reject_factor: float = 2.5

    # if our own position uncertainty is this large (e.g. long coasting) a
    # persistent residual may be our divergence rather than a GNSS fault, so a
    # hard rejection is not justified -- only down-weighting is applied
    low_confidence_m: float = 60.0

    # policy for a *persistent bias* (slow drift). "downweight" keeps fusing the
    # fix with a heavily inflated noise model instead of dropping it, which is
    # usually better than pure inertial coasting when the bias is comparable to
    # the expected inertial drift.
    drift_policy: str = "reject"

    warn_score: float = 0.45
    reject_score: float = 0.85

    # hysteresis: after an anomaly, keep distrusting GNSS until innovations are
    # small again for a short hold period (prevents a corrupted solution from
    # "walking back in" one accepted fix at a time)
    hold_min_s: float = 1.5
    hold_max_s: float = 45.0


class GnssAnomalyDetector:
    def __init__(self, thresholds: Optional[DetectorThresholds] = None) -> None:
        self.th = thresholds or DetectorThresholds()
        self.reset()

    def reset(self) -> None:
        self.prev_gnss: Optional[Tuple[float, float, float]] = None
        self.track: Deque[Tuple[float, float, float]] = deque(maxlen=600)  # t, e, n
        self.residual_track: Deque[Tuple[float, float, float]] = deque(maxlen=1200)
        self.last_result: Optional[AnomalyResult] = None
        self.detections = 0
        self.rejections = 0
        self.downweights = 0
        self._hold_until: float = 0.0
        self._hold_armed_at: float = 0.0

    # ------------------------------------------------------------------ core ---
    def evaluate(
        self,
        t: float,
        gnss_en: Optional[Tuple[float, float]],
        ekf_en: Tuple[float, float],
        uncertainty_m: float,
        nis: Optional[float],
        fused_speed: float,
        fused_heading: float,
        heading_rate: float,
    ) -> AnomalyResult:
        th = self.th
        if gnss_en is None:
            res = AnomalyResult(
                is_anomaly=False,
                score=0.0,
                anomaly_type="none",
                reason="GNSS unavailable - inertial prediction only",
                residual_m=0.0,
                nis=None,
                reject=False,
            )
            self.last_result = res
            self.prev_gnss = None
            self.track.clear()
            return res

        ge, gn = float(gnss_en[0]), float(gnss_en[1])
        de, dn = ge - ekf_en[0], gn - ekf_en[1]
        residual = float(np.hypot(de, dn))
        sig = max(0.5, th.gnss_sigma_m)
        sev: dict[str, float] = {}
        why: dict[str, str] = {}

        # ---------------- 1. position jump ----------------
        sev_jump = 0.0
        if self.prev_gnss is not None:
            pe, pn, pt = self.prev_gnss
            gap = max(t - pt, 1e-3)
            jump = float(np.hypot(ge - pe, gn - pn))
            allowed = th.jump_m + 6.0 * sig + (abs(fused_speed) + th.jump_margin_ms) * gap
            over = jump - allowed
            sev_jump = float(np.clip(over / max(0.4 * allowed, 5.0), 0.0, 1.0))
            if over > 0:
                why["position_jump"] = (
                    f"position step of {jump:.1f} m in {gap:.2f} s exceeds "
                    f"the {allowed:.1f} m physical bound"
                )

            # ---------------- 2. implied velocity (windowed) ----------------
            self.track.append((t, ge, gn))
            window = [p for p in self.track if p[0] >= t - th.velocity_baseline_s]
            if len(window) >= 2 and (t - window[0][0]) >= 0.5 * th.velocity_baseline_s:
                dt_w = max(t - window[0][0], 1e-3)
                implied = float(np.hypot(ge - window[0][1], gn - window[0][2])) / dt_w
                tol = abs(fused_speed) + th.velocity_excess_ms + 3.0 * sig * np.sqrt(2.0) / dt_w
                over_v = implied - tol
                sev_vel = float(np.clip(over_v / max(0.4 * tol, 4.0), 0.0, 1.0))
                if over_v > 0:
                    why["velocity"] = (
                        f"implied ground speed {implied:.1f} m/s vs fused "
                        f"{abs(fused_speed):.1f} m/s over {dt_w:.1f} s"
                    )
                sev["velocity"] = sev_vel

            # ---------------- 3. heading consistency ----------------
            # Course between two fixes is only meaningful when the displacement
            # clearly exceeds the position noise; otherwise the test is skipped.
            min_course_step = 4.0 * sig * np.sqrt(2.0)
            if jump > min_course_step and abs(fused_speed) > 1.5:
                course = float(np.arctan2(gn - pn, ge - pe))
                expected = wrap_angle(fused_heading + heading_rate * (t - pt) * 0.5)
                circle_tol = float(np.arctan2(3.0 * sig * np.sqrt(2.0), jump))
                max_turn = np.radians(th.heading_max_dps) * gap + circle_tol + 0.15
                turn = abs(wrap_angle(course - expected))
                over_h = turn - max_turn
                sev_h = float(np.clip(over_h / max(0.4 * max_turn, 0.05), 0.0, 1.0))
                if over_h > 0:
                    why["heading"] = (
                        f"GNSS course {np.degrees(course):.0f} deg disagrees with fused "
                        f"{np.degrees(wrap_angle(fused_heading)) % 360:.0f} deg "
                        f"(tolerance {np.degrees(max_turn):.0f} deg)"
                    )
                sev["heading"] = sev_h

            self.prev_gnss = (ge, gn, t)
        else:
            self.prev_gnss = (ge, gn, t)
            self.track.append((t, ge, gn))
        for key in ("velocity", "heading"):
            sev.setdefault(key, 0.0)
        sev["position_jump"] = sev_jump
        why.setdefault("position_jump", "no abnormal step")

        # ---------------- 4. innovation / residual ----------------
        if nis is not None and np.isfinite(nis):
            sev_res = float(np.clip(nis / max(th.nis_warn, 1e-6), 0.0, 1.0))
            why["residual"] = f"innovation residual {residual:.1f} m (NIS {nis:.1f})"
        else:
            scale = max(4.0 * sig, 0.25 * max(uncertainty_m, 1.0))
            sev_res = float(np.clip(residual / scale, 0.0, 1.0))
            why["residual"] = f"innovation residual {residual:.1f} m"
        sev["residual"] = sev_res

        # ---------------- 5. persistent drift ----------------
        self.residual_track.append((t, de, dn))
        window_r = [r for r in self.residual_track if r[0] >= t - th.drift_window_s]
        n_win = len(window_r)
        if n_win >= 10:
            mean_vec = np.mean([[r[1], r[2]] for r in window_r], axis=0)
        else:
            mean_vec = np.zeros(2)
        drift_mag = float(np.hypot(mean_vec[0], mean_vec[1]))
        # significance floor: a windowed mean must clearly exceed the standard
        # error of the GNSS noise before it counts as a persistent bias
        noise_floor = th.drift_significance * sig / math.sqrt(max(n_win, 1))
        threshold = max(th.drift_warn_m, noise_floor)
        sev_drift = float(np.clip((drift_mag - threshold) / max(threshold, 1e-6), 0.0, 1.0))
        if sev_drift > 0:
            why["drift"] = (
                f"persistent residual bias of {drift_mag:.1f} m over "
                f"{th.drift_window_s:.0f} s (significance floor {threshold:.1f} m)"
            )
        sev["drift"] = sev_drift

        # ---------------- combine + decision ----------------
        dominant = max(sev, key=lambda k: sev[k])
        score = float(np.clip(sev[dominant], 0.0, 1.0))
        transient = max(sev_jump, sev.get("velocity", 0.0), sev.get("heading", 0.0))

        reject = False
        extra_sigma = 0.0
        if transient >= th.reject_score:
            # kinematic impossibility: the fix cannot be physically real
            reject = True
            dominant = max(("position_jump", "velocity", "heading"), key=lambda k: sev.get(k, 0.0))
        elif (
            th.drift_policy == "reject"
            and sev_drift >= th.warn_score
            and drift_mag > th.drift_warn_m
            and uncertainty_m <= th.low_confidence_m
        ):
            # a residual bias that persists for a whole window is not noise:
            # the channel is untrustworthy, so coast on inertial data instead
            reject = True
            dominant = "drift"
        elif nis is not None and np.isfinite(nis) and nis > th.nis_hard:
            reject = True
            dominant = "residual"
        elif score >= th.warn_score:
            # down-weight: inflate the measurement noise for this update
            extra_sigma = sig * (2.0 + 6.0 * score)
            if dominant == "drift":
                # a persistent bias gets a much weaker weight instead of a
                # rejection: the filter keeps a bounded amount of GNSS
                # information without being dragged onto the corrupted track
                extra_sigma = sig * (8.0 + 40.0 * score)
            self.downweights += 1

        # ---- hysteresis / distrust hold ----
        severe = reject or (sev_drift >= th.warn_score) or (transient >= th.warn_score)
        if severe:
            self._hold_armed_at = t
            self._hold_until = t + th.hold_min_s
        elif self._hold_until > t:
            # still holding: release early only if the innovation is small
            if nis is not None and np.isfinite(nis) and nis < th.nis_warn and t > self._hold_until:
                self._hold_until = t
            else:
                reject = True
                extra_sigma = 0.0
                dominant = "hold"
                score = max(score, th.warn_score)
                if t - self._hold_armed_at > th.hold_max_s:
                    self._hold_until = t
        # extend the hold window while the anomaly persists
        if severe:
            self._hold_until = min(
                max(self._hold_until, t + th.hold_min_s), self._hold_armed_at + th.hold_max_s
            )

        is_anomaly = bool(score >= th.warn_score or reject)
        if reject:
            self.rejections += 1
        if is_anomaly:
            self.detections += 1

        if reject and dominant == "hold":
            anomaly_type = "hold"
            reason = (
                "GNSS held out: recent anomaly on this channel, waiting for the "
                "innovation to return inside the gate"
            )
        elif reject:
            anomaly_type = dominant if dominant != "none" else "residual"
            reason = "GNSS rejected: " + why.get(anomaly_type, f"{anomaly_type} anomaly")
        elif is_anomaly:
            anomaly_type = dominant
            reason = "GNSS down-weighted: " + why.get(anomaly_type, f"{anomaly_type} anomaly")
        else:
            anomaly_type = "none"
            reason = (
                f"nominal: {why['residual']}"
                if residual <= th.residual_degraded_m
                else f"elevated {why['residual']}"
            )

        res = AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            anomaly_type=anomaly_type,
            reason=reason,
            residual_m=residual,
            nis=float(nis) if nis is not None else None,
            reject=reject,
            extra_sigma_m=extra_sigma,
            severities={k: round(v, 3) for k, v in sev.items()},
        )
        self.last_result = res
        return res

    # ----------------------------------------------------------- GNSS status ---
    def status(
        self,
        available: bool,
        residual_m: Optional[float],
        result: Optional[AnomalyResult] = None,
    ) -> str:
        if not available:
            return "unavailable"
        r = result or self.last_result
        if r is not None and r.reject:
            return "suspicious"
        if r is not None and r.is_anomaly:
            return "degraded"
        if residual_m is not None and residual_m > self.th.residual_degraded_m:
            return "degraded"
        return "healthy"
