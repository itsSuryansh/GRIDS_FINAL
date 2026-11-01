# GRIDS — GNSS-Resilient Intelligent Dead Reckoning System

GRIDS is an independent navigation-technology platform for **resilient positioning**:
it keeps estimating where a vehicle is when GNSS becomes unavailable, degraded, or
untrustworthy. The platform ships as a working, self-contained MVP: a physics-based
vehicle/sensor simulator, a dead-reckoning integrator, a 6-state Extended Kalman
Filter, an explainable GNSS anomaly detector with graduated response, drift
monitoring, optional map matching, a real-time WebSocket stream, a mission-control
style dashboard, and ground-truth-scored performance analytics persisted in SQLite.

> **Data provenance.** Everything the platform displays is produced by the
> simulator that ships in this repository. It is *simulated* navigation data.
> Simulated accuracy does not establish real-world performance, and the anomaly
> detector is a statistical detector for injected faults — not a certified
> anti-spoofing system. These limits are stated in the API (`/api/system/info`),
> in the analytics notes of every report, and in the UI.

![GRIDS operations dashboard](docs/images/dashboard-operations.png)

*Operations view during a run: live GNSS/DR/EKF tracks on the offline basemap,
GNSS channel diagnostics, per-module health, system metrics and live analytics.
All values come from the backend in real time.*

---

## 1. Problem statement

Satellite positioning is the default source of vehicle position, but it is not
always available and not always honest. GNSS can disappear (urban canyons,
tunnels, jamming), degrade slowly (multipath, ionospheric disturbance, aiding
failures) or be deliberately spoofed. A navigation system that simply trusts the
receiver will either stop navigating or, worse, confidently follow a false track.

GRIDS addresses this by combining GNSS with inertial dead reckoning, fusing both
in an EKF that can coast on inertial data, and *judging* each GNSS fix before it
is allowed to influence the estimate.

---

## 2. What is implemented (and what is not)

| Capability | Status | Notes |
|---|---|---|
| Vehicle motion simulator (6 patterns, configurable speed/duration/noise) | ✅ | Ground-truth trajectory is the scoring reference |
| GNSS simulator: normal / outage / drift / spoofing | ✅ | Missing fixes are `None`, never zero |
| IMU + odometry sensor simulation with true biases | ✅ | DR genuinely accumulates error |
| Dead reckoning (EN frame, heading-aware) | ✅ | Independent of the EKF, used as a baseline |
| Extended Kalman Filter (6 states, NIS gating, Joseph update) | ✅ | Numerically stabilised, covariance exposed |
| GNSS anomaly detection (5 explainable detectors) | ✅ | Accept / down-weight / reject / hold-out policy |
| Drift monitoring + bounded correction | ✅ | Correction blocked unless GNSS is demonstrably healthy |
| Map matching | ✅ | Offline synthetic road network by default; optional OSM |
| ML drift correction | ⚠️ optional, **disabled by default** | Trained + honestly evaluated; no measured improvement on held-out sessions in this MVP |
| Real-time WebSocket stream + REST API | ✅ | Socket is a pure subscriber; no duplicate loops |
| Performance analytics vs ground truth | ✅ | MAE, RMSE, mean, max, P95, outage recovery |
| SQLite persistence (sessions, results, metrics, anomalies) | ✅ | Batched writes, not row-by-row |
| Docker Compose deployment | ✅ provided | See §11 |
| Real hardware / real receivers / IMU drivers | ❌ out of scope | No hardware is required anywhere |

---

## 3. System architecture

```
                    ┌──────────────────────────────┐
                    │   React + Vite dashboard     │
                    │  Leaflet map · Recharts ·    │
                    │  React components · Tailwind │
                    └───────────┬──────────────────┘
                                │  REST (/api/*)   WebSocket (/api/ws/simulation)
                    ┌───────────▼──────────────────┐
                    │        FastAPI backend       │
                    │                              │
                    │  routes/  simulation · navigation · analytics · health · realtime
                    │  services/ simulation_service · navigation_service · analytics_service · osm_service
                    │  algorithms/ dead_reckoning · ekf · gnss_anomaly · drift_correction · map_matching
                    │  core/  simulator · coordinate_utils · state_manager
                    │  ml/    train · inference · model
                    │  models/ schemas (Pydantic) · database (SQLAlchemy)
                    └───────────┬──────────────────┘
                                │
                    ┌───────────▼──────────────────┐
                    │   SQLite (SQLAlchemy ORM)    │
                    │  sessions · batched results ·│
                    │  metrics · anomaly events    │
                    └──────────────────────────────┘
```

