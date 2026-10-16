"""자기 loopback 서버와 Chromium만으로 출력·cache·실패 경계를 비교한다."""
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import random
import struct
import threading
from urllib.parse import urlsplit

import pytest

from opinet.experimental import browser as module
from opinet.experimental import OpinetBrowserCollector, OpinetBrowserThrottle
from opinet.exceptions import OpinetServerError, OpinetAuthError, OpinetRateLimitError

HTML = '''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/style.css"><script src="/app.js"></script></head><body>
<img src="/image.bmp"><audio preload="auto" src="/sound.wav"></audio>
<select id="SIDO_NM0"><option value=""></option><option value="01" selected>서울</option></select>
<select id="SIGUNGU_NM0"><option value=""></option><option value="0101" selected>테스트구</option></select>
<select id="DONG_NM"><option value=""></option><option value="010101" selected>테스트동</option></select>
<button id="OS_BTN" class="on" aria-selected="true" onclick="tab('station')">주유소</button>
<button id="LPG_BTN" aria-selected="false" onclick="tab('lpg')">충전소</button>
<a href="#" onclick="window.fixtureSearch();return false">조회</a></body></html>'''
JS = '''let kind='station';
function tab(next){kind=next;for(const [id,k] of [['OS_BTN','station'],['LPG_BTN','lpg']]){
 const b=document.getElementById(id);b.className=k===kind?'on':'';b.setAttribute('aria-selected',k===kind?'true':'false');}
 return fetch('/searRgSelect.do',{method:'POST'}).then(r=>r.text());}
async function fixtureSearch(){await document.fonts.ready;
 await (await fetch('/app.js')).text();await (await fetch('/style.css')).text();
 await (await fetch('/searRgCircleAjax.do',{method:'POST',body:kind})).text();}'''


@contextmanager
def fixture_server(*, search_status=200, blocked=False):
    """외부로 전달하지 않는 bounded fixture 자원만 loopback에서 제공한다."""
    width = 512
    pixels = bytes((0, 100, 200)) * width * width
    bmp = b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
    bmp += struct.pack("<IIIHHIIIIII", 40, width, width, 1, 24, 0, len(pixels), 0, 0, 0, 0) + pixels
    pcm = bytes(44100)
    wav = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 22050, 44100, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    resources = {
        "/app.js": ("text/javascript", JS.encode()),
        "/style.css": ("text/css", b"@font-face{font-family:fixture;src:url('/font.ttf')}body{font-family:fixture}"),
        "/font.ttf": ("font/ttf", font.read_bytes() if font.exists() else b"fixture-font"),
        "/image.bmp": ("image/bmp", bmp),
        "/sound.wav": ("audio/wav", wav),
    }
    counts = Counter()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, content_type, body, cache=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = urlsplit(self.path).path
            with lock:
                counts[("GET", path)] += 1
            if path == "/searRgSelect.do":
                self.respond(200, "text/html", HTML.encode())
            elif path in resources:
                content_type, body = resources[path]
                self.respond(200, content_type, body, cache=True)
            else:
                self.respond(404, "text/plain", b"not-found")

        def do_POST(self):
            size = int(self.headers.get("Content-Length", "0"))
            assert 0 <= size <= 256
            kind = self.rfile.read(size).decode()
            path = urlsplit(self.path).path
            with lock:
                counts[("POST", path)] += 1
            if path == "/searRgSelect.do":
                self.respond(200, "text/html", HTML.encode())
            elif path == "/searRgCircleAjax.do":
                if blocked:
                    self.respond(200, "text/html", b"<html>access denied captcha</html>")
                    return
                row = {"UNI_ID": "fixture-01", "OS_NM": "테스트주유소", "B027_P": "1815",
                       "B027_DT": "2026-09-18 18:00:41", "K015_P": "1040",
                       "K015_DT": "2026-09-18 18:00:52", "GIS_X_COOR": "321217.07850",
                       "GIS_Y_COOR": "525868.57030", "LPG_YN": "Y" if kind == "lpg" else "N",
                       "UNRECOGNIZED_PROVIDER_FIELD": "preserve"}
                self.respond(search_status, "application/json", json.dumps({"list": [row]}).encode())
            else:
                self.respond(404, "text/plain", b"not-found")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port), counts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def allow_fixture_origin(monkeypatch, origin):
    """테스트에서만 정확한 loopback origin을 허용한다. 제품 허용 URL은 바꾸지 않는다."""
    monkeypatch.setattr(module, "_is_allowed_opinet_url", lambda value: (
        urlsplit(value).scheme == "http" and urlsplit(value).netloc == urlsplit(origin).netloc
    ))


