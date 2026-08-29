# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따릅니다. 아직 PyPI에 배포되지 않았으므로 버전 태그 없이 모든 항목을 `[Unreleased]`에 시간순(최신 항목이 위)으로 기록합니다.

## [Unreleased]

### Fixed
- README 라이선스 표기 오류(MIT → GPL-3.0-or-later)를 실제 `pyproject.toml`/`LICENSE` 값과 일치하도록 정정.

### Added
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
