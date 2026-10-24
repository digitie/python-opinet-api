# Changelog

## 2026-10-24 — 무작위 조작 대기와 HTML 결과 대기 단축

- 기본 클릭·선택 대기를 0.25~1.25초에서 0.05~0.15초로 줄이고 매 조작의 랜덤성을 유지한다.
- 서버 HTML에 완성된 일반 주유소 결과가 있으면 새 문서·지역·탭·모든 원본 링크 일치를
  확인한 즉시 읽는다. 이미지·지도 완료 대기를 줄이며 빈/동적 결과는 기존 완료 검증을 유지한다.
- 30분은 실제 전국 실행으로 검증할 목표이며 미검증 속도 향상률을 보장하지 않는다.

## 2026-10-24 — 지역 체크포인트와 저장 재개

- 선택적인 영속 체크포인트로 지역 목록·완료 결과·요청 예산을 보존하고 미완료 지역부터 재개한다.
- 완료 스냅샷을 원래 시각으로 재전달하고 DB commit 뒤 명시적으로 소비 완료를 기록한다.
- 시군구 조회의 읍면동 탐색을 제거한다. `regions` 개수는 실제 조회 단위를 따른다.
- 지역 선택·DOM 시간 초과와 HTTP 5xx도 새 문서에서 한 번 재시도한다.

## 2026-09-14 — async-only와 공통 TPS

OpinetClient를 native async 하나로 통합했다. 모든 조회·디버그에 await, 격자 순회에 async for를 사용한다. 공통 AsyncTokenBucket, max_rps/rate_limiter를 공개하고 재시도·리다이렉트마다 TPS를 적용한다. 동기 HTTP·Async 접두사·aio를 제거하고 비동기 VWorld 연동과 동시 디버그를 지원한다.

이 프로젝트의 주요 변경 사항을 기록합니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따릅니다. 아직 PyPI에 배포되지 않았으므로 버전 태그 없이 모든 항목을 `[Unreleased]`에 시간순(최신 항목이 위)으로 기록합니다.

## [Unreleased]

### Fixed
- 지역별 화면 수집에서 한 지역(시군구)의 '조회' 검색 응답이 시간 초과되면 검색 화면을 새로 열고
  탭·지역을 다시 고른 뒤 그 지역만 한 번 다시 조회한다(첫 시도의 늦은 응답을 쓰지 않는다). 재시도
  요청은 `max_search_requests` 상한에서 차감하며, 여유가 없으면 재시도하지 않는다. 지역 선택 단계·결과
  DOM 대기의 시간 초과, 인증 거부·429·차단 화면·파싱 오류는 재시도하지 않는다. 재시도로 성공한 조회는
  경고 로그와 `OpinetBrowserSnapshot.region_retry_count`로 드러난다.
- 지역 선택·검색 실패 진단이 한글 지역 이름을 모두 `target=non-numeric`으로 뭉개던 문제를
  고쳤다. 숫자 코드는 그대로, 이름은 한글 음절·숫자만 남겨 12자로 자른 시도/시군구 경로와
  `attempt`/`attempts`를 남긴다. 응답 이후 DOM 대기 시간 초과도 원 예외 문자열 없이 같은
  형식으로 정제한다(재시도는 하지 않는다).
- HTTP 200의 서비스 이용 불가 HTML을 정상 검색 화면으로 오인하지 않고 조기 실패시킨다.
  브라우저 응답 대기 오류는 단계와 최근 요청 종류로 진단하며 비밀 URL·본문은 기록하지 않는다.
- 서로 다른 검색지역의 같은 주유소 ID를 전역으로 병합해 유효 가격과 주유소/충전소
  출처가 후행 빈 값으로 소실되지 않도록 수정. 가격·갱신 시각은 같은 입력의 쌍으로
  선택하며 대표 지역은 최초 검색 문맥으로 명시.
