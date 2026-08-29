"""오피넷 API 카탈로그 메타데이터 테스트."""

from __future__ import annotations

from opinet import (
    SERVICE_KEY_URL,
    ApiCatalogItem,
    ProductCode,
    SortOrder,
    get_api_catalog,
    get_api_catalog_item,
    get_api_catalog_options,
)


def test_api_catalog_contains_official_five_with_human_readable_names() -> None:
    catalog = get_api_catalog()

    assert len(catalog) == 5
    assert all(isinstance(item, ApiCatalogItem) for item in catalog)
    assert {item.endpoint for item in catalog} == {
        "avgAllPrice.do",
        "lowTop10.do",
        "aroundAll.do",
        "detailById.do",
        "areaCode.do",
    }
    assert {item.dataset_name for item in catalog} >= {
        "전국 주유소 평균가격",
        "전국/지역별 최저가 주유소",
        "반경 내 주유소 가격",
        "주유소 상세정보 및 제품별 가격",
        "오피넷 시도/시군구 코드",
    }
    assert all(item.service_key_url == SERVICE_KEY_URL for item in catalog)


def test_api_catalog_lookup_and_streamlit_options() -> None:
    item = get_api_catalog_item("aroundAll.do")

    assert item.function_name == "search_stations_around"
    assert item.dataset == "nearby_station_price"
    assert item.dataset_name == "반경 내 주유소 가격"
    assert item.display_name == "반경 내 주유소 가격 (aroundAll.do)"
    assert item.to_dict()["parameters"][0]["name"] == "lon"

    assert get_api_catalog_item(function_name="get_area_codes").endpoint == "areaCode.do"
    assert get_api_catalog_item(dataset="station_detail").endpoint == "detailById.do"

    options = get_api_catalog_options()
    assert options[0]["label"] == "전국 주유소 평균가격 (avgAllPrice.do)"
    assert options[0]["value"] == "get_national_average_price"
    assert options[0]["dataset_name"] == "전국 주유소 평균가격"
    assert options[0]["endpoint"] == "avgAllPrice.do"


def test_api_parameter_kind_drives_debug_ui_widget_selection() -> None:
    """디버그 UI가 ``function_name`` 분기 없이 위젯을 고를 수 있도록 ``kind``가 정확해야 한다."""
    by_function = {item.function_name: item for item in get_api_catalog()}

    lowest = by_function["get_lowest_price_top20"]
    parameters = {parameter.name: parameter for parameter in lowest.parameters}
    assert parameters["prodcd"].kind == "enum"
    assert parameters["cnt"].kind == "integer"
    assert parameters["area"].kind == "string"

    around = by_function["search_stations_around"]
    around_parameters = {parameter.name: parameter for parameter in around.parameters}
    assert around_parameters["lon"].kind == "float"
    assert around_parameters["lat"].kind == "float"
    assert around_parameters["katec_x"].kind == "float"
    assert around_parameters["katec_y"].kind == "float"
    assert around_parameters["radius_m"].kind == "integer"
    assert around_parameters["sort"].kind == "enum"

    # enum 파라미터의 selectbox 후보는 하드코딩 문자열이 아니라 codes.py의 실제 Enum에서 온다.
    assert parameters["prodcd"].allowed_values == tuple(code.value for code in ProductCode)
    assert around_parameters["sort"].allowed_values == tuple(order.value for order in SortOrder)
