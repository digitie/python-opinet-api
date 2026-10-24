# 지역별 웹 화면 수집기

## 2026-10-24 수집 시간 단축

기본 화면 조작 간격은 매번 독립적으로 뽑는 **0.05~0.15초 무작위 대기**다.
기존 0.25~1.25초보다 평균 대기는 0.75초에서 0.10초로 줄지만 랜덤성은 유지한다.
지역 선택 AJAX 완료·선택값 일치·검색 응답 검증은 생략하지 않는다.
지역 선택은 헤더 수신뿐 아니라 응답 본문 완료까지 제한 시간 안에 기다린 뒤
하위 목록과 선택값을 확인한다. 빈 결과도 선택 지역·활성 탭이 맞아야 확정한다.

HTML 검색 응답의 결과 표에 일반 주유소 원본 링크가 이미 있으면 새 문서·지역 선택값·
활성 탭·응답 원본 링크 전체와 DOM의 일치를 확인하고 이미지·지도 자원의 `load`를
기다리지 않는다. 가격과 원시 필드는 기존 링크 파서로 동일하게 읽는다. 서버 결과 증거가
없는 빈 표, 동적 결과, 불법 주유소 DOM 필드 경로, 문서 이동 없는 HTML 응답은 기존
문서 완료 대기를 유지한다. 빈 표 존재만으로 수집 성공을 확정하지 않는다.

전국 약230개 시군구·460회 검색의 30분 목표는 시작·탐색 약120초, 랜덤 대기 약100초를
제외한 지역 선택·응답·파싱 평균이 약3.4초 이하여야 한다. 이는 시간 예산이며 운영 실측
보장이 아니다. `selection`·`response`·`results` 누적 로그로 실제 병목을 확인한다.
실제 전국 수집을 30분 안에 완료하기 전에는 목표 달성으로 보고하지 않는다.

## 2026-10-24 재개와 수집 비용

`OpinetBrowserCollector(checkpoint_path="/persistent/opinet.sqlite3")`는 지역별 정상 결과를
SQLite에 확정한다. 다음 실행은 저장된 지역 목록과 완료 지역을 읽고 미완료 지역부터
진행한다. 정상 빈 결과도 완료로 기록하고 요청 예산은 요청 전에 확정해 재기동으로
초기화하지 않는다. 같은 경로는 단일 작성자만 사용하며 프로세스 종료 시 잠금 DB의
잠금은 OS가 해제한다. 두 파일은 영속 디렉터리에 둔다. 디스크 부족·손상은 성공이 아니다.

전체 완료 뒤 `collect_once()`와 `pending_snapshot()`은 브라우저를 시작하지 않고 원래
`collected_at`의 같은 결과를 반환한다. 호출자는 DB commit 뒤
`collector.acknowledge_snapshot(snapshot)`을 호출한다. 저장 실패는 외부 재조회 없이
복구하고, commit 뒤 확인 기록 전 중단은 같은 결과를 멱등 저장해 복구한다. 미완료
결과는 완결 스냅샷으로 제공하지 않는다. 기본 유효기간은 시작부터 12시간이며
`checkpoint_max_age`로 최대 24시간까지 설정한다. 만료·조회 범위 변경·소비 완료 때
새 수집을 시작한다. 진행 중 만료도 거부해 오래된 결과를 최신으로 오인하지 않는다.

`sigungu`는 시도별 시군구 목록만 탐색한다. 읍면동 전체 탐색 후 시군구로 축약하던
불필요한 화면 전환을 제거했다. `snapshot.regions`와 `region_count`는 시군구 목록이며
`dong`에서는 기존 읍면동 목록을 유지한다. 주유소 지역 문맥과 실제 검색 범위는 같다.
지역 선택·검색·DOM 시간 초과와 HTTP 5xx는 새 검색 문서에서 탭·지역을 다시 선택해
한 번 재시도한다. 인증 거부·429·차단·파싱 오류는 그대로 실패한다. 아래 과거 설명 중
검색 응답만 재시도한다는 제한은 이 절로 대체한다.

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

기본 `OpinetBrowserThrottle`은 화면 조작 사이에 0.05~0.15초의 무작위 대기를
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
