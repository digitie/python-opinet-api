import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
import random
from unittest.mock import AsyncMock
from urllib.parse import urlencode
from types import SimpleNamespace

import pytest

from opinet.codes import ProductCode, StationType
from opinet.exceptions import OpinetAuthError, OpinetRateLimitError, OpinetServerError
from opinet.experimental import (
    BrowserRegion,
    OpinetBrowserCollector,
    OpinetBrowserThrottle,
    parse_browser_response,
)
from opinet.experimental import browser as browser_module


def _row(**overrides):
    row = {
        "B034_P": "99999",
        "B027_P": "1815",
        "D047_P": "1815",
        "C004_P": "99999",
        "K015_P": "99999",
        "B034_DT": " ",
        "B027_DT": "2026-09-18 18:00:41",
        "D047_DT": "2026-09-18 18:00:52",
        "C004_DT": " ",
        "K015_DT": " ",
        "GIS_X_COOR": "321217.07850",
        "GIS_Y_COOR": "525868.57030",
        "DISC_IF_CONTS": "할인 정보",
        "SAVE_EVENT_CONTS": "적립 정보",
        "REP_EVENT_CONTS": "사은 행사",
        "ON_EVENT_CONTS": "온라인 행사",
        "ETC_BIZ_CONTS": "기타 안내",
        "VLT_YN": "N",
        "SELF_DIV_CD": "Y",
        "SEL24_YN": "N",
        "POLL_DIV_CD": "SOL",
        "OS_NM": "테스트주유소",
        "POLL_DIV_NM": "S-OIL",
        "PHN_NO": "031-000-0000",
        "RD_ADDR": "경기 용인시 수지구 테스트로 1",
        "CWSH_YN": "Y",
        "MAINT_YN": "N",
        "CVS_YN": "N",
        "LPG_YN": "N",
        "KPETRO_YN": "Y",
        "UNI_ID": "A0000001",
        "BIZ_NO": "1234567890",
        "CB_CD": "CB",
        "CS_YN": "N",
        "KPETRO_DP_YN": "Y",
        "GOOD_OS_YN": "Y",
        "GOOD_OS_YN5": "N",
        "RGN_FRCS_YN": "Y",
    }
    row.update(overrides)
    return row


@pytest.fixture
def region():
    return BrowserRegion(
        sido_value="경기도",
        sido_name="경기",
        sigungu_value="용인시수지구",
        sigungu_name="용인시수지구",
        dong_value="풍덕천동",
        dong_name="풍덕천동",
    )


def test_browser_response_merges_product_lists_and_converts_types(region):
    payload = {
        "selectVO": {"LPG_YN": "N"},
        "list": [_row()],
        "list2": [_row(B034_P="2235", B034_DT="2026-09-18 18:03:46")],
        "list3": [],
        "list4": None,
    }

    stations = parse_browser_response(
        payload,
        region=region,
        station_kind="station",
        query_level="dong",
    )

    assert len(stations) == 1
    station = stations[0]
    assert station.station_id == "A0000001"
    assert station.station_type is StationType.GAS_STATION
    assert station.brand_code == "SOL"
    assert station.is_self is True
    assert station.is_kpetro is True
    assert station.is_electronic is True
    assert station.is_good is True
    assert station.has_carwash is True
    assert station.is_region_franchise is True
    assert station.price_by_product[ProductCode.GASOLINE].price == 1815.0
    assert station.price_by_product[ProductCode.GASOLINE_PREMIUM].price == 2235.0
    assert station.price_by_product[ProductCode.KEROSENE].price is None
    assert station.lon is not None
    assert station.lat is not None
    assert station.raw["B027_P"] == "1815"
    assert station.prices[0].updated_at is not None


def test_browser_response_preserves_illegal_station_and_unknown_raw_fields(region):
    row = _row(
        UNI_ID="A0000002",
        OS_NM="불법표시주유소",
        VLT_YN="Y",
        GOOD_OS_YN5="Y",
        UNKNOWN_PROVIDER_FIELD="keep-me",
    )
    station = parse_browser_response(
        {"selectVO": {"LPG_YN": "N"}, "list": [row]},
        region=region,
        station_kind="station",
        query_level="sigungu",
    )[0]

    assert station.is_illegal is True
    assert station.is_good_strong is True
    assert station.raw["UNKNOWN_PROVIDER_FIELD"] == "keep-me"


def test_browser_response_uses_select_station_type_when_row_omits_it(region):
    row = _row(LPG_YN=" ", K015_P="1040", K015_DT="2026-09-18 10:00:00")
    station = parse_browser_response(
        {"selectVO": {"LPG_YN": "C"}, "list": [row]},
        region=region,
        station_kind="lpg",
        query_level="sigungu",
    )[0]

    assert station.station_type is StationType.BOTH
    assert station.price_by_product[ProductCode.LPG].price == 1040.0
    assert station.source_kinds == ("lpg",)


def test_browser_parsers_cover_provider_values_and_js_arguments():
    assert browser_module._parse_provider_datetime(None) is None
    assert browser_module._parse_provider_datetime("2026-09-18 10:00:00.123").microsecond == 123000
    with pytest.raises(ValueError):
        browser_module._parse_provider_datetime("not-a-date")

    assert browser_module._parse_price("1,815원") == 1815.0
    assert browser_module._parse_price("-") is None
    assert browser_module._parse_station_type(None) is None
    assert browser_module._parse_station_type("unknown") is None

    assert browser_module._parse_js_string_call(
        "javascript:fn_test('a\\'b', 'x&amp;y')",
        "fn_test",
    ) == ("a'b", "x&y")
    with pytest.raises(ValueError):
        browser_module._parse_js_string_call("fn_test('x')", "fn_test")
    with pytest.raises(ValueError):
        browser_module._parse_js_string_call("javascript:fn_test(x)", "fn_test")
    with pytest.raises(ValueError):
        browser_module._parse_js_string_call("javascript:fn_test('x' 'y')", "fn_test")
    with pytest.raises(ValueError):
        browser_module._parse_js_string_call("javascript:fn_test('x)", "fn_test")


def test_browser_raw_rows_and_illegal_dom_price_branches():
    values = [str(index) for index in range(len(browser_module._OS_POP_FIELDS))]
    href = "javascript:fn_osPop(" + ",".join(f"'{value}'" for value in values) + ");"
    parsed = browser_module._row_from_os_pop_href(href)
    assert parsed["UNI_ID"] == values[31]
    with pytest.raises(ValueError):
        browser_module._row_from_os_pop_href("javascript:fn_osPop('one')")

    base = {
        "href": "javascript:fnVolatInfowindow('U1','N','')",
        "title": "불법 주유소",
        "brand": "S-OIL",
        "labels": ["셀프", "품질", "전산", "착한", "착하디 착한주유소"],
        "prices": ["1,800", "1,700"],
    }
    for body_id, expected in (
        ("body1", "B027_P"),
        ("body2", "B034_P"),
        ("body3", "B027_P"),
        ("body4", "C004_P"),
        ("bodyLpg", "K015_P"),
    ):
        raw = browser_module._row_from_illegal_dom_record({**base, "body_id": body_id})
        assert expected in raw
    raw = browser_module._row_from_illegal_dom_record({**base, "body_id": "body1", "prices": []})
    assert "B027_P" not in raw
    with pytest.raises(ValueError):
        browser_module._row_from_illegal_dom_record({"href": "javascript:fnVolatInfowindow('U1')"})


