"""Runtime configuration for Opinet clients."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://www.opinet.co.kr/api/"


@dataclass(frozen=True, slots=True)
class OpinetConfig:
    """Configuration loaded from explicit arguments, environment variables, and local .env files."""

    api_key: str | None
    timeout: float = 10.0
    strict_empty: bool = False
    max_retries: int = 2
    retry_backoff: float = 0.5
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_env(
        cls,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        strict_empty: bool = False,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
    ) -> "OpinetConfig":
        from .client import _load_default_api_key_from_env_file, _normalize_api_key

        return cls(
            api_key=(
                _normalize_api_key(api_key)
                or _normalize_api_key(os.getenv("OPINET_API_KEY"))
                or _load_default_api_key_from_env_file()
            ),
            timeout=timeout,
            strict_empty=strict_empty,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
        )
