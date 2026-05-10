# 오피넷(Opinet) 오픈 API 명세서

> 한국석유공사(KNOC) 운영. 본 문서는 Python 라이브러리 구현용 레퍼런스입니다.
>
> **검증 출처:** https://www.opinet.co.kr/user/custapi/openApiInfo.do (2026-04 확인)
>
> 공식 사이트의 "오픈 API"에 등록된 **5개 API**가 본 라이브러리의 1차 구현 대상입니다.
> 한국석유공사 PDF 가이드북에서 언급되는 "유가정보 무료 API 22종"은 별도 게이트웨이(`custApi`)로 추정되며 공식 명세 페이지가 없으므로 본 라이브러리에서는 **부가(experimental) 모듈**로 분리합니다.

---

## 1. 개요

| 항목 | 값 |
|---|---|
| 공식 사이트 | https://www.opinet.co.kr |
| 오픈 API 안내 | https://www.opinet.co.kr/user/custapi/openApiIntro.do |
| 오픈 API 목록 | https://www.opinet.co.kr/user/custapi/openApiInfo.do |
| 인증키 발급 | https://www.opinet.co.kr/user/custapi/openApiNew.do |
| Base URL | `https://www.opinet.co.kr/api/` |
| 인증 파라미터 | **`certkey`** (공식) |
| 출력 포맷 파라미터 | `out=xml` 또는 `out=json` (모든 엔드포인트 공통, 필수) |
| 좌표계 | **KATEC** (오피넷 자체 TM 좌표계) |
| 호출 한도 | PDF 가이드북 기준 1,500 calls/일 (계약별 상이 가능) |
| 데이터 문의 | (052) 216-2514, price@knoc.co.kr |

### 1.1 인증 파라미터 — `certkey` vs `code`

오피넷 **공식 사이트의 5개 API 문서는 모두 `certkey`를 사용**합니다.
일부 비공식 블로그/예제에서는 `code`를 사용하는데, 이는 PDF 가이드북에서 언급한 "무료 API 22종"의 별도 게이트웨이일 가능성이 큽니다.

본 라이브러리는 **공식 사이트 명세에 따라 `certkey`를 기본**으로 채택합니다.

### 1.2 출력 포맷 권장

라이브러리 내부 호출은 **`out=json` 고정**(한글 인코딩 안전, dict로 즉시 처리). XML은 디버깅 옵션으로만 노출.

### 1.3 응답 데이터의 Python 타입 변환 정책 ⭐

오피넷 API는 모든 값을 **문자열로 반환**합니다 (`PRICE`, `DIFF`, `DISTANCE`, 좌표값까지). 라이브러리는 사용자가 즉시 사용 가능한 **Python 네이티브 타입으로 변환**해서 모델에 채웁니다. 변환 규칙:

| API 원본 형식 | 예시 값 | Python 타입 | 변환 책임 |
|---|---|---|---|
| 날짜 (`YYYYMMDD` 8자리 문자열) | `"20250723"` | `datetime.date` | 라이브러리 |
| 시각 (`HHMMSS` 6자리 문자열) | `"145618"` | `datetime.time` | 라이브러리 |
| 가격 (소수 가능 문자열) | `"1745"`, `"1919.44"` | `float` | 라이브러리 |
| 등락 (부호 포함 문자열) | `"+0.39"`, `"-0.10"` | `float` | 라이브러리 |
| 거리 (미터, 소수 문자열) | `"885.4"` | `float` | 라이브러리 |
| 좌표 (KATEC, 미터) | `"314871.80000"` | `float` | 라이브러리 |
| Y/N 불리언 플래그 | `"Y"` / `"N"` | `bool` | 라이브러리 |
| 업종 코드 (`LPG_YN`) | `"N"` / `"Y"` / `"C"` | `StationType` enum | 라이브러리 |
| 상표 코드 (`POLL_DIV_CO`) | `"SKE"` | `BrandCode` enum | 라이브러리 |
| 제품 코드 (`PRODCD`) | `"B027"` | `ProductCode` enum | 라이브러리 |
| 빈 문자열 / 공백 / `null` | `""`, `" "` | `None` | 라이브러리 |
| 시군구 코드 | `"0113"` | `str` (선행 0 보존) | 그대로 |
| 주유소 ID (`UNI_ID`) | `"A0010207"` | `str` | 그대로 |
| 좌표 (KATEC → WGS84 변환) | KATEC 입력 | `float` (WGS84 lon/lat) | 라이브러리 자동 변환 |

#### 변환 시 주의사항

1. **선행 0이 의미를 갖는 코드는 절대 `int`로 변환하지 않음.**
   - `SIGUNCD="0113"` → `str("0113")`으로 유지 (`int(113)`이 되면 `f"{x:04d}"`로 복원해야 하는 부담 발생).
   - `AREA_CD="01"`, `"02"` 등 시도 코드도 동일.
   - `PRODCD`, `POLL_DIV_CO`도 모두 `str` 기반 enum.

2. **숫자 변환은 항상 `float()` (정수처럼 보여도).**
   - `PRICE`가 `"1745"`로 와도 `float("1745")` → `1745.0`.
   - 절대 `int(price)` 금지: 일부 응답은 `1919.44` 같은 소수.

3. **부호 처리.**
   - `DIFF="+0.39"` 같은 명시적 부호도 `float()`이 자동 처리. `float("+0.39")` → `0.39`.

4. **빈 값의 일관된 처리.**
   - 공식 응답 예시에 `<GPOLL_DIV_CO> </GPOLL_DIV_CO>` (공백 1자) 같은 케이스 존재. `str.strip()` 후 빈 문자열이면 `None`.
   - 빈 가격 (해당 제품 미판매): `PRICE=""` → `None`. 단위 테스트로 강제.

5. **날짜·시간 파싱은 strict.**
   - `datetime.strptime(s, "%Y%m%d").date()` — 길이/포맷 어긋나면 즉시 `ValueError`. 라이브러리는 이를 catch해서 `OpinetServerError`로 변환할지, 아니면 raw 보존을 위한 옵션을 줄지 결정 필요. 본 명세서는 **strict 변환 후 `OpinetServerError`로 wrap**을 권장.

6. **좌표는 항상 두 형태로 모델에 들어감.**
   - 응답에서 받은 KATEC 원본: `katec_x`, `katec_y` (`float`, m).
   - 변환된 WGS84: `lon`, `lat` (`float`, °).
   - 사용자는 둘 중 어느 것이든 직접 접근 가능. 변환은 모델 생성 시 1회.

7. **명시적 변환 헬퍼는 한 곳에서 관리.**
   - `opinet/_parse.py` 또는 `opinet/_convert.py`에 `_to_date`, `_to_time`, `_to_float_or_none`, `_to_bool_yn`, `_strip_or_none` 등을 두고, 모든 모델 생성자가 이를 호출.

#### 변환 헬퍼 예시

```python
# opinet/_convert.py
from datetime import date, datetime, time
from typing import Any

def to_date(s: Any) -> date | None:
    """YYYYMMDD 8자리 문자열 → date. 빈/None은 None."""
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    s = str(s).strip()
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"invalid YYYYMMDD: {s!r}")
    return datetime.strptime(s, "%Y%m%d").date()

def to_time(s: Any) -> time | None:
    """HHMMSS 6자리 문자열 → time. 빈/None은 None."""
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
    return float(s)  # "+0.39", "-1.23", "1745" 등 모두 처리

def to_bool_yn(s: Any) -> bool:
    """Y/N → True/False. 빈/None/그 외 → False."""
    if s is None:
        return False
    return str(s).strip().upper() == "Y"

def strip_or_none(s: Any) -> str | None:
    if s is None:
        return None
    s2 = str(s).strip()
    return s2 if s2 else None
```

---

## 2. 코드 테이블

### 2.1 제품코드 (`prodcd`)

공식 사이트 명세 기준:

| 코드 | 제품 | 비고 |
|---|---|---|
| `B027` | 휘발유 (보통휘발유) | apiId=4의 `PRODNM`은 "휘발유" |
| `B034` | 고급휘발유 | |
| `D047` | 자동차용경유 | apiId=2에서는 "자동차경유"로 표기 |
| `C004` | 실내등유 | |
| `K015` | 자동차용부탄 (LPG) | apiId=4의 `PRODNM`은 "자동차용부탄" |

> ⚠️ **공식 사이트 apiId=2 페이지에는 `K105:자동차부탄`으로 오타 표기된 부분이 있습니다.** apiId=3, apiId=4를 비롯한 모든 다른 페이지는 `K015`이며, apiId=4 응답 예시에도 `K015`가 실제 사용되므로 정확한 코드는 **`K015`**입니다.

### 2.2 시도코드 (`area`/`sido`, 2자리) — ⚠️ 공식 검증 후 정정

**오피넷 공식 `areaCode.do` 응답값** (검증일: 2026-04):

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

> ⚠️ 비공식 블로그/MCP 구현체에서 흔히 보이는 매핑 (`01=서울, 02=경기, 03=인천, 04=강원, 05=부산`...) 과는 **완전히 다릅니다.** 위 표가 공식 응답 그대로의 값입니다. `12`, `13`은 결번입니다.
>
> 운영 환경에서는 항상 `areaCode.do`로 런타임에 코드 목록을 가져와 캐싱하는 전략을 권장.

### 2.3 시군구코드 (4자리)

- `areaCode.do?area=01` 같이 시도코드 2자리를 넘기면 해당 시도의 시군구 4자리 코드 목록 반환.
- 앞 2자리는 시도코드, 뒤 2자리는 시군구 일련번호로 보임 (예: `0113` = 서울 강남구 — apiId=1 응답의 `SIGUNCD` 참고).

