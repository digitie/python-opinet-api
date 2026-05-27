# Debug UI Fixture Workflow

이 문서는 REST API 디버그 UI가 만든 fixture를 `python-opinet-api`의 회귀 테스트 자산으로 사용하는 방식입니다.

## 핵심 원칙

- Web UI는 테스트 코드를 생성하지 않고 fixture JSON을 생성합니다.
- pytest는 공통 runner로 `tests/fixtures/{function}/{case}.json` 형식의 fixture를 자동 replay합니다.
- 라이브러리 본체는 Streamlit에 의존하지 않습니다. Streamlit 앱은 별도 패키지에서 `opinet.debug`를 import해 사용합니다.
- fixture 저장 전 `certkey`, `api_key`, `Authorization`, token 계열 값은 `<REDACTED>`로 마스킹합니다.
- replay 테스트는 외부 오피넷 API를 호출하지 않고 저장된 `response.body`만 사용합니다.

## 라이브러리 지원 모듈

`src/opinet/debug.py`는 UI 없이도 사용할 수 있는 순수 Python 헬퍼를 제공합니다.

| 항목 | 역할 |
|---|---|
| `OpinetClient.debug()` | `OpinetDebugClient` 래퍼 반환 |
| `DebugRun` | function, input, request, response, parsed, processed, trace, catalog item, error 보관 |
| `get_api_catalog()` | 공식 5개 API 카탈로그 반환 |
| `get_api_catalog_options()` | Streamlit selectbox 등에 쓰기 좋은 label/value 목록 반환 |
| `jsonable()` | Pydantic v2, dataclass, enum, date/time 값을 JSON 저장 가능 값으로 변환 |
| `redact_sensitive()` | fixture 저장 전 민감정보 마스킹 |
| `save_fixture()` / `save_debug_fixture()` | 표준 fixture JSON 저장 |
| `parse_debug_response()` | 저장된 raw response를 기존 client parser로 재파싱 |
| `process_debug_result()` | parsed model을 normalized DTO로 변환 |
| `replay_fixture_case()` | fixture 한 건을 replay하고 assertion 수행 |

지원 function 이름은 현재 공식 5개 메서드와 같습니다.

```python
from opinet import OpinetClient, ProductCode, get_api_catalog_options
from opinet.debug import save_debug_fixture

catalog_options = get_api_catalog_options()
# option["label"] 예: "반경 내 주유소 가격 (aroundAll.do)"

client = OpinetClient(api_key="...")
run = client.debug().search_stations_around(
    lon=127.0276,
    lat=37.4979,
    radius_m=3000,
    prodcd=ProductCode.GASOLINE,
)

save_debug_fixture(
    base_dir="tests/fixtures",
    debug_run=run,
    case_name="gangnam gasoline normal",
    description="강남역 반경 3km 휘발유 정상 검색 케이스",
)
```

`DebugRun`은 선택된 API의 카탈로그 항목을 함께 가집니다. Streamlit Debug Trace 탭은 다음 값을 그대로 표시하면 됩니다.

```python
st.markdown(f"**데이터셋:** {run.dataset_name}")
st.link_button("오피넷 인증키 발급", run.service_key_url)
st.json(run.trace_payload)
```

`run.trace_payload["catalog_item"]`에는 `dataset_name`, `endpoint`, `api_id`, `parameters`, `service_key_url`이 포함됩니다.

## Fixture 형식

기본 저장 위치는 `tests/fixtures/{function}/{case}.json`입니다. 기존 API 원본 fixture인 `tests/fixtures/*.json`와 충돌하지 않도록, replay runner는 하위 디렉터리 fixture만 읽습니다.

