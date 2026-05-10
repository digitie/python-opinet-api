"""오피넷 공식 5개 API 엔드포인트용 고수준 클라이언트."""

from __future__ import annotations

import os
from datetime import date, time
from typing import Any

from pykrtour import KatecPoint, PlaceCoordinate

from ._convert import strip_or_none, to_bool_yn, to_date, to_float_or_none, to_time
from ._http import _OpinetHttp
from .codes import BrandCode, ProductCode, SortOrder, StationType, opinet_sido_to_bjd
from .exceptions import OpinetAuthError, OpinetInvalidParameterError, OpinetNoDataError, OpinetServerError
from .models import AreaCode, AvgPrice, OilPrice, Station, StationDetail


def _normalize_oil(data: dict[str, Any], endpoint: str) -> list[dict[str, Any]]:
    result = data.get("RESULT")
    if not isinstance(result, dict):
        raise OpinetServerError(f"{endpoint}: RESULT must be an object")
    if "OIL" not in result:
        raise OpinetServerError(f"{endpoint}: RESULT.OIL is missing")

    oil = result["OIL"]
    if isinstance(oil, dict):
        return [oil]
    if isinstance(oil, list):
        if not all(isinstance(item, dict) for item in oil):
            raise OpinetServerError(f"{endpoint}: RESULT.OIL must contain objects")
        return oil
    raise OpinetServerError(f"{endpoint}: RESULT.OIL must be an object or list")


