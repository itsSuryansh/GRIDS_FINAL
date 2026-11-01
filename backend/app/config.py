"""Application configuration for GRIDS.

All tunables are environment-overridable so the same code runs locally, in
Docker, and in tests. Nothing here depends on network access.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    """Lightweight settings object (no external dependency required)."""

    def __init__(self) -> None:
        self.app_name: str = "GRIDS"
        self.app_full_name: str = "GNSS-Resilient Intelligent Dead Reckoning System"
        self.version: str = "1.0.0"
        self.api_prefix: str = "/api"

        # --- storage ---
        default_db = BASE_DIR / "data" / "grids.db"
        self.database_url: str = os.getenv(
            "GRIDS_DATABASE_URL", f"sqlite:///{default_db}"
        )
        self.echo_sql: bool = os.getenv("GRIDS_ECHO_SQL", "0") == "1"

        # --- CORS / networking ---
        self.cors_origins: List[str] = [
            o.strip()
            for o in os.getenv(
                "GRIDS_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,"
                "http://localhost:4173,http://localhost:3000",
            ).split(",")
            if o.strip()
        ]
        # Vite proxy hosts (e2b preview) are allowed through regex below.
        self.cors_origin_regex: str = os.getenv(
            "GRIDS_CORS_ORIGIN_REGEX", r"https?://([a-zA-Z0-9\-\.]+)?(e2b\.app|localhost|127\.0\.0\.1)(:\d+)?"
        )

        # --- simulation defaults ---
        self.default_rate_hz: float = float(os.getenv("GRIDS_DEFAULT_RATE_HZ", "10"))
        self.min_rate_hz: float = 1.0
        self.max_rate_hz: float = 50.0
        self.max_duration_s: float = float(os.getenv("GRIDS_MAX_DURATION_S", "1800"))
        self.broadcast_every_n_steps: int = int(os.getenv("GRIDS_BROADCAST_EVERY", "1"))

        # --- persistence policy ---
        # High-frequency raw samples are NOT written row-by-row. Instead the
        # navigation service buffers rows and flushes in chunks.
        self.result_flush_rows: int = int(os.getenv("GRIDS_RESULT_FLUSH_ROWS", "250"))
        self.max_history_buffer: int = int(os.getenv("GRIDS_MAX_HISTORY", "20000"))

        # --- algorithms ---
        self.anomaly_innovation_gate: float = float(
            os.getenv("GRIDS_ANOMALY_NIS_GATE", "16.27")  # chi2(2 dof, 0.999)
        )
        self.anomaly_jump_threshold_m: float = float(
            os.getenv("GRIDS_ANOMALY_JUMP_M", "25.0")
        )
        self.ml_correction_enabled_default: bool = (
            os.getenv("GRIDS_ML_CORRECTION_DEFAULT", "0") == "1"
        )
        self.ml_model_path: str = os.getenv(
            "GRIDS_ML_MODEL_PATH", str(BASE_DIR / "ml_artifacts" / "ml_correction.joblib")
        )
        self.ml_dataset_path: str = os.getenv(
            "GRIDS_ML_DATASET_PATH", str(BASE_DIR / "ml_artifacts" / "eval_report.json")
        )

    def ensure_dirs(self) -> None:
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "ml_artifacts").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
