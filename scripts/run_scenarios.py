#!/usr/bin/env python3
"""Headless scenario benchmark for GRIDS.

Runs every built-in scenario end to end without the UI, stores the sessions in
SQLite and prints the comparison table. Useful for regression checks and for
generating the numbers quoted in the documentation.

    python scripts/run_scenarios.py --duration 120 --seed 42
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(ROOT))

from app.models.database_setup import init_db  # noqa: E402
from app.models.schemas import (  # noqa: E402
    RoutePattern,
    ScenarioConfig,
    ScenarioType,
    SimulatorConfig,
)
from app.services.analytics_service import compare_report  # noqa: E402
from app.services.simulation_service import SimulationService  # noqa: E402

CASES = [
    ("normal", ScenarioType.NORMAL, RoutePattern.CURVED, {}),
    ("normal-road", ScenarioType.NORMAL, RoutePattern.ROAD, {}),
    ("outage", ScenarioType.OUTAGE, RoutePattern.CURVED,
     dict(outage_start_s=30.0, outage_duration_s=40.0)),
    ("outage-road", ScenarioType.OUTAGE, RoutePattern.ROAD,
     dict(outage_start_s=30.0, outage_duration_s=40.0)),
    ("drift", ScenarioType.DRIFT, RoutePattern.STRAIGHT,
     dict(drift_onset_s=20.0, drift_rate_ms=0.4, drift_max_m=150.0)),
    ("spoofing", ScenarioType.SPOOFING, RoutePattern.LEFT_TURN,
     dict(spoof_onset_s=25.0, spoof_jump_m=70.0, spoof_drift_ms=1.0)),
    ("spoofing-road", ScenarioType.SPOOFING, RoutePattern.ROAD,
     dict(spoof_onset_s=25.0, spoof_jump_m=70.0, spoof_drift_ms=1.0)),
    ("complex", ScenarioType.OUTAGE, RoutePattern.RANDOM,
     dict(outage_start_s=35.0, outage_duration_s=25.0)),
]

ORDER = ["gnss", "dead_reckoning", "ekf_nomap", "ekf", "rts_smoothed"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--persist", action="store_true", help="store sessions in SQLite")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    init_db()
    rows = []
    for name, scen, pattern, extra in CASES:
        cfg = SimulatorConfig(
            scenario=ScenarioConfig(scenario=scen, **extra),
            route_pattern=pattern,
            duration_s=args.duration,
            rate_hz=10.0,
            speed_ms=14.0,
        )
        engine = SimulationService.run_offline(cfg, seed=args.seed)
        report = compare_report(engine.frames, scenario=name, outage=engine.outage_window())
        session_id = None
        if args.persist:
            session_id = SimulationService.persist_offline(engine, cfg, name=name)
        rows.append(
            {
                "scenario": name,
                "session_id": session_id,
                "frames": report["ground_truth_samples"],
                "rmse": {k: round(v["rmse_m"], 2) for k, v in report["algorithms"].items()},
                "deltas": {k: (round(v, 2) if isinstance(v, (int, float)) else v)
                           for k, v in (report.get("deltas") or {}).items()},
                "rejected": report["anomalies"]["rejected_measurements"],
                "anomalies": report["anomalies"],
                "recovery": report.get("recovery"),
            }
        )

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    print(f"\nGRIDS headless benchmark  (duration={args.duration}s, seed={args.seed})")
    print("All figures are simulated and scored against the simulator's ground truth.\n")
    header = (
        f"{'scenario':<14}{'GNSS':>8}{'DR':>8}{'EKF-nomap':>11}{'EKF':>8}"
        f"{'RTS':>8}{'mapAid':>9}{'smooth':>9}{'rej':>7}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        rm = r["rmse"]
        d = r["deltas"]
        print(
            f"{r['scenario']:<14}{rm['gnss']:>8.2f}{rm['dead_reckoning']:>8.2f}"
            f"{rm['ekf_nomap']:>11.2f}{rm['ekf']:>8.2f}{rm['rts_smoothed']:>8.2f}"
            f"{d.get('map_vs_nomap_rmse_m', 0):>9.2f}{d.get('smoothing_vs_ekf_rmse_m', 0):>9.2f}"
            f"{r['rejected']:>7}"
        )
    print("\nRMSE in metres, lower is better. mapAid/smooth are RMSE gains in metres")
    print("(positive = the extra stage helped on that run).")


if __name__ == "__main__":
    main()
