"""오피넷 클라이언트가 반환하는 데이터 클래스 모델."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from datetime import date, datetime, time, tzinfo
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Mapping
from zoneinfo import ZoneInfo

from pykrtour import KatecPoint, PlaceCoordinate

from .codes import BrandCode, FuelType, ProductCode, StationType, opinet_sido_to_bjd, product_code_to_fuel_type
from .exceptions import OpinetInvalidParameterError

if TYPE_CHECKING:
    from .normalized import (
        NormalizedFuelAverage,
        NormalizedFuelRegionCode,
        NormalizedFuelStation,
        NormalizedFuelStationDetail,
    )

_EMPTY_RAW: Mapping[str, Any] = MappingProxyType({})
_SENSITIVE_RAW_KEYS = frozenset({"certkey", "api_key", "apikey", "authorization", "x-api-key"})


def _coerce_tz(tz: str | tzinfo) -> tzinfo:
    if isinstance(tz, str):
        return ZoneInfo(tz)
    return tz


def _freeze_raw_value(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return _freeze_raw(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_raw_value(item) for item in value)
    return value


def _freeze_raw(raw: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if raw is None:
        return _EMPTY_RAW
    if not isinstance(raw, MappingABC):
        raise TypeError("raw must be a mapping")

    frozen: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise TypeError("raw keys must be strings")
        if key.strip().lower() in _SENSITIVE_RAW_KEYS:
            continue
        frozen[key] = _freeze_raw_value(value)
    return MappingProxyType(frozen)


def _raw_text(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validated_area_level(code: str) -> Literal["sido", "sigungu"]:
    if len(code) == 2 and code.isdigit():
        opinet_sido_to_bjd(code)
        return "sido"
    if len(code) == 4 and code.isdigit():
        opinet_sido_to_bjd(code[:2])
        return "sigungu"
    raise OpinetInvalidParameterError("area code must be a 2-digit sido or 4-digit sigungu code")

@dataclass(frozen=True, slots=True)
class AvgPrice:
    trade_date: date
    product_code: ProductCode
    product_name: str
    price: float
    diff: float
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", _freeze_raw(self.raw))

    @property
    def provider_product_code(self) -> str:
        return _raw_text(self.raw, "PRODCD") or self.product_code.value

    @property
    def provider_product_name(self) -> str:
        return _raw_text(self.raw, "PRODNM") or self.product_name

    @property
    def fuel_type(self) -> FuelType:
        return product_code_to_fuel_type(self.product_code)

    def price_datetime(self, tz: str | tzinfo = "Asia/Seoul") -> datetime:
        """평균가 날짜를 시간대 정보가 포함된 자정 datetime으로 반환한다."""
        return self.to_normalized().price_datetime(tz)

    def price_timestamp(self, tz: str | tzinfo = "Asia/Seoul") -> float:
        """``price_datetime(tz).timestamp()`` 값을 반환한다."""
        return self.to_normalized().price_timestamp(tz)

    def to_normalized(self, *, endpoint: str = "avgAllPrice.do") -> NormalizedFuelAverage:
        """애플리케이션용 정규화 평균가 레코드를 반환한다."""
        from .normalized import normalize_average

        return normalize_average(self, endpoint=endpoint)


@dataclass(frozen=True, slots=True)
class Station:
    uni_id: str
    name: str
    brand: BrandCode | None
    price: float | None
    address_jibun: str | None
    address_road: str | None
    katec_x: float
    katec_y: float
    lon: float
    lat: float
    distance_m: float | None = None
    product_code: ProductCode | None = None
    product_name: str | None = None
    trade_date: date | None = None
    trade_time: time | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        raw = _freeze_raw(self.raw)
        object.__setattr__(self, "raw", raw)

        if self.product_code is None:
            raw_code = _raw_text(raw, "PRODCD")
            if raw_code is not None:
                object.__setattr__(self, "product_code", ProductCode(raw_code))
        else:
            object.__setattr__(self, "product_code", ProductCode(self.product_code))

        if self.product_name is None:
            object.__setattr__(self, "product_name", _raw_text(raw, "PRODNM"))

    @property
    def provider_station_id(self) -> str:
        return _raw_text(self.raw, "UNI_ID") or self.uni_id

    @property
    def provider_product_code(self) -> str | None:
        return self.product_code.value if self.product_code is not None else None

    @property
    def provider_product_name(self) -> str | None:
        return self.product_name

    @property
    def fuel_type(self) -> FuelType:
        if self.product_code is None:
            return FuelType.UNKNOWN
        return product_code_to_fuel_type(self.product_code)

    @property
    def brand_code(self) -> str | None:
        return _raw_text(self.raw, "POLL_DIV_CO") or _raw_text(self.raw, "POLL_DIV_CD") or (
            self.brand.value if self.brand is not None else None
        )

    @property
    def coordinate(self) -> PlaceCoordinate:
        return PlaceCoordinate(lon=self.lon, lat=self.lat)

    @property
    def katec_coordinate(self) -> KatecPoint:
        return KatecPoint(self.katec_x, self.katec_y)

    def trade_datetime(self, tz: str | tzinfo = "Asia/Seoul") -> datetime | None:
        """거래 날짜와 시간이 모두 있으면 시간대 정보가 포함된 datetime을 반환한다."""
        if self.trade_date is None or self.trade_time is None:
            return None
        return datetime.combine(self.trade_date, self.trade_time, tzinfo=_coerce_tz(tz))

    def to_normalized(self, *, endpoint: str) -> NormalizedFuelStation:
        """애플리케이션용 정규화 주유소 레코드를 반환한다."""
        from .normalized import normalize_station

        return normalize_station(self, endpoint=endpoint)


@dataclass(frozen=True, slots=True)
class OilPrice:
    product_code: ProductCode
    price: float | None
    trade_date: date
    trade_time: time
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", _freeze_raw(self.raw))

    @property
    def provider_product_code(self) -> str:
        return _raw_text(self.raw, "PRODCD") or self.product_code.value

    @property
    def fuel_type(self) -> FuelType:
        return product_code_to_fuel_type(self.product_code)


@dataclass(frozen=True, slots=True)
class StationDetail:
    uni_id: str
    name: str
    brand: BrandCode | None
    sub_brand: BrandCode | None
    station_type: StationType
    sigun_code: str
    address_jibun: str | None
    address_road: str | None
    tel: str | None
    katec_x: float
    katec_y: float
    lon: float
    lat: float
    has_maintenance: bool
    has_carwash: bool
    has_cvs: bool
    is_kpetro: bool
    prices: tuple[OilPrice, ...]
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", _freeze_raw(self.raw))

    @property
    def provider_station_id(self) -> str:
        return _raw_text(self.raw, "UNI_ID") or self.uni_id

    @property
    def brand_code(self) -> str | None:
        return _raw_text(self.raw, "POLL_DIV_CO") or _raw_text(self.raw, "POLL_DIV_CD") or (
            self.brand.value if self.brand is not None else None
        )

    @property
    def sub_brand_code(self) -> str | None:
        return _raw_text(self.raw, "GPOLL_DIV_CO") or _raw_text(self.raw, "GPOLL_DIV_CD") or (
            self.sub_brand.value if self.sub_brand is not None else None
        )

    @property
    def coordinate(self) -> PlaceCoordinate:
        return PlaceCoordinate(lon=self.lon, lat=self.lat)

    @property
    def katec_coordinate(self) -> KatecPoint:
        return KatecPoint(self.katec_x, self.katec_y)

    def to_normalized(self, *, endpoint: str = "detailById.do") -> NormalizedFuelStationDetail:
        """애플리케이션용 정규화 주유소 상세 레코드를 반환한다."""
        from .normalized import normalize_station_detail

        return normalize_station_detail(self, endpoint=endpoint)


@dataclass(frozen=True, slots=True)
class AreaCode:
    code: str
    name: str
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", _freeze_raw(self.raw))

    @property
    def is_sido(self) -> bool:
        return self.code_level == "sido"

    @property
    def is_sigungu(self) -> bool:
        return self.code_level == "sigungu"

    @property
    def code_level(self) -> Literal["sido", "sigungu"]:
        return _validated_area_level(self.code)

    @property
    def parent_sido_code(self) -> str | None:
        if self.code_level == "sido":
            return None
        return self.code[:2]

    @property
    def bjd_sido_prefix(self) -> str:
        sido_code = self.code if self.code_level == "sido" else self.code[:2]
        return opinet_sido_to_bjd(sido_code)

    def to_normalized(self, *, endpoint: str = "areaCode.do") -> NormalizedFuelRegionCode:
        """애플리케이션용 정규화 지역 코드 레코드를 반환한다."""
        from .normalized import normalize_region_code

        return normalize_region_code(self, endpoint=endpoint)
