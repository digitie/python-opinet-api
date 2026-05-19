import httpx
import pytest

from opinet import OpinetClient
from opinet.exceptions import OpinetAuthError, OpinetNetworkError, OpinetRateLimitError, OpinetServerError


def test_invalid_key_body_maps_to_auth(load_fixture, mock_opinet):
    mock_opinet.add("avgAllPrice.do", json=load_fixture("error_invalid_key.json"))
    client = OpinetClient(api_key="bad-key", retry_backoff=0)

    with pytest.raises(OpinetAuthError):
        client.get_national_average_price()


def test_limit_body_maps_to_rate_limit(load_fixture, mock_opinet):
    mock_opinet.add("avgAllPrice.do", json=load_fixture("error_rate_limit.json"))
    client = OpinetClient(api_key="test-key", retry_backoff=0)

    with pytest.raises(OpinetRateLimitError):
        client.get_national_average_price()


def test_401_and_403_map_to_auth(mock_opinet):
    for status in (401, 403):
        mock_opinet.reset()
        mock_opinet.add("avgAllPrice.do", body="no", status=status)
        client = OpinetClient(api_key="test-key", retry_backoff=0)
        with pytest.raises(OpinetAuthError):
            client.get_national_average_price()


def test_429_does_not_retry(mock_opinet):
    mock_opinet.add("avgAllPrice.do", body="limit", status=429)
    client = OpinetClient(api_key="test-key", retry_backoff=0, max_retries=2)

    with pytest.raises(OpinetRateLimitError):
        client.get_national_average_price()
    assert len(mock_opinet.calls) == 1


def test_5xx_retries_then_succeeds(load_fixture, mock_opinet):
    route = mock_opinet.add("avgAllPrice.do", body="server down", status=500)
    route.mock(side_effect=[
        httpx.Response(500, text="server down"),
        httpx.Response(502, text="still down"),
        httpx.Response(200, json=load_fixture("avg_all_price.json")),
    ])
    client = OpinetClient(api_key="test-key", retry_backoff=0, max_retries=2)

    rows = client.get_national_average_price()

    assert len(mock_opinet.calls) == 3
    assert rows[0].product_name == "고급휘발유"


def test_5xx_final_failure(mock_opinet):
    mock_opinet.add("avgAllPrice.do", body="server down", status=500)
    client = OpinetClient(api_key="test-key", retry_backoff=0, max_retries=0)

    with pytest.raises(OpinetServerError):
        client.get_national_average_price()


def test_network_error_retries_then_raises(mock_opinet):
    route = mock_opinet.add("avgAllPrice.do", body=httpx.ConnectError("offline"))
    route.mock(side_effect=[httpx.ConnectError("offline"), httpx.TimeoutException("slow")])
    client = OpinetClient(api_key="test-key", retry_backoff=0, max_retries=1)

    with pytest.raises(OpinetNetworkError):
        client.get_national_average_price()
    assert len(mock_opinet.calls) == 2


def test_json_parse_failure_maps_to_server_error(mock_opinet):
    mock_opinet.add("avgAllPrice.do", body="not json", content_type="text/plain")
    client = OpinetClient(api_key="test-key", retry_backoff=0)

    with pytest.raises(OpinetServerError):
        client.get_national_average_price()
