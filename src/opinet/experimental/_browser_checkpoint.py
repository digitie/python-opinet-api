"""지역별 수집 결과를 보존하는 단일 작성자 SQLite 체크포인트.

지역 결과와 요청 예산은 각 단계마다 확정한다. 별도 잠금 DB의 트랜잭션은 프로세스
종료 시 OS가 해제하므로 강제 종료 뒤에도 오래된 잠금 파일을 지울 필요가 없다.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..codes import ProductCode, StationType
from ..exceptions import OpinetCheckpointBusyError, OpinetServerError


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    return value


def _stations(payload: str) -> tuple[Any, ...]:
    from .browser import BrowserFuelPrice, BrowserRegion, BrowserStation

    result = []
    for record in json.loads(payload):
        record["region"] = BrowserRegion(**record["region"])
        record["prices"] = tuple(BrowserFuelPrice(
            product_code=ProductCode(price["product_code"]), price=price["price"],
            updated_at=datetime.fromisoformat(price["updated_at"]) if price["updated_at"] else None,
        ) for price in record["prices"])
        record["source_kinds"] = tuple(record["source_kinds"])
        if record["station_type"] is not None:
            record["station_type"] = StationType(record["station_type"])
        result.append(BrowserStation(**record))
    return tuple(result)


class BrowserCheckpoint:
    """호출 예산·지역 목록·지역 결과·완료 시각을 원자적으로 보존한다."""

    def __init__(self, path: Path, *, url: str, query_level: str, max_age: timedelta, reset: bool = True) -> None:
        self.max_age = max_age
        # 같은 파일의 심볼릭 링크 별칭도 같은 잠금을 사용해야 예산 갱신이 유실되지 않는다.
        path = path.resolve()
        if path.exists() and path.stat().st_nlink > 1:
            raise OpinetServerError("Opinet checkpoint must not have hard links")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = sqlite3.connect(str(path) + ".lock", timeout=0)
        try:
            self.lock.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            self.lock.close()
            code = getattr(exc, "sqlite_errorcode", None)
            if code is not None and code & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise OpinetCheckpointBusyError("Opinet checkpoint is already in use") from None
            # 디스크·I/O·파일 형식 오류를 정상 소유권 경합으로 바꾸지 않는다.
            raise
        try:
            self.db = sqlite3.connect(path)
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL, checksum TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, payload TEXT NOT NULL, checksum TEXT NOT NULL)")
            row = self.db.execute("SELECT payload,checksum FROM metadata WHERE id=1").fetchone()
            if row and hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
                raise OpinetServerError("Opinet checkpoint metadata checksum mismatch")
            self.meta: dict[str, Any] = json.loads(row[0]) if row else {}
            if row and self.meta.get("version") != 1:
                raise OpinetServerError("unsupported Opinet checkpoint version")
            now = datetime.now(timezone.utc)
            valid = (self.meta.get("version") == 1 and self.meta.get("url") == url
                     and self.meta.get("query_level") == query_level
                     and not self.meta.get("acknowledged")
                     and timedelta(0) <= now - datetime.fromisoformat(self.meta["started_at"]) < max_age)
            self.usable = valid
            if not valid and reset:
                self.meta = {"version": 1, "url": url, "query_level": query_level,
                             "started_at": now.isoformat(), "requests": 0, "regions": None,
                             "completed_at": None, "acknowledged": False, "retry_count": 0}
                with self.db:
                    self.db.execute("DELETE FROM results")
                    self._save_meta()
                self.usable = True
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.lock.close()
            raise

    def close(self) -> None:
        self.db.close()
        self.lock.close()

    def _save_meta(self) -> None:
        payload = json.dumps(self.meta, sort_keys=True, allow_nan=False)
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES (1, ?, ?)",
                        (payload, hashlib.sha256(payload.encode()).hexdigest()))

    def save_regions(self, regions: list[Any]) -> None:
        self.meta["regions"] = _encode(regions)
        with self.db:
            self._save_meta()

    def regions(self) -> list[Any] | None:
        from .browser import BrowserRegion

        data = self.meta["regions"]
        return [BrowserRegion(**region) for region in data] if data is not None else None

    def reserve_request(self, limit: int) -> None:
        self._check_age()
        if self.meta["requests"] >= limit:
            raise OpinetServerError("Opinet checkpoint search request budget exhausted")
        self.meta["requests"] += 1
        with self.db:
            self._save_meta()

    @staticmethod
    def key(kind: str, region: Any) -> str:
        return json.dumps([kind, region.sido_value, region.sigungu_value, region.dong_value])

    def load(self, key: str) -> tuple[Any, ...] | None:
        row = self.db.execute("SELECT payload,checksum FROM results WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise OpinetServerError("Opinet checkpoint region checksum mismatch")
        return _stations(row[0])

    def save(self, key: str, stations: tuple[Any, ...], *, retried: bool = False) -> None:
        payload = json.dumps(_encode(stations), ensure_ascii=False, allow_nan=False)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO results VALUES (?,?,?)",
                            (key, payload, hashlib.sha256(payload.encode()).hexdigest()))
            self.meta["retry_count"] += int(retried)
            self._save_meta()

    def complete(self) -> datetime:
        self._check_age()
        if self.meta["completed_at"] is None:
            self.meta["completed_at"] = datetime.now(timezone.utc).isoformat()
            with self.db:
                self._save_meta()
        return datetime.fromisoformat(self.meta["completed_at"])

    def _check_age(self) -> None:
        if datetime.now(timezone.utc) - datetime.fromisoformat(self.meta["started_at"]) >= self.max_age:
            raise OpinetServerError("Opinet checkpoint expired during collection")

    def acknowledge(self, collected_at: datetime) -> None:
        if self.meta["completed_at"] and datetime.fromisoformat(self.meta["completed_at"]) == collected_at:
            self.meta["acknowledged"] = True
            with self.db:
                self._save_meta()
