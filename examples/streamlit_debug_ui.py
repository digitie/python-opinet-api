"""Streamlit 기반 오피넷 API 디버그 카탈로그 뷰어."""
# ruff: noqa: E402,I001

from __future__ import annotations

import json
import os
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

try:
    import pandas as pd
    import streamlit as st
except ModuleNotFoundError as exc:  # pragma: no cover - 선택 실행 도구
    raise SystemExit('Streamlit UI를 쓰려면 `pip install -e ".[debug-ui]"`를 실행하세요.') from exc

from opinet import (
    ApiCatalogItem,
    ApiParameter,
    OpinetClient,
    get_api_catalog,
    get_api_catalog_item,
    get_api_catalog_options,
    jsonable,
    save_debug_fixture,
)

OPINET_API_KEY_ENV = "OPINET_API_KEY"


def main() -> None:
    """Streamlit 디버그 앱을 실행한다."""
    st.set_page_config(page_title="Opinet API Debug", layout="wide")
    st.title("Opinet API Debug")

    # 1. Data source -> API (오피넷은 데이터소스가 하나뿐이라 카테고리 단계는 생략한다)
    st.sidebar.selectbox("Data source", ["opinet"])
    options = get_api_catalog_options()
    labels = [option["label"] for option in options]
    selected_label = st.sidebar.selectbox("API", labels)
    selected_option = options[labels.index(selected_label)]
    catalog_item = get_api_catalog_item(selected_option["value"])

    # 2. 선택한 API 설명 (무엇을 하는지 + 무엇을 반환하는지, 2줄)
    st.sidebar.caption(catalog_item.summary)
    st.sidebar.caption(f"응답: {catalog_item.response_model}")

    # 3. Environment: env var vs 수동 입력
    default_source = _default_key_source()
    environment = "manual"
    if default_source is not None:
        st.sidebar.subheader("Environment")
        environment = st.sidebar.selectbox("Environment", ["env", "manual"])
        if environment == "env":
            st.sidebar.caption(f"{OPINET_API_KEY_ENV} 값을 사용합니다. Source: {default_source}")

    # 4. Auth: 오피넷이 실제로 쓰는 쿼리 파라미터명(certkey)
    st.sidebar.subheader("Auth")
    if environment == "manual":
        api_key = st.sidebar.text_input(
            "certkey",
            value="",
            type="password",
            placeholder="직접 입력",
            help=f"기본값은 process env 또는 현재/상위 디렉터리 .env의 {OPINET_API_KEY_ENV}에서 읽습니다.",
        )
        effective_api_key = api_key
    else:
        effective_api_key = OpinetClient(api_key=None, retry_backoff=0).api_key or ""

    # 5. 서비스키 발급 링크
    st.sidebar.link_button("certkey 발급/확인", catalog_item.service_key_url)

    # 6. Timeout
    timeout = st.sidebar.number_input(
        "Timeout",
        min_value=1.0,
        max_value=60.0,
        value=10.0,
        step=1.0,
        help="API 요청 timeout seconds입니다.",
    )

    # 7. Fixture 저장 기준 디렉터리
    fixture_base_dir = _fixture_base_dir_sidebar()

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
        _raw_response_tab(catalog_item, effective_api_key, timeout=float(timeout))
    with tabs[1]:
        _pydantic_model_tab(catalog_item)
    with tabs[2]:
        _processed_result_tab(catalog_item)
    with tabs[3]:
        _validation_errors_tab(catalog_item)
    with tabs[4]:
        _debug_trace_tab(catalog_item)
    with tabs[5]:
        _fixture_tab(catalog_item, fixture_base_dir)


