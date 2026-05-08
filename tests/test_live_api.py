from datetime import date

import pytest

from opinet import AreaCode, AvgPrice, ProductCode, Station, StationDetail


pytestmark = pytest.mark.live


def _skip_if_empty(rows: list[object], endpoint: str) -> None:
    if not rows:
        pytest.skip(
            f"{endpoint} returned an empty RESULT.OIL from the live server. "
            "The key may not be provisioned for the official open API gateway."
        )


def test_live_area_code_endpoint_is_reachable(live_client):
    """라이브 서버는 문서화된 RESULT/OIL JSON 감싼 구조를 반환해야 한다."""
    data = live_client._require_http().get("areaCode.do")

    assert isinstance(data, dict)
    assert isinstance(data.get("RESULT"), dict)
    assert "OIL" in data["RESULT"]
    assert isinstance(data["RESULT"]["OIL"], list)


def test_live_official_endpoints_parse_when_key_returns_data(live_client):
    """데이터가 있는 키에서는 실제 API로 공식 5개 엔드포인트를 간단히 검증한다."""
    areas = live_client.get_area_codes()
    _skip_if_empty(areas, "areaCode.do")
    assert all(isinstance(row, AreaCode) for row in areas)
    assert all(isinstance(row.code, str) for row in areas)
    assert any(row.code == "01" for row in areas)

    averages = live_client.get_national_average_price()
    _skip_if_empty(averages, "avgAllPrice.do")
    assert all(isinstance(row, AvgPrice) for row in averages)
    assert all(isinstance(row.trade_date, date) for row in averages)
    assert any(row.product_code is ProductCode.GASOLINE for row in averages)

    lowest = live_client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=1)
    _skip_if_empty(lowest, "lowTop10.do")
    assert len(lowest) == 1
    assert isinstance(lowest[0], Station)
    assert lowest[0].uni_id
    assert isinstance(lowest[0].price, float)

    nearby = live_client.search_stations_around(
        wgs84=(127.0276, 37.4979),
        radius_m=1000,
        prodcd=ProductCode.GASOLINE,
    )
    _skip_if_empty(nearby, "aroundAll.do")
    assert all(isinstance(row, Station) for row in nearby)
    assert all(row.distance_m is not None for row in nearby)

    detail = live_client.get_station_detail(lowest[0].uni_id)
    assert isinstance(detail, StationDetail)
    assert detail.uni_id == lowest[0].uni_id
    assert isinstance(detail.prices, tuple)
