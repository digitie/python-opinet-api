"""Opinet API HTTP helpers built on httpx."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import sleep
from typing import Any, Protocol

from .config import DEFAULT_BASE_URL
from .exceptions import OpinetAuthError, OpinetNetworkError, OpinetRateLimitError, OpinetServerError


def _load_httpx() -> Any:
    try:
        import httpx
    except ModuleNotFoundError as exc:
        raise OpinetNetworkError("httpx is required; install the project dependencies first") from exc
    return httpx


def _new_sync_client() -> Any:
    return _load_httpx().Client(follow_redirects=True)


def _new_async_client() -> Any:
    return _load_httpx().AsyncClient(follow_redirects=True)


def _is_retryable_transport_error(exc: Exception) -> bool:
    httpx = _load_httpx()
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError))


def _raise_for_response(response: Any) -> dict[str, Any]:
    if response.status_code in (401, 403):
        raise OpinetAuthError(f"HTTP {response.status_code}: {response.text[:200]}")
    if response.status_code == 429:
        raise OpinetRateLimitError(response.text[:200])
    if 500 <= response.status_code < 600:
        raise OpinetServerError(f"HTTP {response.status_code}: {response.text[:200]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise OpinetServerError(f"JSON parse failure: {exc}") from exc

    result = data.get("RESULT")
    if not isinstance(result, dict):
        text = str(result)
        lowered = text.lower()
        if "invalid" in lowered:
            raise OpinetAuthError(text[:200])
        if "limit" in lowered or "초과" in text:
            raise OpinetRateLimitError(text[:200])
        raise OpinetServerError(f"Unexpected RESULT: {text[:200]}")
    return data


class Transport(Protocol):
    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


class SyncTransport(Protocol):
    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class SyncHttpxTransport:
    api_key: str
    timeout: float = 10.0
    max_retries: int = 2
    retry_backoff: float = 0.5
    session: Any = field(default_factory=_new_sync_client)

    BASE_URL = DEFAULT_BASE_URL

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = _new_sync_client()

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = self._query(params)
        attempts = max(0, self.max_retries) + 1
        last_error: OpinetNetworkError | None = None

        for attempt in range(attempts):
            try:
                response = self.session.get(self.BASE_URL + endpoint, params=query, timeout=self.timeout)
            except Exception as exc:
                if not _is_retryable_transport_error(exc):
                    raise
                last_error = OpinetNetworkError(str(exc))
                if attempt < attempts - 1:
                    self._sleep_before_retry(attempt)
                    continue
                raise last_error from exc

            if 500 <= response.status_code < 600 and attempt < attempts - 1:
                self._sleep_before_retry(attempt)
                continue

            return _raise_for_response(response)

        if last_error is not None:
            raise last_error
        raise OpinetServerError("request failed after retries")

    def close(self) -> None:
        close = getattr(self.session, "close", None)
        if close is not None:
            close()

    def _query(self, params: dict[str, Any] | None) -> dict[str, Any]:
        query = {"certkey": self.api_key, "out": "json"}
        if params:
            query.update(params)
        return query

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff <= 0:
            return
        sleep(self.retry_backoff * (2**attempt))


@dataclass(slots=True)
class AsyncHttpxTransport:
    api_key: str
    timeout: float = 10.0
    max_retries: int = 2
    retry_backoff: float = 0.5
    session: Any = field(default_factory=_new_async_client)

    BASE_URL = SyncHttpxTransport.BASE_URL

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = _new_async_client()

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = self._query(params)
        attempts = max(0, self.max_retries) + 1
        last_error: OpinetNetworkError | None = None

        for attempt in range(attempts):
            try:
                response = await self.session.get(self.BASE_URL + endpoint, params=query, timeout=self.timeout)
            except Exception as exc:
                if not _is_retryable_transport_error(exc):
                    raise
                last_error = OpinetNetworkError(str(exc))
                if attempt < attempts - 1:
                    await self._sleep_before_retry(attempt)
                    continue
                raise last_error from exc

            if 500 <= response.status_code < 600 and attempt < attempts - 1:
                await self._sleep_before_retry(attempt)
                continue

            return _raise_for_response(response)

        if last_error is not None:
            raise last_error
        raise OpinetServerError("request failed after retries")

    async def aclose(self) -> None:
        close = getattr(self.session, "aclose", None)
        if close is not None:
            await close()

    def _query(self, params: dict[str, Any] | None) -> dict[str, Any]:
        query = {"certkey": self.api_key, "out": "json"}
        if params:
            query.update(params)
        return query

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff <= 0:
            return
        await asyncio.sleep(self.retry_backoff * (2**attempt))


_OpinetHttp = SyncHttpxTransport
_AsyncOpinetHttp = AsyncHttpxTransport
