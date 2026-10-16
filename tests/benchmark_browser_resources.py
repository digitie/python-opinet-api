"""자기 loopback fixture의 세 쌍을 별도 프로세스로 비교한다. 운영 성능 시험이 아니다."""
import argparse
import asyncio
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import threading
import time

import pytest

from test_browser_resource_fixture import allow_fixture_origin, fixture_server, run_fixture


def memory_sample(root):
    """다른 프로세스의 인자 없이 자기 하위 PID의 RSS/PSS만 읽는다."""
    parents = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            parents[int(entry.name)] = int(fields[1])
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
            pass
    owned = {root}
    while True:
        expanded = owned | {pid for pid, parent in parents.items() if parent in owned}
        if expanded == owned:
            break
        owned = expanded
    rss = pss = 0
    complete = True
    read = 0
    for pid in owned:
        try:
            data = {}
            for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
                key, _, value = line.partition(":")
                if key in {"Rss", "Pss"}:
                    data[key] = int(value.split()[0]) * 1024
            rss += data["Rss"]
            pss += data["Pss"]
            read += 1
        except (FileNotFoundError, ProcessLookupError):
            pass
        except (PermissionError, KeyError):
            complete = False
    return rss, pss, complete, read


def json_value(value):
    """typed 필드·읽기 전용 raw를 손실 없이 JSON 동등성 비교에 사용한다."""
    if is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(type(value).__name__)


async def one(blocked):
    """Playwright/Chromium과 자기 서버만 포함하고 외부 provider에는 연결하지 않는다."""
    stop = threading.Event()
    samples = []

    def observe():
        while not stop.is_set():
            samples.append(memory_sample(os.getpid()))
            stop.wait(0.05)

    with fixture_server() as (origin, counts), pytest.MonkeyPatch.context() as patch:
        allow_fixture_origin(patch, origin)
        reports = []
        thread = threading.Thread(target=observe, daemon=True)
        thread.start()
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = time.process_time_ns()
        started = time.perf_counter_ns()
        try:
            snapshot = await run_fixture(origin, blocked=blocked, reports=reports)
        finally:
            elapsed = time.perf_counter_ns() - started
            python_cpu = time.process_time_ns() - cpu
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            stop.set()
            thread.join(timeout=5)
            assert not thread.is_alive()
        assert samples and all(sample[2] for sample in samples), "memory sample incomplete"
        # 수집 시각·임시 origin 외 typed/raw 전체 출력은 같은 JSON으로 대조한다.
        stable = {"regions": snapshot.regions,
                  "stations": snapshot.stations,
                  "region_retry_count": snapshot.region_retry_count}
        digest = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True,
                                           default=json_value).encode()).hexdigest()
        assert len(reports) == 1 and reports[0]["success"] == 1
        assert counts[("GET", "/searRgSelect.do")] == 1
        assert counts[("POST", "/searRgSelect.do")] == 1
        assert counts[("POST", "/searRgCircleAjax.do")] == 2
        return {
            "blocked": blocked, "output_sha256": digest, "wall_ns": elapsed,
            "python_cpu_ns": python_cpu,
            "reaped_descendant_cpu_ns": round(((after.ru_utime + after.ru_stime) -
                                               (before.ru_utime + before.ru_stime)) * 1e9),
            "sampled_peak_rss_sum_bytes": max(s[0] for s in samples),
            "sampled_peak_pss_sum_bytes": max(s[1] for s in samples),
            "sample_count": len(samples), "max_sampled_owned_processes": max(s[3] for s in samples),
            "server_request_count": sum(counts.values()),
            "server_requests": {method + " " + path: count for (method, path), count in sorted(counts.items())},
            "metrics": dict(reports[0]),
        }


def main():
    """결과 파일은 배타적으로 생성하며 측정 실패를 성공으로 바꾸지 않는다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["default", "blocked"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.case:
        print(json.dumps(asyncio.run(one(args.case == "blocked"))))
        return
    if args.output is None:
        parser.error("--output is required")
    cases = []
    for pair, order in enumerate([(False, True), (True, False), (False, True)], 1):
        for blocked in order:
            result = subprocess.run([sys.executable, __file__, "--case", "blocked" if blocked else "default"],
                                    capture_output=True, text=True, timeout=60)
            if result.returncode:
                with args.output.with_suffix(".failed.json").open("x", encoding="utf-8") as handle:
                    json.dump({"case": blocked, "returncode": result.returncode,
                               "stdout": result.stdout, "stderr": result.stderr, "completed_cases": cases}, handle)
                raise RuntimeError("fixture benchmark failed; separate evidence saved")
            case = json.loads(result.stdout)
            case["pair"] = pair
            cases.append(case)
        assert cases[-1]["output_sha256"] == cases[-2]["output_sha256"]
    assert len({case["output_sha256"] for case in cases}) == 1
    result = {
        "scope": "Linux loopback Chromium fixture only; no external provider",
        "pairs": 3, "cases": cases,
        "limits": [
            "각 case 별도 Python 프로세스, 순서 교대, fixture 1지역/2탭/검색2회",
            "wall은 Playwright 시작/정상종료 포함, fixture 서버 생성/정리 제외",
            "Python CPU는 자기 서버·50ms sampler 포함, descendant CPU는 종료하여 회수한 하위 프로세스 누계",
            "RSS 합은 공유 페이지 중복, PSS 합은 50ms 표본으로 실제 peak 상한이 아님",
            "운영 workload·ARM·지속 브라우저·cold host cache·성능 개선을 입증하지 않음",
        ],
    }
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"pairs": 3, "cases": len(cases), "equivalent": True}))


if __name__ == "__main__":
    main()
