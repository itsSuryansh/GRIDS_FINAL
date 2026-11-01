"""Vehicle motion + GNSS/IMU sensor simulator.

Design notes
------------
* Routes are generated as dense polylines in a local East-North metric frame
  anchored at the configured origin. Distances are therefore in metres and
  headings are clockwise-from-north, matching vehicle convention.
* The vehicle follows the route with a bounded longitudinal acceleration and
  a speed that is reduced in curves, which produces realistic yaw rates and
  lateral accelerations without needing a full tyre model.
* Sensors are generated from the ground truth: IMU (specific force along the
  body x-axis + yaw rate), wheel-speed odometry and GNSS position. Every sensor
  carries configurable 1-sigma noise plus a *true* accelerometer / gyroscope
  bias so dead reckoning genuinely accumulates error.
* GNSS faults are injected here (outage / drift / spoofing) and the injected
  fault is reported separately from what the anomaly detector concludes.

The generated data is simulated. It is not real-world sensor data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from app.core.coordinate_utils import (
    LocalTangentPlane,
    wrap_angle,
)
from app.models.schemas import RoutePattern, ScenarioType, SimulatorConfig

DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi


# ------------------------------------------------------------------ routes ---
@dataclass
class Route:
    """Dense polyline with cumulative arc length (metres, local EN frame)."""

    points: np.ndarray          # (N, 2) east/north
    arclen: np.ndarray          # (N,) cumulative distance
    headings: np.ndarray        # (N,) tangent heading radians cw-from-north
    curvature: np.ndarray       # (N,) 1/m

    @property
    def length(self) -> float:
        return float(self.arclen[-1])

    def sample(self, s: float) -> Tuple[float, float, float, float]:
        """Interpolate (east, north, heading, curvature) at arc length s."""
        s = min(max(s, 0.0), self.length)
        i = int(np.searchsorted(self.arclen, s, side="right") - 1)
        i = max(0, min(i, len(self.points) - 2))
        seg = self.arclen[i + 1] - self.arclen[i]
        frac = 0.0 if seg <= 1e-9 else (s - self.arclen[i]) / seg
        p0, p1 = self.points[i], self.points[i + 1]
        e = p0[0] + frac * (p1[0] - p0[0])
        n = p0[1] + frac * (p1[1] - p0[1])
        h = self.headings[i] + frac * wrap_angle(self.headings[i + 1] - self.headings[i])
        k = self.curvature[i] + frac * (self.curvature[i + 1] - self.curvature[i])
        return float(e), float(n), float(h), float(k)


def _finalise(points: np.ndarray, step: float = 0.5) -> Route:
    """Densify, compute arc length, tangents and curvature."""
    diffs = np.linalg.norm(np.diff(points, axis=0), axis=1)
    keep = np.concatenate([[True], diffs > 1e-6])
    pts = points[keep]
    if len(pts) < 2:
        pts = np.array([[0.0, 0.0], [0.0, 1.0]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arclen = np.concatenate([[0.0], np.cumsum(seg)])

    # resample at ~step spacing for smooth interpolation
    n_out = max(2, int(arclen[-1] / step) + 1)
    s_out = np.linspace(0.0, arclen[-1], n_out)
    e_out = np.interp(s_out, arclen, pts[:, 0])
    n_out_arr = np.interp(s_out, arclen, pts[:, 1])
    new_pts = np.column_stack([e_out, n_out_arr])

    d = np.gradient(new_pts, axis=0)
    headings = np.arctan2(d[:, 0], d[:, 1])
    headings = np.unwrap(headings)
    ds = np.gradient(s_out)
    ds[ds <= 1e-9] = 1e-9
    curvature = np.gradient(headings) / ds
    return Route(points=new_pts, arclen=s_out, headings=headings, curvature=curvature)


def _polyline_with_heading(
    start: Tuple[float, float], heading: float, length: float, step: float = 0.5
) -> np.ndarray:
    n = max(2, int(length / step) + 1)
    s = np.linspace(0.0, length, n)
    e = start[0] + s * math.sin(heading)
    nn = start[1] + s * math.cos(heading)
    return np.column_stack([e, nn])


def _arc_points(
    start: Tuple[float, float], heading: float, turn_rad: float, radius: float, step: float = 0.5
) -> np.ndarray:
    """Circular arc starting at ``start`` with the given heading and turn angle.

    Heading is clockwise-from-north and increases when turning right. The
    centre sits on the inside of the turn, so the arc is traced by rotating the
    radius vector in the opposite sense to the turn direction.
    """
    sign = 1.0 if turn_rad > 0 else -1.0
    cx = start[0] + sign * radius * math.cos(heading)
    cy = start[1] - sign * radius * math.sin(heading)
    theta0 = math.atan2(start[1] - cy, start[0] - cx)
    length = abs(turn_rad) * radius
    n = max(8, int(length / step) + 1)
    phis = np.linspace(0.0, abs(turn_rad), n)
    ang = theta0 - sign * phis
    return np.column_stack([cx + radius * np.cos(ang), cy + radius * np.sin(ang)])


def _resample_polyline(points: np.ndarray, spacing: float = 0.5) -> np.ndarray:
    """Resample a polyline at (approximately) fixed spacing."""
    pts = np.asarray(points, dtype=float)
    if len(pts) < 2:
        return pts
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    keep = np.concatenate([[True], seg > 1e-9])
    pts = pts[keep]
    if len(pts) < 2:
        return pts
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arclen = np.concatenate([[0.0], np.cumsum(seg)])
    n_out = max(2, int(arclen[-1] / spacing) + 1)
    s_out = np.linspace(0.0, arclen[-1], n_out)
    return np.column_stack([
        np.interp(s_out, arclen, pts[:, 0]),
        np.interp(s_out, arclen, pts[:, 1]),
    ])


def _round_corners(points: np.ndarray, radius: float = 12.0, max_trim: float = 25.0) -> np.ndarray:
    """Replace sharp vertices with quadratic fillets so heading stays continuous."""
    if len(points) < 3:
        return points
    out = [points[0]]
    for i in range(1, len(points) - 1):
        p_prev, p, p_next = points[i - 1], points[i], points[i + 1]
        v1, v2 = p_prev - p, p_next - p
        l1, l2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if l1 < 1e-6 or l2 < 1e-6:
            out.append(p)
            continue
        u1, u2 = v1 / l1, v2 / l2
        cosang = float(np.clip(u1 @ u2, -1.0, 1.0))
        if cosang > 0.999:                       # straight through
            out.append(p)
            continue
        trim = min(radius, max_trim, 0.45 * l1, 0.45 * l2)
        a = p + u1 * trim
        b = p + u2 * trim
        t = np.linspace(0.0, 1.0, max(4, int(trim)))
        curve = ((1 - t)[:, None] ** 2) * a + 2 * ((1 - t) * t)[:, None] * p + (t[:, None] ** 2) * b
        out.append(curve)
    out.append(points[-1])
    return np.vstack(out)


def _clip_segment(
    a: np.ndarray, b: np.ndarray, box: float
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Liang-Barsky clip of a segment to [-box, box]^2 (returns None if outside)."""
    dx, dy = float(b[0] - a[0]), float(b[1] - a[1])
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] + box), (dx, box - a[0]), (-dy, a[1] + box), (dy, box - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    if t1 - t0 < 1e-9:
        return None
    return (
        (a[0] + t0 * dx, a[1] + t0 * dy),
        (a[0] + t1 * dx, a[1] + t1 * dy),
    )


def build_road_route(
    ways: Sequence[Sequence[Tuple[float, float]]],
    rng: np.random.Generator,
    min_length_m: float = 350.0,
    extent_m: float = 600.0,
) -> Optional[np.ndarray]:
    """Follow a real street graph (local EN metres).

    Every way is clipped to a square window and split into individual block
    edges, which become the edges of the road graph. A randomised walk that
    prefers turning at junctions then produces a route that owns real street
    geometry -- exactly what map matching and map aiding are meant to exploit.
    Cost is linear in the number of edges and the walk is O(1) per metre.
    """
    box = float(extent_m)
    key = lambda p: (round(p[0] / 1.5), round(p[1] / 1.5))     # ~1.5 m nodes
    nodes: dict = {}
    coords: List[np.ndarray] = []
    adj: List[List[Tuple[int, float]]] = []

    def node_id(x: float, y: float) -> int:
        k = (round(x / 1.5), round(y / 1.5))
        idx = nodes.get(k)
        if idx is None:
            idx = len(coords)
            nodes[k] = idx
            coords.append(np.array([x, y], dtype=float))
            adj.append([])
        return idx

    edges = set()
    for way in ways:
        pts = [np.asarray(p, dtype=float) for p in way]
        for a, b in zip(pts, pts[1:]):
            clipped = _clip_segment(a, b, box)
            if clipped is None:
                continue
            (x0, y0), (x1, y1) = clipped
            d = math.hypot(x1 - x0, y1 - y0)
            if d < 1.5:                     # drop sub-metre geometry clutter
                continue
            i, j = node_id(x0, y0), node_id(x1, y1)
            if i == j or (min(i, j), max(i, j)) in edges:
                continue
            edges.add((min(i, j), max(i, j)))
            adj[i].append((j, d))
            adj[j].append((i, d))
    if len(coords) < 8:
        return None

    # snap the start to the graph node closest to the origin of the run
    start = min(range(len(coords)), key=lambda i: float(np.linalg.norm(coords[i])))
    path_idx = [start]
    current = start
    came_from = -1
    total = 0.0

    def heading_of(a: int, b: int) -> float:
        d = coords[b] - coords[a]
        return math.atan2(d[0], d[1])

    while total < min_length_m and len(path_idx) < 6000:
        options = [(j, d) for j, d in adj[current] if j != came_from]
        if not options:                                   # dead end
            if len(path_idx) <= 1:
                break
            path_idx.pop()
            came_from = path_idx[-1] if len(path_idx) >= 2 else -1
            current = path_idx[-1]
            continue
        in_heading = heading_of(came_from, current) if came_from >= 0 else None
        best, best_score = None, -1.0
        for j, d in options:
            if in_heading is None:
                score = float(rng.random())
            else:
                turn = abs(wrap_angle(heading_of(current, j) - in_heading))
                # prefer an actual turn at a junction, but allow straight on
                pref = 1.0 if 0.2 < turn < 1.9 else 0.3
                # prefer unvisited nodes when it does not cost much
                score = pref * (0.4 + float(rng.random()))
            if score > best_score:
                best, best_score = (j, d), score
        assert best is not None
        j, d = best
        path_idx.append(j)
        total += d
        came_from, current = current, j
    if len(path_idx) < 3:
        return None
    return _round_corners(np.vstack([coords[i] for i in path_idx]))


def build_route(
    pattern: RoutePattern,
    speed_ms: float,
    duration_s: float,
    initial_heading_rad: float,
    rng: np.random.Generator,
    custom_points_m: Optional[Sequence[Tuple[float, float]]] = None,
    road_vertices_m: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
) -> Route:
    """Create a route polyline for the requested movement pattern."""
    total = max(20.0, speed_ms * duration_s * 1.25)
    h0 = initial_heading_rad

    if pattern == RoutePattern.ROAD and road_vertices_m:
        poly = build_road_route(list(road_vertices_m), rng,
                                min_length_m=max(total, 200.0),
                                extent_m=600.0)
        if poly is not None and len(poly) > 2:
            return _finalise(_resample_polyline(poly))
        # no street graph available -> fall through to the curved pattern
        pattern = RoutePattern.CURVED

    if pattern == RoutePattern.CUSTOM and custom_points_m:
        pts = np.asarray(custom_points_m, dtype=float)
        return _finalise(pts)

    if pattern == RoutePattern.STRAIGHT:
        return _finalise(_polyline_with_heading((0.0, 0.0), h0, total))

    if pattern in (RoutePattern.LEFT_TURN, RoutePattern.RIGHT_TURN):
        # right turn = heading increases (clockwise), left turn = decreases
        sign = -1.0 if pattern == RoutePattern.LEFT_TURN else 1.0
        radius = 55.0
        turn = sign * math.pi / 2.0
        s1 = max(30.0, (total - radius * abs(turn)) * 0.35)
        s3 = max(20.0, total - radius * abs(turn) - s1)
        first = _polyline_with_heading((0.0, 0.0), h0, s1)
        arc = _arc_points((first[-1, 0], first[-1, 1]), h0, turn, radius)
        h_end = h0 + turn
        last = _polyline_with_heading((arc[-1, 0], arc[-1, 1]), h_end, s3)
        return _finalise(np.vstack([first, arc, last]))

    if pattern == RoutePattern.CURVED:
        # heading oscillates sinusoidally around the initial heading
        step = 0.5
        s = np.arange(0.0, total, step)
        wavelength = 520.0
        amp = 32.0 * DEG2RAD
        heading = h0 + amp * np.sin(2.0 * math.pi * s / wavelength)
        de = np.sin(heading) * step
        dn = np.cos(heading) * step
        pts = np.column_stack([np.cumsum(de), np.cumsum(dn)])
        return _finalise(np.vstack([[0.0, 0.0], pts]))

    # RANDOM: sequence of straight runs and random-radius arcs
    pts_list = [np.array([[0.0, 0.0]])]
    heading = h0
    travelled = 0.0
    while travelled < total:
        straight = float(rng.uniform(40.0, 140.0))
        seg = _polyline_with_heading(tuple(pts_list[-1][-1]), heading, straight)
        pts_list.append(seg)
        travelled += straight
        turn = float(rng.uniform(35.0, 100.0) * DEG2RAD) * (1.0 if rng.random() < 0.5 else -1.0)
        radius = float(rng.uniform(25.0, 70.0))
        arc = _arc_points(
            (float(pts_list[-1][-1, 0]), float(pts_list[-1][-1, 1])), heading, turn, radius
        )
        pts_list.append(arc)
        travelled += abs(turn) * radius
        heading = wrap_angle(heading + turn)
    return _finalise(np.vstack(pts_list))


# ------------------------------------------------------------- sensor frame ---
@dataclass
class SimStep:
    """One synchronised simulation step (ground truth + raw sensors)."""

    t: float
    timestamp: float
    step: int

    # ground truth (local EN + geodetic)
    truth_e: float
    truth_n: float
    truth_lat: float
    truth_lon: float
    truth_speed: float
    truth_heading: float          # rad
    truth_accel: float            # m/s^2 along body x
    truth_yaw_rate: float         # rad/s

    # sensors
    imu_accel: float              # m/s^2 (biased + noisy)
    imu_yaw_rate: float           # rad/s (biased + noisy)
    odom_speed: float             # m/s

    # GNSS
    gnss_available: bool
    gnss_e: Optional[float] = None
    gnss_n: Optional[float] = None
    gnss_lat: Optional[float] = None
    gnss_lon: Optional[float] = None
    gnss_bias_e: float = 0.0
    gnss_bias_n: float = 0.0

    # injected fault metadata (what the simulator actually did)
    injected_fault: str = "none"          # none | outage | drift | spoofing
    injected_fault_active: bool = False


def _road_ways(plane: LocalTangentPlane, config: "SimulatorConfig") -> List[List[Tuple[float, float]]]:
    """Street polylines in the local frame (OpenStreetMap when reachable)."""
    ways: List[List[Tuple[float, float]]] = []
    if config.use_real_map_data:
        try:
            from app.services.map_data_service import road_network

            data = road_network(config.origin_lat, config.origin_lon, config.map_radius_m)
            for road in data.get("roads", []):
                pts = [plane.to_local(lat, lon) for lat, lon in road.get("points", [])]
                pts = [(float(e), float(n)) for e, n in pts
                       if abs(e) <= config.map_radius_m and abs(n) <= config.map_radius_m]
                if len(pts) >= 2:
                    ways.append(pts)
        except Exception:                                  # pragma: no cover
            ways = []
    if len(ways) < 8:
        # deterministic synthetic street lattice around the origin (offline mode):
        # one way per block edge so every intersection is a graph node.
        spacing = 120.0
        extent = 600.0
        n = int(extent / spacing)
        ways = []
        for i in range(-n, n):
            for j in range(-n, n + 1):
                y = i * spacing
                ways.append([(j * spacing, y), ((j + 1) * spacing, y)])
                x = j * spacing
                ways.append([(x, i * spacing), (x, (i + 1) * spacing)])
    return ways


class VehicleSimulator:
    """Configurable ground-truth vehicle + sensor simulator."""

    def __init__(self, config: SimulatorConfig, seed: Optional[int] = None) -> None:
        self.config = config
        self.dt = 1.0 / float(config.rate_hz)
        self.plane = LocalTangentPlane(config.origin_lat, config.origin_lon)

        seed_seq = np.random.SeedSequence(
            None if seed is None else [int(seed), int(config.route_seed or 0)]
        )
        self.rng = np.random.default_rng(seed_seq)

        custom_m = None
        if config.route_pattern == RoutePattern.CUSTOM and config.custom_waypoints:
            custom_m = [
                self.plane.to_local(w.lat, w.lon) for w in config.custom_waypoints
            ]

        # Street vertices for the road-following pattern. Real OpenStreetMap
        # geometry is used when it can be fetched; otherwise the synthetic grid
        # provides an equivalent offline street graph.
        road_vertices_m = None
        if config.route_pattern == RoutePattern.ROAD:
            road_vertices_m = _road_ways(self.plane, config)

        self.route = build_route(
            pattern=config.route_pattern,
            speed_ms=config.speed_ms,
            duration_s=config.duration_s,
            initial_heading_rad=config.initial_heading_deg * DEG2RAD,
            rng=self.rng,
            custom_points_m=custom_m,
            road_vertices_m=road_vertices_m,
        )

        # vehicle state
        self.s: float = 0.0
        self.v: float = 0.0
        # The vehicle is placed already pointing along the route tangent. (The
        # requested initial heading only shapes the route geometry; starting
        # misaligned would inject a fictitious yaw-rate spike at t=0.)
        self.heading: float = float(self.route.headings[0])
        self.t: float = 0.0
        self.step_index: int = 0
        self._prev_heading: float = self.heading
        self._prev_v: float = 0.0

        # fault directions: seeded so runs are reproducible
        ang = float(self.rng.uniform(0, 2 * math.pi))
        self._spoof_dir = (math.cos(ang), math.sin(ang))
        ang2 = float(self.rng.uniform(0, 2 * math.pi))
        self._drift_dir = (math.cos(ang2), math.sin(ang2))

        noise = config.noise
        self.sig_gnss = noise.gnss_position_sigma_m
        self.sig_speed = noise.speed_sigma_ms
        self.sig_heading_rad = noise.heading_sigma_deg * DEG2RAD
        self.sig_accel = noise.accel_sigma_ms2
        self.sig_gyro = noise.gyro_sigma_dps * DEG2RAD

        self.accel_bias = config.accel_bias_ms2
        self.gyro_bias = config.gyro_bias_dps * DEG2RAD

        self.completed = False

    # -- helpers ------------------------------------------------------------
    @property
    def scenario(self) -> ScenarioType:
        return self.config.scenario.scenario

    def _target_speed(self, curvature: float) -> float:
        cfg = self.config
        # slow down for curves, plus a gentle cruise variation for realism
        curve_factor = 1.0 / (1.0 + 2.2 * abs(curvature) * cfg.speed_ms)
        cruise = 1.0 + 0.06 * math.sin(0.11 * self.t)
        return max(0.0, cfg.speed_ms * curve_factor * cruise)

    def _outage_window(self) -> Tuple[float, float]:
        sc = self.config.scenario
        start = sc.outage_start_s
        return start, start + sc.outage_duration_s

    def _fault_state(self) -> Tuple[str, bool]:
        sc = self.config.scenario
        if sc.scenario == ScenarioType.OUTAGE:
            a, b = self._outage_window()
            return "outage", (a <= self.t < b)
        if sc.scenario == ScenarioType.DRIFT and self.t >= sc.drift_onset_s:
            return "drift", True
        if sc.scenario == ScenarioType.SPOOFING and self.t >= sc.spoof_onset_s:
            return "spoofing", True
        return "none", False

    def _gnss_bias(self) -> Tuple[float, float]:
        sc = self.config.scenario
        if sc.scenario == ScenarioType.DRIFT:
            dt_after = max(0.0, self.t - sc.drift_onset_s)
            # a drifting solution accumulates a slowly growing offset in a
            # roughly fixed direction (multipath / aiding-failure signature),
            # with a small wander so it is not perfectly axis-aligned
            mag = min(sc.drift_max_m, sc.drift_rate_ms * dt_after)
            ang = 0.04 * dt_after
            base = math.atan2(self._drift_dir[1], self._drift_dir[0]) + ang
            return mag * math.cos(base), mag * math.sin(base)
        if sc.scenario == ScenarioType.SPOOFING:
            dt_after = max(0.0, self.t - sc.spoof_onset_s)
            base = sc.spoof_jump_m * (1.0 if dt_after > 0 else 0.0) + sc.spoof_drift_ms * dt_after
            return base * self._spoof_dir[0], base * self._spoof_dir[1]
        return 0.0, 0.0

    # -- main step ----------------------------------------------------------
    def step(self) -> SimStep:
        cfg = self.config
        dt = self.dt

        # --- longitudinal dynamics along the route ---
        e0, n0, _, k0 = self.route.sample(self.s)
        v_target = self._target_speed(k0)
        accel_limit = 2.2
        dv = v_target - self.v
        accel_cmd = float(np.clip(dv / max(dt, 1e-6) * 0.35, -accel_limit, accel_limit))
        self.v = max(0.0, self.v + accel_cmd * dt)

        s_next = self.s + self.v * dt
        if s_next >= self.route.length:
            s_next = self.route.length
            self.v = 0.0
            self.completed = True

        e1, n1, h1, _ = self.route.sample(s_next)
        dh = wrap_angle(h1 - self.heading)

        true_accel = (self.v - self._prev_v) / dt if dt > 0 else 0.0
        true_yaw_rate = dh / dt if dt > 0 else 0.0

        self.s = s_next
        self.heading = wrap_angle(h1)
        self.t += dt
        self.step_index += 1

        lat, lon = self.plane.to_geodetic(e1, n1)

        # --- sensors ---
        imu_accel = true_accel + self.accel_bias + self.rng.normal(0.0, self.sig_accel)
        imu_yaw = true_yaw_rate + self.gyro_bias + self.rng.normal(0.0, self.sig_gyro)
        odom = max(0.0, self.v + self.rng.normal(0.0, self.sig_speed))

        # --- GNSS ---
        fault, fault_active = self._fault_state()
        gnss_available = True
        be, bn = self._gnss_bias()
        if fault == "outage" and fault_active:
            gnss_available = False

        ge = gn = glat = glon = None
        if gnss_available:
            ne = float(self.rng.normal(0.0, self.sig_gnss))
            nn = float(self.rng.normal(0.0, self.sig_gnss))
            ge = e1 + be + ne
            gn = n1 + bn + nn
            glat, glon = self.plane.to_geodetic(ge, gn)

        self._prev_v = self.v
        self._prev_heading = self.heading

        return SimStep(
            t=float(self.t - dt),
            timestamp=float(self.t),
            step=int(self.step_index),
            truth_e=float(e1),
            truth_n=float(n1),
            truth_lat=float(lat),
            truth_lon=float(lon),
            truth_speed=float(self.v),
            truth_heading=float(self.heading),
            truth_accel=float(true_accel),
            truth_yaw_rate=float(true_yaw_rate),
            imu_accel=float(imu_accel),
            imu_yaw_rate=float(imu_yaw),
            odom_speed=float(odom),
            gnss_available=bool(gnss_available),
            gnss_e=ge,
            gnss_n=gn,
            gnss_lat=glat,
            gnss_lon=glon,
            gnss_bias_e=float(be),
            gnss_bias_n=float(bn),
            injected_fault=fault,
            injected_fault_active=bool(fault_active),
        )

    # -- convenience --------------------------------------------------------
    def run_all(self) -> List[SimStep]:
        """Run the whole simulation offline (used by tests / ML dataset build)."""
        steps: List[SimStep] = []
        n_steps = int(round(self.config.duration_s * self.config.rate_hz))
        for _ in range(n_steps):
            steps.append(self.step())
        return steps

    def route_geodetic(self, max_points: int = 400) -> List[dict]:
        """Route polyline as lat/lon (for map display of the planned path)."""
        n = len(self.route.points)
        idx = np.unique(np.linspace(0, n - 1, min(max_points, n)).astype(int))
        out = []
        for i in idx:
            lat, lon = self.plane.to_geodetic(*self.route.points[i])
            out.append({"lat": float(lat), "lon": float(lon)})
        return out

    def outage_window(self) -> Optional[Tuple[float, float]]:
        if self.scenario != ScenarioType.OUTAGE:
            return None
        a, b = self._outage_window()
        return (a, min(b, self.config.duration_s))
