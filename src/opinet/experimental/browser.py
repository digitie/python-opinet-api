"""오피넷 지역별 검색 화면을 읽는 실험적 Playwright 수집기.

이 모듈은 공식 open API의 안정된 대체물이 아니다. 오피넷 공개 화면의
DOM, ``searRgSelect.do`` HTML, ``searRgCircleAjax.do`` 응답 구조가 바뀌면
검증이 필요하다.
"""

from __future__ import annotations

import asyncio
import html
import importlib
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Literal, TypeAlias
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .._convert import strip_or_none, to_bool_yn, to_float_or_none
from ..codes import ProductCode, StationType, is_alddle
from ..coords import katec_to_wgs84
from ..exceptions import OpinetAuthError, OpinetRateLimitError, OpinetServerError

BrowserStationKind: TypeAlias = Literal["station", "lpg"]
BrowserQueryLevel: TypeAlias = Literal["sigungu", "dong"]

_SEOUL = ZoneInfo("Asia/Seoul")
_SEARCH_ENDPOINT = "searRgCircleAjax.do"
_PAGE_ENDPOINT = "searRgSelect.do"
_REGION_ENDPOINTS_BY_SELECTOR = {
    "#SIDO_NM0": ("sigunguGisSelect.do",),
    "#SIGUNGU_NM0": ("geocodeUtmkSelect.do", _PAGE_ENDPOINT),
}
_DEPENDENT_SELECTOR_BY_SELECTOR = {
    "#SIDO_NM0": "#SIGUNGU_NM0",
    "#SIGUNGU_NM0": "#DONG_NM",
}
_BLOCKED_PAGE_MARKERS = (
    "captcha",
    "access denied",
    "too many requests",
    "비정상적인 접근",
    "접근이 제한",
    "자동화된 접근",
    "서비스 점검",
)
_OS_POP_FIELDS: tuple[str, ...] = (
    "MARKER_P",
    "B034_P",
    "B027_P",
    "D047_P",
    "C004_P",
    "K015_P",
    "B034_DT",
    "B027_DT",
    "D047_DT",
    "C004_DT",
    "K015_DT",
    "GIS_X_COOR",
    "GIS_Y_COOR",
    "DISC_IF_CONTS",
    "SAVE_EVENT_CONTS",
    "REP_EVENT_CONTS",
    "ON_EVENT_CONTS",
    "ETC_BIZ_CONTS",
    "VLT_YN",
    "SELF_DIV_CD",
    "SEL24_YN",
    "POLL_DIV_CD",
    "OS_NM",
    "POLL_DIV_NM",
    "PHN_NO",
    "RD_ADDR",
    "CWSH_YN",
    "MAINT_YN",
    "CVS_YN",
    "LPG_YN",
    "KPETRO_YN",
    "UNI_ID",
    "BIZ_NO",
    "CB_CD",
    "CS_YN",
    "KPETRO_DP_YN",
    "GOOD_OS_YN",
    "GOOD_OS_YN5",
)
_PRODUCT_FIELDS: tuple[tuple[ProductCode, str, str], ...] = (
    (ProductCode.GASOLINE_PREMIUM, "B034_P", "B034_DT"),
    (ProductCode.GASOLINE, "B027_P", "B027_DT"),
    (ProductCode.DIESEL, "D047_P", "D047_DT"),
    (ProductCode.KEROSENE, "C004_P", "C004_DT"),
    (ProductCode.LPG, "K015_P", "K015_DT"),
)
_BRAND_NAME_TO_CODE = {
    "sk에너지": "SKE",
    "gs칼텍스": "GSC",
    "hd현대오일뱅크": "HDO",
    "s-oil": "SOL",
    "알뜰(ex)": "RTX",
    "농협": "NHO",
    "sk가스": "SKG",
    "e1": "E1G",
    "기타": "ETC",
}


def _is_allowed_opinet_url(value: str) -> bool:
    """오피넷 HTTPS 호스트인지 확인한다."""
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and parsed.hostname == "www.opinet.co.kr" and parsed.port in (None, 443)
    except ValueError:
        return False


def _has_endpoint(value: str, endpoint: str) -> bool:
    try:
        return urlsplit(value).path.rstrip("/").endswith(f"/{endpoint}")
    except ValueError:
        return False


def _is_post_response(response: Any, endpoint: str) -> bool:
    request = getattr(response, "request", None)
    return (
        getattr(request, "method", "").upper() == "POST"
        and _is_allowed_opinet_url(str(getattr(response, "url", "")))
        and _has_endpoint(str(getattr(response, "url", "")), endpoint)
    )


def _matching_endpoint(value: str, endpoints: Sequence[str]) -> str | None:
    return next((endpoint for endpoint in endpoints if _has_endpoint(value, endpoint)), None)