### 2.4 상표코드 (`POLL_DIV_CD` / `POLL_DIV_CO`)

공식 사이트 명세 기준:

| 코드 | 의미 |
|---|---|
| `SKE` | SK에너지 |
| `GSC` | GS칼텍스 |
| `HDO` | 현대오일뱅크 |
| `SOL` | S-OIL |
| `RTE` | 자영알뜰 |
| `RTX` | 고속도로알뜰 |
| `NHO` | 농협알뜰 |
| `ETC` | 자가상표 |
| `E1G` | E1 |
| `SKG` | SK가스 |

> ⚠️ **필드 이름 불일치 주의**: 공식 문서의 *반환값 표*는 `POLL_DIV_CD`로 적혀 있지만, *응답 예시 XML*은 `POLL_DIV_CO`로 출력됩니다. **실제 응답은 `POLL_DIV_CO`**. 라이브러리는 양쪽을 모두 받아들이도록 (`POLL_DIV_CO` 우선, 없으면 `POLL_DIV_CD`) 구현해야 합니다.

### 2.5 정렬코드 (`sort`)

| 코드 | 의미 |
|---|---|
| `1` | 가격순 |
| `2` | 거리순 |

### 2.6 업종 / 부가시설 플래그 (apiId=1 detailById)

- `LPG_YN` = **업종구분** (N=주유소, Y=자동차충전소, C=주유소/충전소 겸업)
- `MAINT_YN` = 경정비 시설 존재 여부 (Y/N)
- `CAR_WASH_YN` = 세차장 존재 여부 (Y/N)
- `CVS_YN` = 편의점 존재 여부 (Y/N)
- `KPETRO_YN` = **품질인증주유소 여부** (한국석유관리원의 품질인증프로그램 협약 업체, Y/N)

> ⚠️ 흔한 오해 두 가지:
> 1. `LPG_YN`은 "LPG 취급 여부"가 **아닙니다** — 업종 자체를 가리킵니다.
> 2. `KPETRO_YN`은 "알뜰주유소 여부"가 **아닙니다** — 한국석유관리원 품질인증주유소 여부입니다. 알뜰 여부는 `POLL_DIV_CO ∈ {RTE, RTX, NHO}`로 판정하세요.

### 2.7 시도코드 ↔ 법정동코드 매칭 ⭐

**오피넷 시도코드는 법정동코드(행정안전부 표준)와 완전히 다릅니다.** 다른 정부 데이터(부동산, 주민등록, 법원 등)와 연동하려면 매핑 변환이 필수입니다.

법정동코드(KOSIS/행정안전부) 시도 부분(앞 2자리):

| 시도 | 오피넷 (`AREA_CD`) | 법정동 (앞 2자리) | 비고 |
|---|---|---|---|
| 서울특별시 | `01` | `11` | |
| 부산광역시 | `10` | `26` | |
| 대구광역시 | `14` | `27` | |
| 인천광역시 | `15` | `28` | |
| 광주광역시 | `16` | `29` | |
| 대전광역시 | `17` | `30` | |
| 울산광역시 | `18` | `31` | |
| 세종특별자치시 | `19` | `36` | |
| 경기도 | `02` | `41` | |
| 강원특별자치도 | `03` | `42` (또는 `51`) | 2023-06-11 강원도→강원특별자치도 출범. `51`로 변경된 케이스도 존재. **데이터 소스별 확인 필요.** |
| 충청북도 | `04` | `43` | |
| 충청남도 | `05` | `44` | |
| 전북특별자치도 | `06` | `45` (또는 `52`) | 2024-01-18 전라북도→전북특별자치도 출범. `52`로 변경된 케이스도 존재. |
| 전라남도 | `07` | `46` | |
| 경상북도 | `08` | `47` | 2023-07-01 군위군이 경북→대구로 편입 |
| 경상남도 | `09` | `48` | |
| 제주특별자치도 | `11` | `50` | |

**관찰:**

1. **두 코드 체계 사이에 어떤 산술 규칙도 없음** — 단순 매핑 테이블만 가능.
2. **오피넷 시도코드는 `12`, `13` 결번** — 과거 행정구역 변경(이천/광명 광역시 안건 무산 등)의 흔적으로 추정.
3. **법정동코드는 광역시(11/26~31)와 도(36/41~50) 사이의 번호 체계가 분리**되어 있고, 오피넷은 **단순 일련번호** 방식.
4. **2023~2024년의 특별자치도 출범으로 강원/전북의 법정동 시도코드가 변경**될 수 있음. 운영 환경에서는 행정안전부 변경 공고를 추적하거나 정기적으로 매핑을 재검증해야 함.
5. **오피넷의 `AREA_CD`는 변하지 않은 것으로 추정** (특별자치도 변경 후에도 `03`, `06` 그대로 사용). 본 명세서 작성 시점에는 그대로지만, 라이브러리 구현 시 `get_area_codes()`로 최신값 확인 권장.

#### 라이브러리 구현 가이드 (`opinet/codes.py`)

```python
# 양방향 매핑은 frozen dict로 (변경 시 의도적인 갱신을 강제)
OPINET_TO_BJD = {
    "01": "11",   # 서울
    "02": "41",   # 경기
    "03": "42",   # 강원특별자치도 — 51로 갱신될 가능성 (2023-06-11 출범)
    "04": "43",   # 충북
    "05": "44",   # 충남
    "06": "45",   # 전북특별자치도 — 52로 갱신될 가능성 (2024-01-18 출범)
    "07": "46",   # 전남
    "08": "47",   # 경북
    "09": "48",   # 경남
    "10": "26",   # 부산
    "11": "50",   # 제주
    "14": "27",   # 대구
    "15": "28",   # 인천
    "16": "29",   # 광주
    "17": "30",   # 대전
    "18": "31",   # 울산
    "19": "36",   # 세종
}

BJD_TO_OPINET = {v: k for k, v in OPINET_TO_BJD.items()}

# 강원/전북 특별자치도 출범으로 인한 법정동 코드 변경 (양방향 호환)
BJD_LEGACY_TO_NEW = {
    "42": "51",  # 강원도 → 강원특별자치도 (정책상 변경됐을 수 있음)
    "45": "52",  # 전라북도 → 전북특별자치도
}
BJD_NEW_TO_LEGACY = {v: k for k, v in BJD_LEGACY_TO_NEW.items()}

def opinet_sido_to_bjd(opinet_code: str) -> str:
    """오피넷 시도 코드(2자리)를 법정동 시도 코드(2자리)로 변환."""
    if opinet_code not in OPINET_TO_BJD:
        raise OpinetInvalidParameterError(f"unknown opinet sido code: {opinet_code!r}")
    return OPINET_TO_BJD[opinet_code]

def bjd_sido_to_opinet(bjd_code: str) -> str:
    """법정동 시도 코드(2자리)를 오피넷 시도 코드로 변환.

    구 강원도(42)/구 전라북도(45) 코드도 자동으로 처리한다.
    """
    if bjd_code in BJD_NEW_TO_LEGACY:
        # 새 코드(51, 52)가 들어오면 구 코드(42, 45)로 normalize
        bjd_code = BJD_NEW_TO_LEGACY[bjd_code]
    if bjd_code not in BJD_TO_OPINET:
        raise OpinetInvalidParameterError(f"unknown bjd sido code: {bjd_code!r}")
    return BJD_TO_OPINET[bjd_code]
```

#### 단위 테스트 권장

```python
# 양방향 변환 일치
@pytest.mark.parametrize("opinet,bjd", [
    ("01", "11"), ("10", "26"), ("11", "50"), ("19", "36"),
])
def test_sido_roundtrip(opinet, bjd):
    assert opinet_sido_to_bjd(opinet) == bjd
    assert bjd_sido_to_opinet(bjd) == opinet

# 특별자치도 신규 코드 normalize
def test_special_self_governing():
    assert bjd_sido_to_opinet("51") == "03"  # 강원특별자치도 신코드 → 오피넷 강원
    assert bjd_sido_to_opinet("52") == "06"  # 전북특별자치도 신코드 → 오피넷 전북

# 결번 처리
def test_unknown_opinet_code():
    with pytest.raises(OpinetInvalidParameterError):
        opinet_sido_to_bjd("12")  # 결번
    with pytest.raises(OpinetInvalidParameterError):
        opinet_sido_to_bjd("99")
```

> ⚠️ 시군구 4자리 코드는 두 체계 간 매핑이 더 복잡하며, 오피넷이 자체 일련번호를 쓰므로 **자동 변환이 불가능**합니다. 시군구 변환이 필요하면 오피넷 응답에 함께 들어 있는 `VAN_ADR`/`NEW_ADR` (지번/도로명 주소)를 행정안전부 도로명주소 API로 역지오코딩하는 방법밖에 없습니다.

---

## 3. 엔드포인트 (5종)

공식 사이트 `openApiInfo.do`에 등재된 5개 API. 모든 엔드포인트는 GET, 공통 필수 파라미터는 `certkey`, `out`.

각 응답 필드 표의 **"Python 타입"** 컬럼은 라이브러리가 모델에 채워넣는 최종 타입입니다. 원본 API는 모두 문자열로 반환합니다.

### 3.1 [apiId=4] 전국 주유소 평균가격 — `avgAllPrice.do`

