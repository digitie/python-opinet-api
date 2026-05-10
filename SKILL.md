---
name: opinet-python-builder
description: Use this skill when the user asks to build, extend, debug, or test a Python client library for the Korean Opinet (오피넷) free fuel-price API. Triggers include any mention of "오피넷", "opinet", "유가정보 API", "주유소 가격 API", or filenames like opinet/client.py. Also use when wiring Opinet KATEC/WGS84 coordinates through pykrtour, mapping Opinet sido codes to BJD (법정동) codes, or mapping Opinet HTTP/body errors to Python exceptions. Do NOT use for unrelated KNOC datasets, gov.kr public data portal datasets, or non-Korean fuel APIs.
---

# Opinet Python Library Builder

You are helping build/maintain a Python client for the Korean **Opinet** free fuel-price API (한국석유공사 오피넷). The full API spec lives in `opinet-api.md` in the same project — **read it before writing any code or tests**.

## Project invariants (do not violate)

1. **Base URL**: `https://www.opinet.co.kr/api/`
2. **Auth parameter**: `certkey` (NOT `code`). The official site uses `certkey`. Some unofficial blogs use `code` — that's a different gateway (PDF guidebook's `custApi`).
3. **Output format**: always request `out=json`. XML is debug-only.
4. **Coordinate system**: every response coordinate (`GIS_X_COOR`, `GIS_Y_COOR`) and every request coordinate (`x`, `y` for `aroundAll.do`) is **KATEC**. Use `pykrtour.PlaceCoordinate` for WGS84 and `pykrtour.KatecPoint` for KATEC directly.
5. **Quota**: ~1,500 calls/day per the PDF guidebook. Do not add automatic retries for 401/403/429.
6. **No XML parsing in user-facing methods**.
7. **All response fields are converted to Python native types** before the model is returned to the user. The API itself returns everything as strings. See "Type conversion policy" below.

## Documentation style invariants

1. 문서에서 파일 위치를 언급할 때는 프로젝트 루트 기준 상대 경로만 사용한다. 예: `opinet/client.py`, `tests/fixtures/avg_all_price.json`.
2. 로컬 절대 경로는 저장소 문서에 남기지 않는다.
3. Python 내부 문서(모듈, 클래스, 함수, 메서드 docstring과 유지보수용 주석)는 한글로 작성한다.
4. API 필드명, 엔드포인트명, enum 값, 외부 오류 메시지처럼 원문 자체가 의미 있는 값은 그대로 둔다.

## Local tooling invariants

1. 이 Windows/PowerShell 환경에서는 `rg`가 실행 권한 문제로 실패할 수 있다. 실패하면 반복 시도하지 말고 `git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`을 사용한다.
2. 한글 Markdown/Python 파일을 PowerShell에서 읽을 때는 `Get-Content -Encoding utf8` 또는 `Get-Content -Raw -Encoding utf8`을 사용한다.
3. PowerShell 기본 출력에서 한글이 깨져 보이면 파일 손상으로 간주하지 말고 UTF-8 인코딩을 명시해서 재확인한다.

## Shared-library reuse invariants

1. 공통 타입, 좌표 변환, POI 정규화처럼 다른 TripMate 라이브러리에 이미 구현된 기능은 `opinet` 안에 다시 만들지 말고 해당 라이브러리를 직접 의존한다.
2. `pykrtour`가 제공하는 `PlaceCoordinate`, `KatecPoint` 같은 값 객체는 파라미터와 리턴 모델에서 그대로 사용한다. 단순 wrapper, compatibility alias, mirror dataclass, proxy method를 새로 만들지 않는다.
3. 이 원칙은 "최소 수정"보다 우선한다. 직접 의존으로 공개 API 변경이 필요하면 README, `opinet-api.md`, tests를 함께 바꿔 새 경계를 명확히 한다.
4. `SIGUNCD`는 오피넷 자체 4자리 시군구 코드다. 법정동 5자리 시군구 코드나 10자리 법정동코드와 같다고 추정하거나 `pykrtour` 법정동 DTO로 강제 변환하지 않는다.

