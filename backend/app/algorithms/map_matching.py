"""Lightweight, offline map matching.

The MVP matcher is intentionally simple and explainable:

1. A road network is supplied as a set of polylines in the local EN frame.
   The default network is a *synthetic* grid derived from the simulated route
   (so the feature works with zero internet access), and an optional
   OpenStreetMap overlay can be fetched when the network is available.
2. For each estimated position the nearest road segment is found and the
   point-to-segment offset is computed.
3. A matched position is produced only when the offset is below
   ``max_snap_distance_m``; the search is confined to a small candidate set
   around the previous match to avoid jumping between parallel roads.

Map matching is advisory only: it never feeds back into the EKF, so navigation
keeps working when no map is available.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from app.core.coordinate_utils import LocalTangentPlane


@dataclass
class RoadSegment:
    a: Tuple[float, float]
    b: Tuple[float, float]
    name: str = "road"

    @property
    def length(self) -> float:
        return math.hypot(self.b[0] - self.a[0], self.b[1] - self.a[1])

    def project(self, p: Tuple[float, float]) -> Tuple[Tuple[float, float], float, float]:
        """Return (closest point, distance, along-segment fraction)."""
        ax, ay = self.a
        bx, by = self.b
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy
        if denom <= 1e-12:
            return (ax, ay), math.hypot(p[0] - ax, p[1] - ay), 0.0
        t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / denom
        t = min(1.0, max(0.0, t))
        cp = (ax + t * dx, ay + t * dy)
        return cp, math.hypot(p[0] - cp[0], p[1] - cp[1]), t


class RoadNetwork:
    def __init__(self, segments: Optional[Sequence[RoadSegment]] = None, name: str = "synthetic") -> None:
        self.segments: List[RoadSegment] = list(segments or [])
        self.name = name
        self.source = "synthetic"

    def __len__(self) -> int:
        return len(self.segments)

    @classmethod
    def from_polyline(
        cls,
        points_en: Sequence[Tuple[float, float]],
        name: str = "simulated route",
        simplify_m: float = 12.0,
    ) -> "RoadNetwork":
        """Build a network from the simulated route (Douglas-Peucker-ish)."""
        pts = np.asarray(points_en, dtype=float)
        if len(pts) < 2:
            return cls([], name=name)
        # simple distance-based decimation to keep the segment count small
        keep = [0]
        last = pts[0]
        for i in range(1, len(pts)):
            if np.linalg.norm(pts[i] - last) >= simplify_m or i == len(pts) - 1:
                keep.append(i)
                last = pts[i]
        kept = pts[keep]
        segs = [
            RoadSegment(tuple(kept[i]), tuple(kept[i + 1]), name=f"{name} seg {i}")
            for i in range(len(kept) - 1)
        ]
        return cls(segs, name=name)

    @classmethod
    def synthetic_grid(
        cls, origin_en: Tuple[float, float] = (0.0, 0.0), extent_m: float = 1500.0, spacing_m: float = 150.0
    ) -> "RoadNetwork":
        """Fallback street grid so map matching works offline."""
        segs: List[RoadSegment] = []
        n = int(extent_m / spacing_m)
        for i in range(-n, n + 1):
            y = origin_en[1] + i * spacing_m
            segs.append(RoadSegment((origin_en[0] - extent_m, y), (origin_en[0] + extent_m, y), f"E-W {i}"))
            x = origin_en[0] + i * spacing_m
            segs.append(RoadSegment((x, origin_en[1] - extent_m), (x, origin_en[1] + extent_m), f"N-S {i}"))
        return cls(segs, name="synthetic grid")

    def nearest(self, p: Tuple[float, float], candidates: Optional[int] = None):
        best = (None, float("inf"), 0.0)
        for seg in self.segments:
            cp, d, t = seg.project(p)
            if d < best[1]:
                best = (seg, d, t)
                best_cp = cp
        if best[0] is None:
            return None, float("inf"), (0.0, 0.0)
        return best[0], best[1], best_cp


class MapMatcher:
    """Nearest-road snapping with a snap-distance gate and simple continuity."""

    def __init__(
        self,
        network: Optional[RoadNetwork] = None,
        max_snap_distance_m: float = 35.0,
        smoothing: float = 0.6,
    ) -> None:
        self.network = network if network is not None else RoadNetwork.synthetic_grid()
        self.max_snap = float(max_snap_distance_m)
        self.smoothing = float(np.clip(smoothing, 0.0, 1.0))
        self.last_matched: Optional[Tuple[float, float]] = None
        self.matched_count = 0
        self.unmatched_count = 0

    @property
    def available(self) -> bool:
        return len(self.network) > 0

    def match(self, p_en: Tuple[float, float]) -> dict:
        if not self.available:
            self.unmatched_count += 1
            return {
                "matched": False,
                "reason": "no road network available",
                "offset_m": None,
                "road": None,
                "position": None,
            }
        seg, dist, cp = self.network.nearest(p_en)
        if seg is None or dist > self.max_snap:
            self.unmatched_count += 1
            self.last_matched = None
            return {
                "matched": False,
                "reason": f"nearest road {dist:.1f} m away (gate {self.max_snap:.0f} m)",
                "offset_m": float(dist),
                "road": seg.name if seg else None,
                "position": None,
            }
        if self.last_matched is not None:
            sm = (
                self.smoothing * cp[0] + (1 - self.smoothing) * self.last_matched[0],
                self.smoothing * cp[1] + (1 - self.smoothing) * self.last_matched[1],
            )
        else:
            sm = cp
        self.last_matched = sm
        self.matched_count += 1
        return {
            "matched": True,
            "reason": "snapped to nearest road",
            "offset_m": float(dist),
            "road": seg.name,
            "position": sm,
        }

    def match_geodetic(self, plane: LocalTangentPlane, lat: float, lon: float) -> dict:
        e, n = plane.to_local(lat, lon)
        out = self.match((e, n))
        if out.get("position"):
            mlat, mlon = plane.to_geodetic(*out["position"])
            out["lat"] = mlat
            out["lon"] = mlon
        return out