def test_browser_rows_and_station_properties(region):
    assert browser_module._as_rows(None, "list") == ()
    row = {"value": "one"}
    assert browser_module._as_rows(row, "list") == (row,)
    assert browser_module._as_rows([row], "list") == (row,)
    with pytest.raises(OpinetServerError):
        browser_module._as_rows(["not-a-row"], "list")

    station = parse_browser_response(
        {"list": [_row(POLL_DIV_CD="RTO", UNI_ID=None, B027_P=" ")]},
        region=region,
        station_kind="station",
        query_level="sigungu",
    )[0]
    assert station.is_alddle is True
    assert station.station_id is None
    assert browser_module._station_key(station)[2] == station.name
    assert station.raw["B027_P"] == " "
    assert isinstance(station.raw["B027_P"], str)
    station_repr = repr(station)
    assert "UNKNOWN_PROVIDER_FIELD" not in station_repr
    assert station.phone not in station_repr
    with pytest.raises(TypeError):
        station.raw["new"] = "value"


def test_browser_station_merge_and_invalid_row(region):
    left_row = _row(
        UNI_ID="MERGE",
        OS_NM="",
        POLL_DIV_CD="",
        POLL_DIV_NM="",
        PHN_NO="",
        RD_ADDR="",
        B027_P="",
        B027_DT="",
        DISC_IF_CONTS="",
    )
    right_row = _row(
        UNI_ID="MERGE",
        OS_NM="보강주유소",
        B027_P="1,900",
        B027_DT="2026-09-18 19:00:00",
        DISC_IF_CONTS="할인",
        UNKNOWN="kept",
    )
    stations = parse_browser_response(
        {"list": [left_row], "list2": [right_row]},
        region=region,
        station_kind="station",
        query_level="sigungu",
    )
    station = stations[0]
    assert station.name == "보강주유소"
    assert station.price_by_product[ProductCode.GASOLINE].price == 1900.0
    assert station.price_by_product[ProductCode.GASOLINE].updated_at is not None
    assert station.raw["UNKNOWN"] == "kept"

    with pytest.raises(OpinetServerError):
        parse_browser_response(
            {"list": [_row(B027_DT="not-a-date")]},
            region=region,
            station_kind="station",
            query_level="sigungu",
        )
    with pytest.raises(OpinetServerError):
        parse_browser_response(
            {"list": ["not-a-row"]},
            region=region,
            station_kind="station",
            query_level="sigungu",
        )


def test_browser_response_validation_and_schema_errors(region):
    with pytest.raises(OpinetServerError, match="station lists"):
        parse_browser_response(
            {"selectVO": {"LPG_YN": "N"}},
            region=region,
            station_kind="station",
            query_level="sigungu",
        )
    with pytest.raises(OpinetAuthError):
        browser_module._validate_response(
            _FakeResponse("https://www.opinet.co.kr/searRgSelect.do", status=403),
            "searRgSelect.do",
        )
    with pytest.raises(OpinetRateLimitError):
        browser_module._validate_response(
            _FakeResponse("https://www.opinet.co.kr/searRgSelect.do", status=429),
            "searRgSelect.do",
        )
    with pytest.raises(OpinetServerError):
        browser_module._validate_response(
            _FakeResponse("https://evil.example/searRgSelect.do"),
            "searRgSelect.do",
        )


def test_browser_lpg_dom_brand_precedence_and_optional_region_flag(region):
    lpg_raw = browser_module._row_from_illegal_dom_record(
        {
            "href": "javascript:fnVolatInfowindow('LPG','Y','')",
            "title": "불법 충전소",
            "prices": ["1137"],
            "labels": [],
            "body_id": "body1",
        }
    )
    assert lpg_raw["K015_P"] == "1137"
    assert "B027_P" not in lpg_raw

    station = parse_browser_response(
        {
            "list": [
                _row(
                    POLL_DIV_CD="SOL",
                    POLL_DIV_CO="GSC",
                    RGN_FRCS_YN=" ",
                )
            ]
        },
        region=region,
        station_kind="station",
        query_level="sigungu",
    )[0]
    assert station.brand_code == "GSC"
    assert station.is_region_franchise is None


def test_browser_station_merge_preserves_positive_flags(region):
    station = parse_browser_response(
        {
            "list": [
                _row(
                    UNI_ID="FLAGS",
                    SELF_DIV_CD="N",
                    CWSH_YN="N",
                    GOOD_OS_YN="N",
                    RGN_FRCS_YN=" ",
                )
            ],
            "list2": [
                _row(
                    UNI_ID="FLAGS",
                    SELF_DIV_CD="Y",
                    CWSH_YN="Y",
                    GOOD_OS_YN="Y",
                    RGN_FRCS_YN="Y",
                )
            ],
        },
        region=region,
        station_kind="station",
        query_level="sigungu",
    )[0]
    assert station.is_self is True
    assert station.has_carwash is True
    assert station.is_good is True
    assert station.is_region_franchise is True


def test_browser_throttle_rejects_invalid_request_budget():
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(max_search_requests=0)


def test_browser_throttle_samples_inside_configured_bounds():
    throttle = OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.1)
    rng = random.Random(7)
    action_delay = throttle.sample_action_delay(rng)
    run_delay = throttle.sample_run_interval(rng)

    assert 0.0 <= action_delay <= 0.1
    assert run_delay == timedelta(hours=8)
    assert throttle.max_runs_per_24h == 3


def test_browser_throttle_rejects_intervals_outside_load_policy():
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(run_interval_min=timedelta(hours=7))
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(run_interval_max=timedelta(hours=13))
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(max_runs_per_24h=4)
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(action_min_seconds=2.0, action_max_seconds=1.0)
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(run_interval_min=timedelta(hours=11), run_interval_max=timedelta(hours=10))


def test_browser_throttle_delays_when_daily_run_budget_is_reached():
    throttle = OpinetBrowserThrottle(
        run_interval_min=timedelta(hours=8),
        run_interval_max=timedelta(hours=8),
    )
    delay, recent_runs = browser_module._scheduled_run_delay(
        throttle,
        random.Random(7),
        [0.0, 60 * 60, 2 * 60 * 60],
        now=2 * 60 * 60 + 60,
    )

    assert recent_runs == [0.0, 60 * 60, 2 * 60 * 60]
    assert delay == timedelta(hours=21, minutes=59)


def test_browser_collector_rejects_non_opinet_url():
    assert OpinetBrowserCollector().timeout_ms == 60_000
    assert OpinetBrowserCollector(timeout_ms=30_000).timeout_ms == 30_000
    with pytest.raises(ValueError):
        OpinetBrowserCollector(url="https://example.com/collector")
    with pytest.raises(ValueError):
        OpinetBrowserCollector(url="https://www.opinet.co.kr.evil.example/searRgSelect.do")
    with pytest.raises(ValueError):
        OpinetBrowserCollector(timeout_ms=0)
    with pytest.raises(ValueError):
        OpinetBrowserCollector(query_level="invalid")


