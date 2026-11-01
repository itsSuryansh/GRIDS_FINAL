"""ML correction layer: gradient-boosted residual correction on top of the EKF.

Features are constructed only from information available at run time:

    [ innovation_e, innovation_n, gnss_available, nis, uncertainty_m,
      speed, |yaw_rate|, time_since_gnss, residual_m, rejected, anomaly_score ]

The target is the EKF position residual (EKF minus truth) at the same instant,
so the model learns a *correction* (in metres, EN) that is applied to the EKF
position. If GNSS is unavailable the model is not applied at all.

This module is optional and disabled by default: it is an experimental layer.
``train.py`` evaluates it against the EKF baseline on held-out sessions and the
evaluation report (``eval_report.json``) states whether it actually helps. The
dashboard surfaces that report rather than assuming an improvement.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import joblib
import numpy as np

from app.config import settings

FEATURE_NAMES = [
    "innovation_e",
    "innovation_n",
    "gnss_available",
    "nis",
    "uncertainty_m",
    "speed",
    "abs_yaw_rate",
    "time_since_gnss",
    "residual_m",
    "rejected",
    "anomaly_score",
]

MODEL_NAME = "grids_ml_correction"
MAX_CORRECTION_M = 40.0


class ResidualFeatures:
    """Feature builder shared by training and inference."""

    @staticmethod
    def build(
        innovation: Tuple[float, float],
        gnss_available: bool,
        nis: Optional[float],
        uncertainty_m: float,
        speed: float,
        yaw_rate: float,
        time_since_gnss: float,
        residual_m: float,
        rejected: bool,
        anomaly_score: float,
    ) -> np.ndarray:
        nis_val = 0.0 if (nis is None or not np.isfinite(nis)) else min(float(nis), 1e4)
        return np.array(
            [
                float(np.clip(innovation[0], -500, 500)),
                float(np.clip(innovation[1], -500, 500)),
                1.0 if gnss_available else 0.0,
                nis_val,
                float(np.clip(uncertainty_m, 0, 500)),
                float(np.clip(speed, 0, 100)),
                float(abs(yaw_rate)),
                float(np.clip(time_since_gnss, 0, 300)),
                float(np.clip(residual_m, 0, 500)),
                1.0 if rejected else 0.0,
                float(np.clip(anomaly_score, 0, 1)),
            ],
            dtype=float,
        )


@dataclass
class MlCorrection:
    applied: bool
    de: float
    dn: float
    reason: str


class MlCorrectionModel:
    """Wrapper around a scikit-learn regressor trained by ``ml/train.py``."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or settings.ml_model_path
        self.model = None
        self.report: dict = {}
        self.loaded = False
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self.path):
                bundle = joblib.load(self.path)
                self.model = bundle.get("model")
                self.report = bundle.get("report", {})
                self.loaded = self.model is not None
        except Exception:  # pragma: no cover - corrupt artifact should not crash
            self.model = None
            self.loaded = False

    @property
    def available(self) -> bool:
        return self.loaded and self.model is not None

    def predict(
        self,
        innovation: Tuple[float, float],
        gnss_available: bool,
        nis: Optional[float],
        uncertainty_m: float,
        speed: float,
        yaw_rate: float,
        time_since_gnss: float,
        residual_m: float,
        rejected: bool,
        anomaly_score: float,
    ) -> MlCorrection:
        if not self.available:
            return MlCorrection(False, 0.0, 0.0, "model not available")
        if not gnss_available:
            return MlCorrection(False, 0.0, 0.0, "GNSS unavailable - correction suppressed")
        x = ResidualFeatures.build(
            innovation, gnss_available, nis, uncertainty_m, speed, yaw_rate,
            time_since_gnss, residual_m, rejected, anomaly_score,
        ).reshape(1, -1)
        try:
            pred = np.asarray(self.model.predict(x), dtype=float).ravel()
        except Exception:  # pragma: no cover
            return MlCorrection(False, 0.0, 0.0, "model inference failed")
        de, dn = float(pred[0]), float(pred[1])
        mag = float(np.hypot(de, dn))
        if mag > MAX_CORRECTION_M:
            de *= MAX_CORRECTION_M / mag
            dn *= MAX_CORRECTION_M / mag
        return MlCorrection(True, -de, -dn, "residual correction applied")

    def summary(self) -> dict:
        return {
            "available": self.available,
            "model": MODEL_NAME,
            "evaluation": self.report,
        }
