"""Train and honestly evaluate the optional ML residual-correction layer.

The model predicts the EKF position residual (EKF minus truth) in local EN
metres from run-time observables (innovation, NIS, uncertainty, motion state).
It is only useful if it improves on the EKF baseline on *held-out* sessions
from different random seeds, which is exactly what this script measures.

Usage
-----
    python -m app.ml.train --sessions 6 --duration 90

Artifacts
---------
    ml_artifacts/ml_correction.joblib   model + held-out evaluation report
    ml_artifacts/eval_report.json       the report on its own (served by the API)

The dashboard reads that report and shows the measured delta; it never assumes
an improvement.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List, Tuple

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.multioutput import MultiOutputRegressor

from app.config import settings
from app.ml.model import FEATURE_NAMES, MODEL_NAME, ResidualFeatures
from app.models.schemas import RoutePattern, ScenarioConfig, ScenarioType, SimulatorConfig
from app.services.navigation_service import NavigationEngine
from app.utils.logging import get_logger

log = get_logger("grids.ml.train")

SCENARIO_MIX: List[Tuple[ScenarioType, RoutePattern]] = [
    (ScenarioType.NORMAL, RoutePattern.CURVED),
    (ScenarioType.OUTAGE, RoutePattern.CURVED),
    (ScenarioType.DRIFT, RoutePattern.STRAIGHT),
    (ScenarioType.SPOOFING, RoutePattern.LEFT_TURN),
    (ScenarioType.NORMAL, RoutePattern.RANDOM),
    (ScenarioType.OUTAGE, RoutePattern.CURVED),
]


def build_dataset(
    seeds: List[int], duration_s: float = 90.0, rate_hz: float = 10.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (X, Y, truth_en, ekf_en) for all frames of all sessions."""
    X, Y, T, E = [], [], [], []
    for i, seed in enumerate(seeds):
        scen, pattern = SCENARIO_MIX[i % len(SCENARIO_MIX)]
        cfg = SimulatorConfig(
            scenario=ScenarioConfig(scenario=scen),
            route_pattern=pattern,
            duration_s=duration_s,
            rate_hz=rate_hz,
            speed_ms=14.0,
        )
        engine = NavigationEngine(cfg, seed=seed)
        for _ in range(int(duration_s * rate_hz)):
            engine.step()
        for f in engine.frames:
            if f.innov_e is None:
                continue  # model only learns from frames with a GNSS fix
            X.append(
                ResidualFeatures.build(
                    innovation=(f.innov_e, f.innov_n),
                    gnss_available=f.gnss_available,
                    nis=f.nis,
                    uncertainty_m=f.uncertainty_m,
                    speed=f.speed,
                    yaw_rate=np.radians(f.yaw_rate_dps),
                    time_since_gnss=0.0,
                    residual_m=f.gnss_residual_m or 0.0,
                    rejected=f.gnss_status == "suspicious",
                    anomaly_score=f.anomaly_score,
                )
            )
            Y.append([f.ekf_e - f.truth_e, f.ekf_n - f.truth_n])
            T.append([f.truth_e, f.truth_n])
            E.append([f.ekf_e, f.ekf_n])
        log.info("dataset session seed=%s scenario=%s frames=%d", seed, scen.value, len(engine.frames))
    return (
        np.asarray(X, dtype=float),
        np.asarray(Y, dtype=float),
        np.asarray(T, dtype=float),
        np.asarray(E, dtype=float),
    )


def _metrics(err: np.ndarray) -> dict:
    mag = np.hypot(err[:, 0], err[:, 1])
    return {
        "rmse_m": round(float(np.sqrt(np.mean(mag ** 2))), 3),
        "mae_m": round(float(np.mean(np.abs(mag))), 3),
        "p95_m": round(float(np.percentile(mag, 95)), 3),
        "max_m": round(float(np.max(mag)), 3),
        "samples": int(mag.size),
    }


def train_and_evaluate(
    n_sessions: int = 6, duration_s: float = 90.0, rate_hz: float = 10.0
) -> dict:
    t0 = time.time()
    train_seeds = list(range(1, n_sessions + 1))
    test_seeds = list(range(101, 101 + max(3, n_sessions // 2)))

    log.info("building training dataset (%d sessions)", len(train_seeds))
    Xtr, Ytr, _, _ = build_dataset(train_seeds, duration_s, rate_hz)
    log.info("building held-out dataset (%d sessions)", len(test_seeds))
    Xte, Yte, Tte, Ete = build_dataset(test_seeds, duration_s, rate_hz)

    if len(Xtr) < 50 or len(Xte) < 50:
        raise RuntimeError("not enough samples to train")

    model = MultiOutputRegressor(
        GradientBoostingRegressor(
            n_estimators=260, learning_rate=0.05, max_depth=3, subsample=0.9,
            random_state=0,
        )
    )
    model.fit(Xtr, Ytr)

    pred = model.predict(Xte)
    corrected = Ete - pred              # correction = subtract predicted residual
    baseline_err = Ete - Tte
    corrected_err = corrected - Tte

    baseline = _metrics(baseline_err)
    corrected_m = _metrics(corrected_err)
    delta = round(baseline["rmse_m"] - corrected_m["rmse_m"], 3)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": MODEL_NAME,
        "estimator": "GradientBoostingRegressor (multi-output)",
        "features": FEATURE_NAMES,
        "training_sessions": len(train_seeds),
        "training_samples": int(len(Xtr)),
        "test_sessions": len(test_seeds),
        "test_samples": int(len(Xte)),
        "baseline_ekf": baseline,
        "corrected": corrected_m,
        "rmse_improvement_m": delta,
        "recommended_default": bool(delta > 0.05),
        "notes": [
            "Evaluated on held-out simulated sessions with unseen random seeds.",
            "A positive improvement means the ML layer reduced horizontal RMSE on "
            "those simulated sessions only.",
            "This is an experimental add-on: the EKF remains the baseline and the "
            "correction is disabled unless it demonstrably helps.",
        ],
        "train_wall_s": round(time.time() - t0, 1),
    }

    settings.ensure_dirs()
    Path(settings.ml_dataset_path).write_text(json.dumps(report, indent=2))
    joblib.dump({"model": model, "report": report, "features": FEATURE_NAMES},
                settings.ml_model_path)
    log.info("ML eval: baseline rmse=%.3f corrected=%.3f delta=%.3f",
             baseline["rmse_m"], corrected_m["rmse_m"], delta)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the GRIDS ML correction layer")
    ap.add_argument("--sessions", type=int, default=6)
    ap.add_argument("--duration", type=float, default=90.0)
    ap.add_argument("--rate", type=float, default=10.0)
    args = ap.parse_args()
    report = train_and_evaluate(args.sessions, args.duration, args.rate)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
