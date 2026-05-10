# AGENTS.md

## 역할
- 이 파일은 Codex/agent가 pyopinet 작업 전에 읽는 최소 지침이다.
- 상세 API 명세와 구현 규칙은 작업 주제에 맞춰 `opinet-api.md`와 `SKILL.md`를 추가로 읽는다.
- 루트 기준과 하위 문서가 충돌하면 아래 우선순위를 따른다.

## 지시 우선순위
1. 사용자 요청
2. 이 `AGENTS.md`
3. `opinet-api.md`
4. `SKILL.md`
5. `README.md`
6. 기존 코드베이스 규칙
7. 최소한의, 되돌릴 수 있는 가정

## 프로젝트 기준
- pyopinet은 한국석유공사 오피넷(Opinet) 오픈 API의 비공식 Python 클라이언트 라이브러리다.
- 저장소의 1차 범위는 공식 오픈 API 페이지에 등재된 5개 엔드포인트 구현이다.
- PDF 가이드북의 추가 API는 검증 전까지 `opinet.experimental`에 둔다.
- Python 3.11 이상을 기준으로 하며 `dataclass(frozen=True, slots=True)`와 `StrEnum`을 사용한다.
- 런타임 의존성은 `requests`, `pydantic`, `pykrtour[geo]`이고 테스트는 `pytest`, `responses`, `pytest-cov`를 기준으로 한다.
- 라이선스는 루트 `LICENSE`를 따른다.

## 핵심 불변 조건
- Base URL은 `https://www.opinet.co.kr/api/`이다.
- 인증 파라미터는 `certkey`이다. 비공식 예제의 `code`를 기본값으로 쓰지 않는다.
- 모든 라이브러리 호출은 `out=json`을 기본으로 한다. XML은 디버깅 또는 문서 참조용이다.
- 공식 구현 대상은 `avgAllPrice.do`, `lowTop10.do`, `aroundAll.do`, `detailById.do`, `areaCode.do` 5개다.
- API 응답의 숫자, 날짜, 시간, 플래그는 문자열로 오더라도 모델 경계에서 Python 네이티브 타입으로 변환한다.
- 선행 0이 의미 있는 값(`AREA_CD`, `SIGUNCD`, `UNI_ID`, 제품/상표 코드)은 `int`로 변환하지 않는다.
- KATEC 좌표는 API 내부 좌표계이고, 공개 사용성은 WGS84를 함께 제공한다.
- 좌표 변환은 `pykrtour.PlaceCoordinate`와 `pykrtour.KatecPoint`를 직접 사용한다. `opinet` 내부에 별도 wrapper, proxy dataclass, 호환 adapter를 만들지 않는다.
- `LPG_YN`은 LPG 판매 여부가 아니라 업종 구분이며 `StationType`으로 매핑한다.
- `KPETRO_YN`은 알뜰주유소 여부가 아니라 품질인증 여부이며 `is_kpetro`로 매핑한다.
- 알뜰주유소 여부는 상표 코드 `RTE`, `RTX`, `NHO`로 판정한다.
- 인증키, 실제 API 키, 원본 비밀값은 코드, fixture, 로그, 문서에 남기지 않는다.
- 로컬 live 테스트 키는 `.env` 또는 환경변수에만 둔다. `.env.example` 외의 `.env*` 파일은 커밋하지 않는다.

## 문서 라우팅
- 사용자용 개요와 예시: `README.md`
- 구현 상태/유지보수 체크리스트: `docs/implementation-status.md`
- API 필드, 코드표, 응답 예시, 테스트 전략: `opinet-api.md`
- 에이전트 구현 규칙과 함정 목록: `SKILL.md`
- 패키지/의존성/테스트 설정: `pyproject.toml`
- 공식 클라이언트 진입점: `opinet/client.py`
- HTTP/에러 매핑: `opinet/_http.py`
- 타입 변환: `opinet/_convert.py`
- 코드표/enum/시도 매핑: `opinet/codes.py`
- 공통 좌표/장소 DTO: `pykrtour.PlaceCoordinate`, `pykrtour.KatecPoint`
- 응답 모델: `opinet/models.py`
- 미검증 API: `opinet/experimental/`
- 테스트 fixture: `tests/fixtures/`

## 문서 작성 규칙
- 문서에서 파일 위치를 언급할 때는 프로젝트 루트 기준 상대 경로만 쓴다. 예: `opinet/client.py`, `docs/implementation-status.md`.
- 로컬 절대 경로는 실행 로그나 임시 설명에만 쓰고 저장소 문서에는 남기지 않는다.
- Python 내부 문서(모듈, 클래스, 함수, 메서드 docstring과 유지보수용 주석)는 한글로 작성한다.
- API 필드명, 엔드포인트, enum 값, 외부 오류 메시지처럼 원문 자체가 의미 있는 값은 그대로 둔다.

