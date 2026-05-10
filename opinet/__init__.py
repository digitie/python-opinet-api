"""한국 오피넷 유가 API의 비공식 Python 클라이언트."""

from .client import OpinetClient
from .codes import (
    BrandCode,
    CanonicalFuelType,
    FuelType,
    ProductCode,
    SortOrder,
    StationType,
    bjd_sido_to_opinet,
    fuel_type_to_product_code,
    is_alddle,
    opinet_sido_to_bjd,
    product_code_to_fuel_type,
)
from .exceptions import (
    OpinetAuthError,
    OpinetError,
    OpinetInvalidParameterError,
    OpinetNetworkError,
    OpinetNoDataError,
    OpinetRateLimitError,
    OpinetServerError,
)
from .models import AreaCode, AvgPrice, OilPrice, Station, StationDetail
from .normalized import (
    NormalizedFuelAverage,
    NormalizedFuelRegionCode,
    NormalizedFuelStation,
    NormalizedFuelStationDetail,
    NormalizedFuelStationDetailPrice,
    raw_to_json_safe,
    to_json_safe_raw,
)

__all__ = [
    "AreaCode",
    "AvgPrice",
    "BrandCode",
    "CanonicalFuelType",
    "FuelType",
    "NormalizedFuelAverage",
    "NormalizedFuelRegionCode",
    "NormalizedFuelStation",
    "NormalizedFuelStationDetail",
    "NormalizedFuelStationDetailPrice",
    "OilPrice",
    "OpinetAuthError",
    "OpinetClient",
    "OpinetError",
    "OpinetInvalidParameterError",
    "OpinetNetworkError",
    "OpinetNoDataError",
    "OpinetRateLimitError",
    "OpinetServerError",
    "ProductCode",
    "SortOrder",
    "Station",
    "StationDetail",
    "StationType",
    "bjd_sido_to_opinet",
    "fuel_type_to_product_code",
    "is_alddle",
    "opinet_sido_to_bjd",
    "product_code_to_fuel_type",
    "raw_to_json_safe",
    "to_json_safe_raw",
]