def _validate_response(response: Any, endpoint: str) -> None:
    """브라우저 응답의 출처·상태 코드를 검증한다."""
    response_url = str(getattr(response, "url", ""))
    if not _is_allowed_opinet_url(response_url) or not _has_endpoint(response_url, endpoint):
        raise OpinetServerError(f"unexpected Opinet browser response URL: {response_url!r}")

    status = getattr(response, "status", None)
    if not isinstance(status, int) or status < 400:
        return
    if status in (401, 403):
        raise OpinetAuthError(f"Opinet browser response denied access: HTTP {status}", status_code=status)
    if status == 429:
        raise OpinetRateLimitError(f"Opinet browser response rate limited: HTTP {status}", status_code=status)
    if 500 <= status < 600:
        raise OpinetServerError(f"Opinet browser response failed: HTTP {status}", status_code=status)
    raise OpinetServerError(f"Opinet browser response failed: HTTP {status}", status_code=status)


async def _reject_blocked_response(response: Any) -> None:
    """차단·CAPTCHA 페이지를 정상적인 빈 결과로 처리하지 않는다."""
    content_type = ""
    header_value = getattr(response, "header_value", None)
    if callable(header_value):
        content_type = (await header_value("content-type") or "").lower()
    if "html" not in content_type:
        return
    text_method = getattr(response, "text", None)
    if not callable(text_method):
        return
    body = (await text_method())[:20_000].lower()
    if any(marker in body for marker in _BLOCKED_PAGE_MARKERS):
        raise OpinetServerError("Opinet browser response appears to be an access-block page")


def _freeze_raw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_raw_value(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze_raw_value(item) for item in value)
    return value


