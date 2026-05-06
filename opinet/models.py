"""Dataclasses returned by the Opinet client."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from datetime import date, time
from math import isfinite
from types import MappingProxyType
from typing import Any, Literal, Mapping

from .codes import BrandCode, FuelType, ProductCode, StationType, opinet_sido_to_bjd, product_code_to_fuel_type
from .exceptions import OpinetInvalidParameterError

_EMPTY_RAW: Mapping[str, Any] = MappingProxyType({})
_SENSITIVE_RAW_KEYS = frozenset({"certkey", "api_key", "apikey", "authorization", "x-api-key"})


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


def _finite_float(value: float, field_name: str) -> float:
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _validated_area_level(code: str) -> Literal["sido", "sigungu"]:
    if len(code) == 2 and code.isdigit():
        opinet_sido_to_bjd(code)
        return "sido"
    if len(code) == 4 and code.isdigit():
        opinet_sido_to_bjd(code[:2])
        return "sigungu"
    raise OpinetInvalidParameterError("area code must be a 2-digit sido or 4-digit sigungu code")


@dataclass(frozen=True, slots=True)
class KatecPoint:
    """KATEC coordinate point in ``(x, y)`` meter order."""

    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite_float(self.x, "x"))
        object.__setattr__(self, "y", _finite_float(self.y, "y"))

    def as_x_y(self) -> tuple[float, float]:
        """Return the point as ``(x, y)``."""
        return self.x, self.y


@dataclass(frozen=True, slots=True)
class Wgs84Point:
    """WGS84 coordinate point in ``(lon, lat)`` order."""

    lon: float
    lat: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "lon", _finite_float(self.lon, "lon"))
        object.__setattr__(self, "lat", _finite_float(self.lat, "lat"))

    def as_lon_lat(self) -> tuple[float, float]:
        """Return the point as ``(lon, lat)``."""
        return self.lon, self.lat


@dataclass(frozen=True, slots=True)
class StationCoordinates:
    """Reusable station coordinates with KATEC and WGS84 values."""

    katec: KatecPoint
    wgs84: Wgs84Point

    @classmethod
    def from_values(cls, katec_x: float, katec_y: float, lon: float, lat: float) -> StationCoordinates:
        return cls(katec=KatecPoint(katec_x, katec_y), wgs84=Wgs84Point(lon, lat))

    @property
    def katec_x(self) -> float:
        return self.katec.x

    @property
    def katec_y(self) -> float:
        return self.katec.y

    @property
    def lon(self) -> float:
        return self.wgs84.lon

    @property
    def lat(self) -> float:
        return self.wgs84.lat


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
    def coordinates(self) -> StationCoordinates:
        return StationCoordinates.from_values(self.katec_x, self.katec_y, self.lon, self.lat)


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
    def coordinates(self) -> StationCoordinates:
        return StationCoordinates.from_values(self.katec_x, self.katec_y, self.lon, self.lat)


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