@pytest.mark.asyncio
async def test_default_action_delays_remain_random_and_bounded():
    page = _FakeRegionPage()
    collector = OpinetBrowserCollector(rng=random.Random(23))
    for _ in range(100):
        await collector._pause(page)
    assert len(page.waits) == 100
    assert min(page.waits) >= 50
    assert max(page.waits) <= 150
    assert len(set(page.waits)) > 20
    # 전국 약230개 시군구의 두 탭에서 조작 대기가 시간을 지배하지 않는다.
    assert sum(page.waits) / len(page.waits) * 1150 < 180_000


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "font", "media", "document", "script", "stylesheet", "xhr", "fetch", "other"])
async def test_browser_resource_policy_keeps_scripts_and_price_data(kind):
    route = SimpleNamespace(request=SimpleNamespace(resource_type=kind), abort=AsyncMock(), continue_=AsyncMock())
    await browser_module._route_collection_resource(route)
    if kind in {"image", "font", "media"}:
        route.abort.assert_awaited_once_with("blockedbyclient")
        route.continue_.assert_not_awaited()
    else:
        route.continue_.assert_awaited_once_with()
        route.abort.assert_not_awaited()


@pytest.mark.parametrize("payload", [None, [], {}, {"result": {}}, {"result": [None]}, {"result": [{}]}, {"result": [{"SIGUNGU_NM": " "}]}])
def test_sigungu_response_cannot_turn_invalid_payload_into_empty_options(payload):
    with pytest.raises(OpinetServerError):
        browser_module._sigungu_options(payload)


def test_sigungu_response_preserves_order_and_empty_result():
    assert browser_module._sigungu_options({"result": []}) == []
    assert browser_module._sigungu_options({"result": [{"SIGUNGU_NM": "중구"}, {"SIGUNGU_NM": " 종로구 "}]}) == [
        ["중구", "중구"], ["종로구", "종로구"]]


@pytest.mark.parametrize("changed", ["OS_NM", "OS_ADDR", "SIDO_NM0", "SIDO_NM", "SIGUNGU_NM0", "SIGUNGU_NM",
                                    "DONG_NM", "SEARCH_MOD", "BTN_DIV", "LPG_YN", "iframe", "duplicates"])
def test_auto_query_reuse_rejects_different_search_scope(region, changed):
    region = replace(region, dong_value=None, dong_name=None)
    frame = object()
    page = SimpleNamespace(main_frame=frame)
    fields = {"SIDO_NM0": region.sido_value, "SIDO_NM": region.sido_value,
              "SIGUNGU_NM0": region.sigungu_value, "SIGUNGU_NM": region.sigungu_value,
              "DONG_NM": "", "SEARCH_MOD": "addr", "OS_NM": "", "OS_ADDR": "",
              "BTN_DIV": "os_btn", "LPG_YN": ""}
    request = SimpleNamespace(method="POST", frame=frame, is_navigation_request=lambda: True,
                              post_data=urlencode(fields))
    response = SimpleNamespace(request=request, url="https://www.opinet.co.kr/searRgSelect.do")
    assert browser_module._automatic_sigungu_result(page, response, region, "station")
    if changed == "iframe":
        request.frame = object()
    elif changed == "duplicates":
        request.post_data += "&SIDO_NM0=" + region.sido_value
    else:
        fields[changed] = "다름"
        request.post_data = urlencode(fields)
    assert not browser_module._automatic_sigungu_result(page, response, region, "station")


def test_browser_loader_reports_optional_dependency(monkeypatch):
    def missing(_name):
        raise ModuleNotFoundError("playwright")

    monkeypatch.setattr(browser_module.importlib, "import_module", missing)
    with pytest.raises(ImportError, match="Playwright"):
        browser_module._load_playwright()

    async_playwright = object()
    monkeypatch.setattr(
        browser_module.importlib,
        "import_module",
        lambda _name: SimpleNamespace(async_playwright=async_playwright),
    )
    assert browser_module._load_playwright() is async_playwright


class _FakeLocator:
    def __init__(self, *, values=None, current="", on_select=None, attributes=None):
        self.values = values or []
        self.current = current
        self.on_select = on_select
        self.attributes = attributes or {}
        self.selected = []
        self.clicked = 0

    async def evaluate_all(self, _script):
        return self.values

    async def input_value(self):
        return self.current

    async def get_attribute(self, name):
        return self.attributes.get(name)

    async def select_option(self, *, value):
        self.current = value
        self.selected.append(value)
        if self.on_select is not None:
            self.on_select(value)

    async def click(self, **_kwargs):
        self.clicked += 1


class _FakeEvents:
    def on(self, event, handler):
        pass

    def remove_listener(self, event, handler):
        pass


@pytest.mark.parametrize("phase", ["tab:lpg", "select:#SIGUNGU_NM0", "search:station"])
def test_browser_action_failure_has_bounded_redacted_network_context(phase):
    handlers = {}
    page = SimpleNamespace(on=handlers.__setitem__, remove_listener=lambda event, handler: handlers.pop(event))
    request = SimpleNamespace(
        url="https://www.opinet.co.kr/searRgSelect.do?certkey=secret",
        method="GET", resource_type="document",
    )
    with pytest.raises(OpinetServerError) as raised:
        with browser_module._observe_browser_action(page, phase):
            for _ in range(20):
                handlers["request"](request)
            handlers["response"](SimpleNamespace(request=request, status=503))
            handlers["requestfailed"](request)
            request.url = "https://external.invalid/private-secret-path"
            request.method = "DELETE"
            handlers["request"](request)
            request.resource_type = "image"
            handlers["request"](request)
            handlers["response"](SimpleNamespace(request=request, status=200))
            for _ in range(12):
                handlers["requestfailed"](request)
            raise TimeoutError("secret response body and certkey")
    message = str(raised.value)
    assert f"phase={phase}" in message
    assert "cause=TimeoutError" in message
    assert "response:GET:searRgSelect.do:503" in message
    assert "requestfailed:GET:searRgSelect.do" in message
    assert "request:other:other" in message
    assert "secret" not in message
    assert len(message.split("events=")[1].split(",")) == 8
    assert not handlers


@pytest.mark.parametrize("error", [
    browser_module.OpinetAuthError("denied"), browser_module.OpinetRateLimitError("limited"),
    asyncio.CancelledError(),
])
def test_browser_action_preserves_provider_errors_and_cancellation(error):
    handlers = {}
    page = SimpleNamespace(on=handlers.__setitem__, remove_listener=lambda event, handler: handlers.pop(event))
    with pytest.raises(type(error)) as raised:
        with browser_module._observe_browser_action(page, "search:lpg"):
            raise error
    assert raised.value is error
    assert not handlers


