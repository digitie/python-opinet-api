"""``iter_stations_in_bbox`` 근사 enumeration 테스트.

OpiNet은 지역/전국 bulk 주유소 목록 엔드포인트가 없으므로, bbox를 ``aroundAll``
반경 격자로 덮어 ``uni_id`` 기준 dedup 순회하는 헬퍼를 검증한다.
"""

import asyncio
import math

import pytest

from opinet import AsyncOpinetClient, OpinetClient
from opinet.client import _METERS_PER_DEGREE_LAT, _bbox_grid_centers
from opinet.exceptions import OpinetInvalidParameterError


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def test_bbox_grid_centers_cover_every_point() -> None:
    min_lon, min_lat, max_lon, max_lat = 127.00, 37.49, 127.08, 37.55
    radius_m = 2000
    centers = list(
        _bbox_grid_centers(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            radius_m=radius_m,
        )
    )
    assert len(centers) > 1

    # bbox 내부를 촘촘히 sampling해 모든 점이 어떤 중심에서 radius 이내인지 확인.
    for i in range(11):
        for j in range(11):
            lon = min_lon + (max_lon - min_lon) * i / 10
            lat = min_lat + (max_lat - min_lat) * j / 10
            nearest = min(
                _haversine_m(lon, lat, c_lon, c_lat) for c_lon, c_lat in centers
            )
            assert nearest <= radius_m + 1.0, (lon, lat, nearest)


def test_bbox_grid_centers_spacing_uses_root_two() -> None:
    centers = list(
        _bbox_grid_centers(
            min_lon=127.0, min_lat=37.5, max_lon=127.2, max_lat=37.7, radius_m=5000
        )
    )
    lats = sorted({lat for _, lat in centers})
    lat_step_m = (lats[1] - lats[0]) * _METERS_PER_DEGREE_LAT
    assert lat_step_m == pytest.approx(5000 * math.sqrt(2.0), rel=1e-6)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_lon": 1.0, "min_lat": 0.0, "max_lon": 0.0, "max_lat": 1.0},  # lon 역전
        {"min_lon": 0.0, "min_lat": 1.0, "max_lon": 1.0, "max_lat": 0.0},  # lat 역전
        {"min_lon": 0.0, "min_lat": 0.0, "max_lon": 1.0, "max_lat": 1.0, "radius_m": 0},
        {
            "min_lon": 0.0,
            "min_lat": 0.0,
            "max_lon": 1.0,
            "max_lat": 1.0,
            "radius_m": 6000,
        },
    ],
)
def test_bbox_grid_centers_rejects_invalid(kwargs: dict) -> None:
    params = {"radius_m": 5000, **kwargs}
    with pytest.raises(OpinetInvalidParameterError):
        list(_bbox_grid_centers(**params))


def test_iter_stations_in_bbox_dedupes_across_cells(
    client: OpinetClient, load_fixture, mock_opinet
) -> None:
    # respx는 같은 fixture를 모든 aroundAll 호출에 반환 → 격자 셀마다 같은 2개 station.
    mock_opinet.add("aroundAll.do", json=load_fixture("around_all_gangnam.json"))

    stations = list(
        client.iter_stations_in_bbox(
            min_lon=127.02,
            min_lat=37.49,
            max_lon=127.07,
            max_lat=37.53,
            radius_m=1000,
        )
    )

    # 여러 격자 셀을 호출했지만 uni_id 기준 dedup → fixture의 고유 2개만.
    assert len(mock_opinet.calls) > 1
    uni_ids = [station.uni_id for station in stations]
    assert uni_ids == ["A0010207", "A0010208"]
    assert len(uni_ids) == len(set(uni_ids))


def test_iter_stations_in_bbox_skips_empty_cells(load_fixture, mock_opinet) -> None:
    # strict_empty=True여도 빈 셀의 OpinetNoDataError를 흡수하고 빈 결과로 끝난다.
    mock_opinet.add("aroundAll.do", json=load_fixture("empty_oil.json"))
    strict_client = OpinetClient(api_key="test-key", retry_backoff=0, strict_empty=True)

    stations = list(
        strict_client.iter_stations_in_bbox(
            min_lon=127.02,
            min_lat=37.49,
            max_lon=127.05,
            max_lat=37.51,
            radius_m=1000,
        )
    )

    assert stations == []
    assert len(mock_opinet.calls) > 1


def test_async_iter_stations_in_bbox_dedupes(load_fixture, mock_opinet) -> None:
    mock_opinet.add("aroundAll.do", json=load_fixture("around_all_gangnam.json"))

    async def run() -> list:
        async with AsyncOpinetClient(api_key="test-key", retry_backoff=0) as client:
            collected = []
            async for station in client.iter_stations_in_bbox(
                min_lon=127.02,
                min_lat=37.49,
                max_lon=127.06,
                max_lat=37.52,
                radius_m=1000,
            ):
                collected.append(station)
            return collected

    stations = asyncio.run(run())

    uni_ids = [station.uni_id for station in stations]
    assert uni_ids == ["A0010207", "A0010208"]
    assert len(mock_opinet.calls) > 1