Key architectural decisions:

* **One simulation loop, owned by the service.** `SimulationService` runs a single
  asyncio task per run. WebSocket clients only subscribe, so reconnecting or
  opening a second tab can never spawn a duplicate loop.
* **Metric frame everywhere.** All estimation happens in a local East–North
  tangent plane anchored at the trajectory origin; latitude/longitude is only
  used at the edges (map display, API payloads, ground-truth scoring).
* **Filter baseline is never replaced.** Drift correction moves the DR branch at
  most, and only while the GNSS channel is healthy. The EKF is always the
  reference solution.
* **Storage is coarse-grained on purpose.** Frames are buffered and flushed in
  batches of ~250 as compact columnar JSON; only discrete anomaly events are
  written individually.

---

## 4. Technology stack

**Frontend** React 18, Vite 5, Tailwind CSS 3, Leaflet 1.9 + React-Leaflet 4,
Recharts 2, Lucide icons.
**Backend** Python 3.11+, FastAPI, Uvicorn, Pydantic v2, NumPy, SciPy, Pandas,
scikit-learn, SQLAlchemy 2, native WebSockets.
**Storage** SQLite.
**ML** scikit-learn (`GradientBoostingRegressor`, multi-output), joblib.
**Infra** Docker, Docker Compose, Python virtualenv, Git.

No external service is required for any core function; the optional OSM lookup is
off by default.

---

## 5. Navigation engine

### 5.1 Frames and conventions

* Local tangent plane (equirectangular WGS-84 scaling) at the origin: `east`,
  `north` in metres. Accurate to centimetres over the few kilometres a run covers.
* Heading ψ is **clockwise from north** (compass convention), wrapped to (−π, π].
* Ranges/noise are in metres; biases in m/s² and rad/s.

### 5.2 Vehicle & sensor simulator (`core/simulator.py`)

Routes are built as dense polylines in the EN frame for six patterns: `straight`,
`left_turn`, `right_turn`, `curved`, `random`, `custom` (user waypoints). The
vehicle follows the polyline with a bounded longitudinal acceleration and slows
in curves, producing realistic yaw rates and lateral accelerations.

Sensors are generated from ground truth:

| Sensor | Model |
|---|---|
| GNSS position | truth + injected fault (+ optional bias) + N(0, σ_gnss²) per axis |
| Accelerometer | true longitudinal accel + true bias `b_a` + N(0, σ_a²) |
| Gyroscope | true yaw rate + true bias `b_g` + N(0, σ_g²) |
| Wheel speed | true speed + N(0, σ_v²) |

Fault injection:

* **outage** — no GNSS measurement at all inside the window (`None`, never 0),
* **drift** — bias magnitude grows as `min(max, rate × t_after_onset)` in a slowly
  rotating direction,
* **spoofing** — an instant jump plus a continuous false walk in a seeded
  direction, as a coordinated attack would appear.

### 5.3 Dead reckoning (`algorithms/dead_reckoning.py`)

```
v_{k+1}   = v_k + (a_m − b_a)·Δt
ψ_{k+1}   = ψ_k + (ω_m − b_g)·Δt
e_{k+1}   = e_k + v_{k+1}·sin ψ_{k+1}·Δt
n_{k+1}   = n_k + v_{k+1}·cos ψ_{k+1}·Δt
```

Velocity is a complementary blend of the integrated accelerometer and wheel
odometry (weight configurable), which bounds accelerometer drift the way a
production system would. DR is kept deliberately separate from the EKF so the
dashboard can show an honest drifting baseline.

### 5.4 Extended Kalman Filter (`algorithms/ekf.py`)

State `x = [e, n, v, ψ, b_a, b_g]ᵀ`.

**Prediction** (IMU driven; runs with or without GNSS):

```
e'  = e + v'·sin ψ'·Δt          ψ' = ψ + (ω_m − b_g)·Δt
n'  = n + v'·cos ψ'·Δt          v' = v + (a_m − b_a)·Δt
b_a' = b_a                       b_g' = b_g
```

Jacobian `F = ∂f/∂x` includes the heading/velocity/bias couplings, e.g.
`∂e'/∂ψ = v'·cos ψ'·Δt`, `∂e'/∂b_a = −sin ψ'·Δt²`.