## 로컬 도구/인코딩 규칙
- 이 환경에서 `rg` 실행이 `Access is denied`로 실패할 수 있다. 같은 실패를 반복하지 말고 `git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`으로 우회한다.
- 한글 문서나 소스 파일을 PowerShell에서 읽을 때는 기본 출력 인코딩을 믿지 말고 `Get-Content -Encoding utf8` 또는 `Get-Content -Raw -Encoding utf8`을 사용한다.
- 깨진 한글 출력이 보이면 파일 내용이 깨졌다고 판단하지 말고 먼저 UTF-8 인코딩을 명시해서 다시 확인한다.

## 작업 원칙
- 구현 작업 전에는 `opinet-api.md`의 관련 엔드포인트 섹션과 `SKILL.md`의 불변 조건을 먼저 확인한다.
- 변경은 가능한 한 작은 완성 단위로 만들고, 공개 API 이름과 타입 안정성을 우선한다.
- 공통 타입이나 변환 로직이 `pykrtour` 같은 다른 TripMate 라이브러리에 이미 있으면 최소 수정 범위보다 직접 의존과 직접 적용을 우선한다.
- 불필요한 compatibility wrapper, mirror dataclass, 단순 위임 함수는 만들지 않는다. 기존 공개 API를 깨야 하더라도 문서와 테스트를 함께 고쳐 공통 구현을 직접 쓰는 방향으로 정리한다.
- 응답 파싱 로직은 raw 문자열을 사용자 모델에 그대로 흘리지 않는다.
- HTTP 상태와 body 기반 오류 매핑은 `_http.py` 한 곳에 모은다.
- 엔드포인트별 파라미터 검증은 HTTP 호출 전에 수행하고 `OpinetInvalidParameterError`를 사용한다.
- 실제 API 호출이 필요한 테스트는 `@pytest.mark.live` 뒤에 두고 기본 테스트는 네트워크 없이 동작하게 한다.
- fixture의 숫자/date/time 필드는 실제 API처럼 문자열로 유지해서 변환 경로를 테스트한다.
- 새 public 메서드나 모델을 추가하면 README 또는 docstring도 함께 갱신한다.
- 원격 API 동작이 불확실하면 실험 모듈에 두고 "Unverified" 경고를 남긴다.

## 검증 기준
- 구조/문법 확인: `python -m compileall opinet`
- 단위 테스트: `pytest`
- 커버리지 목표: `pytest --cov=opinet --cov-fail-under=90`
- 타입 검사: `python -m mypy opinet`
- 실제 API 스모크: `pytest -m live --run-live` (`OPINET_API_KEY` 필요)
- HTTP mocking 테스트는 `responses`를 사용한다.
- 좌표 변환 자체는 `pykrtour` 테스트에서 검증하고, `pyopinet`에서는 요청/응답 모델 경계가 `PlaceCoordinate`와 `KatecPoint`를 직접 쓰는지 검증한다.
- 타입 변환 테스트는 정상값, 빈 문자열/공백/None, 잘못된 포맷을 모두 포함한다.

## 반복 실수 방지
- `StationDetail`의 전화번호 필드는 `tel`이다. `phone`을 새로 만들지 않는다.
- `OilPrice`에는 `product_name`이 없다. `OIL_PRICE` 응답에는 `PRODNM`이 오지 않는다.
- fixture 값은 실제 API처럼 문자열로 둔다. 특히 `PRICE`, `DIFF`, `DISTANCE`, `GIS_*`, `TRADE_DT`, `TRADE_TM`을 JSON number로 바꾸지 않는다.
- `RESULT.OIL`과 `OIL_PRICE`는 단일 dict일 수 있다. list로 단정하지 말고 정규화한다.
- `POLL_DIV_CO`/`GPOLL_DIV_CO`가 실제 응답 우선 필드다. 문서 표기의 `*_CD`는 fallback으로만 사용한다.
- 공백 1자(`" "`)는 값이 아니다. `strip_or_none()`으로 `None` 처리한다.
- `SIGUNCD`는 오피넷 4자리 시군구 코드이며 법정동 5자리 시군구 코드나 10자리 법정동코드와 일치한다고 가정하지 않는다.
- 개발 의존성에서 `types-requests`를 빼면 `mypy opinet`이 스텁 부재로 실패한다.

## 에이전트 메모
- 이 저장소는 명세 문서와 공식 5개 엔드포인트의 초기 구현이 함께 있는 상태다.
- "구현 확장해줘" 요청은 공식 5개 엔드포인트와 동일한 파싱/fixture/테스트 패턴을 유지한다.
- "구조 정리" 요청은 README의 프로젝트 파일 구조와 `SKILL.md`의 Required deliverables를 기준으로 맞춘다.
