"""오피넷 공식 API 카탈로그 메타데이터."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Literal

SERVICE_KEY_URL = "https://www.opinet.co.kr/user/custapi/openApiNew.do"


@dataclass(frozen=True, slots=True)
class ApiParameter:
    """API 파라미터 설명."""

    name: str
    label: str
    required: bool
    description: str
    default: Any = None
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ApiCatalogItem:
    """디버그 UI와 문서가 함께 쓰는 API 카탈로그 항목."""

    function_name: str
    endpoint: str
    api_id: int
    dataset: str
    dataset_name: str
    method: Literal["GET"]
    summary: str
    response_model: str
    parameters: tuple[ApiParameter, ...]
    service_key_url: str = SERVICE_KEY_URL
    official: bool = True

    @property
    def display_name(self) -> str:
        """UI 선택 목록에 쓰기 좋은 데이터셋명 중심 label."""
        return f"{self.dataset_name} ({self.endpoint})"

    def to_dict(self) -> dict[str, Any]:
        """Streamlit `st.json`/`st.dataframe`에 바로 넣을 수 있는 dict로 변환한다."""
        return _dataclass_to_dict(self)


API_CATALOG: tuple[ApiCatalogItem, ...] = (
    ApiCatalogItem(
        function_name="get_national_average_price",
        endpoint="avgAllPrice.do",
        api_id=4,
        dataset="national_average_price",
        dataset_name="전국 주유소 평균가격",
        method="GET",
        summary="전국 평균 제품별 유가를 조회한다.",
        response_model="list[AvgPrice]",
        parameters=(),
    ),
    ApiCatalogItem(
        function_name="get_lowest_price_top20",
        endpoint="lowTop10.do",
        api_id=2,
        dataset="lowest_price_station",
        dataset_name="전국/지역별 최저가 주유소",
        method="GET",
        summary="제품과 지역 조건에 맞는 최저가 주유소 목록을 조회한다.",
        response_model="list[Station]",
        parameters=(
            ApiParameter(
                name="prodcd",
                label="제품 코드",
                required=True,
                description="B027/B034/D047/C004/K015 중 하나",
                allowed_values=("B027", "B034", "D047", "C004", "K015"),
            ),
            ApiParameter(
                name="cnt",
                label="결과 건수",
                required=False,
                description="1~20 사이의 결과 건수",
                default=10,
            ),
            ApiParameter(
                name="area",
                label="지역 코드",
                required=False,
                description="오피넷 시도 2자리 또는 시군구 4자리 코드",
            ),
        ),
    ),
    ApiCatalogItem(
        function_name="search_stations_around",
        endpoint="aroundAll.do",
        api_id=3,
        dataset="nearby_station_price",
        dataset_name="반경 내 주유소 가격",
        method="GET",
        summary="WGS84 또는 KATEC 좌표 반경 내 주유소 가격을 조회한다.",
        response_model="list[Station]",
        parameters=(
            ApiParameter(
                name="lon",
                label="WGS84 경도",
                required=False,
                description="lat과 함께 지정. KATEC 좌표와 둘 중 하나만 지정",
            ),
            ApiParameter(
                name="lat",
                label="WGS84 위도",
                required=False,
                description="lon과 함께 지정. KATEC 좌표와 둘 중 하나만 지정",
            ),
            ApiParameter(
                name="katec_x",
                label="KATEC 좌표",
                required=False,
                description="katec_y와 함께 지정. WGS84 좌표와 둘 중 하나만 지정",
            ),
            ApiParameter(
                name="katec_y",
                label="KATEC 좌표",
                required=False,
                description="katec_x와 함께 지정. WGS84 좌표와 둘 중 하나만 지정",
            ),
            ApiParameter(
                name="radius_m",
                label="검색 반경(m)",
                required=False,
                description="1~5000m",
                default=5000,
            ),
            ApiParameter(
                name="prodcd",
                label="제품 코드",
                required=False,
                description="B027/B034/D047/C004/K015 중 하나",
                default="B027",
                allowed_values=("B027", "B034", "D047", "C004", "K015"),
            ),
            ApiParameter(
                name="sort",
                label="정렬",
                required=False,
                description="1=가격순, 2=거리순",
                default="1",
                allowed_values=("1", "2"),
            ),
        ),
    ),
    ApiCatalogItem(
        function_name="get_station_detail",
        endpoint="detailById.do",
        api_id=1,
        dataset="station_detail",
        dataset_name="주유소 상세정보 및 제품별 가격",
        method="GET",
        summary="주유소 ID로 주소, 편의시설, 업종, 제품별 가격을 조회한다.",
        response_model="StationDetail",
        parameters=(
            ApiParameter(
                name="uni_id",
                label="주유소 ID",
                required=True,
                description="오피넷 UNI_ID",
            ),
        ),
    ),
    ApiCatalogItem(
        function_name="get_area_codes",
        endpoint="areaCode.do",
        api_id=5,
        dataset="area_code",
        dataset_name="오피넷 시도/시군구 코드",
        method="GET",
        summary="오피넷 시도 또는 시군구 코드 목록을 조회한다.",
        response_model="list[AreaCode]",
        parameters=(
            ApiParameter(
                name="sido",
                label="시도 코드",
                required=False,
                description="오피넷 시도 2자리 코드. 생략하면 시도 목록 반환",
            ),
        ),
    ),
)


def get_api_catalog() -> tuple[ApiCatalogItem, ...]:
    """공식 5개 API 카탈로그를 반환한다."""
    return API_CATALOG


def get_api_catalog_item(
    identifier: str | None = None,
    *,
    function_name: str | None = None,
    endpoint: str | None = None,
    dataset: str | None = None,
) -> ApiCatalogItem:
    """function, endpoint, dataset 중 하나로 카탈로그 항목을 찾는다."""
    candidates = [value for value in (identifier, function_name, endpoint, dataset) if value is not None]
    if not candidates:
        raise ValueError("one of identifier, function_name, endpoint, or dataset is required")

    for item in API_CATALOG:
        values = {item.function_name, item.endpoint, item.dataset, item.dataset_name}
        if any(candidate in values for candidate in candidates):
            return item
    raise KeyError(f"unknown Opinet API catalog item: {candidates[0]!r}")


def get_api_catalog_options() -> tuple[dict[str, str], ...]:
    """Streamlit selectbox 등에 바로 쓰기 좋은 label/value 목록을 반환한다."""
    return tuple(
        {
            "label": item.display_name,
            "value": item.function_name,
            "dataset": item.dataset,
            "dataset_name": item.dataset_name,
            "endpoint": item.endpoint,
        }
        for item in API_CATALOG
    )


def _dataclass_to_dict(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _dataclass_to_dict(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_dataclass_to_dict(item) for item in value]
    return value