| 항목 | 값 |
|---|---|
| URL | `https://www.opinet.co.kr/api/avgAllPrice.do` |
| 필수 파라미터 | `certkey`, `out` |
| 선택 파라미터 | (없음) |

#### 요청 예시

```
https://www.opinet.co.kr/api/avgAllPrice.do?out=xml&certkey=[KEY]
```

#### 응답 필드 (`RESULT.OIL[]`)

| 필드 | API 원본 | Python 타입 | 모델 속성 | 설명 |
|---|---|---|---|---|
| `TRADE_DT` | str(8) `"YYYYMMDD"` | `datetime.date` | `trade_date` | 해당일자 |
| `PRODCD` | str | `ProductCode` (StrEnum) | `product_code` | 제품구분코드 |
| `PRODNM` | str | `str` | `product_name` | 제품명 |
| `PRICE` | str (소수 가능) | `float` | `price` | 평균가격 (원) |
| `DIFF` | str (`+`/`-` 부호 포함) | `float` | `diff` | 전일 대비 등락값 |

#### 응답 예시 (XML, 2025-07-23 기준)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<RESULT>
  <OIL>
    <TRADE_DT>20250723</TRADE_DT>
    <PRODCD>B034</PRODCD>
    <PRODNM>고급휘발유</PRODNM>
    <PRICE>1919.44</PRICE>
    <DIFF>-0.10</DIFF>
  </OIL>
  <OIL>
    <TRADE_DT>20250723</TRADE_DT>
    <PRODCD>B027</PRODCD>
    <PRODNM>휘발유</PRODNM>
    <PRICE>1667.33</PRICE>
    <DIFF>-0.23</DIFF>
  </OIL>
  <OIL>
    <TRADE_DT>20250723</TRADE_DT>
    <PRODCD>D047</PRODCD>
    <PRODNM>자동차용경유</PRODNM>
    <PRICE>1532.22</PRICE>
    <DIFF>+0.39</DIFF>
  </OIL>
  <OIL>
    <TRADE_DT>20250723</TRADE_DT>
    <PRODCD>C004</PRODCD>
    <PRODNM>실내등유</PRODNM>
    <PRICE>1295.23</PRICE>
    <DIFF>-0.72</DIFF>
  </OIL>
  <OIL>
    <TRADE_DT>20250723</TRADE_DT>
    <PRODCD>K015</PRODCD>
    <PRODNM>자동차용부탄</PRODNM>
    <PRICE>1052.64</PRICE>
    <DIFF>-0.07</DIFF>
  </OIL>
</RESULT>
```

#### 변환 후 Python 객체 (`AvgPrice`)

```python
AvgPrice(
    trade_date=date(2025, 7, 23),
    product_code=ProductCode.GASOLINE_PREMIUM,  # "B034"
    product_name="고급휘발유",
    price=1919.44,
    diff=-0.10,
)
```

---

### 3.2 [apiId=2] 전국/지역별 최저가 주유소 (Top 20) — `lowTop10.do`

| 항목 | 값 |
|---|---|
| URL | `https://www.opinet.co.kr/api/lowTop10.do` |
| 필수 파라미터 | `certkey`, `out`, `prodcd` |
| 선택 파라미터 | `area`, `cnt` |

> ⚠️ 엔드포인트 이름은 `lowTop10.do`이지만 **`cnt`로 최대 20까지** 받을 수 있습니다.
> 공식 문서 표기: "최저가순 결과 건수 (1 ~ 20 사이 숫자 입력, 미입력시 기본값 10건)"

#### 파라미터 상세

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `prodcd` | 필수 | `B027`/`B034`/`D047`/`C004`/`K015` |
| `area` | 선택 | 미입력시 전국, 시도코드 2자리 또는 시군코드 4자리 |
| `cnt` | 선택 | 1 ~ 20, 기본 10 |

#### 응답 필드 (`RESULT.OIL[]`)

| 필드 | API 원본 | Python 타입 | 모델 속성 | 설명 |
|---|---|---|---|---|
| `UNI_ID` | str | `str` | `uni_id` | 주유소코드 |
| `PRICE` | str | `float` | `price` | 판매가격 (원) |
| `POLL_DIV_CD`/`POLL_DIV_CO` | str | `BrandCode` (StrEnum) | `brand` | 상표코드 (실제 응답은 `POLL_DIV_CO`) |
| `OS_NM` | str | `str` | `name` | 상호 |
| `VAN_ADR` | str | `str \| None` | `address_jibun` | 지번주소 |
| `NEW_ADR` | str | `str \| None` | `address_road` | 도로명주소 |
| `GIS_X_COOR` | str (소수) | `float` | `katec_x` | KATEC X (m) |
| `GIS_Y_COOR` | str (소수) | `float` | `katec_y` | KATEC Y (m) |
| (계산 필드) | — | `float` | `lon` | WGS84 경도 (KATEC→WGS84 변환) |
| (계산 필드) | — | `float` | `lat` | WGS84 위도 (KATEC→WGS84 변환) |

#### 요청 예시

```
https://www.opinet.co.kr/api/lowTop10.do?out=xml&prodcd=B027&cnt=4&certkey=[KEY]
```

#### 응답 예시

```xml
<?xml version="1.0" encoding="UTF-8"?>
<RESULT>
  <OIL>
    <UNI_ID>A0013150</UNI_ID>
    <PRICE>1538</PRICE>
    <POLL_DIV_CO>SKE</POLL_DIV_CO>
    <OS_NM>충주주유소</OS_NM>
    <VAN_ADR>충북 충주시 봉방동 337-20</VAN_ADR>
    <NEW_ADR>충북 충주시 중원대로 3506 (봉방동)</NEW_ADR>
    <GIS_X_COOR>392585.72340</GIS_X_COOR>
    <GIS_Y_COOR>485368.42860</GIS_Y_COOR>
  </OIL>
  ...
</RESULT>
```

---

### 3.3 [apiId=3] 반경 내 주유소 — `aroundAll.do`

| 항목 | 값 |
|---|---|
| URL | `https://www.opinet.co.kr/api/aroundAll.do` |
| 필수 파라미터 | `certkey`, `out`, `x`, `y`, `radius`, `prodcd`, `sort` |

#### 파라미터 상세

| 파라미터 | 설명 |
|---|---|
| `x` | 기준 위치 X좌표 (**KATEC**) |
| `y` | 기준 위치 Y좌표 (**KATEC**) |
| `radius` | 반경 (최대 5,000, 단위: m) |
| `prodcd` | `B027`/`B034`/`D047`/`C004`/`K015` |
| `sort` | `1`=가격순, `2`=거리순 |

> ⚠️ `sort`도 **공식 명세상 필수**입니다. 입력 좌표는 KATEC 단위 — WGS84(위경도)는 반드시 변환 후 호출.

#### 응답 필드 (`RESULT.OIL[]`)

3.2의 모델과 동일하되 `DISTANCE` 필드가 추가됨:

| 필드 | API 원본 | Python 타입 | 모델 속성 | 설명 |
|---|---|---|---|---|
| `UNI_ID` | str | `str` | `uni_id` | 주유소코드 |
| `POLL_DIV_CD`/`POLL_DIV_CO` | str | `BrandCode` | `brand` | 상표 |
| `OS_NM` | str | `str` | `name` | 상호 |
| `PRICE` | str | `float` | `price` | 판매가격 (원) |
| `DISTANCE` | str (소수) | `float` | `distance_m` | 기준 위치로부터 거리 (m) |
| `GIS_X_COOR` | str (소수) | `float` | `katec_x` | KATEC X (m) |
| `GIS_Y_COOR` | str (소수) | `float` | `katec_y` | KATEC Y (m) |
| (계산 필드) | — | `float` | `lon` | WGS84 경도 |
| (계산 필드) | — | `float` | `lat` | WGS84 위도 |

#### 요청 예시

```
https://www.opinet.co.kr/api/aroundAll.do?out=xml&x=314681.8&y=544837&radius=5000&sort=1&prodcd=B027&certkey=[KEY]
```

#### 응답 예시

```xml
<?xml version="1.0" encoding="UTF-8"?>
<RESULT>
  <OIL>
    <UNI_ID>A0009907</UNI_ID>
    <POLL_DIV_CO>GSC</POLL_DIV_CO>
    <OS_NM>에너지플러스허브 삼방주유소</OS_NM>
    <PRICE>1725</PRICE>
    <DISTANCE>885.4</DISTANCE>
    <GIS_X_COOR>313828.81720</GIS_X_COOR>
    <GIS_Y_COOR>545078.98990</GIS_Y_COOR>
  </OIL>
  <OIL>
    <UNI_ID>A0010207</UNI_ID>
    <POLL_DIV_CO>SKE</POLL_DIV_CO>
    <OS_NM>SK서광주유소</OS_NM>
    <PRICE>1745</PRICE>
    <DISTANCE>846.6</DISTANCE>
    <GIS_X_COOR>314871.80000</GIS_X_COOR>
    <GIS_Y_COOR>544012.00000</GIS_Y_COOR>
  </OIL>
  ...
</RESULT>
```

---

### 3.4 [apiId=1] 주유소 상세정보 (ID) — `detailById.do`

| 항목 | 값 |
|---|---|
| URL | `https://www.opinet.co.kr/api/detailById.do` |
| 필수 파라미터 | `certkey`, `out`, `id` (주유소 UNI_ID) |

#### 응답 필드 (루트 — `RESULT.OIL`)

