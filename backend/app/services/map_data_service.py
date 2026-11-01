"""Map data for the dashboard: real road geometry and a cached basemap.

Two independent pieces, both optional and both cached on disk so a demo never
needs the network twice:

1. **Road network (Overpass / OSM).** ``road_network`` returns real drivable
   ways around the run origin in local East-North coordinates. When it is
   unreachable, the caller keeps using the synthetic network derived from the
   simulated route, so map matching and map aiding never break.

2. **Basemap tiles.** ``tile`` proxies OpenStreetMap raster tiles and stores them
   under ``backend/data/tiles``. Once a tile has been fetched it is served from
   disk forever, which means the dashboard can show a real map background with
   no internet during a demo. If a tile has never been cached and the network is
   down, the endpoint answers 204 and the UI silently keeps its offline grid.

Everything here is read-only and failure tolerant: navigation never depends on
it.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.config import BASE_DIR
from app.core.coordinate_utils import LocalTangentPlane
from app.utils.logging import get_logger

log = get_logger("grids.mapdata")

TILE_DIR = BASE_DIR / "data" / "tiles"
ROAD_CACHE = BASE_DIR / "data" / "roads"
# Primary + fallback raster styles. Every tile is copied into the disk cache, so
# the background map keeps rendering with no network once it has been seen once.
TILE_URLS = tuple(
    t.strip() for t in os.getenv(
        "GRIDS_TILE_URLS",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png,"
        "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png,"
        "https://tile.opentopomap.org/{z}/{x}/{y}.png",
    ).split(",") if t.strip()
)
# Placeholder/watermark tiles some providers return without an API key. They are
# small, palette based and would poison the cache, so they are rejected.
MIN_TILE_BYTES = 1500
TIMEOUT_S = float(os.getenv("GRIDS_MAP_TIMEOUT", "2.5"))
# Public Overpass instances are frequently rate limited; try several before
# giving up on real road geometry (the synthetic network covers the gap).
OVERPASS_MIRRORS = tuple(
    m.strip() for m in os.getenv(
        "GRIDS_OVERPASS_MIRRORS",
        "https://overpass.kumi.systems/api/interpreter,"
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.private.coffee/api/interpreter",
    ).split(",") if m.strip()
)
MAX_TILE_BYTES = 500_000
# The OSM "map data" endpoint is the primary road source: it needs no query
# language, answers in ~1 s and is far more reliable than public Overpass
# instances. Overpass stays as the secondary path.
OSM_API_URL = os.getenv("GRIDS_OSM_API", "https://api.openstreetmap.org/api/0.6/map")
OSM_API_TIMEOUT_S = float(os.getenv("GRIDS_OSM_TIMEOUT", "12"))
DRIVABLE_HIGHWAYS = frozenset(
    """motorway motorway_link trunk trunk_link primary primary_link secondary
    secondary_link tertiary tertiary_link unclassified residential living_street
    service road""".split()
)
_cache: Dict[str, Tuple[float, dict]] = {}
_failed_until: float = 0.0          # global back-off after a failed lookup
FAIL_BACKOFF_S = float(os.getenv("GRIDS_MAP_BACKOFF", "600"))


def map_online_enabled() -> bool:
    """Real map data is on unless explicitly disabled."""
    return os.getenv("GRIDS_MAP_ONLINE", "1") == "1"


# --------------------------------------------------------------------- roads ---
def _road_cache_path(lat: float, lon: float, radius: float) -> Path:
    key = f"{lat:.3f}_{lon:.3f}_{int(radius)}"
    ROS = hashlib.sha1(key.encode()).hexdigest()[:16]
    return ROAD_CACHE / f"roads_{ROS}.json"


def road_network(lat: float, lon: float, radius_m: float = 1500.0) -> dict:
    """Real road geometry around a point, cached to disk.

    Returns ``{"available": bool, "source": str, "roads": [...], "reason": str}``
    where each road is ``{"name": str, "highway": str, "points": [[lat, lon], ...]}``.
    """
    global _failed_until
    if not map_online_enabled():
        return {"available": False, "source": "disabled", "roads": [],
                "reason": "online map data disabled (GRIDS_MAP_ONLINE=0)"}
    if time.time() < _failed_until:
        return {"available": False, "source": "backoff", "roads": [],
                "reason": "OpenStreetMap recently unreachable - backing off"}

    ROAD_CACHE.mkdir(parents=True, exist_ok=True)
    path = _road_cache_path(lat, lon, radius_m)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < 60 * 60 * 12:                     # 12 h disk cache
            try:
                data = json.loads(path.read_text())
                data["cached"] = True
                return data
            except Exception:                       # pragma: no cover
                path.unlink(missing_ok=True)

    key = f"roads:{lat:.3f}:{lon:.3f}:{int(radius_m)}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]

    api_roads = _roads_from_osm_api(lat, lon, radius_m)
    if api_roads:
        result = {
            "available": True,
            "source": "osm-api",
            "reason": "ok",
            "roads": api_roads[:3000],
            "fetched_at": int(time.time()),
        }
        try:
            path.write_text(json.dumps(result, separators=(",", ":")))
        except Exception:  # pragma: no cover
            pass
        _cache[key] = (time.time(), result)
        log.info("OSM map-data: %d drivable ways around %.4f,%.4f",
                 len(api_roads), lat, lon)
        return result

    query = (
        f"[out:json][timeout:{int(TIMEOUT_S)}];"
        f'way(around:{int(radius_m)},{lat},{lon})["highway"];'
        "out geom 600;"
    )
    encoded = urllib.parse.urlencode({"data": query}).encode()
    payload = None
    last_err = "unreachable"
    for endpoint in OVERPASS_MIRRORS:
        req = urllib.request.Request(
            endpoint, data=encoded,
            headers={"User-Agent": "GRIDS-navigation-platform/1.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S + 4) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:                   # mirror down / rate limited
            last_err = exc.__class__.__name__
            continue
    if payload is None:
        _failed_until = time.time() + FAIL_BACKOFF_S
        log.info("OSM road query failed on all mirrors (%s); backing off %.0f s",
                 last_err, FAIL_BACKOFF_S)
        result = {"available": False, "source": "overpass", "roads": [],
                  "reason": f"OpenStreetMap unreachable ({last_err})"}
        _cache[key] = (time.time(), result)
        return result

    roads: List[dict] = []
    for el in payload.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        tags = el.get("tags", {})
        roads.append(
            {
                "name": tags.get("name") or tags.get("ref") or f"way/{el.get('id')}",
                "highway": tags.get("highway", "road"),
                "points": [[round(float(p["lat"]), 6), round(float(p["lon"]), 6)] for p in geom],
            }
        )

    result = {
        "available": bool(roads),
        "source": "overpass",
        "reason": "ok" if roads else "no roads in this area",
        "roads": roads[:600],
        "fetched_at": int(time.time()),
    }
    if roads:
        try:
            path.write_text(json.dumps(result, separators=(",", ":")))
        except Exception:  # pragma: no cover
            pass
    _cache[key] = (time.time(), result)
    log.info("OSM road data: %d ways around %.4f,%.4f", len(roads), lat, lon)
    return result


def _roads_from_osm_api(lat: float, lon: float, radius_m: float) -> Optional[List[dict]]:
    """Fetch drivable ways with the plain OSM XML map endpoint (bbox query)."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    bbox = f"{lon - dlon:.6f},{lat - dlat:.6f},{lon + dlon:.6f},{lat + dlat:.6f}"
    url = f"{OSM_API_URL}?bbox={bbox}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "GRIDS-navigation-platform/1.1 (demo)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=OSM_API_TIMEOUT_S) as resp:
            raw = resp.read(12_000_000)
    except Exception as exc:
        log.info("OSM map-data request failed: %s", exc.__class__.__name__)
        return None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    nodes: Dict[str, Tuple[float, float]] = {}
    for el in root.findall("node"):
        try:
            nodes[el.get("id", "")] = (float(el.get("lat")), float(el.get("lon")))
        except (TypeError, ValueError):
            continue

    roads: List[dict] = []
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        highway = tags.get("highway", "")
        if highway not in DRIVABLE_HIGHWAYS:
            continue
        pts = [nodes[ref.get("ref", "")] for ref in way.findall("nd")
               if ref.get("ref", "") in nodes]
        if len(pts) < 2:
            continue
        roads.append(
            {
                "name": tags.get("name") or tags.get("ref") or f"way/{way.get('id')}",
                "highway": highway,
                "points": [[round(a, 6), round(b, 6)] for a, b in pts],
            }
        )
    return roads


