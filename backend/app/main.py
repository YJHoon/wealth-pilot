from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import engine
from app.middleware.rate_limit import limiter
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import assets, auth, groups


# Sentry 초기화 (DSN이 설정된 경우에만)
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        traces_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작: DB 연결 확인
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)
    yield
    # 종료: 엔진 정리
    await engine.dispose()


# Rate Limiter 설정 (인스턴스는 middleware/rate_limit.py에서 import)

app = FastAPI(
    title="WealthPilot API",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Rate Limit 초과 핸들러
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 미들웨어
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 보안 헤더 미들웨어
app.add_middleware(SecurityHeadersMiddleware)


# 라우터 등록
app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(groups.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.env}
