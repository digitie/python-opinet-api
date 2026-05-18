"""Streamlit 기반 오피넷 API 디버그 카탈로그 뷰어."""
# ruff: noqa: E402,I001

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
for module_name, module in list(sys.modules.items()):
    if module_name != "opinet" and not module_name.startswith("opinet."):
        continue
    module_file = getattr(module, "__file__", None)
    if module_file is not None and not Path(module_file).resolve().is_relative_to(SRC_DIR):
        del sys.modules[module_name]

import streamlit as st
from kraddr.base import KatecPoint, PlaceCoordinate

from opinet import (
    OpinetClient,
    ProductCode,
    SortOrder,
    get_api_catalog,
    get_api_catalog_item,
    get_api_catalog_options,
)
from opinet.catalog import ApiCatalogItem
from opinet.debug import DebugRun, jsonable, save_debug_fixture


def main() -> None:
    """Streamlit 디버그 앱을 실행한다."""
    st.set_page_config(page_title="Opinet API Debug", layout="wide")
    st.title("Opinet API Debug")

    st.sidebar.selectbox("Data source", ["opinet"])
    options = get_api_catalog_options()
    labels = [option["label"] for option in options]
    selected_label = st.sidebar.selectbox("API", labels)
    selected_option = options[labels.index(selected_label)]
    catalog_item = get_api_catalog_item(selected_option["value"])

    default_key = _default_key()
    api_key = st.sidebar.text_input(
        "certkey",
        value="",
        type="password",
        placeholder="로컬 키 사용" if default_key else "",
        help="기본값은 process env 또는 현재/상위 디렉터리 .env의 OPINET_API_KEY에서 읽습니다.",
    )
    if default_key and not api_key:
        st.sidebar.caption("로컬 인증키가 로드되었습니다.")
    st.sidebar.link_button("certkey 발급/확인", catalog_item.service_key_url)
    effective_api_key = api_key or default_key

    tabs = st.tabs(
        [
            "Raw Response",
            "Pydantic Model",
            "Processed Result",
            "Validation Errors",
            "Debug Trace",
            "Fixture / Testcase",
        ]
    )

    with tabs[0]:
        _raw_response_tab(catalog_item, effective_api_key)
    with tabs[1]:
        _pydantic_model_tab(catalog_item)
    with tabs[2]:
        _processed_result_tab(catalog_item)
    with tabs[3]:
        _validation_errors_tab(catalog_item)
    with tabs[4]:
        _debug_trace_tab(catalog_item)
    with tabs[5]:
        _fixture_tab(catalog_item)


def _raw_response_tab(catalog_item: ApiCatalogItem, api_key: str) -> None:
    st.subheader(catalog_item.dataset_name)
    st.caption(f"opinet / {catalog_item.endpoint} / {catalog_item.function_name}")

    submitted, inputs, preview, missing = _request_form(catalog_item)
    st.subheader("Request params preview")
    st.json(preview)

    if not submitted:
        return
    if missing:
        st.error("필수 파라미터를 입력하세요: " + ", ".join(missing))
        return

    client = OpinetClient(api_key=api_key or None, retry_backoff=0)
    run = _run_debug(client.debug(), catalog_item.function_name, inputs)
    st.session_state["last_run"] = {
        "selection_key": _selection_key(catalog_item),
        "run": run,
    }
    st.json(run.response)


def _request_form(
    catalog_item: ApiCatalogItem,
) -> tuple[bool, dict[str, Any], dict[str, Any], list[str]]:
    key_prefix = _selection_key(catalog_item)
    with st.form(f"request-form:{key_prefix}"):
        st.subheader("Required parameters")
        inputs = _render_inputs(catalog_item.function_name, key_prefix=key_prefix)
        submitted = st.form_submit_button("Run selected API")

    missing = _missing_required(catalog_item, inputs)
    return submitted, inputs, _request_preview(catalog_item, inputs), missing