## Five official endpoints (start here)

These are the only endpoints with a public spec page on the Opinet site:

| Method | Endpoint | apiId |
|---|---|---|
| `get_national_average_price()` | `avgAllPrice.do` | 4 |
| `get_lowest_price_top20()` | `lowTop10.do` | 2 |
| `search_stations_around()` | `aroundAll.do` | 3 |
| `get_station_detail()` | `detailById.do` | 1 |
| `get_area_codes()` | `areaCode.do` | 5 |

The PDF guidebook mentions 22 free APIs but only 5 are formally documented. Put the other 17 in `opinet/experimental/client.py` with explicit "Unverified" warnings in every docstring.

## Required deliverables when implementing from scratch

```
opinet/
├── opinet/__init__.py        # re-export OpinetClient, exceptions, enums, models
├── opinet/client.py          # OpinetClient (5 official endpoints)
├── opinet/_http.py           # HTTP helper + error mapping; one place for response → exception logic
├── opinet/_convert.py        # type conversion helpers (to_date, to_time, to_float_or_none, to_bool_yn, strip_or_none)
├── opinet/exceptions.py      # OpinetError + 6 subclasses (see below)
├── opinet/codes.py           # ProductCode, BrandCode, SortOrder, StationType (StrEnum)
│                             # is_alddle()
│                             # OPINET_TO_BJD / BJD_TO_OPINET / BJD_LEGACY_TO_NEW (sido mapping)
│                             # opinet_sido_to_bjd / bjd_sido_to_opinet
├── opinet/models.py          # frozen slots dataclasses (Python native types)
├── opinet/experimental/
│   ├── __init__.py
│   └── client.py             # OpinetExperimentalClient (PDF guidebook 17 unverified APIs)
├── tests/conftest.py
├── tests/fixtures/*.json     # captured responses (see "Initial fixtures" below)
├── tests/test_*.py
└── pyproject.toml            # deps: requests, pydantic, pykrtour[geo]; dev: pytest, responses, pytest-cov
```

## Type conversion policy ⭐ CRITICAL

The Opinet API returns everything as strings — `"PRICE": "1745"`, `"TRADE_DT": "20250723"`, `"GIS_X_COOR": "314871.80000"`. The library converts these to Python native types **at the model boundary**, never exposing raw strings to users.

### Conversion table

| API original | Python type | Helper | Example |
|---|---|---|---|
| `"YYYYMMDD"` | `datetime.date` | `to_date()` | `"20250723"` → `date(2025, 7, 23)` |
| `"HHMMSS"` | `datetime.time` | `to_time()` | `"145618"` → `time(14, 56, 18)` |
| numeric string (incl. `+`/`-` sign) | `float` | `to_float_or_none()` | `"+0.39"` → `0.39`, `"1745"` → `1745.0` |
| `"Y"` / `"N"` | `bool` | `to_bool_yn()` | `"Y"` → `True` |
| `"N"` / `"Y"` / `"C"` (LPG_YN) | `StationType` enum | enum constructor | `"N"` → `StationType.GAS_STATION` |
| Brand code (`"SKE"` etc.) | `BrandCode` enum | enum constructor | `"SKE"` → `BrandCode.SKE` |
| Product code (`"B027"` etc.) | `ProductCode` enum | enum constructor | `"B027"` → `ProductCode.GASOLINE` |
| Empty string / single space / null | `None` | `strip_or_none()` | `" "` → `None` |
| Codes with leading zeros (`"0113"`, `"01"`) | `str` (preserved) | (no conversion) | `"0113"` stays `"0113"` |
| KATEC coords | `float` (m) | `to_float_or_none()` + auto WGS84 conversion to `lon`/`lat` | `"314871.80000"` → `314871.8` |

### Rules

