# Run it locally, then put it on the internet

Two recipes. Recipe 1 gets GRIDS running on your machine. Recipe 2 puts the
dashboard on Vercel with the API on a host that can keep a process alive.

Both were run end to end before this was written; the checks in the last section
are the same ones the project uses.

---

## Recipe 1 — run it locally from scratch

### What you need

| Tool | Version | Why |
| --- | --- | --- |
| Python | 3.11+ | backend, simulator, tests |
| Node.js | 18+ (20 recommended) | dashboard build and dev server |
| Git | any | to clone |

Nothing else — no database server, no Docker, no API keys.

### The one-command way

```bash
git clone <your-repo-url> grids
cd grids
./scripts/dev.sh
```

On the first run it creates `.venv`, installs the Python and npm dependencies,
starts the API on **:8000**, waits until `/api/health` answers, then starts the
dashboard on **:5173**. Open **http://localhost:5173**.

Press `Ctrl-C` once and it stops both.

```text
▸ creating virtualenv at .venv
▸ installing backend dependencies (first run, ~1 min)
▸ backend  → http://localhost:8000/docs
▸ dashboard → http://localhost:5173   (Ctrl-C to stop both)
  VITE v5.4.21  ready in 211 ms
```

Want the production shape (one port, no dev server)?

```bash
./scripts/dev.sh --prod
# → http://localhost:8000/dashboard
```

### The explicit way (two terminals)

```bash
# once
cd grids
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
npm --prefix frontend install
```

```bash
# terminal 1 — API
cd backend
python3 -m uvicorn app.main:app --reload --port 8000
```

```bash
# terminal 2 — dashboard
cd frontend
npm run dev
```

Open **http://localhost:5173**.

### The single-port way (what you ship)

```bash
npm --prefix frontend run build          # writes frontend/dist
cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

* dashboard → **http://localhost:8000/dashboard**
* API docs → **http://localhost:8000/docs**
* JSON index → **http://localhost:8000/**

The backend mounts the built bundle itself, so there is no proxy to configure in
this mode.

### Check that it is healthy

```bash
python3 scripts/preflight.py          # runtime, deps, data, ports, config
curl -s localhost:8000/api/health     # {"status":"ok", ...}
cd backend && python3 -m pytest -q    # 111 tests, ~30 s
python scripts/verify_ui.py           # 23 headless-browser checks (needs both servers)
```

### First two minutes in the app

1. **Start run** in the left rail — the vehicle follows real OpenStreetMap streets.
2. Watch **GNSS integrity** on the right; pick `spoofing` in *Scenario* and start
   again to see fixes being rejected instead of followed.
3. **Analytics & sessions → Multi-scenario sweep → Run 5 scenarios** — the backend
   runs all five scenarios headlessly and returns an RMSE table per estimator.
4. **System** (top right) shows where the map data comes from and what is cached.

Optional: `cp .env.example .env` to change ports/behaviour. Notable switches:
`GRIDS_MAP_ONLINE=0` for a fully offline basemap, `GRIDS_DATABASE_URL` to move the
SQLite file.

### Things that trip people up

| Symptom | Fix |
| --- | --- |
| `Address already in use` on 8000/5173 | something is already running: `pkill -f "uvicorn app.main"` / `pkill -f vite`, or run `python3 scripts/preflight.py` to see the ports |
| Dashboard loads, every value `—`, **Link** says `retry` | the API is not up; start the backend first (dev.sh does this for you) |
| Map is grey with a graticule | no cached tiles and no network: run once online, or set `GRIDS_MAP_ONLINE=1` |
| `code 500` on first page load after changing `index.css`/`tailwind.config.js` | restart the dev server — Tailwind classes are compiled at startup |
| Windows: `./scripts/dev.sh` refuses to run | use Git Bash or WSL, or follow "The explicit way" above |

---

## Recipe 2 — deploy

### Read this first: which half goes where

The **dashboard** is a static Vite bundle → Vercel is ideal.
The **API** is stateful: starting a run spawns an asyncio task that steps the
simulator and streams frames over a WebSocket, and it writes SQLite + cached map
tiles to disk. Vercel functions can freeze or move between requests, so the API
needs a host that keeps a process, a socket and a disk.

| Piece | Host | Why |
| --- | --- | --- |
| `frontend/` | **Vercel** | static, CDN, free |
| `backend/` | Render / Railway / Fly.io / Koyeb / VPS | long-lived process + WebSocket + volume |

### Step 1 — put the repo on GitHub

```bash
cd grids
git add -A && git commit -m "GRIDS"
git remote add origin git@github.com:<you>/grids.git
git push -u origin main
```

### Step 2 — deploy the backend (Render shown; Railway/Fly are the same idea)

1. Render → **New + → Web Service** → connect the repo.
2. **Root directory:** `backend`
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. **Health check path:** `/api/health`
6. **Environment variables:**

```env
GRIDS_DATABASE_URL=sqlite:////data/grids.db
GRIDS_CORS_ORIGIN_REGEX=https?://([a-zA-Z0-9\-\.]+)?(vercel\.app|localhost|127\.0\.0\.1)(:\d+)?
GRIDS_MAP_ONLINE=1
GRIDS_ML_CORRECTION_DEFAULT=0
```

7. **Disks → Add disk**, mount path `/data` (so the DB and tile cache survive a
   deploy).
8. Deploy, then confirm `https://<your-api>/api/health` returns `{"status":"ok"}`.
   Copy that URL — you need it in step 3.

