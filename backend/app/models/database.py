"""SQLAlchemy models. SQLite storage is deliberately coarse-grained:

* one row per simulation session (config + metadata)
* batched navigation results (flushed in chunks, never row-by-row)
* discrete anomaly events only
* one aggregated performance-metrics row per algorithm per session
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SimulationSession(Base):
    __tablename__ = "simulation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), default="GRIDS run")
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    scenario: Mapped[str] = mapped_column(String(32), index=True)
    route_pattern: Mapped[str] = mapped_column(String(32))
    config_json: Mapped[str] = mapped_column(Text)
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lon: Mapped[float] = mapped_column(Float)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    sim_time_s: Mapped[float] = mapped_column(Float, default=0.0)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="running")
    git_commit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    results: Mapped[list["NavigationResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )
    anomalies: Mapped[list["AnomalyEvent"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )
    metrics: Mapped[list["PerformanceMetric"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def config(self) -> Dict[str, Any]:
        return json.loads(self.config_json or "{}")

    def to_summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "scenario": self.scenario,
            "route_pattern": self.route_pattern,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "duration_s": self.sim_time_s or self.duration_s,
            "status": self.status,
            "notes": self.notes,
        }


class NavigationResult(Base):
    """Batched navigation frames (a chunk of ~N samples per row)."""

    __tablename__ = "navigation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("simulation_sessions.id"), index=True)
    batch_index: Mapped[int] = mapped_column(Integer, default=0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    t_start: Mapped[float] = mapped_column(Float, default=0.0)
    t_end: Mapped[float] = mapped_column(Float, default=0.0)
    # compact columnar payload (JSON lists) keeps the SQLite file small
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped[SimulationSession] = relationship(back_populates="results")

    def as_columns(self) -> Dict[str, list]:
        return json.loads(self.payload)


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("simulation_sessions.id"), index=True)
    t: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[float] = mapped_column(Float)
    anomaly_type: Mapped[str] = mapped_column(String(48))
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(240))
    residual_m: Mapped[float] = mapped_column(Float, default=0.0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)

    session: Mapped[SimulationSession] = relationship(back_populates="anomalies")


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("simulation_sessions.id"), index=True)
    algorithm: Mapped[str] = mapped_column(String(32))
    mae_m: Mapped[float] = mapped_column(Float)
    rmse_m: Mapped[float] = mapped_column(Float)
    max_m: Mapped[float] = mapped_column(Float)
    p95_m: Mapped[float] = mapped_column(Float)
    mean_m: Mapped[float] = mapped_column(Float)
    samples: Mapped[int] = mapped_column(Integer)
    extras_json: Mapped[str] = mapped_column(Text, default="{}")

    session: Mapped[SimulationSession] = relationship(back_populates="metrics")