- Playwright가 검색 화면 자동 이동 후 이전 응답 본문을 폐기한 경우 현재 오피넷 검색
  문서를 검증하도록 수정. 차단 화면·외부 이동·일반 네트워크 오류는 계속 실패 처리.
- README 라이선스 표기 오류(MIT → GPL-3.0-or-later)를 실제 `pyproject.toml`/`LICENSE` 값과 일치하도록 정정.

### Added
- 지역별 화면 수집(`OpinetBrowserCollector.collect_page`)이 단계별 진행을 `INFO` 로그로 남긴다:
  지역 탐색의 시도별 진행·완료(지역 수), 탭(주유소/충전소) 시작·끝, 탭 안의 시도 단위 진행
  (`done=i/N`, 누적 주유소 수, 재시도 수)과 탭·전체 경과 시간. 느린 호스트에서 어디서 시간이 드는지
  보기 위한 것이며 지역 식별자는 기존 진단과 같은 정제 규칙(`_region_label`)을 따른다.
- `opinet.experimental.OpinetBrowserCollector`: Playwright 기반 지역별 공개 화면 수집기. 시도·시군구·읍면동 목록, 주유소·충전소, 유종별 가격·갱신시각, 상표·부가정보·관찰 가능한 원시 응답 필드를 보존하며 요청 부하 분산용 무작위 화면 간격과 기본 8시간 수집 간격, 최근 24시간 최대 3회 실행 제한을 제공한다. 지역 AJAX/응답 상태 검증, 요청 상한, 접근 거부 감지, 리소스 정리와 실패 콜백을 포함한다.
- 서비스키 공백/개행 자동 제거와 `.env` 기본 로드, 공식 5개 API 카탈로그(`get_api_catalog_options()` 등), Streamlit Debug Trace 표시용 `DebugRun`, fixture 저장/replay 문서와 예제 앱(`examples/streamlit_debug_app.py`).
- `StationDetail.to_normalized()`와 `NormalizedFuelStationDetail`, `NormalizedFuelStationDetailPrice` DTO.
- PEP 561 `py.typed` marker와 package data 설정. wheel/sdist 설치 후 `import opinet`, downstream mypy smoke 테스트 추가.
- `opinet.normalized` Pydantic DTO 계층(`NormalizedFuelAverage`, `NormalizedFuelStation`, `NormalizedFuelRegionCode` 등), KST datetime helper, JSON-safe raw 변환 helper, 모델별 `to_normalized()`.
- 공용 normalized layer: `FuelType`/`ProductCode` 양방향 매핑, `Station` product/trade context, 좌표 tuple helper, `AreaCode` helper(`code_level`, `parent_sido_code`, `bjd_sido_prefix`), 읽기 전용 `raw` payload 보존.
- 공식 5개 엔드포인트 구현, fixture 기반 네트워크 없는 테스트 115개, mypy/coverage 검증, 반복 실수 방지 체크리스트.
- 응답 데이터 Python 네이티브 타입 변환(`date`/`time`/`float`/`bool`/enum), 시도코드 ↔ 법정동코드 매핑.
- `opinet-api.md` 초기 명세서 작성. 공식 사이트 기준 5개 API 검증, 시도코드/필드 의미 정정.

### Changed
- Playwright 공개 화면 수집기의 기본 `timeout_ms`를 30초에서 60초로 늘렸다. 지연된
  화면 응답을 기다리는 제한만 조정하며, 추가 요청·자동 재시도·접근 제한 우회는 하지 않는다.
- Playwright 지역별 화면 수집기의 기본 반복 주기를 8시간으로 조정하고, 하나의 반복 작업이 최근 24시간에 최대 3회만 실행되도록 제한.
- Windows/PowerShell 환경에서 `rg` 실행이 권한 문제로 실패할 때의 우회 명령(`git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`)을 문서화.
- 문서의 파일 위치 표기를 프로젝트 루트 기준 상대 경로로 고정하고, Python 내부 문서(docstring/주석)는 한글로 작성한다는 규칙을 추가.
