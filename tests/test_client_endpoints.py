from datetime import date, time
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from pykrtour import KatecPoint, PlaceCoordinate

from opinet import BrandCode, OpinetClient, ProductCode, SortOrder, StationType
from opinet.exceptions import OpinetAuthError, OpinetInvalidParameterError, OpinetNoDataError, OpinetServerError

OPINET_BASE_URL = "https://www.opinet.co.kr/api/"


def _query(call):
    return parse_qs(urlparse(call.request.url).query)


@responses.activate
def test_avg_all_price_types(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "avgAllPrice.do", json=load_fixture("avg_all_price.json"))

    rows = client.get_national_average_price()

    assert len(rows) == 5
    first = rows[0]
    assert isinstance(first.trade_date, date)
    assert first.trade_date == date(2025, 7, 23)
    assert first.product_code is ProductCode.GASOLINE_PREMIUM
    assert isinstance(first.product_name, str)
    assert isinstance(first.price, float)
    assert first.price == pytest.approx(1919.44)
    assert isinstance(first.diff, float)
    assert first.diff == pytest.approx(-0.10)
    diesel = next(row for row in rows if row.product_code is ProductCode.DIESEL)
    assert diesel.diff == pytest.approx(0.39)
    query = _query(responses.calls[0])
    assert query["certkey"] == ["test-key"]
    assert query["out"] == ["json"]


@responses.activate
def test_avg_empty_default_and_strict(load_fixture):
    url = OPINET_BASE_URL + "avgAllPrice.do"
    responses.add(responses.GET, url, json=load_fixture("empty_oil.json"))
    assert OpinetClient("test-key", retry_backoff=0).get_national_average_price() == []

    responses.add(responses.GET, url, json=load_fixture("empty_oil.json"))
    with pytest.raises(OpinetNoDataError):
        OpinetClient("test-key", retry_backoff=0, strict_empty=True).get_national_average_price()


@responses.activate
def test_avg_bad_date_is_server_error(load_fixture):
    payload = load_fixture("avg_all_price.json")
    payload["RESULT"]["OIL"][0]["TRADE_DT"] = "2025-07-23"
    responses.add(responses.GET, OPINET_BASE_URL + "avgAllPrice.do", json=payload)

    with pytest.raises(OpinetServerError):
        OpinetClient("test-key", retry_backoff=0).get_national_average_price()


@responses.activate
def test_avg_accepts_single_oil_object(load_fixture):
    payload = load_fixture("avg_all_price.json")
    payload["RESULT"]["OIL"] = payload["RESULT"]["OIL"][0]
    responses.add(responses.GET, OPINET_BASE_URL + "avgAllPrice.do", json=payload)

    rows = OpinetClient("test-key", retry_backoff=0).get_national_average_price()

    assert len(rows) == 1
    assert rows[0].product_code is ProductCode.GASOLINE_PREMIUM


@responses.activate
def test_avg_rejects_non_object_oil_items():
    responses.add(responses.GET, OPINET_BASE_URL + "avgAllPrice.do", json={"RESULT": {"OIL": ["bad"]}})

    with pytest.raises(OpinetServerError):
        OpinetClient("test-key", retry_backoff=0).get_national_average_price()


@responses.activate
def test_lowest_price_types_and_params(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "lowTop10.do", json=load_fixture("low_top10_B027.json"))

    stations = client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=2, area="01")

    assert len(stations) == 2
    first = stations[0]
    assert isinstance(first.uni_id, str)
    assert isinstance(first.name, str)
    assert first.brand is BrandCode.SKE
    assert isinstance(first.price, float)
    assert first.price == pytest.approx(1538.0)
    assert isinstance(first.address_jibun, str)
    assert isinstance(first.address_road, str)
    assert isinstance(first.katec_x, float)
    assert isinstance(first.katec_y, float)
    assert isinstance(first.lon, float)
    assert isinstance(first.lat, float)
    assert first.distance_m is None
    assert stations[1].brand is BrandCode.RTE
    query = _query(responses.calls[0])
    assert query["prodcd"] == ["B027"]
    assert query["cnt"] == ["2"]
    assert query["area"] == ["01"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cnt": 0},
        {"cnt": 21},
        {"cnt": 10, "area": "1"},
        {"cnt": 10, "area": "001"},
        {"cnt": 10, "area": "99"},
        {"cnt": 10, "area": "abcd"},
    ],
)
def test_lowest_price_invalid_params(client, kwargs):
    with pytest.raises(OpinetInvalidParameterError):
        client.get_lowest_price_top20(ProductCode.GASOLINE, **kwargs)