def test_browser_action_no_response_diagnostic():
    with pytest.raises(OpinetServerError, match="events=none"):
        with browser_module._observe_browser_action(_FakeEvents(), "tab:lpg"):
            raise TimeoutError()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,target",
    [("11680", "11680"), ("secret=value", "redacted"), ("용인시수지구", "용인시수지구")],
)
async def test_selection_timeout_reports_safe_region_target(value, target):
    class NoResponsePage(_FakeRegionPage):
        def expect_response(self, predicate, timeout):
            raise TimeoutError("secret=value")

    with pytest.raises(OpinetServerError, match=f"target={target}") as raised:
        await OpinetBrowserCollector()._select_value(NoResponsePage(), "#SIGUNGU_NM0", value)
    assert "secret=value" not in str(raised.value)


class _FakeRegionPage(_FakeEvents):
    def __init__(self):
        self.current = {"#SIDO_NM0": "", "#SIGUNGU_NM0": "", "#DONG_NM": ""}
        self.locators = {}
        self.waits = []

    async def evaluate(self, _script, **_kwargs):
        return 1.0

    def locator(self, selector):
        if selector.endswith(" option"):
            base = selector.removesuffix(" option")
            if base == "#SIDO_NM0":
                values = [{"value": "11", "name": "서울"}, {"value": "", "name": "무시"}]
            elif base == "#SIGUNGU_NM0" and self.current["#SIDO_NM0"] == "11":
                values = [{"value": "11680", "name": "강남구"}]
            elif base == "#DONG_NM" and self.current["#SIGUNGU_NM0"] == "11680":
                values = [{"value": "11680101", "name": "역삼동"}]
            else:
                values = []
            return _FakeLocator(values=values)
        locator = self.locators.setdefault(
            selector,
            _FakeLocator(
                current=self.current.get(selector, ""),
                on_select=lambda value, selector=selector: self.current.__setitem__(selector, value),
            ),
        )
        return locator

    async def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

    def expect_response(self, predicate, timeout):
        assert timeout > 0
        candidates = (
            _FakeResponse("https://www.opinet.co.kr/common/sigunguGisSelect.do", payload={"result": [{"SIGUNGU_NM": "11680"}]}),
            _FakeResponse("https://www.opinet.co.kr/common/geocodeUtmkSelect.do"),
        )
        for response in candidates:
            if predicate(response):
                return _FakeResponseContext(response)
        raise AssertionError("fake response predicate did not match")

    async def wait_for_function(self, _script, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_browser_region_discovery_and_selection_helpers():
    throttle = OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0)
    page = _FakeRegionPage()
    collector = OpinetBrowserCollector(throttle=throttle, query_level="dong")
    assert await collector._read_options(page, "#SIDO_NM0") == (("11", "서울"),)
    await collector._select_value(page, "#SIDO_NM0", "11")
    await collector._select_value(page, "#SIDO_NM0", "11")
    regions = await collector._discover_regions(page)
    assert regions[0].dong_name == "역삼동"
    assert collector._query_regions(regions) == tuple(regions)

    sigungu_collector = OpinetBrowserCollector(throttle=throttle, query_level="sigungu")
    duplicate = regions + [replace_region(regions[0], dong_value="11680102", dong_name="삼성동")]
    collapsed = sigungu_collector._query_regions(duplicate)
    assert len(collapsed) == 1
    assert collapsed[0].dong_value is None
    assert page.waits == []