**Covariance** `P = F P Fᵀ + Q`, with process noise built from accelerometer and
gyroscope noise plus random-walk terms on both biases.

**Measurement updates**

| Sensor | z | H | R |
|---|---|---|---|
| GNSS | [e, n] | [I₂ \| 0] | σ²·I₂ (inflatable when down-weighting) |
| Wheel speed | [v] | [0 0 1 0 0 0] | σ_v² |
| Compass (optional) | [ψ] | [0 0 0 1 0 0] | σ_ψ² |

**Gating.** Every GNSS fix yields innovation `y = z − Hx`, `S = H P Hᵀ + R`, and
`NIS = yᵀ S⁻¹ y`. Fixes whose NIS exceeds the χ²(2, 0.999) gate are rejected
without touching state or covariance, and anomaly detection can additionally
inflate `R`.

**Stability.** Joseph-form covariance update `P = (I−KH)P(I−KH)ᵀ + K R Kᵀ`,
explicit symmetrisation, eigenvalue flooring, wrapped heading, and non-negative
speed clamping.

**Uncertainty exposure.** The API/UI report both `σ_pos = √λ_max(P_ee, P_nn)` (a
1σ radial scale) and `√tr(P_pos)`. Neither is labelled "confidence": no
probability-of-containment is computed.

### 5.5 GNSS anomaly detection (`algorithms/gnss_anomaly.py`)

Five independent, explainable detectors, each producing a severity in [0, 1]:

1. **position_jump** — geodesic step between consecutive fixes vs what the vehicle
   could physically have travelled (`allowed = 25 m + 6σ + (|v| + 20 m/s)·Δt`).
2. **velocity** — implied ground speed over a ~1 s baseline vs fused speed, with a
   noise-derived tolerance (per-sample GNSS noise dominates at high rates).
3. **heading** — implied course vs fused heading, using a circular tolerance
   `atan2(3σ√2, jump)`; skipped when displacement is below `4σ√2`.
4. **residual** — innovation magnitude and NIS.
5. **drift** — windowed (10 s) mean residual bias, compared with a *significance
   floor* `max(3 m, 5σ/√N)`, which makes slow corruption detectable without
   false-alarming on noise.

Response policy (graduated, not binary):

| Combined severity | Action | GNSS status |
|---|---|---|
| < 0.45 | normal update | `healthy` |
| ≥ 0.45 | update with inflated measurement noise (≥8× σ for drift) | `degraded` |
| kinematically impossible transient ≥ 0.85 | hard reject | `suspicious` |
| persistent bias ≥ 0.45 **and** mean > 3 m **and** own uncertainty ≤ 60 m | hard reject, coast on inertial | `suspicious` |
| after any rejection | hysteresis hold-out until the innovation returns inside the κ gate (1.5 s … 45 s) | `suspicious` |

The last condition matters: if the filter itself is uncertain (long coast), a
persistent residual is more likely filter divergence than a GNSS fault, and a hard
reject would be unjustified.

### 5.6 Drift monitoring and correction (`algorithms/drift_correction.py`)

`DriftMonitor` tracks DR↔EKF separation, DR↔truth error (available in simulation
for evaluation), EKF↔truth error, the running mean of accepted GNSS residuals and
a smoothed drift rate. `DriftCorrector` applies a *bounded* correction
(`gain = 0.08`, `max 2.5 m` per step) to the DR branch only, and only when the
last five GNSS fixes were accepted without anomaly. The EKF is never modified.

### 5.7 Map matching (`algorithms/map_matching.py`, `services/osm_service.py`)

Nearest-segment snapping with a snap-distance gate (40 m), light temporal
smoothing and a "no map → unmatched" path. By default the road network is derived
from the simulated route, so the feature works with zero internet access. With
`GRIDS_ENABLE_OSM=1` the backend queries the Overpass API and caches the result;
if the network is unreachable, the synthetic network is used and the API reports
`map_source: "synthetic"`. Map matching never feeds back into the filter.

### 5.8 Optional ML correction (`ml/`)

Features available at run time only (innovation components, availability, NIS,
uncertainty, speed, |yaw rate|, time since fix, residual, rejected flag, anomaly
score). The model predicts the EKF residual in EN metres and the correction is
subtracted from the EKF position; it is never applied while GNSS is absent.

