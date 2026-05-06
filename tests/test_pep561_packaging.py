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

    install_args = [str(python), "-m", "pip", "install", "--no-deps"]
    if dist_kind == "sdist":
        install_args.append("--no-build-isolation")
    _run([*install_args, str(built_distributions[dist_kind])], cwd=tmp_path)

    import_smoke = tmp_path / f"import_smoke_{dist_kind}.py"
    import_smoke.write_text(
        """
from datetime import date

import opinet
import opinet.normalized
from opinet import FuelType, NormalizedFuelAverage

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
assert opinet.normalized.NormalizedFuelAverage is NormalizedFuelAverage
assert record.provider == "opinet"
assert record.model_dump(mode="json")["trade_date"] == "2025-07-23"
""".lstrip(),
        encoding="utf-8",
    )
    _run([str(python), str(import_smoke)], cwd=tmp_path)

    downstream = tmp_path / f"downstream_mypy_{dist_kind}.py"
    downstream.write_text(
        """
from datetime import date

from opinet import FuelType, NormalizedFuelAverage
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
payload = to_json_safe_raw(avg.raw)
price: float = avg.price
provider_code: str = avg.provider_product_code
reveal_type(avg)
reveal_type(price)
reveal_type(provider_code)
reveal_type(payload)
""".lstrip(),
        encoding="utf-8",
    )
    mypy = _run([str(python), "-m", "mypy", "--no-error-summary", str(downstream)], cwd=tmp_path)
    assert "opinet.normalized.NormalizedFuelAverage" in mypy.stdout
    assert 'Revealed type is "float"' in mypy.stdout
    assert 'Revealed type is "str"' in mypy.stdout
