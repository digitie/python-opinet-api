# python-opinet-api Implementation Status

이 문서는 현재 구현 상태, 검증 방법, 다음 작업자가 반복하지 말아야 할 판단을 한곳에 모읍니다.

## 현재 범위

`OpinetClient`는 오피넷 공식 오픈 API 페이지에 등재된 5개 엔드포인트만 안정 구현 대상으로 둡니다.

## 2026-09-19 공개 지역별 화면 수집기

운영 Chromium에서 검색 화면의 자동 이동 직후 이전 응답 본문이 없어지는 오류를
확인했다. 같은 출처·검색 문서의 현재 HTML만 대체 검사하도록 보완했으며,
차단 화면과 외부 이동, 관련 없는 네트워크 오류는 계속 실패로 처리한다.

공식 open API와 분리된 `opinet.experimental.OpinetBrowserCollector`를 추가했습니다.
Playwright로 지역별 공개 화면의 시도·시군구·읍면동 선택값을 읽고, 화면 조회 시
발생하는 `searRgSelect.do` HTML 또는 `searRgCircleAjax.do` JSON 응답에서
주유소와 충전소 데이터를 typed dataclass로 변환합니다. 기본 주유소 조회 단위는 시군구이며, 필요할 때만
`query_level="dong"`으로 읍면동별 조회를 선택합니다.

화면 조작 사이의 짧은 무작위 지연과 전체 수집 사이의 기본 8시간 간격,
최근 24시간 최대 3회 실행 제한은 요청 부하를 분산하기 위한 정책입니다. 지역 선택 AJAX와 검색 응답 완료,
HTTP 상태·접근 거부 페이지를 확인하며, 자동화 탐지 우회·지문 조작·CAPTCHA
우회는 구현하지 않습니다. 상세 사용법과 이용약관·재배포 확인 조건은
`docs/browser-collection.md`에 기록했습니다.

| Method | Endpoint | Status | Notes |
|---|---|---|---|
| `get_national_average_price()` | `avgAllPrice.do` | Implemented | `TRADE_DT`, `PRICE`, `DIFF`를 Python 타입으로 변환 |
| `get_lowest_price_top20()` | `lowTop10.do` | Implemented | `cnt` 1~20, `area` 2/4자리 사전 검증 |
| `search_stations_around()` | `aroundAll.do` | Implemented | WGS84 입력은 KATEC으로 변환 후 요청 |
| `get_station_detail()` | `detailById.do` | Implemented | `LPG_YN`은 `StationType`, `KPETRO_YN`은 `is_kpetro` |
| `get_area_codes()` | `areaCode.do` | Implemented | 코드값은 선행 0 보존을 위해 항상 `str` |

PDF 가이드북의 추가 API는 아직 공식 명세 페이지가 없으므로 `opinet.experimental`에 둡니다. 검증 전에는 안정 API로 승격하지 않습니다.

## 2026-05-15 디버그 UI/fixture 지원

REST API 디버그 UI 설계안에 맞춰 라이브러리 본체에 Streamlit 비의존 helper를 추가했습니다.

| 영역 | 구현 |
|---|---|
| API 카탈로그 | `src/opinet/catalog.py`의 `get_api_catalog()`, `get_api_catalog_item()`, `get_api_catalog_options()` |
| Async/httpx | `OpinetConfig`, `AsyncHttpxTransport`, `OpinetClient`, `AsyncTokenBucket` |
| 데이터셋 표시 | `ApiCatalogItem.dataset_name`으로 사람이 읽기 쉬운 데이터셋명 제공 |
| 서비스키 링크 | 모든 `ApiCatalogItem.service_key_url`이 오피넷 인증키 발급 페이지를 가리킴 |
| 서비스키 정규화 | `OpinetClient`가 명시 인자/환경변수/`.env`에서 키를 읽고 공백 문자를 제거 |
| DebugRun | `src/opinet/debug.py`의 `DebugRun`이 input, request, response, parsed, processed, trace, catalog item, error를 보관 |
| fixture 저장 | `save_fixture()`, `save_debug_fixture()`가 `tests/fixtures/{function}/{case}.json` 형식으로 저장 |
| replay 테스트 | `tests/test_generated_fixtures.py`가 하위 디렉터리 fixture를 네트워크 없이 재파싱/비교 |
| 예제 UI | `examples/streamlit_debug_ui.py`가 카탈로그 기반 파라미터 폼, 서비스키 링크, 6개 고정 탭(Raw Response/Pydantic Model/Processed Result/Validation Errors/Debug Trace/Fixture)을 검증하는 참고 앱 |