`python -m app.ml.train` trains on 6 simulated sessions and evaluates on 3
**held-out sessions with unseen seeds**. In this MVP the measured held-out result
was *worse* than the EKF baseline (RMSE 10.04 m vs 8.44 m over the mixed test
set), so the layer stays **disabled by default** and the dashboard shows the
measured delta instead of assuming an improvement.

### 5.9 Per-step pipeline (`services/navigation_service.py`)

```
1 simulator step            → ground truth + IMU/odometry/GNSS
2 EKF predict (IMU)         → survives outages by construction
3 GNSS innovation (no update)
4 anomaly evaluation        → score, reason, policy
5 GNSS update if trusted    → EKF NIS gate as second line of defence
6 odometry speed update     → GNSS-independent
7 dead-reckoning integration
8 bounded DR correction     → only while GNSS is healthy
9 drift monitoring (+ optional ML)
10 map matching (advisory, throttled)
11 frame assembly           → geodetic coords, errors vs truth, module health
```

---

## 6. Performance analytics

Every estimator is scored at the **same timestamps** against the **same ground
truth**: MAE, RMSE, mean, max, P95, sample count — separately for GNSS, dead
reckoning, EKF and EKF+ML, plus outage peak error, error at outage end, drift
rate during the outage, time to recover below 10 m, anomaly count and rejected
measurement count. Comparisons are never made between misaligned samples.

Reference results produced by `scripts/run_scenarios.py` (120 s, seed 42, 10 Hz,
σ_gnss = 2.5 m — *simulated*):

| Scenario | GNSS RMSE | DR RMSE | EKF RMSE | anomalies | rejected |
|---|---|---|---|---|---|
| normal | 3.49 | 1.80 | 0.54 | 41 | 16 |
| outage (30–70 s) | 3.50 | 11.49 | 4.79 | 48 | 32 |
| drift (0.4 m/s from 20 s) | 21.35 | 32.00 | 25.92 | 581 | 511 |
| spoofing (70 m jump at 25 s) | 107.53 | 50.48 | 6.14 | 955 | 951 |
| complex (random route + outage) | 3.53 | 6.22 | 0.65 | 37 | 16 |

These numbers are reproduced by the script on demand; they are not constants in
the code.

---

## 7. REST API

Interactive documentation: `http://localhost:8000/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + DB check |
| GET | `/api/system/info` | capabilities, limits, data-provenance disclaimer |
| GET | `/api/simulation/scenarios` | ready-to-run scenarios + defaults |
| GET | `/api/simulation/patterns` | available movement patterns |
| GET | `/api/simulation/status` | state, progress, active config |
| POST | `/api/simulation/start` | start a run (validated `SimulatorConfig`) |
| POST | `/api/simulation/pause` \| `resume` \| `stop` \| `reset` | lifecycle |
| GET | `/api/navigation/current` | latest synchronised frame |
| GET | `/api/navigation/history?limit=&stride=` | down-sampled frames |
| GET | `/api/navigation/route` | planned route, outage window, map source |
| GET | `/api/navigation/anomalies` | discrete anomaly events |
| GET | `/api/navigation/modules` | module health |
| GET | `/api/analytics/summary` | live running metrics |
| GET | `/api/analytics/compare?include_series=` | full comparison report |
| GET | `/api/analytics/ml` | ML model status + held-out evaluation |
| GET | `/api/analytics/sessions` | stored sessions with metrics |
| GET | `/api/analytics/sessions/{id}` | config, metrics, series, anomalies |
| WS | `/api/ws/simulation` | live stream (`navigation_update`, `state_change`, …) |

Example:

```bash
curl -X POST http://localhost:8000/api/simulation/start \
  -H 'Content-Type: application/json' \
  -d '{"scenario":{"scenario":"spoofing","spoof_onset_s":15},
       "duration_s":60,"rate_hz":10,"route_pattern":"left_turn","speed_ms":14}'
curl http://localhost:8000/api/navigation/current | jq '.frame | {t, gnss_status, ekf_error_m}'
curl http://localhost:8000/api/analytics/compare | jq '.algorithms'
```

Custom route example:

```json
{"route_pattern":"custom","duration_s":90,
 "custom_waypoints":[{"lat":26.9124,"lon":75.7873},
                     {"lat":26.9200,"lon":75.7950},
                     {"lat":26.9300,"lon":75.7830}]}
