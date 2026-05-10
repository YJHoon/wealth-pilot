"""투자 분석 + 관심종목 + 원클릭 분석·매매 라우터

종목 분석/관심종목/시뮬레이션 + 원클릭 분석·매매(Advisory) Run.

원클릭 분석·매매 엔드포인트:
- POST   /api/analysis/runs                       run 생성 + 비동기 분석 시작
- GET    /api/analysis/runs                       사용자 이력 (페이징)
- GET    /api/analysis/runs/{id}                  진행/결과 조회 (폴링 대상)
- POST   /api/analysis/runs/{id}/decisions        종목별 approve/reject 일괄 저장
- POST   /api/analysis/runs/{id}/execute          승인 항목 발주 (TTL/2FA/장외 가드)
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.middleware.rate_limit import limiter
from app.dependencies.auth import get_current_active_user
from app.models.trading import (
    AnalysisItemAction,
    AnalysisItemDecision,
    AnalysisRun,
    AnalysisRunItem,
    AnalysisRunStatus,
    TradingAccount,
    TradingMode,
)
from app.models.user import User
from app.schemas.advisory import (
    AnalysisRunListResponse,
    AnalysisRunResponse,
    DecisionsRequest,
    ExecuteItemResult,
    ExecuteRequest,
    ExecuteResponse,
    RunCreateRequest,
    run_to_response,
    run_to_summary,
)
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
from app.services.advisory_candidate import build_candidate_pool
from app.services.advisory_executor import execute_approved_items
from app.services.advisory_run import fail_run, run_analysis
from app.services.crypto_service import (
    decrypt_value,
    encrypt_decimal,
    encrypt_value,
)
from app.services.kis_client import KISClient, KISClientError
from app.services.llm_advisor import PortfolioContext
from app.services.security_service import AccessAction, log_access
from app.services.stock_analysis_service import (
    StockAnalysisError,
    get_fundamental_analysis,
    get_technical_analysis,
    get_trading_signals,
)
from app.services.simulation_service import SimulationError, run_simulation
from app.services.totp_service import decrypt_totp_secret, verify_totp_code
from app.services.watchlist_service import (
    WatchlistDuplicateError,
    WatchlistNotFoundError,
    create_watchlist,
    delete_watchlist,
    list_watchlist,
    update_watchlist,
)
from app.tasks.trading_cycle import _is_market_hours

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["투자 분석"])


# ──────────────────────────────────────────────
# 종목 분석 엔드포인트
# ──────────────────────────────────────────────

@router.get("/stock/{ticker}", response_model=FundamentalAnalysisResponse)
@limiter.limit("100/minute")
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
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("ANALYSIS_VIEW access logging failed", exc_info=True)

    return result


@router.get("/stock/{ticker}/technical", response_model=TechnicalAnalysisResponse)
@limiter.limit("100/minute")
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
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("ANALYSIS_VIEW access logging failed", exc_info=True)

    return result


@router.get("/stock/{ticker}/signals", response_model=TradingSignalsResponse)
@limiter.limit("100/minute")
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
    except SQLAlchemyError:
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
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("SIMULATION_RUN access logging failed", exc_info=True)

    return result


# ──────────────────────────────────────────────
# 관심종목 CRUD
# ──────────────────────────────────────────────

@router.get("/watchlist", response_model=list[WatchlistResponse])
@limiter.limit("100/minute")
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
    except SQLAlchemyError:
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
        raise HTTPException(status_code=409, detail=str(e)) from None

    try:
        await log_access(db, user.id, AccessAction.WATCHLIST_CREATE, request)
        await db.commit()
    except SQLAlchemyError:
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
    except SQLAlchemyError:
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
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("WATCHLIST_DELETE access logging failed", exc_info=True)


# ──────────────────────────────────────────────
# 원클릭 분석·매매 (Advisory) 엔드포인트
# ──────────────────────────────────────────────

# 진행 중으로 간주해 새 run 생성을 차단할 상태들.
# READY 는 사용자가 결과 검토/재분석할 수 있어야 하므로 락 대상에서 제외.
_RUN_IN_PROGRESS_STATES = (
    AnalysisRunStatus.PENDING,
    AnalysisRunStatus.ANALYZING,
    AnalysisRunStatus.EXECUTING,
)

# 1회 run 종목 수 상한 (LLM 호출 비용 가드 — 워크플랜 §4)
ADVISORY_MAX_CANDIDATES = 20


async def _load_run_for_user(
    db: AsyncSession, run_id: UUID, user_id: UUID,
) -> AnalysisRun:
    """소유권 검증 포함 run 로드. 없거나 다른 사용자면 404."""
    result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == run_id,
            AnalysisRun.user_id == user_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="분석 run 을 찾을 수 없습니다.")
    return run


async def _load_account_for_user(
    db: AsyncSession, account_id: UUID, user_id: UUID,
) -> TradingAccount:
    """소유권 검증 포함 계좌 로드."""
    result = await db.execute(
        select(TradingAccount).where(
            TradingAccount.id == account_id,
            TradingAccount.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="계좌를 찾을 수 없습니다.")
    if not account.is_active:
        raise HTTPException(status_code=409, detail="비활성화된 계좌입니다.")
    return account


async def _list_run_items(
    db: AsyncSession, run_id: UUID,
) -> list[AnalysisRunItem]:
    rows = await db.execute(
        select(AnalysisRunItem)
        .where(AnalysisRunItem.run_id == run_id)
        .order_by(AnalysisRunItem.created_at)
    )
    return list(rows.scalars().all())


def _build_kis_client(account: TradingAccount) -> KISClient:
    creds = settings.kis_credentials(account.mode.value)
    return KISClient(
        app_key=creds["app_key"],
        app_secret=creds["app_secret"],
        account_number=creds["account_number"],
        account_product_code=creds["account_product_code"],
        mode=account.mode,
        access_token=decrypt_value(account.access_token)
        if account.access_token else None,
        token_expires_at=account.token_expires_at,
    )


async def _persist_kis_token(
    db: AsyncSession, account: TradingAccount, kis: KISClient,
) -> None:
    """KIS 호출 후 갱신된 토큰을 계좌에 반영. trading.py와 동일 규약."""
    new_token = kis.access_token
    if not new_token:
        return
    old_token = (
        decrypt_value(account.access_token) if account.access_token else None
    )
    if (
        new_token == old_token
        and account.token_expires_at == kis.token_expires_at
    ):
        return
    account.access_token = encrypt_value(new_token)
    account.token_expires_at = kis.token_expires_at


async def _run_analysis_background(run_id: UUID) -> None:
    """BackgroundTasks 진입점 — 별도 세션/KIS 클라이언트로 분석 실행.

    실패 시 fail_run 으로 FAILED 마킹. 정상 종료 시 commit 책임도 여기.
    """
    async with AsyncSessionLocal() as db:
        run = (
            await db.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            logger.error("background analysis: run not found id=%s", run_id)
            return
        account = (
            await db.execute(
                select(TradingAccount).where(TradingAccount.id == run.account_id)
            )
        ).scalar_one_or_none()
        if account is None:
            await fail_run(db, run.id, "계좌를 찾을 수 없습니다.")
            await db.commit()
            return

        kis = _build_kis_client(account)
        try:
            try:
                balance = await kis.get_balance()
            except KISClientError as e:
                await fail_run(db, run.id, f"잔고 조회 실패: {e}")
                await db.commit()
                return

            available_cash: Decimal = balance["cash"]
            total_eval: Decimal = balance["total_eval"] + available_cash
            holdings = [
                {
                    "ticker": h["ticker"],
                    "ticker_name": h.get("name", ""),
                    "quantity": str(h["quantity"]),
                    "avg_buy_price": str(h["avg_price"]),
                }
                for h in balance.get("holdings", [])
            ]
            portfolio = PortfolioContext(
                cash=available_cash,
                total_eval=total_eval,
                holdings=holdings,
            )

            try:
                pool = await build_candidate_pool(
                    db,
                    user_id=run.user_id,
                    account_id=run.account_id,
                    options=run.candidate_pool_options or {},
                    available_cash=available_cash,
                    total_eval=total_eval,
                    max_candidates=ADVISORY_MAX_CANDIDATES,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("build_candidate_pool failed for run=%s", run.id)
                await fail_run(db, run.id, f"후보풀 생성 실패: {type(e).__name__}")
                await db.commit()
                return

            async def _price_fetcher(ticker: str) -> list[dict]:
                return await kis.get_price_history(ticker, period="D", count=60)

            try:
                await run_analysis(
                    db,
                    run,
                    candidates=pool,
                    portfolio=portfolio,
                    price_fetcher=_price_fetcher,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("run_analysis failed for run=%s", run.id)
                await fail_run(db, run.id, f"분석 실패: {type(e).__name__}")
                await db.commit()
                return

            # KIS 토큰 갱신 반영
            await _persist_kis_token(db, account, kis)
            await db.commit()
        finally:
            await kis.close()


@router.post(
    "/runs",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("100/minute")
async def create_analysis_run(
    body: RunCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """원클릭 분석 run 생성 + 비동기 분석 시작.

    사용자당 진행 중(`pending|analyzing|executing`) run 1개 락.
    분석은 BackgroundTasks 로 실행되고, 결과는 GET /runs/{id} 폴링으로 확인.
    """
    # 1) 사용자당 진행 중 run 락
    busy = await db.execute(
        select(AnalysisRun.id).where(
            AnalysisRun.user_id == user.id,
            AnalysisRun.status.in_(_RUN_IN_PROGRESS_STATES),
        ).limit(1)
    )
    if busy.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="이미 진행 중인 분석이 있습니다. 완료 후 재시도하세요.",
        )

    # 2) 계좌 소유권 검증
    account = await _load_account_for_user(db, body.account_id, user.id)
    if account.mode != body.mode:
        raise HTTPException(
            status_code=400,
            detail="요청 mode 와 계좌 mode 가 일치하지 않습니다.",
        )

    # 3) AnalysisRun 영속화 (status=PENDING)
    run = AnalysisRun(
        user_id=user.id,
        account_id=account.id,
        mode=body.mode,
        budget_krw=encrypt_decimal(body.budget_krw),
        candidate_pool_options=body.candidate_pool_options or {},
        status=AnalysisRunStatus.PENDING,
    )
    db.add(run)
    try:
        await db.flush()
        await log_access(db, user.id, AccessAction.ANALYSIS_RUN_CREATE, request)
        await db.commit()
        await db.refresh(run)
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("ANALYSIS_RUN_CREATE persist failed")
        raise HTTPException(status_code=500, detail="분석 run 생성에 실패했습니다.")

    # 4) BackgroundTasks 로 분석 실행
    background_tasks.add_task(_run_analysis_background, run.id)

    return run_to_response(run, [], now=datetime.now(timezone.utc))


@router.get("/runs", response_model=AnalysisRunListResponse)
@limiter.limit("100/minute")
async def list_analysis_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자의 원클릭 분석 이력 페이징."""
    total_result = await db.execute(
        select(func.count(AnalysisRun.id)).where(AnalysisRun.user_id == user.id)
    )
    total = int(total_result.scalar_one() or 0)

    rows = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.user_id == user.id)
        .order_by(AnalysisRun.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = list(rows.scalars().all())

    # 각 run 의 item 카운트 (배치 조회)
    item_counts: dict[UUID, int] = {}
    if runs:
        run_ids = [r.id for r in runs]
        count_rows = await db.execute(
            select(
                AnalysisRunItem.run_id,
                func.count(AnalysisRunItem.id),
            )
            .where(AnalysisRunItem.run_id.in_(run_ids))
            .group_by(AnalysisRunItem.run_id)
        )
        item_counts = {row[0]: int(row[1]) for row in count_rows.all()}

    summaries = [run_to_summary(r, item_counts.get(r.id, 0)) for r in runs]

    try:
        await log_access(db, user.id, AccessAction.ANALYSIS_RUN_LIST, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("ANALYSIS_RUN_LIST access logging failed", exc_info=True)

    return AnalysisRunListResponse(
        items=summaries, total=total, limit=limit, offset=offset,
    )


@router.get("/runs/{run_id}", response_model=AnalysisRunResponse)
@limiter.limit("100/minute")
async def get_analysis_run(
    run_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """진행 상태/결과 조회 (폴링 대상)."""
    run = await _load_run_for_user(db, run_id, user.id)
    items = await _list_run_items(db, run.id)

    try:
        await log_access(db, user.id, AccessAction.ANALYSIS_RUN_GET, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("ANALYSIS_RUN_GET access logging failed", exc_info=True)

    return run_to_response(run, items, now=datetime.now(timezone.utc))


@router.post("/runs/{run_id}/decisions", response_model=AnalysisRunResponse)
@limiter.limit("100/minute")
async def submit_run_decisions(
    run_id: UUID,
    body: DecisionsRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """종목별 approve/reject 일괄 저장.

    PENDING 항목만 변경 가능. SKIPPED / 이미 결정된 항목은 차단.
    run.status 가 READY 가 아니면 변경 불가. 만료된 run 도 변경 불가.
    """
    run = await _load_run_for_user(db, run_id, user.id)

    if run.status != AnalysisRunStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=f"분석이 완료되지 않았습니다 (status={run.status.value}).",
        )

    now = datetime.now(timezone.utc)
    if run.expires_at is not None and run.expires_at < now:
        raise HTTPException(
            status_code=410,
            detail="결과 유효기간이 만료되었습니다. 재분석이 필요합니다.",
        )

    # 모든 대상 item 을 한 번에 로드
    item_ids = [d.item_id for d in body.decisions]
    rows = await db.execute(
        select(AnalysisRunItem).where(
            AnalysisRunItem.run_id == run.id,
            AnalysisRunItem.id.in_(item_ids),
        )
    )
    by_id = {it.id: it for it in rows.scalars().all()}

    if len(by_id) != len(set(item_ids)):
        raise HTTPException(
            status_code=400,
            detail="존재하지 않거나 다른 run 의 item 이 포함되어 있습니다.",
        )

    for d in body.decisions:
        item = by_id[d.item_id]
        if item.decision != AnalysisItemDecision.PENDING:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"이미 결정되었거나 차단된 항목입니다 "
                    f"(item={item.ticker}, decision={item.decision.value})."
                ),
            )
        item.decision = d.decision

    try:
        await log_access(db, user.id, AccessAction.ANALYSIS_RUN_DECISION, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("ANALYSIS_RUN_DECISION persist failed")
        raise HTTPException(status_code=500, detail="결정 저장에 실패했습니다.")

    items = await _list_run_items(db, run.id)
    return run_to_response(run, items, now=datetime.now(timezone.utc))


@router.post("/runs/{run_id}/execute", response_model=ExecuteResponse)
@limiter.limit("100/minute")
async def execute_run(
    run_id: UUID,
    body: ExecuteRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """승인 항목 발주.

    가드:
    - status == READY 만 발주 허용
    - TTL 만료 시 410
    - 한국장 시간(09:00–15:30 KST) 외 차단 (paper / live 동일 — 워크플랜 §4)
    - live 모드: TOTP 코드 재검증 필수
    """
    run = await _load_run_for_user(db, run_id, user.id)

    if run.status != AnalysisRunStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=f"발주 가능한 상태가 아닙니다 (status={run.status.value}).",
        )

    now = datetime.now(timezone.utc)
    if run.expires_at is not None and run.expires_at < now:
        # 만료 — 라운드트립 누락을 막기 위해 상태도 FAILED 로 마킹
        run.status = AnalysisRunStatus.FAILED
        run.error_message = "결과 유효기간 만료"
        await db.commit()
        raise HTTPException(
            status_code=410,
            detail="결과 유효기간이 만료되었습니다. 재분석이 필요합니다.",
        )

    # 장외 시간 가드 (paper / live 동일 차단)
    if not _is_market_hours():
        raise HTTPException(
            status_code=409,
            detail="장 운영 시간이 아닙니다 (KST 평일 09:00–15:30). 분석만 허용됩니다.",
        )

    # live 모드 2FA 재확인
    if run.mode == TradingMode.LIVE:
        if not user.totp_enabled or not user.totp_secret:
            raise HTTPException(
                status_code=403,
                detail="실거래 발주는 2FA 설정이 필요합니다.",
            )
        if not body.totp_code:
            raise HTTPException(
                status_code=400,
                detail="실거래 발주는 TOTP 코드가 필요합니다.",
            )
        try:
            secret = decrypt_totp_secret(user.totp_secret)
        except Exception:
            logger.exception("totp_secret decrypt failed user=%s", user.id)
            raise HTTPException(
                status_code=500,
                detail="2FA 검증에 실패했습니다.",
            )
        if not verify_totp_code(secret, body.totp_code):
            raise HTTPException(
                status_code=403, detail="TOTP 코드가 올바르지 않습니다.",
            )

    # 계좌 로드
    account = await _load_account_for_user(db, run.account_id, user.id)

    # 승인된 BUY/SELL 항목만 추출
    rows = await db.execute(
        select(AnalysisRunItem).where(
            AnalysisRunItem.run_id == run.id,
            AnalysisRunItem.decision == AnalysisItemDecision.APPROVED,
            AnalysisRunItem.action.in_(
                (AnalysisItemAction.BUY, AnalysisItemAction.SELL)
            ),
        )
    )
    approved_items = list(rows.scalars().all())
    if not approved_items:
        raise HTTPException(
            status_code=400, detail="승인된 항목이 없습니다.",
        )

    # 상태 EXECUTING 으로 락 효과
    run.status = AnalysisRunStatus.EXECUTING
    try:
        await db.flush()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="발주 시작에 실패했습니다.")

    # 발주
    kis: KISClient | None = None
    place_order = None
    if run.mode == TradingMode.LIVE:
        kis = _build_kis_client(account)
        place_order = kis.place_order

    try:
        outcomes = await execute_approved_items(
            db,
            user_id=user.id,
            account=account,
            items=approved_items,
            place_order=place_order,
        )
        # KIS 토큰 갱신 반영
        if kis is not None:
            await _persist_kis_token(db, account, kis)

        run.status = AnalysisRunStatus.DONE
        run.completed_at = datetime.now(timezone.utc)

        await log_access(db, user.id, AccessAction.ANALYSIS_RUN_EXECUTE, request)
        await db.commit()
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        # 발주 도중 치명적 예외 — run 을 FAILED 로 별도 트랜잭션에 기록
        async with AsyncSessionLocal() as fdb:
            await fail_run(fdb, run.id, f"발주 중 예외: {type(e).__name__}")
            await fdb.commit()
        logger.exception("execute_run fatal: run=%s", run.id)
        raise HTTPException(status_code=500, detail="발주 처리 중 오류가 발생했습니다.")
    finally:
        if kis is not None:
            await kis.close()

    return ExecuteResponse(
        run_id=run.id,
        executed=sum(1 for o in outcomes if o.success),
        failed=sum(1 for o in outcomes if not o.success),
        results=[
            ExecuteItemResult(
                item_id=o.item_id,
                ticker=o.ticker,
                action=o.action,
                success=o.success,
                order_id=o.order_id,
                error_message=o.error_message,
            )
            for o in outcomes
        ],
    )
