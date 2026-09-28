"""외부 통신 없이 실제 Chromium의 응답 대기 실패를 재현한다."""

import pytest

from opinet.exceptions import OpinetServerError
from opinet.experimental.browser import OpinetBrowserCollector, OpinetBrowserThrottle


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
