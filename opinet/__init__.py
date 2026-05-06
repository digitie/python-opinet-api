"""Unofficial Python client for the Korean Opinet fuel price API."""

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
from .models import AreaCode, AvgPrice, KatecPoint, OilPrice, Station, StationCoordinates, StationDetail, Wgs84Point

__all__ = [
    "AreaCode",
    "AvgPrice",
    "BrandCode",
    "CanonicalFuelType",
    "FuelType",
    "KatecPoint",
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
    "StationCoordinates",
    "StationDetail",
    "StationType",
    "Wgs84Point",
    "bjd_sido_to_opinet",
    "fuel_type_to_product_code",
    "is_alddle",
    "opinet_sido_to_bjd",
    "product_code_to_fuel_type",
]
