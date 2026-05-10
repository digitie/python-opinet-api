# pyopinet Implementation Status

이 문서는 현재 구현 상태, 검증 방법, 다음 작업자가 반복하지 말아야 할 판단을 한곳에 모읍니다.

## 현재 범위

`OpinetClient`는 오피넷 공식 오픈 API 페이지에 등재된 5개 엔드포인트만 안정 구현 대상으로 둡니다.

| Method | Endpoint | Status | Notes |
|---|---|---|---|
| `get_national_average_price()` | `avgAllPrice.do` | Implemented | `TRADE_DT`, `PRICE`, `DIFF`를 Python 타입으로 변환 |
| `get_lowest_price_top20()` | `lowTop10.do` | Implemented | `cnt` 1~20, `area` 2/4자리 사전 검증 |
| `search_stations_around()` | `aroundAll.do` | Implemented | WGS84 입력은 KATEC으로 변환 후 요청 |
| `get_station_detail()` | `detailById.do` | Implemented | `LPG_YN`은 `StationType`, `KPETRO_YN`은 `is_kpetro` |
| `get_area_codes()` | `areaCode.do` | Implemented | 코드값은 선행 0 보존을 위해 항상 `str` |

PDF 가이드북의 추가 API는 아직 공식 명세 페이지가 없으므로 `opinet.experimental`에 둡니다. 검증 전에는 안정 API로 승격하지 않습니다.

## 구현 원칙

- 인증 파라미터는 `certkey`, 출력 포맷은 `out=json`입니다.
- HTTP 상태/본문 기반 오류 매핑은 `opinet/_http.py`에 모읍니다.
- 엔드포인트 파라미터 오류는 HTTP 호출 전에 `OpinetInvalidParameterError`로 실패시킵니다.
- API 응답은 모델 생성 전에 `date`, `time`, `float`, `bool`, `StrEnum`으로 변환합니다.
- `AREA_CD`, `SIGUNCD`, `UNI_ID`, 제품 코드, 상표 코드는 정수로 변환하지 않습니다.
- KATEC 변환은 `pykrtour.PlaceCoordinate`와 `pykrtour.KatecPoint`를 직접 사용합니다.
- 공통 기능이 `pykrtour` 같은 다른 TripMate 라이브러리에 구현돼 있으면 최소 수정보다 직접 의존을 우선합니다. 얇은 wrapper나 mirror dataclass는 만들지 않습니다.
- `SIGUNCD`는 오피넷 자체 4자리 시군구 코드이며 법정동 시군구 코드나 10자리 법정동코드로 추정 변환하지 않습니다.
- 문서에서 파일 위치는 프로젝트 루트 기준 상대 경로로 표기합니다.
- Python 내부 문서(docstring과 유지보수용 주석)는 한글로 작성합니다. 외부 API 고유 명칭과 코드 식별자는 원문을 유지합니다.
- 이 Windows/PowerShell 환경에서는 `rg`가 실행 권한 문제로 실패할 수 있으므로, 실패 시 `git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`으로 파일 목록과 검색을 수행합니다.
- 한글 문서/소스 파일 확인 시 `Get-Content -Encoding utf8` 또는 `Get-Content -Raw -Encoding utf8`을 사용해 깨진 출력으로 인한 오판을 피합니다.

## 테스트 매트릭스

기본 테스트는 네트워크 없이 실행됩니다.

| Area | Files | Coverage Intent |
|---|---|---|
| Type conversion | `tests/test_convert.py` | 날짜/시간/숫자/불리언/공백 처리 |
| Code mappings | `tests/test_codes.py` | Opinet ↔ BJD 시도 매핑, 알뜰 상표 판정 |
| Coordinates | `pykrtour` 테스트, `tests/test_client_endpoints.py` | WGS84↔KATEC 변환은 `pykrtour`, 오피넷 요청/응답 경계는 클라이언트 테스트 |
| HTTP errors | `tests/test_http.py` | 인증/쿼터/5xx/네트워크/JSON 오류 |
| Endpoints | `tests/test_client_endpoints.py` | 공식 5개 API의 타입, 파라미터, 빈 결과, 단일 dict 응답 |
| Experimental boundary | `tests/test_experimental.py` | 미검증 API가 명시적으로 unimplemented임을 고정 |

필수 검증 명령:

```bash
python -m compileall opinet tests
python -m pytest
python -m pytest --cov=opinet --cov-fail-under=90
python -m mypy opinet
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
- 좌표 변환 정밀도는 `pykrtour` 테스트가 소유합니다. `pyopinet`에서는 오피넷 모델 경계가 `PlaceCoordinate`/`KatecPoint`를 직접 쓰는지 확인합니다.
- `types-requests`는 `mypy`용 개발 의존성입니다. 제거하면 타입 검사가 실패합니다.

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
| 좌표 value object | `pykrtour.PlaceCoordinate`, `pykrtour.KatecPoint` |
| raw payload | `AvgPrice.raw`, `Station.raw`, `StationDetail.raw`, `OilPrice.raw`, `AreaCode.raw` |
| Station product context | `Station.product_code`, `Station.product_name` |
| Station trade context | `Station.trade_date`, `Station.trade_time` |
| Station normalized helpers | `provider_station_id`, `provider_product_code`, `provider_product_name`, `fuel_type`, `brand_code`, `coordinate`, `katec_coordinate` |
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
from pykrtour import PlaceCoordinate
from opinet import OpinetClient, ProductCode

client = OpinetClient()
station = client.search_stations_around(
    coordinate=PlaceCoordinate(lon=127.0276, lat=37.4979),
    prodcd=ProductCode.DIESEL,
)[0]

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
```

이 예시는 pyopinet의 normalized 모델만 사용합니다. 저장 schema, cache 전략, raw 보관 여부는 호출 애플리케이션의 책임입니다.

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

- `opinet/py.typed` marker를 추가했습니다.
- `pyproject.toml`의 setuptools package data에 `py.typed`를 등록했습니다.
- dev extra에 packaging smoke용 `build`, `wheel`, `setuptools>=68`를 명시했습니다.
- `tests/test_pep561_packaging.py`에서 wheel/sdist를 빌드하고, 각 산출물을 임시 venv에 설치한 뒤 `import opinet`, `import opinet.normalized`, downstream mypy reveal smoke를 실행합니다.

이 테스트는 Pydantic DTO와 기존 public export가 설치 환경에서도 typed package로 보이는지 확인합니다.