라이브러리 런타임 의존성에는 Streamlit을 추가하지 않았습니다. 화면 앱은 `pip install -e ".[debug-ui]"`(`pyproject.toml`의 `debug-ui` extra)로 선택적으로 설치해 `examples/streamlit_debug_ui.py`를 실행합니다.

## 구현 원칙

- 인증 파라미터는 `certkey`, 출력 포맷은 `out=json`입니다.
- 서비스키는 `OpinetClient(api_key=...)`, `OPINET_API_KEY`, 현재 작업 디렉터리 또는 부모 디렉터리의 `.env` 순서로 읽습니다. 복사/붙여넣기 중 섞인 공백 문자는 값이 아니므로 제거합니다.
- HTTP status/body error mapping lives in the httpx-based `src/opinet/_http.py`.
- 공개 HTTP/API는 config + native async OpinetClient/AsyncHttpxTransport + 공통 AsyncTokenBucket으로 구성한다.
- The normalized station detail contract consumed by `python-krtour-map` is kept stable around `provider_station_id`, `provider_station_name`, `lon`/`lat`, `katec_x`/`katec_y`, `prices`, and `raw`.
- 엔드포인트 파라미터 오류는 HTTP 호출 전에 `OpinetInvalidParameterError`로 실패시킵니다.
- API 응답은 모델 생성 전에 `date`, `time`, `float`, `bool`, `StrEnum`으로 변환합니다.
- `AREA_CD`, `SIGUNCD`, `UNI_ID`, 제품 코드, 상표 코드는 정수로 변환하지 않습니다.
- KATEC 변환은 `src/opinet/coords.py`에서 `pyproj`를 직접 사용합니다.
- 주유소 좌표/지역 매핑 관련 타입과 변환 로직은 이 저장소 안에서 직접 소유합니다. 얇은 wrapper나 mirror dataclass는 만들지 않습니다.
- `SIGUNCD`는 오피넷 자체 4자리 시군구 코드이며 법정동 시군구 코드나 10자리 법정동코드로 추정 변환하지 않습니다. 필요하면 `src/opinet/vworld.py`에서 `vworld.VworldClient.search_district(..., category="L2")` 결과의 5자리 `id`와 `title`을 명시 매칭합니다.
- 문서에서 파일 위치는 프로젝트 루트 기준 상대 경로로 표기합니다.
- Python 내부 문서(docstring과 유지보수용 주석)는 한글로 작성합니다. 외부 API 고유 명칭과 코드 식별자는 원문을 유지합니다.
- 이 Windows/PowerShell 환경에서는 `rg`가 실행 권한 문제로 실패할 수 있으므로, 실패 시 `git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`으로 파일 목록과 검색을 수행합니다.
- 한글 문서/소스 파일 확인 시 `Get-Content -Encoding utf8` 또는 `Get-Content -Raw -Encoding utf8`을 사용해 깨진 출력으로 인한 오판을 피합니다.

## 테스트 매트릭스

기본 테스트는 네트워크 없이 실행됩니다.

