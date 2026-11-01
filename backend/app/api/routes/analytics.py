"""Analytics: live summary, algorithm comparison, stored sessions."""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.database import AnomalyEvent, NavigationResult, PerformanceMetric, SimulationSession
from app.models.database_setup import get_db
from app.ml.inference import model_summary
from app.services.analytics_service import compare_report, live_summary, timeseries_for_charts
from app.services.simulation_service import simulation_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def summary() -> dict:
    """Live performance summary of the current run (ground truth based)."""
    run = simulation_service.run
    if run is None or not run.engine.frames:
        return {"available": False, "summary": None, "message": "no simulation data"}
    return {
        "available": True,
        "run_id": run.run_id,
        "session_id": run.session_id,
        "scenario": run.config.scenario.scenario.value,
        "summary": live_summary(run.engine.frames),
        "notes": ["Metrics computed against the simulated ground truth."],
    }


@router.get("/compare")
def compare(include_series: bool = Query(True)) -> dict:
    """Full algorithm comparison for the active run."""
    run = simulation_service.run
    if run is None or not run.engine.frames:
        raise HTTPException(status_code=404, detail="no simulation data available")
    report = compare_report(
        run.engine.frames,
        scenario=run.config.scenario.scenario.value,
        session_id=run.session_id,
        run_id=run.run_id,
        outage=run.engine.outage_window(),
    )
    if include_series:
        report["series"] = timeseries_for_charts(run.engine.frames)
    return report


@router.get("/ml")
def ml_status() -> dict:
    """Status and held-out evaluation of the optional ML correction layer."""
    return model_summary()


@router.get("/sessions")
def sessions(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> dict:
    """Previously persisted simulation sessions with their metrics."""
    rows = db.execute(
        select(SimulationSession).order_by(SimulationSession.id.desc()).limit(limit)
    ).scalars().all()
    out = []
    for s in rows:
        metrics = {
            m.algorithm: {
                "mae_m": round(m.mae_m, 3),
                "rmse_m": round(m.rmse_m, 3),
                "max_m": round(m.max_m, 3),
                "p95_m": round(m.p95_m, 3),
                "samples": m.samples,
            }
            for m in s.metrics
        }
        item = s.to_summary()
        item["metrics"] = metrics
        out.append(item)
    return {"count": len(out), "sessions": out}


@router.get("/sessions/{session_id}")
def session_detail(session_id: int, db: Session = Depends(get_db)) -> dict:
    """Full stored record of one session: config, metrics, anomalies, series."""
    s = db.get(SimulationSession, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")

    metrics = {}
    for m in s.metrics:
        metrics[m.algorithm] = {
            "mae_m": m.mae_m,
            "rmse_m": m.rmse_m,
            "max_m": m.max_m,
            "p95_m": m.p95_m,
            "mean_m": m.mean_m,
            "samples": m.samples,
            "extras": json.loads(m.extras_json or "{}"),
        }

    batches = db.execute(
        select(NavigationResult)
        .where(NavigationResult.session_id == session_id)
        .order_by(NavigationResult.batch_index)
    ).scalars().all()

    # merge columnar payloads and return a down-sampled series
    merged: dict = {}
    for b in batches:
        for k, v in b.as_columns().items():
            merged.setdefault(k, []).extend(v)
    n = len(merged.get("t", []))
    stride = max(1, n // 800)
    series = []
    for i in range(0, n, stride):
        series.append(
            {
                "t": merged["t"][i],
                "truth_lat": merged["truth_lat"][i],
                "truth_lon": merged["truth_lon"][i],
                "ekf_lat": merged["ekf_lat"][i],
                "ekf_lon": merged["ekf_lon"][i],
                "dr_lat": merged["dr_lat"][i],
                "dr_lon": merged["dr_lon"][i],
                "gnss_lat": merged["gnss_lat"][i],
                "gnss_lon": merged["gnss_lon"][i],
                "ekf_error_m": merged["ekf_error_m"][i],
                "dr_error_m": merged["dr_error_m"][i],
                "gnss_error_m": merged["gnss_error_m"][i],
                "anomaly_score": merged["anomaly_score"][i],
            }
        )

    anomalies = db.execute(
        select(AnomalyEvent)
        .where(AnomalyEvent.session_id == session_id)
        .order_by(AnomalyEvent.t)
        .limit(400)
    ).scalars().all()

    return {
        "session": s.to_summary(),
        "config": s.config,
        "metrics": metrics,
        "sample_count": n,
        "series": series,
        "anomalies": [
            {
                "t": a.t,
                "type": a.anomaly_type,
                "score": a.score,
                "reason": a.reason,
                "residual_m": a.residual_m,
                "rejected": bool(a.rejected),
            }
            for a in anomalies
        ],
    }
