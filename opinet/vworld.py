"""pyvworld를 활용한 오피넷 지역 코드 보강 helper."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from .codes import BJD_LEGACY_TO_NEW, opinet_sido_to_bjd
from .exceptions import OpinetInvalidParameterError, OpinetNoDataError, OpinetServerError
from .models import AreaCode


class _OpinetAreaClient(Protocol):
    def get_area_codes(self, sido: str | None = None) -> list[AreaCode]: ...


class _VworldDistrictClient(Protocol):
    def search_district(
        self,
        query: str,
        *,
        category: str = "L2",
        size: int = 10,
    ) -> Mapping[str, Any]: ...


OPINET_SIDO_VWORLD_NAMES: dict[str, tuple[str, ...]] = {
    "01": ("서울특별시", "서울"),
    "02": ("경기도", "경기"),
    "03": ("강원특별자치도", "강원도", "강원"),
    "04": ("충청북도", "충북"),
    "05": ("충청남도", "충남"),
    "06": ("전북특별자치도", "전라북도", "전북"),
    "07": ("전라남도", "전남"),
    "08": ("경상북도", "경북"),
    "09": ("경상남도", "경남"),
    "10": ("부산광역시", "부산"),
    "11": ("제주특별자치도", "제주"),
    "14": ("대구광역시", "대구"),
    "15": ("인천광역시", "인천"),
    "16": ("광주광역시", "광주"),
    "17": ("대전광역시", "대전"),
    "18": ("울산광역시", "울산"),
    "19": ("세종특별자치시", "세종"),
}


@dataclass(frozen=True, slots=True)
class OpinetSigunguBjdMapping:
    """오피넷 4자리 시군구 코드와 VWorld 법정동 시군구 코드의 명시 매핑."""

    opinet_sigungu_code: str
    opinet_sigungu_name: str
    opinet_sido_code: str
    opinet_sido_name: str
    bjd_sigungu_code: str
    vworld_title: str
    vworld_query: str
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.bjd_sigungu_code) != 5 or not self.bjd_sigungu_code.isdigit():
            raise ValueError("bjd_sigungu_code must be a 5-digit code")
        object.__setattr__(self, "raw", MappingProxyType(dict(self.raw)))

    @property
    def bjd_sido_code(self) -> str:
        """법정동 시도 코드 2자리 접두어를 반환한다."""

        return self.bjd_sigungu_code[:2]


def _validate_sigungu_code(sigungu_code: str) -> str:
    if len(sigungu_code) != 4 or not sigungu_code.isdigit():
        raise OpinetInvalidParameterError("sigungu_code must be a 4-digit Opinet sigungu code")
    opinet_sido_to_bjd(sigungu_code[:2])
    return sigungu_code


def _find_area(areas: Sequence[AreaCode], code: str) -> AreaCode | None:
    for area in areas:
        if area.code == code:
            return area
    return None


def _vworld_queries(sido_code: str, opinet_sido_name: str, sigungu_name: str) -> list[str]:
    names = list(OPINET_SIDO_VWORLD_NAMES.get(sido_code, ()))
    if opinet_sido_name and opinet_sido_name not in names:
        names.append(opinet_sido_name)

    queries: list[str] = []
    for sido_name in names:
        query = f"{sido_name} {sigungu_name}".strip()
        if query not in queries:
            queries.append(query)
    if sigungu_name not in queries:
        queries.append(sigungu_name)
    return queries


def _acceptable_bjd_sido_prefixes(opinet_sido_code: str) -> set[str]:
    prefix = opinet_sido_to_bjd(opinet_sido_code)
    return {prefix, BJD_LEGACY_TO_NEW.get(prefix, prefix)}


def _response_items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    response = payload.get("response")
    if not isinstance(response, Mapping):
        raise OpinetServerError("VWorld district response must contain a response object")
    result = response.get("result")
    if not isinstance(result, Mapping):
        return []
    items = result.get("items")
    if items is None:
        return []
    if isinstance(items, Mapping):
        return [items]
    if isinstance(items, list) and all(isinstance(item, Mapping) for item in items):
        return items
    raise OpinetServerError("VWorld district response items must be objects")


def _is_vworld_no_data(exc: Exception) -> bool:
    return exc.__class__.__name__ == "VworldNoDataError"


def _pick_sigungu_item(
    items: Sequence[Mapping[str, Any]],
    *,
    expected_prefixes: set[str],
    expected_titles: set[str],
    sigungu_name: str,
) -> Mapping[str, Any] | None:
    candidates: list[Mapping[str, Any]] = []
    for item in items:
        code = str(item.get("id", "")).strip()
        if len(code) == 5 and code.isdigit() and code[:2] in expected_prefixes:
            candidates.append(item)

    if not candidates:
        return None

    for item in candidates:
        title = str(item.get("title", "")).strip()
        if title in expected_titles:
            return item

    suffix = f" {sigungu_name}"
    for item in candidates:
        title = str(item.get("title", "")).strip()
        if title == sigungu_name or title.endswith(suffix):
            return item

    if len(candidates) == 1:
        return candidates[0]

    raise OpinetServerError(f"VWorld returned multiple sigungu candidates for {sigungu_name!r}")


def resolve_sigungu_bjd_code(
    sigungu_code: str,
    *,
    opinet_client: _OpinetAreaClient,
    vworld_client: _VworldDistrictClient,
) -> OpinetSigunguBjdMapping:
    """오피넷 4자리 시군구 코드를 VWorld의 5자리 법정동 시군구 코드로 해석한다.

    오피넷 `SIGUNCD`/`AREA_CD` 시군구 값은 법정동코드가 아니므로 코드 자체를
    산술 변환하지 않는다. 대신 `areaCode.do`에서 시도명과 시군구명을 얻고,
    `pyvworld.VworldClient.search_district(..., category="L2")` 결과의 5자리
    `id`를 명시적으로 매칭한다.
    """

    normalized_code = _validate_sigungu_code(sigungu_code)
    sido_code = normalized_code[:2]

    sido = _find_area(opinet_client.get_area_codes(), sido_code)
    if sido is None:
        raise OpinetNoDataError(f"Opinet sido code {sido_code!r} was not found")

    sigungu = _find_area(opinet_client.get_area_codes(sido_code), normalized_code)
    if sigungu is None:
        raise OpinetNoDataError(f"Opinet sigungu code {normalized_code!r} was not found")

    queries = _vworld_queries(sido_code, sido.name, sigungu.name)
    expected_prefixes = _acceptable_bjd_sido_prefixes(sido_code)
    expected_titles = {query for query in queries if query != sigungu.name}

    for query in queries:
        try:
            payload = vworld_client.search_district(query, category="L2", size=10)
        except Exception as exc:
            if _is_vworld_no_data(exc):
                continue
            raise

        item = _pick_sigungu_item(
            _response_items(payload),
            expected_prefixes=expected_prefixes,
            expected_titles=expected_titles,
            sigungu_name=sigungu.name,
        )
        if item is None:
            continue

        return OpinetSigunguBjdMapping(
            opinet_sigungu_code=normalized_code,
            opinet_sigungu_name=sigungu.name,
            opinet_sido_code=sido_code,
            opinet_sido_name=sido.name,
            bjd_sigungu_code=str(item["id"]).strip(),
            vworld_title=str(item.get("title", "")).strip(),
            vworld_query=query,
            raw=item,
        )

    raise OpinetNoDataError(f"VWorld district search did not resolve Opinet code {normalized_code!r}")