1. **Never convert IDs/codes to int.** `SIGUNCD="0113"`, `AREA_CD="01"`, `UNI_ID="A0010207"` all stay as `str`.
2. **Always use `float()` for numbers, never `int()`** even if value looks integer-like — `PRICE` can be `"1919.44"`.
3. **Empty/blank strings normalize to `None`** — uniform behavior across all `*_or_none` helpers.
4. **Conversion failures (bad date format, non-numeric in numeric field) raise `OpinetServerError`** (wrapping the underlying ValueError). The HTTP layer catches them.
5. **Coords are stored in BOTH forms** on the model — `katec_x/katec_y` (raw) AND `lon/lat` (auto-converted). Conversion happens once at model creation.

### Helper module template (`opinet/_convert.py`)

```python
from datetime import date, datetime, time
from typing import Any

def to_date(s: Any) -> date | None:
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    s = str(s).strip()
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"invalid YYYYMMDD: {s!r}")
    return datetime.strptime(s, "%Y%m%d").date()

def to_time(s: Any) -> time | None:
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    s = str(s).strip()
    if len(s) != 6 or not s.isdigit():
        raise ValueError(f"invalid HHMMSS: {s!r}")
    return datetime.strptime(s, "%H%M%S").time()

def to_float_or_none(s: Any) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s:
        return None
    return float(s)

def to_bool_yn(s: Any) -> bool:
    if s is None:
        return False
    return str(s).strip().upper() == "Y"

def strip_or_none(s: Any) -> str | None:
    if s is None:
        return None
    s2 = str(s).strip()
    return s2 if s2 else None
```

All these helpers must have unit tests in `tests/test_convert.py` covering: valid inputs, empty/None, malformed inputs (must raise `ValueError`), and edge cases.

## Sido code ↔ BJD code mapping ⭐

Opinet's `AREA_CD` is **NOT** the standard Korean BJD (법정동) code. Users will often need to join Opinet data with other government datasets (real estate, demographics, residency) which use BJD. Provide a mapping module.

### The mapping

```python
# opinet/codes.py — module-level constants
OPINET_TO_BJD: dict[str, str] = {
    "01": "11",   # 서울특별시
    "02": "41",   # 경기도
    "03": "42",   # 강원특별자치도 (legacy code; new code may be "51")
    "04": "43",   # 충청북도
    "05": "44",   # 충청남도
    "06": "45",   # 전북특별자치도 (legacy code; new code may be "52")
    "07": "46",   # 전라남도
    "08": "47",   # 경상북도
    "09": "48",   # 경상남도
    "10": "26",   # 부산광역시
    "11": "50",   # 제주특별자치도
    "14": "27",   # 대구광역시
    "15": "28",   # 인천광역시
    "16": "29",   # 광주광역시
    "17": "30",   # 대전광역시
    "18": "31",   # 울산광역시
    "19": "36",   # 세종특별자치시
}

BJD_TO_OPINET: dict[str, str] = {v: k for k, v in OPINET_TO_BJD.items()}

# 2023-06-11 강원도 → 강원특별자치도 / 2024-01-18 전라북도 → 전북특별자치도
# Some datasets use new BJD codes 51/52; we accept both forms.
BJD_LEGACY_TO_NEW: dict[str, str] = {"42": "51", "45": "52"}
BJD_NEW_TO_LEGACY: dict[str, str] = {v: k for k, v in BJD_LEGACY_TO_NEW.items()}

def opinet_sido_to_bjd(opinet_code: str) -> str:
    """Opinet 2-digit sido code → BJD 2-digit prefix."""
    if opinet_code not in OPINET_TO_BJD:
        raise OpinetInvalidParameterError(
            f"unknown opinet sido code: {opinet_code!r}. "
            f"Valid codes are 01-11, 14-19 (12, 13 are unassigned)."
        )
    return OPINET_TO_BJD[opinet_code]

def bjd_sido_to_opinet(bjd_code: str) -> str:
    """BJD 2-digit prefix → Opinet 2-digit sido code.

    Accepts both legacy BJD (42/45) and new (51/52) for the
    special self-governing provinces.
    """
    # Normalize new codes to legacy
    if bjd_code in BJD_NEW_TO_LEGACY:
        bjd_code = BJD_NEW_TO_LEGACY[bjd_code]
    if bjd_code not in BJD_TO_OPINET:
        raise OpinetInvalidParameterError(f"unknown BJD sido code: {bjd_code!r}")
    return BJD_TO_OPINET[bjd_code]
```

