#!/usr/bin/env bash
# GRIDS - one-command local development.
#
#   ./scripts/dev.sh            backend :8000 + frontend :5173 (hot reload)
#   ./scripts/dev.sh --prod     build once, serve dashboard on :8000 only
#
# Creates the virtualenv and installs dependencies on first run. Ctrl-C stops
# everything it started.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-dev}"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

say()  { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight ---
command -v python3 >/dev/null || fail "python3 not found (need 3.11+)"
command -v node    >/dev/null || fail "node not found (need 18+)"
node -v | grep -qE 'v(1[89]|2[0-9])' || warn "node $(node -v) detected; 18+ recommended"

# ------------------------------------------------------------------- set-up ---
if [ ! -x "$PY" ]; then
  say "creating virtualenv at .venv"
  python3 -m venv "$VENV"
fi

if ! "$PY" -c "import fastapi, uvicorn, numpy, scipy, sqlalchemy, sklearn" 2>/dev/null; then
  say "installing backend dependencies (first run, ~1 min)"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  say "installing frontend dependencies"
  npm --prefix frontend install --no-audit --no-fund
fi

# ------------------------------------------------------------------ cleanup ---
PIDS=()
CLEANED=0
cleanup() {
  [ "$CLEANED" = "1" ] && return
  CLEANED=1
  printf '\n'
  say "shutting down"
  for pid in "${PIDS[@]:-}"; do
    [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# --------------------------------------------------------------------- run ---
if [ "$MODE" = "--prod" ] || [ "$MODE" = "prod" ]; then
  say "building the dashboard bundle"
  npm --prefix frontend run build
  say "serving API + dashboard on http://localhost:8000/dashboard"
  ( cd backend && exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 ) &
  PIDS+=($!)
  wait
else
  say "backend  → http://localhost:8000/docs"
  ( cd backend && exec "$PY" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 ) &
  PIDS+=($!)

  # give uvicorn a moment so the Vite proxy's first request does not ECONNREFUSED
  for _ in $(seq 1 40); do
    curl -sf -m 1 http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
    sleep 0.25
  done

  say "dashboard → http://localhost:5173   (Ctrl-C to stop both)"
  npm --prefix frontend run dev &
  PIDS+=($!)
  wait
fi
