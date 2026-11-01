"""Analytics: per-algorithm comparison, outage recovery, session reports."""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from app.services.navigation_service import EngineFrame
from app.utils.metrics import error_stats, outage_recovery_metrics


ALGO_LABELS = {
    "gnss": "GNSS (raw)",
    "dead_reckoning": "Dead Reckoning",
    "ekf_nomap": "EKF (no map aiding)",
    "ekf": "EKF Fusion (GRIDS)",
    "ekf_ml": "EKF + ML correction",
    "rts_smoothed": "RTS smoothed (post-processed)",
}


def _algo_metrics(frames: List[EngineFrame]) -> Dict[str, dict]:
    def collect(attr: str) -> List[float]:
        return [getattr(f, attr) for f in frames if getattr(f, attr) is not None]

    return {
        "gnss": error_stats(collect("gnss_error_m")).to_dict(),
        "dead_reckoning": error_stats(collect("dr_error_m")).to_dict(),
        "ekf_nomap": error_stats(collect("nomap_error_m")).to_dict(),
        "ekf": error_stats(collect("ekf_error_m")).to_dict(),
        "ekf_ml": error_stats(collect("ml_error_m")).to_dict(),
        "rts_smoothed": error_stats(collect("sm_error_m")).to_dict(),
    }


def compare_report(
    frames: List[EngineFrame],
    scenario: str,
    session_id: Optional[int] = None,
    run_id: Optional[str] = None,
    outage: Optional[tuple] = None,
) -> dict:
    """Fair comparison: every algorithm is scored at the same timestamps
    against the same ground-truth reference."""
    frames = [f for f in frames if f is not None]
    algorithms = _algo_metrics(frames)

    # availability-weighted counts so a partly unavailable channel is honest
    gnss_frames = [f for f in frames if f.gnss_error_m is not None]
    ml_frames = [f for f in frames if f.ml_error_m is not None]

    anomalies = [f for f in frames if f.anomaly]
    rejected = frames[-1].rejected_count if frames else 0

    notes: List[str] = []
    notes.append(
        f"All algorithms scored against the same simulated ground truth at "
        f"{len(frames)} synchronised timestamps."
    )
    if len(gnss_frames) < len(frames):
        notes.append(
            f"GNSS was unavailable for {len(frames) - len(gnss_frames)} of "
            f"{len(frames)} samples, so its metrics cover only available fixes."
        )
    if not ml_frames:
        notes.append("ML correction was disabled for this run (no samples).")
    notes.append("These are simulation results and do not establish real-world accuracy.")

    times = [f.t for f in frames]
    ekf_errors = [f.ekf_error_m for f in frames]
    recovery = {}
    if outage is not None:
        recovery = outage_recovery_metrics(
            times=times,
            ekf_errors=ekf_errors,
            outage_start=outage[0] if outage else None,
            outage_end=outage[1] if outage else None,
            gnss_available=[f.gnss_available for f in frames],
        )

    dr_rmse = algorithms["dead_reckoning"]["rmse_m"]
    ekf_rmse = algorithms["ekf"]["rmse_m"]
    gnss_rmse = algorithms["gnss"]["rmse_m"]
    ml_rmse = algorithms["ekf_ml"]["rmse_m"]
    nomap_rmse = algorithms["ekf_nomap"]["rmse_m"]
    sm_rmse = algorithms["rts_smoothed"]["rmse_m"]

    return {
        "session_id": session_id,
        "run_id": run_id,
        "scenario": scenario,
        "ground_truth_samples": len(frames),
        "algorithms": algorithms,
        "outage": {
            "start_s": float(outage[0]) if outage else None,
            "end_s": float(outage[1]) if outage else None,
        },
        "recovery": recovery,
        "anomalies": {
            "detected": len(anomalies),
            "rejected_measurements": int(rejected),
            "gnss_samples_available": len(gnss_frames),
        },
        "deltas": {
            "ekf_vs_gnss_rmse_m": round(gnss_rmse - ekf_rmse, 3) if gnss_rmse else 0.0,
            "ekf_vs_dr_rmse_m": round(dr_rmse - ekf_rmse, 3),
            "ml_vs_ekf_rmse_m": round(ekf_rmse - ml_rmse, 3) if ml_rmse else None,
            "map_vs_nomap_rmse_m": round(nomap_rmse - ekf_rmse, 3) if nomap_rmse else None,
            "smoothing_vs_ekf_rmse_m": round(ekf_rmse - sm_rmse, 3) if sm_rmse else None,
        },
        "notes": notes,
    }


def timeseries_for_charts(frames: List[EngineFrame], max_points: int = 600) -> List[dict]:
    """Down-sample frames for chart payloads (keeps the API light)."""
    if not frames:
        return []
    n = len(frames)
    step = max(1, n // max_points)
    out = []
    for i in range(0, n, step):
        f = frames[i]
        out.append(
            {
                "t": round(f.t, 2),
                "ekf_error_m": round(f.ekf_error_m, 2),
                "dr_error_m": round(f.dr_error_m, 2),
                "gnss_error_m": None if f.gnss_error_m is None else round(f.gnss_error_m, 2),
                "ml_error_m": None if f.ml_error_m is None else round(f.ml_error_m, 2),
                "sm_error_m": None if f.sm_error_m is None else round(f.sm_error_m, 2),
                "nomap_error_m": None if f.nomap_error_m is None else round(f.nomap_error_m, 2),
                "gnss_residual_m": None if f.gnss_residual_m is None else round(f.gnss_residual_m, 2),
                "speed_ms": round(f.speed, 2),
                "drift_m": round(f.drift_estimate_m, 2),
                "uncertainty_m": round(f.uncertainty_m, 2),
                "anomaly_score": round(f.anomaly_score, 3),
                "gnss_available": f.gnss_available,
            }
        )
    return out


def live_summary(frames: List[EngineFrame]) -> dict:
    """Running numbers for the live dashboard (backend-computed, not mocked)."""
    if not frames:
        return {
            "samples": 0,
            "ekf_rmse_m": 0.0,
            "dr_rmse_m": 0.0,
            "gnss_rmse_m": 0.0,
            "max_ekf_error_m": 0.0,
            "mean_ekf_error_m": 0.0,
            "anomalies": 0,
            "rejected": 0,
            "gnss_availability_pct": 0.0,
        }
    gnss_available = [f for f in frames if f.gnss_available]
    return {
        "samples": len(frames),
        "ekf_rmse_m": round(error_stats([f.ekf_error_m for f in frames]).rmse_m, 3),
        "smoothed_rmse_m": round(error_stats([f.sm_error_m for f in frames]).rmse_m, 3),
        "dr_rmse_m": round(error_stats([f.dr_error_m for f in frames]).rmse_m, 3),
        "gnss_rmse_m": round(error_stats([f.gnss_error_m for f in frames]).rmse_m, 3),
        "max_ekf_error_m": round(max(f.ekf_error_m for f in frames), 3),
        "mean_ekf_error_m": round(float(np.mean([f.ekf_error_m for f in frames])), 3),
        "anomalies": int(sum(1 for f in frames if f.anomaly)),
        "rejected": int(frames[-1].rejected_count),
        "gnss_availability_pct": round(100.0 * len(gnss_available) / len(frames), 1),
    }
