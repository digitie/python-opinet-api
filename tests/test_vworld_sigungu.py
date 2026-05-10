from __future__ import annotations

from typing import Any

import pytest

from opinet.exceptions import OpinetInvalidParameterError, OpinetNoDataError
from opinet.models import AreaCode
from opinet.vworld import OpinetSigunguBjdMapping, resolve_sigungu_bjd_code


class FakeOpinetClient:
    def __init__(self, children: dict[str, list[AreaCode]] | None = None) -> None:
        self.root = [AreaCode(code="01", name="서울"), AreaCode(code="10", name="부산")]
        self.children = children or {
            "01": [
                AreaCode(code="0102", name="중구"),
                AreaCode(code="0113", name="강남구"),
            ],
            "10": [AreaCode(code="1002", name="해운대구")],
        }

    def get_area_codes(self, sido: str | None = None) -> list[AreaCode]:
        if sido is None:
            return self.root
        return self.children.get(sido, [])


class FakeVworldClient:
    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, str, int]] = []

    def search_district(self, query: str, *, category: str = "L2", size: int = 10) -> dict[str, Any]:
        self.calls.append((query, category, size))
        return self.payloads.get(query, {"response": {"result": {"items": []}}})


def _payload(*items: dict[str, Any]) -> dict[str, Any]:
    return {"response": {"status": "OK", "result": {"items": list(items)}}}


def test_resolve_sigungu_bjd_code_with_full_vworld_title() -> None:
    vworld = FakeVworldClient(
        {
            "서울특별시 강남구": _payload(
                {
                    "id": "11680",
                    "title": "서울특별시 강남구",
                    "point": {"x": "127.0474864", "y": "37.51756978"},
                }
            )
        }
    )

    mapping = resolve_sigungu_bjd_code(
        "0113",
        opinet_client=FakeOpinetClient(),
        vworld_client=vworld,
    )

    assert isinstance(mapping, OpinetSigunguBjdMapping)
    assert mapping.opinet_sigungu_code == "0113"
    assert mapping.opinet_sigungu_name == "강남구"
    assert mapping.bjd_sigungu_code == "11680"
    assert mapping.bjd_sido_code == "11"
    assert mapping.vworld_query == "서울특별시 강남구"
    assert vworld.calls == [("서울특별시 강남구", "L2", 10)]


def test_resolve_sigungu_bjd_code_filters_ambiguous_districts_by_sido_prefix() -> None:
    vworld = FakeVworldClient(
        {
            "서울특별시 중구": _payload(
                {"id": "26110", "title": "부산광역시 중구"},
                {"id": "11140", "title": "서울특별시 중구"},
            )
        }
    )

    mapping = resolve_sigungu_bjd_code(
        "0102",
        opinet_client=FakeOpinetClient(),
        vworld_client=vworld,
    )

    assert mapping.bjd_sigungu_code == "11140"
    assert mapping.vworld_title == "서울특별시 중구"


def test_resolve_sigungu_bjd_code_rejects_non_sigungu_code() -> None:
    with pytest.raises(OpinetInvalidParameterError):
        resolve_sigungu_bjd_code(
            "01",
            opinet_client=FakeOpinetClient(),
            vworld_client=FakeVworldClient({}),
        )


def test_resolve_sigungu_bjd_code_raises_when_opinet_area_is_missing() -> None:
    with pytest.raises(OpinetNoDataError):
        resolve_sigungu_bjd_code(
            "0113",
            opinet_client=FakeOpinetClient(children={"01": []}),
            vworld_client=FakeVworldClient({}),
        )