def replace_region(region, **changes):
    values = {
        "sido_value": region.sido_value,
        "sido_name": region.sido_name,
        "sigungu_value": region.sigungu_value,
        "sigungu_name": region.sigungu_name,
        "dong_value": region.dong_value,
        "dong_name": region.dong_name,
    }
    values.update(changes)
    return BrowserRegion(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_body", [True, False])
async def test_region_selection_waits_for_body_after_response_headers(finish_body):
    headers_received = asyncio.Event()
    body_received = asyncio.Event()

    class StreamingResponse(_FakeResponse):
        async def body(self):
            headers_received.set()
            await body_received.wait()
            return b"{}"

        async def json(self):
            return {"result": []}

    class StreamingPage(_FakeRegionPage):
        def expect_response(self, predicate, timeout):
            response = StreamingResponse("https://www.opinet.co.kr/common/sigunguGisSelect.do")
            assert predicate(response)
            return _FakeResponseContext(response)

        async def wait_for_function(self, _script, **_kwargs):
            assert body_received.is_set()

    collector = OpinetBrowserCollector(timeout_ms=100,
        throttle=OpinetBrowserThrottle(action_min_seconds=0, action_max_seconds=0))
    task = asyncio.create_task(collector._select_value(StreamingPage(), "#SIDO_NM0", "11"))
    await asyncio.wait_for(headers_received.wait(), 1)
    assert not task.done()
    if finish_body:
        body_received.set()
        await task
    else:
        with pytest.raises(TimeoutError):
            await task


class _FakeResponse:
    def __init__(self, url, payload=None, content_type="application/json", status=200, text_body=""):
        self.url = url
        self.payload = payload
        self.content_type = content_type
        self.status = status
        self.text_body = text_body
        self.request = SimpleNamespace(method="POST")

    async def body(self):
        return self.text_body.encode()

    async def header_value(self, _name):
        return self.content_type

    async def json(self):
        return self.payload

    async def text(self):
        return self.text_body


class _FakeResponseContext:
    def __init__(self, response):
        self.response = response

    @property
    def value(self):
        return self._get_response()

    async def _get_response(self):
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    '<html><title>error.jsp</title><body>The service is not available.</body></html>',
    '<html><body>THE SERVICE IS NOT AVAILABLE.</body></html>',
])
async def test_http_200_service_unavailable_is_not_a_search_page(body):
    response = _FakeResponse(
        "https://www.opinet.co.kr/searRgSelect.do", content_type="text/html", text_body=body,
    )
    with pytest.raises(OpinetServerError, match="service-unavailable"):
        await browser_module._reject_blocked_response(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("body,blocked", [("<html>지역 검색</html>", False), ("<html>CAPTCHA</html>", True)])
async def test_lost_navigation_response_checks_current_document(body, blocked):
    class LostResponse(_FakeResponse):
        async def text(self):
            raise RuntimeError("Protocol error (Network.getResponseBody): No resource with given identifier found")

    class CurrentPage:
        url = "https://www.opinet.co.kr/searRgSelect.do"

        async def wait_for_load_state(self, state, *, timeout):
            assert state == "domcontentloaded"
            assert timeout == 30_000

        async def content(self):
            return body

    response = LostResponse(CurrentPage.url, content_type="text/html")
    if blocked:
        with pytest.raises(OpinetServerError, match="access-block"):
            await browser_module._reject_blocked_response(response, page=CurrentPage())
    else:
        await browser_module._reject_blocked_response(response, page=CurrentPage())


@pytest.mark.asyncio
async def test_lost_response_does_not_accept_external_or_unrelated_navigation():
    class LostResponse(_FakeResponse):
        async def text(self):
            raise RuntimeError("Protocol error (Network.getResponseBody): No resource with given identifier found")

    response = LostResponse("https://www.opinet.co.kr/searRgSelect.do", content_type="text/html")
    for url in (
        "https://example.com/searRgSelect.do", "https://www.opinet.co.kr/login.do",
        "https://www.opinet.co.kr/a/searRgSelect.do", "https://www.opinet.co.kr/searRgSelect.do?region=other",
    ):
        page = SimpleNamespace(url=url)
        with pytest.raises(OpinetServerError, match="navigation"):
            await browser_module._reject_blocked_response(response, page=page)
    with pytest.raises(RuntimeError, match="No resource"):
        await browser_module._reject_blocked_response(response)

    response = LostResponse("https://www.opinet.co.kr/a/searRgSelect.do", content_type="text/html")
    with pytest.raises(OpinetServerError, match="navigation"):
        await browser_module._reject_blocked_response(
            response, page=SimpleNamespace(url="https://www.opinet.co.kr/b/searRgSelect.do")
        )


@pytest.mark.asyncio
async def test_unrelated_response_read_failure_is_not_hidden():
    class FailedResponse(_FakeResponse):
        async def text(self):
            raise RuntimeError("Connection closed")

    response = FailedResponse("https://www.opinet.co.kr/searRgSelect.do", content_type="text/html")
    with pytest.raises(RuntimeError, match="Connection closed"):
        await browser_module._reject_blocked_response(response, page=SimpleNamespace())


class _FakeSearchPage(_FakeEvents):
    def __init__(self, response, records=()):
        self.response = response
        self.records = records
        self.selectors = {}
        self.waits = []

    async def evaluate(self, _script, **_kwargs):
        return 1.0

    def locator(self, selector):
        if selector == "table.tbl_type10 tbody tr":
            return _FakeLocator(values=self.records)
        return self.selectors.setdefault(selector, _FakeLocator(current=""))

    def set_region(self, region):
        self.selectors.update(
            {
                "#SIDO_NM0": _FakeLocator(current=region.sido_value),
                "#SIGUNGU_NM0": _FakeLocator(current=region.sigungu_value),
                "#DONG_NM": _FakeLocator(current=region.dong_value or ""),
            }
        )

    def expect_response(self, _predicate, timeout):
        assert timeout > 0
        return _FakeResponseContext(self.response)

    def get_by_role(self, _role, *, name, exact):
        assert name == "조회"
        assert exact is True
        return _FakeLocator()

    async def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

    async def wait_for_function(self, _script, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_browser_dom_and_search_response_paths(monkeypatch, region):
    source_row = _row()
    values = [source_row.get(field, "") for field in browser_module._OS_POP_FIELDS]
    href = "javascript:fn_osPop(" + ",".join(f"'{value}'" for value in values) + ");"
    records = [
        {"href": href, "title": "", "brand": "", "body_id": "", "prices": [], "labels": []},
        {
            "href": "javascript:fnVolatInfowindow('ILLEGAL','N','')",
            "title": "불법",
            "brand": "S-OIL",
            "body_id": "body1",
            "prices": ["1800", "1700"],
            "labels": ["셀프"],
        },
        {"href": "other", "title": "", "brand": "", "body_id": "", "prices": [], "labels": []},
        "not-a-record",
    ]
    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0),
        query_level="sigungu",
    )

    async def select_without_network(_page, _selector, _value, **_kwargs):
        return None

    monkeypatch.setattr(collector, "_select_value", select_without_network)
    dom_page = _FakeSearchPage(
        _FakeResponse("https://www.opinet.co.kr/searRgSelect.do", payload=None, content_type="text/html"),
        records=records,
    )
    dom_page.set_region(region)
    dom_stations = await collector._read_dom_stations(dom_page, region=region, station_kind="station")
    assert {station.station_id for station in dom_stations} == {"A0000001", "ILLEGAL"}

    json_page = _FakeSearchPage(
        _FakeResponse(
            "https://www.opinet.co.kr/searRgCircleAjax.do",
            payload={"list": [_row()]},
        )
    )
    json_page.set_region(region)
    json_stations = await collector._search_region(json_page, region, station_kind="station")
    assert len(json_stations) == 1
    assert json_page.waits == []

    html_page = _FakeSearchPage(
        _FakeResponse(
            "https://www.opinet.co.kr/searRgSelect.do",
            payload=None,
            content_type="text/html",
        ),
        records=records,
    )
    html_page.set_region(region)
    html_stations = await collector._search_region(html_page, region, station_kind="lpg")
    assert len(html_stations) == 2

    invalid_json_page = _FakeSearchPage(
        _FakeResponse(
            "https://www.opinet.co.kr/searRgSelect.do",
            payload=[_row()],
            content_type="application/json",
        )
    )
    invalid_json_page.set_region(region)
    with pytest.raises(OpinetServerError):
        await collector._search_region(invalid_json_page, region, station_kind="station")


@pytest.mark.asyncio
async def test_browser_rejects_block_page_and_only_malformed_dom(region):
    with pytest.raises(OpinetServerError, match="access-block"):
        await browser_module._reject_blocked_response(
            _FakeResponse(
                "https://www.opinet.co.kr/searRgSelect.do",
                content_type="text/html",
                text_body="<html>CAPTCHA required</html>",
            )
        )

    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0)
    )
    page = _FakeSearchPage(
        _FakeResponse("https://www.opinet.co.kr/searRgSelect.do", content_type="text/html"),
        records=[{"href": "javascript:fn_osPop('broken')"}],
    )
    with pytest.raises(OpinetServerError, match="malformed"):
        await collector._read_dom_stations(page, region=region, station_kind="station")


class _FakeTabPage(_FakeEvents):
    def __init__(self):
        self.tabs = {
            "#OS_BTN": _FakeLocator(attributes={"class": "on", "aria-selected": "true"}),
            "#LPG_BTN": _FakeLocator(attributes={"class": "", "aria-selected": "false"}),
        }

    def locator(self, selector):
        return self.tabs[selector]

    async def evaluate(self, _script, *, arg):
        attributes = self.tabs[arg["selector"]].attributes
        return attributes.get("aria-selected") == "true" or attributes.get("class") == "on"

    def expect_response(self, predicate, timeout):
        assert timeout > 0
        response = _FakeResponse("https://www.opinet.co.kr/searRgSelect.do")
        assert predicate(response)
        return _FakeResponseContext(response)

    async def wait_for_function(self, _script, **_kwargs):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_browser_collect_page_merges_uid_across_query_regions(monkeypatch, region, reverse):
    region = replace(region, dong_value=None, dong_name=None)
    other_region = replace(region, sigungu_value="다른구", sigungu_name="다른구")
    gas = parse_browser_response(
        {"list": [_row(B027_P="1700", B027_DT="", D047_P="99999", D047_DT="")]},
        region=region, station_kind="station", query_level="sigungu",
    )[0]
    lpg = parse_browser_response(
        {"list": [_row(B027_P="99999", B027_DT="", D047_P="99999", D047_DT="", K015_P="1100", LPG_YN="Y")]},
        region=other_region, station_kind="lpg", query_level="sigungu",
    )[0]
    inputs = [gas, lpg] if not reverse else [lpg, gas]
    collector = OpinetBrowserCollector(throttle=OpinetBrowserThrottle(action_min_seconds=0, action_max_seconds=0))

    async def discover(_page):
        return [item.region for item in inputs]

    async def search(_page, query_region, *, station_kind):
        return tuple(item for item in inputs if item.region.sigungu_key == query_region.sigungu_key)

    monkeypatch.setattr(collector, "_discover_regions", discover)
    monkeypatch.setattr(collector, "_search_region", search)
    snapshot = await collector.collect_page(_FakeTabPage())
    assert len(snapshot.stations) == 1
    merged = snapshot.stations[0]
    assert merged.region == inputs[0].region
    assert set(merged.source_kinds) == {"station", "lpg"}
    assert merged.station_type is StationType.BOTH
    assert merged.price_by_product[ProductCode.GASOLINE].price == 1700
    assert merged.price_by_product[ProductCode.LPG].price == 1100
    assert browser_module._station_key(replace(gas, station_id=None)) != browser_module._station_key(replace(lpg, station_id=None))


