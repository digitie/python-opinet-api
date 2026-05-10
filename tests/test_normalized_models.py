from datetime import date, time

import pytest
import responses
from pykrtour import PlaceCoordinate

from opinet import (
    AreaCode,
    FuelType,
    OpinetClient,
    ProductCode,
    fuel_type_to_product_code,
    product_code_to_fuel_type,
)
from opinet.exceptions import OpinetInvalidParameterError

OPINET_BASE_URL = "https://www.opinet.co.kr/api/"


@pytest.mark.parametrize(
    ("product_code", "fuel_type"),
    [
        (ProductCode.GASOLINE, FuelType.GASOLINE),
        (ProductCode.GASOLINE_PREMIUM, FuelType.PREMIUM_GASOLINE),
        (ProductCode.DIESEL, FuelType.DIESEL),
        (ProductCode.LPG, FuelType.LPG),
        (ProductCode.KEROSENE, FuelType.KEROSENE),
    ],
)
def test_product_code_fuel_type_roundtrip(product_code, fuel_type):
    assert product_code_to_fuel_type(product_code) is fuel_type
    assert product_code_to_fuel_type(product_code.value) is fuel_type
    assert fuel_type_to_product_code(fuel_type) is product_code
    assert fuel_type_to_product_code(fuel_type.value) is product_code


def test_product_code_fuel_type_mapping_failures():
    with pytest.raises(OpinetInvalidParameterError):
        product_code_to_fuel_type("BAD")
    with pytest.raises(OpinetInvalidParameterError):
        fuel_type_to_product_code("bad")
    with pytest.raises(OpinetInvalidParameterError):
        fuel_type_to_product_code(FuelType.UNKNOWN)


def test_area_code_level_parent_and_bjd_prefix():
    sido = AreaCode(code="01", name="Seoul", raw={"AREA_CD": "01", "AREA_NM": "Seoul", "certkey": "secret"})
    sigungu = AreaCode(code="0113", name="Gangnam", raw={"AREA_CD": "0113", "AREA_NM": "Gangnam"})

    assert sido.code_level == "sido"
    assert sido.parent_sido_code is None
    assert sido.bjd_sido_prefix == "11"
    assert sido.raw["AREA_CD"] == "01"
    assert "certkey" not in sido.raw

    assert sigungu.code_level == "sigungu"
    assert sigungu.parent_sido_code == "01"
    assert sigungu.bjd_sido_prefix == "11"


@pytest.mark.parametrize("code", ["001", "99", "9913"])
def test_area_code_invalid_level_raises(code):
    area = AreaCode(code=code, name="invalid")
    with pytest.raises(OpinetInvalidParameterError):
        _ = area.code_level


@responses.activate
def test_avg_price_normalized_fields_and_raw(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "avgAllPrice.do", json=load_fixture("avg_all_price.json"))

    rows = client.get_national_average_price()
    premium = rows[0]

    assert premium.provider_product_code == "B034"
    assert premium.provider_product_name == premium.raw["PRODNM"]
    assert premium.fuel_type is FuelType.PREMIUM_GASOLINE
    assert premium.raw["PRICE"] == "1919.44"
    assert premium.price == pytest.approx(1919.44)
    with pytest.raises(TypeError):
        premium.raw["PRICE"] = "0"


@responses.activate
def test_station_request_product_context_coordinates_and_raw(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "lowTop10.do", json=load_fixture("low_top10_B027.json"))

    stations = client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=2, area="01")
    station = stations[0]

    assert station.product_code is ProductCode.GASOLINE
    assert station.provider_product_code == "B027"
    assert station.product_name is None
    assert station.provider_product_name is None
    assert station.fuel_type is FuelType.GASOLINE
    assert station.provider_station_id == "A0013150"
    assert station.brand_code == "SKE"
    assert station.raw["PRICE"] == "1538"
    assert station.price == pytest.approx(1538.0)

    assert station.katec_coordinate.as_x_y() == (station.katec_x, station.katec_y)
    assert station.coordinate.as_lon_lat() == pytest.approx((station.lon, station.lat))
    with pytest.raises(TypeError):
        station.raw["PRICE"] = "0"


@responses.activate
def test_station_response_product_and_trade_context_prefer_response(client, load_fixture):
    responses.add(
        responses.GET,
        OPINET_BASE_URL + "lowTop10.do",
        json=load_fixture("low_top10_with_trade_context.json"),
    )

    stations = client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=1)
    station = stations[0]

    assert station.product_code is ProductCode.DIESEL
    assert station.product_name == "provider diesel"
    assert station.provider_product_code == "D047"
    assert station.provider_product_name == "provider diesel"
    assert station.fuel_type is FuelType.DIESEL
    assert station.trade_date == date(2025, 7, 23)
    assert station.trade_time == time(14, 56, 18)
    assert station.raw["TRADE_DT"] == "20250723"
    assert station.raw["TRADE_TM"] == "145618"


@responses.activate
def test_around_station_request_product_context(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "aroundAll.do", json=load_fixture("around_all_gangnam.json"))

    stations = client.search_stations_around(
        coordinate=PlaceCoordinate(lon=127.0276, lat=37.4979),
        prodcd=ProductCode.DIESEL,
    )

    assert stations[0].product_code is ProductCode.DIESEL
    assert stations[0].provider_product_code == "D047"
    assert stations[0].fuel_type is FuelType.DIESEL


@responses.activate
def test_station_detail_and_oil_price_raw_preserve_nested_strings(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "detailById.do", json=load_fixture("detail_by_id_A0010207.json"))

    detail = client.get_station_detail("A0010207")
    first_price = detail.prices[0]

    assert detail.raw["UNI_ID"] == "A0010207"
    assert isinstance(detail.raw["OIL_PRICE"], tuple)
    assert detail.raw["OIL_PRICE"][0]["PRICE"] == "1745"
    assert detail.raw["OIL_PRICE"][0]["TRADE_TM"] == "145618"
    assert first_price.provider_product_code == "B027"
    assert first_price.fuel_type is FuelType.GASOLINE
    assert first_price.raw["PRICE"] == "1745"
    with pytest.raises(TypeError):
        detail.raw["OIL_PRICE"][0]["PRICE"] = "0"


def test_raw_payload_rejects_invalid_shape():
    with pytest.raises(TypeError):
        AreaCode(code="01", name="Seoul", raw="not-a-mapping")
