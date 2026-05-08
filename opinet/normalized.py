"""오피넷 응답 모델의 애플리케이션용 정규화 레코드."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from datetime import date, datetime, time, tzinfo
from enum import Enum
from typing import Any, Literal, TypeAlias, TYPE_CHECKING
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .codes import FuelType, StationType
from .models import StationCoordinates

if TYPE_CHECKING:
    from .models import AreaCode, AvgPrice, OilPrice, Station, StationDetail

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

PROVIDER: Literal["opinet"] = "opinet"
DEFAULT_TIMEZONE = "Asia/Seoul"


def _coerce_tz(tz: str | tzinfo = DEFAULT_TIMEZONE) -> tzinfo:
    if isinstance(tz, str):
        return ZoneInfo(tz)
    return tz


def to_json_safe_raw(value: Any) -> JsonValue:
    """raw payload 값을 JSON으로 안전한 기본 dict/list 구조로 변환한다."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, MappingABC):
        return {str(key): to_json_safe_raw(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [to_json_safe_raw(item) for item in value]
    return str(value)


raw_to_json_safe = to_json_safe_raw


class _NormalizedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NormalizedFuelAverage(_NormalizedModel):
    """정규화된 전국 평균 유가 레코드."""

    provider: Literal["opinet"] = PROVIDER
    provider_endpoint: str
    provider_product_code: str
    provider_product_name: str
    fuel_type: FuelType
    trade_date: date
    price: float
    diff: float
    raw: dict[str, Any]

    def price_datetime(self, tz: str | tzinfo = DEFAULT_TIMEZONE) -> datetime:
        """가격 날짜를 지정 시간대의 시간대 정보가 포함된 자정으로 반환한다."""
        return datetime.combine(self.trade_date, time.min, tzinfo=_coerce_tz(tz))

    def price_timestamp(self, tz: str | tzinfo = DEFAULT_TIMEZONE) -> float:
        """``price_datetime(tz).timestamp()`` 값을 반환한다."""
        return self.price_datetime(tz).timestamp()


class NormalizedFuelStation(_NormalizedModel):
    """정규화된 주유소 가격/검색 레코드."""

    provider: Literal["opinet"] = PROVIDER
    provider_endpoint: str
    provider_station_id: str
    provider_station_name: str
    provider_product_code: str | None
    provider_product_name: str | None
    fuel_type: FuelType
    brand_code: str | None
    price: float | None
    diff: float | None
    distance_m: float | None
    address_jibun: str | None
    address_road: str | None
    coordinates: StationCoordinates
    katec_x: float
    katec_y: float
    lon: float
    lat: float
    trade_date: date | None
    trade_time: time | None
    raw: dict[str, Any]

    def trade_datetime(self, tz: str | tzinfo = DEFAULT_TIMEZONE) -> datetime | None:
        """거래 날짜와 시간이 모두 있으면 시간대 정보가 포함된 datetime을 반환한다."""
        if self.trade_date is None or self.trade_time is None:
            return None
        return datetime.combine(self.trade_date, self.trade_time, tzinfo=_coerce_tz(tz))


class NormalizedFuelStationDetailPrice(_NormalizedModel):
    """주유소 상세 레코드 안의 정규화된 제품별 가격 row."""

    provider: Literal["opinet"] = PROVIDER
    provider_endpoint: str
    provider_station_id: str
    provider_station_name: str
    provider_product_code: str
    fuel_type: FuelType
    price: float | None
    trade_date: date
    trade_time: time
    raw: dict[str, Any]

    def trade_datetime(self, tz: str | tzinfo = DEFAULT_TIMEZONE) -> datetime:
        """이 가격 row의 거래 시각을 시간대 정보가 포함된 datetime으로 반환한다."""
        return datetime.combine(self.trade_date, self.trade_time, tzinfo=_coerce_tz(tz))


class NormalizedFuelStationDetail(_NormalizedModel):
    """정규화된 주유소 상세 레코드."""

    provider: Literal["opinet"] = PROVIDER
    provider_endpoint: str
    provider_station_id: str
    provider_station_name: str
    brand_code: str | None
    sub_brand_code: str | None
    station_type: StationType
    sigun_code: str
    address_jibun: str | None
    address_road: str | None
    tel: str | None
    coordinates: StationCoordinates
    katec_x: float
    katec_y: float
    lon: float
    lat: float
    has_maintenance: bool
    has_carwash: bool
    has_cvs: bool
    is_kpetro: bool
    prices: tuple[NormalizedFuelStationDetailPrice, ...]
    raw: dict[str, Any]


class NormalizedFuelRegionCode(_NormalizedModel):
    """정규화된 오피넷 지역 코드 레코드."""

    provider: Literal["opinet"] = PROVIDER
    provider_endpoint: str
    provider_region_code: str
    provider_region_name: str
    code_level: Literal["sido", "sigungu"]
    parent_sido_code: str | None
    bjd_sido_prefix: str
    raw: dict[str, Any]


def normalize_average(avg: AvgPrice, *, endpoint: str = "avgAllPrice.do") -> NormalizedFuelAverage:
    """``AvgPrice``에서 정규화 평균가 레코드를 만든다."""
    return NormalizedFuelAverage(
        provider_endpoint=endpoint,
        provider_product_code=avg.provider_product_code,
        provider_product_name=avg.provider_product_name,
        fuel_type=avg.fuel_type,
        trade_date=avg.trade_date,
        price=avg.price,
        diff=avg.diff,
        raw=_json_safe_raw_dict(avg.raw),
    )


def normalize_station(station: Station, *, endpoint: str) -> NormalizedFuelStation:
    """``Station``에서 정규화 주유소 레코드를 만든다."""
    return NormalizedFuelStation(
        provider_endpoint=endpoint,
        provider_station_id=station.provider_station_id,
        provider_station_name=station.name,
        provider_product_code=station.provider_product_code,
        provider_product_name=station.provider_product_name,
        fuel_type=station.fuel_type,
        brand_code=station.brand_code,
        price=station.price,
        diff=None,
        distance_m=station.distance_m,
        address_jibun=station.address_jibun,
        address_road=station.address_road,
        coordinates=station.coordinates,
        katec_x=station.katec_x,
        katec_y=station.katec_y,
        lon=station.lon,
        lat=station.lat,
        trade_date=station.trade_date,
        trade_time=station.trade_time,
        raw=_json_safe_raw_dict(station.raw),
    )


def normalize_station_detail(
    detail: StationDetail,
    *,
    endpoint: str = "detailById.do",
) -> NormalizedFuelStationDetail:
    """``StationDetail``에서 정규화 주유소 상세 레코드를 만든다."""
    return NormalizedFuelStationDetail(
        provider_endpoint=endpoint,
        provider_station_id=detail.provider_station_id,
        provider_station_name=detail.name,
        brand_code=detail.brand_code,
        sub_brand_code=detail.sub_brand_code,
        station_type=detail.station_type,
        sigun_code=detail.sigun_code,
        address_jibun=detail.address_jibun,
        address_road=detail.address_road,
        tel=detail.tel,
        coordinates=detail.coordinates,
        katec_x=detail.katec_x,
        katec_y=detail.katec_y,
        lon=detail.lon,
        lat=detail.lat,
        has_maintenance=detail.has_maintenance,
        has_carwash=detail.has_carwash,
        has_cvs=detail.has_cvs,
        is_kpetro=detail.is_kpetro,
        prices=tuple(
            _normalize_station_detail_price(price, endpoint=endpoint, detail=detail) for price in detail.prices
        ),
        raw=_json_safe_raw_dict(detail.raw),
    )


def _normalize_station_detail_price(
    price: OilPrice,
    *,
    endpoint: str,
    detail: StationDetail,
) -> NormalizedFuelStationDetailPrice:
    return NormalizedFuelStationDetailPrice(
        provider_endpoint=endpoint,
        provider_station_id=detail.provider_station_id,
        provider_station_name=detail.name,
        provider_product_code=price.provider_product_code,
        fuel_type=price.fuel_type,
        price=price.price,
        trade_date=price.trade_date,
        trade_time=price.trade_time,
        raw=_json_safe_raw_dict(price.raw),
    )


def normalize_region_code(area: AreaCode, *, endpoint: str = "areaCode.do") -> NormalizedFuelRegionCode:
    """``AreaCode``에서 정규화 지역 코드 레코드를 만든다."""
    return NormalizedFuelRegionCode(
        provider_endpoint=endpoint,
        provider_region_code=area.code,
        provider_region_name=area.name,
        code_level=area.code_level,
        parent_sido_code=area.parent_sido_code,
        bjd_sido_prefix=area.bjd_sido_prefix,
        raw=_json_safe_raw_dict(area.raw),
    )


def _json_safe_raw_dict(raw: Any) -> dict[str, Any]:
    converted = to_json_safe_raw(raw)
    if isinstance(converted, dict):
        return converted
    return {"value": converted}