### Mapping invariants

1. **17 sidos, no more.** Opinet doesn't issue codes 12, 13, 20, etc. Reject them.
2. **No arithmetic relationship** between Opinet and BJD codes — only the table.
3. **Sigungu (4-digit) codes are NOT mappable** between systems. Don't fake it. If a user needs sigungu mapping, they must geocode the address text.
4. **Don't change the table without verification.** If Opinet ever adds code `12` or `13`, or if `AREA_CD` for 강원/전북 changes to `51`/`52` after a special-province update, update with explicit comment + test.

## Exception hierarchy (exact)

```python
class OpinetError(Exception): ...
class OpinetAuthError(OpinetError): ...           # invalid key, 401, 403, body says "Invalid"
class OpinetRateLimitError(OpinetError): ...      # 429 or body says "Limit"/"초과"
class OpinetInvalidParameterError(OpinetError): ...  # raised BEFORE the HTTP call
class OpinetNoDataError(OpinetError): ...         # only when client(strict_empty=True)
class OpinetServerError(OpinetError): ...         # 5xx, parse failure, type conversion failure
class OpinetNetworkError(OpinetError): ...        # ConnectionError, Timeout
```

Centralize the response→exception mapping in `_http.py::_raise_for_response`. **Every endpoint method goes through this helper** — no per-endpoint exception logic.

Type conversion errors (e.g., bad date format from server) should be caught at the model construction site and re-raised as `OpinetServerError` with the original `ValueError` chained.

## KATEC ↔ WGS84

Opinet KATEC 변환 로직은 `pykrtour`에 둔다. `opinet`은 `pykrtour.PlaceCoordinate.to_katec()`, `PlaceCoordinate.from_katec()`, `pykrtour.KatecPoint`를 직접 호출하고, 내부 `coords.py`나 얇은 wrapper를 다시 만들지 않는다.

좌표 변환의 proj 문자열, transformer singleton, roundtrip tolerance는 `pykrtour` 테스트와 문서가 소유한다. `opinet` 테스트는 aroundAll 요청 파라미터가 `PlaceCoordinate`/`KatecPoint`에서 나온 값인지, 응답 모델이 같은 값 객체를 리턴하는지만 검증한다.

## Critical field gotchas (DO NOT misinterpret)

These are documented mistakes seen in unofficial implementations. **Read carefully:**

### `LPG_YN` is NOT "is LPG sold here" — it's the **station type**

| Value | Meaning |
|---|---|
| `N` | Gas station (gasoline/diesel only) |
| `Y` | Auto LPG charging station |
| `C` | Both (combined) |

Map this to `StationType` enum in `codes.py`. Field name on the model: `station_type`, not `has_lpg`.

### `KPETRO_YN` is NOT "is alddle (알뜰)" — it's **quality-certified by KPC**

`KPETRO_YN=Y` means the station is part of Korea Petroleum Quality & Distribution Authority's certification program. Alddle status is determined by **brand code**, not by this flag:

```python
ALDDLE_BRANDS = frozenset({BrandCode.RTE, BrandCode.RTX, BrandCode.NHO})
def is_alddle(brand) -> bool:
    if brand is None:
        return False
    try:
        return BrandCode(brand) in ALDDLE_BRANDS
    except ValueError:
        return False
```

Model field: `is_kpetro` (boolean for KPETRO_YN). Don't conflate with `is_alddle`.

### Sido codes are NOT what most blogs say

The Opinet `areaCode.do` returns these — they are **NOT** the standard Korean administrative codes:

