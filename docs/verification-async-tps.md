# async-only와 TPS 검증

2026-09-14, baseline `356cb0eaad46e4d1896092b164ff4ba08ede25c0` 대비 검증했다.

- 독립 적대적 리뷰 A: 전송/TPS/취소/세션 소유권/동시 진단/키 노출 검토 후 승인.
- 독립 적대적 리뷰 B: 공식 API/좌표/코드/반환 모델/bbox/VWorld/문서 검토 후 승인.
- 리뷰에서 발견한 실패 캐시의 잠금 참조, 진단 모델의 tuple·mappingproxy 보존,
  파싱 예외의 키 노출, 독립 문서 예제의 client 누락과 None 가격 출력을 수정했다.
- 전체 offline: 212 passed, 14 subtests passed, live 4 deselected. 커버리지 93.08%로
  90% 기준을 충족했다. RuntimeWarning 오류 승격 상태에서 통과했다.
- wheel/sdist 빌드·설치·downstream mypy 포함 패키징 3개 테스트 통과.
- mypy: 18개 소스 파일 통과. compileall: src/tests/examples 통과.
- 문서의 async main 12개를 저장소 fixture와 MockTransport로 실행해 모두 통과했다.
- 두 최종 리뷰 이후 live E2E: **4 passed, 212 deselected, 4.19초**.
  공식 5개 엔드포인트의 실제 데이터 파싱, 지역 코드 raw 응답, bbox 순회와 중복 제거,
  VWorld L2 검색을 통한 0113→11680 매핑을 확인했다. skip/xfail/HTTP 403은 없었다.

실행 명령:

```bash
python -m pytest -m "not live" --cov=opinet --cov-fail-under=90 -q -W error::RuntimeWarning
python -m mypy src/opinet
python -m compileall src/opinet tests examples
python -m pytest -m live --run-live -rs
```

인증키는 로컬 환경에서만 읽고 로그에서 마스킹했다. 이 검증은 관찰된 호출 범위의
결과이며 공급자 전체 데이터나 이후 가용성을 보장하지 않는다.
