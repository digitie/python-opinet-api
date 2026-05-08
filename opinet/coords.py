"""오피넷 주유소 데이터의 KATEC ↔ WGS84 좌표 변환."""

from __future__ import annotations

from math import isfinite

from pyproj import CRS, Transformer

KATEC_PROJ = (
    "+proj=tmerc +lat_0=38 +lon_0=128 +k=0.9999 +x_0=400000 +y_0=600000 "
    "+ellps=bessel +units=m "
    "+towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43 +no_defs"
)

_KATEC = CRS.from_proj4(KATEC_PROJ)
_WGS84 = CRS.from_epsg(4326)
_WGS84_TO_KATEC = Transformer.from_crs(_WGS84, _KATEC, always_xy=True)
_KATEC_TO_WGS84 = Transformer.from_crs(_KATEC, _WGS84, always_xy=True)


def _ensure_finite(*values: float) -> None:
    if not all(isfinite(value) for value in values):
        raise ValueError("coordinate values must be finite")


def wgs84_to_katec(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 경도/위도를 미터 단위 KATEC x/y로 변환한다."""
    _ensure_finite(lon, lat)
    x, y = _WGS84_TO_KATEC.transform(lon, lat)
    return float(x), float(y)


def katec_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """미터 단위 KATEC x/y를 WGS84 경도/위도로 변환한다."""
    _ensure_finite(x, y)
    lon, lat = _KATEC_TO_WGS84.transform(x, y)
    return float(lon), float(lat)