```
01:서울  02:경기  03:강원  04:충북  05:충남  06:전북  07:전남  08:경북  09:경남
10:부산  11:제주  14:대구  15:인천  16:광주  17:대전  18:울산  19:세종
(12, 13 are unassigned)
```

For BJD code mapping, see `opinet_sido_to_bjd()` in `codes.py`.

### Field name `POLL_DIV_CD` vs `POLL_DIV_CO`

The official tables write `POLL_DIV_CD`, but actual XML responses use `POLL_DIV_CO`. The model parser must accept both:

```python
brand_str = oil.get("POLL_DIV_CO") or oil.get("POLL_DIV_CD")
brand = BrandCode(brand_str) if brand_str else None
```

Same for `GPOLL_DIV_CD` / `GPOLL_DIV_CO`.

### `K015` vs `K105`

apiId=2's official page has a typo: `K105:자동차부탄`. The correct product code is **`K015`** (verified by apiId=4 response example). Always use `K015`.

## Method naming and signatures

### Official 5

```python
def get_national_average_price(self) -> list[AvgPrice]: ...

def get_lowest_price_top20(
    self,
    prodcd: ProductCode,
    cnt: int = 10,           # 1..20, default 10
    area: str | None = None, # 2-digit sido or 4-digit sigun
) -> list[Station]: ...

def search_stations_around(
    self,
    *,                                       # keyword-only!
    wgs84: tuple[float, float] | None = None,  # (lon, lat)
    katec: tuple[float, float] | None = None,  # (x, y)
    radius_m: int = 5000,                    # 1..5000
    prodcd: ProductCode = ProductCode.GASOLINE,
    sort: SortOrder = SortOrder.PRICE,
) -> list[Station]: ...

def get_station_detail(self, uni_id: str) -> StationDetail: ...

def get_area_codes(self, sido: str | None = None) -> list[AreaCode]: ...
```

`search_stations_around` MUST be keyword-only and accept either `wgs84` OR `katec` (XOR). Validate before HTTP call. Radius bound: `1 ≤ radius_m ≤ 5000`.

`get_lowest_price_top20`: validate `1 ≤ cnt ≤ 20`. If `area` is given, must be exactly 2 or 4 chars and digits.

### Experimental 17

Naming follows English action verbs, never Korean transliteration:
- `get_sido_average_price`, `get_sigun_average_price`
- `get_recent_7days_price`, `get_recent_7days_sido_price`, `get_recent_7days_brand_price`
- `get_period_price`, `get_period_sido_price`, `get_period_brand_price`
- `get_weekly_average_price`
- `get_duty_*` for duty-free variants
- `get_urea_prices`, `search_stations_by_name`

Each experimental method's docstring must start with:

```
.. warning::
   이 엔드포인트는 PDF 가이드북에만 있고 공식 오피넷 open API
   페이지에는 문서화되어 있지 않습니다. 경로, 파라미터 이름,
   응답 구조는 검증되지 않았습니다. Last verified: <DATE> by <CONTRIBUTOR>.
```

## Docstring rules (every public method)

1. 모든 Python docstring은 한글로 작성한다. public 메서드는 1줄 요약으로 시작한다.
2. **Args**: type, meaning, allowed values/ranges, default.
3. **Returns**: model class, "empty list when no result" if applicable. **State explicitly that all fields are Python native types** (date/time/float/bool/enum) — not strings.
4. **Raises**: list every exception that can actually be thrown — `OpinetAuthError`, `OpinetRateLimitError`, `OpinetInvalidParameterError`, `OpinetNetworkError`, `OpinetServerError`. Skip ones impossible for that method.
5. **Example** with `# doctest: +SKIP` for any network call.
6. The exact endpoint name (e.g. `avgAllPrice.do`) and apiId in the body of the docstring.
7. Units: prices = 원, distance = m, KATEC = m, WGS84 = degrees.
8. 모듈, 클래스, private helper, 테스트 helper의 docstring도 한글로 유지한다.

