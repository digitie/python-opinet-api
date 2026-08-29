"""디버그 실행, fixture 저장, replay 헬퍼 테스트."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from opinet import OpinetClient, ProductCode
from opinet.debug import (
    DebugRun,
    assert_case,
    build_fixture,
    jsonable,
    parse_debug_response,
    process_debug_result,
    redact_sensitive,
    replay_fixture_case,
    save_debug_fixture,
    save_fixture,
    slugify_case_name,
)
from opinet.exceptions import OpinetAuthError, OpinetInvalidParameterError

OPINET_BASE_URL = "https://www.opinet.co.kr/api/"


def test_debug_client_collects_area_code_run(load_fixture, mock_opinet) -> None:
    mock_opinet.add("areaCode.do", json=load_fixture("area_code_root.json"))

    run = OpinetClient("secret-key", retry_backoff=0).debug().get_area_codes()

    assert isinstance(run, DebugRun)
    assert run.ok is True
    assert run.function == "get_area_codes"
    assert run.request["query"]["certkey"] == "<REDACTED>"
    assert run.request["query"]["out"] == "json"
    assert run.response["body"]["RESULT"]["OIL"][0]["AREA_CD"] == "01"
    assert len(run.parsed) == 17
    assert run.processed[0].provider_region_code == "01"
    assert run.dataset_name == "오피넷 시도/시군구 코드"
    assert run.service_key_url == "https://www.opinet.co.kr/user/custapi/openApiNew.do"
    assert run.catalog_item.dataset_name == "오피넷 시도/시군구 코드"
    assert run.trace_payload["catalog_item"]["dataset_name"] == "오피넷 시도/시군구 코드"
    assert run.trace_payload["service_key_url"].endswith("/openApiNew.do")
    assert "parsed response" in " ".join(run.trace)


def test_debug_fixture_save_masks_and_blocks_overwrite(load_fixture, tmp_path: Path, mock_opinet) -> None:
    mock_opinet.add("lowTop10.do", json=load_fixture("low_top10_B027.json"))
    run = OpinetClient("secret-key", retry_backoff=0).debug().get_lowest_price_top20(
        ProductCode.GASOLINE,
        cnt=2,
        area="01",
    )

    path = save_debug_fixture(
        base_dir=tmp_path,
        debug_run=run,
        case_name="서울 최저가",
        description="최저가 fixture 저장 smoke",
        library_version="0.1.0",
    )
    fixture = json.loads(path.read_text(encoding="utf-8"))

    assert path.parent.name == "get_lowest_price_top20"
    assert fixture["name"] == "서울-최저가"
    assert fixture["request"]["query"]["certkey"] == "<REDACTED>"
    assert fixture["catalog"]["dataset_name"] == "전국/지역별 최저가 주유소"
    assert fixture["catalog"]["service_key_url"].endswith("/openApiNew.do")
    assert fixture["input"]["prodcd"] == "B027"
    assert fixture["processed"][0]["provider_station_id"] == "A0013150"
    assert fixture["meta"]["source"] == "debug_ui"
    with pytest.raises(FileExistsError):
        save_debug_fixture(
            base_dir=tmp_path,
            debug_run=run,
            case_name="서울 최저가",
            description="duplicate",
        )


def test_debug_client_validation_error_is_captured() -> None:
    run = OpinetClient("secret-key", retry_backoff=0).debug().get_lowest_price_top20(ProductCode.GASOLINE, cnt=0)

    assert run.ok is False
    assert run.error is not None
    assert run.error["type"] == "OpinetInvalidParameterError"
    assert run.response == {}
    with pytest.raises(OpinetInvalidParameterError):
        OpinetClient("secret-key", retry_backoff=0).debug().get_lowest_price_top20(
            ProductCode.GASOLINE,
            cnt=0,
            raise_errors=True,
        )


def test_fixture_replay_snapshot(load_fixture) -> None:
    response_body = load_fixture("area_code_root.json")
    fixture = build_fixture(
        function_name="get_area_codes",
        case_name="area root",
        description="snapshot replay",
        input_data={"sido": None},
        request_data={
            "method": "GET",
            "url": OPINET_BASE_URL + "areaCode.do",
            "query": {"certkey": "secret", "out": "json"},
            "headers": {},
        },
        response_data={"status_code": 200, "headers": {}, "body": response_body},
        parsed_result=[],
        processed_result=jsonable(
            OpinetClient("fixture", retry_backoff=0)
            ._parse_area_codes_response(response_body)[0]
            .to_normalized()
        ),
        assertion={"mode": "schema_only", "exclude_fields": [], "required_fields": []},
        library_version="0.1.0",
    )

    actual = replay_fixture_case(fixture)

    assert isinstance(actual, list)
    assert actual[0]["provider_region_code"] == "01"
    assert fixture["request"]["query"]["certkey"] == "<REDACTED>"


def test_save_fixture_accepts_explicit_sections(tmp_path: Path) -> None:
    path = save_fixture(
        base_dir=tmp_path,
        function_name="get_area_codes",
        case_name="root",
        description="explicit save",
        input_data={"api_key": "secret"},
        request_data={"headers": {"Authorization": "Bearer secret"}},
        response_data={"body": {"RESULT": {"OIL": []}}},
        parsed_result=[],
        processed_result=[],
        assertion={"mode": "schema_only"},
        library_version="0.1.0",
    )
    fixture = json.loads(path.read_text(encoding="utf-8"))

    assert fixture["input"]["api_key"] == "<REDACTED>"
    assert fixture["request"]["headers"]["Authorization"] == "<REDACTED>"


def test_jsonable_redaction_slug_and_assertions() -> None:
    assert slugify_case_name("  서울 최저가 / 정상  ") == "서울-최저가-정상"
    assert slugify_case_name(" ... ") == "case"
    assert jsonable(ProductCode.GASOLINE) == "B027"
    assert jsonable(date(2026, 5, 15)) == "2026-05-15"
    assert jsonable(object()).startswith("<object object at")
    assert redact_sensitive({"nested": [{"access_token": "secret"}]}) == {
        "nested": [{"access_token": "<REDACTED>"}]
    }
    assert_case(
        {"items": [{"id": "a", "updated_at": "now"}]},
        {"items": [{"id": "a", "updated_at": "then"}]},
        {"mode": "snapshot", "exclude_fields": ["updated_at"]},
    )
    assert_case(
        [{"provider": "opinet", "provider_region_code": "01"}],
        [],
        {"mode": "required_fields", "required_fields": ["provider", "provider_region_code"]},
    )
    assert_case([{"id": 1}, {"id": 2}], {"count": 2}, {"mode": "count"})
    assert_case({"count": 2}, {"count": 2}, {"mode": "count"})
    with pytest.raises(AssertionError):
        assert_case("bad", {}, {"mode": "count"})
    with pytest.raises(ValueError):
        assert_case({}, {}, {"mode": "custom"})
    with pytest.raises(AssertionError):
        assert_case({"id": 1}, {}, {"mode": "required_fields", "required_fields": ["missing"]})


def test_parse_and_process_all_debug_response_shapes(load_fixture) -> None:
    avg = parse_debug_response("get_national_average_price", load_fixture("avg_all_price.json"))
    around = parse_debug_response(
        "search_stations_around",
        load_fixture("around_all_gangnam.json"),
        input_data={"prodcd": "D047"},
    )
    detail = parse_debug_response("get_station_detail", load_fixture("detail_by_id_A0010207.json"))

    assert avg[0].product_code is ProductCode.GASOLINE_PREMIUM
    assert around[0].provider_product_code == "D047"
    assert process_debug_result("get_station_detail", detail).provider_station_id == "A0010207"
    assert process_debug_result("get_area_codes", {"plain": "value"}) == {"plain": "value"}
    with pytest.raises(ValueError):
        parse_debug_response("unknown", {"RESULT": {"OIL": []}})
    with pytest.raises(ValueError):
        process_debug_result("unknown", [])


def test_debug_client_runs_avg_around_and_detail(load_fixture, mock_opinet) -> None:
    client = OpinetClient("secret-key", retry_backoff=0)
    mock_opinet.add("avgAllPrice.do", json=load_fixture("avg_all_price.json"))
    mock_opinet.add("aroundAll.do", json=load_fixture("around_all_gangnam.json"))
    mock_opinet.add("detailById.do", json=load_fixture("detail_by_id_A0010207.json"))

    avg_run = client.debug().get_national_average_price()
    around_run = client.debug().search_stations_around(
        katec_x=314871.8,
        katec_y=544012.0,
        radius_m=1000,
        prodcd="B027",
        sort="2",
    )
    detail_run = client.debug().get_station_detail("A0010207")

    assert avg_run.ok is True
    assert avg_run.processed[0].provider_product_code == "B034"
    assert around_run.request["query"]["sort"] == "2"
    assert around_run.processed[0].provider_station_id == "A0010207"
    assert detail_run.processed.provider_station_id == "A0010207"


def test_debug_client_captures_runtime_and_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPINET_API_KEY", raising=False)
    missing_key_run = OpinetClient(retry_backoff=0).debug().get_area_codes()

    assert missing_key_run.ok is False
    assert missing_key_run.error["type"] == "OpinetAuthError"
    with pytest.raises(OpinetAuthError):
        OpinetClient(retry_backoff=0).debug().get_area_codes(raise_errors=True)

    invalid_around = OpinetClient("secret-key", retry_backoff=0).debug().search_stations_around(
        lon=127.0,
        lat=37.5,
        radius_m=0,
    )
    assert invalid_around.error["type"] == "OpinetInvalidParameterError"

    invalid_detail = OpinetClient("secret-key", retry_backoff=0).debug().get_station_detail("")
    assert invalid_detail.error["type"] == "OpinetInvalidParameterError"

    invalid_area = OpinetClient("secret-key", retry_backoff=0).debug().get_area_codes("001")
    assert invalid_area.error["type"] == "OpinetInvalidParameterError"


def test_replay_fixture_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError):
        replay_fixture_case({"function": "get_area_codes", "response": []})
    with pytest.raises(ValueError):
        replay_fixture_case({"function": "get_area_codes", "response": {"body": []}})


def test_debug_fetch_routes_all_five_apis_without_hardcoded_branches(load_fixture, mock_opinet) -> None:
    """``debug_fetch``는 ``function_name`` 문자열 분기 없이 카탈로그로만 라우팅해야 한다."""
    mock_opinet.add("avgAllPrice.do", json=load_fixture("avg_all_price.json"))
    mock_opinet.add("lowTop10.do", json=load_fixture("low_top10_B027.json"))
    mock_opinet.add("aroundAll.do", json=load_fixture("around_all_gangnam.json"))
    mock_opinet.add("detailById.do", json=load_fixture("detail_by_id_A0010207.json"))
    mock_opinet.add("areaCode.do", json=load_fixture("area_code_root.json"))

    client = OpinetClient("secret-key", retry_backoff=0)
    original_transport = client._http

    avg = client.debug_fetch("get_national_average_price", {})
    assert avg.ok is True
    assert avg.request["url"].endswith("avgAllPrice.do")
    assert avg.response["status_code"] == 200
    assert avg.processed[0].provider_product_code == "B034"

    # Streamlit 위젯은 text_input/selectbox로 항상 문자열을 준다. 카탈로그의
    # ApiParameter.kind로 int/float 변환이 이뤄지는지 여기서 함께 검증한다.
    low = client.debug_fetch("get_lowest_price_top20", {"prodcd": "B027", "cnt": "2", "area": "01"})
    assert low.ok is True
    assert low.request["query"]["cnt"] == 2
    assert low.processed[0].provider_station_id == "A0013150"

    around = client.debug_fetch(
        "search_stations_around",
        {"katec_x": "314871.8", "katec_y": "544012.0", "radius_m": "1000", "prodcd": "B027", "sort": "2"},
    )
    assert around.ok is True
    assert around.request["query"]["sort"] == "2"
    assert around.processed[0].provider_station_id == "A0010207"

    detail = client.debug_fetch("get_station_detail", {"uni_id": "A0010207"})
    assert detail.ok is True
    assert detail.processed.provider_station_id == "A0010207"

    area = client.debug_fetch("get_area_codes", {})
    assert area.ok is True
    assert area.processed[0].provider_region_code == "01"

    # 요청 동안 client의 transport를 기록용 proxy로 바꿔치기하지만 항상 원상복구해야 한다.
    assert client._http is original_transport


def test_debug_fetch_unknown_function_raises() -> None:
    with pytest.raises(KeyError):
        OpinetClient("secret-key", retry_backoff=0).debug_fetch("unknown_function")


def test_debug_fetch_validation_error_before_request_has_no_call(mock_opinet) -> None:
    run = OpinetClient("secret-key", retry_backoff=0).debug_fetch("search_stations_around", {})

    assert run.ok is False
    assert run.error["type"] == "OpinetInvalidParameterError"
    assert run.error["status_code"] is None
    assert run.request == {}
    assert run.response == {}
    assert not mock_opinet.calls


def test_debug_fetch_missing_auth_returns_structured_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPINET_API_KEY", raising=False)

    run = OpinetClient(retry_backoff=0).debug_fetch("get_area_codes", {})

    assert run.ok is False
    assert run.error["type"] == "OpinetAuthError"
    assert run.request == {}
    assert run.response == {}


def test_debug_fetch_captures_request_response_on_downstream_error(load_fixture, mock_opinet) -> None:
    """HTTP 호출은 성공했지만 이후 단계(빈 결과 처리)에서 실패해도 request/response는 남아야 한다."""
    mock_opinet.add("areaCode.do", json=load_fixture("empty_oil.json"))
    client = OpinetClient("secret-key", retry_backoff=0, strict_empty=True)

    run = client.debug_fetch("get_area_codes", {})

    assert run.ok is False
    assert run.error["type"] == "OpinetNoDataError"
    assert run.response["status_code"] == 200
    assert run.response["body"] == {"RESULT": {"OIL": []}}
    assert run.request["url"].endswith("areaCode.do")


def test_debug_fetch_http_error_includes_provider_status_code(mock_opinet) -> None:
    mock_opinet.add("areaCode.do", status=401, body="invalid key")
    client = OpinetClient("secret-key", retry_backoff=0)

    run = client.debug_fetch("get_area_codes", {})

    assert run.ok is False
    assert run.error["type"] == "OpinetAuthError"
    assert run.error["status_code"] == 401


def test_debug_fetch_extra_params_reach_client_as_typeerror(mock_opinet) -> None:
    """카탈로그에 없는 파라미터(Extra params escape hatch)는 그대로 전달되고, client가 받아들이지
    못하면 예외를 삼키지 않고 구조화된 오류로 드러나야 한다."""
    client = OpinetClient("secret-key", retry_backoff=0)

    run = client.debug_fetch("get_area_codes", {"typo_param": "x"})

    assert run.ok is False
    assert run.error["type"] == "TypeError"
    assert not mock_opinet.calls