| 필드 | API 원본 | Python 타입 | 모델 속성 | 설명 |
|---|---|---|---|---|
| `UNI_ID` | str | `str` | `uni_id` | 주유소코드 |
| `POLL_DIV_CD`/`POLL_DIV_CO` | str | `BrandCode` | `brand` | 상표코드 |
| `GPOLL_DIV_CD`/`GPOLL_DIV_CO` | str (공백 가능) | `str \| None` | `sub_brand` | 부상표 (공백→None) |
| `OS_NM` | str | `str` | `name` | 상호 |
| `VAN_ADR` | str | `str \| None` | `address_jibun` | 지번주소 |
| `NEW_ADR` | str | `str \| None` | `address_road` | 도로명주소 |
| `TEL` | str | `str \| None` | `tel` | 전화번호 |
| `SIGUNCD` | str(4) | `str` | `sigun_code` | 시군구코드 (선행 0 보존) |
| `LPG_YN` | str (`N`/`Y`/`C`) | `StationType` (StrEnum) | `station_type` | **업종구분** (NOT LPG 취급여부) |
| `MAINT_YN` | str (Y/N) | `bool` | `has_maintenance` | 경정비 |
| `CAR_WASH_YN` | str (Y/N) | `bool` | `has_carwash` | 세차장 |
| `CVS_YN` | str (Y/N) | `bool` | `has_cvs` | 편의점 |
| `KPETRO_YN` | str (Y/N) | `bool` | `is_kpetro` | **품질인증주유소** (NOT 알뜰) |
| `GIS_X_COOR` | str (소수) | `float` | `katec_x` | KATEC X (m) |
| `GIS_Y_COOR` | str (소수) | `float` | `katec_y` | KATEC Y (m) |
| (계산 필드) | — | `float` | `lon` | WGS84 경도 |
| (계산 필드) | — | `float` | `lat` | WGS84 위도 |
| `OIL_PRICE` | array of dict | `tuple[OilPrice, ...]` | `prices` | 제품별 가격 배열 |

#### 응답 필드 (중첩 — `OIL_PRICE`)

| 필드 | API 원본 | Python 타입 | 모델 속성 | 설명 |
|---|---|---|---|---|
| `PRODCD` | str | `ProductCode` | `product_code` | 제품코드 |
| `PRICE` | str | `float \| None` | `price` | 가격 (해당 제품 미판매 시 None) |
| `TRADE_DT` | str(8) | `date` | `trade_date` | 기준일자 |
| `TRADE_TM` | str(6) | `time` | `trade_time` | 기준시간 (HH:MM:SS) |

#### 요청 예시

```
https://www.opinet.co.kr/api/detailById.do?out=xml&id=A0010207&certkey=[KEY]
```

#### 응답 예시 (SK서광주유소)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<RESULT>
  <OIL>
    <UNI_ID>A0010207</UNI_ID>
    <POLL_DIV_CO>SKE</POLL_DIV_CO>
    <GPOLL_DIV_CO> </GPOLL_DIV_CO>
    <OS_NM>SK서광주유소</OS_NM>
    <VAN_ADR>서울 강남구 역삼동 834-47</VAN_ADR>
    <NEW_ADR>서울 강남구 역삼로 142</NEW_ADR>
    <TEL>02-562-4855</TEL>
    <SIGUNCD>0113</SIGUNCD>
    <LPG_YN>N</LPG_YN>
    <MAINT_YN>Y</MAINT_YN>
    <CAR_WASH_YN>Y</CAR_WASH_YN>
    <CVS_YN>N</CVS_YN>
    <KPETRO_YN>N</KPETRO_YN>
    <GIS_X_COOR>314871.80000</GIS_X_COOR>
    <GIS_Y_COOR>544012.00000</GIS_Y_COOR>
    <OIL_PRICE>
      <PRODCD>B027</PRODCD>
      <PRICE>1745</PRICE>
      <TRADE_DT>20250723</TRADE_DT>
      <TRADE_TM>145618</TRADE_TM>
    </OIL_PRICE>
    <OIL_PRICE>
      <PRODCD>B034</PRODCD>
      <PRICE>1920</PRICE>
      <TRADE_DT>20250723</TRADE_DT>
      <TRADE_TM>145312</TRADE_TM>
    </OIL_PRICE>
    <OIL_PRICE>
      <PRODCD>D047</PRODCD>
      <PRICE>1629</PRICE>
      <TRADE_DT>20250723</TRADE_DT>
      <TRADE_TM>144009</TRADE_TM>
    </OIL_PRICE>
  </OIL>
</RESULT>
```

#### 변환 후 Python 객체

```python
StationDetail(
    uni_id="A0010207",
    name="SK서광주유소",
    brand=BrandCode.SKE,
    sub_brand=None,                        # 공백 1자 → None
    address_jibun="서울 강남구 역삼동 834-47",
    address_road="서울 강남구 역삼로 142",
    tel="02-562-4855",
    sigun_code="0113",                     # str 유지 (선행 0)
    station_type=StationType.GAS_STATION,  # "N" → enum
    has_maintenance=True,
    has_carwash=True,
    has_cvs=False,
    is_kpetro=False,                       # 알뜰 여부 아님!
    katec_x=314871.80,
    katec_y=544012.00,
    lon=127.0381,                          # 자동 변환
    lat=37.5006,                           # 자동 변환
    prices=(
        OilPrice(ProductCode.GASOLINE, 1745.0,
                 date(2025, 7, 23), time(14, 56, 18)),
        OilPrice(ProductCode.GASOLINE_PREMIUM, 1920.0,
                 date(2025, 7, 23), time(14, 53, 12)),
        OilPrice(ProductCode.DIESEL, 1629.0,
                 date(2025, 7, 23), time(14, 40, 9)),
    ),
)
```

---

### 3.5 [apiId=5] 지역코드 조회 — `areaCode.do`

| 항목 | 값 |
|---|---|
| URL | `https://www.opinet.co.kr/api/areaCode.do` |
| 필수 파라미터 | `certkey`, `out` |
| 선택 파라미터 | `area` (미입력시 시도, 시도코드 2자리 입력시 해당 시도의 시군구 목록) |

#### 응답 필드 (`RESULT.OIL[]`)

| 필드 | API 원본 | Python 타입 | 모델 속성 | 설명 |
|---|---|---|---|---|
| `AREA_CD` | str(2) 또는 str(4) | `str` | `code` | 지역코드 (선행 0 보존) |
| `AREA_NM` | str | `str` | `name` | 지역명 |

> 공식 문서 표기는 `AREA_CD: "주유소코드"`로 되어 있는데 이는 문서 오타이며, 실제로는 지역코드를 반환합니다.

#### 요청 예시

```
https://www.opinet.co.kr/api/areaCode.do?out=xml&certkey=[KEY]
```

#### 응답 예시

```xml
<?xml version="1.0" encoding="UTF-8"?>
<RESULT>
  <OIL><AREA_CD>01</AREA_CD><AREA_NM>서울</AREA_NM></OIL>
  <OIL><AREA_CD>02</AREA_CD><AREA_NM>경기</AREA_NM></OIL>
  <OIL><AREA_CD>03</AREA_CD><AREA_NM>강원</AREA_NM></OIL>
  <OIL><AREA_CD>04</AREA_CD><AREA_NM>충북</AREA_NM></OIL>
  <OIL><AREA_CD>05</AREA_CD><AREA_NM>충남</AREA_NM></OIL>
  <OIL><AREA_CD>06</AREA_CD><AREA_NM>전북</AREA_NM></OIL>
  <OIL><AREA_CD>07</AREA_CD><AREA_NM>전남</AREA_NM></OIL>
  <OIL><AREA_CD>08</AREA_CD><AREA_NM>경북</AREA_NM></OIL>
  <OIL><AREA_CD>09</AREA_CD><AREA_NM>경남</AREA_NM></OIL>
  <OIL><AREA_CD>10</AREA_CD><AREA_NM>부산</AREA_NM></OIL>
  <OIL><AREA_CD>11</AREA_CD><AREA_NM>제주</AREA_NM></OIL>
  <OIL><AREA_CD>14</AREA_CD><AREA_NM>대구</AREA_NM></OIL>
  <OIL><AREA_CD>15</AREA_CD><AREA_NM>인천</AREA_NM></OIL>
  <OIL><AREA_CD>16</AREA_CD><AREA_NM>광주</AREA_NM></OIL>
  <OIL><AREA_CD>17</AREA_CD><AREA_NM>대전</AREA_NM></OIL>
  <OIL><AREA_CD>18</AREA_CD><AREA_NM>울산</AREA_NM></OIL>
  <OIL><AREA_CD>19</AREA_CD><AREA_NM>세종</AREA_NM></OIL>
</RESULT>
```

---

## 4. 부가(experimental) 엔드포인트 — PDF 가이드북 22종

PDF 가이드북에는 무료 API 22종이 명시되어 있지만, 공식 사이트에는 5종만 노출됩니다. 다음은 PDF 항목과 통상 알려진 엔드포인트 매핑입니다 — **공식 검증되지 않았으므로 호출 시 동작하지 않을 수 있습니다.** 라이브러리에서는 `opinet.experimental` 서브모듈로 분리해 격리하고, 모든 메서드 docstring에 "검증되지 않음 (Unverified)" 경고를 명시합니다.

