import asyncio

import httpx
import pytest

from opinet import AsyncOpinetClient, OpinetClient, ProductCode, SortOrder
from opinet.exceptions import OpinetAuthError, OpinetInvalidParameterError


def test_async_client_fetches_area_codes(load_fixture, mock_opinet):
    mock_opinet.add("areaCode.do", json=load_fixture("area_code_sido_01.json"))

    async def run():
        async with AsyncOpinetClient(api_key="test-key", retry_backoff=0) as client:
            rows = await client.get_area_codes("01")
            assert client.closed is False
            return rows, client

    rows, client = asyncio.run(run())

    assert client.closed is True
    assert rows[1].code == "0113"
    assert mock_opinet.query()["certkey"] == ["test-key"]
    assert mock_opinet.query()["area"] == ["01"]


def test_opinet_client_aio_factory_fetches_lowest_prices(load_fixture, mock_opinet):
    mock_opinet.add("lowTop10.do", json=load_fixture("low_top10_B027.json"))

    async def run():
        async with OpinetClient.aio(api_key="test-key", retry_backoff=0) as client:
            return await client.get_lowest_price_top20(ProductCode.GASOLINE, cnt=2, area="01")

    rows = asyncio.run(run())

    assert len(rows) == 2
    assert rows[0].provider_station_id == "A0013150"


def test_async_client_fetches_average_around_and_detail(load_fixture, mock_opinet):
    mock_opinet.add("avgAllPrice.do", json=load_fixture("avg_all_price.json"))
    mock_opinet.add("aroundAll.do", json=load_fixture("around_all_gangnam.json"))
    mock_opinet.add("detailById.do", json=load_fixture("detail_by_id_A0010207.json"))

    async def run():
        async with AsyncOpinetClient(api_key="test-key", retry_backoff=0) as client:
            averages = await client.get_national_average_price()
            nearby = await client.search_stations_around(
                katec_x=314871.8,
                katec_y=544012.0,
                radius_m=1000,
                prodcd=ProductCode.GASOLINE,
                sort=SortOrder.DISTANCE,
            )
            detail = await client.get_station_detail("A0010207")
            return averages, nearby, detail

    averages, nearby, detail = asyncio.run(run())

    assert averages[0].provider_product_code == "B034"
    assert nearby[0].provider_station_id == "A0010207"
    assert detail.provider_station_id == "A0010207"
    assert mock_opinet.query(1)["sort"] == ["2"]
    assert mock_opinet.query(2)["id"] == ["A0010207"]


def test_async_client_retries_server_errors(load_fixture, mock_opinet):
    route = mock_opinet.add("areaCode.do", body="server down", status=500)
    route.mock(
        side_effect=[
            httpx.Response(500, text="server down"),
            httpx.Response(200, json=load_fixture("area_code_root.json")),
        ]
    )

    async def run():
        async with AsyncOpinetClient(api_key="test-key", retry_backoff=0, max_retries=1) as client:
            return await client.get_area_codes()

    rows = asyncio.run(run())

    assert rows[0].code == "01"
    assert len(mock_opinet.calls) == 2


def test_async_client_preserves_validation_and_auth_errors(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPINET_API_KEY", raising=False)
    client = AsyncOpinetClient(retry_backoff=0)

    async def missing_key():
        await client.get_area_codes()

    with pytest.raises(OpinetAuthError):
        asyncio.run(missing_key())

    async def invalid_param():
        async with AsyncOpinetClient(api_key="test-key", retry_backoff=0) as async_client:
            await async_client.get_lowest_price_top20(
                ProductCode.GASOLINE,
                cnt=0,
            )

    with pytest.raises(OpinetInvalidParameterError):
        asyncio.run(invalid_param())
