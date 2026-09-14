"""전송 예산, 동시 진단, 취소, 소유권 및 오류 경계를 검증한다."""
import asyncio
import gc
import inspect
import traceback
import weakref
from types import MappingProxyType
from urllib.parse import quote

import httpx
import pytest

import opinet
from opinet import AsyncTokenBucket, OpinetClient
from opinet._http import AsyncHttpxTransport
from opinet.exceptions import OpinetAuthError, OpinetNetworkError, OpinetRateLimitError, OpinetServerError
from opinet.vworld import _cached_area_codes


class CountingBucket(AsyncTokenBucket):
    def __init__(self):
        super().__init__(10000)
        self.count = 0

    async def acquire(self):
        await super().acquire()
        self.count += 1


def test_async_only_exports():
    assert not hasattr(opinet, 'AsyncOpinetClient')
    assert not hasattr(opinet, 'SyncHttpxTransport')
    assert not hasattr(OpinetClient, 'aio')
    assert not hasattr(OpinetClient, 'close')
    assert inspect.iscoroutinefunction(OpinetClient.debug_fetch)
    assert inspect.isasyncgenfunction(OpinetClient.iter_stations_in_bbox)
    assert inspect.iscoroutinefunction(AsyncHttpxTransport.get)


async def test_shared_bucket_counts_debug_retry_and_redirect(load_fixture):
    budget = CountingBucket()
    seen = []

    async def handler(request):
        seen.append(str(request.url))
        if len(seen) == 1:
            return httpx.Response(503)
        if len(seen) == 2:
            return httpx.Response(302, headers={'Location': '/api/final.do'})
        return httpx.Response(200, json=load_fixture('area_code_root.json'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as session:
        async with OpinetClient('test-key', session=session, rate_limiter=budget, max_rps=float('nan'), retry_backoff=0) as first:
            async with OpinetClient('test-key', session=session, rate_limiter=budget) as second:
                assert len(await first.get_area_codes()) == 17
                assert (await second.debug_fetch('get_area_codes')).ok
                assert (await first.debug().get_area_codes()).ok
                assert budget.count == len(seen) == 5
        assert not session.is_closed
        with pytest.raises(RuntimeError, match='closed'):
            await first.get_area_codes()
        assert budget.count == 5


@pytest.mark.parametrize('status,error', [(401, OpinetAuthError), (403, OpinetAuthError), (429, OpinetRateLimitError)])
async def test_auth_and_quota_errors_do_not_retry(status, error):
    budget = CountingBucket()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status))) as session:
        async with OpinetClient('test-key', session=session, rate_limiter=budget, max_retries=3) as client:
            with pytest.raises(error):
                await client.get_area_codes()
    assert budget.count == 1


async def test_redirect_limit_keeps_transport_error_and_budget():
    budget = CountingBucket()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={'Location': '/api/loop'})), follow_redirects=True, max_redirects=1) as session:
        async with OpinetClient('test-key', session=session, rate_limiter=budget) as client:
            with pytest.raises(OpinetNetworkError):
                await client.get_area_codes()
    assert budget.count == 2


async def test_owned_session_closed_once_and_invalid_rate_never_allocates(monkeypatch, load_fixture):
    allocated = []
    def factory():
        session = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=load_fixture('area_code_root.json'))))
        allocated.append(session)
        return session
    monkeypatch.setattr('opinet._http._new_async_client', factory)
    with pytest.raises(ValueError):
        OpinetClient('test-key', max_rps=0)
    assert not allocated
    client = OpinetClient('test-key')
    assert not allocated
    async with client:
        await client.get_area_codes()
    await client.aclose()
    assert len(allocated) == 1 and allocated[0].is_closed
    with httpx.Client() as sync_session:
        with pytest.raises(TypeError, match='async'):
            OpinetClient('test-key', session=sync_session)


async def test_concurrent_debug_records_are_isolated_and_cancel_restores(load_fixture):
    entered = asyncio.Event()
    release = asyncio.Event()
    async def handler(request):
        if request.url.params.get('area') == '01':
            entered.set()
            await release.wait()
            return httpx.Response(200, json=load_fixture('area_code_sido_01.json'))
        return httpx.Response(200, json=load_fixture('area_code_root.json'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        async with OpinetClient('test-key', session=session) as client:
            first = asyncio.create_task(client.debug_fetch('get_area_codes', {'sido': '01'}))
            await entered.wait()
            root = await client.debug().get_area_codes()
            assert root.response['body']['RESULT']['OIL'][0]['AREA_CD'] == '01'
            assert 'area' not in root.request['query']
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert client._require_http()._calls.get() is None
            release.set()
            child = await client.debug_fetch('get_area_codes', {'sido': '01'})
            assert child.request['query']['area'] == '01'
            assert child.parsed[1].code == '0113'


async def test_debug_preserves_model_shapes_while_masking_key(load_fixture):
    key = 'synthetic/key+value'
    payload = load_fixture('detail_by_id_A0010207.json')
    rows = payload['RESULT']['OIL']
    row = rows[0] if isinstance(rows, list) else rows
    row['echo'] = key
    row['encoded'] = quote(key, safe='')
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as session:
        async with OpinetClient(key, session=session) as client:
            run = await client.debug_fetch('get_station_detail', {'uni_id': 'A0010207'})
            assert run.ok
            assert isinstance(run.parsed.prices, tuple)
            assert isinstance(run.parsed.raw, MappingProxyType)
            assert isinstance(run.processed.prices, tuple)
            assert key not in str(opinet.jsonable(run))
            assert quote(key, safe='') not in str(opinet.jsonable(run))
            assert row['echo'] == key


@pytest.mark.parametrize('method', ['public', 'debug', 'explicit_debug'])
async def test_key_echo_in_parser_errors_is_masked_after_classification(load_fixture, method):
    key = 'synthetic-parser-key'
    payload = load_fixture('avg_all_price.json')
    payload['RESULT']['OIL'][0]['PRICE'] = key
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as session:
        async with OpinetClient(key, session=session) as client:
            with pytest.raises(OpinetServerError) as caught:
                if method == 'public':
                    await client.get_national_average_price()
                elif method == 'debug':
                    await client.debug_fetch('get_national_average_price', raise_errors=True)
                else:
                    await client.debug().get_national_average_price(raise_errors=True)
            assert key not in str(caught.value)
            assert key not in ''.join(traceback.format_exception(caught.value))


async def test_failed_area_cache_does_not_retain_client():
    class FailingClient:
        async def get_area_codes(self, sido=None):
            raise OpinetNetworkError('offline')
    client = FailingClient()
    ref = weakref.ref(client)
    with pytest.raises(OpinetNetworkError):
        await _cached_area_codes(client)
    del client
    gc.collect()
    assert ref() is None