def _render_inputs(function_name: str, *, key_prefix: str) -> dict[str, Any]:
    if function_name == "get_national_average_price":
        st.caption("이 API는 추가 입력 파라미터가 없습니다.")
        return {}
    if function_name == "get_lowest_price_top20":
        col1, col2, col3 = st.columns(3)
        with col1:
            prodcd = st.selectbox(
                "제품",
                list(ProductCode),
                format_func=lambda item: item.value,
                key=f"{key_prefix}:prodcd",
            )
        with col2:
            cnt = st.number_input(
                "cnt",
                min_value=1,
                max_value=20,
                value=10,
                key=f"{key_prefix}:cnt",
            )
        with col3:
            area = st.text_input(
                "area",
                placeholder="시도 2자리 또는 시군구 4자리",
                key=f"{key_prefix}:area",
            )
        return {"prodcd": prodcd, "cnt": cnt, "area": area}
    if function_name == "search_stations_around":
        coordinate_mode = st.radio(
            "좌표",
            ["WGS84", "KATEC"],
            horizontal=True,
            key=f"{key_prefix}:coordinate-mode",
        )
        if coordinate_mode == "WGS84":
            col1, col2 = st.columns(2)
            with col1:
                lon = st.number_input("lon", value=127.0276, format="%.6f", key=f"{key_prefix}:lon")
            with col2:
                lat = st.number_input("lat", value=37.4979, format="%.6f", key=f"{key_prefix}:lat")
            coordinate = PlaceCoordinate(lat=lat, lon=lon)
            katec = None
        else:
            col1, col2 = st.columns(2)
            with col1:
                x = st.number_input("KATEC X", value=314871.8, format="%.4f", key=f"{key_prefix}:x")
            with col2:
                y = st.number_input("KATEC Y", value=544012.0, format="%.4f", key=f"{key_prefix}:y")
            coordinate = None
            katec = KatecPoint(x, y)

        col1, col2, col3 = st.columns(3)
        with col1:
            radius_m = st.number_input(
                "radius_m",
                min_value=1,
                max_value=5000,
                value=3000,
                key=f"{key_prefix}:radius",
            )
        with col2:
            prodcd = st.selectbox(
                "prodcd",
                list(ProductCode),
                format_func=lambda item: item.value,
                key=f"{key_prefix}:around-prodcd",
            )
        with col3:
            sort = st.selectbox(
                "sort",
                list(SortOrder),
                format_func=lambda item: item.value,
                key=f"{key_prefix}:sort",
            )
        return {
            "coordinate": coordinate,
            "katec": katec,
            "radius_m": radius_m,
            "prodcd": prodcd,
            "sort": sort,
        }
    if function_name == "get_station_detail":
        return {
            "uni_id": st.text_input(
                "uni_id",
                value="A0010207",
                help="오피넷 UNI_ID입니다.",
                key=f"{key_prefix}:uni_id",
            )
        }
    if function_name == "get_area_codes":
        return {
            "sido": st.text_input(
                "sido",
                placeholder="생략하면 시도 목록",
                key=f"{key_prefix}:sido",
            )
        }
    raise ValueError(f"unknown function: {function_name}")


def _run_debug(debug_client: Any, function_name: str, inputs: dict[str, Any]) -> DebugRun:
    if function_name == "get_national_average_price":
        return debug_client.get_national_average_price()
    if function_name == "get_lowest_price_top20":
        return debug_client.get_lowest_price_top20(
            inputs["prodcd"],
            cnt=int(inputs["cnt"]),
            area=inputs["area"] or None,
        )
    if function_name == "search_stations_around":
        return debug_client.search_stations_around(
            coordinate=inputs["coordinate"],
            katec=inputs["katec"],
            radius_m=int(inputs["radius_m"]),
            prodcd=inputs["prodcd"],
            sort=inputs["sort"],
        )
    if function_name == "get_station_detail":
        return debug_client.get_station_detail(inputs["uni_id"])
    if function_name == "get_area_codes":
        return debug_client.get_area_codes(inputs["sido"] or None)
    raise ValueError(f"unknown function: {function_name}")


def _pydantic_model_tab(catalog_item: ApiCatalogItem) -> None:
    run = _current_run(catalog_item)
    if run is None:
        st.info("Raw Response 탭에서 선택한 API를 실행하면 여기에서 Pydantic 모델을 확인합니다.")
        return
    if run.error:
        st.warning("모델 파싱 전 실행 오류가 발생했습니다. Validation Errors 탭을 확인하세요.")
        return
    st.caption(catalog_item.response_model)
    st.json(jsonable(run.parsed))