## Models

`@dataclass(frozen=True, slots=True)`. **All fields are Python native types** (never str for what should be a number/date/bool). Stations always carry both `katec_x/katec_y` AND derived `lon/lat`.

Required dataclasses:
- `AvgPrice` — for `avgAllPrice.do`. `trade_date: date`, `price: float`, `diff: float`, `product_code: ProductCode`.
- `Station` — for `lowTop10.do` and `aroundAll.do`. Optional `distance_m: float | None`. `brand: BrandCode | None`.
- `StationDetail` — for `detailById.do`. `station_type: StationType`, `has_*: bool`, `is_kpetro: bool`, `prices: tuple[OilPrice, ...]`. `sigun_code: str` (preserve leading zeros).
- `OilPrice` — nested in `StationDetail`. `trade_date: date`, `trade_time: time`, `price: float | None`.
- `AreaCode` — for `areaCode.do`. `code: str`, `name: str`. Add `is_sido` / `is_sigungu` properties based on `len(code)`.

## Initial fixtures (paste these into `tests/fixtures/`)

Convert these XML responses (from `opinet-api.md`) to JSON for fixture files. Sample minimal JSON for `avg_all_price.json`:

```json
{
  "RESULT": {
    "OIL": [
      {"TRADE_DT": "20250723", "PRODCD": "B034", "PRODNM": "고급휘발유", "PRICE": "1919.44", "DIFF": "-0.10"},
      {"TRADE_DT": "20250723", "PRODCD": "B027", "PRODNM": "휘발유", "PRICE": "1667.33", "DIFF": "-0.23"},
      {"TRADE_DT": "20250723", "PRODCD": "D047", "PRODNM": "자동차용경유", "PRICE": "1532.22", "DIFF": "+0.39"},
      {"TRADE_DT": "20250723", "PRODCD": "C004", "PRODNM": "실내등유", "PRICE": "1295.23", "DIFF": "-0.72"},
      {"TRADE_DT": "20250723", "PRODCD": "K015", "PRODNM": "자동차용부탄", "PRICE": "1052.64", "DIFF": "-0.07"}
    ]
  }
}
```

> Important: keep numeric fields as **strings** in fixtures. The actual Opinet API returns strings, and we want fixture-based tests to exercise the conversion code path.

Required fixtures:
- `avg_all_price.json`
- `low_top10_B027.json`
- `around_all_gangnam.json`
- `detail_by_id_A0010207.json`
- `area_code_root.json`
- `area_code_sido_01.json` (optional, requires live call)
- `error_invalid_key.json` (`{"RESULT": "Invalid Key"}`)
- `error_rate_limit.json` (`{"RESULT": "Limit Exceeded"}`)
- `empty_oil.json` (`{"RESULT": {"OIL": []}}`)

## Testing rules

- **Default tests are network-free.** Use `responses` for HTTP mocking.
- Live tests live behind `@pytest.mark.live` and require `OPINET_API_KEY`.
- Every endpoint needs ≥3 tests: happy path (with explicit type assertions), empty result, error response.
- **Type assertions are mandatory** for happy-path tests. For each model field, `assert isinstance(value, ExpectedType)`. Don't just check that values are truthy.
- `_convert.py` helpers each need a parametrize'd test: valid inputs, empty/None, malformed inputs raising `ValueError`.
- `search_stations_around` needs explicit tests for: WGS84→KATEC conversion in query string, response KATEC→WGS84 conversion, both-args / no-args validation, radius bounds.
- `get_lowest_price_top20` needs `cnt` boundary tests (0, 1, 20, 21).
- `get_station_detail` needs explicit tests that `LPG_YN=N` → `StationType.GAS_STATION`, `KPETRO_YN=N` → `is_kpetro=False` (with a comment that this is NOT the alddle flag), `GPOLL_DIV_CO=" "` → `sub_brand=None`, `SIGUNCD="0113"` → `"0113"` (str, leading zero preserved), and that `OIL_PRICE` items have `trade_date: date` and `trade_time: time`.
- `get_area_codes` should verify the official 17-entry list (codes 01-11, 14-19) is returned and that `code` is `str`.
- Sido mapping tests: roundtrip all 17 sidos, special-province new codes (51, 52) normalize correctly, unknown codes raise `OpinetInvalidParameterError`.
- Coord tests use named landmarks (강남역 127.0276/37.4979, 서울시청 126.9784/37.5666, 부산시청 129.0756/35.1796) AND real station KATEC values from `opinet-api.md` §5.3.
- Coverage gate: `pytest --cov=opinet --cov-fail-under=90`.

