"""오피넷 API 원본 값의 타입 변환 헬퍼."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any


def to_date(value: Any) -> date | None:
    """YYYYMMDD 값을 ``date``로 변환하고 빈 값은 ``None``으로 유지한다."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid YYYYMMDD: {text!r}")
    return datetime.strptime(text, "%Y%m%d").date()


def to_time(value: Any) -> time | None:
    """HHMMSS 값을 ``time``으로 변환하고 빈 값은 ``None``으로 유지한다."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    if len(text) != 6 or not text.isdigit():
        raise ValueError(f"invalid HHMMSS: {text!r}")
    return datetime.strptime(text, "%H%M%S").time()


def to_float_or_none(value: Any) -> float | None:
    """부호 있는 값을 포함한 숫자 문자열을 ``float``로 변환한다."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def to_bool_yn(value: Any) -> bool:
    """오피넷 Y/N 플래그를 ``bool``로 변환한다."""
    if value is None:
        return False
    return str(value).strip().upper() == "Y"


def strip_or_none(value: Any) -> str | None:
    """문자열 유사 값을 strip하고 빈 값은 ``None``으로 정규화한다."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None