async def run_fixture(origin, *, blocked, reports):
    collector = OpinetBrowserCollector(
        url=origin + "/searRgSelect.do", block_visual_resources=blocked, on_metrics=reports.append,
        timeout_ms=3000, rng=random.Random(7),
        throttle=OpinetBrowserThrottle(action_min_seconds=0.01, action_max_seconds=0.01),
    )
    return await collector.collect_once()


async def test_actual_fixture_outputs_critical_requests_and_cache_tradeoff(monkeypatch):
    pytest.importorskip("playwright.async_api")
    snapshots = []
    counters = []
    reports = []
    for blocked in [False, True]:
        with fixture_server() as (origin, counts):
            allow_fixture_origin(monkeypatch, origin)
            local_reports = []
            snapshots.append(await run_fixture(origin, blocked=blocked, reports=local_reports))
            assert len(local_reports) == 1
            counters.append(counts.copy())
            reports.append(local_reports[0])
    assert snapshots[0].regions == snapshots[1].regions
    assert snapshots[0].stations == snapshots[1].stations
    assert snapshots[0].region_retry_count == snapshots[1].region_retry_count == 0
    station = snapshots[1].stations[0]
    assert station.source_kinds == ("station", "lpg")
    assert station.raw["UNRECOGNIZED_PROVIDER_FIELD"] == "preserve"
    assert station.raw["B027_P"] == "1815" and station.lon is not None and station.lat is not None
    for counter in counters:
        assert counter[("GET", "/searRgSelect.do")] == 1
        assert counter[("POST", "/searRgSelect.do")] == 1
        assert counter[("POST", "/searRgCircleAjax.do")] == 2
    assert counters[0][("GET", "/image.bmp")] == 1 and counters[1][("GET", "/image.bmp")] == 0
    assert counters[0][("GET", "/font.ttf")] == 1 and counters[1][("GET", "/font.ttf")] == 0
    # 실제 네트워크 cache는 기본 경로에서 재사용되지만 route를 켜면 JS/CSS를 재전송한다.
    assert counters[0][("GET", "/app.js")] == counters[0][("GET", "/style.css")] == 1
    assert counters[1][("GET", "/app.js")] == counters[1][("GET", "/style.css")] == 3
    assert reports[0]["blocked_resource_count"] == 0 and reports[1]["blocked_resource_count"] >= 2
    for report in reports:
        assert report["success"] == 1 and report["regions"] == report["query_regions"] == report["stations"] == 1
        assert report["discovery_count"] == 1 and report["search_count"] == report["parse_count"] == 2
        assert report["close_count"] == 1 and report["close_elapsed_us"] > 0
        assert report["wait_count"] > 0


@pytest.mark.parametrize("status,blocked,error", [
    (401, False, OpinetAuthError), (403, False, OpinetAuthError),
    (429, False, OpinetRateLimitError), (200, True, OpinetServerError),
])
async def test_actual_resource_option_preserves_denials_without_extra_search(monkeypatch, status, blocked, error):
    pytest.importorskip("playwright.async_api")
    with fixture_server(search_status=status, blocked=blocked) as (origin, counts):
        allow_fixture_origin(monkeypatch, origin)
        reports = []
        with pytest.raises(error):
            await run_fixture(origin, blocked=True, reports=reports)
        assert counts[("POST", "/searRgCircleAjax.do")] == 1
        assert reports[0]["failed"] == 1 and reports[0]["success"] == 0
        assert reports[0]["close_count"] == 1
