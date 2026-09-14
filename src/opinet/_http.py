"""Opinet API HTTP helpers built on httpx."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator
from inspect import iscoroutinefunction
from urllib.parse import quote, quote_plus
from typing import Any, Protocol

from ._ratelimit import AsyncTokenBucket
from ._httpx import send_after_token
from .config import DEFAULT_BASE_URL
from .exceptions import OpinetError, OpinetAuthError, OpinetNetworkError, OpinetRateLimitError, OpinetServerError

_MAX_BACKOFF_SECONDS = 30.0
_CERTKEY_RE = re.compile(r"certkey=[^&\s<>]+", re.IGNORECASE)


def _redact(text: str, api_key: str | None = None) -> str:
    if api_key:
        for secret in sorted({api_key, quote(api_key, safe=""), quote_plus(api_key)}, key=len, reverse=True):
            text = text.replace(secret, "<REDACTED>")
    return _CERTKEY_RE.sub("certkey=<REDACTED>", text)


class _CertkeyLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "certkey=" in message:
            record.msg = _redact(message)
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_CertkeyLogFilter())


def _load_httpx() -> Any:
    try:
        import httpx
    except ModuleNotFoundError as exc:
        raise OpinetNetworkError("httpx is required; install the project dependencies first") from exc
    return httpx




def _new_async_client() -> Any:
    return _load_httpx().AsyncClient(follow_redirects=True)


def _is_retryable_transport_error(exc: Exception) -> bool:
    httpx = _load_httpx()
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError))


def _raise_for_response(response: Any) -> dict[str, Any]:
    if response.status_code in (401, 403):
        raise OpinetAuthError(
            f"HTTP {response.status_code}: {_redact(response.text)[:200]}",
            status_code=response.status_code,
            headers=response.headers,
        )
    if response.status_code == 429:
        raise OpinetRateLimitError(
            _redact(response.text)[:200],
            status_code=response.status_code,
            headers=response.headers,
        )
    if 500 <= response.status_code < 600:
        raise OpinetServerError(
            f"HTTP {response.status_code}: {_redact(response.text)[:200]}",
            status_code=response.status_code,
            headers=response.headers,
        )

    try:
        data = response.json()
    except (ValueError, RecursionError) as exc:
        raise OpinetServerError(
            f"JSON parse failure: {exc}",
            status_code=response.status_code,
            headers=response.headers,
        ) from exc

    if not isinstance(data, dict):
        raise OpinetServerError(
            f"Unexpected response body: {str(data)[:200]}",
            status_code=response.status_code,
            headers=response.headers,
        )

    result = data.get("RESULT")
    if not isinstance(result, dict):
        text = _redact(str(result))
        lowered = text.lower()
        if "invalid" in lowered:
            raise OpinetAuthError(text[:200], status_code=response.status_code, headers=response.headers)
        if "limit" in lowered or "초과" in text:
            raise OpinetRateLimitError(text[:200], status_code=response.status_code, headers=response.headers)
        raise OpinetServerError(
            f"Unexpected RESULT: {text[:200]}",
            status_code=response.status_code,
            headers=response.headers,
        )
    return data


class Transport(Protocol):
    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...








@dataclass(slots=True)
class AsyncHttpxTransport:
    """공유 토큰 버킷으로 모든 전송 시도를 제어하는 비동기 HTTP 계층."""

    api_key: str = field(repr=False)
    timeout: float = 10.0
    max_retries: int = 2
    retry_backoff: float = 0.5
    session: Any = field(default=None, repr=False)
    max_rps: float = 5.0
    rate_limiter: AsyncTokenBucket | None = None
    _owns_session: bool = field(default=False, init=False)
    _closed: bool = field(default=False, init=False)
    _calls: ContextVar[list[dict[str, Any]] | None] = field(
        default_factory=lambda: ContextVar("opinet_http_calls", default=None), init=False, repr=False
    )

    BASE_URL = DEFAULT_BASE_URL

    def __post_init__(self) -> None:
        if self.rate_limiter is None:
            self.rate_limiter = AsyncTokenBucket(self.max_rps)
        if self.session is not None and not iscoroutinefunction(self.session.get):
            raise TypeError("session must provide an async get method")
        self._owns_session = self.session is None

    @contextmanager
    def capture_calls(self) -> Iterator[list[dict[str, Any]]]:
        """현재 작업의 HTTP 기록을 격리하고 취소 시에도 복구한다."""
        calls: list[dict[str, Any]] = []
        token = self._calls.set(calls)
        try:
            yield calls
        finally:
            self._calls.reset(token)

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("Opinet transport is closed")
        if self.session is None:
            self.session = _new_async_client()
        query = self._query(params)
        attempts = max(0, self.max_retries) + 1
        httpx = _load_httpx()
        for attempt in range(attempts):
            assert self.rate_limiter is not None
            await self.rate_limiter.acquire()
            if self._closed:
                raise RuntimeError("Opinet transport is closed")
            try:
                if isinstance(self.session, httpx.AsyncClient):
                    request = self.session.build_request("GET", self.BASE_URL + endpoint, params=query, timeout=self.timeout)
                    response = await send_after_token(self.session, request, self.rate_limiter)
                else:
                    response = await self.session.get(self.BASE_URL + endpoint, params=query, timeout=self.timeout)
            except Exception as exc:
                if not isinstance(exc, httpx.HTTPError):
                    raise
                if _is_retryable_transport_error(exc) and attempt < attempts - 1:
                    await self._sleep_before_retry(attempt)
                    continue
                raise OpinetNetworkError(_redact(str(exc), self.api_key)) from None

            if 500 <= response.status_code < 600 and attempt < attempts - 1:
                await self._sleep_before_retry(attempt)
                continue
            try:
                body = _raise_for_response(response)
            except OpinetError as exc:
                # 분류는 원문으로 수행하고 외부에 표시되는 오류만 마스킹한다.
                exc.args = (_redact(str(exc), self.api_key),)
                if exc.headers is not None:
                    exc.headers = {key: _redact(value, self.api_key) for key, value in exc.headers.items()}
                raise exc from None
            calls = self._calls.get()
            if calls is not None:
                calls.append({"endpoint": endpoint, "params": dict(params or {}), "status_code": response.status_code, "body": body})
            return body
        raise OpinetServerError("request failed after retries")

    async def aclose(self) -> None:
        """소유한 세션만 닫고 이후 요청을 차단한다."""
        if not self._closed:
            self._closed = True
            if self._owns_session and self.session is not None:
                await self.session.aclose()

    def _query(self, params: dict[str, Any] | None) -> dict[str, Any]:
        query = dict(params or {})
        query.update(certkey=self.api_key, out="json")
        return query

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff > 0:
            delay = min(self.retry_backoff * (2**attempt) * random.uniform(0.5, 1.5), _MAX_BACKOFF_SECONDS)
            await asyncio.sleep(delay)
