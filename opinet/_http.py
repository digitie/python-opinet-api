"""오피넷 API용 HTTP 헬퍼."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import sleep
from typing import Any

from .exceptions import OpinetAuthError, OpinetNetworkError, OpinetRateLimitError, OpinetServerError


def _load_requests() -> Any:
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise OpinetNetworkError("requests is required; install the project dependencies first") from exc
    return requests


def _new_session() -> Any:
    return _load_requests().Session()


@dataclass(slots=True)
class _OpinetHttp:
    api_key: str
    timeout: float = 10.0
    max_retries: int = 2
    retry_backoff: float = 0.5
    session: Any = field(default_factory=_new_session)

    BASE_URL = "https://www.opinet.co.kr/api/"

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = _new_session()

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = {"certkey": self.api_key, "out": "json"}
        if params:
            query.update(params)
        requests = _load_requests()

        attempts = max(0, self.max_retries) + 1
        last_error: OpinetNetworkError | None = None
        for attempt in range(attempts):
            try:
                response = self.session.get(self.BASE_URL + endpoint, params=query, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = OpinetNetworkError(str(exc))
                if attempt < attempts - 1:
                    self._sleep_before_retry(attempt)
                    continue
                raise last_error from exc

            if 500 <= response.status_code < 600 and attempt < attempts - 1:
                self._sleep_before_retry(attempt)
                continue

            return self._raise_for_response(response)

        if last_error is not None:
            raise last_error
        raise OpinetServerError("request failed after retries")

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff <= 0:
            return
        sleep(self.retry_backoff * (2**attempt))

    def _raise_for_response(self, response: Any) -> dict[str, Any]:
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
