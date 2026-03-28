"""투자 분석 + 관심종목 라우터

8개 엔드포인트:
- GET    /api/analysis/stock/{ticker}            기본적 분석
- GET    /api/analysis/stock/{ticker}/technical   기술적 분석
- GET    /api/analysis/stock/{ticker}/signals     매매 시그널
- POST   /api/analysis/simulate                   시뮬레이션 (DCA/포트폴리오/시나리오)
- GET    /api/analysis/watchlist                   관심종목 목록
- POST   /api/analysis/watchlist                   관심종목 추가
- PUT    /api/analysis/watchlist/{id}              관심종목 수정
- DELETE /api/analysis/watchlist/{id}              관심종목 삭제
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rate_limit import limiter
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.schemas.analysis import (
    FundamentalAnalysisResponse,
    MarketType,
    SimulationRequest,
    SimulationResponse,
    TechnicalAnalysisResponse,
    TradingSignalsResponse,
    WatchlistCreate,
    WatchlistResponse,
    WatchlistUpdate,
)
from app.services.security_service import AccessAction, log_access
from app.services.stock_analysis_service import (
    StockAnalysisError,
    get_fundamental_analysis,
    get_technical_analysis,
    get_trading_signals,
)
from app.services.simulation_service import SimulationError, run_simulation
from app.services.watchlist_service import (
    WatchlistDuplicateError,
    WatchlistNotFoundError,
    create_watchlist,
    delete_watchlist,
    list_watchlist,
    update_watchlist,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["투자 분석"])


# ──────────────────────────────────────────────
# 종목 분석 엔드포인트
# ──────────────────────────────────────────────

@router.get("/stock/{ticker}", response_model=FundamentalAnalysisResponse)
async def fundamental_analysis(
    ticker: str,
    request: Request,
    market: MarketType = Query(default=MarketType.KRX),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """기본적 분석: PER, PBR, ROE, EPS, 적정가, 평가 시그널."""
    try:
        result = await get_fundamental_analysis(ticker, market.value)
    except StockAnalysisError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None

    try:
        await log_access(db, user.id, AccessAction.ANALYSIS_VIEW, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("ANALYSIS_VIEW access logging failed", exc_info=True)

    return result


@router.get("/stock/{ticker}/technical", response_model=TechnicalAnalysisResponse)
async def technical_analysis(
    ticker: str,
    request: Request,
    market: MarketType = Query(default=MarketType.KRX),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """기술적 분석: RSI, MACD, 볼린저밴드, SMA, 지지/저항선."""
    try:
        result = await get_technical_analysis(ticker, market.value)
    except StockAnalysisError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None

    try:
        await log_access(db, user.id, AccessAction.ANALYSIS_VIEW, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("ANALYSIS_VIEW access logging failed", exc_info=True)

    return result


@router.get("/stock/{ticker}/signals", response_model=TradingSignalsResponse)
async def trading_signals(
    ticker: str,
    request: Request,
    market: MarketType = Query(default=MarketType.KRX),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """종합 매매 시그널: 매수/매도/관망, 신뢰도, 리스크 레벨."""
    try:
        result = await get_trading_signals(ticker, market.value)
    except StockAnalysisError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None

    try:
        await log_access(db, user.id, AccessAction.ANALYSIS_VIEW, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("ANALYSIS_VIEW access logging failed", exc_info=True)

    return result


# ──────────────────────────────────────────────
# 시뮬레이션
# ──────────────────────────────────────────────

@router.post("/simulate", response_model=SimulationResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("100/minute")
async def simulate(
    body: SimulationRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """시뮬레이션 실행 (DCA / 포트폴리오 / 시나리오)."""
    try:
        result = await run_simulation(db, user.id, body.params)
        await db.commit()
    except SimulationError as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from None

    try:
        await log_access(db, user.id, AccessAction.SIMULATION_RUN, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("SIMULATION_RUN access logging failed", exc_info=True)

    return result


# ──────────────────────────────────────────────
# 관심종목 CRUD
# ──────────────────────────────────────────────

@router.get("/watchlist", response_model=list[WatchlistResponse])
async def get_watchlist(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자의 관심종목 목록 조회."""
    items = await list_watchlist(db, user.id)

    try:
        await log_access(db, user.id, AccessAction.WATCHLIST_VIEW, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("WATCHLIST_VIEW access logging failed", exc_info=True)

    return items


@router.post(
    "/watchlist",
    response_model=WatchlistResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("100/minute")
async def add_watchlist(
    body: WatchlistCreate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """관심종목 추가."""
    try:
        result = await create_watchlist(db, user.id, body)
        await db.commit()
    except WatchlistDuplicateError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from None

    try:
        await log_access(db, user.id, AccessAction.WATCHLIST_CREATE, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("WATCHLIST_CREATE access logging failed", exc_info=True)

    return result


@router.put("/watchlist/{watchlist_id}", response_model=WatchlistResponse)
@limiter.limit("100/minute")
async def modify_watchlist(
    watchlist_id: UUID,
    body: WatchlistUpdate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """관심종목 수정."""
    try:
        result = await update_watchlist(db, user.id, watchlist_id, body)
        await db.commit()
    except WatchlistNotFoundError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from None

    try:
        await log_access(db, user.id, AccessAction.WATCHLIST_UPDATE, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("WATCHLIST_UPDATE access logging failed", exc_info=True)

    return result


@router.delete(
    "/watchlist/{watchlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("100/minute")
async def remove_watchlist(
    watchlist_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """관심종목 삭제."""
    try:
        await delete_watchlist(db, user.id, watchlist_id)
        await db.commit()
    except WatchlistNotFoundError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from None

    try:
        await log_access(db, user.id, AccessAction.WATCHLIST_DELETE, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("WATCHLIST_DELETE access logging failed", exc_info=True)