@pytest.mark.parametrize(
    "left_price,left_time,right_price,right_time,expected_price,expected_time",
    [
        ("1700", "2026-09-18 18:00:00", "1800", "2026-09-18 19:00:00", 1800, "2026-09-18 19:00:00"),
        ("1800", "2026-09-18 19:00:00", "1700", "2026-09-18 18:00:00", 1800, "2026-09-18 19:00:00"),
        ("1700", "", "99999", "2026-09-18 19:00:00", 1700, ""),
        ("1700", "", "1800", "2026-09-18 19:00:00", 1800, "2026-09-18 19:00:00"),
        ("1700", "2026-09-18 19:00:00", "1800", "", 1700, "2026-09-18 19:00:00"),
        ("1700", "", "1800", "", 1700, ""),
        ("1700", "2026-09-18 19:00:00", "1800", "2026-09-18 19:00:00", 1700, "2026-09-18 19:00:00"),
    ],
)
def test_browser_price_merge_keeps_value_and_time_together(region, left_price, left_time, right_price, right_time, expected_price, expected_time):
    station = parse_browser_response(
        {"list": [_row(B027_P=left_price, B027_DT=left_time), _row(B027_P=right_price, B027_DT=right_time)]},
        region=region, station_kind="station", query_level="sigungu",
    )[0]
    price = station.price_by_product[ProductCode.GASOLINE]
    assert price.price == expected_price
    assert price.updated_at == browser_module._parse_provider_datetime(expected_time)


@pytest.mark.asyncio
async def test_browser_collect_page_and_run_forever(monkeypatch, region):
    station = parse_browser_response(
        {"list": [_row()]},
        region=region,
        station_kind="station",
        query_level="sigungu",
    )[0]
    lpg_station = parse_browser_response(
        {"list": [_row()]},
        region=region,
        station_kind="lpg",
        query_level="sigungu",
    )[0]
    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0),
        query_level="sigungu",
    )

    async def discover(_page):
        return [region]

    calls = []

    async def search(_page, _region, *, station_kind):
        calls.append(station_kind)
        return (station if station_kind == "station" else lpg_station,)

    monkeypatch.setattr(collector, "_discover_regions", discover)
    monkeypatch.setattr(collector, "_search_region", search)
    snapshot = await collector.collect_page(_FakeTabPage())
    assert snapshot.source_url == collector.url
    assert snapshot.regions == (region,)
    assert snapshot.stations[0].source_kinds == ("station", "lpg")
    assert calls == ["station", "lpg"]

    limited_collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(
            action_min_seconds=0.0,
            action_max_seconds=0.0,
            max_search_requests=1,
        )
    )
    monkeypatch.setattr(limited_collector, "_discover_regions", discover)
    with pytest.raises(OpinetServerError, match="budget"):
        await limited_collector.collect_page(_FakeTabPage())

    class LoopCollector(OpinetBrowserCollector):
        async def _wait_or_stop(self, _delay, _stop_event):
            return False

        async def collect_once(self):
            return snapshot

    loop_collector = LoopCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0),
    )
    stop_event = asyncio.Event()
    seen = []

    async def sink(value):
        seen.append(value)
        stop_event.set()

    await loop_collector.run_forever(sink, stop_event=stop_event, run_immediately=False)
    assert seen == [snapshot]

    error_collector = LoopCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0),
    )
    error_stop = asyncio.Event()
    errors = []

    async def failing_collect():
        raise RuntimeError("temporary")

    async def handle_error(error):
        errors.append(str(error))
        error_stop.set()

    error_collector.collect_once = failing_collect
    await error_collector.run_forever(
        sink,
        stop_event=error_stop,
        on_error=handle_error,
    )
    assert errors == ["temporary"]


@pytest.mark.asyncio
async def test_browser_wait_and_collect_once_lifecycle(monkeypatch, region):
    page = _FakeSearchPage(
        _FakeResponse("https://www.opinet.co.kr/searRgSelect.do", payload=None, content_type="text/html")
    )
    collector = OpinetBrowserCollector(
        browser_channel="chrome",
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0),
    )
    await collector._pause(page)
    assert page.waits == []
    assert await collector._wait_or_stop(timedelta(0), None) is False

    stopped = asyncio.Event()
    stopped.set()
    assert await collector._wait_or_stop(timedelta(hours=1), stopped) is True

    snapshot = browser_module.OpinetBrowserSnapshot(
        collected_at=datetime.now(),
        source_url=collector.url,
        regions=(region,),
        stations=(),
    )
    entered = []
    closed = []

    class FakePage:
        url = "https://www.opinet.co.kr/searRgSelect.do"

        async def goto(self, url, **kwargs):
            entered.append((url, kwargs))
            return _FakeResponse(url, content_type="text/html")

        async def wait_for_timeout(self, _milliseconds):
            pass

    class FakeContext:
        async def route(self, pattern, handler):
            assert pattern == "**/*"
            assert handler is browser_module._route_collection_resource

        async def new_page(self):
            return FakePage()

        async def close(self):
            closed.append("context")

    class FakeBrowser:
        async def new_context(self):
            return FakeContext()

        async def close(self):
            closed.append("browser")

    class FakeChromium:
        async def launch(self, **options):
            assert options == {"headless": True, "channel": "chrome"}
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightContext:
        async def __aenter__(self):
            return FakePlaywright()

        async def __aexit__(self, _exc_type, _exc, _traceback):
            closed.append("playwright")
            return False

    monkeypatch.setattr(browser_module, "_load_playwright", lambda: lambda: FakePlaywrightContext())
    monkeypatch.setattr(collector, "collect_page", lambda _page: _async_result(snapshot))
    result = await collector.collect_once()
    assert result == snapshot
    assert entered[0][0] == collector.url
    assert entered[0][1]["wait_until"] == "domcontentloaded"
    assert closed == ["context", "browser", "playwright"]


async def _async_result(value):
    return value


