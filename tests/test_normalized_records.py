import json
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
import responses
from pydantic import BaseModel, ValidationError
from pykrtour import KatecPoint, PlaceCoordinate

from opinet import (
    FuelType,
    NormalizedFuelAverage,
    NormalizedFuelRegionCode,
    NormalizedFuelStation,
    NormalizedFuelStationDetail,
    NormalizedFuelStationDetailPrice,
    ProductCode,
    StationType,
    to_json_safe_raw,
)

OPINET_BASE_URL = "https://www.opinet.co.kr/api/"


@responses.activate
def test_avg_price_to_normalized_record(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "avgAllPrice.do", json=load_fixture("avg_all_price.json"))

    avg = client.get_national_average_price()[1]
    normalized = avg.to_normalized(endpoint="avgAllPrice.do")

    assert isinstance(normalized, NormalizedFuelAverage)
    assert isinstance(normalized, BaseModel)
    assert normalized.provider == "opinet"
    assert normalized.provider_endpoint == "avgAllPrice.do"
    assert normalized.provider_product_code == "B027"
    assert normalized.provider_product_name == avg.raw["PRODNM"]
    assert normalized.fuel_type is FuelType.GASOLINE
    assert normalized.price == pytest.approx(1667.33)
    assert normalized.diff == pytest.approx(-0.23)
    assert normalized.raw["PRICE"] == "1667.33"
    assert normalized.model_dump()["provider"] == "opinet"
    assert normalized.model_dump(mode="json")["trade_date"] == "2025-07-23"
    with pytest.raises(ValidationError):
        normalized.price = 0.0


def test_normalized_records_reject_extra_fields():
    with pytest.raises(ValidationError):
        NormalizedFuelRegionCode(
            provider_endpoint="areaCode.do",
            provider_region_code="01",
            provider_region_name="Seoul",
            code_level="sido",
            parent_sido_code=None,
            bjd_sido_prefix="11",
            raw={},
            extra_field="not allowed",
        )


@responses.activate
def test_avg_price_kst_datetime_and_timestamp(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "avgAllPrice.do", json=load_fixture("avg_all_price.json"))

    avg = client.get_national_average_price()[0]
    normalized = avg.to_normalized()
    expected = datetime(2025, 7, 23, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    assert normalized.price_datetime() == expected
    assert normalized.price_timestamp() == pytest.approx(expected.timestamp())
    assert avg.price_datetime() == expected
    assert avg.price_timestamp() == pytest.approx(expected.timestamp())


@responses.activate
def test_station_to_normalized_record_without_provider_product_name(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "lowTop10.do", json=load_fixture("low_top10_B027.json"))

    station = client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=2, area="01")[0]
    normalized = station.to_normalized(endpoint="lowTop10.do")

    assert isinstance(normalized, NormalizedFuelStation)
    assert normalized.provider == "opinet"
    assert normalized.provider_endpoint == "lowTop10.do"
    assert normalized.provider_station_id == "A0013150"
    assert normalized.provider_station_name == station.name
    assert normalized.provider_product_code == "B027"
    assert normalized.provider_product_name is None
    assert normalized.fuel_type is FuelType.GASOLINE
    assert normalized.brand_code == "SKE"
    assert normalized.price == pytest.approx(1538.0)
    assert normalized.diff is None
    assert normalized.distance_m is None
    assert normalized.address_jibun == station.address_jibun
    assert normalized.address_road == station.address_road
    assert isinstance(normalized.coordinate, PlaceCoordinate)
    assert normalized.coordinate == station.coordinate
    assert isinstance(normalized.katec_coordinate, KatecPoint)
    assert normalized.katec_coordinate == station.katec_coordinate
    assert normalized.katec_x == station.katec_x
    assert normalized.lon == station.lon
    assert normalized.trade_datetime() is None
    assert station.trade_datetime() is None
    assert normalized.raw["PRICE"] == "1538"


@responses.activate
def test_station_trade_datetime_when_trade_fields_exist(client, load_fixture):
    responses.add(
        responses.GET,
        OPINET_BASE_URL + "lowTop10.do",
        json=load_fixture("low_top10_with_trade_context.json"),
    )

    station = client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=1)[0]
    normalized = station.to_normalized(endpoint="lowTop10.do")
    expected = datetime(2025, 7, 23, 14, 56, 18, tzinfo=ZoneInfo("Asia/Seoul"))

    assert normalized.provider_product_code == "D047"
    assert normalized.provider_product_name == "provider diesel"
    assert normalized.fuel_type is FuelType.DIESEL
    assert normalized.trade_datetime() == expected
    assert station.trade_datetime() == expected
    assert normalized.raw["TRADE_DT"] == "20250723"
    assert normalized.raw["TRADE_TM"] == "145618"


