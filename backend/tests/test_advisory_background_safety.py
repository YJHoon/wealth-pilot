"""`_run_analysis_background` 안전망 회귀 테스트.

이 테스트는 background task 안의 어떤 경로에서 예외가 발생해도 run.status 가
ANALYZING/PENDING 으로 stuck 되지 않고 FAILED 로 마킹되는지를 보장한다.

배경: 사용자 보고 — 마지막 종목 시세 호출에서 KISClientError 가 떨어진 후
"결과 준비" 단계가 영원히 멈춤. outer try/except 부재로 background task 가
조용히 죽고 run.status 가 진행 중 상태로 stuck.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.trading import (
    AnalysisRun,
    AnalysisRunStatus,
    TradingAccount,
    TradingMode,
)
from app.models.user import User
from app.routers.analysis import _run_analysis_background
from app.services.crypto_service import encrypt_decimal
from app.services.kis_client import KISClientError


@pytest_asyncio.fixture
async def paper_account(db_session: AsyncSession, mock_user: User) -> TradingAccount:
    a = TradingAccount(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


@pytest_asyncio.fixture
async def pending_run(
    db_session: AsyncSession, mock_user: User, paper_account: TradingAccount,
) -> AnalysisRun:
    """PENDING 상태로 시작하는 run — background task 가 이걸 받아 진행한다."""
    run = AnalysisRun(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=paper_account.id,
        mode=TradingMode.PAPER,
        budget_krw=encrypt_decimal(Decimal("1000000")),
        candidate_pool_options={},
        status=AnalysisRunStatus.PENDING,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


async def _reload_run(run_id: uuid.UUID) -> AnalysisRun:
    """별도 세션으로 DB 에서 직접 다시 읽어온다.

    background task 가 commit 한 결과는 fixture 의 db_session 트랜잭션 캐시에
    바로 안 보이고, expire_all + select 로 강제로 읽으면 teardown 시 세션 상태가
    꼬여 greenlet 에러가 난다 — 그래서 깨끗한 새 세션을 쓴다.
    """
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(AnalysisRun).where(AnalysisRun.id == run_id)
            )
        ).scalar_one()
        return row


def _kis_mock_with_balance() -> MagicMock:
    """get_balance 까지는 성공하는 KIS Mock 빌더."""
    kis = MagicMock()
    kis.get_balance = AsyncMock(
        return_value={
            "cash": Decimal("5000000"),
            "total_eval": Decimal("10000000"),
            "holdings": [],
        }
    )
    kis.access_token = "tok"
    kis.token_expires_at = None
    kis.close = AsyncMock()
    return kis


@pytest.mark.asyncio
async def test_kis_client_build_failure_marks_run_failed(
    db_session: AsyncSession, pending_run: AnalysisRun,
):
    """`_build_kis_client` 가 raise 해도 run.status=FAILED 로 마킹된다."""
    with patch(
        "app.routers.analysis._build_kis_client",
        side_effect=RuntimeError("자격증명 없음"),
    ):
        await _run_analysis_background(pending_run.id)

    refreshed = await _reload_run(pending_run.id)
    assert refreshed.status == AnalysisRunStatus.FAILED
    assert refreshed.error_message and "KIS 클라이언트 생성 실패" in refreshed.error_message


@pytest.mark.asyncio
async def test_kis_client_error_on_balance_marks_run_failed(
    db_session: AsyncSession, pending_run: AnalysisRun,
):
    """KISClientError 가 잔고 조회에서 떨어지면 FAILED + 에러 메시지에 사유 포함."""
    kis = MagicMock()
    kis.get_balance = AsyncMock(side_effect=KISClientError("rate limit"))
    kis.close = AsyncMock()
    with patch("app.routers.analysis._build_kis_client", return_value=kis):
        await _run_analysis_background(pending_run.id)

    refreshed = await _reload_run(pending_run.id)
    assert refreshed.status == AnalysisRunStatus.FAILED
    assert "rate limit" in (refreshed.error_message or "")
    kis.close.assert_awaited()


@pytest.mark.asyncio
async def test_non_kis_error_on_balance_also_marks_run_failed(
    db_session: AsyncSession, pending_run: AnalysisRun,
):
    """KISClientError 외 예외(예: 네트워크 끊김)도 FAILED 마킹 — 이전엔 outer
    try 부재로 stuck 됐던 경로."""
    kis = MagicMock()
    kis.get_balance = AsyncMock(side_effect=OSError("connection reset"))
    kis.close = AsyncMock()
    with patch("app.routers.analysis._build_kis_client", return_value=kis):
        await _run_analysis_background(pending_run.id)

    refreshed = await _reload_run(pending_run.id)
    assert refreshed.status == AnalysisRunStatus.FAILED
    assert "잔고 조회 실패" in (refreshed.error_message or "")


@pytest.mark.asyncio
async def test_token_persist_failure_does_not_overwrite_ready(
    db_session: AsyncSession, pending_run: AnalysisRun,
):
    """`_persist_kis_token` 실패는 분석 결과(READY)를 덮어쓰지 않는다."""
    kis = _kis_mock_with_balance()

    async def _stub_run_analysis(_db, run, **_kwargs):
        run.status = AnalysisRunStatus.READY
        run.completed_at = datetime.now(timezone.utc)
        run.expires_at = run.completed_at + timedelta(minutes=5)
        run.summary_json = {"total": 0}
        return run

    with (
        patch("app.routers.analysis._build_kis_client", return_value=kis),
        patch(
            "app.routers.analysis.build_candidate_pool",
            new=AsyncMock(return_value=MagicMock(items=[])),
        ),
        patch("app.routers.analysis.run_analysis", side_effect=_stub_run_analysis),
        patch(
            "app.routers.analysis._persist_kis_token",
            side_effect=RuntimeError("token persist boom"),
        ),
    ):
        await _run_analysis_background(pending_run.id)

    refreshed = await _reload_run(pending_run.id)
    assert refreshed.status == AnalysisRunStatus.READY


@pytest.mark.asyncio
async def test_outer_safety_net_catches_unexpected_error(
    db_session: AsyncSession, pending_run: AnalysisRun,
):
    """outer try/except 가 예기치 못한 예외도 잡아 FAILED 로 마킹한다.

    AsyncSessionLocal context 진입 자체에서 raise 되는 시나리오를 시뮬레이션
    (DB 연결 풀 고갈 등에 대응). 별도 세션의 `_mark_failed_safely` 가 호출되어
    status 가 FAILED 로 commit 되어야 한다.
    """

    real_session_local = __import__(
        "app.routers.analysis", fromlist=["AsyncSessionLocal"]
    ).AsyncSessionLocal

    call_count = {"n": 0}

    def _fail_first_succeed_after(*args, **kwargs):
        """첫 호출(main 분석용 세션)은 raise. 그 후 호출(_mark_failed_safely)은 정상."""
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("pool exhausted")
        return real_session_local(*args, **kwargs)

    with patch(
        "app.routers.analysis.AsyncSessionLocal",
        side_effect=_fail_first_succeed_after,
    ):
        await _run_analysis_background(pending_run.id)

    refreshed = await _reload_run(pending_run.id)
    assert refreshed.status == AnalysisRunStatus.FAILED
    assert "예기치 못한 오류" in (refreshed.error_message or "")
