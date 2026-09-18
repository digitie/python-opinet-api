import asyncio
from datetime import datetime, timedelta
import random
from types import SimpleNamespace

import pytest

from opinet.codes import ProductCode, StationType
from opinet.exceptions import OpinetServerError
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


def test_browser_throttle_samples_inside_configured_bounds():
    throttle = OpinetBrowserThrottle(action_min_seconds=0.0, action_max_seconds=0.1)
    rng = random.Random(7)
    action_delay = throttle.sample_action_delay(rng)
    run_delay = throttle.sample_run_interval(rng)

    assert 0.0 <= action_delay <= 0.1
    assert timedelta(hours=10) <= run_delay <= timedelta(hours=12)


def test_browser_throttle_rejects_intervals_outside_load_policy():
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(run_interval_min=timedelta(hours=9))
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(run_interval_max=timedelta(hours=13))
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(action_min_seconds=2.0, action_max_seconds=1.0)
    with pytest.raises(ValueError):
        OpinetBrowserThrottle(run_interval_min=timedelta(hours=11), run_interval_max=timedelta(hours=10))


def test_browser_collector_rejects_non_opinet_url():
    with pytest.raises(ValueError):
        OpinetBrowserCollector(url="https://example.com/collector")
    with pytest.raises(ValueError):
        OpinetBrowserCollector(timeout_ms=0)
    with pytest.raises(ValueError):
        OpinetBrowserCollector(query_level="invalid")


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
    def __init__(self, *, values=None, current="", on_select=None):
        self.values = values or []
        self.current = current
        self.on_select = on_select
        self.selected = []
        self.clicked = 0

    async def evaluate_all(self, _script):
        return self.values

    async def input_value(self):
        return self.current

    async def select_option(self, *, value):
        self.current = value
        self.selected.append(value)
        if self.on_select is not None:
            self.on_select(value)

    async def click(self, **_kwargs):
        self.clicked += 1


class _FakeRegionPage:
    def __init__(self):
        self.current = {"#SIDO_NM0": "", "#SIGUNGU_NM0": "", "#DONG_NM": ""}
        self.locators = {}
        self.waits = []

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


class _FakeResponse:
    def __init__(self, url, payload=None, content_type="application/json"):
        self.url = url
        self.payload = payload
        self.content_type = content_type
        self.request = SimpleNamespace(method="POST")

    async def header_value(self, _name):
        return self.content_type

    async def json(self):
        return self.payload


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


class _FakeSearchPage:
    def __init__(self, response, records=()):
        self.response = response
        self.records = records
        self.selectors = {}
        self.waits = []

    def locator(self, selector):
        if selector == "table.tbl_type10 tbody tr":
            return _FakeLocator(values=self.records)
        return self.selectors.setdefault(selector, _FakeLocator(current=""))

    def expect_response(self, _predicate, timeout):
        assert timeout > 0
        return _FakeResponseContext(self.response)

    def get_by_role(self, _role, *, name, exact):
        assert name == "조회"
        assert exact is True
        return _FakeLocator()

    async def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)


@pytest.mark.asyncio
async def test_browser_dom_and_search_response_paths(region):
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
    dom_page = _FakeSearchPage(
        _FakeResponse("https://www.opinet.co.kr/searRgSelect.do", payload=None, content_type="text/html"),
        records=records,
    )
    dom_stations = await collector._read_dom_stations(dom_page, region=region, station_kind="station")
    assert {station.station_id for station in dom_stations} == {"A0000001", "ILLEGAL"}

    json_page = _FakeSearchPage(
        _FakeResponse(
            "https://www.opinet.co.kr/searRgCircleAjax.do",
            payload={"list": [_row()]},
        )
    )
    json_stations = await collector._search_region(json_page, region, station_kind="station")
    assert len(json_stations) == 1
    assert json_page.waits == [1_000]

    html_page = _FakeSearchPage(
        _FakeResponse(
            "https://www.opinet.co.kr/searRgSelect.do",
            payload=None,
            content_type="text/html",
        ),
        records=records,
    )
    html_stations = await collector._search_region(html_page, region, station_kind="lpg")
    assert len(html_stations) == 2

    invalid_json_page = _FakeSearchPage(
        _FakeResponse(
            "https://www.opinet.co.kr/searRgSelect.do",
            payload=[_row()],
            content_type="application/json",
        )
    )
    with pytest.raises(OpinetServerError):
        await collector._search_region(invalid_json_page, region, station_kind="station")


class _FakeTabPage:
    def __init__(self):
        self.tabs = {"#OS_BTN": _FakeLocator(), "#LPG_BTN": _FakeLocator()}

    def locator(self, selector):
        return self.tabs[selector]


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
        async def goto(self, url, **kwargs):
            entered.append((url, kwargs))

        async def wait_for_timeout(self, _milliseconds):
            pass

    class FakeContext:
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