### Type-assertion test pattern

```python
def test_avg_all_price_types(client, load_fixture):
    payload = load_fixture("avg_all_price.json")
    responses.add(responses.GET, "...", json=payload)
    rows = client.get_national_average_price()

    r = rows[0]
    assert isinstance(r.trade_date, date)
    assert r.trade_date == date(2025, 7, 23)
    assert isinstance(r.product_code, ProductCode)
    assert isinstance(r.product_name, str)
    assert isinstance(r.price, float)
    assert isinstance(r.diff, float)
    # explicitly check sign handling
    diesel = next(x for x in rows if x.product_code is ProductCode.DIESEL)
    assert diesel.diff == 0.39  # not 0.39 string, not "+0.39"
```

## HTTP layer specifics

```python
# _http.py — sketch
class _OpinetHttp:
    BASE = "https://www.opinet.co.kr/api/"

    def get(self, endpoint: str, params: dict) -> dict:
        params = {**params, "certkey": self._key, "out": "json"}
        try:
            r = self._session.get(self.BASE + endpoint, params=params, timeout=self._timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            raise OpinetNetworkError(str(e)) from e
        return self._raise_for_response(r)

    def _raise_for_response(self, r: requests.Response) -> dict:
        if r.status_code in (401, 403):
            raise OpinetAuthError(f"HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code == 429:
            raise OpinetRateLimitError(r.text[:200])
        if 500 <= r.status_code < 600:
            raise OpinetServerError(f"HTTP {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except ValueError as e:
            raise OpinetServerError(f"JSON parse failure: {e}") from e

        result = data.get("RESULT")
        if not isinstance(result, dict):
            text = str(result)
            if "Invalid" in text or "invalid" in text:
                raise OpinetAuthError(text[:200])
            if "Limit" in text or "초과" in text:
                raise OpinetRateLimitError(text[:200])
            raise OpinetServerError(f"Unexpected RESULT: {text[:200]}")
        return data
```

The result extraction (`OIL` array) and the dict-vs-list normalization happen in client methods, not here.

## Response normalization helpers (in client.py or _parse.py)

```python
def _normalize_oil(data: dict) -> list[dict]:
    """Always return list[dict] from RESULT.OIL, even if API gave a single dict."""
    oil = data["RESULT"].get("OIL")
    if oil is None:
        return []
    if isinstance(oil, dict):
        return [oil]
    return oil


def _build_station(oil: dict) -> Station:
    """Convert a raw OIL dict into Station model with all native types."""
    try:
        brand_str = oil.get("POLL_DIV_CO") or oil.get("POLL_DIV_CD")
        brand = BrandCode(brand_str) if brand_str else None
        katec_x = to_float_or_none(oil.get("GIS_X_COOR")) or 0.0
        katec_y = to_float_or_none(oil.get("GIS_Y_COOR")) or 0.0
        lon, lat = katec_to_wgs84(katec_x, katec_y)
        return Station(
            uni_id=str(oil["UNI_ID"]),
            name=str(oil.get("OS_NM", "")),
            brand=brand,
            price=to_float_or_none(oil.get("PRICE")),
            address_jibun=strip_or_none(oil.get("VAN_ADR")),
            address_road=strip_or_none(oil.get("NEW_ADR")),
            katec_x=katec_x,
            katec_y=katec_y,
            lon=lon,
            lat=lat,
            distance_m=to_float_or_none(oil.get("DISTANCE")),
        )
    except (ValueError, KeyError) as e:
        raise OpinetServerError(f"failed to parse station record: {e!r}") from e
```