@pytest.mark.asyncio
async def test_browser_collector_can_stop_before_first_run():
    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0)
    )
    stop_event = asyncio.Event()
    stop_event.set()
    called = False

    async def sink(_snapshot):
        nonlocal called
        called = True

    await collector.run_forever(sink, stop_event=stop_event)
    assert called is False


def test_region_label_keeps_codes_and_truncates_sanitized_names():
    assert browser_module._region_label("11680") == "11680"
    assert browser_module._region_label(" 경기도 ") == "경기도"
    assert browser_module._region_label("용인시 수지구") == "용인시수지구"
    assert browser_module._region_label("가" * 20) == "가" * 12 + "~"
    assert browser_module._region_label("https://evil.invalid/?certkey=abc") == "redacted"
    assert browser_module._region_label("") == "redacted"
    assert browser_module._region_label(None) == "redacted"
    # 숫자 코드라도 10자를 넘으면 그대로 싣지 않고 절단 규칙을 따른다.
    assert browser_module._region_label("1" * 20) == "1" * 12 + "~"


@pytest.mark.asyncio
async def test_selection_timeout_reports_parent_region():
    class NoResponsePage(_FakeRegionPage):
        def expect_response(self, predicate, timeout):
            raise TimeoutError("secret=value")

    with pytest.raises(OpinetServerError, match="target=경기도/용인시수지구") as raised:
        await OpinetBrowserCollector()._select_value(
            NoResponsePage(), "#SIGUNGU_NM0", "용인시수지구", parent="경기도"
        )
    assert isinstance(raised.value, browser_module._BrowserActionTimeoutError)
    assert not isinstance(raised.value, browser_module._SearchResponseTimeoutError)


@pytest.mark.asyncio
async def test_search_timeout_phase_names_region_and_attempt(region):
    class TimeoutSearchPage(_FakeSearchPage):
        def expect_response(self, _predicate, timeout):
            raise TimeoutError("certkey=secret body")

    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0),
    )
    page = TimeoutSearchPage(_FakeResponse("https://www.opinet.co.kr/searRgCircleAjax.do"))
    page.set_region(region)
    with pytest.raises(OpinetServerError) as raised:
        await collector._search_region(page, region, station_kind="lpg")
    message = str(raised.value)
    assert "phase=search:lpg:region=경기도/용인시수지구/풍덕천동:attempt=1" in message
    assert "cause=TimeoutError" in message
    assert "non-numeric" not in message
    assert "secret" not in message
    assert isinstance(raised.value, browser_module._SearchResponseTimeoutError)


def _scripted_search_collector(monkeypatch, outcomes, *, max_search_requests=10_000):
    """``outcomes``를 차례로 돌려주는 가짜 지역 조회를 붙인 collector."""
    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(
            action_min_seconds=0.0,
            action_max_seconds=0.0,
            max_search_requests=max_search_requests,
        ),
        query_level="sigungu",
    )
    calls = []
    reloads = []

    async def search(_page, region, *, station_kind, attempt=1):
        calls.append((region.sigungu_value, station_kind, attempt))
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def reload(_page, region, *, station_kind):
        reloads.append((len(calls), region.sigungu_value, station_kind))

    monkeypatch.setattr(collector, "_search_region", search)
    monkeypatch.setattr(collector, "_reload_search_page", reload)
    return collector, calls, reloads


def _wrapped_timeout(region_text="region=경기도/용인시수지구:attempt=1"):
    return browser_module._SearchResponseTimeoutError(
        f"Opinet browser action failed: phase=search:station:{region_text}; cause=TimeoutError; events=none"
    )


@pytest.mark.asyncio
async def test_region_search_timeout_is_retried_once_then_succeeds(monkeypatch, region):
    station = parse_browser_response(
        {"list": [_row()]}, region=region, station_kind="station", query_level="sigungu"
    )[0]
    collector, calls, reloads = _scripted_search_collector(monkeypatch, [_wrapped_timeout(), (station,)])

    found, retried = await collector._search_region_with_retry(
        object(), region, station_kind="station", retry_allowed=True
    )

    assert found == (station,)
    assert retried is True
    assert calls == [("용인시수지구", "station", 1), ("용인시수지구", "station", 2)]
    # 재시도 전에 화면을 다시 연다(첫 시도 뒤, 두 번째 시도 전).
    assert reloads == [(1, "용인시수지구", "station")]


@pytest.mark.asyncio
async def test_region_search_second_timeout_fails_with_region_and_attempts(monkeypatch, region):
    collector, calls, _ = _scripted_search_collector(
        monkeypatch, [_wrapped_timeout(), _wrapped_timeout("region=경기도/용인시수지구:attempt=2")]
    )

    with pytest.raises(browser_module._BrowserActionTimeoutError) as raised:
        await collector._search_region_with_retry(object(), region, station_kind="station", retry_allowed=True)

    message = str(raised.value)
    assert "region=경기도/용인시수지구:attempt=2" in message
    assert message.endswith("; attempts=2")
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        OpinetRateLimitError("limited"),
        OpinetAuthError("denied"),
        OpinetServerError("Opinet browser response appears to be an access-block page"),
        ValueError("parse"),
    ],
)
async def test_region_search_non_retryable_errors_are_not_retried(monkeypatch, region, error):
    collector, calls, reloads = _scripted_search_collector(monkeypatch, [error, ()])

    with pytest.raises(type(error)) as raised:
        await collector._search_region_with_retry(object(), region, station_kind="station", retry_allowed=True)

    assert raised.value is error
    assert len(calls) == 1
    assert reloads == []


@pytest.mark.asyncio
async def test_raw_dom_timeout_reloads_before_retry_without_leaking_original_text(monkeypatch, region):
    """결과 DOM 시간 초과도 새 문서에서 재시도하며 원 예외를 노출하지 않는다."""
    raw = TimeoutError("Timeout 60000ms exceeded waiting for certkey=secret")
    collector, calls, reloads = _scripted_search_collector(monkeypatch, [raw, ()])

    found, retried = await collector._search_region_with_retry(object(), region, station_kind="lpg", retry_allowed=True)
    assert found == () and retried
    assert len(calls) == 2
    assert reloads == [(1, region.sigungu_value, "lpg")]


@pytest.mark.asyncio
async def test_selection_stage_timeout_reloads_document_before_retry(region, monkeypatch):
    """지역 선택 응답이 오지 않으면 새 문서를 열고 지역을 처음부터 다시 고른다."""

    class NoSelectResponsePage(_FakeRegionPage):
        def __init__(self):
            super().__init__()
            self.gotos = []

        def expect_response(self, predicate, timeout):
            raise TimeoutError("late dropdown response")

        async def goto(self, url, **_kwargs):
            self.gotos.append(url)
            return _FakeResponse(url)

    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0),
    )
    page = NoSelectResponsePage()
    async def ready(*args, **kwargs):
        pass
    monkeypatch.setattr(collector, "_wait_for_options", ready)
    monkeypatch.setattr(collector, "_activate_tab", ready)
    with pytest.raises(browser_module._BrowserActionTimeoutError) as raised:
        await collector._search_region_with_retry(page, region, station_kind="station", retry_allowed=True)

    assert not isinstance(raised.value, browser_module._SearchResponseTimeoutError)
    assert "phase=select:#SIDO_NM0:target=경기도" in str(raised.value)
    assert page.gotos == [collector.url]


