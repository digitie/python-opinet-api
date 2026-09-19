# 지역별 웹 화면 수집기

`opinet.experimental.OpinetBrowserCollector`는 공식 open API에 포함되지 않은
실험 기능입니다. `https://www.opinet.co.kr/searRgSelect.do`의 공개 화면을
Playwright로 열고, 화면의 지역 선택과 조회 동작을 수행한 뒤
`searRgSelect.do` HTML 결과 또는 `searRgCircleAjax.do` JSON 결과를
typed dataclass로 변환합니다.

## 설치

```bash
pip install -e ".[browser]"
playwright install chromium
```

## 기본 사용

```python
import asyncio

from opinet.experimental import OpinetBrowserCollector


async def save(snapshot):
    for station in snapshot.stations:
        print(
            station.name,
            station.address,
            station.price_by_product,
            station.is_illegal,
            station.is_self,
        )


async def main():
    collector = OpinetBrowserCollector(
        # 시군구별 조회가 기본값이다. 읍면동별 조회는 요청 수가 크게 늘어난다.
        query_level="sigungu",
        headless=True,
    )
    snapshot = await collector.collect_once()
    await save(snapshot)


asyncio.run(main())
```

`headless=False`로 바꾸면 브라우저 창을 표시할 수 있다. 기본 User-Agent와
Chromium 설정을 사용하며 PC 브라우저로 위장하기 위한 패치나 stealth 플러그인은
사용하지 않는다. Playwright bundled Chromium 대신 시스템에 설치된 Chrome을
사용하려면 호환성 선택지인 `browser_channel="chrome"`을 명시할 수 있다.
지역 선택 AJAX와 검색 응답이 완료되고 실제 DOM이 갱신된 뒤 다음 단계로 진행하며,
HTTP 오류·접근 거부·CAPTCHA 응답은 빈 결과로 바꾸지 않고 실패시킨다.
초기 화면이 같은 검색 문서로 자동 이동해 Chromium이 이전 응답 본문을 폐기하면,
현재 문서와 응답이 모두 오피넷 HTTPS의 정확한 `/searRgSelect.do` 경로와 같은 query인지
확인한 뒤 그 HTML에서 차단 여부를 검사한다. 대기 시간은 collector의 `timeout_ms`를 따른다.
외부 주소·다른 화면으로의 이동과 일반 네트워크 오류는 복구 대상으로 취급하지 않는다.

## 반복 수집과 부하 분산

기본 `OpinetBrowserThrottle`은 화면 조작 사이에 0.25~1.25초의 무작위 대기를
넣고, 전체 수집 사이에는 8시간의 대기를 선택한다. 최근 24시간 실행 횟수는
최대 3회로 제한한다. 이 지연은
사람인 것처럼 보이기 위한 기능이 아니라 요청과 화면 갱신을 한 시점에 몰리지
않게 하는 부하 분산 정책이다.

```python
import asyncio

from opinet.experimental import OpinetBrowserCollector, OpinetBrowserThrottle


async def save(snapshot):
    # 파일/DB 저장은 호출 애플리케이션이 담당한다.
    ...


async def main():
    collector = OpinetBrowserCollector(
        throttle=OpinetBrowserThrottle(
            action_min_seconds=0.5,
            action_max_seconds=2.0,
            max_runs_per_24h=3,
            max_search_requests=10_000,
        )
    )
    stop_event = asyncio.Event()
    await collector.run_forever(save, stop_event=stop_event)


asyncio.run(main())
```

`run_forever()`는 기본적으로 시작할 때 한 번 즉시 실행하고 이후 실행 전에
8시간을 기다린다. 최근 24시간에 3회 실행한 경우에는 다음 실행 가능 시각까지
추가로 기다린다. `stop_event.set()` 또는 `asyncio` 작업 취소로 중단할 수 있다.
한 실행은 `max_search_requests`를 넘는 지역 조회를 시작하지 않는다.
저장 실패나 일시적 네트워크 오류 후에도 다음 주기를 예약하려면 `on_error`에
호출 애플리케이션의 알림 함수를 전달한다. 기본값은 오류를 호출자에게 전파해
실패를 숨기지 않는다. `max_runs_per_24h`는 하나의 `run_forever()` 작업에
적용되므로, 여러 프로세스에서 동시에 수집을 시작하지 않도록 호출 애플리케이션에서
단일 실행과 마지막 성공 시각을 관리해야 한다.

## 수집 범위

`OpinetBrowserSnapshot.regions`에는 시도·시군구·읍면동 선택값이 들어간다.
`stations`에는 주유소 탭과 충전소 탭의 결과를 합쳐 다음 정보가 포함된다.

- `B034_P`, `B027_P`, `D047_P`, `C004_P`, `K015_P` 가격과 각각의 갱신시각
- KATEC 원시 좌표와 변환된 WGS84 `lon`/`lat`
- `POLL_DIV_CD`/`POLL_DIV_NM`, 전화번호, 주소, 사업자번호, `CB_CD`
- `VLT_YN`, `SELF_DIV_CD`, `SEL24_YN`, `KPETRO_YN`, `KPETRO_DP_YN`
- `GOOD_OS_YN`, `GOOD_OS_YN5`, `RGN_FRCS_YN` (`RGN_FRCS_YN`은 HTML 경로에서
  provider가 제공하지 않으면 `None`)
- `CWSH_YN`, `MAINT_YN`, `CVS_YN`, `CS_YN`
- 할인·적립·사은/오픈행사·온라인행사·기타 안내 문자열
- 알 수 있는 새 provider 필드를 잃지 않도록 한 원시 JSON 매핑

같은 주유소가 유종별 목록에 반복되면 `UNI_ID` 기준으로 하나로 합친다. 주유소와
충전소 탭에서 모두 반환된 겸업 시설은 `source_kinds`에 두 종류가 남고, 가격은
유종별로 병합된다.

`query_level="sigungu"`는 지역 목록은 읍면동까지 수집하되 주유소 조회는
시군구 단위로 실행한다. 모든 읍면동마다 별도 조회해야 하는 경우에만
`query_level="dong"`을 사용한다. 후자는 요청 수가 크게 증가하므로 운영 전
실제 반환 건수와 오피넷 이용 약관을 확인해야 한다.

## 제한사항

- 공식 API 계약이 아닌 공개 화면의 DOM, `searRgSelect.do` HTML, `searRgCircleAjax.do`
  응답에 의존한다.
- 화면 구조나 응답 필드가 바뀌면 fixture와 파서를 다시 검증해야 한다.
- CAPTCHA, 자동화 확인, 접근 거부 화면이 나타나면 우회하지 않고 실패한다.
- 운영 전 [오피넷 이용약관·저작권·공개 API 안내](https://www.opinet.co.kr/user/custapi/openApiInfo.do),
  robots 정책, 허용된 수집·보관·재배포 범위를 확인하고 필요한 승인과 출처 표시를 확보한다.
- 공식 API나 사전 협의된 데이터 제공 경로가 있으면 화면 수집보다 우선한다.
- 수집한 전화번호·사업자번호 등 공개 사업자 정보도 필요한 범위에서만 저장하고
  로그에 원문을 남기지 않는다.
