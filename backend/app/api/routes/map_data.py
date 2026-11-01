"""Map data endpoints: real road geometry + cached basemap tiles.

Both are additive: when unreachable the dashboard falls back to the offline
grid and the navigation engine falls back to the synthetic road network.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from app.services import map_data_service as mds

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/roads")
def roads(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: float = Query(1500.0, ge=200, le=8000),
) -> dict:
    """Real drivable road geometry (OpenStreetMap via Overpass), cached on disk."""
    return mds.road_network(lat, lon, radius_m)


@router.get("/tile/{z}/{x}/{y}.png")
def tile(z: int, x: int, y: int) -> Response:
    """Cached slippy-map tile. 204 means 'not available' (UI uses its grid)."""
    if z < 0 or z > 19 or x < 0 or y < 0 or x >= 2 ** z or y >= 2 ** z:
        raise HTTPException(status_code=422, detail="tile index out of range")
    blob, source = mds.tile(z, x, y)
    if blob is None:
        return Response(status_code=204, headers={"X-Tile-Source": source})
    return Response(
        content=blob,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400", "X-Tile-Source": source},
    )


@router.post("/prefetch")
def prefetch(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict:
    """Warm the tile cache around a point so the map works offline later."""
    return mds.prefetch_tiles(lat, lon)


@router.get("/status")
def status() -> dict:
    """Availability + cache state of online map data."""
    return {
        "online_enabled": mds.map_online_enabled(),
        "cached_tiles": mds.cached_tile_count(),
        "tile_dir": str(mds.TILE_DIR),
        "attribution": "© OpenStreetMap contributors",
        "tile_sources": list(mds.TILE_URLS),
    }