@pytest.mark.asyncio
async def test_search_click_timeout_reloads_page_and_reselects_before_retry(region):
    """조회 응답 시간 초과 뒤에는 화면을 새로 열고 탭·지역을 다시 고른 다음에만 다시 조회한다."""
    region = replace(region, dong_value=None, dong_name=None)

    class RetryPage(_FakeSearchPage):
        def __init__(self):
            super().__init__(_FakeResponse("https://www.opinet.co.kr/searRgCircleAjax.do", payload={"list": [_row()]}))
            self.url = "https://www.opinet.co.kr/searRgSelect.do"
            self.events = []
            self.searches = 0
            self.selectors["#OS_BTN"] = _FakeLocator(attributes={"class": "on", "aria-selected": "true"})
            self.set_region(region)

        def expect_response(self, predicate, timeout):
            self.searches += 1
            self.events.append(f"search{self.searches}")
            if self.searches == 1:
                raise TimeoutError("first search response never arrived")
            return _FakeResponseContext(self.response)

        async def goto(self, url, *, wait_until, timeout):
            assert wait_until == "domcontentloaded" and timeout > 0
            self.events.append("goto")
            # 새 화면은 선택값이 비어 있다. 재시도는 이를 다시 골라야 한다.
            for selector in ("#SIDO_NM0", "#SIGUNGU_NM0", "#DONG_NM"):
                self.selectors[selector] = _FakeLocator(current="")
            return _FakeResponse(url, content_type="text/html", text_body="<html>지역 검색</html>")

    selected = []
    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0),
    )
    page = RetryPage()

    async def select(page_, selector, value, *, parent=None):
        selected.append((page_.events[-1] if page_.events else "start", selector, value))
        page_.selectors[selector] = _FakeLocator(current=value)

    collector._select_value = select

    found, retried = await collector._search_region_with_retry(
        page, region, station_kind="station", retry_allowed=True
    )

    assert retried is True
    assert len(found) == 1
    assert page.events == ["search1", "goto", "search2"]
    # 두 번째 조회 전의 지역 선택은 새로 연 화면(goto 뒤)에서 다시 이뤄진다.
    assert [item for item in selected if item[0] == "goto"] == [
        ("goto", "#SIDO_NM0", "경기도"),
        ("goto", "#SIGUNGU_NM0", "용인시수지구"),
        ("goto", "#DONG_NM", ""),
    ]


@pytest.mark.asyncio
async def test_region_retry_counts_against_search_request_budget(monkeypatch, region):
    first = replace(region, dong_value=None, dong_name=None)
    other = replace(first, sigungu_value="수원시장안구", sigungu_name="수원시장안구")

    async def discover(_page):
        return [first, other]

    # 2개 지역 x 2탭 = 4건 예약, 상한 5 => 재시도 여유 1건.
    collector, calls, _ = _scripted_search_collector(
        monkeypatch,
        [_wrapped_timeout(), (), _wrapped_timeout()],
        max_search_requests=5,
    )
    monkeypatch.setattr(collector, "_discover_regions", discover)

    with pytest.raises(browser_module._BrowserActionTimeoutError) as raised:
        await collector.collect_page(_FakeTabPage())

    # 첫 지역은 한 번 재시도해 성공, 다음 지역의 시간 초과는 상한 때문에 재시도하지 않는다.
    assert calls == [
        ("용인시수지구", "station", 1),
        ("용인시수지구", "station", 2),
        ("수원시장안구", "station", 1),
    ]
    assert str(raised.value).endswith("; attempts=1; retry=budget-exhausted")


@pytest.mark.asyncio
async def test_region_retry_within_budget_completes_collection(monkeypatch, region):
    first = replace(region, dong_value=None, dong_name=None)
    station = parse_browser_response(
        {"list": [_row()]}, region=first, station_kind="station", query_level="sigungu"
    )[0]

    async def discover(_page):
        return [first]

    collector, calls, _ = _scripted_search_collector(
        monkeypatch,
        [_wrapped_timeout(), (station,), _wrapped_timeout(), ()],
    )
    monkeypatch.setattr(collector, "_discover_regions", discover)

    snapshot = await collector.collect_page(_FakeTabPage())

    assert [attempt for *_, attempt in calls] == [1, 2, 1, 2]
    assert [kind for _, kind, _ in calls] == ["station", "station", "lpg", "lpg"]
    assert len(snapshot.stations) == 1
    assert snapshot.region_retry_count == 2


@pytest.mark.asyncio
async def test_browser_collect_page_logs_stage_progress_per_sido(monkeypatch, region, caplog):
    seoul_a = replace(region, sido_value="11", sido_name="서울", dong_value=None, dong_name=None)
    seoul_b = replace(seoul_a, sigungu_value="11680", sigungu_name="강남구")
    busan = replace(seoul_a, sido_value="26", sido_name="부산", sigungu_value="26110", sigungu_name="중구")
    collector = OpinetBrowserCollector(throttle=OpinetBrowserThrottle(action_min_seconds=0, action_max_seconds=0))

    async def discover(_page):
        return [seoul_a, seoul_b, busan]

    async def search(_page, _query_region, *, station_kind):
        return ()

    monkeypatch.setattr(collector, "_discover_regions", discover)
    monkeypatch.setattr(collector, "_search_region", search)
    with caplog.at_level("INFO", logger="opinet.experimental.browser"):
        await collector.collect_page(_FakeTabPage())
    messages = [record.getMessage() for record in caplog.records]
    assert any(m.startswith("Opinet browser region discovery finished: regions=3 query_regions=3") for m in messages)
    progress = [m for m in messages if m.startswith("Opinet browser tab progress:")]
    # 탭마다 시도가 바뀔 때와 마지막에 한 줄씩: 서울(2/3), 부산(3/3).
    assert [m.split(" stations=")[0] for m in progress] == [
        "Opinet browser tab progress: kind=station sido=11 done=2/3",
        "Opinet browser tab progress: kind=station sido=26 done=3/3",
        "Opinet browser tab progress: kind=lpg sido=11 done=2/3",
        "Opinet browser tab progress: kind=lpg sido=26 done=3/3",
    ]
    assert all("elapsed=" in m for m in progress)
    assert sum(m.startswith("Opinet browser tab started:") for m in messages) == 2
    assert sum(m.startswith("Opinet browser tab finished:") for m in messages) == 2
    assert messages[-1].startswith("Opinet browser collection finished: regions=3 stations=0 retries=0 elapsed=")


@pytest.mark.asyncio
async def test_browser_region_discovery_logs_each_sido(caplog):
    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.0), query_level="dong",
    )
    with caplog.at_level("INFO", logger="opinet.experimental.browser"):
        await collector._discover_regions(_FakeRegionPage())
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Opinet browser region discovery progress:")]
    assert len(lines) == 1
    assert lines[0].startswith("Opinet browser region discovery progress: sido=11 done=1/1 sigungu=1 regions=")
