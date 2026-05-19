"""오피넷 테스트 공용 pytest 헬퍼."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from opinet import OpinetClient

OPINET_BASE_URL = "https://www.opinet.co.kr/api/"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip().lstrip("\ufeff"), value.strip().strip("\"'"))


def _load_local_env() -> None:
    """런타임 의존성을 추가하지 않고 ignore된 로컬 .env 값을 읽는다."""
    _load_env_file(PROJECT_ROOT / ".env")
    _load_env_file(PROJECT_ROOT.parent / "python-vworld-api" / ".env")


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


class MockOpinetApi:
    def __init__(self, router: respx.MockRouter) -> None:
        self._router = router

    @property
    def calls(self):
        return self._router.calls

    def add(
        self,
        endpoint_or_url: str,
        *,
        json: Any | None = None,
        body: str | bytes | Exception | None = None,
        status: int = 200,
        content_type: str | None = None,
    ):
        url = endpoint_or_url if endpoint_or_url.startswith("http") else OPINET_BASE_URL + endpoint_or_url
        route = self._router.get(url__regex=rf"^{re.escape(url)}(?:\?.*)?$")
        if isinstance(body, Exception):
            return route.mock(side_effect=body)
        headers = {"content-type": content_type} if content_type else None
        if json is not None:
            response = httpx.Response(status, json=json, headers=headers)
        elif isinstance(body, bytes):
            response = httpx.Response(status, content=body, headers=headers)
        else:
            response = httpx.Response(status, text=body or "", headers=headers)
        return route.mock(return_value=response)

    def reset(self) -> None:
        self._router.reset()

    def query(self, index: int = 0) -> dict[str, list[str]]:
        return parse_qs(urlparse(str(self.calls[index].request.url)).query)


@pytest.fixture
def mock_opinet(respx_mock: respx.MockRouter) -> MockOpinetApi:
    return MockOpinetApi(respx_mock)


@pytest.fixture(scope="session")
def live_api_key() -> str:
    key = os.getenv("OPINET_API_KEY")
    if not key:
        pytest.skip("OPINET_API_KEY is not set; live Opinet tests are skipped")
    return key


@pytest.fixture(scope="session")
def live_client(live_api_key: str) -> OpinetClient:
    return OpinetClient(api_key=live_api_key, retry_backoff=0)
