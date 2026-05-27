"""오피넷 API 카탈로그 메타데이터 테스트."""

from __future__ import annotations

from opinet import (
    SERVICE_KEY_URL,
    ApiCatalogItem,
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
