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
A slow bias is intrinsically ambiguous with respect to filter divergence. The
reference drift run still yields EKF RMSE 25.9 m vs DR 32.0 m (simulated), i.e.
the filter helps but the drift scenario remains the weakest case. This is stated
in the README's limitations rather than being tuned away with an
OSM-reference or truth-based correction that would not exist in reality.

## 6. Drift correction cannot touch the EKF
The corrector pulls the DR branch toward the filter only after five consecutive
clean GNSS updates. A corrupted filter therefore cannot be copied into the
independent dead-reckoning track (this was observed during development and fixed).

## 7. ML correction is opt-in and measured
The layer is trained on six simulated sessions and evaluated on three held-out
sessions with unseen seeds. The measured held-out result was worse than the EKF
baseline, so the default stays off and the dashboard shows the delta. Tests assert
that the recommendation follows the measurement, not an assumption.

## 8. Map matching is advisory
Road data may be missing (offline) or wrong. Snapping never feeds back into the
filter, the synthetic network is always available, and OSM is opt-in.

## 9. One simulation loop, sockets subscribe
The loop lives in `SimulationService`, not in a WebSocket handler, so reconnects
and extra tabs cannot spawn duplicate loops. Control commands go over REST, so
lifecycle transitions have a single source of truth.

## 10. Batched persistence
Frames are buffered and flushed per ~250 samples as columnar JSON, with discrete
anomaly events stored individually. This keeps SQLite compact and off the hot
path while still allowing full session replay through the API.