```json
{
  "name": "gangnam-gasoline-normal",
  "function": "search_stations_around",
  "description": "강남역 반경 3km 휘발유 정상 검색 케이스",
  "catalog": {
    "dataset_name": "반경 내 주유소 가격",
    "endpoint": "aroundAll.do",
    "service_key_url": "https://www.opinet.co.kr/user/custapi/openApiNew.do"
  },
  "input": {
    "coordinate": {"lon": 127.0276, "lat": 37.4979},
    "radius_m": 3000,
    "prodcd": "B027",
    "sort": "1"
  },
  "request": {
    "method": "GET",
    "url": "https://www.opinet.co.kr/api/aroundAll.do",
    "query": {
      "certkey": "<REDACTED>",
      "out": "json",
      "prodcd": "B027"
    },
    "headers": {}
  },
  "response": {
    "status_code": 200,
    "headers": {},
    "body": {"RESULT": {"OIL": []}}
  },
  "parsed": [],
  "processed": [],
  "assertion": {
    "mode": "snapshot",
    "exclude_fields": ["fetched_at", "request_id", "updated_at"],
    "required_fields": []
  },
  "meta": {
    "created_at": "2026-05-15T00:00:00+09:00",
    "library_version": "0.1.0",
    "source": "debug_ui"
  }
}
```

`parsed`와 `processed`는 UI preview와 사람의 검토를 위한 저장값입니다. replay 테스트의 actual 값은 항상 `response.body`를 다시 파싱해 만듭니다.

## Assertion mode

| Mode | 동작 |
|---|---|
| `snapshot` | processed actual과 fixture의 `processed`를 비교합니다. `exclude_fields`는 key 또는 dotted path로 제외합니다. |
| `schema_only` | 파싱과 processed 변환이 성공하고 actual이 `None`이 아니면 통과합니다. |
| `required_fields` | actual dict 또는 list 안의 모든 dict가 지정 필드를 갖는지 확인합니다. |
| `count` | actual list 길이 또는 dict의 `count` 값을 expected와 비교합니다. |

## pytest replay runner

관련 파일은 다음과 같습니다.

| 파일 | 역할 |
|---|---|
| `tests/runners.py` | 지원 function과 replay entrypoint |
| `tests/utils.py` | assertion helper re-export |
| `tests/test_generated_fixtures.py` | `tests/fixtures/*/*.json` 자동 발견 및 replay |
| `tests/fixtures/get_area_codes/area_code_root_schema_only.json` | runner smoke fixture |

실행:

```bash
python -m pytest tests/test_generated_fixtures.py
```

전체 기본 테스트에서도 replay runner가 함께 실행됩니다.

## 별도 Streamlit UI 연결 기준

Streamlit 프로젝트를 별도 패키지로 만들 때는 다음 경계를 지킵니다.

- UI 프로젝트에서만 `streamlit`, `pandas` 같은 화면 의존성을 둡니다.
- 개발 중에는 `pip install -e ../python-opinet-api`로 라이브러리를 import합니다.
- 릴리즈 검증은 wheel 설치 후 UI 실행으로 확인합니다.
- UI의 Save 버튼은 `save_debug_fixture(base_dir="tests/fixtures", debug_run=run, ...)`만 호출합니다.
- API 선택 UI는 `get_api_catalog_options()`의 `label`을 보여주고 `value`로 debug function을 선택합니다.
- Debug Trace 탭은 `run.trace_payload`와 `run.service_key_url`을 표시합니다.
- Fixture/Testcase 탭은 case name, description, assertion mode, exclude fields, required fields, overwrite 설정을 받아 `tests/fixtures/{function}/{case}.json`으로 저장합니다.
- Copy pytest code는 보조 기능으로만 둡니다. 기본 회귀 테스트는 parametrize runner 방식입니다.

이 저장소에는 바로 참고할 수 있는 선택형 예제 `examples/streamlit_debug_app.py`가 있습니다. 예제는 Raw/Parsed/Processed/Error/Debug Trace/Fixture 탭을 제공하지만, Streamlit은 라이브러리 런타임 의존성이 아니므로 별도 UI 환경에서 설치해 실행합니다.

```bash
pip install streamlit
streamlit run examples/streamlit_debug_app.py
```
