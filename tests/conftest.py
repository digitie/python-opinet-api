"""오피넷 테스트 공용 pytest 헬퍼."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from opinet import OpinetClient

OPINET_BASE_URL = "https://www.opinet.co.kr/api/"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_local_env() -> None:
    """런타임 의존성을 추가하지 않고 ignore된 로컬 .env 값을 읽는다."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip().lstrip("\ufeff"), value.strip().strip("\"'"))


_load_local_env()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-live", action="store_true", default=False, help="run live Opinet API tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-live"):
        return
    skip_live = pytest.mark.skip(reason="need --run-live option to run live Opinet API tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def load_fixture() -> Any:
    def _load(name: str) -> Any:
        path = Path(__file__).parent / "fixtures" / name
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    return _load


@pytest.fixture
def client() -> OpinetClient:
    return OpinetClient(api_key="test-key", retry_backoff=0)


@pytest.fixture(scope="session")
def live_api_key() -> str:
    key = os.getenv("OPINET_API_KEY")
    if not key:
        pytest.skip("OPINET_API_KEY is not set; live Opinet tests are skipped")
    return key


@pytest.fixture(scope="session")
def live_client(live_api_key: str) -> OpinetClient:
    return OpinetClient(api_key=live_api_key, retry_backoff=0)
