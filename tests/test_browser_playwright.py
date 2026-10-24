"""외부 통신 없이 실제 Chromium의 응답 대기 실패를 재현한다."""

import asyncio
import html
import json
from urllib.parse import parse_qs

import pytest

from opinet.exceptions import OpinetServerError
from opinet.experimental.browser import BrowserRegion, OpinetBrowserCollector, OpinetBrowserThrottle, _OS_POP_FIELDS, _route_collection_resource


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
@pytest.mark.parametrize("block_visual", [False, True])
@pytest.mark.parametrize("mode", ["server", "dynamic", "mixed", "empty", "wrong-region", "wrong-tab", "empty-wrong-region", "empty-wrong-tab"])
async def test_html_results_wait_for_data_instead_of_unrelated_image(mode, block_visual):
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
        extra_link = link.replace("A0000001", "A0000002")
        dynamic = ('<script>window.addEventListener("load", () => { document.querySelector("tbody").innerHTML += '
                   + json.dumps(extra_link if mode == "mixed" else link) + '; });</script>') if result and mode in ("dynamic", "mixed") else ""
        return (controls + '<form method="post" action="/searRgSelect.do"><a href="#" '
                'onclick="this.closest(\'form\').submit(); return false;">조회</a></form>'
                '<table class="tbl_type10"><tbody>' + body + '</tbody></table>' + dynamic
                + ('<img src="/slow-image.png">' if result else ""))

    release_image = asyncio.Event()
    image_requested = asyncio.Event()
    async with api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context()
            if block_visual:
                await context.route("**/*", _route_collection_resource)
            page = await context.new_page()

            async def respond(route):
                if route.request.url.endswith("/slow-image.png"):
                    image_requested.set()
                    if block_visual:
                        await route.fallback()
                        return
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
            if not block_visual:
                await asyncio.sleep(0.1)
                assert not task.done()
                release_image.set()
            if "wrong" in mode:
                with pytest.raises(Exception, match="Timeout"):
                    await task
            else:
                stations = await asyncio.wait_for(task, 2)
                expected = 0 if mode == "empty" else (2 if mode == "mixed" else 1)
                assert len(stations) == expected
                assert await page.evaluate("document.readyState") == "complete"
                assert release_image.is_set() is not block_visual
        finally:
            release_image.set()
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["late", "replace", "clear-late", "empty", "empty-noop"])
async def test_region_selection_waits_for_actual_child_options(mode):
    api = pytest.importorskip("playwright.async_api", reason="browser extra가 필요한 검증")
    empty = mode.startswith("empty")
    parent = "SIDO_NM0"
    child = "SIGUNGU_NM0"
    endpoint = "sigunguGisSelect.do"
    options = '<option value="">전체</option>' if empty else '<option value="220">220</option>'
    apply_options = "" if mode == "empty-noop" else (
        "document.getElementById(child).outerHTML = '<select id=\"' + child + '\">' + options + '</select>';"
        if mode == "replace" else "document.getElementById(child).innerHTML = options;"
    )
    clear = "document.getElementById(child).innerHTML = '<option value=\"\">전체</option>';" if mode in ("clear-late", "empty-noop") else ""
    source = ('<meta charset="utf-8"><select id="' + parent + '"><option value="11">이전</option>'
              '<option value="22">다음</option></select><select id="' + child + '">'
              '<option value="110">이전 지역</option></select><script>'
              'const child = ' + json.dumps(child) + '; const options = ' + json.dumps(options) + ';'
              'document.getElementById(' + json.dumps(parent) + ').onchange = () => { ' + clear
              + 'fetch("/common/' + endpoint + '", {method:"POST"}).then(r=>r.json()).then(()=>setTimeout(()=>{'
              + apply_options + '}, 200)); }; </script>')
    async with api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            async def respond(route):
                if route.request.method == "POST":
                    await route.fulfill(content_type="application/json", body=json.dumps({"result": [] if empty else [{"SIGUNGU_NM": "220"}]}))
                else:
                    await route.fulfill(content_type="text/html; charset=utf-8", body=source)
            await page.route("**/*", respond)
            await page.goto("https://www.opinet.co.kr/searRgSelect.do")
            collector = OpinetBrowserCollector(timeout_ms=700, query_level="dong")
            await collector._select_value(page, "#" + parent, "22")
            assert await collector._read_options(page, "#" + child) == (() if empty else (("220", "220"),))
        finally:
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,filtered,same_region", [("station", False, False), ("lpg", False, False),
                                                      ("station", True, False), ("station", False, True)])
