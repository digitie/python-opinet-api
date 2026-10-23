"""프로세스 간 지역 재개·저장 재전달과 호출 예산을 검증한다."""
from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from opinet.experimental import browser as module
from opinet.experimental._browser_checkpoint import BrowserCheckpoint
from opinet.exceptions import OpinetServerError
from test_experimental_browser import _FakeTabPage, _row, _scripted_search_collector, region


@pytest.mark.asyncio
async def test_resume_skips_completed_regions_and_replays_complete_without_browser(tmp_path, monkeypatch, region):
    first = replace(region, dong_value=None, dong_name=None)
    second = replace(first, sigungu_value="other")
    station = module.parse_browser_response({"list": [_row()]}, region=first,
                                          station_kind="station", query_level="sigungu")[0]
    path = tmp_path / "progress.sqlite3"
    collector, calls, _ = _scripted_search_collector(monkeypatch, [(station,), RuntimeError("process stopped")])
    collector.checkpoint_path = path
    monkeypatch.setattr(collector, "_discover_regions", AsyncMock(return_value=[first, second]))
    with pytest.raises(RuntimeError, match="stopped"):
        await collector.collect_page(_FakeTabPage())
    assert len(calls) == 2

    # 새 collector는 지역 탐색과 첫 성공 지역을 모두 건너뛴다. 정상 빈 결과도 완료로 보존한다.
    resumed, calls, _ = _scripted_search_collector(monkeypatch, [(), (), ()])
    resumed.checkpoint_path = path
    discovery = AsyncMock(side_effect=AssertionError("must not rediscover"))
    monkeypatch.setattr(resumed, "_discover_regions", discovery)
    snapshot = await resumed.collect_page(_FakeTabPage())
    assert len(calls) == 3 and snapshot.stations == (station,)
    discovery.assert_not_called()

    monkeypatch.setattr(module, "_load_playwright", lambda: pytest.fail("must not launch browser"))
    replay = await module.OpinetBrowserCollector(checkpoint_path=path).collect_once()
    assert replay.collected_at == snapshot.collected_at
    assert replay.stations == snapshot.stations
    assert await resumed.pending_snapshot() == replay
    resumed.acknowledge_snapshot(replay)
    assert await resumed.pending_snapshot() is None


def test_checkpoint_single_writer_and_request_budget_survive_reopen(tmp_path):
    path = tmp_path / "progress.sqlite3"
    kwargs = dict(url="https://www.opinet.co.kr/searRgSelect.do", query_level="sigungu", max_age=timedelta(hours=12))
    checkpoint = BrowserCheckpoint(path, **kwargs)
    try:
        checkpoint.reserve_request(1)
        with pytest.raises(OpinetServerError, match="already in use"):
            BrowserCheckpoint(path, **kwargs)
    finally:
        checkpoint.close()
    checkpoint = BrowserCheckpoint(path, **kwargs)
    try:
        with pytest.raises(OpinetServerError, match="budget exhausted"):
            checkpoint.reserve_request(1)
    finally:
        checkpoint.close()


@pytest.mark.asyncio
async def test_completed_checkpoint_corruption_fails_before_network(tmp_path, monkeypatch, region):
    import sqlite3
    path = tmp_path / "progress.sqlite3"
    collector, _, _ = _scripted_search_collector(monkeypatch, [(), ()])
    collector.checkpoint_path = path
    monkeypatch.setattr(collector, "_discover_regions", AsyncMock(return_value=[region]))
    await collector.collect_page(_FakeTabPage())
    with sqlite3.connect(path) as db:
        db.execute("UPDATE results SET payload='[]x'")
    with pytest.raises(OpinetServerError, match="checksum"):
        await collector.pending_snapshot()


def test_process_death_releases_lock_and_preserves_request_budget(tmp_path):
    import subprocess
    import sys
    path = tmp_path / "progress.sqlite3"
    script = """
import os,sys
from datetime import timedelta
from pathlib import Path
from opinet.experimental._browser_checkpoint import BrowserCheckpoint
checkpoint=BrowserCheckpoint(Path(sys.argv[1]),url='https://www.opinet.co.kr/searRgSelect.do',query_level='sigungu',max_age=timedelta(hours=12))
checkpoint.reserve_request(10)
os._exit(7)
"""
    assert subprocess.run([sys.executable, "-c", script, str(path)], timeout=15).returncode == 7
    checkpoint = BrowserCheckpoint(path, url="https://www.opinet.co.kr/searRgSelect.do",
                                   query_level="sigungu", max_age=timedelta(hours=12))
    try:
        assert checkpoint.meta["requests"] == 1
    finally:
        checkpoint.close()