| Area | Files | Coverage Intent |
|---|---|---|
| Type conversion | `tests/test_convert.py` | 날짜/시간/숫자/불리언/공백 처리 |
| Code mappings | `tests/test_codes.py`, `tests/test_vworld_sigungu.py` | Opinet ↔ BJD 시도 매핑, 알뜰 상표 판정, VWorld 시군구 매핑 |
| Coordinates | `tests/test_client_endpoints.py` | WGS84↔KATEC 변환과 오피넷 요청/응답 경계 |
| HTTP errors | `tests/test_http.py` | 인증/쿼터/5xx/네트워크/JSON 오류 |
| Async client | `tests/test_async_client.py` | `OpinetClient`, async context manager, TPS, 세션 소유권 |
| Endpoints | `tests/test_client_endpoints.py` | 공식 5개 API의 타입, 파라미터, 빈 결과, 단일 dict 응답 |
| API catalog/debug | `tests/test_catalog.py`, `tests/test_debug.py`, `tests/test_generated_fixtures.py` | 카탈로그 export, DebugRun trace, 민감정보 마스킹, fixture replay |
| Experimental boundary | `tests/test_experimental.py` | 미검증 API가 명시적으로 unimplemented임을 고정 |

필수 검증 명령:

```bash
python -m compileall src/opinet tests
python -m pytest
python -m pytest --cov=opinet --cov-fail-under=90
python -m mypy src/opinet
```

## Live API 테스트 정책

실제 오피넷 호출은 기본 테스트에 넣지 않습니다.

- `OPINET_API_KEY`가 있을 때만 동작하게 합니다.
- 테스트에는 `@pytest.mark.live`를 붙입니다.
- 캡처한 fixture에는 키, 개인 식별 정보, 호출 URL의 인증 파라미터를 남기지 않습니다.
- 라이브 호출로 확인한 응답도 fixture에 저장할 때 숫자/날짜/시간 필드는 문자열 그대로 둡니다.
- `.env`는 로컬 전용이며 커밋하지 않습니다. `.env.example`만 추적합니다.
- `areaCode.do`처럼 항상 데이터가 있어야 할 엔드포인트가 빈 `RESULT.OIL`을 반환하면 키가 공식 open API 게이트웨이에 provision되지 않은 상태로 간주하고 파싱 smoke 테스트를 skip합니다.

라이브 테스트 실행:

```bash
pytest -m live --run-live
```

### 2026-05-01 Live Run Note

로컬 `.env`의 키로 실제 서버에 연결했을 때 `areaCode.do`의 JSON envelope는 정상 수신되었습니다. 다만 공식 5개 API가 모두 HTTP 200과 빈 `RESULT.OIL`을 반환하는 상태가 관찰되었습니다. 이 응답은 파서 오류가 아니라 키가 공식 open API 게이트웨이에 데이터 반환 권한으로 provision되지 않은 상태일 가능성이 높습니다.

그래서 live 테스트는 두 단계로 나뉩니다.

- 서버 연결과 `RESULT.OIL` envelope 확인은 pass/fail로 검증합니다.
- 실제 데이터 파싱 smoke는 `areaCode.do`가 비어 있으면 skip하고, 데이터가 반환되는 키에서는 공식 5개 API 전체를 검증합니다.

## 반복 실수 방지

이미 한 번 확인한 혼동 지점입니다.

- `StationDetail.tel`을 사용합니다. `phone` 필드를 새로 만들지 않습니다.
- `OilPrice`에는 `product_name`이 없습니다. `OIL_PRICE` 응답에는 `PRODNM`이 오지 않습니다.
- `RESULT.OIL`과 `OIL_PRICE`는 list뿐 아니라 단일 dict로 올 수 있습니다.
- 실제 응답의 상표 필드는 `POLL_DIV_CO`, `GPOLL_DIV_CO`가 우선입니다. `*_CD`는 fallback입니다.
- 공백 1자(`" "`)는 의미 있는 문자열이 아니라 `None`입니다.
- 좌표 변환 정밀도와 오피넷 모델 경계는 `python-opinet-api` 테스트가 소유합니다.
- Unit HTTP mocks replay httpx calls with `respx`.

## 다음 작업 기준

새 엔드포인트를 추가할 때:

1. `opinet-api.md` 또는 실제 응답으로 필드를 확인합니다.
2. 공식 5개에 속하지 않으면 `opinet.experimental`에 둡니다.
3. 모델 필드는 Python 네이티브 타입으로 정의합니다.
4. fixture는 실제 응답처럼 문자열 값을 유지합니다.
5. happy path, empty result, error response, 파라미터 검증 테스트를 추가합니다.
6. README와 이 문서를 갱신합니다.