## Common pitfalls to avoid

- **Don't return strings for numeric/date fields.** Always go through `_convert.py` helpers.
- Don't pass coordinates manually as URL strings — use `requests.get(params=...)` so encoding is handled.
- Don't trust that `RESULT.OIL` is always a list. The API sometimes returns a single dict for one-result responses.
- Don't trust that nested `OIL_PRICE` is always a list. It can also be a single dict.
- Don't add LPG_YN/KPETRO_YN to the model with their literal names — use `station_type` and `is_kpetro` to avoid future readers misinterpreting.
- Don't hardcode sido codes from memory or unofficial sources. Use the official 17-entry table from `opinet-api.md` §2.2.
- Don't silently coerce `int` for codes with leading zeros — `"0113"` != `113`. Keep them `str`.
- 좌표 변환은 `pykrtour` 값 객체를 직접 사용한다. `opinet.coords`, 단순 wrapper, legacy alias를 되살리지 않는다.
- KATEC has multiple "dialects" in the wild (different `+towgs84` values). The values in this skill match Opinet's published station coordinates within ±10 m. Don't change without re-verifying.
- For BJD mapping, don't try to derive Opinet sigungu (4-digit) codes algorithmically. They're not BJD sigungu/legal-dong codes and are not mappable without an explicit table.
- `StationDetail` uses `tel`, not `phone`.
- `OilPrice` does not include `product_name`; official `OIL_PRICE` rows do not include `PRODNM`.
- Keep fixture numeric/date/time values as strings. Turning them into JSON numbers weakens conversion tests.
- Prefer the actual response field `POLL_DIV_CO` / `GPOLL_DIV_CO`; accept `*_CD` only as fallback.
- Keep `types-requests` in dev dependencies so `python -m mypy opinet` stays green.

## When the user asks to add a new endpoint

1. Read the relevant section in `opinet-api.md`.
2. **Is it one of the 5 official endpoints?** Add to `OpinetClient` in `client.py`. Otherwise add to `OpinetExperimentalClient` with the "Unverified" warning.
3. Add a model in `models.py` if the response shape is new. **All fields must be Python native types.**
4. Add helper conversion calls — never put raw strings into the model.
5. Add ≥3 tests with a fixture in `tests/fixtures/`. Use string values in fixtures (matching API's actual format).
6. Add explicit type assertions in the happy-path test.
7. Update `__init__.py` re-exports (only for official; experimental is opt-in import).
8. Update `README.md` usage examples if user-facing.

## When the user reports a bug

1. Reproduce with a fixture from `tests/fixtures/` if possible.
2. If the bug needs a new fixture, capture from live API with key redacted (`[REDACTED]`).
3. Add a regression test BEFORE fixing.
4. If the bug is a type conversion edge case (e.g., a date format we hadn't seen), add a parametrize'd entry in `tests/test_convert.py` AND an integration fixture covering the same case.
5. Confirm the fix doesn't drop coverage below 90%.

## When the user asks to verify an experimental endpoint

1. They run with their real key against the experimental method.
2. If it works: capture the response as a fixture (key redacted), add a regression test with type assertions, move the method from `OpinetExperimentalClient` to `OpinetClient`, remove the "Unverified" warning, update the README's "Provided APIs" table.
3. If it fails with 404 or returns an error: document the failure mode in the docstring, leave the method in experimental.

## When the user asks about sido code translation

If the user wants to map Opinet data with another government dataset, point them at `opinet_sido_to_bjd()` / `bjd_sido_to_opinet()`. If they need sigungu (4-digit) mapping, explain that it's not algorithmically possible — they need to geocode the address text from `address_jibun`/`address_road` via the Korean MOIS road-address API, or use the embedded city name in the address.
