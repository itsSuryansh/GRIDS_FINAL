"""Coordinate transformations.

The navigation stack never treats latitude/longitude as Cartesian coordinates.
Internally we work in a local East-North (EN) tangent plane anchored at a
reference geodetic point (the trajectory origin). Because a vehicle simulation
covers a few kilometres at most, the local tangent-plane (equirectangular,
WGS-84 scaled) approximation is accurate to the centimetre level over that
extent, and it keeps the EKF linear-algebra simple and numerically stable.

Functions
---------
geodetic_to_local(lat, lon)  -> (east, north)  metres
local_to_geodetic(e, n)      -> (lat, lon)     degrees
haversine_m(...)             -> great-circle distance
bearing_deg(...)             -> initial bearing between two geodetic points
wrap_angle(rad)              -> angle in (-pi, pi]
"""
from __future__ import annotations

import math
from dataclasses import dataclass

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi


def wrap_angle(angle: float) -> float:
    """Wrap an angle (radians) into (-pi, pi]."""
    w = (angle + math.pi) % (2.0 * math.pi) - math.pi
    return math.pi if w <= -math.pi else w


def wrap_angle_array(angles):
    """Vectorised wrap for NumPy arrays."""
    import numpy as np

    return (np.asarray(angles) + np.pi) % (2.0 * np.pi) - np.pi


def meridian_radius(lat_rad: float) -> float:
    """Radius of curvature in the meridian (M) at a given latitude."""
    s = math.sin(lat_rad)
    return (WGS84_A * (1.0 - WGS84_E2)) / ((1.0 - WGS84_E2 * s * s) ** 1.5)


def prime_vertical_radius(lat_rad: float) -> float:
    """Radius of curvature in the prime vertical (N) at a given latitude."""
    s = math.sin(lat_rad)
    return WGS84_A / math.sqrt(1.0 - WGS84_E2 * s * s)


def meters_per_degree(lat_deg: float) -> tuple[float, float]:
    """Metres per degree of latitude and of longitude at a latitude."""
    lat_rad = lat_deg * DEG2RAD
    m_per_deg_lat = meridian_radius(lat_rad) * DEG2RAD
    m_per_deg_lon = prime_vertical_radius(lat_rad) * math.cos(lat_rad) * DEG2RAD
    return m_per_deg_lat, m_per_deg_lon


@dataclass(frozen=True)
class LocalTangentPlane:
    """Local East-North frame anchored at a geodetic reference point."""

    ref_lat: float
    ref_lon: float

    @property
    def meters_per_deg(self) -> tuple[float, float]:
        return meters_per_degree(self.ref_lat)

    def to_local(self, lat: float, lon: float) -> tuple[float, float]:
        m_lat, m_lon = self.meters_per_deg
        east = (lon - self.ref_lon) * m_lon
        north = (lat - self.ref_lat) * m_lat
        return east, north

    def to_geodetic(self, east: float, north: float) -> tuple[float, float]:
        m_lat, m_lon = self.meters_per_deg
        lat = self.ref_lat + north / m_lat
        lon = self.ref_lon + east / m_lon
        return lat, lon


def geodetic_to_local(
    lat: float, lon: float, ref_lat: float, ref_lon: float
) -> tuple[float, float]:
    return LocalTangentPlane(ref_lat, ref_lon).to_local(lat, lon)


def local_to_geodetic(
    east: float, north: float, ref_lat: float, ref_lon: float
) -> tuple[float, float]:
    return LocalTangentPlane(ref_lat, ref_lon).to_geodetic(east, north)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = lat1 * DEG2RAD, lat2 * DEG2RAD
    dp = p2 - p1
    dl = (lon2 - lon1) * DEG2RAD
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * WGS84_A * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    p1, p2 = lat1 * DEG2RAD, lat2 * DEG2RAD
    dl = (lon2 - lon1) * DEG2RAD
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.atan2(y, x) * RAD2DEG + 360.0) % 360.0


def en_to_polar(east: float, north: float) -> tuple[float, float]:
    """Convert EN displacement to (range, bearing_rad) where bearing from north."""
    return math.hypot(east, north), math.atan2(east, north)


def polar_to_en(range_m: float, bearing_rad: float) -> tuple[float, float]:
    return range_m * math.sin(bearing_rad), range_m * math.cos(bearing_rad)
