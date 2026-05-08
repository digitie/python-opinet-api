"""오피넷 API에서 사용하는 enum과 코드 매핑."""

from __future__ import annotations

from enum import StrEnum

from .exceptions import OpinetInvalidParameterError


class ProductCode(StrEnum):
    """오피넷 제품 코드."""

    GASOLINE = "B027"
    GASOLINE_PREMIUM = "B034"
    DIESEL = "D047"
    KEROSENE = "C004"
    LPG = "K015"


class FuelType(StrEnum):
    """애플리케이션 연동용 표준 유종."""

    GASOLINE = "gasoline"
    PREMIUM_GASOLINE = "premium_gasoline"
    DIESEL = "diesel"
    LPG = "lpg"
    KEROSENE = "kerosene"
    UNKNOWN = "unknown"


CanonicalFuelType = FuelType


class BrandCode(StrEnum):
    """오피넷 상표 코드."""

    SKE = "SKE"
    GSC = "GSC"
    HDO = "HDO"
    SOL = "SOL"
    RTE = "RTE"
    RTX = "RTX"
    NHO = "NHO"
    ETC = "ETC"
    E1G = "E1G"
    SKG = "SKG"


class SortOrder(StrEnum):
    """검색 정렬 옵션."""

    PRICE = "1"
    DISTANCE = "2"


class StationType(StrEnum):
    """API의 ``LPG_YN`` 필드로 표현되는 업종 구분."""

    GAS_STATION = "N"
    LPG_STATION = "Y"
    BOTH = "C"


ALDDLE_BRANDS = frozenset({BrandCode.RTE, BrandCode.RTX, BrandCode.NHO})

PRODUCT_CODE_TO_FUEL_TYPE: dict[ProductCode, FuelType] = {
    ProductCode.GASOLINE: FuelType.GASOLINE,
    ProductCode.GASOLINE_PREMIUM: FuelType.PREMIUM_GASOLINE,
    ProductCode.DIESEL: FuelType.DIESEL,
    ProductCode.KEROSENE: FuelType.KEROSENE,
    ProductCode.LPG: FuelType.LPG,
}

FUEL_TYPE_TO_PRODUCT_CODE: dict[FuelType, ProductCode] = {
    fuel_type: product_code for product_code, fuel_type in PRODUCT_CODE_TO_FUEL_TYPE.items()
}

OPINET_TO_BJD: dict[str, str] = {
    "01": "11",
    "02": "41",
    "03": "42",
    "04": "43",
    "05": "44",
    "06": "45",
    "07": "46",
    "08": "47",
    "09": "48",
    "10": "26",
    "11": "50",
    "14": "27",
    "15": "28",
    "16": "29",
    "17": "30",
    "18": "31",
    "19": "36",
}

BJD_TO_OPINET: dict[str, str] = {value: key for key, value in OPINET_TO_BJD.items()}
BJD_LEGACY_TO_NEW: dict[str, str] = {"42": "51", "45": "52"}
BJD_NEW_TO_LEGACY: dict[str, str] = {value: key for key, value in BJD_LEGACY_TO_NEW.items()}


def is_alddle(brand: BrandCode | str | None) -> bool:
    """상표 코드가 알뜰주유소 계열인지 반환한다."""
    if brand is None:
        return False
    try:
        return BrandCode(brand) in ALDDLE_BRANDS
    except ValueError:
        return False


def product_code_to_fuel_type(product_code: ProductCode | str) -> FuelType:
    """오피넷 제품 코드를 표준 유종으로 변환한다."""
    try:
        normalized = ProductCode(product_code)
    except ValueError as exc:
        raise OpinetInvalidParameterError(f"unknown Opinet product code: {product_code!r}") from exc
    return PRODUCT_CODE_TO_FUEL_TYPE[normalized]


def fuel_type_to_product_code(fuel_type: FuelType | str) -> ProductCode:
    """표준 유종을 대응하는 오피넷 제품 코드로 변환한다."""
    try:
        normalized = FuelType(fuel_type)
    except ValueError as exc:
        raise OpinetInvalidParameterError(f"unknown fuel type: {fuel_type!r}") from exc
    if normalized is FuelType.UNKNOWN:
        raise OpinetInvalidParameterError("FuelType.UNKNOWN cannot be mapped to an Opinet product code")
    return FUEL_TYPE_TO_PRODUCT_CODE[normalized]


def opinet_sido_to_bjd(opinet_code: str) -> str:
    """오피넷 2자리 시도 코드를 법정동 시도 접두어로 변환한다."""
    if opinet_code not in OPINET_TO_BJD:
        raise OpinetInvalidParameterError(
            f"unknown opinet sido code: {opinet_code!r}. Valid codes are 01-11 and 14-19."
        )
    return OPINET_TO_BJD[opinet_code]


def bjd_sido_to_opinet(bjd_code: str) -> str:
    """법정동 2자리 시도 접두어를 오피넷 시도 코드로 변환한다."""
    normalized = BJD_NEW_TO_LEGACY.get(bjd_code, bjd_code)
    if normalized not in BJD_TO_OPINET:
        raise OpinetInvalidParameterError(f"unknown BJD sido code: {bjd_code!r}")
    return BJD_TO_OPINET[normalized]