@responses.activate
def test_station_trade_datetime_does_not_depend_on_normalized_endpoint(client, load_fixture, monkeypatch):
    responses.add(
        responses.GET,
        OPINET_BASE_URL + "lowTop10.do",
        json=load_fixture("low_top10_with_trade_context.json"),
    )

    station = client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=1)[0]
    expected = datetime(2025, 7, 23, 14, 56, 18, tzinfo=ZoneInfo("Asia/Seoul"))

    assert station.to_normalized(endpoint="lowTop10.do").provider_endpoint == "lowTop10.do"

    def fail_to_normalized(*args, **kwargs):
        raise AssertionError("Station.trade_datetime should not call to_normalized")

    monkeypatch.setattr(type(station), "to_normalized", fail_to_normalized)

    assert station.trade_datetime() == expected


@responses.activate
def test_station_detail_to_normalized_record(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "detailById.do", json=load_fixture("detail_by_id_A0010207.json"))

    detail = client.get_station_detail("A0010207")
    normalized = detail.to_normalized(endpoint="detailById.do")

    assert isinstance(normalized, NormalizedFuelStationDetail)
    assert isinstance(normalized, BaseModel)
    assert normalized.provider == "opinet"
    assert normalized.provider_endpoint == "detailById.do"
    assert normalized.provider_station_id == "A0010207"
    assert normalized.provider_station_name == detail.name
    assert normalized.brand_code == "SKE"
    assert normalized.sub_brand_code is None
    assert normalized.station_type is StationType.GAS_STATION
    assert normalized.sigun_code == "0113"
    assert normalized.address_jibun == detail.address_jibun
    assert normalized.address_road == detail.address_road
    assert normalized.tel == "02-562-4855"
    assert isinstance(normalized.coordinate, PlaceCoordinate)
    assert normalized.coordinate == detail.coordinate
    assert isinstance(normalized.katec_coordinate, KatecPoint)
    assert normalized.katec_coordinate == detail.katec_coordinate
    assert normalized.katec_x == detail.katec_x
    assert normalized.katec_y == detail.katec_y
    assert normalized.lon == detail.lon
    assert normalized.lat == detail.lat
    assert normalized.has_maintenance is True
    assert normalized.has_carwash is True
    assert normalized.has_cvs is False
    assert normalized.is_kpetro is False
    assert normalized.raw["OIL_PRICE"][0]["PRICE"] == "1745"

    first_price = normalized.prices[0]
    assert isinstance(first_price, NormalizedFuelStationDetailPrice)
    assert first_price.provider == "opinet"
    assert first_price.provider_endpoint == "detailById.do"
    assert first_price.provider_station_id == "A0010207"
    assert first_price.provider_station_name == detail.name
    assert first_price.provider_product_code == "B027"
    assert first_price.fuel_type is FuelType.GASOLINE
    assert first_price.price == pytest.approx(1745.0)
    assert first_price.trade_date == date(2025, 7, 23)
    assert first_price.trade_time == time(14, 56, 18)
    assert first_price.trade_datetime() == datetime(2025, 7, 23, 14, 56, 18, tzinfo=ZoneInfo("Asia/Seoul"))
    assert first_price.raw["TRADE_TM"] == "145618"

    payload = normalized.model_dump(mode="json")
    assert payload["station_type"] == "N"
    assert payload["prices"][0]["trade_date"] == "2025-07-23"
    assert payload["prices"][0]["trade_time"] == "14:56:18"


@responses.activate
def test_area_code_to_normalized_region_code(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "areaCode.do", json=load_fixture("area_code_sido_01.json"))

    area = client.get_area_codes("01")[1]
    normalized = area.to_normalized()

    assert isinstance(normalized, NormalizedFuelRegionCode)
    assert normalized.provider == "opinet"
    assert normalized.provider_endpoint == "areaCode.do"
    assert normalized.provider_region_code == "0113"
    assert normalized.provider_region_name == area.name
    assert normalized.code_level == "sigungu"
    assert normalized.parent_sido_code == "01"
    assert normalized.bjd_sido_prefix == "11"
    assert normalized.raw["AREA_CD"] == "0113"


@responses.activate
def test_json_safe_raw_helper_converts_mapping_proxy_and_tuples(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "detailById.do", json=load_fixture("detail_by_id_A0010207.json"))

    detail = client.get_station_detail("A0010207")
    raw = to_json_safe_raw(detail.raw)

    assert isinstance(raw, dict)
    assert isinstance(raw["OIL_PRICE"], list)
    assert raw["OIL_PRICE"][0]["PRICE"] == "1745"
    assert raw["OIL_PRICE"][0]["TRADE_TM"] == "145618"
    json.dumps(raw, ensure_ascii=False)