```

---

## 8. Simulation scenarios

| Scenario | What the simulator does | What you should observe |
|---|---|---|
| **1 · Normal** | GNSS available throughout with configurable noise | GNSS, DR and EKF all track truth; EKF smoother than raw GNSS |
| **2 · Outage** | GNSS stops entirely for a configurable window | EKF and DR keep moving; error and covariance grow, then recover after the fix returns |
| **3 · Drift** | Bias grows slowly in a near-fixed direction | Windowed-residual detector raises the alarm; corrupted fixes are down-weighted/rejected; EKF does not follow the false track |
| **4 · Spoofing** | Instant jump + continuous false walk | Jump/velocity/heading detectors fire immediately; fixes rejected; EKF coasts |
| **5 · Complex** | Randomised route with turns, accel/decel, mid-run outage | Navigation continues through aggressive manoeuvres; EKF bounds DR drift |

Scenario 5 is exposed as `scenario: "complex"` and automatically uses the random
route pattern.

---

## 9. Dashboard

Mission-control layout, light theme, navy typography, blue accents, compact data
density:

* **Top bar** — product identity, system / simulation / GNSS / link status pills,
  mission clock.
* **Navigation map** (Leaflet) — ground truth, GNSS, dead reckoning, EKF and
  EKF+ML tracks with per-layer toggles, vehicle heading marker, start point,
  GNSS-outage regions, detected-anomaly markers, live coordinate readout. Two
  basemaps: an **offline graticule grid** (default, works with no internet) and
  CARTO/OSM light tiles (optional).
* **GNSS channel** — status, fix validity, residual, anomaly score, NIS, raw
  error, rejected count, per-detector severity bars, detector explanation.
* **Navigation algorithms** — live state of GNSS, DR, EKF, anomaly detection,
  drift correction and map matching (`active`, `degraded`, `coasting`,
  `rejected`, `alert`, `unavailable`, …).
* **System metrics** — latitude, longitude, speed, heading, GNSS availability,
  position error (with DR and GNSS comparison), drift estimate, EKF 1σ.
* **Live analytics** — five switchable charts: position error, GNSS residual +
  anomaly score, velocity, drift accumulation, EKF uncertainty vs actual error,
  with outage shading.
* **Simulation control** — start / pause / resume / stop / reset, scenario
  selection, fault parameters, route pattern, speed, duration, rate, origin,
  seed, sensor noise, module toggles.
* **Analytics page** — comparison table (best estimator highlighted), RMSE/P95
  bar chart, per-timestamp error curves, outage-recovery panel, ML evaluation
  panel, stored-session archive with click-through reports.

![GRIDS analytics view](docs/images/dashboard-analytics.png)

*Analytics view: per-estimator RMSE/MAE/P95/max at identical timestamps, outage
recovery figures, the measured ML evaluation, and the stored-session archive.*

---

## 10. Local development

Requirements: Python 3.11+, Node 18+.

```bash
git clone <repo> grids && cd grids

# backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000               # http://localhost:8000/docs

# frontend (new terminal)
cd frontend
npm install
npm run dev                                             # http://localhost:5173
```

The Vite dev server proxies `/api` (including WebSocket upgrade) to
`http://127.0.0.1:8000`, so browser code only ever uses relative URLs. Change the
proxy target with `VITE_BACKEND_PROXY` if the API runs elsewhere.

Headless runs (no UI at all):

```bash
cd backend
python -m app.ml.train --sessions 6 --duration 90        # optional ML layer
cd ..
python scripts/run_scenarios.py --duration 120 --seed 42 --persist
```

---

## 11. Docker execution

```bash
cp .env.example .env
docker compose up --build
# dashboard  → http://localhost:5173
# API docs   → http://localhost:8000/docs
docker compose down          # add -v to drop the SQLite volume
```

* `backend` runs Uvicorn on **8000**, exposes `/api/health` as a healthcheck.
* `frontend` builds the Vite bundle and serves it through Nginx on **5173**,
  proxying `/api/*` (and the WebSocket) to `backend:8000` — no hardcoded URLs.
* Named volumes persist `grids_data` (SQLite) and `grids_ml` (model artifacts).

---

## 12. Testing

```bash
cd backend
python -m pytest -q                 # 90 tests, ~11 s
python -m pytest tests/test_api.py -q -v
```

Coverage:

| File | Focus |
|---|---|
| `test_coordinates.py` | local↔geodetic round trip, scale factors, haversine, bearing, angle wrapping |
| `test_simulator.py` | route continuity/geometry, motion, sensor noise, outage produces `None` (not 0), drift growth, spoof injection, seed determinism |
| `test_dead_reckoning.py` | exact integration of straight/accel/turn motion, bias handling, odometry blending, correction, geodetic round trip |
| `test_ekf.py` | prediction, covariance growth, GNSS/velocity/heading updates, Joseph stability over 400 steps, NIS gating, outage coasting, bias observability, reset |
| `test_anomaly.py` | zero rejections on clean GNSS, jump detection, persistent-drift detection, graduated response, status classification, explainability fields |
| `test_drift_and_metrics.py` | drift monitor/rate, bounded correction, segment projection, snap gating, no-map fallback, error statistics, outage recovery metrics |
| `test_scenarios.py` | full pipeline for all five scenarios + every route pattern, outage keeps navigating, spoof rejected, EKF vs baselines, map matching advisory |
| `test_api.py` | health/info, scenario catalogue, validation failures (422), full lifecycle (start → pause → resume → stop → reset), analytics, session retrieval (404 handling), WebSocket streaming |
| `test_regression.py` | policy guards: ML layer stays opt-in, detection report is self-consistent, zero rejections on a clean run, EKF beats raw GNSS, outage frames carry no GNSS coordinates, drift correction suspended while GNSS is untrusted, run-to-run reproducibility |

All tests use deterministic seeds and a temporary SQLite database.

---

## 13. Known limitations

1. **Simulated data only.** No receiver, IMU or CAN data is ingested; the physics
   is a kinematic model with noise and bias, not a hardware model.
2. **Slow drift is the hardest case.** The detector flags it and stops trusting
   the channel, but with only IMU/odometry remaining, the filtered solution can
   still degrade to dead-reckoning accuracy (measured: EKF 25.9 m RMSE vs DR
   32.0 m on the reference drift run). Absolute GNSS aiding (e.g. a trusted
   external reference) would be required to do better; the platform does not
   pretend otherwise.
3. **The ML correction layer does not currently help.** Its held-out evaluation
   is worse than the EKF baseline, so it is disabled by default.
4. **Loose/loose-coupling only.** There is no tight coupling to raw GNSS
   observables (pseudoranges, Doppler), so no satellite-level fault detection.
5. **2-D kinematics.** No vertical channel, heading from a magnetometer model, or
   wheel-slip/vehicle-dynamics model beyond the odometry blend.
6. **Map matching is generic.** Default network is synthetic (derived from the
   route); OSM mode is a nearest-segment matcher without HMM/topology inference,
   and it never corrects the filter.
7. **Single vehicle, single active run** — the state manager keeps one active run
   at a time (completed runs remain available for comparison).
8. **Docker image was authored but not executed in this environment** (no Docker
   daemon available where the project was built); the local workflow, API,
   WebSocket, and full test suite were executed and verified.

---

## 14. Future improvements

* Tight coupling with raw GNSS measurements and RAIM-style satellite-level checks.
* IMM/UKF variants for aggressive manoeuvres; 3-D state with a barometer.
* Learned anomaly detection (sequence model) benchmarked against the statistical
  detector, with the same honest held-out protocol as the ML layer.
* HMM map matching with road topology and OSM ingestion pipeline.
* Multi-vehicle simulation and shared-map integrity monitoring (cooperative
  spoofing detection).
* Server-side run replay with time-scrubbing and report export (PDF/CSV).

---

## 15. Repository layout

```
grids/
├── backend/
│   ├── app/
│   │   ├── main.py config.py
│   │   ├── api/router.py + routes/{simulation,navigation,analytics,health,realtime}.py
│   │   ├── core/{simulator,coordinate_utils,state_manager}.py
│   │   ├── algorithms/{dead_reckoning,ekf,gnss_anomaly,drift_correction,map_matching}.py
│   │   ├── services/{navigation_service,simulation_service,analytics_service,osm_service}.py
│   │   ├── models/{schemas,database,database_setup}.py
│   │   ├── ml/{model,inference,train}.py
│   │   └── utils/{metrics,logging}.py
│   ├── tests/                 (90 tests)
│   ├── requirements.txt  Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/        (map, metrics, panels, controls, charts, analytics)
│   │   ├── hooks/useSimulationSocket.js
│   │   ├── pages/Dashboard.jsx  services/api.js  utils/format.js
│   ├── Dockerfile  nginx.conf  vite.config.js  tailwind.config.js
├── scripts/run_scenarios.py
├── docs/{ARCHITECTURE.md,images/}
├── docker-compose.yml  .env.example  README.md
```