def _raw_response_tab(catalog_item: ApiCatalogItem, api_key: str, *, timeout: float) -> None:
    st.subheader(catalog_item.dataset_name)
    st.caption(f"opinet / {catalog_item.endpoint} / {catalog_item.function_name}")

    submitted, params, missing, extra_error = _request_form(catalog_item)

    st.subheader("Request params preview")
    st.json(
        {
            "function": catalog_item.function_name,
            "endpoint": catalog_item.endpoint,
            "params": jsonable(params),
        }
    )

    if not submitted:
        return
    if extra_error:
        st.error(extra_error)
        return
    if missing:
        st.error("필수 파라미터를 입력하세요: " + ", ".join(missing))
        return

    client = OpinetClient(api_key=api_key or None, timeout=timeout, retry_backoff=0)
    run = client.debug_fetch(catalog_item.function_name, params)
    _store_run(catalog_item, run)
    if run.error:
        st.error(run.error.get("message", "Unknown error"))
    st.json(jsonable(run.response))


def _request_form(
    catalog_item: ApiCatalogItem,
) -> tuple[bool, dict[str, Any], list[str], str | None]:
    """카탈로그의 ``required_params``/``optional_params`` 메타데이터로 입력 폼을 만든다.

    ``function_name``별 ``if``/``elif`` 위젯 분기는 없다. 위젯 종류는 각
    ``ApiParameter.kind``(string/integer/float/enum) 하나로 결정된다.
    """
    key_prefix = _selection_key(catalog_item)
    required_params = [parameter for parameter in catalog_item.parameters if parameter.required]
    optional_params = [parameter for parameter in catalog_item.parameters if not parameter.required]

    with st.form(f"request-form:{key_prefix}"):
        st.subheader("Required parameters")
        if required_params:
            required_values = _render_param_grid(required_params, key_prefix=key_prefix)
        else:
            st.caption("이 API에는 필수 파라미터가 없습니다.")
            required_values = {}

        st.subheader("Optional parameters")
        if optional_params:
            optional_values = _render_param_grid(optional_params, key_prefix=key_prefix)
        else:
            st.caption("이 API에는 선택 파라미터가 없습니다.")
            optional_values = {}

        extra_text = st.text_area(
            "Extra params JSON",
            value="{}",
            height=100,
            help="카탈로그에 없는 파라미터를 JSON object로 추가하는 escape hatch입니다.",
            key=f"{key_prefix}:extra",
        )
        submitted = st.form_submit_button("Run selected API")

    extra_error: str | None = None
    try:
        extra_params = _parse_extra_params(extra_text)
    except ValueError as exc:
        extra_params = {}
        extra_error = str(exc)

    params = {**required_values, **optional_values, **extra_params}
    missing = [parameter.name for parameter in required_params if not str(params.get(parameter.name, "")).strip()]
    return submitted, params, missing, extra_error