---

## 공용 normalized layer 현황

2026-05-06 기준으로 기존 public API를 유지하면서 optional/additive normalized layer를 추가했습니다. 이 layer는 OpiNet provider row를 여러 프로젝트에서 바로 재사용할 수 있게 하는 공용 해석 계층이며, 애플리케이션별 DB 저장, ETL cache, serving table, 서비스 enum 정책은 포함하지 않습니다.

### 추가된 public surface

| 영역 | 구현 |
|---|---|
| canonical 유종 | `FuelType` 및 `CanonicalFuelType` alias |
| 유종 mapping | `product_code_to_fuel_type()`, `fuel_type_to_product_code()` |
| 좌표 필드 | `lon`, `lat`, `katec_x`, `katec_y`, `lon_lat`, `katec_xy` |
| raw payload | `AvgPrice.raw`, `Station.raw`, `StationDetail.raw`, `OilPrice.raw`, `AreaCode.raw` |
| Station product context | `Station.product_code`, `Station.product_name` |
| Station trade context | `Station.trade_date`, `Station.trade_time` |
| Station normalized helpers | `provider_station_id`, `provider_product_code`, `provider_product_name`, `fuel_type`, `brand_code`, `lon_lat`, `katec_xy` |
| AvgPrice normalized helpers | `provider_product_code`, `provider_product_name`, `fuel_type` |
| OilPrice helper | `provider_product_code`, `fuel_type` |
| AreaCode helpers | `code_level`, `parent_sido_code`, `bjd_sido_prefix` |

### 호환성 원칙

- 기존 dataclass 필드는 순서를 유지했습니다.
- 새 선택 필드는 기존 필드 뒤에 추가했습니다.
- 모든 model의 `raw`는 마지막 dataclass 필드입니다.
- `raw`는 읽기 전용 mapping이며, nested `OIL_PRICE`는 tuple과 read-only mapping으로 가능한 한 원형 문자열 값을 보존합니다.
- `certkey`, `api_key`, `authorization`, `x-api-key` 같은 인증 관련 key는 raw에서 제외합니다.

### request context 규칙

`lowTop10.do`와 `aroundAll.do`의 Station row에는 `PRODCD`/`PRODNM`이 없는 경우가 많습니다.

- row에 `PRODCD`가 있으면 응답 값을 `Station.product_code`로 사용합니다.
- row에 `PRODCD`가 없으면 요청에 사용한 `prodcd`를 `Station.product_code`에 채웁니다.
- row에 `PRODNM`이 있으면 `Station.product_name`에 보존합니다.
- row에 `TRADE_DT`/`TRADE_TM`이 있으면 `Station.trade_date`/`Station.trade_time`으로 변환합니다.
- 필드가 없으면 `product_name`, `trade_date`, `trade_time`은 `None`입니다.

### 검증 케이스

`tests/test_normalized_models.py`에 fixture 기반 회귀 테스트를 추가했습니다.

| 케이스 | 검증 |
|---|---|
| ProductCode ↔ FuelType | gasoline, premium_gasoline, diesel, lpg, kerosene roundtrip |
| mapping 실패 | 알 수 없는 product code, 알 수 없는 fuel type, `FuelType.UNKNOWN` 역변환 실패 |
| AreaCode | `01`, `0113`, `001`, 미확인 시도 code |
| BJD prefix | `AreaCode.bjd_sido_prefix`가 `opinet_sido_to_bjd` 기반으로 동작 |
| 좌표 value object | 기존 float 필드 유지 및 `Station.coordinates` 제공 |
| Station request product | `lowTop10.do`, `aroundAll.do` 요청 `prodcd`가 Station에 보존 |
| Station response product | 응답 `PRODCD`가 있으면 요청 값보다 우선 |
| Station trade context | 응답 `TRADE_DT`/`TRADE_TM` 문자열을 date/time으로 변환 |
| raw payload | 타입 변환 전 문자열 값 보존, top-level 및 nested raw read-only 확인 |
| raw shape | mapping이 아닌 raw payload는 명시적으로 실패 |

