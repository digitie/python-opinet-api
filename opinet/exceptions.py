"""오피넷 클라이언트 예외 계층."""


class OpinetError(Exception):
    """모든 오피넷 클라이언트 오류의 공통 기본 클래스."""


class OpinetAuthError(OpinetError):
    """인증 실패 또는 API 키 오류."""


class OpinetRateLimitError(OpinetError):
    """API 호출 한도 또는 호출 제한 초과."""


class OpinetInvalidParameterError(OpinetError):
    """HTTP 호출 전 클라이언트 파라미터 검증 실패."""


class OpinetNoDataError(OpinetError):
    """엄격한 빈 결과 처리에서 API가 빈 결과를 반환했을 때의 오류."""


class OpinetServerError(OpinetError):
    """API 응답이 예기치 않거나 파싱에 실패했을 때의 오류."""


class OpinetNetworkError(OpinetError):
    """오피넷 호출 중 발생한 네트워크 레벨 오류."""