async def test_sigungu_auto_query_is_reused_only_for_the_same_unfiltered_request(kind, filtered, same_region):
    api = pytest.importorskip("playwright.async_api", reason="browser extra가 필요한 검증")
    region = BrowserRegion(sido_value="11", sido_name="서울", sigungu_value="110", sigungu_name="구")
    row = {"UNI_ID": "A0000001", "OS_NM": "테스트", "B027_P": "1800", "GIS_X_COOR": "321217", "GIS_Y_COOR": "525868"}
    href = "javascript:fn_osPop(" + ",".join("'" + row.get(name, "") + "'" for name in _OS_POP_FIELDS) + ");"
    posts = []
    def document(fields):
        hidden = {"SIDO_NM": "11", "SIGUNGU_NM": fields.get("SIGUNGU_NM0", "0"), "SEARCH_MOD": "addr",
                  "BTN_DIV": "lpg_btn" if kind == "lpg" else "os_btn", "LPG_YN": "Y" if kind == "lpg" else ""}
        return ('<meta charset="utf-8"><form method="POST" action="/searRgSelect.do">'
                + ''.join('<input type="hidden" id="' + key + '" name="' + key + '" value="' + value + '">' for key, value in hidden.items())
                + '<input id="OS_NM" name="OS_NM" value="' + fields.get("OS_NM", "") + '">'
                + '<input id="OS_ADDR" name="OS_ADDR" value="">'
                + '<select id="SIDO_NM0" name="SIDO_NM0"><option value="11">서울</option></select>'
                + '<select id="SIGUNGU_NM0" name="SIGUNGU_NM0" onchange="document.getElementById(\'SIGUNGU_NM\').value=this.value;this.form.submit()">'
                + '<option value="' + fields.get("SIGUNGU_NM0", "0") + '">현재</option><option value="110">구</option></select>'
                + '<select id="DONG_NM" name="DONG_NM"><option value="">전체</option></select>'
                + '<ul><li class="sel"><a id="' + ("LPG_BTN" if kind == "lpg" else "OS_BTN") + '">탭</a></li></ul>'
                + '<a href="#" onclick="document.getElementById(\'OS_NM\').value=\'\';document.getElementById(\'OS_ADDR\').value=\'\';this.closest(\'form\').submit();return false;">조회</a>'
                + '<table class="tbl_type10"><tbody><tr><td><a href="' + html.escape(href, quote=True) + '">가격</a></td></tr></tbody></table></form>')
    async with api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            async def respond(route):
                fields = {"SIGUNGU_NM0": "110" if same_region else "0", "OS_NM": "필터" if filtered else ""}
                if route.request.method == "POST":
                    parsed = parse_qs(route.request.post_data or "", keep_blank_values=True)
                    posts.append(parsed)
                    fields = {key: values[0] for key, values in parsed.items()}
                await route.fulfill(content_type="text/html; charset=utf-8", body=document(fields))
            await page.route("**/*", respond)
            await page.goto("https://www.opinet.co.kr/searRgSelect.do")
            stations = await OpinetBrowserCollector(timeout_ms=1500)._search_region(page, region, station_kind=kind)
            assert [station.station_id for station in stations] == ["A0000001"]
            assert len(posts) == (2 if filtered and not same_region else 1)
            assert posts[-1]["OS_NM"] == [""]
            assert posts[-1]["SIGUNGU_NM0"] == ["110"]
        finally:
            await browser.close()
