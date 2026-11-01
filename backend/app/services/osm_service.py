"""Optional OpenStreetMap road lookup via the Overpass API.

Map matching is **never** a dependency of the navigation engine. If the network
is unavailable, times out, or returns nothing, callers fall back to the
synthetic road network derived from the simulated route. Results are cached in
process so repeated simulations do not hammer the public endpoint.

Enable with ``GRIDS_ENABLE_OSM=1`` (off by default: zero internet required).
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.core.coordinate_utils import LocalTangentPlane
from app.utils.logging import get_logger

log = get_logger("grids.osm")

OVERPASS_URL = os.getenv("GRIDS_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
CACHE_TTL_S = float(os.getenv("GRIDS_OSM_CACHE_TTL", "900"))
MAX_ROADS = 400


@dataclass
class OsmRoad:
    name: str
    points: List[Tuple[float, float]]  # lat, lon
    highway: str


_cache: Dict[str, Tuple[float, dict]] = {}


def osm_enabled() -> bool:
    return os.getenv("GRIDS_ENABLE_OSM", "0") == "1"


def _cache_key(lat: float, lon: float, radius: float) -> str:
    return f"{round(lat, 4)}:{round(lon, 4)}:{int(radius)}"


def fetch_roads(lat: float, lon: float, radius_m: float = 1200.0, timeout: float = 6.0) -> dict:
    """Fetch nearby drivable ways. Returns a status dict, never raises."""
    if not osm_enabled():
        return {
            "available": False,
            "reason": "OpenStreetMap lookup disabled (set GRIDS_ENABLE_OSM=1)",
            "roads": [],
            "source": "disabled",
        }

    key = _cache_key(lat, lon, radius_m)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_S:
        return cached[1]

    query = f"""
    [out:json][timeout:{int(timeout)}];
    way(around:{int(radius_m)},{lat},{lon})["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified|service)$"];
    out geom {MAX_ROADS};
    """
    params = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        OVERPASS_URL, data=params, headers={"User-Agent": "GRIDS-navigation-simulator/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # offline, rate-limited, DNS failure, ...
        result = {
            "available": False,
            "reason": f"OpenStreetMap unavailable: {exc.__class__.__name__}",
            "roads": [],
            "source": "overpass",
        }
        _cache[key] = (time.time(), result)
        log.info("OSM lookup failed (%s) - falling back to synthetic network", exc.__class__.__name__)
        return result

    roads: List[dict] = []
    for element in payload.get("elements", []):
        geom = element.get("geometry") or []
        if len(geom) < 2:
            continue
        tags = element.get("tags", {})
        roads.append(
            {
                "name": tags.get("name") or tags.get("ref") or f"way/{element.get('id')}",
                "highway": tags.get("highway", "road"),
                "points": [[float(p["lat"]), float(p["lon"])] for p in geom],
            }
        )

    result = {
        "available": bool(roads),
        "reason": "ok" if roads else "no roads returned for this area",
        "roads": roads[:MAX_ROADS],
        "source": "overpass",
    }
    _cache[key] = (time.time(), result)
    log.info("OSM lookup returned %d ways", len(roads))
    return result


def to_road_network(lat: float, lon: float, radius_m: float = 1200.0):
    """Convert the OSM response into the local-EN ``RoadNetwork`` type."""
    from app.algorithms.map_matching import RoadNetwork, RoadSegment

    data = fetch_roads(lat, lon, radius_m)
    if not data["available"]:
        return None, data

    plane = LocalTangentPlane(lat, lon)
    segments: List[RoadSegment] = []
    for road in data["roads"]:
        pts = [plane.to_local(p[0], p[1]) for p in road["points"]]
        for a, b in zip(pts, pts[1:]):
            # skip near-zero and absurdly long segments (bad data)
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            if 1.0 < d < 400.0:
                segments.append(RoadSegment(a, b, road["name"]))
    if not segments:
        return None, {**data, "available": False, "reason": "no usable road segments"}
    net = RoadNetwork(segments, name="OpenStreetMap")
    net.source = "osm"
    return net, data
