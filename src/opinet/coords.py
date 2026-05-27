"""오피넷 주유소 좌표 변환 helper."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

WGS84_CRS = "EPSG:4326"
KATEC_CRS = (
    "+proj=tmerc +lat_0=38 +lon_0=128 +k=0.9999 +x_0=400000 +y_0=600000 "
    "+ellps=bessel +units=m "
    "+towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43 +no_defs"
)


def validate_lon_lat(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 경도/위도 범위를 검증하고 float 쌍으로 반환한다."""

    lon_value = _finite_float(lon, "lon")
    lat_value = _finite_float(lat, "lat")
    if not -180 <= lon_value <= 180:
        raise ValueError(f"longitude out of range: {lon!r}")
    if not -90 <= lat_value <= 90:
        raise ValueError(f"latitude out of range: {lat!r}")
    return lon_value, lat_value


def validate_katec_xy(x: float, y: float) -> tuple[float, float]:
    """KATEC x/y 값을 finite float 쌍으로 반환한다."""

    return _finite_float(x, "katec_x"), _finite_float(y, "katec_y")


def wgs84_to_katec(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 `(lon, lat)`를 오피넷 KATEC `(x, y)`로 변환한다."""

    lon_value, lat_value = validate_lon_lat(lon, lat)
    x, y = _transformer(WGS84_CRS, KATEC_CRS).transform(lon_value, lat_value)
    return float(x), float(y)


def katec_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """오피넷 KATEC `(x, y)`를 WGS84 `(lon, lat)`로 변환한다."""

    x_value, y_value = validate_katec_xy(x, y)
    lon, lat = _transformer(KATEC_CRS, WGS84_CRS).transform(x_value, y_value)
    return validate_lon_lat(float(lon), float(lat))


def _finite_float(value: Any, field_name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


@lru_cache(maxsize=8)
def _transformer(source_crs: str, target_crs: str):  # type: ignore[no-untyped-def]
    from pyproj import Transformer

    return Transformer.from_crs(source_crs, target_crs, always_xy=True)