def _render_param_grid(specs: list[ApiParameter], *, key_prefix: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for index in range(0, len(specs), 2):
        columns = st.columns(2)
        for column, spec in zip(columns, specs[index : index + 2], strict=False):
            with column:
                values[spec.name] = _render_param_widget(spec, key_prefix=key_prefix)
    return values


def _render_param_widget(spec: ApiParameter, *, key_prefix: str) -> Any:
    widget_key = f"{key_prefix}:param:{spec.name}"
    label = f"{spec.label} ({spec.name})"
    help_text = spec.description or None
    if spec.kind == "enum" and spec.allowed_values:
        options = list(spec.allowed_values)
        default_text = str(spec.default) if spec.default is not None else ""
        default_index = options.index(default_text) if default_text in options else 0
        return st.selectbox(label, options, index=default_index, help=help_text, key=widget_key)
    placeholder = "정수" if spec.kind == "integer" else "숫자(소수 가능)" if spec.kind == "float" else ""
    default_value = str(spec.default) if spec.default is not None else ""
    return st.text_input(label, value=default_value, placeholder=placeholder, help=help_text, key=widget_key)


def _parse_extra_params(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Extra params JSON이 올바르지 않습니다: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Extra params JSON은 object여야 합니다")
    return payload


def _pydantic_model_tab(catalog_item: ApiCatalogItem) -> None:
    run = _current_run(catalog_item)
    if run is None:
        st.info("Raw Response 탭에서 선택한 API를 실행하면 여기에서 Pydantic 모델을 확인합니다.")
        return
    st.caption(catalog_item.response_model)
    if run.error:
        st.warning("실행 중 오류가 발생해 모델을 만들지 못했습니다. Validation Errors 탭도 확인하세요.")
        st.json(run.error)
        return
    st.json(jsonable(run.parsed))


def _processed_result_tab(catalog_item: ApiCatalogItem) -> None:
    run = _current_run(catalog_item)
    if run is None:
        st.info("Raw Response 탭에서 API를 실행하면 처리된 결과를 표시합니다.")
        return
    if run.error:
        st.warning("실행 중 오류가 발생해 처리된 결과가 없습니다. Validation Errors 탭을 확인하세요.")
        st.json(run.error)
        return

    data = jsonable(run.processed)
    if isinstance(data, list) and data:
        st.dataframe(pd.json_normalize(data, sep="."), width="stretch", hide_index=True)
    else:
        st.json(data)


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
    st.caption(f"credential env: {OPINET_API_KEY_ENV}")

    run = _current_run(catalog_item)
    if run is not None:
        st.subheader("Run Trace")
        st.json(run.trace_payload)


def _fixture_tab(catalog_item: ApiCatalogItem, fixture_base_dir: str) -> None:
    run = _current_run(catalog_item)
    if run is None:
        st.info("Raw Response 탭에서 API를 실행하면 fixture 저장 옵션을 표시합니다.")
        st.caption("Fixture base dir")
        st.code(fixture_base_dir, language=None)
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

    st.subheader("Fixture preview")
    st.json(
        {
            "function": run.function,
            "dataset_name": run.dataset_name,
            "fixture_dir": fixture_base_dir,
            "assertion": assertion,
        }
    )

    if st.button("Save as fixture"):
        try:
            path = save_debug_fixture(
                base_dir=fixture_base_dir,
                debug_run=run,
                case_name=case_name,
                description=description,
                assertion=assertion,
                overwrite=overwrite,
            )
        except FileExistsError as exc:
            st.error(str(exc))
        else:
            st.success(f"Saved: {path}")


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
        "required_params": ", ".join(parameter.name for parameter in item.parameters if parameter.required) or "-",
        "optional_params": ", ".join(parameter.name for parameter in item.parameters if not parameter.required) or "-",
    }


def _default_key_source() -> str | None:
    """``OPINET_API_KEY``를 process env 또는 로컬 ``.env``에서 이미 읽을 수 있는지 확인한다."""
    if os.getenv(OPINET_API_KEY_ENV, "").strip():
        return "process env"
    if OpinetClient(api_key=None, retry_backoff=0).api_key:
        return ".env"
    return None


def _fixture_base_dir_sidebar() -> str:
    st.sidebar.subheader("Fixtures")
    candidates = _fixture_dir_candidates()
    options = [str(path) for path in candidates]
    custom_label = "Custom..."
    selected = st.sidebar.selectbox("Fixture base dir", [*options, custom_label])
    if selected == custom_label:
        selected = st.sidebar.text_input(
            "Custom fixture base dir",
            value=str((PROJECT_ROOT / "tests" / "fixtures").resolve()),
        )
    st.sidebar.caption(selected)
    return selected


def _fixture_dir_candidates() -> list[Path]:
    preferred = [
        PROJECT_ROOT / "tests" / "fixtures",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "examples",
        PROJECT_ROOT,
    ]
    candidates: list[Path] = []
    for path in preferred:
        resolved = path.resolve()
        if resolved not in candidates:
            candidates.append(resolved)
    return candidates


def _store_run(catalog_item: ApiCatalogItem, run: Any) -> None:
    st.session_state["last_run"] = {
        "selection_key": _selection_key(catalog_item),
        "run": run,
    }


def _current_run(catalog_item: ApiCatalogItem) -> Any | None:
    state = st.session_state.get("last_run")
    if not isinstance(state, dict):
        return None
    if state.get("selection_key") != _selection_key(catalog_item):
        return None
    return state.get("run")


def _selection_key(catalog_item: ApiCatalogItem) -> str:
    return f"opinet:{catalog_item.dataset}:{catalog_item.function_name}"


if __name__ == "__main__":
    main()