def build_road_network(lat: float, lon: float, radius_m: float = 1500.0):
    """Return a ``RoadNetwork`` in local EN coordinates, or ``(None, info)``."""
    from app.algorithms.map_matching import RoadNetwork, RoadSegment

    data = road_network(lat, lon, radius_m)
    if not data["available"]:
        return None, data
    plane = LocalTangentPlane(lat, lon)
    segments: List[RoadSegment] = []
    for road in data["roads"]:
        pts = [plane.to_local(p[0], p[1]) for p in road["points"]]
        for a, b in zip(pts, pts[1:]):
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            if 0.5 < d < 500.0:
                segments.append(RoadSegment(a, b, road["name"]))
    if not segments:
        return None, {**data, "available": False, "reason": "no usable segments"}
    net = RoadNetwork(segments, name="OpenStreetMap")
    net.source = "osm"
    return net, {**data, "segments": len(segments)}


# --------------------------------------------------------------------- tiles ---
def _tile_path(z: int, x: int, y: int) -> Path:
    return TILE_DIR / str(z) / str(x) / f"{y}.png"


def tile(z: int, x: int, y: int) -> Tuple[Optional[bytes], str]:
    """Return (png bytes, source) for a slippy-map tile; ``None`` when unknown.

    Cached tiles win, so the map keeps working offline after a first run.
    """
    path = _tile_path(z, x, y)
    if path.exists():
        try:
            blob = path.read_bytes()
            if len(blob) >= MIN_TILE_BYTES:
                return blob, "cache"
            path.unlink(missing_ok=True)        # drop a previously poisoned tile
        except Exception:  # pragma: no cover
            pass
    if not map_online_enabled():
        return None, "disabled"

    for template in TILE_URLS:
        url = template.format(z=z, x=x, y=y)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "GRIDS-navigation-platform/1.1"}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                blob = resp.read(MAX_TILE_BYTES)
            if not blob or not blob.startswith(b"\x89PNG"):
                continue
            if len(blob) < MIN_TILE_BYTES:      # provider watermark placeholder
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            return blob, "network"
        except Exception:
            continue
    return None, "unavailable"


def cached_tile_count() -> int:
    if not TILE_DIR.exists():
        return 0
    return sum(1 for _ in TILE_DIR.rglob("*.png"))


def prefetch_tiles(
    lat: float, lon: float, zoom_levels=(14, 15, 16, 17, 18), span: int = 2
) -> dict:
    """Warm the tile cache around a point so the map works offline afterwards.

    The span is chosen so the default dashboard view (z16-17) is fully covered;
    the request count stays bounded (<= (2*span+1)^2 per zoom level).
    """
    if not map_online_enabled():
        return {"ok": False, "reason": "online map data disabled", "fetched": 0,
                "attempted": 0, "cached_total": cached_tile_count()}
    fetched = 0
    attempted = 0
    for z in zoom_levels:
        n = 2 ** z
        xt = int((lon + 180.0) / 360.0 * n)
        yt = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                attempted += 1
                blob, src = tile(z, (xt + dx) % n, max(0, min(n - 1, yt + dy)))
                if blob and src == "network":
                    fetched += 1
    return {"ok": True, "attempted": attempted, "fetched": fetched,
            "cached_total": cached_tile_count()}
