"""Coordinate transformation tests."""
import math

import numpy as np
import pytest

from app.core.coordinate_utils import (
    LocalTangentPlane,
    bearing_deg,
    geodetic_to_local,
    haversine_m,
    local_to_geodetic,
    meters_per_degree,
    wrap_angle,
)


def test_round_trip_local_geodetic():
    ref_lat, ref_lon = 26.9124, 75.7873
    lat, lon = 26.9210, 75.7960
    e, n = geodetic_to_local(lat, lon, ref_lat, ref_lon)
    lat2, lon2 = local_to_geodetic(e, n, ref_lat, ref_lon)
    assert lat2 == pytest.approx(lat, abs=1e-9)
    assert lon2 == pytest.approx(lon, abs=1e-9)


def test_origin_maps_to_zero():
    plane = LocalTangentPlane(26.9124, 75.7873)
    e, n = plane.to_local(26.9124, 75.7873)
    assert abs(e) < 1e-9 and abs(n) < 1e-9


def test_local_offsets_have_expected_sign_and_scale():
    plane = LocalTangentPlane(0.0, 0.0)
    m_lat, m_lon = meters_per_degree(0.0)
    e, n = plane.to_local(0.0, 1.0 / m_lon)   # ~1 m east
    assert e == pytest.approx(1.0, abs=1e-6)
    assert abs(n) < 1e-9
    e, n = plane.to_local(1.0 / m_lat, 0.0)   # ~1 m north
    assert n == pytest.approx(1.0, abs=1e-6)
    assert abs(e) < 1e-9


def test_haversine_matches_local_distance():
    ref = (26.9124, 75.7873)
    d = 100.0
    m_lat, _ = meters_per_degree(ref[0])
    lat2 = ref[0] + d / m_lat
    # the meridian radius of curvature differs slightly from the linear
    # metres-per-degree scale, so allow 1% agreement
    assert haversine_m(ref[0], ref[1], lat2, ref[1]) == pytest.approx(d, rel=1e-2)


def test_bearing_cardinal_directions():
    lat, lon = 26.9124, 75.7873
    m_lat, m_lon = meters_per_degree(lat)
    assert bearing_deg(lat, lon, lat + 0.001, lon) == pytest.approx(0.0, abs=0.2)
    assert bearing_deg(lat, lon, lat, lon + 0.001) == pytest.approx(90.0, abs=0.2)
    assert bearing_deg(lat, lon, lat - 0.001, lon) == pytest.approx(180.0, abs=0.2)
    assert bearing_deg(lat, lon, lat, lon - 0.001) == pytest.approx(270.0, abs=0.2)


def test_wrap_angle_bounds():
    for a in np.linspace(-10, 10, 101):
        w = wrap_angle(float(a))
        assert -math.pi <= w <= math.pi
    assert wrap_angle(math.pi) == pytest.approx(math.pi)
    assert wrap_angle(3 * math.pi / 2) == pytest.approx(-math.pi / 2)


def test_no_cartesian_latlon_shortcut():
    """1 degree of longitude is not 1 degree of latitude in metres."""
    m_lat, m_lon = meters_per_degree(26.9)
    assert m_lon < m_lat < 112000
