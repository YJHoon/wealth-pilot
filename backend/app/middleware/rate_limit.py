"""Rate Limiter 인스턴스 — 순환 import 방지를 위해 별도 모듈로 분리"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
