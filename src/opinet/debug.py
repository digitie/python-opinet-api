"""디버그 UI와 fixture replay를 위한 순수 Python 헬퍼."""

from __future__ import annotations

import json
import re
import traceback
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from ._http import _OpinetHttp
from .catalog import ApiCatalogItem, get_api_catalog_item
from .client import OpinetClient, _coerce_product_code, _coerce_sort_order, _coordinate_query_params, _validate_area_param
from .codes import ProductCode, SortOrder
from .exceptions import OpinetInvalidParameterError

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "x-api-key",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "certkey",
    }
)

DEFAULT_ASSERTION: dict[str, Any] = {
    "mode": "snapshot",
    "exclude_fields": ["fetched_at", "request_id", "updated_at"],
    "required_fields": [],
}

ENDPOINT_BY_FUNCTION = MappingProxyType(
    {
        "get_national_average_price": "avgAllPrice.do",
        "get_lowest_price_top20": "lowTop10.do",
        "search_stations_around": "aroundAll.do",
        "get_station_detail": "detailById.do",
        "get_area_codes": "areaCode.do",
    }
)

SUPPORTED_DEBUG_FUNCTIONS = tuple(ENDPOINT_BY_FUNCTION)


@dataclass(frozen=True, slots=True)
class DebugRun:
    """디버그 UI가 표시하거나 fixture로 저장할 단일 실행 결과."""

    function: str
    input: dict[str, Any]
    request: dict[str, Any]
    response: dict[str, Any]
    parsed: Any
    processed: Any
    trace: tuple[str, ...]
    catalog_item: ApiCatalogItem
    error: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        """실행 중 예외가 없었는지 반환한다."""
        return self.error is None

    @property
    def dataset_name(self) -> str:
        """디버그 UI에 표시할 사람이 읽기 쉬운 데이터셋명을 반환한다."""
        return self.catalog_item.dataset_name

    @property
    def service_key_url(self) -> str:
        """선택된 API에 사용할 서비스키 발급 링크를 반환한다."""
        return self.catalog_item.service_key_url

    @property
    def trace_payload(self) -> dict[str, Any]:
        """Streamlit Debug Trace 탭에 바로 표시할 구조화 payload를 반환한다."""
        return {
            "dataset_name": self.catalog_item.dataset_name,
            "service_key_url": self.catalog_item.service_key_url,
            "catalog_item": self.catalog_item.to_dict(),
            "trace": list(self.trace),
            "error": self.error,
        }