> Free tiers sleep when idle; the first request after a nap takes a few seconds
> (numpy/scipy import). That is normal.

### Step 3 — point the Vercel rewrite at that API

In `vercel.json`, replace the placeholder:

```json
"rewrites": [
  { "source": "/api/:path*", "destination": "https://<your-api>/api/:path*" }
]
```

```bash
git commit -am "point the /api rewrite at the deployed backend"
git push
```

### Step 4 — deploy the dashboard on Vercel

1. Vercel → **Add New → Project** → import the repo.
2. Settings:
   * **Framework preset:** Vite
   * **Root directory:** repository root (`.`)
   * **Build / Output / Install commands:** leave empty — `vercel.json` already
     sets `npm --prefix frontend run build`, `outputDirectory: frontend/dist` and
     `npm --prefix frontend ci`
3. **Deploy.** Open `https://<project>.vercel.app`.

The **Link** pill in the top bar should read **live**. If it says `retry`, the
rewrite target is wrong (step 3) or the backend is asleep.

### Step 5 — check before you share the link

```bash
python3 scripts/preflight.py --vercel   # flags a placeholder rewrite, bad config
```

Then from the deployed URL: start a run, let it stream for ~20 s, open Analytics
and run a sweep. You want live frames and real numbers, not zeros.

### Environment variables (usually none)

The frontend calls `/api` relatively and derives the socket from the page origin,
so **no env vars are needed** when you use the rewrite. Only if you want the
browser to hit the API directly:

| Variable | Where | Example |
| --- | --- | --- |
| `VITE_API_BASE` | Vercel → Settings → Environment Variables | `https://<your-api>/api` |
| `VITE_WS_URL` | same | `wss://<your-api>/api/ws/simulation` |

If you set them, redeploy (Vite inlines env at build time) **and** allow the
Vercel domain on the backend with `GRIDS_CORS_ORIGINS`.

### All on Vercel instead?

Possible for short demo runs: Vercel's Python runtime serves FastAPI and can hold
a WebSocket. What it cannot promise is that a run started in one request is still
alive in the next. If you want to try: switch the rewrite to
`{ "source": "/api/:path*", "destination": "/api/index" }` and set
`GRIDS_DATABASE_URL=sqlite:////tmp/grids.db` (the only writable path). `api/index.py`,
root `requirements.txt` and `pyproject.toml` are already in the repo.
Details and caveats: `docs/DEPLOYMENT.md` Option B.

### Deployment failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Numbers all `—`, Link `retry` | `/api` rewrite still the placeholder, or wrong backend URL | step 3, redeploy |
| CORS error in console | using `VITE_API_BASE` without allowing the Vercel domain | add it to `GRIDS_CORS_ORIGINS`, or drop the env var and proxy |
| Socket opens then closes | host/proxy not forwarding WebSocket upgrades | use a host that supports WS; keep `/api` proxied |
| Sessions vanish after a redeploy | no disk mounted for SQLite | add the `/data` volume (`GRIDS_DATABASE_URL`) |
| Blank map, everything else fine | tiles not fetched yet | set `GRIDS_MAP_ONLINE=1`, open the map once, or accept the offline graticule |
| Sweep times out on a small instance | a sweep is CPU work on the API box | smaller `durations_s`, or poll `/api/batch/status` |

---

## Appendix — what the runs measure

Sweep of all five scenarios, 45 s each, seed 42 (typical output):

| Scenario | GNSS | DR | EKF | RTS | EKF vs GNSS |
| --- | --- | --- | --- | --- | --- |
| Normal | 3.44 m | 1.10 m | 0.80 m | 0.32 m | 76.7% lower |
| Outage | 3.48 m | 4.49 m | 0.81 m | 0.38 m | 76.7% lower |
| Drift | 9.30 m | 2.65 m | 1.84 m | 1.62 m | 80.2% lower |
| Spoofing | 55.28 m | 5.09 m | 0.73 m | 0.32 m | 98.7% lower |
| Complex | 3.45 m | 4.53 m | 1.11 m | 0.53 m | 68.0% lower |

All values are simulated by the simulator in this repository; they do not
establish real-world performance.
