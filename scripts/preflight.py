#!/usr/bin/env python3
"""Check a GRIDS checkout before you run or deploy it.

    python3 scripts/preflight.py            # local run
    python3 scripts/preflight.py --vercel   # + deployment checks

Exits non-zero if something would definitely break, and prints what to do about
it. Read-only: it never starts servers or writes files (except nothing at all).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
problems: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def bad(msg: str) -> None:
    problems.append(msg)
    print(f"  \033[31m✗\033[0m {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  \033[33m!\033[0m {msg}")


def section(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")


def check_runtime() -> None:
    section("Runtime")
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11):
        ok(f"python {major}.{minor}")
    else:
        bad(f"python {major}.{minor} — need 3.11+")

    node = shutil.which("node")
    if not node:
        bad("node not found — install Node 18+ (https://nodejs.org)")
        return
    ver = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip()
    try:
        n = int(ver.lstrip("v").split(".")[0])
    except ValueError:
        n = 0
    (ok if n >= 18 else bad)(f"node {ver}{'' if n >= 18 else ' — need 18+'}")

    if shutil.which("npm"):
        ok("npm present")
    else:
        bad("npm not found")


def check_backend() -> None:
    section("Backend")
    if not (ROOT / "backend" / "requirements.txt").is_file():
        bad("backend/requirements.txt missing")
        return
    try:
        import fastapi  # noqa: F401
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import sqlalchemy  # noqa: F401
        ok("python dependencies importable")
    except Exception as exc:  # pragma: no cover - environment dependent
        bad(f"missing python deps ({exc.__class__.__name__}) — "
            f"pip install -r backend/requirements.txt")
        return

    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.core.scenarios import SCENARIOS  # noqa: WPS433

        ok(f"scenario catalogue loads ({len(SCENARIOS)} scenarios: "
           f"{', '.join(s.id.value for s in SCENARIOS)})")
    except Exception as exc:
        bad(f"cannot import app.core.scenarios: {exc}")

    data = ROOT / "backend" / "data"
    if data.is_dir():
        if (data / "grids.db").exists():
            ok("sqlite database present")
        else:
            warn("no database yet — it is created on first start")

        tiles = data / "tiles"
        cached = len(list(tiles.rglob("*.png"))) if tiles.is_dir() else 0
        if cached:
            ok(f"{cached} cached map tiles (offline basemap ready)")
        else:
            warn("no cached map tiles — the map needs a network for its first run, "
                 "or set GRIDS_MAP_ONLINE=0 for the offline graticule")
    else:
        warn("backend/data missing — created on first start")


def check_frontend() -> None:
    section("Frontend")
    if not (ROOT / "frontend" / "package.json").is_file():
        bad("frontend/package.json missing")
        return
    if (ROOT / "frontend" / "node_modules").is_dir():
        ok("node_modules installed")
    else:
        warn("node_modules missing — run: npm --prefix frontend install")
    dist = ROOT / "frontend" / "dist" / "index.html"
    if dist.is_file():
        ok("production bundle present (dashboard served on :8000)")
    else:
        warn("no production bundle — run: npm --prefix frontend run build "
             "(only needed for the single-port mode)")


def check_ports() -> None:
    section("Ports")
    import socket

    for port, name in ((8000, "API"), (5173, "Vite dev server")):
        with socket.socket() as sock:
            sock.settimeout(0.3)
            in_use = sock.connect_ex(("127.0.0.1", port)) == 0
        if in_use:
            warn(f"port {port} already in use ({name}) — stop that process first")
        else:
            ok(f"port {port} free ({name})")


def check_vercel() -> None:
    section("Vercel")
    cfg_path = ROOT / "vercel.json"
    if not cfg_path.is_file():
        bad("vercel.json missing")
        return
    try:
        cfg = json.loads(cfg_path.read_text())
    except json.JSONDecodeError as exc:
        bad(f"vercel.json is not valid JSON: {exc}")
        return
    ok("vercel.json parses")

    out = cfg.get("outputDirectory")
    (ok if out == "frontend/dist" else warn)(f"outputDirectory = {out}")

    rewrites = cfg.get("rewrites") or []
    api_rw = next((r for r in rewrites if str(r.get("source", "")).startswith("/api")), None)
    if api_rw is None:
        warn("no /api rewrite — the dashboard would call its own origin and 404")
    elif "REPLACE-WITH-YOUR-BACKEND" in str(api_rw.get("destination")):
        bad("the /api rewrite still points at the placeholder backend URL — "
            "set it to your deployed API (docs/DEPLOYMENT.md §A2 step 4)")
    else:
        ok(f"/api → {api_rw.get('destination')}")

    if (ROOT / "api" / "index.py").is_file():
        ok("api/index.py present (optional full-Vercel mode)")
    if (ROOT / "pyproject.toml").is_file():
        ok("pyproject.toml present (required by Vercel's Python runtime)")
    if not (ROOT / "requirements.txt").is_file():
        warn("no root requirements.txt — needed for the Python function mode")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vercel", action="store_true", help="also check deployment config")
    ap.add_argument("--no-ports", action="store_true", help="skip the port scan")
    args = ap.parse_args()

    print(f"\033[1mGRIDS preflight\033[0m — {ROOT}")
    check_runtime()
    check_backend()
    check_frontend()
    if not args.no_ports:
        check_ports()
    if args.vercel:
        check_vercel()

    print()
    if problems:
        print(f"\033[31m{len(problems)} blocking problem(s)\033[0m")
        for p in problems:
            print(f"  • {p}")
        return 1
    if warnings:
        print(f"\033[33m{len(warnings)} warning(s)\033[0m — the app will still start")
    print("\033[32mready\033[0m — start it with: ./scripts/dev.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
