import pytest

from opinet.coords import katec_to_wgs84, validate_katec_xy, wgs84_to_katec


def test_wgs84_to_katec_known_gangnam_point():
    x, y = wgs84_to_katec(127.0276, 37.4979)

    assert x == pytest.approx(314213.3092)
    assert y == pytest.approx(544413.5797)


def test_katec_to_wgs84_known_station_point():
    lon, lat = katec_to_wgs84(314871.8, 544012.0)

    assert 127.02 < lon < 127.06
    assert 37.49 < lat < 37.51


def test_coordinate_roundtrip():
    lon, lat = 127.0276, 37.4979

    x, y = wgs84_to_katec(lon, lat)
    new_lon, new_lat = katec_to_wgs84(x, y)

    assert new_lon == pytest.approx(lon, abs=1e-5)
    assert new_lat == pytest.approx(lat, abs=1e-5)


@pytest.mark.parametrize(
    ("lon", "lat"),
    [
        (float("nan"), 37.5),
        (127.0, float("inf")),
        (181.0, 37.5),
        (127.0, 91.0),
    ],
)
def test_wgs84_validation_errors(lon, lat):
    with pytest.raises(ValueError):
        wgs84_to_katec(lon, lat)


def test_katec_validation_errors():
    with pytest.raises(ValueError):
        validate_katec_xy(float("inf"), 540000.0)
