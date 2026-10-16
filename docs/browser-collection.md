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
기본 `timeout_ms`는 60초다. 이는 지연된 화면 갱신을 기다리는 상한이며, 차단·CAPTCHA
응답에 대한 자동 재시도를 뜻하지 않는다. 더 짧거나 긴 제한이 필요한 호출자는
생성자 인자로 명시할 수 있다.

한 지역(시군구 또는 읍면동)의 '조회' 검색 응답이 시간 초과되면 검색 화면을 새로 열고
(`page.goto`, 출처·차단 검사 포함) 탭과 지역을 처음부터 다시 고른 뒤 그 지역만 **한 번** 다시
조회한다. 같은 화면에서 다시 조회하면 첫 시도의 늦은 응답이 두 번째 조회의 결과로 쓰일 수 있기
때문이다. 그래도 실패하면 전체 수집을 실패시킨다. 재시도 사이에도 화면 조작 간격
(`action_min_seconds`~`action_max_seconds`)을 지키며, 재시도 요청은
`max_search_requests` 상한에서 차감된다. 첫 조회분(`지역 수 × 2탭`)을 예약하고 남은
여유가 없으면 재시도하지 않고 `retry=budget-exhausted`로 실패한다. 지역 선택 단계의 시간 초과
(같은 화면에서 다시 고르면 이미 선택된 값으로 보고 응답 검증과 하위 목록 대기를 건너뛴다),
결과 DOM 대기 시간 초과(차단·빈 화면일 수 있다), HTTP 401/403/429, 차단·서비스 불가 화면,
파싱 오류는 재시도하지 않는다. 재시도로 성공한 조회는 `opinet.experimental.browser` 경고 로그와
`OpinetBrowserSnapshot.region_retry_count`로 확인한다.

HTTP 200이어도 `The service is not available.` 오류 HTML이면 즉시 실패한다.
탭 전환·지역 선택·검색의 응답 대기 실패는 `OpinetServerError`에 단계·지역 식별자와
최근 8개 요청/응답/전송 실패 이벤트를 남긴다. 지역 식별자는 숫자 지역 코드면 그대로,
오피넷 화면처럼 값이 지역 이름이면 한글 음절·숫자만 남겨 최대 12자로 자른 값을 쓴다
(예: `phase=search:station:region=경기도/용인시수지구:attempt=2`, 그 밖의 문자열은
`redacted`). 지역 조회 실패에는 `attempts=1|2`가 붙는다. 인증 URL의 query, 헤더, 본문,
원 예외 문자열은 포함하지 않는다. 진단 자체는 같은 화면 동작만 관찰하며 요청을 추가하지 않는다.
HTTP 401/403/429와 취소는 기존 예외 의미를 유지한다. 오류 화면 감지가 과거 모든
timeout 원인의 해결을 뜻하지는 않으며, 실제 수집 복구는 별도로 확인해야 한다.
현재 이 안전 진단 범위는 응답 대기 구간이다. 초기 navigation과 응답 이후 DOM/파싱
오류까지 같은 진단으로 정제한다는 보장은 없으며, 소비자는 기존 오류 마스킹도 유지해야 한다.

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

같은 주유소가 유종별 목록이나 서로 다른 지역 검색에 반복되면 전역 `UNI_ID` 기준으로
하나로 합친다. ID가 없는 행만 지역·이름·좌표를 이용한 기존 fallback을 사용한다. 주유소와
충전소 탭에서 모두 반환된 겸업 시설은 `source_kinds`에 두 종류가 남고, 가격은
유종별로 병합된다.

가격은 빈 값으로 기존 유효 값을 덮지 않는다. 두 가격에 갱신 시각이 있으면 더 최신인
가격·시각 쌍을 선택하고, 한쪽만 시각이 있으면 그 유효 가격 쌍을 우선한다. 시각이 모두
없거나 같으면 먼저 읽은 유효 가격을 유지한다. 다른 가격의 갱신 시각만 복사하지 않는다.
`BrowserStation.region`은 최초 검색 선택값을 대표 문맥으로 유지하며 실제 소재지 또는
모든 검색지역 관계가 아니다. 실제 위치는 주소·좌표를 확인해야 한다. snapshot의 `regions`는
발견한 지역 목록이며 주유소별 지역 연결관계는 제공하지 않는다. 후속 저장/API의 지역 필터도
이 검색 문맥 의미를 보존해야 한다. 원시 `raw`는 기존처럼 최초 값 우선의 진단용 병합으로,
모든 입력 행의 완전한 감사 이력이 아니며 최종 가격은 typed `prices`를 사용한다.

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


## 부수 자원 비용의 선택적 비교

기본 block_visual_resources=False는 route를 설치하지 않는다. True를 명시하면
현재 페이지의 image/font/media 요청만 abort한다. document/script/stylesheet/XHR/fetch
및 알 수 없는 종류는 기존 route로 fallback한다. service worker 정책·탭·지역 선택·
파서/raw/좌표/가격·재시도/검색 상한/pacing은 바꾸지 않는다.
collect_once는 첫 navigation부터, collect_page(page)는 호출 이후 요청에만 적용한다.
이미 로드된 자원은 되돌리지 않는다. 실패·취소 시 자기 handler만 제거하며
호출자 페이지나 기존 route를 닫거나 지우지 않는다.