def _freeze_raw(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    return _freeze_raw_value(raw)


def _merge_raw(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    """제품별 목록으로 나뉜 원시 행을 하나로 합친다."""
    merged = dict(left)
    for key, value in right.items():
        if key not in merged or strip_or_none(merged[key]) is None:
            merged[key] = value
    return merged


def _parse_provider_datetime(value: Any) -> datetime | None:
    text = strip_or_none(value)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=_SEOUL)
        except ValueError:
            continue
    raise ValueError(f"invalid Opinet datetime: {text!r}")


def _parse_price(value: Any) -> float | None:
    text = strip_or_none(value)
    if text is None or text in {"99999", "-", "."}:
        return None
    return to_float_or_none(text.replace(",", "").replace("원", ""))


def _parse_station_type(value: Any) -> StationType | None:
    text = strip_or_none(value)
    if text is None:
        return None
    try:
        return StationType(text)
    except ValueError:
        return None


def _to_optional_bool_yn(value: Any) -> bool | None:
    text = strip_or_none(value)
    if text is None:
        return None
    upper = text.upper()
    if upper == "Y":
        return True
    if upper == "N":
        return False
    return None


def _parse_js_string_call(href: str, function_name: str) -> tuple[str, ...]:
    """화면 링크의 단순한 JavaScript 문자열 인자 목록을 파싱한다."""
    prefix = f"javascript:{function_name}("
    if not href.startswith(prefix):
        raise ValueError(f"unexpected JavaScript link: {href[:80]!r}")
    source = href[len(prefix) :]
    if source.endswith(");"):
        source = source[:-2]
    elif source.endswith(")"):
        source = source[:-1]

    values: list[str] = []
    index = 0
    while index < len(source):
        while index < len(source) and source[index].isspace():
            index += 1
        if index >= len(source):
            break
        if source[index] != "'":
            raise ValueError("Opinet JavaScript link contains a non-string argument")
        index += 1
        chars: list[str] = []
        while index < len(source):
            char = source[index]
            if char == "'":
                index += 1
                break
            if char == "\\" and index + 1 < len(source):
                index += 1
                escaped = source[index]
                chars.append({"n": "\n", "r": "\r", "t": "\t"}.get(escaped, escaped))
            else:
                chars.append(char)
            index += 1
        else:
            raise ValueError("unterminated Opinet JavaScript string argument")
        values.append(html.unescape("".join(chars)))
        while index < len(source) and source[index].isspace():
            index += 1
        if index < len(source):
            if source[index] != ",":
                raise ValueError("Opinet JavaScript link arguments are not comma-separated")
            index += 1
    return tuple(values)


def _row_from_os_pop_href(href: str) -> dict[str, Any]:
    values = _parse_js_string_call(href, "fn_osPop")
    if len(values) != len(_OS_POP_FIELDS):
        raise ValueError(f"fn_osPop expected {len(_OS_POP_FIELDS)} arguments, got {len(values)}")
    return dict(zip(_OS_POP_FIELDS, values, strict=True))


def _row_from_illegal_dom_record(
    record: Mapping[str, Any],
    *,
    station_kind: BrowserStationKind | None = None,
) -> dict[str, Any]:
    """상세 링크가 없는 불법 행의 화면 표시값을 원시 행으로 만든다."""
    href = str(record.get("href") or "")
    values = _parse_js_string_call(href, "fnVolatInfowindow")
    if len(values) < 2:
        raise ValueError("fnVolatInfowindow expected a station id and station type")

    labels = {str(value).strip() for value in record.get("labels", ())}
    body_id = str(record.get("body_id") or "")
    price_values = [str(value).strip() for value in record.get("prices", ())]
    brand_name = strip_or_none(record.get("brand"))
    brand_key = brand_name.replace(" ", "").lower() if brand_name is not None else ""
    raw: dict[str, Any] = {
        "UNI_ID": values[0],
        "LPG_YN": values[1],
        "VLT_YN": "Y",
        "OS_NM": strip_or_none(record.get("title")) or "",
        "POLL_DIV_CD": _BRAND_NAME_TO_CODE.get(brand_key),
        "POLL_DIV_NM": brand_name,
        "SELF_DIV_CD": "Y" if "셀프" in labels else "N",
        "KPETRO_YN": "Y" if "품질" in labels else "N",
        "KPETRO_DP_YN": "Y" if "전산" in labels else "N",
        "GOOD_OS_YN": "Y" if "착한" in labels else "N",
        "GOOD_OS_YN5": "Y" if "착하디 착한주유소" in labels else "N",
        "TABLE_BODY_ID": body_id,
        "DOM_VISIBLE_FLAGS": tuple(sorted(labels)),
    }
    if station_kind == "lpg" or values[1].strip().upper() == "Y" or "lpg" in body_id.lower():
        if price_values:
            raw["K015_P"] = price_values[0]
    elif body_id in {"body1", "body11"}:
        if price_values:
            raw["B027_P"] = price_values[0]
        if len(price_values) > 1:
            raw["D047_P"] = price_values[1]
    elif body_id in {"body2", "body22"}:
        if price_values:
            raw["B034_P"] = price_values[0]
    elif body_id in {"body3", "body33"}:
        if price_values:
            raw["B027_P"] = price_values[0]
        if len(price_values) > 1:
            raw["D047_P"] = price_values[1]
    elif body_id in {"body4", "body44"}:
        if price_values:
            raw["C004_P"] = price_values[0]
    elif "lpg" in body_id.lower():
        if price_values:
            raw["K015_P"] = price_values[0]
    return raw


def _as_rows(value: Any, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        return tuple(value)
    raise OpinetServerError(f"{_SEARCH_ENDPOINT}: {field_name} must be an object, list, or null")


def _payload_list_fields(payload: Mapping[str, Any]) -> tuple[str, ...]:
    fields = [
        key
        for key in payload
        if isinstance(key, str) and (key == "list" or (key.startswith("list") and key[4:].isdigit()))
    ]
    return tuple(sorted(fields, key=lambda key: 0 if key == "list" else int(key[4:])))


@dataclass(frozen=True, slots=True)
class BrowserRegion:
    """화면의 시도·시군구·읍면동 선택값을 보존한다."""

    sido_value: str
    sido_name: str
    sigungu_value: str
    sigungu_name: str
    dong_value: str | None = None
    dong_name: str | None = None

    @property
    def sigungu_key(self) -> tuple[str, str]:
        """시도와 시군구를 조합한 안정적인 조회 키를 반환한다."""
        return self.sido_value, self.sigungu_value


@dataclass(frozen=True, slots=True)
class BrowserFuelPrice:
    """화면 응답에 포함된 유종별 가격과 갱신시각."""

    product_code: ProductCode
    price: float | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class BrowserStation:
    """오피넷 지역별 검색 화면에서 읽은 주유소 또는 충전소 한 건."""

    region: BrowserRegion
    query_level: BrowserQueryLevel
    source_kinds: tuple[BrowserStationKind, ...]
    station_id: str | None
    name: str
    brand_code: str | None
    brand_name: str | None
    phone: str | None = field(repr=False)
    address: str | None = field(repr=False)
    business_number: str | None = field(repr=False)
    cb_code: str | None = field(repr=False)
    station_type: StationType | None
    katec_x: float | None
    katec_y: float | None
    lon: float | None
    lat: float | None
    prices: tuple[BrowserFuelPrice, ...]
    is_illegal: bool
    is_self: bool
    is_24h: bool
    is_kpetro: bool
    is_electronic: bool
    is_good: bool
    is_good_strong: bool
    is_region_franchise: bool | None
    has_carwash: bool
    has_maintenance: bool
    has_cvs: bool
    cs_yn: bool
    discount_info: str | None
    save_event_info: str | None
    representative_event_info: str | None
    on_event_info: str | None
    other_business_info: str | None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", _freeze_raw(self.raw))

    @property
    def is_alddle(self) -> bool:
        """상표 코드가 오피넷 알뜰 계열인지 반환한다."""
        return is_alddle(self.brand_code)

    @property
    def price_by_product(self) -> Mapping[ProductCode, BrowserFuelPrice]:
        """유종 코드별 가격 매핑을 반환한다."""
        return MappingProxyType({item.product_code: item for item in self.prices})


@dataclass(frozen=True, slots=True)
class OpinetBrowserSnapshot:
    """한 번의 지역별 화면 수집 결과."""

    collected_at: datetime
    source_url: str
    regions: tuple[BrowserRegion, ...]
    stations: tuple[BrowserStation, ...]


@dataclass(frozen=True, slots=True)
class OpinetBrowserThrottle:
    """화면 조작과 전체 실행 사이의 부하 분산 정책."""

    action_min_seconds: float = 0.25
    action_max_seconds: float = 1.25
    run_interval_min: timedelta = timedelta(hours=10)
    run_interval_max: timedelta = timedelta(hours=12)
    max_search_requests: int = 10_000

    def __post_init__(self) -> None:
        if self.action_min_seconds < 0 or self.action_max_seconds < self.action_min_seconds:
            raise ValueError("action delay bounds are invalid")
        if self.run_interval_min < timedelta(hours=10):
            raise ValueError("run_interval_min must be at least 10 hours")
        if self.run_interval_max > timedelta(hours=12):
            raise ValueError("run_interval_max must be at most 12 hours")
        if self.run_interval_max < self.run_interval_min:
            raise ValueError("run interval bounds are invalid")
        if self.max_search_requests <= 0:
            raise ValueError("max_search_requests must be positive")

    def sample_action_delay(self, rng: random.Random) -> float:
        """다음 화면 조작 전에 적용할 무작위 대기시간(초)을 반환한다."""
        return rng.uniform(self.action_min_seconds, self.action_max_seconds)

    def sample_run_interval(self, rng: random.Random) -> timedelta:
        """다음 전체 수집까지의 무작위 대기시간을 반환한다."""
        seconds = rng.uniform(self.run_interval_min.total_seconds(), self.run_interval_max.total_seconds())
        return timedelta(seconds=seconds)


def _station_from_row(
    row: Mapping[str, Any],
    *,
    region: BrowserRegion,
    station_kind: BrowserStationKind,
    query_level: BrowserQueryLevel,
    select_values: Mapping[str, Any],
) -> BrowserStation:
    raw = dict(row)
    lpg_value = row.get("LPG_YN")
    if strip_or_none(lpg_value) is None:
        lpg_value = select_values.get("LPG_YN")
        if lpg_value is not None:
            raw["LPG_YN"] = lpg_value

    try:
        katec_x = to_float_or_none(row.get("GIS_X_COOR"))
        katec_y = to_float_or_none(row.get("GIS_Y_COOR"))
        lon: float | None = None
        lat: float | None = None
        if katec_x is not None and katec_y is not None:
            lon, lat = katec_to_wgs84(katec_x, katec_y)

        prices = tuple(
            BrowserFuelPrice(
                product_code=product_code,
                price=_parse_price(row.get(price_key)),
                updated_at=_parse_provider_datetime(row.get(date_key)),
            )
            for product_code, price_key, date_key in _PRODUCT_FIELDS
        )
    except (ValueError, TypeError) as exc:
        raise OpinetServerError(f"{_SEARCH_ENDPOINT}: failed to parse station row: {exc}") from exc

    return BrowserStation(
        region=region,
        query_level=query_level,
        source_kinds=(station_kind,),
        station_id=strip_or_none(row.get("UNI_ID")),
        name=strip_or_none(row.get("OS_NM")) or "",
        brand_code=strip_or_none(row.get("POLL_DIV_CO")) or strip_or_none(row.get("POLL_DIV_CD")),
        brand_name=strip_or_none(row.get("POLL_DIV_NM")),
        phone=strip_or_none(row.get("PHN_NO")),
        address=strip_or_none(row.get("RD_ADDR")),
        business_number=strip_or_none(row.get("BIZ_NO")),
        cb_code=strip_or_none(row.get("CB_CD")),
        station_type=_parse_station_type(lpg_value),
        katec_x=katec_x,
        katec_y=katec_y,
        lon=lon,
        lat=lat,
        prices=prices,
        is_illegal=to_bool_yn(row.get("VLT_YN")),
        is_self=to_bool_yn(row.get("SELF_DIV_CD")),
        is_24h=to_bool_yn(row.get("SEL24_YN")),
        is_kpetro=to_bool_yn(row.get("KPETRO_YN")),
        is_electronic=to_bool_yn(row.get("KPETRO_DP_YN")),
        is_good=to_bool_yn(row.get("GOOD_OS_YN")),
        is_good_strong=to_bool_yn(row.get("GOOD_OS_YN5")),
        is_region_franchise=_to_optional_bool_yn(row.get("RGN_FRCS_YN")),
        has_carwash=to_bool_yn(row.get("CWSH_YN")),
        has_maintenance=to_bool_yn(row.get("MAINT_YN")),
        has_cvs=to_bool_yn(row.get("CVS_YN")),
        cs_yn=to_bool_yn(row.get("CS_YN")),
        discount_info=strip_or_none(row.get("DISC_IF_CONTS")),
        save_event_info=strip_or_none(row.get("SAVE_EVENT_CONTS")),
        representative_event_info=strip_or_none(row.get("REP_EVENT_CONTS")),
        on_event_info=strip_or_none(row.get("ON_EVENT_CONTS")),
        other_business_info=strip_or_none(row.get("ETC_BIZ_CONTS")),
        raw=raw,
    )


def _station_key(station: BrowserStation) -> tuple[str, ...]:
    if station.station_id is not None:
        return (station.region.sido_value, station.region.sigungu_value, station.station_id)
    return (
        station.region.sido_value,
        station.region.sigungu_value,
        station.name,
        str(station.katec_x),
        str(station.katec_y),
    )


def _merge_station(left: BrowserStation, right: BrowserStation) -> BrowserStation:
    prices: list[BrowserFuelPrice] = []
    right_prices = {item.product_code: item for item in right.prices}
    for item in left.prices:
        other = right_prices.get(item.product_code)
        if other is not None and item.price is None and other.price is not None:
            item = other
        elif other is not None and item.updated_at is None and other.updated_at is not None:
            item = replace(item, updated_at=other.updated_at)
        prices.append(item)

    def prefer(left_value: Any, right_value: Any) -> Any:
        return left_value if left_value not in (None, "") else right_value

    def merge_station_type(left_value: StationType | None, right_value: StationType | None) -> StationType | None:
        if left_value is None:
            return right_value
        if right_value is None or left_value == right_value:
            return left_value
        if StationType.BOTH in (left_value, right_value):
            return StationType.BOTH
        return left_value

    def merge_optional_bool(left_value: bool | None, right_value: bool | None) -> bool | None:
        if left_value is True or right_value is True:
            return True
        if left_value is False and right_value is False:
            return False
        return right_value if left_value is None else left_value

    return replace(
        left,
        source_kinds=tuple(dict.fromkeys((*left.source_kinds, *right.source_kinds))),
        station_id=prefer(left.station_id, right.station_id),
        name=prefer(left.name, right.name),
        brand_code=prefer(left.brand_code, right.brand_code),
        brand_name=prefer(left.brand_name, right.brand_name),
        phone=prefer(left.phone, right.phone),
        address=prefer(left.address, right.address),
        business_number=prefer(left.business_number, right.business_number),
        cb_code=prefer(left.cb_code, right.cb_code),
        station_type=merge_station_type(left.station_type, right.station_type),
        katec_x=prefer(left.katec_x, right.katec_x),
        katec_y=prefer(left.katec_y, right.katec_y),
        lon=prefer(left.lon, right.lon),
        lat=prefer(left.lat, right.lat),
        prices=tuple(prices),
        is_illegal=left.is_illegal or right.is_illegal,
        is_self=left.is_self or right.is_self,
        is_24h=left.is_24h or right.is_24h,
        is_kpetro=left.is_kpetro or right.is_kpetro,
        is_electronic=left.is_electronic or right.is_electronic,
        is_good=left.is_good or right.is_good,
        is_good_strong=left.is_good_strong or right.is_good_strong,
        is_region_franchise=merge_optional_bool(left.is_region_franchise, right.is_region_franchise),
        has_carwash=left.has_carwash or right.has_carwash,
        has_maintenance=left.has_maintenance or right.has_maintenance,
        has_cvs=left.has_cvs or right.has_cvs,
        cs_yn=left.cs_yn or right.cs_yn,
        discount_info=prefer(left.discount_info, right.discount_info),
        save_event_info=prefer(left.save_event_info, right.save_event_info),
        representative_event_info=prefer(left.representative_event_info, right.representative_event_info),
        on_event_info=prefer(left.on_event_info, right.on_event_info),
        other_business_info=prefer(left.other_business_info, right.other_business_info),
        raw=_merge_raw(left.raw, right.raw),
    )


def parse_browser_response(
    payload: Mapping[str, Any],
    *,
    region: BrowserRegion,
    station_kind: BrowserStationKind,
    query_level: BrowserQueryLevel,
) -> tuple[BrowserStation, ...]:
    """지역 검색 AJAX 응답을 유종별로 합쳐 주유소 모델로 변환한다.

    ``searRgCircleAjax.do`` 응답의 ``list``부터 ``list4``까지를 합치므로
    같은 주유소가 고급휘발유·휘발유·경유·실내등유 표에 반복되어도 한 건으로
    반환한다. 불법 행은 화면 링크가 상세 팝업이 아니더라도 JSON 원본에서
    플래그와 식별자를 보존한다.
    """
    select_values = payload.get("selectVO")
    if not isinstance(select_values, Mapping):
        select_values = {}

    list_fields = _payload_list_fields(payload)
    if not list_fields:
        raise OpinetServerError(f"{_SEARCH_ENDPOINT}: response does not contain station lists")

    stations: dict[tuple[str, ...], BrowserStation] = {}
    for field_name in list_fields:
        for row in _as_rows(payload.get(field_name), field_name):
            station = _station_from_row(
                row,
                region=region,
                station_kind=station_kind,
                query_level=query_level,
                select_values=select_values,
            )
            key = _station_key(station)
            previous = stations.get(key)
            stations[key] = station if previous is None else _merge_station(previous, station)
    return tuple(stations.values())


def _load_playwright() -> Any:
    try:
        module = importlib.import_module("playwright.async_api")
    except ModuleNotFoundError as exc:
        raise ImportError(
            "Playwright 수집기를 사용하려면 `pip install -e '.[browser]'`와 "
            "`playwright install chromium`을 실행하세요."
        ) from exc
    return getattr(module, "async_playwright")


class OpinetBrowserCollector:
    """오피넷 지역별 화면에서 지역·주유소·충전소 데이터를 수집한다.

    .. warning::
       공개 화면의 DOM, ``searRgSelect.do`` HTML, ``searRgCircleAjax.do``
       응답은 공식 API 계약이 아니므로 검증되지 않은 실험 기능이다.
       자동화 탐지 우회, 브라우저
       지문 조작, CAPTCHA 우회는 수행하지 않는다. 사이트가 접근을 거부하거나
       자동화 확인 화면을 반환하면 오류를 그대로 노출한다.

    ``headless``는 브라우저 표시 여부만 제어한다. 기본 브라우저 설정과
    기본 User-Agent를 사용하며, PC 브라우저로 위장하기 위한 패치나 stealth
    플러그인은 적용하지 않는다. 부하 분산을 위해 화면 조작 사이에는 짧은
    무작위 대기, 전체 수집 사이에는 기본 10~12시간의 무작위 대기를 사용한다.
    """

    def __init__(
        self,
        *,
        url: str = "https://www.opinet.co.kr/searRgSelect.do",
        headless: bool = True,
        browser_channel: str | None = None,
        timeout_ms: int = 30_000,
        query_level: BrowserQueryLevel = "sigungu",
        throttle: OpinetBrowserThrottle | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if not _is_allowed_opinet_url(url):
            raise ValueError("url must be an HTTPS Opinet URL")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if query_level not in ("sigungu", "dong"):
            raise ValueError("query_level must be 'sigungu' or 'dong'")
        self.url = url
        self.headless = headless
        self.browser_channel = browser_channel
        self.timeout_ms = timeout_ms
        self.query_level = query_level
        self.throttle = throttle or OpinetBrowserThrottle()
        self.rng = rng or random.Random()

    async def collect_once(self) -> OpinetBrowserSnapshot:
        """새 Chromium 컨텍스트로 한 번 전체 지역 수집을 실행한다."""
        async_playwright = _load_playwright()
        async with async_playwright() as playwright:
            launch_options: dict[str, Any] = {"headless": self.headless}
            if self.browser_channel is not None:
                launch_options["channel"] = self.browser_channel
            browser = None
            context = None
            try:
                browser = await playwright.chromium.launch(**launch_options)
                context = await browser.new_context()
                page = await context.new_page()
                navigation_response = await page.goto(self.url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                if navigation_response is None:
                    raise OpinetServerError("Opinet browser navigation returned no response")
                _validate_response(navigation_response, _PAGE_ENDPOINT)
                await _reject_blocked_response(navigation_response)
                final_url = str(getattr(page, "url", self.url))
                if not _is_allowed_opinet_url(final_url):
                    raise OpinetServerError(f"Opinet browser navigation redirected to {final_url!r}")
                await self._pause(page)
                return await self.collect_page(page)
            finally:
                if context is not None:
                    try:
                        await context.close()
                    finally:
                        if browser is not None:
                            await browser.close()
                elif browser is not None:
                    await browser.close()

    async def collect_page(self, page: Any) -> OpinetBrowserSnapshot:
        """이미 열린 Playwright 페이지에서 한 번 전체 지역 수집을 실행한다."""
        regions = await self._discover_regions(page)
        query_regions = self._query_regions(regions)
        if not query_regions:
            raise OpinetServerError("Opinet browser returned no queryable regions")
        search_request_count = len(query_regions) * 2
        if search_request_count > self.throttle.max_search_requests:
            raise OpinetServerError(
                "Opinet browser search request budget exceeded: "
                f"{search_request_count} > {self.throttle.max_search_requests}"
            )
        stations: dict[tuple[str, ...], BrowserStation] = {}

        tab_targets: tuple[tuple[BrowserStationKind, str], ...] = (
            ("station", "#OS_BTN"),
            ("lpg", "#LPG_BTN"),
        )
        for station_kind, tab_selector in tab_targets:
            await self._activate_tab(page, station_kind=station_kind, selector=tab_selector)
            for region in query_regions:
                for station in await self._search_region(
                    page,
                    region,
                    station_kind=station_kind,
                ):
                    key = _station_key(station)
                    previous = stations.get(key)
                    stations[key] = station if previous is None else _merge_station(previous, station)

        return OpinetBrowserSnapshot(
            collected_at=datetime.now(_SEOUL),
            source_url=self.url,
            regions=tuple(regions),
            stations=tuple(stations.values()),
        )

    async def _activate_tab(self, page: Any, *, station_kind: BrowserStationKind, selector: str) -> None:
        locator = page.locator(selector)
        class_name = (await locator.get_attribute("class") or "").lower()
        aria_selected = await locator.get_attribute("aria-selected")
        is_active = aria_selected == "true" or bool(
            {"on", "active", "selected"}.intersection(class_name.split())
        )
        if not is_active:
            async with page.expect_response(
                lambda response: _is_post_response(response, _PAGE_ENDPOINT),
                timeout=self.timeout_ms,
            ) as response_info:
                await locator.click(timeout=self.timeout_ms)
            response = await response_info.value
            _validate_response(response, _PAGE_ENDPOINT)
            await _reject_blocked_response(response)
        await self._pause(page)
        await self._wait_for_page_ready(page)

    async def _wait_for_page_ready(self, page: Any) -> None:
        await page.wait_for_function(
            "() => document.readyState === 'complete'",
            timeout=self.timeout_ms,
        )

    async def _wait_for_results_dom(self, page: Any) -> None:
        await page.wait_for_function(
            "() => document.readyState === 'complete' && "
            "document.querySelector('table.tbl_type10') !== null",
            timeout=self.timeout_ms,
        )

    async def _wait_for_options(self, page: Any, selector: str) -> None:
        await page.wait_for_function(
            "selector => { const element = document.querySelector(selector); "
            "return element !== null && Array.from(element.options).some(option => option.value.trim() !== ''); }",
            arg=selector,
            timeout=self.timeout_ms,
        )

    async def run_forever(
        self,
        sink: Callable[[OpinetBrowserSnapshot], Awaitable[None]],
        *,
        stop_event: asyncio.Event | None = None,
        run_immediately: bool = True,
        on_error: Callable[[Exception], Awaitable[None]] | None = None,
    ) -> None:
        """수집 결과를 전달하고 10~12시간 무작위 간격으로 반복한다.

        ``stop_event``가 설정되거나 작업이 취소되면 대기와 다음 실행을
        중단한다. 수집 결과 저장은 호출자가 제공한 ``sink``의 책임이다.
        """
        first = True
        while stop_event is None or not stop_event.is_set():
            if not first or not run_immediately:
                if await self._wait_or_stop(self.throttle.sample_run_interval(self.rng), stop_event):
                    return
            first = False
            try:
                snapshot = await self.collect_once()
                await sink(snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if on_error is None:
                    raise
                await on_error(exc)

    async def _pause(self, page: Any) -> None:
        delay_ms = round(self.throttle.sample_action_delay(self.rng) * 1000)
        if delay_ms > 0:
            await page.wait_for_timeout(delay_ms)

    async def _wait_or_stop(self, delay: timedelta, stop_event: asyncio.Event | None) -> bool:
        if stop_event is None:
            await asyncio.sleep(delay.total_seconds())
            return False
        stop_task = asyncio.create_task(stop_event.wait())
        delay_task = asyncio.create_task(asyncio.sleep(delay.total_seconds()))
        stop_requested = False
        try:
            done, _ = await asyncio.wait({stop_task, delay_task}, return_when=asyncio.FIRST_COMPLETED)
            stop_requested = stop_task in done and stop_task.result()
        finally:
            for task in (stop_task, delay_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(stop_task, delay_task, return_exceptions=True)
        return stop_requested

    async def _read_options(self, page: Any, selector: str) -> tuple[tuple[str, str], ...]:
        values = await page.locator(f"{selector} option").evaluate_all(
            "options => options.map(option => ({value: option.value, name: option.textContent.trim()}))"
        )
        result: list[tuple[str, str]] = []
        for item in values:
            if isinstance(item, Mapping):
                value = strip_or_none(item.get("value"))
                name = strip_or_none(item.get("name"))
                if value is not None and name is not None:
                    result.append((value, name))
        return tuple(result)

    async def _select_value(self, page: Any, selector: str, value: str) -> None:
        locator = page.locator(selector)
        current = await locator.input_value()
        if current == value:
            return
        region_endpoints = _REGION_ENDPOINTS_BY_SELECTOR.get(selector)
        dependent_selector = _DEPENDENT_SELECTOR_BY_SELECTOR.get(selector)
        if region_endpoints is None:
            await locator.select_option(value=value)
        else:
            async with page.expect_response(
                lambda response: any(_is_post_response(response, endpoint) for endpoint in region_endpoints),
                timeout=self.timeout_ms,
            ) as response_info:
                await locator.select_option(value=value)
            response = await response_info.value
            response_endpoint = _matching_endpoint(str(response.url), region_endpoints)
            if response_endpoint is None:
                raise OpinetServerError("unexpected Opinet region response URL")
            _validate_response(response, response_endpoint)
            await _reject_blocked_response(response)
        await self._pause(page)
        if dependent_selector is not None:
            await page.wait_for_function(
                "({selector, value, dependent}) => { "
                "const current = document.querySelector(selector); "
                "const next = document.querySelector(dependent); "
                "return current !== null && current.value === value && "
                "next !== null && (dependent === '#DONG_NM' || "
                "Array.from(next.options).some(option => option.value.trim() !== '')); }",
                arg={"selector": selector, "value": value, "dependent": dependent_selector},
                timeout=self.timeout_ms,
            )

    async def _discover_regions(self, page: Any) -> list[BrowserRegion]:
        regions: list[BrowserRegion] = []
        await self._wait_for_options(page, "#SIDO_NM0")
        sidos = await self._read_options(page, "#SIDO_NM0")
        if not sidos:
            raise OpinetServerError("Opinet browser returned no sido options")
        for sido_value, sido_name in sidos:
            await self._select_value(page, "#SIDO_NM0", sido_value)
            sigungus = await self._read_options(page, "#SIGUNGU_NM0")
            if not sigungus:
                raise OpinetServerError(f"Opinet browser returned no sigungu options for {sido_value!r}")
            for sigungu_value, sigungu_name in sigungus:
                await self._select_value(page, "#SIGUNGU_NM0", sigungu_value)
                dongs = await self._read_options(page, "#DONG_NM")
                if dongs:
                    regions.extend(
                        BrowserRegion(
                            sido_value=sido_value,
                            sido_name=sido_name,
                            sigungu_value=sigungu_value,
                            sigungu_name=sigungu_name,
                            dong_value=dong_value,
                            dong_name=dong_name,
                        )
                        for dong_value, dong_name in dongs
                    )
                else:
                    regions.append(
                        BrowserRegion(
                            sido_value=sido_value,
                            sido_name=sido_name,
                            sigungu_value=sigungu_value,
                            sigungu_name=sigungu_name,
                        )
                    )
        return regions

    def _query_regions(self, regions: Sequence[BrowserRegion]) -> tuple[BrowserRegion, ...]:
        if self.query_level == "dong":
            return tuple(regions)
        unique: dict[tuple[str, str], BrowserRegion] = {}
        for region in regions:
            unique.setdefault(
                region.sigungu_key,
                replace(region, dong_value=None, dong_name=None),
            )
        return tuple(unique.values())

    async def _read_dom_stations(
        self,
        page: Any,
        *,
        region: BrowserRegion,
        station_kind: BrowserStationKind,
    ) -> tuple[BrowserStation, ...]:
        records = await page.locator("table.tbl_type10 tbody tr").evaluate_all(
            """
            rows => rows.map(row => ({
                href: row.querySelector('a')?.getAttribute('href') || '',
                title: row.querySelector('td.rlist')?.getAttribute('title') || '',
                brand: row.querySelector('img')?.getAttribute('alt') || '',
                body_id: row.closest('tbody')?.id || '',
                prices: Array.from(row.querySelectorAll('td.price')).map(cell => cell.textContent.trim()),
                labels: Array.from(row.querySelectorAll('.ico')).map(cell => cell.textContent.trim()),
            }))
            """
        )
        stations: dict[tuple[str, ...], BrowserStation] = {}
        malformed_records = 0
        for record in records:
            if not isinstance(record, Mapping):
                malformed_records += 1
                continue
            href = str(record.get("href") or "")
            try:
                if href.startswith("javascript:fn_osPop("):
                    row = _row_from_os_pop_href(href)
                elif href.startswith("javascript:fnVolatInfowindow("):
                    row = _row_from_illegal_dom_record(record, station_kind=station_kind)
                else:
                    continue
                station = _station_from_row(
                    row,
                    region=region,
                    station_kind=station_kind,
                    query_level=self.query_level,
                    select_values={},
                )
            except (ValueError, OpinetServerError):
                malformed_records += 1
                continue
            key = _station_key(station)
            previous = stations.get(key)
            stations[key] = station if previous is None else _merge_station(previous, station)
        if records and not stations and malformed_records:
            raise OpinetServerError("Opinet browser returned only malformed station rows")
        return tuple(stations.values())

    async def _search_region(
        self,
        page: Any,
        region: BrowserRegion,
        *,
        station_kind: BrowserStationKind,
    ) -> tuple[BrowserStation, ...]:
        await self._select_value(page, "#SIDO_NM0", region.sido_value)
        await self._select_value(page, "#SIGUNGU_NM0", region.sigungu_value)
        await self._select_value(page, "#DONG_NM", region.dong_value or "")
        for selector, expected in (
            ("#SIDO_NM0", region.sido_value),
            ("#SIGUNGU_NM0", region.sigungu_value),
            ("#DONG_NM", region.dong_value or ""),
        ):
            actual = await page.locator(selector).input_value()
            if actual != expected:
                raise OpinetServerError(
                    f"Opinet browser selected value mismatch for {selector}: "
                    f"expected {expected!r}, got {actual!r}"
                )
        await self._pause(page)

        async with page.expect_response(
            lambda response: _is_post_response(response, _SEARCH_ENDPOINT)
            or _is_post_response(response, _PAGE_ENDPOINT),
            timeout=self.timeout_ms,
        ) as response_info:
            await page.get_by_role("link", name="조회", exact=True).click(timeout=self.timeout_ms)
        response = await response_info.value
        response_endpoint = _SEARCH_ENDPOINT if _has_endpoint(str(response.url), _SEARCH_ENDPOINT) else _PAGE_ENDPOINT
        _validate_response(response, response_endpoint)
        await _reject_blocked_response(response)
        content_type = (await response.header_value("content-type") or "").lower()
        if response_endpoint == _SEARCH_ENDPOINT or "json" in content_type:
            payload = await response.json()
            if not isinstance(payload, Mapping):
                raise OpinetServerError(f"{_SEARCH_ENDPOINT}: response must be a JSON object")
            return parse_browser_response(
                payload,
                region=region,
                station_kind=station_kind,
                query_level=self.query_level,
            )
        await self._wait_for_results_dom(page)
        return await self._read_dom_stations(page, region=region, station_kind=station_kind)


__all__ = [
    "BrowserFuelPrice",
    "BrowserRegion",
    "BrowserStation",
    "BrowserQueryLevel",
    "BrowserStationKind",
    "OpinetBrowserCollector",
    "OpinetBrowserSnapshot",
    "OpinetBrowserThrottle",
    "parse_browser_response",
]
