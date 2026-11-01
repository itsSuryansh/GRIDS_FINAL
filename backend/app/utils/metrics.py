"""Performance metrics computed against ground truth only.

All metrics operate on *synchronised* frames: every estimate is produced for the
same timestamp as the matching ground-truth sample, so comparisons are fair.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional, Sequence

import numpy as np


@dataclass
class ErrorStats:
    mae_m: float
    rmse_m: float
    max_m: float
    p95_m: float
    mean_m: float
    samples: int

    def to_dict(self) -> dict:
        return {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                for k, v in asdict(self).items()}


def error_stats(errors_m: Sequence[float]) -> ErrorStats:
    """Basic error statistics from a list of scalar error magnitudes."""
    arr = np.asarray([e for e in errors_m if e is not None and np.isfinite(e)], dtype=float)
    if arr.size == 0:
        return ErrorStats(0.0, 0.0, 0.0, 0.0, 0.0, 0)
    return ErrorStats(
        mae_m=float(np.mean(np.abs(arr))),
        rmse_m=float(np.sqrt(np.mean(arr ** 2))),
        max_m=float(np.max(arr)),
        p95_m=float(np.percentile(arr, 95)),
        mean_m=float(np.mean(arr)),
        samples=int(arr.size),
    )


def en_error(e_est: float, n_est: float, e_true: float, n_true: float) -> float:
    return float(np.hypot(e_est - e_true, n_est - n_true))


def horizontal_drms(east_err: Sequence[float], north_err: Sequence[float]) -> float:
    e = np.asarray(east_err, dtype=float)
    n = np.asarray(north_err, dtype=float)
    if e.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(e ** 2 + n ** 2)))


def cep95(east_err: Sequence[float], north_err: Sequence[float]) -> float:
    """95% circular error probability (empirical)."""
    e = np.asarray(east_err, dtype=float)
    n = np.asarray(north_err, dtype=float)
    if e.size == 0:
        return 0.0
    return float(np.percentile(np.hypot(e, n), 95))


def outage_recovery_metrics(
    times: Sequence[float],
    ekf_errors: Sequence[float],
    outage_start: Optional[float],
    outage_end: Optional[float],
    gnss_available: Sequence[bool],
    window_s: float = 10.0,
) -> dict:
    """Error level at the end of the outage and seconds-to-recover after it.

    Recovery is defined as the first time after GNSS returns at which the EKF
    error falls below 10 m and stays below it for the remainder of the window.
    Returns ``{}`` when no outage occurred.
    """
    if outage_start is None or outage_end is None:
        return {}
    t = np.asarray(times, dtype=float)
    err = np.asarray(ekf_errors, dtype=float)
    if t.size == 0:
        return {}

    during = (t >= outage_start) & (t < outage_end)
    after = t >= outage_end
    if not np.any(during):
        return {}

    peak_during = float(np.max(err[during]))
    end_during = float(err[during][-1])
    recovery_time: Optional[float] = None

    idx_after = np.where(after)[0]
    threshold = 10.0
    for i in idx_after:
        remaining = err[i:]
        if remaining.size and np.all(remaining <= threshold):
            recovery_time = float(t[i] - outage_end)
            break

    # sustained drift rate during the outage (m/s)
    duration = max(1e-6, outage_end - outage_start)
    drift_rate = (end_during - float(err[during][0])) / duration

    return {
        "outage_start_s": float(outage_start),
        "outage_end_s": float(outage_end),
        "peak_error_during_outage_m": peak_during,
        "error_at_outage_end_m": end_during,
        "drift_rate_during_outage_ms": float(drift_rate),
        "recovery_time_s": recovery_time,
        "recovery_threshold_m": threshold,
    }


def summarise_frames(
    frames: Iterable[dict], algorithms: Sequence[str] = ("gnss", "dead_reckoning", "ekf", "ekf_ml")
) -> dict:
    """Compute per-algorithm metrics from a list of frame dicts.

    Each frame must contain ``t``, ``truth_e``, ``truth_n`` and
    ``<algo>_e`` / ``<algo>_n`` keys (None allowed when unavailable).
    """
    frames = list(frames)
    out: dict = {}
    for algo in algorithms:
        errs: List[float] = []
        for f in frames:
            e, n = f.get(f"{algo}_e"), f.get(f"{algo}_n")
            if e is None or n is None:
                continue
            errs.append(float(np.hypot(e - f["truth_e"], n - f["truth_n"])))
        out[algo] = error_stats(errs)
    return out
