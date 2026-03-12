"""보안 헤더 미들웨어 — 모든 응답에 보안 헤더 추가"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Swagger/ReDoc 문서 경로 (비프로덕션 전용)
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

# API 전용 엄격 CSP
_STRICT_CSP = "default-src 'none'; frame-ancestors 'none'"

# Swagger UI가 작동하려면 script/style/img 허용 필요
_DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # 문서 경로는 완화된 CSP 적용 (비프로덕션에서만 docs_url이 활성화됨)
        if request.url.path in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = _DOCS_CSP
        else:
            response.headers["Content-Security-Policy"] = _STRICT_CSP

        return response
