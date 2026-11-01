"""Navigation engine: one synchronised pipeline step per tick.

Order of operations per step (identical for live runs, offline runs and tests):

    1. vehicle simulator advances -> ground truth + raw IMU/odometry/GNSS
    2. EKF prediction using IMU (always; this is what survives an outage)
    3. GNSS innovation computed *without* applying the update
    4. anomaly detector scores the innovation + measurement history
    5. GNSS update applied only if the measurement is trustworthy
       (the EKF applies its own NIS gate as a second line of defence)
    6. odometry speed update (independent of GNSS)
    7. dead-reckoning integration from the same IMU/odometry inputs
    8. bounded drift correction of the DR branch (never touches the EKF)
    9. drift monitoring + optional experimental ML correction
   10. map matching (advisory only, never fed back)
   11. frame assembled with geodetic coordinates + errors vs ground truth
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app.algorithms.dead_reckoning import DeadReckoningEngine
from app.algorithms.drift_correction import DriftCorrector, DriftMonitor
from app.algorithms.ekf import ExtendedKalmanFilter, I_BA, I_BG, I_PSI, I_V, N_STATE
from app.algorithms.gnss_anomaly import AnomalyResult, DetectorThresholds, GnssAnomalyDetector
from app.algorithms.map_matching import MapMatcher, RoadNetwork, RoadSegment
from app.algorithms.smoother import SmoothingHistory, SmoothedPoint
from app.config import settings
from app.core.coordinate_utils import LocalTangentPlane
from app.core.simulator import SimStep, VehicleSimulator
from app.ml.inference import get_model
from app.models.schemas import GnssStatus, SimulatorConfig
from app.utils.logging import get_logger
from app.utils.metrics import ErrorStats, error_stats

log = get_logger("grids.nav")

DEG = 180.0 / math.pi


@dataclass
class EngineFrame:
    """Internal frame: metric EN coordinates + everything needed for the API."""

    t: float
    timestamp: float
    step: int

    truth_e: float
    truth_n: float
    truth_lat: float
    truth_lon: float

    gnss_e: Optional[float]
    gnss_n: Optional[float]
    gnss_lat: Optional[float]
    gnss_lon: Optional[float]

    dr_e: float
    dr_n: float
    dr_lat: float
    dr_lon: float

    ekf_e: float
    ekf_n: float
    ekf_lat: float
    ekf_lon: float

    ml_e: Optional[float]
    ml_n: Optional[float]
    ml_lat: Optional[float]
    ml_lon: Optional[float]

    # retrospective (fixed-lag RTS) track and map-aided estimate
    sm_e: Optional[float]
    sm_n: Optional[float]
    sm_lat: Optional[float]
    sm_lon: Optional[float]
    # shadow filter without map aiding: honest A/B for the map contribution
    nomap_e: Optional[float]
    nomap_n: Optional[float]
    nomap_lat: Optional[float]
    nomap_lon: Optional[float]

    speed: float
    heading_deg: float
    accel: float
    yaw_rate_dps: float

    gnss_status: str
    gnss_available: bool
    gnss_accepted: bool
    gnss_residual_m: Optional[float]
    nis: Optional[float]
    innov_e: Optional[float]
    innov_n: Optional[float]
    rejected_count: int

    anomaly: bool
    anomaly_score: float
    anomaly_type: str
    anomaly_reason: str

    ekf_error_m: float
    dr_error_m: float
    gnss_error_m: Optional[float]
    ml_error_m: Optional[float]
    sm_error_m: Optional[float]
    nomap_error_m: Optional[float]
    drift_estimate_m: float
    drift_rate_ms: float
    uncertainty_m: float
    position_sigma_m: float

    injected_fault: str
    sm_sigma_m: Optional[float] = None
    anomaly_severities: Dict[str, float] = field(default_factory=dict)
    modules: Dict[str, str] = field(default_factory=dict)
    map_match: Optional[dict] = None

    def to_api(self) -> dict:
        return {
            "t": round(self.t, 3),
            "timestamp": round(self.timestamp, 3),
            "truth_lat": self.truth_lat,
            "truth_lon": self.truth_lon,
            "gnss_lat": self.gnss_lat,
            "gnss_lon": self.gnss_lon,
            "dr_lat": self.dr_lat,
            "dr_lon": self.dr_lon,
            "ekf_lat": self.ekf_lat,
            "ekf_lon": self.ekf_lon,
            "ml_lat": self.ml_lat,
            "ml_lon": self.ml_lon,
            "sm_lat": self.sm_lat,
            "sm_lon": self.sm_lon,
            "nomap_lat": self.nomap_lat,
            "nomap_lon": self.nomap_lon,
            "speed_ms": round(self.speed, 3),
            "heading_deg": round(self.heading_deg, 2),
            "accel_ms2": round(self.accel, 3),
            "yaw_rate_dps": round(self.yaw_rate_dps, 2),
            "gnss_status": self.gnss_status,
            "gnss_available": self.gnss_available,
            "gnss_residual_m": None if self.gnss_residual_m is None else round(self.gnss_residual_m, 2),
            "gnss_accepted": self.gnss_accepted,
            "rejected_count": self.rejected_count,
            "anomaly": self.anomaly,
            "anomaly_score": round(self.anomaly_score, 3),
            "anomaly_reason": self.anomaly_reason,
            "nis": None if self.nis is None else round(self.nis, 3),
            "ekf_error_m": round(self.ekf_error_m, 3),
            "dr_error_m": round(self.dr_error_m, 3),
            "gnss_error_m": None if self.gnss_error_m is None else round(self.gnss_error_m, 3),
            "ml_error_m": None if self.ml_error_m is None else round(self.ml_error_m, 3),
            "sm_error_m": None if self.sm_error_m is None else round(self.sm_error_m, 3),
            "nomap_error_m": None if self.nomap_error_m is None else round(self.nomap_error_m, 3),
            "drift_estimate_m": round(self.drift_estimate_m, 3),
            "drift_rate_ms": round(self.drift_rate_ms, 4),
            "uncertainty_m": round(self.uncertainty_m, 3),
            "position_sigma_m": round(self.position_sigma_m, 3),
            "anomaly_severities": self.anomaly_severities,
            "modules": self.modules,
            "map_match": self.map_match,
        }


class NavigationEngine:
    """Full navigation pipeline for a single simulation run."""

    def __init__(self, config: SimulatorConfig, seed: Optional[int] = None) -> None:
        self.config = config
        self.seed = seed
        self.dt = 1.0 / float(config.rate_hz)
        self.plane = LocalTangentPlane(config.origin_lat, config.origin_lon)
        self.simulator = VehicleSimulator(config, seed=seed)
        self.gnss_noise_sigma = config.noise.gnss_position_sigma_m

        # Process/measurement noise are tuned from the configured sensor noise.
        # The accelerometer/gyro terms are inflated relative to the raw sensor
        # sigma because the motion model ignores lateral dynamics and road
        # grade; the speed term uses the odometry sigma directly (it is a real
        # measurement, not a model).
        self.ekf = ExtendedKalmanFilter(
            plane=self.plane,
            gnss_sigma_m=max(0.5, config.noise.gnss_position_sigma_m) * 1.15,
            speed_sigma_ms=max(0.03, config.noise.speed_sigma_ms * 1.5),
            heading_sigma_deg=2.0,
            accel_noise=max(0.04, config.noise.accel_sigma_ms2 * 4.0),
            gyro_noise_deg=max(0.04, config.noise.gyro_sigma_dps * 4.0),
            nis_gate=settings.anomaly_innovation_gate,
        )
        # Shadow filter: identical model, NO map aiding. Always running so the
        # dashboard and the report can show what the map constraint actually
        # contributes instead of asserting a benefit.
        self.ekf_nomap = ExtendedKalmanFilter(
            plane=self.plane,
            gnss_sigma_m=max(0.5, config.noise.gnss_position_sigma_m) * 1.15,
            speed_sigma_ms=max(0.03, config.noise.speed_sigma_ms * 1.5),
            heading_sigma_deg=2.0,
            accel_noise=max(0.04, config.noise.accel_sigma_ms2 * 4.0),
            gyro_noise_deg=max(0.04, config.noise.gyro_sigma_dps * 4.0),
            nis_gate=settings.anomaly_innovation_gate,
        )
        self.dr = DeadReckoningEngine(
            plane=self.plane,
            speed=0.0,
            heading=math.radians(config.initial_heading_deg),
        )
        self.detector = GnssAnomalyDetector(
            DetectorThresholds(
                gnss_sigma_m=max(0.5, config.noise.gnss_position_sigma_m),
                jump_m=settings.anomaly_jump_threshold_m,
                nis_warn=settings.anomaly_innovation_gate,
            )
        )
        self.drift_monitor = DriftMonitor()
        self.corrector = DriftCorrector(gain=0.08, max_correction_m=2.5, trust_ekf_coast=False)
        self.map_matcher: Optional[MapMatcher] = None
        self.smoother = SmoothingHistory(max_len=260)
        self._last_match: Optional[dict] = None
        self.map_aiding_available = False
        self._map_discredited = False
        self._map_reject_streak = 0
        # Exponential average of the road offset observed while GNSS was
        # trusted. Map aiding is only allowed when the fused track has been
        # consistently close to the road graph, so a route that is not on the
        # street network can never be dragged onto it.
        self.map_offset_ema: Optional[float] = None
        self.smooth_lag_s = 4.0            # fixed-lag used for the live RTS track
        self.smoothed_fixes = 0
        self.map_aided = bool(config.enable_map_aiding)
        self.map_anchor: Optional[tuple] = None
        self.map_constraints = 0
        self._route_hint: Optional[tuple] = None
        self.map_source: str = "none"
        self.osm_info: Optional[dict] = None
        self.ml_model = get_model()
        self.ml_enabled = bool(config.enable_ml_correction and self.ml_model.available)

        self.frames: List[EngineFrame] = []
        self.anomaly_events: List[dict] = []
        self.initialised = False
        self.t_last_gnss: Optional[float] = None
        self.rejected_total = 0
        self.accepted_total = 0
        self._healthy_streak = 0
        self.t0_wall = time.time()

    # ------------------------------------------------------------------ init ---
    def _initialise(self, s: SimStep) -> None:
        """Cold start: use the first good GNSS fix if present, otherwise origin."""
        if s.gnss_e is not None:
            e0, n0 = s.gnss_e, s.gnss_n
            sigma0 = self.gnss_noise_sigma * 1.5
            self.t_last_gnss = s.t
        else:
            e0, n0 = 0.0, 0.0
            sigma0 = 80.0  # unknown initial position
        heading = math.radians(self.config.initial_heading_deg)
        x0 = np.zeros(N_STATE)
        x0[0], x0[1] = e0, n0
        x0[I_V] = 0.0
        # Initialise from the vehicle's actual starting heading (it is aligned
        # with the route tangent), not from the requested route seed heading.
        heading = float(self.simulator.heading)
        x0[I_PSI] = heading
        P0 = np.diag(
            [max(4.0, sigma0 ** 2), max(4.0, sigma0 ** 2), 0.5,
             math.radians(8.0) ** 2, 0.2 ** 2, math.radians(1.0) ** 2]
        )
        self.ekf.reset(x0, P0)
        self.ekf_nomap.reset(x0, P0)
        self.dr.reset(e0, n0, 0.0, heading)
        self.smoother.clear()

        # road network for map matching. The synthetic network derived from the
        # simulated route always works offline; OpenStreetMap is used only when
        # explicitly enabled and reachable.
        if self.config.enable_map_matching:
            net = None
            self.map_source = "synthetic"
            try:
                from app.services.map_data_service import build_road_network

                if self.config.use_real_map_data:
                    net, info = build_road_network(
                        self.config.origin_lat, self.config.origin_lon,
                        radius_m=float(self.config.map_radius_m),
                    )
                    if net is not None:
                        self.map_source = "osm"
                    self.osm_info = info
            except Exception as exc:  # pragma: no cover - network layer
                log.info("real map data unavailable (%s); using synthetic network", exc)
            if net is None:
                net = RoadNetwork.from_polyline(
                    [tuple(p) for p in self.simulator.route.points], name="simulated route"
                )
            self.map_matcher = MapMatcher(network=net, max_snap_distance_m=40.0)
            # Cross-track aiding is only trusted on a surveyed street network.
            # The synthetic network is a skeleton of the simulated route (it has
            # chords instead of carriageways), so it is used for the matching
            # read-out but never to constrain the filter.
            self.map_aiding_available = net.source == "osm"
        self.initialised = True

    # ------------------------------------------------------------------ step ---
    def step(self) -> EngineFrame:
        cfg = self.config
        s = self.simulator.step()
        if not self.initialised:
            self._initialise(s)

        dt = self.dt
        # --- 2. EKF prediction (runs with or without GNSS) ---
        _, trans_F = self.ekf.predict(dt, s.imu_accel, s.imu_yaw_rate, keep_jacobian=True)
        self.ekf_nomap.predict(dt, s.imu_accel, s.imu_yaw_rate)
        # x_k|k-1 and P_k|k-1 are what an RTS smoother needs for step k
        pred_x_k = self.ekf.x.copy()
        pred_P_k = self.ekf.P.copy()

        # --- 3./4. GNSS innovation + anomaly evaluation ---
        gnss_en = (s.gnss_e, s.gnss_n) if s.gnss_lat is not None else None
        nis = None
        inn = None
        ekf_pos = self.ekf.position
        innov_pair = None
        if gnss_en is not None:
            inn = self.ekf.innovation_gnss(*gnss_en)
            nis = inn.nis
            innov_pair = (gnss_en[0] - ekf_pos[0], gnss_en[1] - ekf_pos[1])
        anomaly: AnomalyResult = self.detector.evaluate(
            t=s.t,
            gnss_en=gnss_en,
            ekf_en=ekf_pos,
            uncertainty_m=self.ekf.uncertainty(),
            nis=nis,
            fused_speed=float(self.ekf.x[I_V]),
            fused_heading=float(self.ekf.x[I_PSI]),
            heading_rate=s.imu_yaw_rate,
        )

        # --- 5. gated GNSS update ---
        accepted = False
        gated_out = False
        if gnss_en is not None and not anomaly.reject:
            inn2 = self.ekf.update_gnss(
                gnss_en[0], gnss_en[1], timestamp=s.t, gate=True,
                extra_sigma_m=anomaly.extra_sigma_m,
            )
            accepted = bool(inn2.accepted)
            if accepted:
                self.ekf_nomap.update_gnss(
                    gnss_en[0], gnss_en[1], timestamp=s.t, gate=False,
                    extra_sigma_m=anomaly.extra_sigma_m,
                )
            if accepted:
                self.t_last_gnss = s.t
                self.accepted_total += 1
            else:
                gated_out = True
                self.rejected_total += 1
        elif gnss_en is not None:
            self.rejected_total += 1

        # --- 6. odometry speed update (GNSS independent) ---
        self.ekf.update_speed(s.odom_speed)
        self.ekf_nomap.update_speed(s.odom_speed)

        # --- 6b. map-aided cross-track constraint -------------------------
        # A soft pseudo-measurement that says "you are on this road". It is
        # applied only while the map match is credible (small offset) and is
        # gated by its own innovation, so a wrong map cannot hijack the filter.
        map_applied = False
        map_confident = False
        # Aiding is a *coasting* aid: while GNSS is trusted the filter already
        # has a better measurement than the road centre-line, and forcing it
        # onto a road would bias healthy innovations (and can drag the track
        # onto the wrong street). It is therefore applied only when the GNSS
        # channel is not delivering accepted fixes.
        coasting = (not s.gnss_available) or (not accepted)
        # Trust requires a tight, persistent match and a filter that still knows
        # roughly where it is. Loose gates let a road 10 m away capture a track
        # that is not actually on that street.
        map_trusted = bool(
            self.map_offset_ema is not None
            and self.map_offset_ema <= 5.0
            and self.ekf.position_sigma() <= 20.0
            and self._map_discredited is False
        )
        if (
            self.map_aided
            and coasting
            and map_trusted
            and self.map_aiding_available
            and self.map_matcher is not None
            and self.map_matcher.available
        ):
            ex, ny_ = self.ekf.position
            seg, offset, cp = self.map_matcher.network.nearest_within(
                (ex, ny_), self.map_matcher.max_snap * 1.5
            )
            # Confidence gate: a wrong road must never pull the filter. The
            # match has to be close *and* the filter has to be reasonably sure
            # of where it is (a coasting filter near a junction is not).
            map_confident = bool(
                seg is not None
                and offset <= min(5.0, self.map_matcher.max_snap)
                and self.ekf.position_sigma() <= 20.0
            )
            if map_confident:
                heading = math.atan2(seg.b[0] - seg.a[0], seg.b[1] - seg.a[1])
                # sigma scales with confidence in the map: a close match gets a
                # tighter corridor than a marginal one
                sigma_ct = max(2.0, 1.0 * offset + 0.5 * self.ekf.position_sigma())
                map_applied = self.ekf.update_cross_track(
                    cp[0], cp[1], heading, sigma_m=sigma_ct, gate=3.0
                )
                if map_applied:
                    self.map_constraints += 1
                    self.map_anchor = (cp[0], cp[1], heading)

        # --- 7. dead reckoning ---
        self.dr.step(dt, s.imu_accel, s.imu_yaw_rate, odom_speed=s.odom_speed)

        # --- 8. conservative drift correction of the DR branch ---
        # The DR branch may only be pulled toward the filter while the GNSS
        # channel is demonstrably healthy; otherwise the corrector would copy a
        # corrupted estimate into the independent dead-reckoning track.
        dr_en = self.dr.position
        self._healthy_streak = (
            self._healthy_streak + 1 if (accepted and not anomaly.is_anomaly) else 0
        )
        corrector_trusted = bool(accepted and not anomaly.is_anomaly and self._healthy_streak >= 5)
        de, dn, applied = self.corrector.compute(
            dr_en, self.ekf.position, gnss_trusted=corrector_trusted
        )
        if applied:
            self.dr.correct(de, dn)

        # --- 9. drift monitoring ---
        drift = self.drift_monitor.record(
            t=s.t,
            dr_en=self.dr.position,
            ekf_en=self.ekf.position,
            truth_en=(s.truth_e, s.truth_n),
            accepted_residual=(anomaly.residual_m if accepted else None),
        )

        # --- ML correction (experimental, optional) ---
        ml_en = None
        if self.ml_enabled:
            corr = self.ml_model.predict(
                innovation=innov_pair or (0.0, 0.0),
                gnss_available=gnss_en is not None,
                nis=nis,
                uncertainty_m=self.ekf.uncertainty(),
                speed=float(self.ekf.x[I_V]),
                yaw_rate=s.imu_yaw_rate,
                time_since_gnss=(s.t - self.t_last_gnss) if self.t_last_gnss is not None else 99.0,
                residual_m=anomaly.residual_m,
                rejected=anomaly.reject,
                anomaly_score=anomaly.score,
            )
            if corr.applied:
                ml_en = (self.ekf.position[0] + corr.de, self.ekf.position[1] + corr.dn)

        # --- 9b. fixed-lag RTS smoothing (retrospective track) ------------
        self.smoother.push(
            step=s.step,
            t=s.t,
            filt_x=self.ekf.x,
            filt_P=self.ekf.P,
            F=trans_F,
            pred_x=pred_x_k,
            pred_P=pred_P_k,
        )
        lag_steps = max(1, int(round(self.smooth_lag_s / dt)))
        sm_pt: Optional[SmoothedPoint] = None
        if len(self.smoother) > lag_steps + 2:
            sm_pt = self.smoother.lagged_point(lag_steps=lag_steps)

        # --- build geodetic coordinates ---
        ekf_lat, ekf_lon = self.ekf.geodetic
        dr_lat, dr_lon = self.dr.geodetic()
        ml_lat = ml_lon = None
        if ml_en is not None:
            ml_lat, ml_lon = self.plane.to_geodetic(*ml_en)

        ekf_err = math.hypot(self.ekf.position[0] - s.truth_e, self.ekf.position[1] - s.truth_n)
        dr_err = math.hypot(self.dr.position[0] - s.truth_e, self.dr.position[1] - s.truth_n)
        gnss_err = (
            math.hypot(s.gnss_e - s.truth_e, s.gnss_n - s.truth_n)
            if s.gnss_e is not None
            else None
        )
        ml_err = (
            math.hypot(ml_en[0] - s.truth_e, ml_en[1] - s.truth_n) if ml_en else None
        )
        # The RTS estimate produced now refers to a past sample. It is written
        # back into that sample's frame, so the retrospective track is scored
        # against the ground truth of its own timestamp (never against "now").
        sm_en = None
        if sm_pt is not None:
            idx = sm_pt.step - 1
            if 0 <= idx < len(self.frames):
                past = self.frames[idx]
                past.sm_e, past.sm_n = sm_pt.east, sm_pt.north
                past.sm_lat, past.sm_lon = self.plane.to_geodetic(sm_pt.east, sm_pt.north)
                past.sm_error_m = math.hypot(
                    sm_pt.east - past.truth_e, sm_pt.north - past.truth_n
                )
                past.sm_sigma_m = sm_pt.sigma_m
                if past.sm_error_m:
                    self.smoothed_fixes += 1
        sm_lat = sm_lon = None
        sm_err = None
        # shadow (no map aiding) output for an honest A/B comparison
        nomap_en = self.ekf_nomap.position
        nomap_lat, nomap_lon = self.plane.to_geodetic(*nomap_en)
        nomap_err = math.hypot(nomap_en[0] - s.truth_e, nomap_en[1] - s.truth_n)

        status = self.detector.status(
            available=gnss_en is not None,
            residual_m=anomaly.residual_m if gnss_en is not None else None,
            result=anomaly,
        )

        if gnss_en is None:
            gnss_module = "unavailable"
        elif anomaly.reject or gated_out:
            gnss_module = "rejected"
        elif anomaly.extra_sigma_m > 0:
            gnss_module = "degraded"
        else:
            gnss_module = "active"

        if gnss_en is None:
            ekf_module = "coasting"
        elif gnss_module == "active":
            ekf_module = "active"
        else:
            ekf_module = "degraded"

        modules = {
            "gnss": gnss_module,
            "dead_reckoning": "active",
            "ekf": ekf_module,
            "anomaly_detection": "alert" if anomaly.is_anomaly else "active",
            "drift_correction": ("active" if applied else "idle")
            if gnss_module != "unavailable" else "suspended (no trusted reference)",
            "map_matching": "n/a" if self.map_matcher is None else "active",
            "map_aiding": (
                "active" if map_applied
                else ("idle" if self.map_aided else "off")
            ),
            "smoothing": "active" if sm_pt is not None else "warming up",
        }

        # --- 10. map matching (throttled; the last fix is held in between) ---
        if self.map_matcher is not None and (s.step % 5 == 0):
            raw = self.map_matcher.match_geodetic(self.plane, ekf_lat, ekf_lon)
            self._last_match = {
                "matched": bool(raw.get("matched")),
                "offset_m": round(raw.get("offset_m") or 0.0, 2),
                "road": raw.get("road"),
                "lat": raw.get("lat"),
                "lon": raw.get("lon"),
                "reason": raw.get("reason"),
                "t": round(s.t, 2),
            }
        mm = self._last_match
        if mm is not None:
            modules["map_matching"] = "active" if mm["matched"] else "degraded"
        # Only a *delivered but rejected* fix is evidence that the road
        # constraint is fighting the receiver; during an outage there is simply
        # nothing to disagree with.
        if map_applied and s.gnss_available and not accepted:
            self._map_reject_streak += 1
            if self._map_reject_streak >= 25:      # ~2.5 s at 10 Hz
                self._map_discredited = True
                log.info("map aiding discredited at t=%.1f s (GNSS kept failing "
                         "while the road constraint was active)", s.t)
        else:
            self._map_reject_streak = 0
        if accepted and mm is not None and mm.get("matched"):
            off = float(mm.get("offset_m") or 0.0)
            self.map_offset_ema = off if self.map_offset_ema is None else (
                0.98 * self.map_offset_ema + 0.02 * off
            )
        modules["map_aiding"] = (
            "active" if map_applied
            else ("off" if not self.map_aided else
                  ("idle" if not coasting else "gated (map not trusted)"))
        )

        frame = EngineFrame(
            t=s.t,
            timestamp=s.timestamp,
            step=s.step,
            truth_e=s.truth_e,
            truth_n=s.truth_n,
            truth_lat=s.truth_lat,
            truth_lon=s.truth_lon,
            gnss_e=s.gnss_e,
            gnss_n=s.gnss_n,
            gnss_lat=s.gnss_lat,
            gnss_lon=s.gnss_lon,
            dr_e=self.dr.position[0],
            dr_n=self.dr.position[1],
            dr_lat=dr_lat,
            dr_lon=dr_lon,
            ekf_e=self.ekf.position[0],
            ekf_n=self.ekf.position[1],
            ekf_lat=ekf_lat,
            ekf_lon=ekf_lon,
            ml_e=ml_en[0] if ml_en else None,
            ml_n=ml_en[1] if ml_en else None,
            ml_lat=ml_lat,
            ml_lon=ml_lon,
            sm_e=None,
            sm_n=None,
            sm_lat=sm_lat,
            sm_lon=sm_lon,
            nomap_e=nomap_en[0],
            nomap_n=nomap_en[1],
            nomap_lat=nomap_lat,
            nomap_lon=nomap_lon,
            speed=float(self.ekf.x[I_V]),
            heading_deg=float(s.truth_heading * DEG % 360.0),
            accel=float(s.truth_accel),
            yaw_rate_dps=float(s.truth_yaw_rate * DEG),
            gnss_status=status,
            gnss_available=gnss_en is not None,
            gnss_accepted=accepted,
            gnss_residual_m=anomaly.residual_m if gnss_en is not None else None,
            nis=nis,
            innov_e=innov_pair[0] if innov_pair else None,
            innov_n=innov_pair[1] if innov_pair else None,
            rejected_count=self.rejected_total,
            anomaly=anomaly.is_anomaly,
            anomaly_score=anomaly.score,
            anomaly_type=anomaly.anomaly_type,
            anomaly_reason=anomaly.reason,
            ekf_error_m=ekf_err,
            dr_error_m=dr_err,
            gnss_error_m=gnss_err,
            ml_error_m=ml_err,
            sm_error_m=sm_err,
            sm_sigma_m=None,
            nomap_error_m=nomap_err,
            drift_estimate_m=drift.dr_vs_ekf_m,
            drift_rate_ms=drift.drift_rate_ms,
            uncertainty_m=self.ekf.uncertainty(),
            position_sigma_m=self.ekf.position_sigma(),
            injected_fault=s.injected_fault,
            anomaly_severities=dict(anomaly.severities or {}),
            modules=modules,
            map_match=mm,
        )

        if anomaly.is_anomaly and (anomaly.reject or anomaly.anomaly_type != "residual"):
            self.anomaly_events.append(
                {
                    "t": round(frame.t, 3),
                    "timestamp": round(frame.timestamp, 3),
                    "anomaly_type": anomaly.anomaly_type,
                    "score": round(anomaly.score, 3),
                    "reason": anomaly.reason,
                    "residual_m": round(anomaly.residual_m, 2),
                    "rejected": bool(anomaly.reject),
                }
            )

        self.frames.append(frame)
        return frame

    # ------------------------------------------------------------- analytics ---
    def algorithm_errors(self) -> Dict[str, ErrorStats]:
        return {
            "gnss": error_stats([f.gnss_error_m for f in self.frames]),
            "dead_reckoning": error_stats([f.dr_error_m for f in self.frames]),
            "ekf": error_stats([f.ekf_error_m for f in self.frames]),
            "ekf_ml": error_stats([f.ml_error_m for f in self.frames]),
            "ekf_nomap": error_stats([f.nomap_error_m for f in self.frames]),
            "rts_smoothed": error_stats([f.sm_error_m for f in self.frames]),
        }

    def smoothed_track(self, max_points: int = 900) -> List[dict]:
        """Retrospective (RTS) track attached to the stored frames."""
        pts = [
            {
                "t": round(f.t, 2),
                "lat": f.sm_lat,
                "lon": f.sm_lon,
                "error_m": round(f.sm_error_m, 2) if f.sm_error_m is not None else None,
                "sigma_m": round(f.sm_sigma_m, 2) if f.sm_sigma_m is not None else None,
            }
            for f in self.frames
            if f.sm_lat is not None
        ]
        if len(pts) > max_points:
            stride = len(pts) // max_points + 1
            pts = pts[::stride]
        return pts

    def route_geodetic(self) -> List[dict]:
        return self.simulator.route_geodetic()

    def outage_window(self) -> Optional[tuple]:
        return self.simulator.outage_window()