| 카테고리 | PDF 항목 | 추정 엔드포인트 |
|---|---|---|
| 통계 | 주유소 시도별 평균가격 (현재) | `avgSidoPrice.do` |
| 통계 | 주유소 시군구별 평균가격 (현재) | `avgSigunPrice.do` |
| 통계 | 최근 7일간 전국 일일 평균 | `avgRecentPrice.do` |
| 통계 | 최근 7일간 지역별 일일 평균 | `avgRecentSidoPrice.do` |
| 통계 | 최근 7일간 상표별 일일 평균 | `avgRecentBrandPrice.do` |
| 통계 | 특정 7일간 전국 일일 평균 | `avgPeriodPrice.do` |
| 통계 | 특정 7일간 지역별 일일 평균 | `avgPeriodSidoPrice.do` |
| 통계 | 특정 7일간 상표별 일일 평균 | `avgPeriodBrandPrice.do` |
| 통계 | 주간 평균 가격 | `avgWeekPrice.do` |
| 면세유 | 면세유 주유소 전국 평균 (현재) | `dutyAvgAllPrice.do` |
| 면세유 | 면세유 주유소 시도별 평균 (현재) | `dutyAvgSidoPrice.do` |
| 면세유 | 면세유 주유소 시군구별 평균 (현재) | `dutyAvgSigunPrice.do` |
| 면세유 | 최근 7일간 면세유 일일 평균 | `dutyAvgRecentPrice.do` |
| 면세유 | 최근 7일간 상표별 면세유 평균 | `dutyAvgRecentBrandPrice.do` |
| 면세유 | 전국/지역별 최저가 면세유 (Top 20) | `dutyLowTop10.do` |
| 주유소 | 상호로 주유소 검색 | `searchByName.do` |
| 기타 | 요소수 주유소 판매가격 (현재) | `ureaPrice.do` |

> ⚠️ 위 17개 엔드포인트는 **본 명세서 작성 시점에 공식 명세 페이지가 없습니다**. 실제 호출 시:
> - 인증 파라미터가 `certkey`인지 `code`인지 (PDF 가이드북은 별도 신청 절차 — `유가관련정보 > 유가정보 API > 무료API 이용 신청`)
> - 응답 필드 이름
> - 엔드포인트 경로 자체
>
> 이 모두 검증 필요. 라이브러리는 공식 5종 우선 구현 후, 실키로 검증된 엔드포인트만 단계적으로 추가하는 전략을 권장합니다.

---

## 5. 좌표계 변환 (KATEC ↔ WGS84)

### 5.1 KATEC proj 정의

```
+proj=tmerc +lat_0=38 +lon_0=128 +k=0.9999 +x_0=400000 +y_0=600000 +ellps=bessel +units=m +towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43 +no_defs
```

### 5.2 Python 구현 (`pykrtour`)

```python
from pykrtour import KatecPoint, PlaceCoordinate

x, y = PlaceCoordinate(lon=127.0276, lat=37.4979).to_katec().as_x_y()
coord = PlaceCoordinate.from_katec(KatecPoint(314871.80, 544012.00))
```

### 5.3 검증 기준점

**오피넷 공식 응답에서 추출된 실제 KATEC 좌표** (검증용):

| 위치 | UNI_ID | KATEC (x, y) |
|---|---|---|
| SK서광주유소 (서울 강남구 역삼로 142) | A0010207 | (314871.80, 544012.00) |
| 충주주유소 (충북 충주시 봉방동) | A0013150 | (392585.72, 485368.43) |
| 대성산업㈜ 충주주유소 (충북 충주시 금릉동) | A0013255 | (392804.00, 487722.00) |
| 오일드림주유소 (경북 구미시 원평동) | A0033771 | (430907.88, 392046.93) |

이 좌표를 WGS84로 역변환했을 때 실제 행정주소와 일치하는지 단위테스트에서 확인. ±10m 오차 허용.

---

## 6. 에러 처리

### 6.1 오피넷의 에러 표현

오피넷 공식 사이트는 에러 응답 명세를 공개하지 않습니다. 실측 패턴:

| 응답 | 의미 |
|---|---|
| `{"RESULT":{"OIL":[...]}}` | 정상 |
| `{"RESULT":{"OIL":[]}}` | 결과 없음 (정상) |
| `{"RESULT":"Invalid Key"}` 류 | 인증 실패 |
| 본문에 `Limit` / `초과` 류 | 호출 한도 초과 추정 |
| HTTP 5xx | 서버 점검/오류 |

라이브러리는 **`RESULT.OIL` 키 부재 또는 비-list 타입을 모두 에러로 분기**하고, 본문 일부를 예외 메시지에 포함시킵니다.

### 6.2 Python 예외 계층

```python
# opinet/exceptions.py

class OpinetError(Exception):
    """모든 오피넷 API 예외의 베이스."""

class OpinetAuthError(OpinetError):
    """인증키 오류 (Invalid Key, 401, 403, 본문에 'Invalid')."""

class OpinetRateLimitError(OpinetError):
    """일일 호출 한도 초과 (429 또는 본문에 'Limit'/'초과')."""

class OpinetInvalidParameterError(OpinetError):
    """파라미터 검증 실패. 호출 전에 발생."""

class OpinetNoDataError(OpinetError):
    """결과 비어있음 (옵션, strict_empty=True일 때만 raise)."""

class OpinetServerError(OpinetError):
    """5xx, 응답 파싱 실패, 또는 응답 데이터 타입 변환 실패."""

class OpinetNetworkError(OpinetError):
    """connection/timeout 등 네트워크 레벨."""
```

### 6.3 매핑 규칙

| 트리거 | 예외 |
|---|---|
| `requests.ConnectionError`, `Timeout` | `OpinetNetworkError` |
| HTTP 401 / 403 | `OpinetAuthError` |
| HTTP 429 또는 본문에 `Limit`/`초과` | `OpinetRateLimitError` |
| HTTP 5xx | `OpinetServerError` (재시도 후 최종 실패 시) |
| JSON 파싱 실패 | `OpinetServerError` |
| 응답 데이터 타입 변환 실패 (날짜 포맷 오류 등) | `OpinetServerError` |
| `RESULT`가 dict 아니거나 본문에 `Invalid` | `OpinetAuthError` |
| `RESULT.OIL`이 빈 배열 | 기본=빈 리스트, `strict_empty`이면 `OpinetNoDataError` |
| 미지원 prodcd, NaN 좌표, radius>5000, cnt>20 등 | `OpinetInvalidParameterError` (호출 전) |

### 6.4 재시도

- 5xx, 네트워크 에러: exponential backoff (0.5→1→2초, 최대 3회).
- 401/403/429: 즉시 실패 (재시도 무의미).

---

## 7. Python 라이브러리 설계

### 7.0 문서와 경로 표기

- 저장소 문서에서 파일 위치를 언급할 때는 프로젝트 루트 기준 상대 경로를 사용합니다. 예: `opinet/client.py`, `tests/fixtures/avg_all_price.json`.
- 로컬 절대 경로는 저장소 문서에 남기지 않습니다.
- Python 내부 문서(docstring과 유지보수용 주석)는 한글로 작성합니다.
- API 필드명, 엔드포인트, enum 값처럼 원문 자체가 의미 있는 값은 그대로 둡니다.
- Windows/PowerShell 환경에서 `rg`가 실행 권한 문제로 실패하면 반복 시도하지 말고 `git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`으로 우회합니다.
- 한글 문서/소스 파일은 `Get-Content -Encoding utf8` 또는 `Get-Content -Raw -Encoding utf8`로 확인합니다. PowerShell 기본 출력에서 한글이 깨져 보이면 UTF-8로 다시 읽습니다.

### 7.0.1 공통 라이브러리 직접 사용

- 좌표, 장소 DTO, POI 정규화처럼 다른 TripMate 라이브러리에 이미 구현된 기능은 `opinet` 안에 복제하지 않고 해당 라이브러리를 직접 의존합니다.
- KATEC/WGS84 경계는 `pykrtour.PlaceCoordinate`와 `pykrtour.KatecPoint`를 파라미터와 리턴 모델에 그대로 노출합니다. 단순 wrapper, compatibility alias, mirror dataclass는 만들지 않습니다.
- 이 원칙은 "최소 수정"보다 우선합니다. 직접 의존으로 공개 API가 바뀌면 README, 테스트, 타입 힌트를 함께 갱신해 새 계약을 명확히 합니다.
- `SIGUNCD`는 오피넷 자체 4자리 시군구 코드입니다. 법정동 5자리 시군구 코드나 10자리 법정동코드와 일치한다고 추정하지 않습니다.

### 7.1 패키지 구조

```
opinet/
├── opinet/
│   ├── __init__.py          # 공개 API 재노출
│   ├── client.py            # OpinetClient (5개 공식 API)
│   ├── _http.py             # HTTP 헬퍼 + 에러 매핑
│   ├── _convert.py          # 타입 변환 헬퍼 (to_date, to_time, to_float_or_none, ...)
│   ├── exceptions.py        # 예외 계층
│   ├── codes.py             # ProductCode, BrandCode, SortOrder, StationType (StrEnum)
│   │                        # + 시도코드 ↔ 법정동코드 매핑
│   ├── models.py            # frozen slots dataclasses (Python 네이티브 타입)
│   └── experimental/        # PDF 가이드북 17종 (검증되지 않음)
│       ├── __init__.py
│       └── client.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/            # 실제 응답 JSON
│   ├── test_client.py
│   ├── test_convert.py      # 타입 변환 헬퍼 단위테스트
│   ├── test_codes.py        # 시도코드 매핑 포함
│   ├── test_exceptions.py
│   ├── test_models.py
│   └── test_endpoints/
│       ├── test_avg_all_price.py
│       ├── test_low_top10.py
│       ├── test_around_all.py
│       ├── test_detail_by_id.py
│       └── test_area_code.py
├── pyproject.toml
├── README.md
└── LICENSE
```

