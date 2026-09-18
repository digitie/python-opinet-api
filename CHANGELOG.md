# Changelog

## 2026-09-14 — async-only와 공통 TPS

OpinetClient를 native async 하나로 통합했다. 모든 조회·디버그에 await, 격자 순회에 async for를 사용한다. 공통 AsyncTokenBucket, max_rps/rate_limiter를 공개하고 재시도·리다이렉트마다 TPS를 적용한다. 동기 HTTP·Async 접두사·aio를 제거하고 비동기 VWorld 연동과 동시 디버그를 지원한다.

이 프로젝트의 주요 변경 사항을 기록합니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따릅니다. 아직 PyPI에 배포되지 않았으므로 버전 태그 없이 모든 항목을 `[Unreleased]`에 시간순(최신 항목이 위)으로 기록합니다.

## [Unreleased]

### Fixed
- README 라이선스 표기 오류(MIT → GPL-3.0-or-later)를 실제 `pyproject.toml`/`LICENSE` 값과 일치하도록 정정.

### Added
- `opinet.experimental.OpinetBrowserCollector`: Playwright 기반 지역별 공개 화면 수집기. 시도·시군구·읍면동 목록, 주유소·충전소, 유종별 가격·갱신시각, 상표·부가정보·관찰 가능한 원시 응답 필드를 보존하며 요청 부하 분산용 무작위 화면 간격과 기본 10~12시간 수집 간격을 제공한다. 지역 AJAX/응답 상태 검증, 요청 상한, 접근 거부 감지, 리소스 정리와 실패 콜백을 포함한다.
- 서비스키 공백/개행 자동 제거와 `.env` 기본 로드, 공식 5개 API 카탈로그(`get_api_catalog_options()` 등), Streamlit Debug Trace 표시용 `DebugRun`, fixture 저장/replay 문서와 예제 앱(`examples/streamlit_debug_app.py`).
- `StationDetail.to_normalized()`와 `NormalizedFuelStationDetail`, `NormalizedFuelStationDetailPrice` DTO.
- PEP 561 `py.typed` marker와 package data 설정. wheel/sdist 설치 후 `import opinet`, downstream mypy smoke 테스트 추가.
- `opinet.normalized` Pydantic DTO 계층(`NormalizedFuelAverage`, `NormalizedFuelStation`, `NormalizedFuelRegionCode` 등), KST datetime helper, JSON-safe raw 변환 helper, 모델별 `to_normalized()`.
- 공용 normalized layer: `FuelType`/`ProductCode` 양방향 매핑, `Station` product/trade context, 좌표 tuple helper, `AreaCode` helper(`code_level`, `parent_sido_code`, `bjd_sido_prefix`), 읽기 전용 `raw` payload 보존.
- 공식 5개 엔드포인트 구현, fixture 기반 네트워크 없는 테스트 115개, mypy/coverage 검증, 반복 실수 방지 체크리스트.
- 응답 데이터 Python 네이티브 타입 변환(`date`/`time`/`float`/`bool`/enum), 시도코드 ↔ 법정동코드 매핑.
- `opinet-api.md` 초기 명세서 작성. 공식 사이트 기준 5개 API 검증, 시도코드/필드 의미 정정.

### Changed
- Windows/PowerShell 환경에서 `rg` 실행이 권한 문제로 실패할 때의 우회 명령(`git ls-files`, `Get-ChildItem -Recurse -File`, `Select-String`)을 문서화.
- 문서의 파일 위치 표기를 프로젝트 루트 기준 상대 경로로 고정하고, Python 내부 문서(docstring/주석)는 한글로 작성한다는 규칙을 추가.
