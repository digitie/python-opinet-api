# AGENTS.md

## 목표

python-opinet-api는 한국석유공사 오피넷(Opinet) 오픈 API의 비공식 Python 클라이언트 라이브러리다. 공식 오픈 API 페이지에 등재된 5개 엔드포인트는 `OpinetClient`/`AsyncOpinetClient`로, PDF 가이드북의 미검증 17개 엔드포인트는 `opinet.experimental.OpinetExperimentalClient`로 분리해 제공한다. 좌표(KATEC ↔ WGS84) 변환과 응답 데이터의 Python 네이티브 타입 변환을 함께 처리하는 것이 이 패키지의 핵심 책임이다.

## Think Before Coding

- 구현 전 `opinet-api.md`의 관련 엔드포인트 스펙과 `SKILL.md`의 불변 조건을 먼저 확인한다.
- 필드가 실제로 어떻게 오는지(list vs 단일 dict, `POLL_DIV_CO` vs `POLL_DIV_CD` 우선순위)는 문서 표기만 믿지 않고 fixture로 확인한다.
- 새 엔드포인트나 코드 매핑을 추가하기 전 `src/opinet/codes.py`, `src/opinet/models.py`의 기존 패턴부터 살펴본다.

## Simplicity First

- 얇은 wrapper, mirror dataclass, 단순 위임 함수를 만들지 않는다.
- 좌표 변환은 `src/opinet/coords.py`에서 `pyproj`를 직접 사용하고 별도 좌표 DTO/adapter를 씌우지 않는다.
- 공식 5개 엔드포인트와 실험 17개 엔드포인트는 동일한 파싱/fixture/테스트 패턴을 재사용한다.

## Surgical Changes

- 변경은 가능한 한 작은 완성 단위로 만들고 공개 API 이름과 타입 안정성을 우선한다.
- HTTP 상태/본문 기반 오류 매핑은 `src/opinet/_http.py` 한 곳에만 모은다.
- 응답 파싱 로직은 raw 문자열을 사용자 모델에 그대로 흘리지 않는다.

## Goal-Driven Execution

- 새 public 메서드나 모델을 추가하면 README, `opinet-api.md`, `docs/implementation-status.md` 중 관련 문서를 함께 갱신한다.
- 원격 API 동작이 불확실하면 `opinet.experimental`에 두고 "Unverified" 경고를 남긴다.
- 사용자 가시적 변경이 있으면 `CHANGELOG.md`를 갱신한다.

## Practical Bias

- 실제 API 호출이 필요한 테스트는 `@pytest.mark.live` 뒤에 두고, 기본 테스트는 네트워크 없이 동작하게 한다.
- fixture의 숫자/날짜/시간 필드는 실제 API처럼 문자열로 유지해서 변환 경로를 테스트한다.
- 불확실한 가정보다 실제 응답(fixture, live 호출 기록)에 근거해 판단한다.

## 문서 언어 정책

이 저장소의 모든 Markdown/RST 문서는 한글로 작성합니다. 공식 API 필드명, 코드 식별자, 명령어, URL, provider 원문처럼 그대로 보존해야 하는 값만 영어를 유지합니다. 새 문서나 기존 문서를 수정할 때도 이 규칙을 우선합니다.

## 식별자 표

| 항목 | 값 |
|------|----|
| GitHub 저장소 이름 | `python-opinet-api` |
| 패키지/모듈 이름 | `opinet` |
| import 경로 | `from opinet import OpinetClient` |
| 런타임 의존성 | `httpx`, `pydantic`, `pyproj` |
| 테스트/개발 의존성 | `pytest`, `respx`, `pytest-cov`, `mypy` |

## 절대 하지 말 것 (DO NOT)

- 단순 전달용 wrapper, 장기 호환 alias, 임시 facade를 만들지 않는다. 다른 라이브러리에 검증된 구현이 있으면 라이선스/출처를 확인한 뒤 현재 구조에 직접 반영한다.
- 인증키, 실제 API 키, 원본 비밀값을 코드, fixture, 로그, 문서에 남기지 않는다.
- `AREA_CD`, `SIGUNCD`, `UNI_ID`, 제품/상표 코드를 `int`로 변환하지 않는다 (선행 0이 의미 있는 값).
- `SIGUNCD`(오피넷 시군구 코드)를 법정동 코드로 산술 변환하지 않는다 — 필요하면 `vworld.VworldClient.search_district(..., category="L2")` 결과를 명시 매칭한다.
- `.env.example` 외의 `.env*` 파일을 커밋하지 않는다.