### 7.2 Enum

```python
from enum import StrEnum

class ProductCode(StrEnum):
    GASOLINE = "B027"          # 휘발유
    GASOLINE_PREMIUM = "B034"  # 고급휘발유
    DIESEL = "D047"            # 자동차용경유
    KEROSENE = "C004"          # 실내등유
    LPG = "K015"               # 자동차용부탄

class BrandCode(StrEnum):
    SKE = "SKE"  # SK에너지
    GSC = "GSC"  # GS칼텍스
    HDO = "HDO"  # 현대오일뱅크
    SOL = "SOL"  # S-OIL
    RTE = "RTE"  # 자영알뜰
    RTX = "RTX"  # 고속도로알뜰
    NHO = "NHO"  # 농협알뜰
    ETC = "ETC"  # 자가상표
    E1G = "E1G"  # E1
    SKG = "SKG"  # SK가스

class SortOrder(StrEnum):
    PRICE = "1"
    DISTANCE = "2"

class StationType(StrEnum):
    """LPG_YN 필드의 의미 (이름과 달리 업종구분)."""
    GAS_STATION = "N"   # 주유소
    LPG_STATION = "Y"   # 자동차충전소
    BOTH = "C"          # 주유소/충전소 겸업

ALDDLE_BRANDS = frozenset({BrandCode.RTE, BrandCode.RTX, BrandCode.NHO})

def is_alddle(brand: str | BrandCode | None) -> bool:
    """알뜰주유소 여부. KPETRO_YN과는 무관."""
    if brand is None:
        return False
    try:
        return BrandCode(brand) in ALDDLE_BRANDS
    except ValueError:
        return False
```

### 7.3 데이터 모델 (모든 필드는 Python 네이티브 타입)

```python
from dataclasses import dataclass, field
from datetime import date, time

@dataclass(frozen=True, slots=True)
class AvgPrice:
    """전국 평균가격 (avgAllPrice.do 결과)."""
    trade_date: date              # YYYYMMDD → date
    product_code: ProductCode     # str → enum
    product_name: str
    price: float                  # str → float
    diff: float                   # "+0.39" → 0.39

@dataclass(frozen=True, slots=True)
class OilPrice:
    """주유소 상세의 제품별 가격 (detailById.do 의 OIL_PRICE)."""
    product_code: ProductCode
    price: float | None           # 미판매 시 None
    trade_date: date              # YYYYMMDD → date
    trade_time: time              # HHMMSS → time

@dataclass(frozen=True, slots=True)
class Station:
    """반경검색 / 최저가Top 공용 모델. 좌표는 항상 WGS84로 정규화."""
    uni_id: str
    name: str
    brand: BrandCode | None
    price: float | None
    address_jibun: str | None = None
    address_road: str | None = None
    katec_x: float = 0.0
    katec_y: float = 0.0
    lon: float = 0.0              # 자동 변환된 WGS84
    lat: float = 0.0              # 자동 변환된 WGS84
    distance_m: float | None = None  # aroundAll만

@dataclass(frozen=True, slots=True)
class StationDetail:
    """detailById.do 결과."""
    uni_id: str
    name: str
    brand: BrandCode | None
    sub_brand: BrandCode | None
    address_jibun: str | None
    address_road: str | None
    tel: str | None
    sigun_code: str | None        # "0113" — 선행 0 보존
    station_type: StationType     # LPG_YN: 주유소 / 충전소 / 겸업
    has_maintenance: bool         # MAINT_YN
    has_carwash: bool             # CAR_WASH_YN
    has_cvs: bool                 # CVS_YN
    is_kpetro: bool               # KPETRO_YN (품질인증주유소; 알뜰 아님!)
    katec_x: float
    katec_y: float
    lon: float
    lat: float
    prices: tuple[OilPrice, ...] = field(default_factory=tuple)

@dataclass(frozen=True, slots=True)
class AreaCode:
    code: str                     # str (선행 0 보존)
    name: str

    @property
    def is_sido(self) -> bool:
        return len(self.code) == 2

    @property
    def is_sigungu(self) -> bool:
        return len(self.code) == 4
```

### 7.4 클라이언트 메서드 시그니처 (공식 5개)

```python
class OpinetClient:
    def get_national_average_price(self) -> list[AvgPrice]:
        """avgAllPrice.do — 전국 주유소 평균가격(현재)."""

    def get_lowest_price_top20(
        self,
        prodcd: ProductCode,
        cnt: int = 10,
        area: str | None = None,
    ) -> list[Station]:
        """lowTop10.do — 전국/지역별 최저가 주유소 Top 20."""

    def search_stations_around(
        self,
        *,
        coordinate: PlaceCoordinate | None = None,
        katec: KatecPoint | None = None,
        radius_m: int = 5000,
        prodcd: ProductCode = ProductCode.GASOLINE,
        sort: SortOrder = SortOrder.PRICE,
    ) -> list[Station]:
        """aroundAll.do — 반경 내 주유소 검색."""

    def get_station_detail(self, uni_id: str) -> StationDetail:
        """detailById.do — 주유소 상세정보."""

    def get_area_codes(self, sido: str | None = None) -> list[AreaCode]:
        """areaCode.do — 시도/시군구 코드 조회."""
```

### 7.5 docstring 작성 원칙

각 public 메서드는 다음을 모두 포함합니다:

1. **요약** (1줄, 한글)
2. **`Args`**: 각 인자의 타입, 의미, 허용값/제약, 기본값.
3. **`Returns`**: 반환 모델, 빈 리스트 가능성, **모든 필드가 Python 네이티브 타입임을 명시**.
4. **`Raises`**: `OpinetAuthError`, `OpinetRateLimitError`, `OpinetInvalidParameterError`, `OpinetNetworkError`, `OpinetServerError` 중 발생 가능한 것 모두.
5. **`Example`**: doctest용 예제 (네트워크 의존이면 `# doctest: +SKIP`).
6. **API 출처**: 호출 엔드포인트 (`avgAllPrice.do` 등).
7. **단위 표기**: 가격은 원, 거리는 미터, 좌표 단위는 변수명에 포함.
8. 모듈, 클래스, private helper, 테스트 helper의 docstring도 한글로 작성.

#### 예시

```python
def search_stations_around(
    self,
    *,
    coordinate: PlaceCoordinate | None = None,
    katec: KatecPoint | None = None,
    radius_m: int = 5000,
    prodcd: ProductCode = ProductCode.GASOLINE,
    sort: SortOrder = SortOrder.PRICE,
) -> list[Station]:
    """주어진 좌표 반경 내 주유소를 검색한다.

    오피넷 ``aroundAll.do`` 엔드포인트(apiId=3)를 호출한다. 입력 좌표는
    ``pykrtour.PlaceCoordinate`` 또는 KATEC 둘 중 하나로만 받을 수 있고,
    응답의 KATEC 좌표는 자동으로 WGS84로 변환되어
    ``Station.coordinate``에 채워진다.

    응답 데이터의 모든 필드는 Python 네이티브 타입으로 변환되어 들어간다:
    ``price``/``distance_m``/``katec_*``/``lon``/``lat``은 ``float``,
    ``brand``는 ``BrandCode`` enum.

    Args:
        coordinate: ``pykrtour.PlaceCoordinate`` WGS84 좌표. 내부에서 KATEC으로
            변환되어 API에 전달된다.
        katec: ``pykrtour.KatecPoint`` KATEC 좌표(m). 변환 없이 그대로 전달.
        radius_m: 검색 반경(미터). 1 ≤ radius_m ≤ 5000.
        prodcd: 제품 종류. 기본 ``ProductCode.GASOLINE`` (B027 휘발유).
        sort: 정렬 기준. ``SortOrder.PRICE`` 또는 ``SortOrder.DISTANCE``.

    Returns:
        ``Station`` 리스트. 결과가 없으면 빈 리스트. 각 항목의
        ``distance_m`` 필드(``float``, m)가 채워져 있다.

    Raises:
        OpinetInvalidParameterError: 좌표 인자가 둘 다 None이거나 둘 다
            지정된 경우, 또는 ``radius_m``이 허용 범위를 벗어난 경우.
        OpinetAuthError: API 키 인증 실패.
        OpinetRateLimitError: 일일 호출 한도 초과.
        OpinetNetworkError: 네트워크 레벨 오류.
        OpinetServerError: 5xx, 응답 파싱 실패, 또는 응답 데이터의 타입
            변환 실패 (예: 좌표 문자열이 숫자가 아닌 경우).

    Example:
        >>> client = OpinetClient(api_key="...")  # doctest: +SKIP
        >>> stations = client.search_stations_around(  # doctest: +SKIP
        ...     coordinate=PlaceCoordinate(lon=127.0276, lat=37.4979),  # 강남역
        ...     radius_m=3000,
        ...     prodcd=ProductCode.DIESEL,
        ... )
        >>> stations[0].name  # doctest: +SKIP
        'SK서광주유소'
        >>> stations[0].distance_m  # 거리는 float (m)
        846.6
    """
```

---

## 8. 테스트 전략

### 8.1 계층

| 계층 | 도구 | 비고 |
|---|---|---|
| 단위 | pytest, `unittest.mock` | 네트워크 0건 |
| 통합 | `responses` 또는 `pytest-httpx` | fixture JSON 재생 |
| 계약(opt-in) | `@pytest.mark.live` | 실제 API. CI에서 skip |
| 좌표 | pytest, ±10m 허용 | 검증 기준점 |
| 타입 변환 | pytest, parametrize | `_convert.py` 헬퍼 |

