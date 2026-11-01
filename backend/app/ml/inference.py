"""ML inference facade used by the navigation engine."""
from __future__ import annotations

from typing import Optional

from app.ml.model import MlCorrection, MlCorrectionModel, MODEL_NAME, ResidualFeatures

_singleton: Optional[MlCorrectionModel] = None


def get_model(reload: bool = False) -> MlCorrectionModel:
    global _singleton
    if _singleton is None or reload:
        _singleton = MlCorrectionModel()
    return _singleton


def model_summary() -> dict:
    return get_model().summary()


__all__ = ["get_model", "model_summary", "MlCorrection", "ResidualFeatures", "MODEL_NAME"]