**운영 개선은 아직 검증하지 않았다.** Playwright 공식
[route 계약](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-route)은
routing 활성화가 HTTP cache를 끈다고 명시한다. 반복 navigation의 JS/CSS 요청은
늘 수 있고 service worker가 처리한 요청은 route를 통과하지 않을 수 있다.
CAPTCHA/접근 거부/401·403·429는 종전처럼 실패한다. 같은 입력에서 실제 출력·
서버 요청 수/CPU/메모리/wall을 검증하기 전 기본값을 바꾸거나 소비자에서 켜지 않는다.

on_metrics=callback은 별도 선택이며 실행당 한 번 읽기 전용 Mapping[str, int]를 받는다.
고정 키32개이며 URL·헤더·본문·지역·주유소·인증값은 없다. callback 일반 예외는
정제된 경고만 남기며 수집 결과나 원래 실패를 바꾸지 않는다. 동기 함수로 짧게 실행한다.

- navigation/discovery/search/wait/parse/close_elapsed_us와 같은 접두사의 count:
  실제 경과 마이크로초·호출 수. wait는 의도적 pacing 대기이며 응답/DOM 대기는
  discovery/search에 포함된다. 중첩 단계 시간을 합쳐 전체 CPU로 설명하지 않는다.
- total_elapsed_us, success/failed/cancelled: 전체 경과와 종료 상태. collect_once는
  Playwright 시작/종료와 context/browser cleanup을 포함하며 Chromium CPU/RSS는 아니다.
- request_count/request_failed_count, 종류별 requests, blocked_resource_count:
  브라우저의 요청 시도/실패/차단 수. cache/SW 때문에 서버 전송 수와 다를 수 있다.
- regions/query_regions/stations/region_retries: 완료 snapshot의 개수.
  도중 실패한 호출에서 완료 개수를 추정하지 않는다.

계측만 켜면 route/cache 정책은 바뀌지 않는다. 과거 run별 내역을 collector에 쌓지 않으며
ContextVar로 동시 호출을 격리한다. 생산 CPU/RSS 감소나 누수 해결을 주장하지 않는다.


### 로컬 Chromium 비교와 재현

의존성 browser/dev와 Playwright bundled Chromium을 준비한 환경에서 아래 검증을 실행한다.
기본 unit suite는 Playwright 미설치 시 실제 브라우저 fixture를 건너뛴다. 설치했으나
브라우저 binary가 없으면 설치/환경 실패를 숨기지 않고 실패한다. 실제 Opinet에는 접속하지 않는다.

    python -m pytest tests/test_browser_resource_fixture.py -q
    python tests/benchmark_browser_resources.py --output 비교결과.json

테스트 전용 loopback origin만 허용하는 fixture로 1지역·주유소/LPG 2탭을 읽었다.
세 쌍 각각 다른 Python 프로세스를 사용하고 실행 순서를 off/on, on/off, off/on으로 바꿨다.
수집 시각·임시 origin을 제외한 모든 typed/raw 출력 digest는 여섯 번 모두 같았다.
숫자·가격·좌표 원문, unknown raw 필드, 두 업종 병합, 지역 선택은 보존됐다.
서버가 받은 검색 POST2회/탭 POST1회/문서 GET1회도 동일했다.
별도 실제 fixture는 401/403/429와 HTTP200 CAPTCHA를 추가 검색 없이 실패시켰다.

2026-10-16 Linux x86_64/Python3.12.13/Playwright1.63.0의 단기 fixture 측정이다.
각 칸은 자원 정책 기본 / 차단이며, 양쪽 모두 on_metrics를 켰다. ms와 MiB 단위를 쓴다.

| 쌍 | wall ms | Python+회수 하위 CPU ms | 표본 RSS 합 MiB | 표본 PSS 합 MiB |
| --- | --- | --- | --- | --- |
| 1 | 815.05 / 810.35 | 1017.84 / 1029.65 | 758.57 / 679.16 | 453.59 / 429.33 |
| 2 | 807.48 / 824.36 | 973.47 / 1004.70 | 758.04 / 683.07 | 453.37 / 459.56 |
| 3 | 824.21 / 820.96 | 990.86 / 985.49 | 762.98 / 678.09 | 456.38 / 429.48 |

서버 총 요청은 기본9회/차단10회였다. image/font/media 전송3회는 없어졌지만
JS/CSS 각각1회가3회로 증가했다. 요청 시도/차단 계수와 서버 전송 수를 혼용하지 않는다.
wall은 Playwright 시작과 cleanup을 포함한다. Python CPU에는 자기 fixture 서버와
50ms 메모리 sampler가 포함되며 하위 CPU는 종료 후 회수한 누계다.
RSS는 공유 페이지를 중복 합산한다. PSS도 50ms 표본이므로 실제 peak 상한이 아니며
두 메모리 수치의 peak 시점이 다를 수 있다. sampler와 서버는 이 비교용 도구에만 있다.

CPU·wall 개선은 입증되지 않았고 메모리 표본만으로 운영 개선을 주장하지 않는다.
짧은 단일 fixture·세 쌍·통제되지 않은 호스트 cache/부하이며 장시간·ARM·실제 provider
지역 수와 자원 정책은 검증하지 않았다. 특히 cache 재전송 비용 때문에 실제 수집에서
오히려 느려질 수 있다. 운영 출력·요청량·CPU/PSS/wall 비교와 두 독립 리뷰 전에는
소비자 pin/옵션을 바꾸지 않는다. Transport의 scraper 재구현이나 현재 fuel 중단은 없다.