### 8.2 fixture 디렉토리

본 명세서의 응답 예시를 그대로 fixture로 쓰면 됩니다:

```
tests/fixtures/
├── avg_all_price.json          # 3.1 응답 (XML→JSON 변환)
├── low_top10_B027.json         # 3.2 응답
├── around_all_gangnam.json     # 3.3 응답
├── detail_by_id_A0010207.json  # 3.4 응답
├── area_code_root.json         # 3.5 응답
├── area_code_sido_01.json      # 시군구 응답 (실제 호출 후 캡처)
├── error_invalid_key.json
├── error_rate_limit.json
└── empty_oil.json
```

### 8.3 필수 테스트 케이스

#### 클라이언트 초기화
- `api_key=None` + 환경변수 없음 → `OpinetAuthError` (첫 호출 시).
- 환경변수 `OPINET_API_KEY`로 동작.
- 명시 키 > 환경변수 우선순위.
- `timeout`, `max_retries` 세션에 정확히 전달.

#### HTTP 레이어
- 200 + 정상 JSON → 모델 반환.
- 200 + `{"RESULT":"Invalid Key"}` → `OpinetAuthError`.
- 200 + 빈 OIL → 빈 리스트 (또는 `strict_empty`이면 `OpinetNoDataError`).
- 401/403 → `OpinetAuthError`.
- 429 → `OpinetRateLimitError`, 재시도 없음.
- 500 → `OpinetServerError`, `max_retries`만큼 재시도.
- `ConnectionError`/`Timeout` → `OpinetNetworkError`.
- JSON 파싱 실패 → `OpinetServerError`.

#### 엔드포인트별 (각 최소 3개)
- 정상 → 모델 매핑 검증 — **각 필드의 Python 타입 명시적으로 assert** (`isinstance(row.trade_date, date)`, `isinstance(row.price, float)` 등).
- 빈 결과.
- 에러 응답.

#### 타입 변환 단위테스트 (`test_convert.py`)
- `to_date("20250723")` → `date(2025, 7, 23)`.
- `to_date("")` / `to_date(None)` / `to_date("  ")` → `None`.
- `to_date("2025-07-23")` → `ValueError` (포맷 오류).
- `to_date("20250732")` → `ValueError` (잘못된 날짜).
- `to_time("145618")` → `time(14, 56, 18)`.
- `to_time("000000")` → `time(0, 0, 0)`.
- `to_float_or_none("+0.39")` → `0.39`.
- `to_float_or_none("-1.23")` → `-1.23`.
- `to_float_or_none("")` / `to_float_or_none(None)` → `None`.
- `to_float_or_none("abc")` → `ValueError`.
- `to_bool_yn("Y")` → `True`. `to_bool_yn("N")` → `False`. `to_bool_yn("")` → `False`. `to_bool_yn(None)` → `False`.
- `strip_or_none(" ")` → `None`. `strip_or_none(" hello ")` → `"hello"`.

#### 시도코드 매핑 단위테스트
- `opinet_sido_to_bjd("01")` → `"11"`, ..., `opinet_sido_to_bjd("11")` → `"50"`.
- `bjd_sido_to_opinet("50")` → `"11"`.
- `bjd_sido_to_opinet("51")` → `"03"` (강원특별자치도 신코드 → 오피넷 강원).
- `bjd_sido_to_opinet("52")` → `"06"` (전북특별자치도 신코드 → 오피넷 전북).
- `opinet_sido_to_bjd("12")` → `OpinetInvalidParameterError` (결번).
- `opinet_sido_to_bjd("99")` → `OpinetInvalidParameterError`.
- 모든 17개 시도 양방향 roundtrip.

#### `search_stations_around` 추가
- `coordinate`만 줬을 때 KATEC 변환되어 query에 들어가는지.
- `katec`만 줬을 때 변환 없이 그대로.
- 응답 KATEC → WGS84 변환이 모델에 반영.
- 둘 다 None / 둘 다 줌 → `OpinetInvalidParameterError`.
- `radius_m=0`, `5001` → `OpinetInvalidParameterError`.

#### `get_lowest_price_top20` 추가
- `cnt=21` → `OpinetInvalidParameterError`.
- `cnt=0` → `OpinetInvalidParameterError`.
- `area`가 시도(2자리)/시군구(4자리)/None 모두 동작.

#### `get_station_detail` 추가
- `LPG_YN` 값이 `StationType` enum으로 변환됨 (`N`→`GAS_STATION`).
- `KPETRO_YN`이 `is_kpetro` (boolean)로 매핑됨 — `is_alddle`과 헷갈리지 않는지.
- `OIL_PRICE`가 단일 dict로 와도 list로 wrap 됨.
- `OIL_PRICE`의 `TRADE_DT` → `date`, `TRADE_TM` → `time` 변환.
- `GPOLL_DIV_CO`가 공백 1자일 때 `sub_brand=None`.
- `SIGUNCD="0113"` → 모델에 `"0113"` 그대로 (str, 선행 0 보존).

#### `get_area_codes` 추가
- 시도 응답 (위 표 17개 항목)이 모두 들어옴.
- 반환된 `code`가 `str`이고 선행 0이 보존됨 (`"01"`, `"04"` 등).
- `sido="01"`로 호출 시 query에 정확히 전달.
- 시도코드 길이가 2가 아니면 → `OpinetInvalidParameterError`.

#### 좌표 변환
- 강남역 (127.0276, 37.4979) ↔ KATEC 왕복 ±1e-5° 오차.
- 서울시청 (126.9784, 37.5666) 왕복.
- **실측점:** SK서광주유소 KATEC (314871.80, 544012.00) → WGS84로 역변환 시 강남구 역삼동 부근 (lon ≈ 127.04, lat ≈ 37.50).
- **실측점:** 충주주유소 KATEC (392585.72, 485368.43) → 충주시 봉방동 부근.
- **실측점:** 오일드림주유소 KATEC (430907.88, 392046.93) → 구미시 원평동 부근.
- NaN/inf → `ValueError`.

### 8.4 테스트 코드 예시

```python
# tests/test_convert.py
import pytest
from datetime import date, time
from opinet._convert import to_date, to_time, to_float_or_none, to_bool_yn, strip_or_none


@pytest.mark.parametrize("s,expected", [
    ("20250723", date(2025, 7, 23)),
    ("19000101", date(1900, 1, 1)),
])
def test_to_date_valid(s, expected):
    result = to_date(s)
    assert result == expected
    assert isinstance(result, date)


@pytest.mark.parametrize("s", [None, "", "   "])
def test_to_date_empty(s):
    assert to_date(s) is None


@pytest.mark.parametrize("s", [
    "2025-07-23",  # 하이픈 포함
    "20250732",    # 잘못된 일자
    "2025723",     # 7자리
    "abc",
])
def test_to_date_invalid(s):
    with pytest.raises(ValueError):
        to_date(s)


@pytest.mark.parametrize("s,expected", [
    ("145618", time(14, 56, 18)),
    ("000000", time(0, 0, 0)),
    ("235959", time(23, 59, 59)),
])
def test_to_time_valid(s, expected):
    result = to_time(s)
    assert result == expected
    assert isinstance(result, time)


@pytest.mark.parametrize("s,expected", [
    ("1745", 1745.0),
    ("1919.44", 1919.44),
    ("+0.39", 0.39),
    ("-0.10", -0.10),
    (1745, 1745.0),       # int 입력
    (1919.44, 1919.44),
])
def test_to_float_valid(s, expected):
    result = to_float_or_none(s)
    assert result == pytest.approx(expected)
    assert isinstance(result, float)


@pytest.mark.parametrize("s", [None, "", "   "])
def test_to_float_empty(s):
    assert to_float_or_none(s) is None


@pytest.mark.parametrize("s,expected", [
    ("Y", True), ("y", True),
    ("N", False), ("n", False),
    ("", False), (None, False), ("X", False),
])
def test_to_bool_yn(s, expected):
    assert to_bool_yn(s) is expected
```

```python
# tests/test_endpoints/test_around_all.py
import responses
import pytest
from datetime import date
from opinet import OpinetClient, ProductCode, SortOrder
from opinet.codes import BrandCode
from opinet.exceptions import OpinetInvalidParameterError


@responses.activate
def test_around_all_types(client, load_fixture):
    """응답 모델의 모든 필드가 Python 네이티브 타입으로 채워져야 한다."""
    payload = load_fixture("around_all_gangnam.json")
    responses.add(
        responses.GET,
        "https://www.opinet.co.kr/api/aroundAll.do",
        json=payload,
        status=200,
    )

    stations = client.search_stations_around(
        coordinate=PlaceCoordinate(lon=127.0276, lat=37.4979),
        radius_m=3000,
        prodcd=ProductCode.GASOLINE,
        sort=SortOrder.PRICE,
    )

    s = stations[0]
    assert isinstance(s.uni_id, str)
    assert isinstance(s.name, str)
    assert isinstance(s.brand, BrandCode)
    assert isinstance(s.price, float)
    assert isinstance(s.distance_m, float)
    assert isinstance(s.katec_x, float)
    assert isinstance(s.katec_y, float)
    assert isinstance(s.lon, float)
    assert isinstance(s.lat, float)


@pytest.mark.parametrize("kwargs", [
    dict(),
    dict(coordinate=PlaceCoordinate(lon=127.0, lat=37.5), katec=KatecPoint(300000, 540000)),
    dict(coordinate=PlaceCoordinate(lon=127.0, lat=37.5), radius_m=0),
    dict(coordinate=PlaceCoordinate(lon=127.0, lat=37.5), radius_m=6000),
])
def test_around_all_invalid(client, kwargs):
    with pytest.raises(OpinetInvalidParameterError):
        client.search_stations_around(**kwargs)
```

