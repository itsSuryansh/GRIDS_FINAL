# Deploying GRIDS

Two supported shapes. Read the first section before choosing, because the
simulation is **stateful** and that rules out the simplest option.

## What the app actually needs from the host

| Requirement | Why |
| --- | --- |
| A **long-lived process** | Starting a run spawns an `asyncio` task that steps the simulator and owns the live state (`services/simulation_service.py`). It must keep running between requests. |
| A **persistent WebSocket** | The dashboard streams frames over `/api/ws/simulation`. It reconnects, but the run must survive the reconnect — which needs the same backend instance. |
| A **writable disk** | SQLite (`backend/data/grids.db`) plus the OSM tile/road cache (`backend/data/{tiles,roads}`). |
| Anyone can reach the API | The browser talks to `/api` on the frontend origin, so the frontend needs a proxy/rewrite to the backend. |

> **The catch:** on Vercel a serverless function can freeze or be discarded
> between invocations. A simulation started in one invocation is not reliably
> still running in the next, and two invocations may land on different instances.
> Everything else works, but *start a run and come back* is exactly the pattern
> serverless is worst at.

## Option A — recommended: static dashboard on Vercel + backend on a container host

Frontend is a static Vite bundle, so Vercel is a perfect fit for it. The API keeps
running on a host that allows a persistent process with a WebSocket and a disk.

### A1. Deploy the backend (Render, Railway, Fly.io, Koyeb, or a VPS)

Any of these works; the steps are the same shape:

1. New **Web Service** from your repo.
2. **Root directory:** `backend`
3. **Build:** `pip install -r requirements.txt`
4. **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. **Health check path:** `/api/health`
6. **Environment:**

```env
GRIDS_DATABASE_URL=sqlite:////data/grids.db
GRIDS_CORS_ORIGIN_REGEX=https?://([a-zA-Z0-9\-\.]+)?(vercel\.app|localhost|127\.0\.0\.1)(:\d+)?
GRIDS_MAP_ONLINE=1
GRIDS_ML_CORRECTION_DEFAULT=0
```

7. **Attach a persistent volume** and mount it at `/data` (SQLite and the tile
   cache live there). Without a volume the DB is wiped on every deploy.
8. Note the public URL, e.g. `https://grids-api.onrender.com`. Check
   `https://<backend>/api/health` returns `{"status":"ok", ...}`.

> The backend can also serve the built dashboard itself on the same origin
> (`/dashboard`) — useful for a VPS, or as a fallback if you would rather not use
> Vercel at all.

### A2. Deploy the frontend to Vercel

1. Push the repo to GitHub (the Vite app lives in `frontend/`).
2. On Vercel: **Add New → Project → Import** the repo.
3. Configure exactly:
   * **Framework preset:** Vite
   * **Root directory:** `.` (repository root — the repo-level `vercel.json`
     already builds `frontend/` and publishes `frontend/dist`)
   * **Build command / Output directory:** leave empty, `vercel.json` supplies
     `npm --prefix frontend run build` → `outputDirectory: frontend/dist`
4. **Set the rewrite target first.** In `vercel.json`, replace
   `https://REPLACE-WITH-YOUR-BACKEND` with your real backend URL, commit, push.
   Without this the dashboard loads but every API call 404s.
5. **Deploy.** Open `https://<project>.vercel.app` — the *Link* pill in the top
   bar should read **live**.

### A3. Environment variables

The frontend uses relative URLs by default (`/api`, and the WebSocket is derived
from `window.location.host`), so with the rewrite **no env vars are required**.
Only set these if you want the browser to call the backend directly instead of
proxying:

| Variable | Where | Example |
| --- | --- | --- |
| `VITE_API_BASE` | Vercel → Project → Settings → Environment Variables | `https://grids-api.onrender.com/api` |
| `VITE_WS_URL` | same | `wss://grids-api.onrender.com/api/ws/simulation` |

If you use them, redeploy (Vite inlines env vars at build time) **and** add the
Vercel domain to `GRIDS_CORS_ORIGINS` on the backend.

## Option B — everything on Vercel (works for the dashboard, not for long runs)

Vercel's Python runtime does serve FastAPI as a function, and can mount a
WebSocket. What it cannot do is guarantee that the between-request process keeps
the simulation alive or that reconnects hit the same instance. So: fine for a demo
where runs are started and watched inside one function's lifetime, not for
"start a run, come back later".

If you want to try it:

1. Add `api/index.py` at the repo root:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: F401  (Vercel looks for a variable named `app`)
```

2. Root `requirements.txt`:

```text
-r backend/requirements.txt
```

3. Root `pyproject.toml` — Vercel's Python runtime refuses to build without one:

```toml
[project]
name = "grids"
version = "1.0.0"
requires-python = ">=3.12"
```

4. Wire `/api/*` (and the socket) to the function rather than to a remote host:
   change the `rewrites` block in `vercel.json` to
   ```json
   { "source": "/api/:path*", "destination": "/api/index" }
   ```
5. Point SQLite at `/tmp` (`GRIDS_DATABASE_URL=sqlite:////tmp/grids.db`) — the only
   writable path — and expect sessions to disappear between invocations.

Expect cold starts of a few seconds (numpy/scipy import), executions capped by the
plan's function duration, and no shared state across instances.

## Local: two ways to serve it, plus a benchmark

```bash
# 0. once
git clone <your-repo> && cd grids
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
npm --prefix frontend install
```

**1. Two processes (development, hot reload)**

```bash
# terminal A
cd backend && python3 -m uvicorn app.main:app --reload --port 8000
# terminal B
cd frontend && npm run dev          # http://localhost:5173  (proxies /api → :8000)
```

**2. One port (production-like, what you would actually ship)**

```bash
cd frontend && npm run build        # writes frontend/dist
cd ../backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# dashboard → http://localhost:8000/dashboard
# API docs  → http://localhost:8000/docs
```

**3. Batch benchmark (no UI)**

```bash
python scripts/run_scenarios.py --duration 120 --seed 42   # RMSE table per scenario
```

### Checks before you announce anything

```bash
cd backend && python3 -m pytest -q                 # 103 tests
python scripts/verify_ui.py                        # 19 headless-browser checks
# both servers must be running for verify_ui.py
```

## Common failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Dashboard loads, every number empty, *Link* says `retry` | `/api` rewrite still points at the placeholder, or the backend URL is wrong | Fix `rewrites` in `vercel.json`, redeploy |
| `CORS` error in the console | Using `VITE_API_BASE` to call the backend cross-origin without allowing the Vercel domain | Either keep relative URLs (proxying) or add the domain to `GRIDS_CORS_ORIGINS` |
| WebSocket connects then closes | Free tier idling, or a proxy that does not forward upgrades | Use a host with WebSocket support; confirm the proxy passes `Upgrade` headers |
| Sessions disappear after a restart | No persistent volume for SQLite | Mount a volume at `/data` and set `GRIDS_DATABASE_URL` to it |
| Map is blank, everything else works | Tiles/roads not fetched and `GRIDS_MAP_ONLINE=0` | Set `GRIDS_MAP_ONLINE=1` and click *Cache tiles* once, or accept the offline graticule |
| First request takes ~5 s | Cold start (numpy/scipy) | Normal on serverless; use an always-on host for demos |
| A multi-scenario sweep 504s | A sweep is CPU work on the API box (5 runs × 45 s ≈ 6 s of wall time here, longer on a small instance) | Use `/api/batch/status` polling with a small plan, or lower `durations_s`; the endpoint caps at 40 runs / 300 s per run |
