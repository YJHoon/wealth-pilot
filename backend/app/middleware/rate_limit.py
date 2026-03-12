"""Rate Limiter 인스턴스 — 순환 import 방지를 위해 별도 모듈로 분리"""

from starlette.requests import Request

from slowapi import Limiter
from slowapi.util import get_remote_address


def _user_or_ip_key(request: Request) -> str:
    """인증된 요청은 user_id, 미인증 요청은 IP로 rate limit 키 결정."""
    # get_current_user 의존성이 request.state.user_id를 설정한 경우 사용
    user_id = getattr(request.state, "rate_limit_user_id", None)
    if user_id:
        return str(user_id)
    return get_remote_address(request)


limiter = Limiter(key_func=_user_or_ip_key, default_limits=["100/minute"])
