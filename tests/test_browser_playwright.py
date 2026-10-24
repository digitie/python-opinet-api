"""외부 통신 없이 실제 Chromium의 응답 대기 실패를 재현한다."""

import asyncio
import html
import json

import pytest

from opinet.exceptions import OpinetServerError
from opinet.experimental.browser import BrowserRegion, OpinetBrowserCollector, OpinetBrowserThrottle, _OS_POP_FIELDS


@pytest.mark.asyncio
async def test_tab_get_response_mismatch_reports_phase_without_retry():
    api = pytest.importorskip("playwright.async_api", reason="browser extra가 필요한 검증")
    requests = []
    async with api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()

            async def respond(route):
                requests.append(route.request.method)
                await route.fulfill(content_type="text/html", body=(
                    '<button id="LPG_BTN" onclick="fetch(\'/searRgSelect.do?certkey=secret\')">LPG</button>'
                ))

            await page.route("**/*", respond)
            await page.goto("https://www.opinet.co.kr/searRgSelect.do")
            collector = OpinetBrowserCollector(
                timeout_ms=500,
                throttle=OpinetBrowserThrottle(action_min_seconds=0, action_max_seconds=0),
            )
            with pytest.raises(OpinetServerError) as raised:
                await collector._activate_tab(page, station_kind="lpg", selector="#LPG_BTN")
            message = str(raised.value)
            assert "phase=tab:lpg" in message
            assert "cause=TimeoutError" in message
            assert "response:GET:searRgSelect.do:200" in message
            assert "secret" not in message
            assert requests == ["GET", "GET"]
        finally:
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["server", "dynamic", "empty", "wrong-region", "wrong-tab", "empty-wrong-region", "empty-wrong-tab"])
async def test_html_results_wait_for_data_instead_of_unrelated_image(mode):
    api = pytest.importorskip("playwright.async_api", reason="browser extra가 필요한 검증")
    region = BrowserRegion(sido_value="11", sido_name="서울", sigungu_value="110", sigungu_name="테스트구")
    row = {"UNI_ID": "A0000001", "OS_NM": "테스트", "B027_P": "1800", "GIS_X_COOR": "321217", "GIS_Y_COOR": "525868"}
    href = "javascript:fn_osPop(" + ",".join("'" + row.get(name, "") + "'" for name in _OS_POP_FIELDS) + ");"
    link = '<tr><td><a href="' + html.escape(href, quote=True) + '">테스트</a></td></tr>'

    def document(*, result=False):
        wrong_region = result and mode.endswith("wrong-region")
        controls = ('<select id="SIDO_NM0"><option value="11">서울</option></select>'
                    '<select id="SIGUNGU_NM0"><option value="' + ("999" if wrong_region else "110") + '">구</option></select>'
                    '<select id="DONG_NM"><option value="">전체</option></select>'
                    '<button id="OS_BTN" class="' + ("" if result and mode.endswith("wrong-tab") else "on") + '">주유소</button>')
        body = link if result and mode != "dynamic" and not mode.startswith("empty") else ""
        dynamic = ('<script>window.addEventListener("load", () => { document.querySelector("tbody").innerHTML = '
                   + json.dumps(link) + '; });</script>') if result and mode == "dynamic" else ""
        return (controls + '<form method="post" action="/searRgSelect.do"><a href="#" '
                'onclick="this.closest(\'form\').submit(); return false;">조회</a></form>'
                '<table class="tbl_type10"><tbody>' + body + '</tbody></table>' + dynamic
                + ('<img src="/slow-image.png">' if result else ""))

    release_image = asyncio.Event()
    image_requested = asyncio.Event()
    async with api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()

            async def respond(route):
                if route.request.url.endswith("/slow-image.png"):
                    image_requested.set()
                    await release_image.wait()
                    await route.fulfill(content_type="image/png", body=b"")
                else:
                    await route.fulfill(content_type="text/html; charset=utf-8", body=document(result=route.request.method == "POST"))

            await page.route("**/*", respond)
            await page.goto("https://www.opinet.co.kr/searRgSelect.do")
            collector = OpinetBrowserCollector(timeout_ms=1500)
            task = asyncio.create_task(collector._search_region(page, region, station_kind="station"))
            try:
                await asyncio.wait_for(image_requested.wait(), 3)
            except TimeoutError:
                if task.done():
                    task.result()
                raise
            if mode == "server":
                stations = await asyncio.wait_for(task, 1)
                assert [station.station_id for station in stations] == ["A0000001"]
                assert stations[0].price_by_product
                assert await page.evaluate("document.readyState") == "interactive"
            elif "wrong" in mode:
                release_image.set()
                with pytest.raises(Exception, match="Timeout"):
                    await task
            else:
                # 빈 표를 DCL 시점에 정상 결과로 확정하면 동적 결과를 잃는다.
                await asyncio.sleep(0.1)
                assert not task.done()
                release_image.set()
                stations = await asyncio.wait_for(task, 2)
                assert len(stations) == (1 if mode == "dynamic" else 0)
        finally:
            release_image.set()
            await browser.close()