```python
# tests/test_endpoints/test_detail_by_id.py
import responses
from datetime import date, time
from opinet import OpinetClient
from opinet.codes import BrandCode, ProductCode, StationType


@responses.activate
def test_detail_full_type_mapping(client, load_fixture):
    payload = load_fixture("detail_by_id_A0010207.json")
    responses.add(
        responses.GET,
        "https://www.opinet.co.kr/api/detailById.do",
        json=payload,
    )
    detail = client.get_station_detail("A0010207")

    # enum 변환
    assert detail.brand is BrandCode.SKE
    assert detail.station_type is StationType.GAS_STATION  # LPG_YN=N
    # boolean 변환
    assert detail.has_maintenance is True   # MAINT_YN=Y
    assert detail.has_carwash is True       # CAR_WASH_YN=Y
    assert detail.has_cvs is False          # CVS_YN=N
    assert detail.is_kpetro is False        # KPETRO_YN=N (알뜰과 무관!)
    # 공백 → None
    assert detail.sub_brand is None         # GPOLL_DIV_CO=" "
    # str 보존
    assert detail.sigun_code == "0113"      # 선행 0
    # float 변환
    assert isinstance(detail.katec_x, float)
    assert isinstance(detail.lon, float)

    # 중첩 OIL_PRICE의 타입
    p = detail.prices[0]
    assert p.product_code is ProductCode.GASOLINE
    assert isinstance(p.price, float)
    assert isinstance(p.trade_date, date)
    assert p.trade_date == date(2025, 7, 23)
    assert isinstance(p.trade_time, time)
    assert p.trade_time == time(14, 56, 18)
```

```python
# tests/test_codes.py
import pytest
from opinet.codes import (
    opinet_sido_to_bjd, bjd_sido_to_opinet, OPINET_TO_BJD,
)
from opinet.exceptions import OpinetInvalidParameterError


@pytest.mark.parametrize("opinet,bjd", [
    ("01", "11"),  # 서울
    ("02", "41"),  # 경기
    ("10", "26"),  # 부산
    ("11", "50"),  # 제주
    ("19", "36"),  # 세종
])
def test_sido_roundtrip(opinet, bjd):
    assert opinet_sido_to_bjd(opinet) == bjd
    assert bjd_sido_to_opinet(bjd) == opinet


def test_special_self_governing_new_codes():
    # 강원특별자치도 신코드 51, 전북특별자치도 신코드 52
    assert bjd_sido_to_opinet("51") == "03"
    assert bjd_sido_to_opinet("52") == "06"


@pytest.mark.parametrize("code", ["12", "13", "20", "99", "1", "001"])
def test_unknown_opinet_code(code):
    with pytest.raises(OpinetInvalidParameterError):
        opinet_sido_to_bjd(code)


def test_all_17_sidos_mapped():
    """오피넷 시도코드 17개가 모두 법정동 시도코드로 매핑된다."""
    assert len(OPINET_TO_BJD) == 17
    # 광역시·도 + 특별자치시(세종)
    bjd_codes = set(OPINET_TO_BJD.values())
    assert {"11", "26", "27", "28", "29", "30", "31", "36",
            "41", "42", "43", "44", "45", "46", "47", "48", "50"} == bjd_codes
```

```python
# pykrtour/tests/test_coordinates.py
import pytest
from pykrtour import KatecPoint, PlaceCoordinate


@pytest.mark.parametrize("lon,lat", [
    (127.0276, 37.4979),  # 강남역
    (126.9784, 37.5666),  # 서울시청
    (129.0756, 35.1796),  # 부산시청
])
def test_roundtrip(lon, lat):
    katec = PlaceCoordinate(lon=lon, lat=lat).to_katec()
    coord = PlaceCoordinate.from_katec(katec)
    assert abs(coord.lon - lon) < 1e-5
    assert abs(coord.lat - lat) < 1e-5


@pytest.mark.parametrize("katec,lon_range,lat_range", [
    ((314871.80, 544012.00), (127.02, 127.06), (37.49, 37.51)),  # SK서광
    ((392585.72, 485368.43), (127.91, 127.94), (36.97, 37.00)),  # 충주
    ((430907.88, 392046.93), (128.32, 128.36), (36.10, 36.14)),  # 구미 오일드림
])
def test_real_station_coords(katec, lon_range, lat_range):
    coord = PlaceCoordinate.from_katec(KatecPoint(*katec))
    assert lon_range[0] < coord.lon < lon_range[1]
    assert lat_range[0] < coord.lat < lat_range[1]


def test_invalid_input():
    with pytest.raises(ValueError):
        PlaceCoordinate(lon=float("nan"), lat=37.5).to_katec()
    with pytest.raises(ValueError):
        PlaceCoordinate.from_katec(KatecPoint(float("inf"), 540000))
```

### 8.5 커버리지

- 핵심 모듈 (`client`, `coords`, `_http`, `_convert`, `exceptions`): **95% 이상**.
- 모델/enum/codes (시도매핑 포함): **100%**.
- CI: `pytest --cov=opinet --cov-fail-under=90`.

---

## 9. 알려진 한계 / 유의사항

### 9.1 공식 사이트 문서의 일관성 문제
- **`POLL_DIV_CD` vs `POLL_DIV_CO`**: 표는 CD, 응답 예시는 CO. 라이브러리는 양쪽 모두 받아들임.
- **`K015` vs `K105`**: apiId=2 페이지 본문에 `K105:자동차부탄`으로 오타. 실제 코드는 `K015`.
- **시도코드 결번**: 12, 13이 비어있음. 과거 행정구역 변경 결과로 추정.

### 9.2 PDF 22종과 공식 5종의 괴리
- PDF 가이드북은 `유가관련정보 > 유가정보 API > 무료API 이용 신청` 메뉴 (즉 `custApiInfo.do`)를 가리키는 것으로 보이며, `code` 인증 파라미터를 사용하는 것 같음.
- 공식 사이트 `오픈 API` 메뉴는 `openApiInfo.do` 게이트웨이로, `certkey` 인증 파라미터를 사용.
- 두 게이트웨이의 키가 같은지 다른지, 정확한 매핑 관계는 본 명세서 작성 시점에 미확인. **실제 키 발급 후 양쪽으로 호출해 보고 확인 필요.**

### 9.3 응답 포맷 (XML vs JSON)
- `out=xml` vs `out=json` 응답에서 단일 항목일 때 array 대 객체 차이가 있을 수 있음. 라이브러리는 dict가 오면 자동으로 `[dict]`로 wrap.

### 9.4 숫자 필드의 문자열 반환
- `PRICE`, `DIFF`, `DISTANCE`, `GIS_*_COOR` 등이 JSON에서도 문자열로 올 수 있음. 모델 변환 시 `float()` 캐스트 필수.

### 9.5 좌표계
- KATEC은 EPSG에 공식 등록되지 않음. `+towgs84` 파라미터의 한국 좌표계 변환은 다양한 방언이 있음. 본 문서의 값은 오피넷 공식 좌표와 ±10 m 이내로 매칭됨을 검증함.

### 9.6 시도코드와 법정동코드의 분리
- 오피넷 `AREA_CD`는 행정안전부 표준 법정동코드와 **완전히 다른 별도 체계**. 시군구 코드도 마찬가지.
- 오피넷에서 받은 주유소 데이터를 다른 정부 데이터(부동산, 인구통계, 주민등록 등)와 join하려면 §2.7의 시도 매핑 + 주소 기반 시군구 매칭(역지오코딩)이 필요.

### 9.7 특별자치도 출범으로 인한 코드 변경 가능성
- 강원도(2023-06-11) → 강원특별자치도, 전라북도(2024-01-18) → 전북특별자치도 출범으로 법정동코드가 변경됐을 수 있음.
- 오피넷 `AREA_CD`는 본 명세서 작성 시점까지는 변경 흔적 없음 (`03=강원`, `06=전북` 그대로).
- 라이브러리는 `BJD_LEGACY_TO_NEW`로 양방향 매핑하되, 운영 환경에서는 행정안전부 변경 공지를 정기 추적해 매핑을 갱신할 것을 권장.

---

## 10. 라이선스 / 약관

- 데이터 출처: 한국석유공사 오피넷.
- 데이터 사용 시 오피넷 이용 약관 준수.
- 본 라이브러리는 비공식이며 한국석유공사와 무관.
- 데이터 관련 문의: (052) 216-2514, price@knoc.co.kr

## 변경 이력

| 일자 | 변경 |
|---|---|
| 2026-05-09 (rev4) | Windows/PowerShell 환경에서 `rg` 실패 시 우회 명령을 사용하고, 한글 파일은 UTF-8 인코딩을 명시해 읽는 규칙 추가. |
| 2026-05-09 (rev3) | 문서의 파일 위치는 프로젝트 기준 상대 경로로 쓰고, Python 내부 문서는 한글로 작성한다는 규칙 추가. |
| 2026-04-30 (rev2) | Python 타입 변환 정책 명시. 시도코드 ↔ 법정동코드 매핑 추가. 응답 필드 표에 Python 타입 컬럼 추가. |
| 2026-04-30 (rev1) | 초기 작성. 공식 사이트 기준 5개 API 검증. 시도코드/필드 의미 정정. |