def jsonable(obj: Any) -> Any:
    """Pydantic, dataclass, enum, 날짜 값을 JSON 저장 가능한 값으로 변환한다."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if obj is None or isinstance(obj, bool | int | float | str):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime | date | time):
        return obj.isoformat()
    if isinstance(obj, MappingABC):
        return {str(key): jsonable(value) for key, value in obj.items()}
    if isinstance(obj, list | tuple | set | frozenset):
        return [jsonable(value) for value in obj]
    if is_dataclass(obj) and not isinstance(obj, type):
        return {field.name: jsonable(getattr(obj, field.name)) for field in fields(obj)}
    return str(obj)


def redact_sensitive(obj: Any) -> Any:
    """fixture 저장 전에 인증/토큰 계열 값을 재귀적으로 마스킹한다."""
    if isinstance(obj, MappingABC):
        redacted: dict[str, Any] = {}
        for key, value in obj.items():
            key_text = str(key)
            if key_text.strip().lower() in SENSITIVE_KEYS:
                redacted[key_text] = "<REDACTED>"
            else:
                redacted[key_text] = redact_sensitive(value)
        return redacted
    if isinstance(obj, list | tuple | set | frozenset):
        return [redact_sensitive(value) for value in obj]
    return obj


def slugify_case_name(name: str) -> str:
    """case 이름을 경로 구분자 없는 파일명 slug로 변환한다."""
    slug = re.sub(r"[^\w.-]+", "-", name.strip(), flags=re.UNICODE).strip("-._").lower()
    return slug or "case"


def build_fixture(
    *,
    function_name: str,
    case_name: str,
    description: str,
    input_data: dict[str, Any],
    request_data: dict[str, Any],
    response_data: dict[str, Any],
    parsed_result: Any,
    processed_result: Any,
    assertion: dict[str, Any] | None = None,
    library_version: str | None = None,
) -> dict[str, Any]:
    """디버그 실행 결과를 표준 fixture dict로 만든다."""
    safe_case_name = slugify_case_name(case_name)
    catalog_item = get_api_catalog_item(function_name=function_name)
    return {
        "name": safe_case_name,
        "function": function_name,
        "description": description,
        "catalog": catalog_item.to_dict(),
        "input": redact_sensitive(jsonable(input_data)),
        "request": redact_sensitive(jsonable(request_data)),
        "response": redact_sensitive(jsonable(response_data)),
        "parsed": redact_sensitive(jsonable(parsed_result)),
        "processed": redact_sensitive(jsonable(processed_result)),
        "assertion": assertion or DEFAULT_ASSERTION.copy(),
        "meta": {
            "created_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
            "library_version": library_version if library_version is not None else _installed_version(),
            "source": "debug_ui",
        },
    }


def save_fixture(
    *,
    base_dir: str | Path,
    function_name: str,
    case_name: str,
    description: str,
    input_data: dict[str, Any],
    request_data: dict[str, Any],
    response_data: dict[str, Any],
    parsed_result: Any,
    processed_result: Any,
    assertion: dict[str, Any] | None = None,
    library_version: str | None = None,
    overwrite: bool = False,
) -> Path:
    """표준 fixture JSON 파일을 저장하고 저장 경로를 반환한다."""
    fixture = build_fixture(
        function_name=function_name,
        case_name=case_name,
        description=description,
        input_data=input_data,
        request_data=request_data,
        response_data=response_data,
        parsed_result=parsed_result,
        processed_result=processed_result,
        assertion=assertion,
        library_version=library_version,
    )
    fixture_dir = Path(base_dir) / slugify_case_name(function_name)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = fixture_dir / f"{fixture['name']}.json"
    if fixture_path.exists() and not overwrite:
        raise FileExistsError(f"Fixture already exists: {fixture_path}")
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return fixture_path


def save_debug_fixture(
    *,
    base_dir: str | Path,
    debug_run: DebugRun,
    case_name: str,
    description: str = "",
    assertion: dict[str, Any] | None = None,
    library_version: str | None = None,
    overwrite: bool = False,
) -> Path:
    """``DebugRun``을 표준 fixture JSON 파일로 저장한다."""
    return save_fixture(
        base_dir=base_dir,
        function_name=debug_run.function,
        case_name=case_name,
        description=description,
        input_data=debug_run.input,
        request_data=debug_run.request,
        response_data=debug_run.response,
        parsed_result=debug_run.parsed,
        processed_result=debug_run.processed,
        assertion=assertion,
        library_version=library_version,
        overwrite=overwrite,
    )


def parse_debug_response(
    function_name: str,
    response_body: dict[str, Any],
    *,
    input_data: MappingABC[str, Any] | None = None,
) -> Any:
    """fixture의 raw response body를 공식 클라이언트 모델로 파싱한다."""
    client = OpinetClient(api_key="fixture-replay", retry_backoff=0)
    input_data = input_data or {}
    if function_name == "get_national_average_price":
        return client._parse_national_average_price_response(response_body)
    if function_name == "get_lowest_price_top20":
        product_code = _coerce_product_code(input_data.get("prodcd", ProductCode.GASOLINE))
        return client._parse_station_list_response(
            response_body,
            "lowTop10.do",
            request_product_code=product_code,
        )
    if function_name == "search_stations_around":
        product_code = _coerce_product_code(input_data.get("prodcd", ProductCode.GASOLINE))
        return client._parse_station_list_response(
            response_body,
            "aroundAll.do",
            request_product_code=product_code,
        )
    if function_name == "get_station_detail":
        return client._parse_station_detail_response(response_body)
    if function_name == "get_area_codes":
        return client._parse_area_codes_response(response_body)
    raise ValueError(f"Unknown debug fixture function: {function_name}")


def process_debug_result(function_name: str, parsed: Any) -> Any:
    """파싱된 모델을 normalized processed 결과로 변환한다."""
    endpoint = _endpoint_for(function_name)
    if isinstance(parsed, list):
        return [item.to_normalized(endpoint=endpoint) if hasattr(item, "to_normalized") else item for item in parsed]
    if hasattr(parsed, "to_normalized"):
        return parsed.to_normalized(endpoint=endpoint)
    return parsed


def replay_fixture_case(case: MappingABC[str, Any]) -> Any:
    """표준 fixture dict를 파싱/가공하고 assertion을 수행한 뒤 actual 값을 반환한다."""
    function_name = str(case["function"])
    response = case["response"]
    if not isinstance(response, MappingABC):
        raise ValueError("fixture response must be an object")
    body = response.get("body")
    if not isinstance(body, dict):
        raise ValueError("fixture response.body must be an object")

    parsed = parse_debug_response(function_name, body, input_data=case.get("input"))
    processed = process_debug_result(function_name, parsed)
    actual = jsonable(processed)
    assert_case(actual, case.get("processed"), case.get("assertion", DEFAULT_ASSERTION))
    return actual


def remove_fields(obj: Any, exclude_fields: list[str]) -> Any:
    """dict/list 구조에서 지정한 key 또는 dotted path를 제거한다."""
    excludes = set(exclude_fields)

    def _remove(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                if key_text in excludes or child_path in excludes:
                    continue
                result[key_text] = _remove(item, child_path)
            return result
        if isinstance(value, list):
            return [_remove(item, path) for item in value]
        return value

    return _remove(obj, "")


def assert_case(actual: Any, expected: Any, assertion: MappingABC[str, Any] | None) -> None:
    """fixture assertion 설정에 따라 actual/expected를 비교한다."""
    assertion = assertion or DEFAULT_ASSERTION
    mode = assertion.get("mode", "snapshot")
    if mode == "snapshot":
        exclude_fields = list(assertion.get("exclude_fields", []))
        assert remove_fields(actual, exclude_fields) == remove_fields(expected, exclude_fields)
        return
    if mode == "schema_only":
        assert actual is not None
        return
    if mode == "required_fields":
        required_fields = list(assertion.get("required_fields", []))
        for field in required_fields:
            assert _has_required_field(actual, str(field))
        return
    if mode == "count":
        if isinstance(actual, list):
            expected_count = expected.get("count") if isinstance(expected, dict) else len(expected)
            assert len(actual) == expected_count
            return
        if isinstance(actual, dict) and isinstance(expected, dict):
            assert actual.get("count") == expected.get("count")
            return
        raise AssertionError("count assertion requires list or dict values")
    raise ValueError(f"Unknown assertion mode: {mode}")


class OpinetDebugClient:
    """공식 클라이언트 실행 결과를 DebugRun 형태로 수집하는 래퍼."""

    def __init__(self, client: OpinetClient) -> None:
        self._client = client

    def get_national_average_price(self, *, raise_errors: bool = False) -> DebugRun:
        """전국 평균가 API를 실행하고 디버그 결과를 반환한다."""
        return self._run(
            function_name="get_national_average_price",
            input_data={},
            params=None,
            raise_errors=raise_errors,
        )

    def get_lowest_price_top20(
        self,
        prodcd: ProductCode | str,
        cnt: int = 10,
        area: str | None = None,
        *,
        raise_errors: bool = False,
    ) -> DebugRun:
        """최저가 Top 20 API를 실행하고 디버그 결과를 반환한다."""
        input_data = {"prodcd": jsonable(prodcd), "cnt": cnt, "area": area}
        try:
            if not 1 <= cnt <= 20:
                raise OpinetInvalidParameterError("cnt must be between 1 and 20")
            if area is not None:
                _validate_area_param(area)
            product_code = _coerce_product_code(prodcd)
            params: dict[str, Any] = {"prodcd": product_code.value, "cnt": cnt}
            if area is not None:
                params["area"] = area
        except Exception as exc:
            return self._error_run("get_lowest_price_top20", input_data, None, exc, raise_errors)
        return self._run(
            function_name="get_lowest_price_top20",
            input_data=input_data,
            params=params,
            raise_errors=raise_errors,
        )

    def search_stations_around(
        self,
        *,
        lon: float | None = None,
        lat: float | None = None,
        katec_x: float | None = None,
        katec_y: float | None = None,
        radius_m: int = 5000,
        prodcd: ProductCode | str = ProductCode.GASOLINE,
        sort: SortOrder | str = SortOrder.PRICE,
        raise_errors: bool = False,
    ) -> DebugRun:
        """주변 주유소 검색 API를 실행하고 디버그 결과를 반환한다."""
        input_data = {
            "lon": lon,
            "lat": lat,
            "katec_x": katec_x,
            "katec_y": katec_y,
            "radius_m": radius_m,
            "prodcd": jsonable(prodcd),
            "sort": jsonable(sort),
        }
        try:
            if not 1 <= radius_m <= 5000:
                raise OpinetInvalidParameterError("radius_m must be between 1 and 5000")
            x, y = _coordinate_query_params(lon=lon, lat=lat, katec_x=katec_x, katec_y=katec_y)
            product_code = _coerce_product_code(prodcd)
            sort_order = _coerce_sort_order(sort)
        except Exception as exc:
            return self._error_run("search_stations_around", input_data, None, exc, raise_errors)
        return self._run(
            function_name="search_stations_around",
            input_data=input_data,
            params={
                "x": x,
                "y": y,
                "radius": radius_m,
                "prodcd": product_code.value,
                "sort": sort_order.value,
            },
            raise_errors=raise_errors,
        )

    def get_station_detail(self, uni_id: str, *, raise_errors: bool = False) -> DebugRun:
        """주유소 상세 API를 실행하고 디버그 결과를 반환한다."""
        input_data = {"uni_id": uni_id}
        if not uni_id:
            return self._error_run(
                "get_station_detail",
                input_data,
                None,
                OpinetInvalidParameterError("uni_id must not be empty"),
                raise_errors,
            )
        return self._run(
            function_name="get_station_detail",
            input_data=input_data,
            params={"id": uni_id},
            raise_errors=raise_errors,
        )

    def get_area_codes(self, sido: str | None = None, *, raise_errors: bool = False) -> DebugRun:
        """지역 코드 API를 실행하고 디버그 결과를 반환한다."""
        input_data = {"sido": sido}
        try:
            if sido is not None and (len(sido) != 2 or not sido.isdigit()):
                raise OpinetInvalidParameterError("sido must be a 2-digit code")
            if sido is not None:
                _validate_area_param(sido)
        except Exception as exc:
            return self._error_run("get_area_codes", input_data, None, exc, raise_errors)
        return self._run(
            function_name="get_area_codes",
            input_data=input_data,
            params={"area": sido} if sido is not None else None,
            raise_errors=raise_errors,
        )

    def _run(
        self,
        *,
        function_name: str,
        input_data: dict[str, Any],
        params: dict[str, Any] | None,
        raise_errors: bool,
    ) -> DebugRun:
        endpoint = _endpoint_for(function_name)
        catalog_item = get_api_catalog_item(function_name=function_name)
        request = _request_snapshot(endpoint, params)
        trace: list[str] = [
            f"catalog selected: {catalog_item.dataset_name} ({catalog_item.endpoint})",
            f"service key url: {catalog_item.service_key_url}",
            f"prepared request for {endpoint}",
        ]
        try:
            body = self._client._require_http().get(endpoint, params=params)
            response = {"status_code": 200, "headers": {}, "body": body}
            trace.append("received JSON response")
            parsed = parse_debug_response(function_name, body, input_data=input_data)
            if isinstance(parsed, list):
                self._client._handle_empty(parsed, endpoint)
            trace.append("parsed response into client models")
            processed = process_debug_result(function_name, parsed)
            trace.append("converted parsed result into normalized records")
            return DebugRun(
                function=function_name,
                input=redact_sensitive(jsonable(input_data)),
                request=request,
                response=response,
                parsed=parsed,
                processed=processed,
                trace=tuple(trace),
                catalog_item=catalog_item,
            )
        except Exception as exc:
            if raise_errors:
                raise
            trace.append(f"failed: {type(exc).__name__}")
            return DebugRun(
                function=function_name,
                input=redact_sensitive(jsonable(input_data)),
                request=request,
                response={},
                parsed=None,
                processed=None,
                trace=tuple(trace),
                catalog_item=catalog_item,
                error=_error_dict(exc),
            )

    def _error_run(
        self,
        function_name: str,
        input_data: dict[str, Any],
        params: dict[str, Any] | None,
        exc: Exception,
        raise_errors: bool,
    ) -> DebugRun:
        if raise_errors:
            raise exc
        endpoint = _endpoint_for(function_name)
        catalog_item = get_api_catalog_item(function_name=function_name)
        return DebugRun(
            function=function_name,
            input=redact_sensitive(jsonable(input_data)),
            request=_request_snapshot(endpoint, params),
            response={},
            parsed=None,
            processed=None,
            trace=(
                f"catalog selected: {catalog_item.dataset_name} ({catalog_item.endpoint})",
                f"service key url: {catalog_item.service_key_url}",
                f"validation failed before request: {type(exc).__name__}",
            ),
            catalog_item=catalog_item,
            error=_error_dict(exc),
        )


def _endpoint_for(function_name: str) -> str:
    try:
        return ENDPOINT_BY_FUNCTION[function_name]
    except KeyError as exc:
        raise ValueError(f"Unknown debug function: {function_name}") from exc


def _request_snapshot(endpoint: str, params: dict[str, Any] | None) -> dict[str, Any]:
    query = {"certkey": "<REDACTED>", "out": "json"}
    if params:
        query.update(jsonable(params))
    return {
        "method": "GET",
        "url": _OpinetHttp.BASE_URL + endpoint,
        "query": query,
        "headers": {},
    }


def _error_dict(exc: Exception) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }


def _installed_version() -> str | None:
    try:
        return version("python-opinet-api")
    except PackageNotFoundError:
        return None


def _has_required_field(actual: Any, field: str) -> bool:
    if isinstance(actual, list):
        return bool(actual) and all(_has_required_field(item, field) for item in actual)
    if not isinstance(actual, dict):
        return False
    current: Any = actual
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True
