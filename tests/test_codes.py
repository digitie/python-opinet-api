import pytest

from opinet.codes import (
    BJD_LEGACY_TO_NEW,
    OPINET_TO_BJD,
    BrandCode,
    bjd_sido_to_opinet,
    is_alddle,
    opinet_sido_to_bjd,
)
from opinet.exceptions import OpinetInvalidParameterError


def test_all_17_sidos_mapped():
    assert len(OPINET_TO_BJD) == 17
    assert set(OPINET_TO_BJD) == {
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
    }
    assert BJD_LEGACY_TO_NEW == {"42": "51", "45": "52"}


@pytest.mark.parametrize(
    ("opinet", "bjd"),
    [
        ("01", "11"),
        ("02", "41"),
        ("10", "26"),
        ("11", "50"),
        ("14", "27"),
        ("19", "36"),
    ],
)
def test_sido_roundtrip(opinet, bjd):
    assert opinet_sido_to_bjd(opinet) == bjd
    assert bjd_sido_to_opinet(bjd) == opinet


def test_special_self_governing_new_codes():
    assert bjd_sido_to_opinet("51") == "03"
    assert bjd_sido_to_opinet("52") == "06"


@pytest.mark.parametrize("code", ["12", "13", "20", "99", "1", "001"])
def test_unknown_opinet_code(code):
    with pytest.raises(OpinetInvalidParameterError):
        opinet_sido_to_bjd(code)


@pytest.mark.parametrize("code", ["99", "00", "1"])
def test_unknown_bjd_code(code):
    with pytest.raises(OpinetInvalidParameterError):
        bjd_sido_to_opinet(code)


@pytest.mark.parametrize("brand", [BrandCode.RTO, BrandCode.RTE, BrandCode.RTX, BrandCode.NHO, "RTE"])
def test_is_alddle_true(brand):
    assert is_alddle(brand) is True


@pytest.mark.parametrize("brand", [BrandCode.SKE, "SKE", "UNKNOWN", None])
def test_is_alddle_false(brand):
    assert is_alddle(brand) is False
