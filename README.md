# opinet-py

[한국석유공사(KNOC) 오피넷](https://www.opinet.co.kr) 오픈 API의 비공식 Python 클라이언트 라이브러리.

전국 약 1만 2천여 개 주유소·자동차충전소의 가격 정보를 조회하고, 좌표(KATEC ↔ WGS84) 변환과 응답 데이터의 Python 네이티브 타입 변환을 자동 처리합니다.

> 현재 저장소는 `opinet-api.md` 명세를 바탕으로 공식 5개 엔드포인트를 구현한 초기 라이브러리입니다. PDF 가이드북의 추가 API는 아직 검증 전이므로 `opinet.experimental`에 분리합니다.

---

## 핵심 특징

- **공식 검증된 5개 엔드포인트**: 한국석유공사 공식 사이트의 [오픈 API 페이지](https://www.opinet.co.kr/user/custapi/openApiInfo.do)에 등재된 5종을 1차 구현 대상으로 삼아 안정성을 확보합니다.
- **Python 네이티브 타입으로 자동 변환**: API가 모두 문자열로 주는 응답을 `datetime.date`, `datetime.time`, `float`, `bool`, `StrEnum`으로 변환해서 모델에 채웁니다. 사용자가 별도 캐스팅할 필요 없습니다.
- **좌표계 자동 변환**: 사용자 입력은 WGS84(위경도), API 호출은 KATEC. 응답의 KATEC 좌표는 자동으로 WGS84로 변환되어 모델에 채워집니다.
- **타입 안전한 모델**: `dataclass(frozen, slots)` 기반의 응답 모델, `StrEnum`으로 제품/상표/정렬/업종 코드를 정의합니다.
- **시도코드 ↔ 법정동코드 매핑**: 다른 정부 데이터와 join할 수 있도록 행정안전부 표준 법정동코드와의 양방향 매핑을 제공합니다.
- **체계적인 예외 매핑**: 인증 실패, 호출 한도, 네트워크 오류, 서버 오류, 파라미터 오류, 타입 변환 오류를 별도 예외로 구분합니다.
- **실제 응답 기반 fixture**: 명세서 자체가 오피넷 공식 사이트에서 발췌한 실제 응답을 포함하므로, 키 없이도 단위테스트가 동작합니다.

---

## 시작하기

### 1단계: 인증키 발급

1. https://www.opinet.co.kr/user/custapi/openApiNew.do 에서 회원가입 후 신청.
2. 자동 승인되며 즉시 키가 발급됩니다.
3. 환경변수에 저장:
   ```bash
   export OPINET_API_KEY="발급받은_키"
   ```

### 2단계: 라이브러리 설치

```bash
pip install opinet  # PyPI 배포 후
```

또는 소스에서:

```bash
git clone https://github.com/<your-org>/opinet-py.git
cd opinet-py
pip install -e .
```

개발 환경:

```bash
pip install -e ".[dev]"
pytest
```

실제 API 서버 테스트를 하려면 저장소에 커밋되지 않는 로컬 `.env`에 키를 넣습니다.

```bash
cp .env.example .env
# .env 안의 OPINET_API_KEY 값을 본인 키로 변경
pytest -m live --run-live
```

### 3단계: 사용

```python
from datetime import date, time
from opinet import OpinetClient, ProductCode, SortOrder
from opinet.codes import StationType, BrandCode

client = OpinetClient()  # 환경변수에서 키 자동 로드

# 1) 전국 평균가 — 모든 필드는 Python 타입
for row in client.get_national_average_price():
    assert isinstance(row.trade_date, date)   # YYYYMMDD → date
    assert isinstance(row.price, float)       # "1919.44" → 1919.44
    assert isinstance(row.diff, float)        # "+0.39" → 0.39
    assert isinstance(row.product_code, ProductCode)  # "B027" → enum
    print(f"{row.product_name}: {row.price:,.2f}원 ({row.diff:+.2f}) — {row.trade_date}")

# 2) 강남역 반경 3km 내 가장 싼 휘발유 5곳 — 좌표 자동 변환
stations = client.search_stations_around(
    wgs84=(127.0276, 37.4979),  # 강남역 위경도
    radius_m=3000,
    prodcd=ProductCode.GASOLINE,
    sort=SortOrder.PRICE,
)
for s in stations[:5]:
    # KATEC, WGS84 모두 float
    print(f"{s.name}: {s.price:,.0f}원, {s.distance_m:.0f}m, "
          f"({s.lon:.4f}, {s.lat:.4f})")

# 3) 주유소 ID로 상세 조회
detail = client.get_station_detail("A0010207")
assert isinstance(detail.station_type, StationType)
assert isinstance(detail.has_carwash, bool)
print(f"{detail.name} ({detail.brand.name})")
print(f"  주소: {detail.address_road}")
print(f"  업종: {detail.station_type.name}")  # GAS_STATION / LPG_STATION / BOTH
print(f"  편의시설: 정비={detail.has_maintenance}, 세차={detail.has_carwash}")
for p in detail.prices:
    # trade_date는 date, trade_time은 time
    print(f"  {p.product_code.name}: {p.price:,.0f}원 "
          f"({p.trade_date.isoformat()} {p.trade_time.isoformat()})")

# 4) 전국 휘발유 최저가 Top 10
for s in client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=10):
    print(f"{s.price:,.0f}원 — {s.name}")

# 5) 시도 코드 목록 — code는 str (선행 0 보존)
for area in client.get_area_codes():
    print(f"{area.code}: {area.name}")  # "01: 서울"
```

---

## 응답 데이터의 Python 타입 ⭐

오피넷 API는 모든 값을 문자열로 반환합니다 (`"PRICE": "1745"`, `"TRADE_DT": "20250723"` 등). 본 라이브러리는 이를 자동으로 Python 네이티브 타입으로 변환합니다.

| API 원본 | Python 타입 | 예시 |
|---|---|---|
| 날짜 `"YYYYMMDD"` | `datetime.date` | `"20250723"` → `date(2025, 7, 23)` |
| 시각 `"HHMMSS"` | `datetime.time` | `"145618"` → `time(14, 56, 18)` |
| 가격/거리/좌표 | `float` | `"1919.44"` → `1919.44` |
| 부호 있는 등락값 | `float` | `"+0.39"` → `0.39` |
| Y/N 플래그 | `bool` | `"Y"` → `True` |
| 업종 (`LPG_YN`) | `StationType` enum | `"N"` → `StationType.GAS_STATION` |
| 상표 (`POLL_DIV_CO`) | `BrandCode` enum | `"SKE"` → `BrandCode.SKE` |
| 제품 (`PRODCD`) | `ProductCode` enum | `"B027"` → `ProductCode.GASOLINE` |
| 빈 문자열 / 공백 | `None` | `" "` → `None` |
| 시군구 코드 | `str` (선행 0 보존) | `"0113"` 그대로 |

타입 변환에 실패하면(예: 잘못된 날짜 포맷) `OpinetServerError`로 변환되어 raise됩니다.

---

## 제공 API (5종)

| 메서드 | 엔드포인트 | 반환 |
|---|---|---|
| `get_national_average_price()` | `avgAllPrice.do` | `list[AvgPrice]` |
| `get_lowest_price_top20()` | `lowTop10.do` | `list[Station]` |
| `search_stations_around()` | `aroundAll.do` | `list[Station]` (with `distance_m`) |
| `get_station_detail()` | `detailById.do` | `StationDetail` (with `prices: tuple[OilPrice, ...]`) |
| `get_area_codes()` | `areaCode.do` | `list[AreaCode]` |

상세 명세는 [`opinet-api.md`](./opinet-api.md) 참조.

### 코드 상수

```python
from opinet.codes import ProductCode, BrandCode, SortOrder, StationType, is_alddle

ProductCode.GASOLINE          # "B027" 휘발유
ProductCode.GASOLINE_PREMIUM  # "B034" 고급휘발유
ProductCode.DIESEL            # "D047" 자동차용경유
ProductCode.KEROSENE          # "C004" 실내등유
ProductCode.LPG               # "K015" 자동차용부탄

BrandCode.SKE   # SK에너지
BrandCode.GSC   # GS칼텍스
BrandCode.HDO   # 현대오일뱅크
BrandCode.SOL   # S-OIL
BrandCode.RTE   # 자영알뜰
BrandCode.RTX   # 고속도로알뜰
BrandCode.NHO   # 농협알뜰

SortOrder.PRICE      # "1" 가격순
SortOrder.DISTANCE   # "2" 거리순

StationType.GAS_STATION  # "N" 주유소
StationType.LPG_STATION  # "Y" 자동차충전소
StationType.BOTH         # "C" 겸업

is_alddle(BrandCode.RTE)  # True (RTE/RTX/NHO이면 알뜰)
is_alddle(BrandCode.SKE)  # False
```

---

## 좌표계 처리 (KATEC ↔ WGS84)

오피넷 API는 모든 좌표를 **KATEC** (오피넷 자체 TM 좌표계, m 단위)로 주고받습니다. 일반적인 위경도(WGS84)와 다릅니다.

본 라이브러리는 사용자 인터페이스를 **WGS84로 통일**하고, KATEC 변환은 내부에서 자동 처리합니다.

```python
# 입력: WGS84 (lon, lat)
stations = client.search_stations_around(wgs84=(127.0276, 37.4979), ...)

# 응답 모델: WGS84 + KATEC 둘 다 들어있음
station = stations[0]
station.lon, station.lat          # WGS84 (변환된 값, float)
station.katec_x, station.katec_y  # KATEC (서버가 준 원본, float)
```

직접 변환이 필요하면:

```python
from opinet.coords import wgs84_to_katec, katec_to_wgs84

x, y = wgs84_to_katec(127.0276, 37.4979)
lon, lat = katec_to_wgs84(314871.80, 544012.00)  # SK서광주유소
```

### KATEC proj 정의

```
+proj=tmerc +lat_0=38 +lon_0=128 +k=0.9999 +x_0=400000 +y_0=600000
+ellps=bessel +units=m
+towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43 +no_defs
```

오피넷 공식 응답의 실측 좌표와 ±10m 이내로 일치함을 검증.

---

## 시도코드 ↔ 법정동코드 매핑 ⭐

오피넷의 시도 코드는 **행정안전부 표준 법정동 코드와 완전히 다른 별도 체계**입니다. 다른 정부 데이터(부동산, 인구통계, 주민등록 등)와 join하려면 매핑이 필요합니다.

```python
from opinet.codes import opinet_sido_to_bjd, bjd_sido_to_opinet

# 오피넷 → 법정동
opinet_sido_to_bjd("01")  # → "11" (서울특별시)
opinet_sido_to_bjd("11")  # → "50" (제주특별자치도)
opinet_sido_to_bjd("19")  # → "36" (세종특별자치시)

# 법정동 → 오피넷
bjd_sido_to_opinet("11")  # → "01"
bjd_sido_to_opinet("26")  # → "10" (부산)
bjd_sido_to_opinet("51")  # → "03" (강원특별자치도 신코드 → 오피넷 강원)
bjd_sido_to_opinet("52")  # → "06" (전북특별자치도 신코드 → 오피넷 전북)
```

매핑 테이블 전체:

| 시도 | 오피넷 (`AREA_CD`) | 법정동 (앞 2자리) |
|---|---|---|
| 서울특별시 | `01` | `11` |
| 부산광역시 | `10` | `26` |
| 대구광역시 | `14` | `27` |
| 인천광역시 | `15` | `28` |
| 광주광역시 | `16` | `29` |
| 대전광역시 | `17` | `30` |
| 울산광역시 | `18` | `31` |
| 세종특별자치시 | `19` | `36` |
| 경기도 | `02` | `41` |
| 강원특별자치도 | `03` | `42` (또는 `51`) |
| 충청북도 | `04` | `43` |
| 충청남도 | `05` | `44` |
| 전북특별자치도 | `06` | `45` (또는 `52`) |
| 전라남도 | `07` | `46` |
| 경상북도 | `08` | `47` |
| 경상남도 | `09` | `48` |
| 제주특별자치도 | `11` | `50` |

> ⚠️ **두 코드 체계 사이에 산술 규칙은 없습니다** — 매핑 테이블만 가능. 오피넷은 단순 일련번호 방식이고 법정동은 광역시(11/26~31)·도(36/41~50)·세종(36) 별도 체계.
>
> ⚠️ 강원특별자치도(2023-06-11)와 전북특별자치도(2024-01-18) 출범으로 법정동 시도코드가 `51`/`52`로 변경된 케이스도 있습니다. `bjd_sido_to_opinet`은 양쪽 모두 받아들입니다.
>
> ⚠️ **시군구 4자리 코드는 자동 변환 불가능**합니다. 필요하면 응답의 `address_jibun`/`address_road`를 행정안전부 도로명주소 API로 역지오코딩하세요.

---

## 에러 처리

```python
from opinet.exceptions import (
    OpinetError,                  # 공통 베이스
    OpinetAuthError,              # 인증 실패 (Invalid Key, 401, 403)
    OpinetRateLimitError,         # 호출 한도 초과 (429)
    OpinetInvalidParameterError,  # 파라미터 오류 (호출 전)
    OpinetNoDataError,            # 결과 비어있음 (옵션)
    OpinetServerError,            # 5xx, 응답 파싱 실패, 타입 변환 실패
    OpinetNetworkError,           # 네트워크 레벨 오류
)

try:
    stations = client.search_stations_around(wgs84=(127.0, 37.5), radius_m=10000)
except OpinetInvalidParameterError as e:
    # radius_m > 5000 → 호출 전에 검증 실패
    print(f"파라미터 오류: {e}")
except OpinetAuthError:
    print("인증키를 확인하세요")
except OpinetRateLimitError:
    print("일일 호출 한도(1,500회)를 초과했습니다")
except (OpinetServerError, OpinetNetworkError) as e:
    print(f"일시적 오류, 재시도 권장: {e}")
```

5xx와 네트워크 오류는 라이브러리 내부에서 exponential backoff로 자동 재시도합니다 (기본 2회). 401/403/429는 즉시 실패시킵니다.

---

## 시도 코드 — 주의사항

오피넷의 시도 코드는 **일반적으로 알려진 행정구역 코드와 다릅니다**. 비공식 블로그/MCP 구현체에서 흔히 보이는 매핑(`01=서울, 02=경기, 03=인천, 04=강원, 05=부산`...)은 **틀린 정보**입니다.

오피넷 공식 `areaCode.do` 응답값:

| 코드 | 시도 | 코드 | 시도 |
|---|---|---|---|
| `01` | 서울 | `10` | 부산 |
| `02` | 경기 | `11` | 제주 |
| `03` | 강원 | `14` | 대구 |
| `04` | 충북 | `15` | 인천 |
| `05` | 충남 | `16` | 광주 |
| `06` | 전북 | `17` | 대전 |
| `07` | 전남 | `18` | 울산 |
| `08` | 경북 | `19` | 세종 |
| `09` | 경남 | | |

(`12`, `13` 결번)

운영 환경에서는 **`get_area_codes()`로 런타임에 코드를 가져와 캐싱**하는 것을 권장합니다.

---

## 주유소 상세정보의 함정

`detailById.do`의 일부 필드는 이름과 의미가 일치하지 않습니다.

### `LPG_YN`은 LPG 취급 여부가 아닙니다 → **업종구분**

| 값 | 의미 |
|---|---|
| `N` | 주유소 (휘발유/경유) |
| `Y` | 자동차충전소 (LPG) |
| `C` | 주유소/충전소 겸업 |

본 라이브러리는 이를 `StationType` enum과 `station_type` 필드로 매핑합니다.

### `KPETRO_YN`은 알뜰주유소가 아닙니다 → **품질인증주유소**

`KPETRO_YN=Y`는 한국석유관리원의 품질인증프로그램 협약 업체를 뜻합니다. **알뜰주유소와 무관합니다.** 알뜰 여부는 상표 코드로 판정하세요:

```python
from opinet.codes import is_alddle

is_alddle(detail.brand)  # brand가 RTE/RTX/NHO이면 True
detail.is_kpetro          # KPETRO_YN을 매핑한 별도 boolean (품질인증 여부)
```

---

## 반복 실수 방지 체크리스트

이 저장소에서 한 번 확인한 함정은 다음 규칙으로 고정합니다.

- fixture의 숫자/날짜/시간 값은 실제 API처럼 문자열로 둡니다. JSON number로 바꾸면 변환 테스트가 약해집니다.
- `RESULT.OIL`은 list뿐 아니라 단일 dict로 올 수 있으므로 항상 정규화합니다.
- `OIL_PRICE`도 단일 dict 또는 list 모두 처리합니다.
- `StationDetail` 전화번호 필드명은 `tel`입니다. `phone`으로 새 필드를 만들지 않습니다.
- `OilPrice`에는 `PRODNM`이 오지 않으므로 `product_name`을 만들지 않습니다.
- `POLL_DIV_CO`를 우선하고, 없을 때만 문서 표기의 `POLL_DIV_CD`를 fallback으로 봅니다.
- `GPOLL_DIV_CO=" "` 같은 공백은 `None`으로 정규화합니다.
- 좌표 범위 테스트는 주소 권역 확인용입니다. 실제 변환값의 소수점 하한을 임의로 좁히지 않습니다.
- `requests` 타입 검사를 위해 개발 의존성에는 `types-requests`를 포함합니다.

---

## PDF 가이드북의 22종 API에 대해

한국석유공사가 배포한 [2025 공공데이터 활용 가이드북 PDF](https://www.opinet.co.kr/)에는 무료 API가 22종으로 명시되어 있지만, 공식 사이트 [오픈 API 페이지](https://www.opinet.co.kr/user/custapi/openApiInfo.do)에는 5종만 등재되어 있습니다.

이는 두 가지 다른 게이트웨이로 추정됩니다:

| | 공식 오픈 API | PDF 가이드북 무료 API |
|---|---|---|
| 메뉴 위치 | 푸터 → 오픈 API | 유가관련정보 → 유가정보 API |
| URL 패턴 | `openApiInfo.do` | `custApiInfo.do` |
| 인증 파라미터 | `certkey` | `code` (추정) |
| 엔드포인트 수 | 5 | 22 |
| 명세 페이지 | 있음 | 없음 |

본 라이브러리는 공식 5종을 `OpinetClient`에 안정적으로 구현하고, PDF의 추가 17종은 `opinet.experimental.OpinetExperimentalClient`로 분리해 "검증되지 않음(Unverified)" 경고와 함께 제공합니다.

```python
# 공식 5종 (안정)
from opinet import OpinetClient

# PDF 추가 17종 (실험적)
from opinet.experimental import OpinetExperimentalClient
exp = OpinetExperimentalClient()
weekly = exp.get_weekly_average_price(ProductCode.GASOLINE)  # avgWeekPrice.do
```

실험 모듈의 메서드는 실제 호출이 동작하는지 보장하지 않습니다. PR을 통한 검증 보고를 환영합니다.

---

## Claude Code / AI Agent 사용

본 저장소는 [Claude Code](https://docs.claude.com/en/docs/claude-code) 등 AI 에이전트로 라이브러리를 자동 생성/유지보수할 수 있도록 [`SKILL.md`](./SKILL.md)를 포함합니다.

```bash
# Claude Code 글로벌 skill로 등록
mkdir -p ~/.claude/skills/opinet-python-builder
cp SKILL.md ~/.claude/skills/opinet-python-builder/

# 또는 프로젝트 단위 skill
mkdir -p .claude/skills/opinet-python-builder
cp SKILL.md .claude/skills/opinet-python-builder/
```

이후 Claude Code 세션에서:

> opinet-python-builder skill을 써서 처음부터 라이브러리 만들어줘. opinet-api.md를 먼저 읽고 시작해.

skill 파일은 다음을 정의합니다:
- 패키지 구조와 모듈 책임
- Python 네이티브 타입 변환 정책
- 시도코드 ↔ 법정동코드 매핑
- 예외 계층과 매핑 규칙
- KATEC 변환 구현 방식
- docstring 작성 원칙
- 테스트 전략과 fixture 처리
- 흔한 함정 (LPG_YN, KPETRO_YN, K015 vs K105 등)

다른 AI 에이전트(Cursor, Aider, Cline 등)에서도 `opinet-api.md` + `SKILL.md`를 컨텍스트로 제공하면 동일한 결과를 얻을 수 있습니다.

---

## 의존성

**런타임:**
- `requests` ≥ 2.28
- `pyproj` ≥ 3.5
- `pydantic` ≥ 2.0

**개발:**
- `pytest` ≥ 7.0
- `responses` ≥ 0.23 (HTTP mocking)
- `pytest-cov`
- `mypy` (선택)
- `types-requests` (mypy용)

Python 3.11 이상 (`StrEnum`, `slots=True` 사용).

---

## 검증

```bash
python -m compileall opinet tests
python -m pytest
python -m pytest --cov=opinet --cov-fail-under=90
python -m mypy opinet
```

기본 테스트는 네트워크를 사용하지 않고 `responses`로 HTTP 응답을 재생합니다. 실제 API 호출 테스트를 추가할 때는 `@pytest.mark.live`로 분리하고 `--run-live`와 `OPINET_API_KEY`를 요구하세요.
라이브 테스트는 `.env` 또는 환경변수의 `OPINET_API_KEY`를 읽지만, 키는 `.gitignore`로 보호되는 로컬 파일에만 둡니다.
키가 공식 open API 게이트웨이에 아직 provision되지 않은 경우 서버가 HTTP 200과 빈 `RESULT.OIL`을 줄 수 있으며, 이때 live 파싱 smoke는 skip됩니다.

구현 상태와 유지보수 체크리스트는 [`docs/implementation-status.md`](./docs/implementation-status.md)에 따로 정리되어 있습니다.

---

## 문서 작성 규칙

- 문서에서 파일 위치를 적을 때는 프로젝트 루트 기준 상대 경로를 사용합니다. 예: `opinet/client.py`, `tests/fixtures/avg_all_price.json`.
- 로컬 절대 경로는 저장소 문서에 남기지 않습니다.
- Python 내부 문서(docstring과 유지보수용 주석)는 한글로 작성합니다.
- API 필드명, 엔드포인트, enum 값처럼 원문 자체가 의미 있는 값은 그대로 둡니다.
- 이 Windows/PowerShell 환경에서 `rg`가 실행 권한 문제로 실패하면 반복 시도하지 말고 `git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`으로 우회합니다.
- 한글 문서/소스 파일은 `Get-Content -Encoding utf8` 또는 `Get-Content -Raw -Encoding utf8`로 확인합니다. PowerShell 기본 출력에서 한글이 깨져 보이면 UTF-8로 다시 읽습니다.

---

## 프로젝트 파일

```
.
├── AGENTS.md           # 에이전트 작업 지침
├── README.md            # 이 파일
├── opinet-api.md        # API 명세서 (라이브러리 구현 레퍼런스)
├── SKILL.md             # Claude Code용 자동 구현 skill
├── pyproject.toml       # 패키지/테스트 설정
├── docs/
│   └── implementation-status.md
├── opinet/              # 라이브러리 소스
│   ├── __init__.py
│   ├── client.py        # OpinetClient
│   ├── _http.py
│   ├── _convert.py      # 타입 변환 헬퍼
│   ├── exceptions.py
│   ├── codes.py         # enum + 시도매핑
│   ├── coords.py
│   ├── models.py
│   └── experimental/    # PDF 22종 중 미검증 17종
└── tests/
    ├── conftest.py
    ├── fixtures/        # 실제 API 응답 JSON
    └── test_*.py
```

---

## 호출 한도

PDF 가이드북 기준 **1,500 calls / 일**. 라이브러리는 옵션으로 사용량 카운터(`OpinetClient(track_usage=True)`)를 제공하여 잔여 호출 추정을 도울 수 있습니다.

응답 받은 데이터는 다음과 같은 시점까지 캐싱하면 호출 절감에 좋습니다:

| 데이터 | 갱신 주기 | 권장 캐시 TTL |
|---|---|---|
| 시도/시군구 코드 | 거의 변하지 않음 | 며칠 ~ 영구 |
| 주유소 상세 (위치, 편의시설) | 변경 드뭄 | 며칠 |
| 가격 정보 | 일 1~2회 갱신 | 1시간 ~ 6시간 |

---

## 기여

PR과 이슈를 환영합니다. 특히:

- `opinet.experimental`의 미검증 엔드포인트를 실제 키로 호출해 본 결과 (응답 fixture, query 결과)
- KATEC 좌표 변환 정확도 개선 데이터 (실제 GPS 측정값과의 비교)
- 시군구 코드 매핑 (예: `0113`이 강남구라면, 다른 4자리 코드도 매핑)
- 강원·전북 특별자치도 코드 변경 추적 (오피넷 `AREA_CD`가 `51`/`52`로 바뀐 시점)

테스트 추가:

```bash
pytest                              # 단위 + 통합
pytest -m live                      # 실제 API 호출 (OPINET_API_KEY 필요)
pytest --cov=opinet --cov-fail-under=90
```

---

## 라이선스

라이브러리 코드: MIT (또는 사용자 지정).

데이터: 한국석유공사 오피넷 이용 약관 준수.

본 프로젝트는 비공식이며 한국석유공사와 무관합니다.

---

## 참고 링크

- 오피넷 메인: https://www.opinet.co.kr
- 오픈 API 안내: https://www.opinet.co.kr/user/custapi/openApiIntro.do
- 오픈 API 목록: https://www.opinet.co.kr/user/custapi/openApiInfo.do
- 인증키 발급: https://www.opinet.co.kr/user/custapi/openApiNew.do
- 데이터 문의: (052) 216-2514, price@knoc.co.kr
- KNOC 공공데이터 가이드북: https://www.knoc.co.kr (공공데이터 메뉴)
- 행정안전부 행정표준코드관리시스템 (법정동): https://www.code.go.kr

## 변경 이력

| 일자 | 내용 |
|---|---|
| 2026-05-09 (rev9) | Windows/PowerShell 환경에서 `rg` 실행 권한 실패 시 우회 명령을 사용하고, 한글 파일은 UTF-8 인코딩을 명시해 읽는 규칙 추가. |
| 2026-05-09 (rev8) | 문서의 파일 위치 표기를 프로젝트 기준 상대 경로로 고정하고, Python 내부 문서를 한글로 작성한다는 규칙을 추가. |
| 2026-04-30 (rev3) | 공식 5개 엔드포인트 구현, fixture 기반 네트워크-free 테스트 115개, mypy/coverage 검증, 반복 실수 방지 체크리스트 추가. |
| 2026-04-30 (rev2) | 응답 데이터 Python 네이티브 타입 변환(`date`/`time`/`float`/`bool`/enum) 명시. 시도코드 ↔ 법정동코드 매핑 추가. |
| 2026-04-30 (rev1) | 초기 명세서 작성. 공식 사이트 기준 5개 API 검증. 시도코드/필드 의미 정정. |


---

## 공용 normalized layer

pyopinet은 OpiNet 원본 응답을 Python 타입으로 변환한 기존 모델을 유지하면서, 여러 프로젝트에서 공통으로 재사용하기 좋은 normalized 필드도 함께 제공합니다. 이 계층은 OpiNet 자체의 도메인 해석만 담당합니다. DB 저장 방식, ETL cache, 서비스별 enum 정책, raw/serving table 설계는 각 애플리케이션에서 결정하면 됩니다.

### canonical 유종

`ProductCode`는 OpiNet provider code를 보존하고, `FuelType`은 앱에서 안정적으로 쓰기 좋은 문자열 값을 제공합니다.

```python
from opinet import FuelType, ProductCode, fuel_type_to_product_code, product_code_to_fuel_type

product_code_to_fuel_type(ProductCode.GASOLINE)          # FuelType.GASOLINE
product_code_to_fuel_type(ProductCode.GASOLINE_PREMIUM)  # FuelType.PREMIUM_GASOLINE
product_code_to_fuel_type(ProductCode.DIESEL)            # FuelType.DIESEL
product_code_to_fuel_type(ProductCode.LPG)               # FuelType.LPG
product_code_to_fuel_type(ProductCode.KEROSENE)          # FuelType.KEROSENE

FuelType.GASOLINE.value          # "gasoline"
FuelType.PREMIUM_GASOLINE.value  # "premium_gasoline"
FuelType.DIESEL.value            # "diesel"
FuelType.LPG.value               # "lpg"
FuelType.KEROSENE.value          # "kerosene"

fuel_type_to_product_code(FuelType.DIESEL)  # ProductCode.DIESEL
```

알 수 없는 provider code나 `FuelType.UNKNOWN`을 역변환하려는 경우에는 `OpinetInvalidParameterError`가 발생합니다.

### Station normalized 필드

`lowTop10.do`와 `aroundAll.do`의 Station 응답은 OpiNet row에 `PRODCD`가 없는 경우가 많습니다. 이때 pyopinet은 요청에 사용한 `prodcd`를 `Station.product_code`에 채웁니다. 응답 row에 `PRODCD`가 실제로 있으면 응답 값을 우선합니다.

```python
from opinet import OpinetClient, ProductCode

client = OpinetClient()

stations = client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=10)
station = stations[0]

station.product_code           # ProductCode.GASOLINE, 요청 context에서 보존
station.product_name           # 응답 PRODNM이 없으면 None
station.provider_product_code  # "B027"
station.provider_product_name  # 응답 PRODNM 또는 None
station.fuel_type              # FuelType.GASOLINE
station.provider_station_id    # OpiNet UNI_ID
station.brand_code             # OpiNet POLL_DIV_CO/POLL_DIV_CD 원문 code
```

최저가/주변검색 응답 row에 `TRADE_DT` 또는 `TRADE_TM`이 실제로 포함되면 `Station.trade_date`와 `Station.trade_time`에 각각 `datetime.date`, `datetime.time`으로 노출됩니다. 필드가 없으면 `None`입니다.

### 좌표 value object

기존 호환 필드인 `station.katec_x`, `station.katec_y`, `station.lon`, `station.lat`는 그대로 유지됩니다. 새 코드에서는 `station.coordinates`를 사용하면 좌표 순서를 더 명확히 다룰 수 있습니다.

```python
coords = station.coordinates

coords.katec.x, coords.katec.y      # KATEC (x, y), meters
coords.wgs84.lon, coords.wgs84.lat  # WGS84 (lon, lat), degrees

coords.katec.as_x_y()      # (x, y)
coords.wgs84.as_lon_lat()  # (lon, lat)
```

`KatecPoint`, `Wgs84Point`, `StationCoordinates`는 모두 finite float만 허용합니다. WGS84 tuple order는 항상 `(lon, lat)`입니다.

### AreaCode helper

`AreaCode`는 OpiNet code level과 BJD 시도 prefix를 명시적으로 제공합니다. 시도는 2자리, 시군구는 4자리입니다. 시군구 4자리 OpiNet code를 법정동 10자리 code로 자동 변환할 수는 없으며, pyopinet은 그런 변환을 추정하지 않습니다.

```python
area = client.get_area_codes("01")[0]

area.code_level        # "sigungu"
area.parent_sido_code  # "01"
area.bjd_sido_prefix   # "11"
```

잘못된 길이의 code나 미확인 OpiNet 시도 code는 `OpinetInvalidParameterError`로 실패합니다.

### raw payload 보존

`AvgPrice`, `Station`, `StationDetail`, `OilPrice`, `AreaCode`는 마지막 dataclass 필드로 `raw`를 가집니다. `raw`에는 타입 변환 전 원본 row payload가 보존됩니다. 숫자, 날짜, 시간도 OpiNet 응답처럼 문자열입니다.

```python
avg = client.get_national_average_price()[0]

avg.price            # 1919.44, float
avg.trade_date       # datetime.date(2025, 7, 23)
avg.raw["PRICE"]     # "1919.44", provider 원문 문자열
avg.raw["TRADE_DT"]  # "20250723"
```

`raw`는 읽기 전용 mapping입니다. `StationDetail.raw["OIL_PRICE"]`처럼 nested `OIL_PRICE`가 있으면 가능한 한 원형 row를 보존하되, 내부 mapping도 읽기 전용으로 제공합니다. `certkey`, `api_key`, `authorization` 같은 인증 관련 key는 raw에 남기지 않습니다.

### normalized 저장 예시

아래 예시는 앱별 adapter를 최소화하고, pyopinet의 공용 해석 결과를 그대로 저장 계층에 넘기는 형태입니다.

```python
def to_station_record(station):
    return {
        "provider": "opinet",
        "provider_station_id": station.provider_station_id,
        "provider_product_code": station.provider_product_code,
        "provider_product_name": station.provider_product_name,
        "fuel_type": station.fuel_type.value,
        "brand_code": station.brand_code,
        "price": station.price,
        "trade_date": station.trade_date,
        "trade_time": station.trade_time,
        "katec_x": station.coordinates.katec.x,
        "katec_y": station.coordinates.katec.y,
        "lon": station.coordinates.wgs84.lon,
        "lat": station.coordinates.wgs84.lat,
        "raw": dict(station.raw),
    }
```

`raw`를 저장할지, 별도 raw table에 둘지, serving table에 normalized 값만 둘지는 애플리케이션 정책으로 결정하세요. pyopinet은 OpiNet domain parsing과 canonical helper만 제공합니다.

| 날짜 | 내용 |
|---|---|
| 2026-05-06 (rev4) | 공용 normalized layer 추가. `FuelType`, ProductCode 양방향 mapping, Station product/trade context, coordinate value object, AreaCode helper, read-only raw payload 보존을 문서화. |

### normalized DTO records

`opinet.normalized` 모듈은 앱 저장 계층에 바로 넘기기 쉬운 Pydantic DTO record를 제공합니다. 기존 `AvgPrice`, `Station`, `AreaCode` 모델은 그대로 유지되고, 필요할 때 `to_normalized()`로 변환합니다. DTO는 Pydantic v2 `BaseModel` 기반이며 `frozen=True`, `extra="forbid"` 설정으로 불변 record처럼 동작합니다.

```python
from opinet import OpinetClient, ProductCode
from opinet.normalized import (
    NormalizedFuelAverage,
    NormalizedFuelStation,
    NormalizedFuelStationDetail,
    NormalizedFuelStationDetailPrice,
    NormalizedFuelRegionCode,
    to_json_safe_raw,
)

client = OpinetClient()

avg = client.get_national_average_price()[0]
avg_record = avg.to_normalized(endpoint="avgAllPrice.do")
assert isinstance(avg_record, NormalizedFuelAverage)
assert avg_record.provider == "opinet"
assert avg_record.provider_product_code == "B034"
assert avg_record.fuel_type.value == "premium_gasoline"
assert avg_record.price_datetime().tzinfo is not None  # Asia/Seoul midnight by default
assert avg_record.price_timestamp() == avg.price_timestamp()

station = client.get_lowest_price_top20(ProductCode.GASOLINE)[0]
station_record = station.to_normalized(endpoint="lowTop10.do")
assert isinstance(station_record, NormalizedFuelStation)
assert station_record.provider_station_id == station.provider_station_id
assert station_record.provider_product_code == "B027"  # request context is preserved
assert station_record.provider_product_name is None    # PRODNM is absent in many station rows
assert station_record.trade_datetime() is None         # unless TRADE_DT and TRADE_TM both exist

detail = client.get_station_detail("A0010207")
detail_record = detail.to_normalized(endpoint="detailById.do")
assert isinstance(detail_record, NormalizedFuelStationDetail)
assert detail_record.provider_station_id == detail.provider_station_id
assert detail_record.brand_code == "SKE"
assert detail_record.sub_brand_code is None
assert detail_record.station_type.value == "N"         # LPG_YN 업종구분
assert detail_record.sigun_code == "0113"
assert detail_record.has_carwash is True
assert detail_record.is_kpetro is False                # 품질인증 여부
assert isinstance(detail_record.prices[0], NormalizedFuelStationDetailPrice)
assert detail_record.prices[0].provider_station_id == "A0010207"
assert detail_record.prices[0].provider_product_code == "B027"
assert detail_record.prices[0].fuel_type.value == "gasoline"

area = client.get_area_codes("01")[0]
area_record = area.to_normalized()
assert isinstance(area_record, NormalizedFuelRegionCode)
assert area_record.code_level == "sigungu"
assert area_record.parent_sido_code == "01"
assert area_record.bjd_sido_prefix == "11"

plain_raw = to_json_safe_raw(station.raw)  # plain dict/list, safe for json.dumps

payload = station_record.model_dump(mode="json")  # Pydantic JSON mode
```

`NormalizedFuelAverage.price_datetime()`는 평균가처럼 날짜만 있는 record를 KST 자정의 timezone-aware `datetime`으로 반환합니다. `NormalizedFuelStation.trade_datetime()`는 `trade_date`와 `trade_time`이 모두 있을 때만 KST timezone-aware `datetime`을 반환하고, 둘 중 하나라도 없으면 `None`을 반환합니다.

`NormalizedFuelStationDetail`은 `detailById.do`의 주유소 단위 정보를 보존합니다. station id/name, brand/sub-brand code, `StationType`, sigun code, 주소, 전화번호, KATEC/WGS84 좌표, 편의시설 flag, `is_kpetro`, nested `NormalizedFuelStationDetailPrice` 가격 목록, JSON-safe raw payload를 제공합니다.

`NormalizedFuelRegionCode`는 OpiNet 지역 코드의 level, parent sido, BJD sido prefix까지만 제공합니다. OpiNet 시군구 4자리 code를 법정동 10자리 code로 자동 변환하지 않습니다.

### PEP 561 typing

pyopinet은 PEP 561 typed package입니다. 배포 산출물에는 `opinet/py.typed` marker가 포함되며, downstream 프로젝트의 mypy가 `opinet`과 `opinet.normalized` 타입 정보를 직접 읽을 수 있습니다.

패키징 테스트는 wheel과 sdist를 각각 임시 venv에 설치한 뒤 `import opinet`, `import opinet.normalized`, downstream mypy smoke를 확인합니다.

| 날짜 | 내용 |
|---|---|
| 2026-05-06 (rev5) | `opinet.normalized` Pydantic DTO layer 추가. `NormalizedFuelAverage`, `NormalizedFuelStation`, `NormalizedFuelRegionCode`, KST datetime helper, JSON-safe raw 변환 helper, 모델별 `to_normalized()` 문서화. |
| 2026-05-06 (rev6) | PEP 561 `py.typed` marker와 package data 설정 추가. wheel/sdist 설치 후 import와 downstream mypy smoke 테스트 추가. |
| 2026-05-07 (rev7) | `StationDetail.to_normalized()`와 `NormalizedFuelStationDetail`, `NormalizedFuelStationDetailPrice` DTO 추가. |