### 사용 예시

```python
import asyncio
from opinet import OpinetClient, ProductCode


async def main() -> None:
    async with OpinetClient() as client:
        station = (await client.search_stations_around(
            lon=127.0276,
            lat=37.4979,
            prodcd=ProductCode.DIESEL,
        ))[0]

        record = {
            "provider_station_id": station.provider_station_id,
            "provider_product_code": station.provider_product_code,
            "fuel_type": station.fuel_type.value,
            "brand_code": station.brand_code,
            "price": station.price,
            "trade_date": station.trade_date,
            "trade_time": station.trade_time,
            "lon": station.coordinates.wgs84.lon,
            "lat": station.coordinates.wgs84.lat,
            "raw_price": station.raw.get("PRICE"),
        }


asyncio.run(main())
```

이 예시는 python-opinet-api의 normalized 모델만 사용합니다. 저장 schema, cache 전략, raw 보관 여부는 호출 애플리케이션의 책임입니다.

---

## normalized DTO record layer

2026-05-06에 `opinet.normalized` 모듈을 추가했습니다. 이 모듈은 기존 응답 모델의 속성 위에 앱 친화적인 Pydantic DTO를 얹는 계층입니다. 기존 public model과 client method는 변경하지 않고, `AvgPrice.to_normalized()`, `Station.to_normalized()`, `AreaCode.to_normalized()`로 변환합니다.

DTO는 Pydantic v2 `BaseModel` 기반이며 `frozen=True`, `extra="forbid"` 설정을 사용합니다. 호출 앱은 `model_dump()` 또는 `model_dump(mode="json")`로 저장 계층에 넘길 payload를 만들 수 있습니다.

### DTO classes

| DTO | Source model | 기본 endpoint | 주요 필드 |
|---|---|---|---|
| `NormalizedFuelAverage` | `AvgPrice` | `avgAllPrice.do` | `provider`, `provider_endpoint`, `provider_product_code`, `provider_product_name`, `fuel_type`, `trade_date`, `price`, `diff`, `raw` |
| `NormalizedFuelStation` | `Station` | 호출자가 지정 | `provider_station_id`, `provider_station_name`, `provider_product_code`, `provider_product_name`, `fuel_type`, `brand_code`, `price`, `distance_m`, 주소, 좌표, 거래시각, `raw` |
| `NormalizedFuelRegionCode` | `AreaCode` | `areaCode.do` | `provider_region_code`, `provider_region_name`, `code_level`, `parent_sido_code`, `bjd_sido_prefix`, `raw` |

모든 DTO의 `provider` 값은 `"opinet"`입니다. Station DTO의 `provider_endpoint`는 `lowTop10.do`와 `aroundAll.do` 중 호출 맥락에 따라 달라지므로 변환 시 명시하게 했습니다.

### datetime helpers

- `NormalizedFuelAverage.price_datetime(tz="Asia/Seoul")`: `trade_date`를 해당 timezone의 자정으로 변환합니다.
- `NormalizedFuelAverage.price_timestamp(tz="Asia/Seoul")`: 위 datetime의 Unix timestamp를 반환합니다.
- `NormalizedFuelStation.trade_datetime(tz="Asia/Seoul")`: `trade_date`와 `trade_time`이 모두 있을 때 timezone-aware datetime을 반환합니다. 둘 중 하나라도 없으면 `None`입니다.
- 기존 `AvgPrice.price_datetime()`, `AvgPrice.price_timestamp()`, `Station.trade_datetime()`도 동일한 helper로 연결했습니다.

### raw JSON-safe helper

`to_json_safe_raw()`와 alias `raw_to_json_safe()`는 read-only `MappingProxyType`, tuple로 보존된 nested `OIL_PRICE`, enum, date/time 값을 JSON-safe plain `dict`/`list` 구조로 변환합니다. 기본 fixture 경로에서는 숫자/날짜/시간 raw 값이 원본 문자열 그대로 보존됩니다.

