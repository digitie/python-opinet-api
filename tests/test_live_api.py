from datetime import date
from pathlib import Path
import sys
import time

import pytest

from opinet import AreaCode, AvgPrice, ProductCode, Station, StationDetail
from opinet.vworld import resolve_sigungu_bjd_code


pytestmark = pytest.mark.live
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_VWORLD_ROOT = PROJECT_ROOT.parent / "python-vworld-api"


def _skip_if_empty(rows: list[object], endpoint: str) -> None:
    if not rows:
        pytest.skip(
            f"{endpoint} returned an empty RESULT.OIL from the live server. "
            "The key may not be provisioned for the official open API gateway."
        )


def _retry_live_call(call):
    last_error: Exception | None = None
    retry_names = {"VworldAuthError", "VworldNetworkError", "VworldServerError"}
    for attempt in range(5):
        try:
            return call()
        except Exception as exc:
            if exc.__class__.__name__ not in retry_names:
                raise
            last_error = exc
            if attempt < 4:
                time.sleep(0.5)
    assert last_error is not None
    raise last_error


@pytest.fixture(scope="session")
def live_vworld_client():
    """같은 workspace의 python-vworld-api와 VWORLD_API_KEY로 VWorld live client를 만든다."""
    if PYTHON_VWORLD_ROOT.exists():
        sys.path.insert(0, str(PYTHON_VWORLD_ROOT / "src"))
    try:
        from vworld import VworldClient
    except ImportError:
        pytest.skip("python-vworld-api is required for VWorld live integration tests")
    client = VworldClient.from_env(domain="", timeout=20, max_retries=1, retry_backoff=0)
    if not client.api_key:
        pytest.skip("VWORLD_API_KEY is required for VWorld live integration tests")
    return client


def test_live_area_code_endpoint_is_reachable(live_client):
    """라이브 서버는 문서화된 RESULT/OIL JSON 감싼 구조를 반환해야 한다."""
    data = live_client._require_http().get("areaCode.do")

    assert isinstance(data, dict)
    assert isinstance(data.get("RESULT"), dict)
    assert "OIL" in data["RESULT"]
    assert isinstance(data["RESULT"]["OIL"], list)


def test_live_resolve_opinet_sigungu_code_with_vworld(live_client, live_vworld_client):
    """오피넷 시군구 코드는 VWorld district 검색으로 법정동 시군구 코드에 매핑된다."""
    areas = live_client.get_area_codes()
    _skip_if_empty(areas, "areaCode.do")

    mapping = _retry_live_call(
        lambda: resolve_sigungu_bjd_code(
            "0113",
            opinet_client=live_client,
            vworld_client=live_vworld_client,
        )
    )

    assert mapping.opinet_sigungu_code == "0113"
    assert mapping.opinet_sigungu_name == "강남구"
    assert mapping.bjd_sigungu_code == "11680"
    assert mapping.bjd_sido_code == "11"
    assert mapping.bjd_sido_name == "서울특별시"
    assert mapping.bjd_sigungu_name == "강남구"
    assert mapping.vworld_title == "서울특별시 강남구"


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
        lon=127.0276,
        lat=37.4979,
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
