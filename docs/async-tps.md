# 비동기 API와 공통 TPS

## 비동기 호출과 요청 속도

`OpinetClient`의 조회와 디버그는 `await`, `iter_stations_in_bbox`는 `async for`,
종료는 `async with` 또는 `await client.aclose()`를 사용한다. Async 접두사 클라이언트,
aio 팩터리와 동기 transport는 제거했다. 코드표·좌표·모델 변환·fixture 저장 같은
로컬 유틸리티는 일반 함수다. 기존 엔드포인트 인자와 반환 모델은 유지한다.

기본 `max_rps=5.0`이다. `AsyncTokenBucket(max_rps, capacity=...)`를
`rate_limiter=`에 주입하면 여러 클라이언트가 같은 요청 예산을 쓴다. 주입된 버킷이
max_rps보다 우선한다. 기본 capacity는 max(1, max_rps)이며 초기에는 가득 차
있으므로 burst를 허용한다. 일정한 간격은 capacity=1로 설정한다.
각 요청·재시도·리다이렉트·디버그·격자 셀에 같은 버킷을 적용한다.
인자 검증 실패와 캐시 적중은 요청을 보내지 않는다. TPS는 일일 쿼터를 대신하지 않는다.

버킷은 한 이벤트 루프에서 사용한다. 대기 취소는 토큰을 소비하지 않고 다음 대기자를
진행시킨다. 401/403/429는 즉시 실패하며 네트워크 오류와 5xx만 기존 backoff로
재시도한다. 사용자 정의 인증/transport 내부에서 발생하는 추가 전송은 계측 범위 밖이다.

내부 HTTP 세션은 첫 요청 시 생성하고 종료 시 닫는다. session에 주입하는 비동기
세션은 호출자가 닫는다. 종료한 클라이언트의 추가 요청은 실패한다.
디버그 기록은 ContextVar로 호출별 격리하고 성공·실패·취소 모두에서 복원한다.
응답 파싱은 원문으로 완료한 후 진단 결과의 알려진 키와 인코딩된 키를 마스킹한다.
VWorld 연동은 비동기 search_district를 사용하며 완료된 지역 코드만 캐시한다.

```python
import asyncio
from opinet import AsyncTokenBucket, OpinetClient


async def main() -> None:
    bucket = AsyncTokenBucket(2, capacity=1)
    async with OpinetClient(rate_limiter=bucket) as client:
        rows = await client.get_national_average_price()
        print(rows)


asyncio.run(main())
```