## 검증

```bash
# 구조 및 문법 확인
python -m compileall src/opinet tests

# 타입 검사 (품질 게이트)
python -m mypy src/opinet

# 단위 테스트 및 커버리지 측정
pytest --cov=opinet --cov-fail-under=90

# 실제 API 스모크 테스트 (필요시)
pytest -m live --run-live
```

- HTTP mocking 테스트는 `respx`로 `httpx` 호출을 재생합니다.
- 좌표 변환 자체와 요청/응답 모델 경계는 이 저장소 테스트에서 검증합니다.
- 타입 변환 테스트는 정상값, 빈 문자열/공백/None, 잘못된 포맷을 모두 포함해야 합니다.
- 이 저장소는 ruff 설정이 없습니다. lint 게이트를 추가하는 작업은 별도 PR로 다룹니다.

## 지시 우선순위

사용자 요청 > `AGENTS.md` > README/tests

## 핵심 불변 조건

- Base URL은 `https://www.opinet.co.kr/api/`이다.
- 인증 파라미터는 `certkey`이다. 비공식 예제의 `code`를 기본값으로 쓰지 않는다.
- 모든 라이브러리 호출은 `out=json`을 기본으로 한다. XML은 디버깅 또는 문서 참조용이다.
- 공식 구현 대상은 `avgAllPrice.do`, `lowTop10.do`, `aroundAll.do`, `detailById.do`, `areaCode.do` 5개다.
- API 응답의 숫자, 날짜, 시간, 플래그는 문자열로 오더라도 모델 경계에서 Python 네이티브 타입으로 변환한다.
- 선행 0이 의미 있는 값(`AREA_CD`, `SIGUNCD`, `UNI_ID`, 제품/상표 코드)은 `int`로 변환하지 않는다.
- KATEC 좌표는 API 내부 좌표계이고, 공개 사용성은 WGS84 `lon`/`lat`와 KATEC `katec_x`/`katec_y` 원시 좌표 쌍을 함께 제공한다.
- `LPG_YN`은 LPG 판매 여부가 아니라 업종 구분이며 `StationType`으로 매핑한다.
- `KPETRO_YN`은 알뜰주유소 여부가 아니라 품질인증 여부이며 `is_kpetro`로 매핑한다.
- 알뜰주유소 여부는 상표 코드 `RTO`, `RTE`, `RTX`, `NHO`로 판정한다.
- 라이선스는 루트 `LICENSE`를 따른다.
- 구조적 결정의 근거는 `docs/decisions.md`에서 확인한다.

## 문서 라우팅

- 사용자용 개요와 예시: `README.md`
- 구현 상태/유지보수 체크리스트: `docs/implementation-status.md`
- API 필드, 코드표, 응답 예시, 테스트 전략: `opinet-api.md`
- 구조적 의사결정 기록: `docs/decisions.md`
- 에이전트 구현 규칙과 함정 목록: `SKILL.md`
- 패키지/의존성/테스트 설정: `pyproject.toml`
- 공식 클라이언트 진입점: `src/opinet/client.py`
- HTTP/에러 매핑: `src/opinet/_http.py`
- 타입 변환: `src/opinet/_convert.py`
- 코드표/enum/시도 매핑: `src/opinet/codes.py`
- 좌표 변환 helper: `src/opinet/coords.py`
- 응답 모델: `src/opinet/models.py`
- 미검증 API: `src/opinet/experimental/`
- 테스트 fixture: `tests/fixtures/`

## 문서 작성 규칙

- 문서에서 파일 위치를 언급할 때는 프로젝트 루트 기준 상대 경로만 쓴다. 예: `src/opinet/client.py`, `docs/implementation-status.md`.
- 로컬 절대 경로는 실행 로그나 임시 설명에만 쓰고 저장소 문서에는 남기지 않는다.
- Python 내부 문서(모듈, 클래스, 함수, 메서드 docstring과 유지보수용 주석)는 한글로 작성한다.
- API 필드명, 엔드포인트, enum 값, 외부 오류 메시지처럼 원문 자체가 의미 있는 값은 그대로 둔다.

## 로컬 도구/인코딩 규칙