```python
from opinet.normalized import to_json_safe_raw

raw = to_json_safe_raw(station.raw)
# json.dumps(raw, ensure_ascii=False) 가능
```

### 추가 검증

`tests/test_normalized_records.py`를 추가했습니다.

| 케이스 | 검증 |
|---|---|
| normalized record 생성 | 세 DTO의 provider/endpoint/provider code/name/fuel field 확인 |
| AvgPrice KST timestamp | 날짜-only 평균가가 Asia/Seoul 자정 datetime/timestamp로 변환됨 |
| Station trade datetime | trade field 없음은 `None`, `TRADE_DT`/`TRADE_TM` 있음은 KST datetime |
| AreaCode normalized | code level, parent sido, BJD sido prefix 포함 |
| raw JSON-safe | nested `OIL_PRICE`가 plain list/dict로 변환되고 `json.dumps` 가능 |
| PRODNM 없는 Station | 요청 `prodcd`는 product code로 보존되고 provider product name은 `None` |
| Pydantic 동작 | DTO가 `BaseModel`이며 frozen/extra forbid/model_dump 동작 |

---

## PEP 561 typed package

2026-05-06에 PEP 561 typed package 지원을 추가했습니다.

- `src/opinet/py.typed` marker를 추가했습니다.
- `pyproject.toml`의 setuptools package data에 `py.typed`를 등록했습니다.
- dev extra에 packaging smoke용 `build`, `wheel`, `setuptools>=68`를 명시했습니다.
- `tests/test_pep561_packaging.py`에서 wheel/sdist를 빌드하고, 각 산출물을 임시 venv에 설치한 뒤 `import opinet`, `import opinet.normalized`, downstream mypy reveal smoke를 실행합니다.

이 테스트는 Pydantic DTO와 기존 public export가 설치 환경에서도 typed package로 보이는지 확인합니다.


## 비동기 호출과 요청 속도

`OpinetClient`의 조회와 디버그는 `await`, `iter_stations_in_bbox`는 `async for`,
종료는 `async with` 또는 `await client.aclose()`를 사용한다. Async 접두사 클라이언트,
aio 팩터리와 동기 transport는 제거했다. 코드표·좌표·모델 변환·fixture 저장 같은
로컬 유틸리티는 일반 함수다. 기존 엔드포인트 인자와 반환 모델은 유지한다.

기본 `max_rps=5.0`이다. `AsyncTokenBucket(max_rps, capacity=...)`를
`rate_limiter=`에 주입하면 여러 클라이언트가 같은 요청 예산을 쓴다. 주입된 버킷이
max_rps보다 우선한다. 기본 capacity는 max(1, max_rps)이며 초기에는 가득 차
있으므로 burst를 허용한다. 일정한 간격은 capacity=1로 설정한다.
각 요청·재시도·리다이렉트·디버그·격자 셀에 같은 버킷을 적용한다.
인자 검증 실패와 캐시 적중은 요청을 보내지 않는다. TPS는 일일 쿼터를 대신하지 않는다.

버킷은 한 이벤트 루프에서 사용한다. 대기 취소는 토큰을 소비하지 않고 다음 대기자를
진행시킨다. 401/403/429는 즉시 실패하며 네트워크 오류와 5xx만 기존 backoff로
재시도한다. 사용자 정의 인증/transport 내부에서 발생하는 추가 전송은 계측 범위 밖이다.

내부 HTTP 세션은 첫 요청 시 생성하고 종료 시 닫는다. session에 주입하는 비동기
세션은 호출자가 닫는다. 종료한 클라이언트의 추가 요청은 실패한다.
디버그 기록은 ContextVar로 호출별 격리하고 성공·실패·취소 모두에서 복원한다.
응답 파싱은 원문으로 완료한 후 진단 결과의 알려진 키와 인코딩된 키를 마스킹한다.
VWorld 연동은 비동기 search_district를 사용하며 완료된 지역 코드만 캐시한다.


예제는 [docs/async-tps.md](../docs/async-tps.md)를 참고한다.
