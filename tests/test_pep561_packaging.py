from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import venv
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYKRTOUR_ROOT = PROJECT_ROOT.parent / "pykrtour"


def _run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


@pytest.fixture(scope="session")
def built_distributions(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    dist_dir = tmp_path_factory.mktemp("opinet-dist")
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            "--sdist",
            "--outdir",
            str(dist_dir),
        ],
        cwd=PROJECT_ROOT,
    )
    return {
        "wheel": next(dist_dir.glob("opinet-*.whl")),
        "sdist": next(dist_dir.glob("opinet-*.tar.gz")),
    }


def test_py_typed_is_in_built_distributions(built_distributions: dict[str, Path]) -> None:
    with zipfile.ZipFile(built_distributions["wheel"]) as wheel:
        assert "opinet/py.typed" in wheel.namelist()

    with tarfile.open(built_distributions["sdist"], "r:gz") as sdist:
        assert any(name.endswith("/opinet/py.typed") for name in sdist.getnames())


@pytest.mark.parametrize("dist_kind", ["wheel", "sdist"])
def test_built_distribution_install_import_and_downstream_mypy(
    built_distributions: dict[str, Path],
    tmp_path: Path,
    dist_kind: str,
) -> None:
    venv_dir = tmp_path / f"venv-{dist_kind}"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(venv_dir)
    python = _venv_python(venv_dir)

    if PYKRTOUR_ROOT.exists():
        _run([str(python), "-m", "pip", "install", "--no-deps", str(PYKRTOUR_ROOT)], cwd=tmp_path)

    install_args = [str(python), "-m", "pip", "install", "--no-deps"]
    if dist_kind == "sdist":
        install_args.append("--no-build-isolation")
    _run([*install_args, str(built_distributions[dist_kind])], cwd=tmp_path)

    import_smoke = tmp_path / f"import_smoke_{dist_kind}.py"
    import_smoke.write_text(
        """
from datetime import date, time

import opinet
import opinet.normalized
from pykrtour import KatecPoint, PlaceCoordinate
from opinet import (
    FuelType,
    NormalizedFuelAverage,
    NormalizedFuelStationDetail,
    NormalizedFuelStationDetailPrice,
    StationType,
)

record = NormalizedFuelAverage(
    provider_endpoint="avgAllPrice.do",
    provider_product_code="B027",
    provider_product_name="gasoline",
    fuel_type=FuelType.GASOLINE,
    trade_date=date(2025, 7, 23),
    price=1667.33,
    diff=-0.23,
    raw={"PRICE": "1667.33"},
)
price = NormalizedFuelStationDetailPrice(
    provider_endpoint="detailById.do",
    provider_station_id="A0010207",
    provider_station_name="SK station",
    provider_product_code="B027",
    fuel_type=FuelType.GASOLINE,
    price=1745.0,
    trade_date=date(2025, 7, 23),
    trade_time=time(14, 56, 18),
    raw={"PRICE": "1745"},
)
detail = NormalizedFuelStationDetail(
    provider_endpoint="detailById.do",
    provider_station_id="A0010207",
    provider_station_name="SK station",
    brand_code="SKE",
    sub_brand_code=None,
    station_type=StationType.GAS_STATION,
    sigun_code="0113",
    address_jibun="서울 강남구 역삼동 834-47",
    address_road="서울 강남구 역삼로 142",
    tel="02-562-4855",
    coordinate=PlaceCoordinate(lon=127.0381, lat=37.5006),
    katec_coordinate=KatecPoint(314871.8, 544012.0),
    katec_x=314871.8,
    katec_y=544012.0,
    lon=127.0381,
    lat=37.5006,
    has_maintenance=True,
    has_carwash=True,
    has_cvs=False,
    is_kpetro=False,
    prices=(price,),
    raw={"UNI_ID": "A0010207"},
)
assert opinet.normalized.NormalizedFuelAverage is NormalizedFuelAverage
assert opinet.normalized.NormalizedFuelStationDetail is NormalizedFuelStationDetail
assert record.provider == "opinet"
assert detail.prices[0].provider_product_code == "B027"
assert record.model_dump(mode="json")["trade_date"] == "2025-07-23"
""".lstrip(),
        encoding="utf-8",
    )
    _run([str(python), str(import_smoke)], cwd=tmp_path)

    downstream = tmp_path / f"downstream_mypy_{dist_kind}.py"
    downstream.write_text(
        """
from datetime import date, time

from pykrtour import KatecPoint, PlaceCoordinate
from opinet import (
    FuelType,
    NormalizedFuelAverage,
    NormalizedFuelStationDetail,
    NormalizedFuelStationDetailPrice,
    StationType,
)
from opinet.normalized import to_json_safe_raw

avg = NormalizedFuelAverage(
    provider_endpoint="avgAllPrice.do",
    provider_product_code="B027",
    provider_product_name="gasoline",
    fuel_type=FuelType.GASOLINE,
    trade_date=date(2025, 7, 23),
    price=1667.33,
    diff=-0.23,
    raw={"PRICE": "1667.33"},
)
price_row = NormalizedFuelStationDetailPrice(
    provider_endpoint="detailById.do",
    provider_station_id="A0010207",
    provider_station_name="SK station",
    provider_product_code="B027",
    fuel_type=FuelType.GASOLINE,
    price=1745.0,
    trade_date=date(2025, 7, 23),
    trade_time=time(14, 56, 18),
    raw={"PRICE": "1745"},
)
detail = NormalizedFuelStationDetail(
    provider_endpoint="detailById.do",
    provider_station_id="A0010207",
    provider_station_name="SK station",
    brand_code="SKE",
    sub_brand_code=None,
    station_type=StationType.GAS_STATION,
    sigun_code="0113",
    address_jibun="서울 강남구 역삼동 834-47",
    address_road="서울 강남구 역삼로 142",
    tel="02-562-4855",
    coordinate=PlaceCoordinate(lon=127.0381, lat=37.5006),
    katec_coordinate=KatecPoint(314871.8, 544012.0),
    katec_x=314871.8,
    katec_y=544012.0,
    lon=127.0381,
    lat=37.5006,
    has_maintenance=True,
    has_carwash=True,
    has_cvs=False,
    is_kpetro=False,
    prices=(price_row,),
    raw={"UNI_ID": "A0010207"},
)
payload = to_json_safe_raw(avg.raw)
price: float = avg.price
provider_code: str = avg.provider_product_code
detail_code: str = detail.prices[0].provider_product_code
reveal_type(avg)
reveal_type(detail)
reveal_type(price)
reveal_type(provider_code)
reveal_type(detail_code)
reveal_type(payload)
""".lstrip(),
        encoding="utf-8",
    )
    mypy = _run([str(python), "-m", "mypy", "--no-error-summary", str(downstream)], cwd=tmp_path)
    assert "opinet.normalized.NormalizedFuelAverage" in mypy.stdout
    assert "opinet.normalized.NormalizedFuelStationDetail" in mypy.stdout
    assert 'Revealed type is "float"' in mypy.stdout
    assert 'Revealed type is "str"' in mypy.stdout