- 이 환경에서 `rg` 실행이 `Access is denied`로 실패할 수 있다. 같은 실패를 반복하지 말고 `git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`으로 우회한다.
- 한글 문서나 소스 파일을 PowerShell에서 읽을 때는 기본 출력 인코딩을 믿지 말고 `Get-Content -Encoding utf8` 또는 `Get-Content -Raw -Encoding utf8`을 사용한다.
- 깨진 한글 출력이 보이면 파일 내용이 깨졌다고 판단하지 말고 먼저 UTF-8 인코딩을 명시해서 다시 확인한다.

## 작업 원칙

- 변경은 가능한 한 작은 완성 단위로 만들고, 공개 API 이름과 타입 안정성을 우선한다.
- 주유소 좌표/지역 매핑 관련 타입과 변환 로직은 이 저장소 안에서 직접 소유한다.
- 불필요한 compatibility wrapper, mirror dataclass, 단순 위임 함수는 만들지 않는다. 기존 공개 API를 깨야 하더라도 문서와 테스트를 함께 고쳐 공통 구현을 직접 쓰는 방향으로 정리한다.
- 응답 파싱 로직은 raw 문자열을 사용자 모델에 그대로 흘리지 않는다.
- HTTP 상태와 body 기반 오류 매핑은 `_http.py` 한 곳에 모은다.
- 엔드포인트별 파라미터 검증은 HTTP 호출 전에 수행하고 `OpinetInvalidParameterError`를 사용한다.
- 실제 API 호출이 필요한 테스트는 `@pytest.mark.live` 뒤에 두고 기본 테스트는 네트워크 없이 동작하게 한다.
- fixture의 숫자/date/time 필드는 실제 API처럼 문자열로 유지해서 변환 경로를 테스트한다.
- 새 public 메서드나 모델을 추가하면 README 또는 docstring도 함께 갱신한다.
- 원격 API 동작이 불확실하면 실험 모듈에 두고 "Unverified" 경고를 남긴다.

## 반복 실수 방지

- `StationDetail`의 전화번호 필드는 `tel`이다. `phone`을 새로 만들지 않는다.
- `OilPrice`에는 `product_name`이 없다. `OIL_PRICE` 응답에는 `PRODNM`이 오지 않는다.
- fixture 값은 실제 API처럼 문자열로 둔다. 특히 `PRICE`, `DIFF`, `DISTANCE`, `GIS_*`, `TRADE_DT`, `TRADE_TM`을 JSON number로 바꾸지 않는다.
- `RESULT.OIL`과 `OIL_PRICE`는 단일 dict일 수 있다. list로 단정하지 말고 정규화한다.
- `POLL_DIV_CO`/`GPOLL_DIV_CO`가 실제 응답 우선 필드다. 문서 표기의 `*_CD`는 fallback으로만 사용한다.
- 공백 1자(`" "`)는 값이 아니다. `strip_or_none()`으로 `None` 처리한다.
- `SIGUNCD`는 오피넷 4자리 시군구 코드이며 법정동 5자리 시군구 코드나 10자리 법정동코드와 일치한다고 가정하지 않는다.
- HTTP transport는 `httpx` 기반이며 sync/async transport 타입을 함께 유지한다.

## 작업 후 체크리스트

- [ ] `python -m compileall src/opinet tests` 통과
- [ ] `python -m mypy src/opinet` 타입 검사 통과
- [ ] `pytest --cov=opinet --cov-fail-under=90` 단위 테스트 및 커버리지 충족
- [ ] 변경된 소스 및 추가 설정 파일 확인
- [ ] `docs/implementation-status.md` 또는 관련 명세 문서의 변경 상태 반영
- [ ] 새로운 구조적 결정이 있었다면 `docs/decisions.md`에 항목 추가
- [ ] 작업 후 `CHANGELOG.md` 갱신 (사용자 가시 변경이 있을 때)
- [ ] PR 생성 및 승인 후 main 브랜치로 머지

## 에이전트 메모

- 이 저장소는 명세 문서와 공식 5개 엔드포인트의 초기 구현이 함께 있는 상태다.
- "구현 확장해줘" 요청은 공식 5개 엔드포인트와 동일한 파싱/fixture/테스트 패턴을 유지한다.
- "구조 정리" 요청은 README의 프로젝트 파일 구조와 `SKILL.md`의 Required deliverables를 기준으로 맞춘다.