@responses.activate
def test_lowest_price_unknown_brand_is_server_error(load_fixture):
    payload = load_fixture("low_top10_B027.json")
    payload["RESULT"]["OIL"][0]["POLL_DIV_CO"] = "BAD"
    responses.add(responses.GET, OPINET_BASE_URL + "lowTop10.do", json=payload)

    with pytest.raises(OpinetServerError):
        OpinetClient("test-key", retry_backoff=0).get_lowest_price_top20(ProductCode.GASOLINE)


@responses.activate
def test_around_all_wgs84_types_and_query(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "aroundAll.do", json=load_fixture("around_all_gangnam.json"))

    stations = client.search_stations_around(
        coordinate=PlaceCoordinate(lon=127.0276, lat=37.4979),
        radius_m=3000,
        prodcd=ProductCode.GASOLINE,
        sort=SortOrder.PRICE,
    )

    first = stations[0]
    assert first.uni_id == "A0010207"
    assert first.brand is BrandCode.SKE
    assert isinstance(first.price, float)
    assert isinstance(first.distance_m, float)
    assert first.distance_m == pytest.approx(846.6)
    assert 127.02 < first.lon < 127.06
    assert 37.49 < first.lat < 37.51
    assert isinstance(first.coordinate, PlaceCoordinate)
    assert first.coordinate.as_lon_lat() == pytest.approx((first.lon, first.lat))
    query = _query(responses.calls[0])
    assert query["radius"] == ["3000"]
    assert query["prodcd"] == ["B027"]
    assert query["sort"] == ["1"]
    assert float(query["x"][0]) != pytest.approx(127.0276)
    assert float(query["y"][0]) != pytest.approx(37.4979)


@responses.activate
def test_around_all_place_coordinate_query(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "aroundAll.do", json=load_fixture("around_all_gangnam.json"))

    client.search_stations_around(coordinate=PlaceCoordinate(lon=127.0276, lat=37.4979), radius_m=1000)

    query = _query(responses.calls[0])
    assert float(query["x"][0]) == pytest.approx(314213.3092)
    assert float(query["y"][0]) == pytest.approx(544413.5797)


@responses.activate
def test_around_all_katec_query(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "aroundAll.do", json=load_fixture("around_all_gangnam.json"))

    client.search_stations_around(katec=KatecPoint(314871.8, 544012.0), radius_m=1000, sort=SortOrder.DISTANCE)

    query = _query(responses.calls[0])
    assert float(query["x"][0]) == pytest.approx(314871.8)
    assert float(query["y"][0]) == pytest.approx(544012.0)
    assert query["sort"] == ["2"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"coordinate": PlaceCoordinate(lon=127.0, lat=37.5), "katec": KatecPoint(300000.0, 540000.0)},
        {"coordinate": PlaceCoordinate(lon=127.0, lat=37.5), "radius_m": 0},
        {"coordinate": PlaceCoordinate(lon=127.0, lat=37.5), "radius_m": 5001},
    ],
)
def test_around_invalid_params(client, kwargs):
    with pytest.raises(OpinetInvalidParameterError):
        client.search_stations_around(**kwargs)