def _processed_result_tab(catalog_item: ApiCatalogItem) -> None:
    run = _current_run(catalog_item)
    if run is None:
        st.info("Raw Response 탭에서 API를 실행하면 처리된 row preview를 표시합니다.")
        return
    if run.error or run.processed is None:
        st.info("표시할 처리 결과가 없습니다.")
        return

    payload = jsonable(run.processed)
    rows = _rows_for_dataframe(payload)
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    st.json(payload)


def _validation_errors_tab(catalog_item: ApiCatalogItem) -> None:
    run = _current_run(catalog_item)
    if run is None:
        st.info("아직 실행된 API가 없습니다.")
        return
    if run.error is None:
        st.success("현재 실행 결과에서 validation error가 없습니다.")
        return
    st.error(run.error.get("message", "Unknown error"))
    st.json(run.error)


def _debug_trace_tab(catalog_item: ApiCatalogItem) -> None:
    st.subheader("Catalog")
    st.dataframe(
        [_catalog_row(item) for item in get_api_catalog()],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Selected API")
    st.json(catalog_item.to_dict())
    st.link_button("certkey 발급/확인", catalog_item.service_key_url)
    st.caption("credential env: OPINET_API_KEY")

    run = _current_run(catalog_item)
    if run is not None:
        st.subheader("Run Trace")
        st.json(run.trace_payload)


def _fixture_tab(catalog_item: ApiCatalogItem) -> None:
    run = _current_run(catalog_item)
    if run is None:
        st.info("Raw Response 탭에서 API를 실행하면 fixture 저장 옵션을 표시합니다.")
        return

    case_name = st.text_input("Case name", value=f"{run.function}-case")
    description = st.text_area("Description", value=f"{run.dataset_name} fixture")
    assertion_mode = st.selectbox("Assertion mode", ["snapshot", "schema_only", "required_fields", "count"])
    exclude_fields_raw = st.text_input("Exclude fields", value="fetched_at, request_id, updated_at")
    required_fields_raw = st.text_input("Required fields", value="")
    overwrite = st.checkbox("Overwrite existing fixture", value=False)
    assertion = {
        "mode": assertion_mode,
        "exclude_fields": [value.strip() for value in exclude_fields_raw.split(",") if value.strip()],
        "required_fields": [value.strip() for value in required_fields_raw.split(",") if value.strip()],
    }
    st.json(
        {
            "function": run.function,
            "dataset_name": run.dataset_name,
            "fixture_dir": "tests/fixtures",
            "assertion": assertion,
        }
    )
    if st.button("Save as fixture"):
        try:
            path = save_debug_fixture(
                base_dir=PROJECT_ROOT / "tests" / "fixtures",
                debug_run=run,
                case_name=case_name,
                description=description,
                assertion=assertion,
                overwrite=overwrite,
            )
        except FileExistsError as exc:
            st.error(str(exc))
        else:
            st.success(f"Saved: {path.relative_to(PROJECT_ROOT)}")


def _missing_required(catalog_item: ApiCatalogItem, inputs: dict[str, Any]) -> list[str]:
    missing = []
    for parameter in catalog_item.parameters:
        if not parameter.required:
            continue
        value = inputs.get(parameter.name)
        if value is None or str(value).strip() == "":
            missing.append(parameter.name)
    return missing


def _request_preview(catalog_item: ApiCatalogItem, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "endpoint": catalog_item.endpoint,
        "method": catalog_item.method,
        "credential_param": "certkey",
        "out": "json",
        "input": jsonable(inputs),
    }


def _selection_key(catalog_item: ApiCatalogItem) -> str:
    return f"opinet:{catalog_item.dataset}:{catalog_item.function_name}"


def _current_run(catalog_item: ApiCatalogItem) -> DebugRun | None:
    state = st.session_state.get("last_run")
    if not isinstance(state, dict):
        return None
    if state.get("selection_key") != _selection_key(catalog_item):
        return None
    run = state.get("run")
    return run if isinstance(run, DebugRun) else None


def _rows_for_dataframe(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _catalog_row(item: ApiCatalogItem) -> dict[str, Any]:
    return {
        "dataset_name": item.dataset_name,
        "function_name": item.function_name,
        "endpoint": item.endpoint,
        "api_id": item.api_id,
        "dataset": item.dataset,
        "method": item.method,
        "response_model": item.response_model,
        "official": item.official,
    }


def _default_key() -> str:
    return OpinetClient(api_key=None, retry_backoff=0).api_key or ""


if __name__ == "__main__":
    main()