def _normalize_items(value: Any, field: str, endpoint: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    raise OpinetServerError(f"{endpoint}: {field} must be an object or list")


def _require_float(value: Any, field: str, endpoint: str) -> float:
    result = to_float_or_none(value)
    if result is None:
        raise ValueError(f"{field} is required")
    return result


def _require_date(value: Any, field: str, endpoint: str) -> date:
    result = to_date(value)
    if result is None:
        raise ValueError(f"{field} is required")
    return result


def _require_time(value: Any, field: str, endpoint: str) -> time:
    result = to_time(value)
    if result is None:
        raise ValueError(f"{field} is required")
    return result


def _brand_or_none(value: Any) -> BrandCode | None:
    text = strip_or_none(value)
    return BrandCode(text) if text else None


def _product_code(value: Any) -> ProductCode:
    text = strip_or_none(value)
    if text is None:
        raise ValueError("PRODCD is required")
    return ProductCode(text)


def _optional_product_code(value: Any) -> ProductCode | None:
    text = strip_or_none(value)
    return ProductCode(text) if text is not None else None


def _coerce_product_code(value: ProductCode | str, field: str = "prodcd") -> ProductCode:
    try:
        return ProductCode(value)
    except ValueError as exc:
        raise OpinetInvalidParameterError(f"{field} must be a valid Opinet product code") from exc


def _validate_area_param(area: str) -> None:
    if len(area) not in (2, 4) or not area.isdigit():
        raise OpinetInvalidParameterError("area must be a 2-digit sido or 4-digit sigungu code")
    opinet_sido_to_bjd(area if len(area) == 2 else area[:2])


def _station_type(value: Any) -> StationType:
    text = strip_or_none(value)
    if text is None:
        raise ValueError("LPG_YN is required")
    return StationType(text)


def _katec_to_place_coordinate(katec_x: float, katec_y: float) -> PlaceCoordinate:
    return PlaceCoordinate.from_katec(KatecPoint(katec_x, katec_y))


def _parse_error(endpoint: str, exc: Exception) -> OpinetServerError:
    return OpinetServerError(f"{endpoint}: failed to parse response record: {exc}")


class OpinetClient:
    """오피넷 공식 5개 API 엔드포인트 진입점."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 10.0,
        strict_empty: bool = False,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        session: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPINET_API_KEY")
        self.timeout = timeout
        self.strict_empty = strict_empty
        self._http = (
            _OpinetHttp(
                self.api_key,
                timeout=timeout,
                max_retries=max_retries,
                retry_backoff=retry_backoff,
                session=session,
            )
            if self.api_key
            else None
        )

    def _require_http(self) -> _OpinetHttp:
        if self._http is None:
            raise OpinetAuthError("OPINET_API_KEY is not set and api_key was not provided")
        return self._http

    def _handle_empty(self, rows: list[Any], endpoint: str) -> None:
        if not rows and self.strict_empty:
            raise OpinetNoDataError(f"{endpoint}: RESULT.OIL is empty")

    def get_national_average_price(self) -> list[AvgPrice]:
        """전국 주유소 평균가격을 조회한다.

        ``avgAllPrice.do``(apiId=4)를 호출하며 날짜와 가격 필드는 각각
        ``date``와 ``float``로 변환된다.
        """
        endpoint = "avgAllPrice.do"
        rows = _normalize_oil(self._require_http().get(endpoint), endpoint)
        self._handle_empty(rows, endpoint)
        parsed: list[AvgPrice] = []
        for row in rows:
            try:
                parsed.append(
                    AvgPrice(
                        trade_date=_require_date(row.get("TRADE_DT"), "TRADE_DT", endpoint),
                        product_code=_product_code(row.get("PRODCD")),
                        product_name=str(strip_or_none(row.get("PRODNM")) or ""),
                        price=_require_float(row.get("PRICE"), "PRICE", endpoint),
                        diff=_require_float(row.get("DIFF"), "DIFF", endpoint),
                        raw=row,
                    )
                )
            except (ValueError, KeyError) as exc:
                raise _parse_error(endpoint, exc) from exc
        return parsed

    def get_lowest_price_top20(
        self,
        prodcd: ProductCode | str,
        cnt: int = 10,
        area: str | None = None,
    ) -> list[Station]:
        """전국/지역별 최저가 주유소 목록을 조회한다.

        ``lowTop10.do``(apiId=2)를 호출하며 ``cnt``는 1~20만 허용한다.
        """
        if not 1 <= cnt <= 20:
            raise OpinetInvalidParameterError("cnt must be between 1 and 20")
        if area is not None:
            _validate_area_param(area)
        endpoint = "lowTop10.do"
        product_code = _coerce_product_code(prodcd)
        params: dict[str, Any] = {"prodcd": product_code.value, "cnt": cnt}
        if area is not None:
            params["area"] = area
        rows = _normalize_oil(self._require_http().get(endpoint, params=params), endpoint)
        self._handle_empty(rows, endpoint)
        return [self._build_station(row, endpoint, request_product_code=product_code) for row in rows]

    def search_stations_around(
        self,
        *,
        coordinate: PlaceCoordinate | None = None,
        katec: KatecPoint | None = None,
        radius_m: int = 5000,
        prodcd: ProductCode | str = ProductCode.GASOLINE,
        sort: SortOrder = SortOrder.PRICE,
    ) -> list[Station]:
        """주어진 좌표 반경 내 주유소를 검색한다.

        ``aroundAll.do``(apiId=3)를 호출한다. 공개 입력은
        ``pykrtour.PlaceCoordinate`` 또는 ``pykrtour.KatecPoint``만 받으며,
        응답 모델에는 ``coordinate``와 KATEC 원본 좌표가 모두 들어간다.
        """
        if (coordinate is None) == (katec is None):
            raise OpinetInvalidParameterError("pass exactly one of coordinate or katec")
        if not 1 <= radius_m <= 5000:
            raise OpinetInvalidParameterError("radius_m must be between 1 and 5000")
        if coordinate is not None:
            x, y = coordinate.to_katec().as_x_y()
        else:
            assert katec is not None
            x, y = katec.as_x_y()

        product_code = _coerce_product_code(prodcd)
        endpoint = "aroundAll.do"
        rows = _normalize_oil(
            self._require_http().get(
                endpoint,
                params={
                    "x": x,
                    "y": y,
                    "radius": radius_m,
                    "prodcd": product_code.value,
                    "sort": SortOrder(sort).value,
                },
            ),
            endpoint,
        )
        self._handle_empty(rows, endpoint)
        return [self._build_station(row, endpoint, request_product_code=product_code) for row in rows]

    def get_station_detail(self, uni_id: str) -> StationDetail:
        """주유소 ID로 상세정보를 조회한다.

        ``detailById.do``(apiId=1)를 호출한다. ``LPG_YN``은
        ``station_type``으로, ``KPETRO_YN``은 ``is_kpetro``로 매핑한다.
        """
        if not uni_id:
            raise OpinetInvalidParameterError("uni_id must not be empty")
        endpoint = "detailById.do"
        rows = _normalize_oil(self._require_http().get(endpoint, params={"id": uni_id}), endpoint)
        if not rows:
            raise OpinetNoDataError(f"{endpoint}: RESULT.OIL is empty")
        return self._build_station_detail(rows[0], endpoint)

    def get_area_codes(self, sido: str | None = None) -> list[AreaCode]:
        """시도 또는 시군구 코드를 조회한다.

        ``areaCode.do``(apiId=5)를 호출하며 코드값은 선행 0을 보존하는
        ``str``로 반환한다.
        """
        if sido is not None and (len(sido) != 2 or not sido.isdigit()):
            raise OpinetInvalidParameterError("sido must be a 2-digit code")
        if sido is not None:
            opinet_sido_to_bjd(sido)
        endpoint = "areaCode.do"
        params = {"area": sido} if sido is not None else None
        rows = _normalize_oil(self._require_http().get(endpoint, params=params), endpoint)
        self._handle_empty(rows, endpoint)
        parsed: list[AreaCode] = []
        for row in rows:
            code = strip_or_none(row.get("AREA_CD"))
            name = strip_or_none(row.get("AREA_NM"))
            if code is None or name is None:
                raise OpinetServerError(f"{endpoint}: AREA_CD and AREA_NM are required")
            parsed.append(AreaCode(code=code, name=name, raw=row))
        return parsed

    def _build_station(
        self,
        row: dict[str, Any],
        endpoint: str,
        *,
        request_product_code: ProductCode | None = None,
    ) -> Station:
        try:
            katec_x = _require_float(row.get("GIS_X_COOR"), "GIS_X_COOR", endpoint)
            katec_y = _require_float(row.get("GIS_Y_COOR"), "GIS_Y_COOR", endpoint)
            coordinate = _katec_to_place_coordinate(katec_x, katec_y)
            product_code = _optional_product_code(row.get("PRODCD")) or request_product_code
            return Station(
                uni_id=str(row["UNI_ID"]),
                name=str(strip_or_none(row.get("OS_NM")) or ""),
                brand=_brand_or_none(row.get("POLL_DIV_CO") or row.get("POLL_DIV_CD")),
                price=to_float_or_none(row.get("PRICE")),
                address_jibun=strip_or_none(row.get("VAN_ADR")),
                address_road=strip_or_none(row.get("NEW_ADR")),
                katec_x=katec_x,
                katec_y=katec_y,
                lon=coordinate.lon,
                lat=coordinate.lat,
                distance_m=to_float_or_none(row.get("DISTANCE")),
                product_code=product_code,
                product_name=strip_or_none(row.get("PRODNM")),
                trade_date=to_date(row.get("TRADE_DT")),
                trade_time=to_time(row.get("TRADE_TM")),
                raw=row,
            )
        except (ValueError, KeyError) as exc:
            raise _parse_error(endpoint, exc) from exc

    def _build_station_detail(self, row: dict[str, Any], endpoint: str) -> StationDetail:
        try:
            katec_x = _require_float(row.get("GIS_X_COOR"), "GIS_X_COOR", endpoint)
            katec_y = _require_float(row.get("GIS_Y_COOR"), "GIS_Y_COOR", endpoint)
            coordinate = _katec_to_place_coordinate(katec_x, katec_y)
            prices = tuple(
                self._build_oil_price(item, endpoint)
                for item in _normalize_items(row.get("OIL_PRICE"), "OIL_PRICE", endpoint)
            )
            sigun_code = strip_or_none(row.get("SIGUNCD"))
            if sigun_code is None:
                raise ValueError("SIGUNCD is required")
            return StationDetail(
                uni_id=str(row["UNI_ID"]),
                name=str(strip_or_none(row.get("OS_NM")) or ""),
                brand=_brand_or_none(row.get("POLL_DIV_CO") or row.get("POLL_DIV_CD")),
                sub_brand=_brand_or_none(row.get("GPOLL_DIV_CO") or row.get("GPOLL_DIV_CD")),
                station_type=_station_type(row.get("LPG_YN")),
                sigun_code=sigun_code,
                address_jibun=strip_or_none(row.get("VAN_ADR")),
                address_road=strip_or_none(row.get("NEW_ADR")),
                tel=strip_or_none(row.get("TEL")),
                katec_x=katec_x,
                katec_y=katec_y,
                lon=coordinate.lon,
                lat=coordinate.lat,
                has_maintenance=to_bool_yn(row.get("MAINT_YN")),
                has_carwash=to_bool_yn(row.get("CAR_WASH_YN")),
                has_cvs=to_bool_yn(row.get("CVS_YN")),
                is_kpetro=to_bool_yn(row.get("KPETRO_YN")),
                prices=prices,
                raw=row,
            )
        except (ValueError, KeyError) as exc:
            raise _parse_error(endpoint, exc) from exc

    def _build_oil_price(self, row: dict[str, Any], endpoint: str) -> OilPrice:
        try:
            return OilPrice(
                product_code=_product_code(row.get("PRODCD")),
                price=to_float_or_none(row.get("PRICE")),
                trade_date=_require_date(row.get("TRADE_DT"), "TRADE_DT", endpoint),
                trade_time=_require_time(row.get("TRADE_TM"), "TRADE_TM", endpoint),
                raw=row,
            )
        except (ValueError, KeyError) as exc:
            raise _parse_error(endpoint, exc) from exc
