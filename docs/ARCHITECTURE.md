# GRIDS — engineering decisions

Short rationale for the choices that are easy to get wrong.

## 1. Local tangent plane instead of lat/lon in the filter
The filter integrates velocities, so the state must be metric. A local
East-North plane anchored at the run origin is accurate to centimetres over a few
kilometres, keeps the Jacobians simple, and avoids the ill-conditioning that
comes from treating degrees as metres. Conversion happens only at the edges.

## 2. Dead reckoning kept separate from the EKF
A single fused output hides how much of the solution is inertial. Keeping an
independent DR integrator makes drift visible in the UI and provides an honest
baseline in the comparison report.

## 3. Anomaly detection sits *in front of* the EKF update
The innovation is computed before the update, scored, and only then applied (or
rejected / down-weighted / held out). Applying first and "correcting later" would
let a spoofed fix poison the state and the covariance.

## 4. Three-state response instead of accept/reject
Hard rejection is a strong action. For a slowly drifting solution the better
answer is usually to inflate the measurement noise, because dropping GNSS
entirely hands the solution to inertial drift. Rejection is reserved for
kinematically impossible fixes, persistent biases that exceed noise significance,
and the hysteretic hold-out that follows any anomaly.

## 5. Drift-pathological case documented, not hidden
A slow common-mode bias is intrinsically ambiguous with respect to filter
divergence: nothing in the inertial data reveals it. While the detector can see it,
the fixes are rejected; once it is re-accepted the fused track follows the bias
(reference run: EKF 26.5 m vs raw GNSS 21.4 m RMSE, simulated). The detector's
residual floor was raised from 6 m to 8 m so that healthy runs are never rejected
(the cost is a slightly later detection), and the weakness is stated in the README
and in the UI instead of being tuned away with ground-truth information that would
not exist in reality.

## 6. Drift correction cannot touch the EKF
The corrector pulls the DR branch toward the filter only after five consecutive
clean GNSS updates. A corrupted filter therefore cannot be copied into the
independent dead-reckoning track (this was observed during development and fixed).

## 7. ML correction is opt-in and measured
The layer is trained on six simulated sessions and evaluated on three held-out
sessions with unseen seeds. The measured held-out result was worse than the EKF
baseline, so the default stays off and the dashboard shows the delta. Tests assert
that the recommendation follows the measurement, not an assumption.

## 8. Map aiding is a gated coasting aid, and the synthetic network never aids
Road data may be missing (offline), out of date, or simply not the road the vehicle
is on. Three decisions follow:

* **Matching is always advisory.** The snap point is displayed and reported, never
  used to correct the filter.
* **Aiding is only for coasting.** While GNSS is delivering accepted fixes the filter
  already has a better measurement than a road centre-line; forcing the track onto a
  road biases healthy innovations. The cross-track constraint is therefore applied
  only when GNSS is unavailable or its fixes are being rejected.
* **The constraint must earn trust.** It needs a surveyed OSM network, a persistent
  match offset ≤ 5 m, a filter 1σ ≤ 20 m, and it disables itself for the rest of the
  run if the receiver keeps rejecting fixes while it is active. The synthetic network
  (chords through the simulated route) is good enough to display a match, and much
  too coarse to constrain a filter — so it never does.

A parallel no-map shadow filter always runs the identical model, so the benefit is
*measured* (`map_vs_nomap_rmse_m`) rather than asserted; the honest result is that it
is small, and the README says so.

## 9. Fixed-lag smoothing writes back into the past
The RTS pass produces an estimate for a sample that is 4 s old. It is written into
that sample's own frame and scored against that sample's ground truth. Scoring it
against "now" (an early bug) produced a 2.5 km apparent error and would have made the
smoother either look broken or be "fixed" by cheating. The state difference also
wraps the heading component, otherwise crossing ±180° injects a large false
correction.

## 10. Real road geometry via the OSM map-data endpoint
Public Overpass instances were unreachable/rate-limited here. The plain
`api.openstreetmap.org/api/0.6/map?bbox=` endpoint answers in about a second with raw
XML, needs no query language, and is used as the primary road source with Overpass as
fallback; both are cached on disk for 12 h and surrounded by a global back-off so a
dead network costs one timeout, not one per frame. Basemap tiles are proxied and
cached by the backend for the same reason: the map must render during a demo with no
internet. Providers that return a watermark placeholder (a tiny PNG) instead of a tile
are rejected so they cannot poison the cache.

## 11. One simulation loop, sockets subscribe
The loop lives in `SimulationService`, not in a WebSocket handler, so reconnects
and extra tabs cannot spawn duplicate loops. Control commands go over REST, so
lifecycle transitions have a single source of truth.

## 12. The simulator starts aligned with the route
The requested initial heading shapes the route geometry; the vehicle itself is
placed already pointing along the tangent. Starting misaligned injected a fictitious
yaw-rate spike (≈1400 °/s) at t = 0, which the filter correctly treated as a real
manoeuvre and which destroyed the first second of every run.

## 13. Batched persistence
Frames are buffered and flushed per ~250 samples as columnar JSON, with discrete
anomaly events stored individually. This keeps SQLite compact and off the hot
path while still allowing full session replay through the API.
