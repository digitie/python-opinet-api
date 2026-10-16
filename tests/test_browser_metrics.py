"""브라우저 자원 정책과 정수 계수를 외부 통신 없이 검증한다."""
import asyncio
from collections import defaultdict

import pytest

from opinet.exceptions import OpinetServerError
from opinet.experimental import OpinetBrowserCollector


class Page:
    """핸들러 소유권과 route 동작만 기록하는 페이지다."""
    def __init__(self):
        self.events = defaultdict(list)
        self.routes = []
        self.removed = []

    def on(self, event, handler):
        self.events[event].append(handler)

    def remove_listener(self, event, handler):
        self.events[event].remove(handler)

    async def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    async def unroute(self, pattern, handler):
        self.routes.remove((pattern, handler))
        self.removed.append((pattern, handler))


class Request:
    def __init__(self, kind):
        self.resource_type = kind

    @property
    def url(self):
        raise AssertionError("metrics must never inspect a URL")


class Route:
    def __init__(self, kind):
        self.request = Request(kind)
        self.action = None

    async def abort(self):
        self.action = "abort"

    async def fallback(self):
        self.action = "fallback"


@pytest.mark.parametrize("value", [None, 0, 1, "false", [], {}])
def test_visual_policy_requires_explicit_bool(value):
    with pytest.raises(ValueError, match="bool"):
        OpinetBrowserCollector(block_visual_resources=value)


def test_metrics_callback_must_be_callable():
    with pytest.raises(ValueError, match="callable"):
        OpinetBrowserCollector(on_metrics=123)


async def test_default_scope_does_not_touch_page_or_routing():
    async with OpinetBrowserCollector()._page_scope(object()):
        pass


async def test_visual_policy_is_allowlisted_and_preserves_other_routes():
    reports = []
    collector = OpinetBrowserCollector(block_visual_resources=True, on_metrics=reports.append)
    page = Page()
    existing = lambda route: None
    page.routes.append(("**/fixture", existing))
    with collector._metric_session():
        async with collector._page_scope(page):
            own = page.routes[-1][1]
            async with collector._page_scope(page):
                assert len(page.routes) == 2
            for kind in ["image", "font", "media", "document", "script", "stylesheet", "xhr", "fetch", "other"]:
                route = Route(kind)
                for handler in page.events["request"]:
                    handler(route.request)
                await own(route)
                assert route.action == ("abort" if kind in {"image", "font", "media"} else "fallback")
    assert page.routes == [("**/fixture", existing)]
    assert all(not handlers for handlers in page.events.values())
    assert len(page.removed) == len(reports) == 1
    report = reports[0]
    assert report["request_count"] == 9
    assert report["blocked_resource_count"] == 3
    assert report["image_requests"] == report["font_requests"] == report["media_requests"] == 1
    assert report["success"] == 1
    assert len(report) == 32
    assert all(type(v) is int and v >= 0 for v in report.values())
    with pytest.raises(TypeError):
        report["request_count"] = 0


async def test_metrics_observation_alone_does_not_install_cache_disabling_route():
    reports = []
    page = Page()
    collector = OpinetBrowserCollector(on_metrics=reports.append)
    with collector._metric_session():
        async with collector._page_scope(page):
            assert page.routes == []
            for handler in page.events["requestfailed"]:
                handler(Request("xhr"))
    assert reports[0]["request_failed_count"] == 1


async def test_sessions_isolate_same_collector_concurrent_calls():
    reports = []
    collector = OpinetBrowserCollector(on_metrics=reports.append)
    async def one(count):
        with collector._metric_session():
            with collector._metric_session():
                collector._metrics()["stations"] = count
                await asyncio.sleep(0)
                assert collector._metrics()["stations"] == count
    await asyncio.gather(one(1), one(2))
    assert sorted(r["stations"] for r in reports) == [1, 2]
    assert collector._metrics() is None


@pytest.mark.parametrize("error", [OpinetServerError("original"), asyncio.CancelledError()])
async def test_error_and_cancellation_preserve_route_cleanup_and_report(error):
    reports = []
    collector = OpinetBrowserCollector(block_visual_resources=True, on_metrics=reports.append)
    page = Page()
    with pytest.raises(type(error)) as raised:
        with collector._metric_session():
            async with collector._page_scope(page):
                with collector._measure("search"):
                    raise error
    assert raised.value is error
    assert page.routes == [] and all(not v for v in page.events.values())
    assert len(reports) == 1 and reports[0]["success"] == 0
    assert reports[0]["cancelled"] == isinstance(error, asyncio.CancelledError)
    assert reports[0]["failed"] == isinstance(error, OpinetServerError)
    assert reports[0]["search_count"] == 1


def test_metrics_callback_failure_does_not_mask_provider_error_or_log_content(caplog):
    def callback(report):
        raise RuntimeError("secret-url-and-body")
    collector = OpinetBrowserCollector(on_metrics=callback)
    error = OpinetServerError("original")
    with pytest.raises(OpinetServerError) as raised:
        with collector._metric_session():
            raise error
    assert raised.value is error and collector._metrics() is None
    assert "secret-url-and-body" not in caplog.text


def test_other_collectors_do_not_steal_parent_metrics():
    first, second = [], []
    a = OpinetBrowserCollector(on_metrics=first.append)
    b = OpinetBrowserCollector(on_metrics=second.append)
    with a._metric_session():
        a._metrics()["stations"] = 7
        with b._metric_session():
            b._metrics()["stations"] = 3
        assert a._metrics()["stations"] == 7
    assert first[0]["stations"] == 7 and second[0]["stations"] == 3


async def test_real_task_cancellation_cleans_only_own_handlers():
    reports = []
    collector = OpinetBrowserCollector(block_visual_resources=True, on_metrics=reports.append)
    page = Page()
    entered = asyncio.Event()
    async def collect():
        with collector._metric_session():
            async with collector._page_scope(page):
                entered.set()
                await asyncio.Event().wait()
    task = asyncio.create_task(collect())
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert page.routes == [] and all(not v for v in page.events.values())
    assert reports[0]["cancelled"] == 1 and reports[0]["success"] == 0


async def test_other_collector_same_page_keeps_its_own_resource_policy():
    a = OpinetBrowserCollector(on_metrics=lambda report: None)
    b = OpinetBrowserCollector(block_visual_resources=True)
    page = Page()
    with a._metric_session():
        async with a._page_scope(page):
            assert not page.routes
            async with b._page_scope(page):
                route = Route("image")
                await page.routes[0][1](route)
                assert route.action == "abort"
            assert not page.routes and len(page.events["request"]) == 1
    assert all(not v for v in page.events.values())