@responses.activate
def test_detail_full_type_mapping(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "detailById.do", json=load_fixture("detail_by_id_A0010207.json"))

    detail = client.get_station_detail("A0010207")

    assert detail.uni_id == "A0010207"
    assert detail.name == "SK서광주유소"
    assert detail.brand is BrandCode.SKE
    assert detail.sub_brand is None
    assert detail.station_type is StationType.GAS_STATION
    assert detail.sigun_code == "0113"
    assert detail.address_jibun == "서울 강남구 역삼동 834-47"
    assert detail.address_road == "서울 강남구 역삼로 142"
    assert detail.tel == "02-562-4855"
    assert isinstance(detail.katec_x, float)
    assert isinstance(detail.katec_y, float)
    assert isinstance(detail.lon, float)
    assert isinstance(detail.lat, float)
    assert isinstance(detail.coordinate, PlaceCoordinate)
    assert detail.coordinate.as_lon_lat() == pytest.approx((detail.lon, detail.lat))
    assert detail.has_maintenance is True
    assert detail.has_carwash is True
    assert detail.has_cvs is False
    assert detail.is_kpetro is False

    price = detail.prices[0]
    assert price.product_code is ProductCode.GASOLINE
    assert isinstance(price.price, float)
    assert price.price == pytest.approx(1745.0)
    assert isinstance(price.trade_date, date)
    assert price.trade_date == date(2025, 7, 23)
    assert isinstance(price.trade_time, time)
    assert price.trade_time == time(14, 56, 18)
    assert detail.prices[-1].price is None
    assert detail.prices[-1].trade_time == time(0, 0, 0)
    query = _query(responses.calls[0])
    assert query["id"] == ["A0010207"]


@responses.activate
def test_detail_wraps_single_oil_price(load_fixture):
    payload = load_fixture("detail_by_id_A0010207.json")
    payload["RESULT"]["OIL"]["OIL_PRICE"] = payload["RESULT"]["OIL"]["OIL_PRICE"][0]
    responses.add(responses.GET, OPINET_BASE_URL + "detailById.do", json=payload)

    detail = OpinetClient("test-key", retry_backoff=0).get_station_detail("A0010207")

    assert len(detail.prices) == 1
    assert detail.prices[0].product_code is ProductCode.GASOLINE


@responses.activate
def test_detail_rejects_invalid_oil_price_shape(load_fixture):
    payload = load_fixture("detail_by_id_A0010207.json")
    payload["RESULT"]["OIL"]["OIL_PRICE"] = "bad"
    responses.add(responses.GET, OPINET_BASE_URL + "detailById.do", json=payload)

    with pytest.raises(OpinetServerError):
        OpinetClient("test-key", retry_backoff=0).get_station_detail("A0010207")


@responses.activate
def test_detail_empty_raises(load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "detailById.do", json=load_fixture("empty_oil.json"))

    with pytest.raises(OpinetNoDataError):
        OpinetClient("test-key", retry_backoff=0).get_station_detail("A0000000")


def test_detail_invalid_id(client):
    with pytest.raises(OpinetInvalidParameterError):
        client.get_station_detail("")


@responses.activate
def test_area_codes_root(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "areaCode.do", json=load_fixture("area_code_root.json"))

    rows = client.get_area_codes()

    assert len(rows) == 17
    assert rows[0].code == "01"
    assert rows[0].name == "서울"
    assert rows[0].is_sido is True
    assert rows[0].is_sigungu is False
    assert {row.code for row in rows}.isdisjoint({"12", "13"})
    assert all(isinstance(row.code, str) for row in rows)


@responses.activate
def test_area_codes_sido_query(client, load_fixture):
    responses.add(responses.GET, OPINET_BASE_URL + "areaCode.do", json=load_fixture("area_code_sido_01.json"))

    rows = client.get_area_codes("01")

    assert rows[1].code == "0113"
    assert rows[1].is_sigungu is True
    query = _query(responses.calls[0])
    assert query["area"] == ["01"]


@pytest.mark.parametrize("sido", ["1", "001", "ab", "12", "99"])
def test_area_codes_invalid_sido(client, sido):
    with pytest.raises(OpinetInvalidParameterError):
        client.get_area_codes(sido)


@responses.activate
def test_area_codes_missing_name_is_server_error():
    responses.add(responses.GET, OPINET_BASE_URL + "areaCode.do", json={"RESULT": {"OIL": [{"AREA_CD": "01"}]}})

    with pytest.raises(OpinetServerError):
        OpinetClient("test-key", retry_backoff=0).get_area_codes()


@responses.activate
def test_missing_oil_is_server_error():
    responses.add(responses.GET, OPINET_BASE_URL + "areaCode.do", json={"RESULT": {}})

    with pytest.raises(OpinetServerError):
        OpinetClient("test-key", retry_backoff=0).get_area_codes()


def test_missing_api_key_raises_auth_error(monkeypatch):
    monkeypatch.delenv("OPINET_API_KEY", raising=False)
    client = OpinetClient(retry_backoff=0)

    with pytest.raises(OpinetAuthError):
        client.get_area_codes()
