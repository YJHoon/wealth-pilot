"""원클릭 분석·매매 라우터(`/api/analysis/runs`) 테스트.

라우터 단위 동작에 집중 — 분석 오케스트레이터/후보풀/포지션 핸들러는 자체 단위 테스트가 있다.
KIS 호출과 BackgroundTasks 는 mock 처리하여 외부 의존성 없이 라우터만 검증.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    AdvisoryPosition,
    AnalysisItemAction,
    AnalysisItemDecision,
    AnalysisItemSource,
    AnalysisRun,
    AnalysisRunItem,
    AnalysisRunStatus,
    OrderStatus,
    TradingAccount,
    TradingMode,
    TradingOrder,
)
from app.models.user import User
from app.services.crypto_service import (
    decrypt_decimal,
    encrypt_decimal,
    encrypt_value,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

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
async def live_account(db_session: AsyncSession, mock_user: User) -> TradingAccount:
    a = TradingAccount(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        mode=TradingMode.LIVE,
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


def _make_ready_run(
    user_id: uuid.UUID,
    account: TradingAccount,
    *,
    expires_in_minutes: int = 5,
    mode: TradingMode | None = None,
) -> AnalysisRun:
    now = datetime.now(timezone.utc)
    return AnalysisRun(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account.id,
        mode=mode or account.mode,
        budget_krw=encrypt_decimal(Decimal("1000000")),
        candidate_pool_options={},
        status=AnalysisRunStatus.READY,
        completed_at=now,
        expires_at=now + timedelta(minutes=expires_in_minutes),
        summary_json={"total": 1},
    )


def _make_item(
    run_id: uuid.UUID,
    *,
    ticker: str = "005930",
    action: AnalysisItemAction = AnalysisItemAction.BUY,
    decision: AnalysisItemDecision = AnalysisItemDecision.PENDING,
    ref_price: Decimal = Decimal("70000"),
    suggested_qty: Decimal = Decimal("5"),
    source: AnalysisItemSource = AnalysisItemSource.AUTO_PICK,
) -> AnalysisRunItem:
    return AnalysisRunItem(
        id=uuid.uuid4(),
        run_id=run_id,
        ticker=ticker,
        ticker_name=ticker,
        source=source,
        action=action,
        confidence=85,
        reason="테스트",
        ref_price=encrypt_decimal(ref_price),
        suggested_qty=encrypt_decimal(suggested_qty),
        decision=decision,
    )


# ──────────────────────────────────────────────
# POST /runs
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_run_returns_pending_and_schedules_background(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    paper_account: TradingAccount,
):
    """POST /runs — 201 + status=pending. background task 는 mock."""
    with patch(
        "app.routers.analysis._run_analysis_background",
        new=AsyncMock(),
    ) as mock_bg:
        resp = await auth_client.post(
            "/api/analysis/runs",
            json={
                "account_id": str(paper_account.id),
                "mode": "paper",
                "budget_krw": "1000000",
            },
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert data["mode"] == "paper"
    assert data["account_id"] == str(paper_account.id)
    # background task 가 등록되어 호출됐어야 함
    mock_bg.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_run_blocked_when_in_progress(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """진행 중 run 이 있으면 새 run 생성 차단 (409)."""
    busy = AnalysisRun(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=paper_account.id,
        mode=TradingMode.PAPER,
        budget_krw=encrypt_decimal(Decimal("100")),
        candidate_pool_options={},
        status=AnalysisRunStatus.ANALYZING,
    )
    db_session.add(busy)
    await db_session.commit()

    with patch(
        "app.routers.analysis._run_analysis_background", new=AsyncMock(),
    ):
        resp = await auth_client.post(
            "/api/analysis/runs",
            json={
                "account_id": str(paper_account.id),
                "mode": "paper",
                "budget_krw": "1000000",
            },
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_run_account_mode_mismatch(
    auth_client: AsyncClient,
    paper_account: TradingAccount,
):
    """body.mode 와 계좌.mode 가 다르면 400."""
    with patch(
        "app.routers.analysis._run_analysis_background", new=AsyncMock(),
    ):
        resp = await auth_client.post(
            "/api/analysis/runs",
            json={
                "account_id": str(paper_account.id),
                "mode": "live",
                "budget_krw": "1000000",
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_run_other_users_account_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    other_user: User,
):
    """다른 사용자의 계좌 ID 로 시도하면 404."""
    other_account = TradingAccount(
        id=uuid.uuid4(),
        user_id=other_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("1000000")),
    )
    db_session.add(other_account)
    await db_session.commit()

    try:
        with patch(
            "app.routers.analysis._run_analysis_background", new=AsyncMock(),
        ):
            resp = await auth_client.post(
                "/api/analysis/runs",
                json={
                    "account_id": str(other_account.id),
                    "mode": "paper",
                    "budget_krw": "1000000",
                },
            )
        assert resp.status_code == 404
    finally:
        from sqlalchemy import text
        await db_session.execute(
            text("DELETE FROM trading_accounts WHERE id = :i"),
            {"i": str(other_account.id)},
        )
        await db_session.commit()


# ──────────────────────────────────────────────
# GET /runs/{id}
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_run_returns_items_and_expired_flag(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """READY 상태 run + items 반환 + expired=False."""
    run = _make_ready_run(mock_user.id, paper_account)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(run.id)
    db_session.add(item)
    await db_session.commit()

    resp = await auth_client.get(f"/api/analysis/runs/{run.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["expired"] is False
    assert len(data["items"]) == 1
    assert data["items"][0]["ticker"] == "005930"
    assert Decimal(data["items"][0]["ref_price"]) == Decimal("70000")


@pytest.mark.asyncio
async def test_get_run_expired_flag_true_after_ttl(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """expires_at 경과 후엔 expired=True."""
    run = _make_ready_run(mock_user.id, paper_account, expires_in_minutes=-1)
    db_session.add(run)
    await db_session.commit()

    resp = await auth_client.get(f"/api/analysis/runs/{run.id}")
    assert resp.status_code == 200
    assert resp.json()["expired"] is True


@pytest.mark.asyncio
async def test_get_run_other_user_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    other_user: User,
):
    """다른 사용자의 run id 는 404 (소유권 검증)."""
    other_account = TradingAccount(
        id=uuid.uuid4(),
        user_id=other_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("1000000")),
    )
    db_session.add(other_account)
    await db_session.flush()
    run = _make_ready_run(other_user.id, other_account)
    db_session.add(run)
    await db_session.commit()

    try:
        resp = await auth_client.get(f"/api/analysis/runs/{run.id}")
        assert resp.status_code == 404
    finally:
        from sqlalchemy import text
        await db_session.execute(
            text("DELETE FROM analysis_runs WHERE id = :i"), {"i": str(run.id)},
        )
        await db_session.execute(
            text("DELETE FROM trading_accounts WHERE id = :i"),
            {"i": str(other_account.id)},
        )
        await db_session.commit()


# ──────────────────────────────────────────────
# POST /runs/{id}/decisions
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decisions_pending_to_approved(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    run = _make_ready_run(mock_user.id, paper_account)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(run.id)
    db_session.add(item)
    await db_session.commit()

    resp = await auth_client.post(
        f"/api/analysis/runs/{run.id}/decisions",
        json={"decisions": [{"item_id": str(item.id), "decision": "approved"}]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"][0]["decision"] == "approved"


@pytest.mark.asyncio
async def test_decisions_blocks_skipped_items(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """SKIPPED 항목은 변경 차단 (409)."""
    run = _make_ready_run(mock_user.id, paper_account)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(
        run.id, decision=AnalysisItemDecision.SKIPPED,
    )
    db_session.add(item)
    await db_session.commit()

    resp = await auth_client.post(
        f"/api/analysis/runs/{run.id}/decisions",
        json={"decisions": [{"item_id": str(item.id), "decision": "approved"}]},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_decisions_blocks_when_run_expired(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """만료된 run 은 결정 변경 차단 (410)."""
    run = _make_ready_run(mock_user.id, paper_account, expires_in_minutes=-1)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(run.id)
    db_session.add(item)
    await db_session.commit()

    resp = await auth_client.post(
        f"/api/analysis/runs/{run.id}/decisions",
        json={"decisions": [{"item_id": str(item.id), "decision": "approved"}]},
    )
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_decisions_rejects_invalid_value(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """approved/rejected 외엔 422 (Pydantic validation)."""
    run = _make_ready_run(mock_user.id, paper_account)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(run.id)
    db_session.add(item)
    await db_session.commit()

    resp = await auth_client.post(
        f"/api/analysis/runs/{run.id}/decisions",
        json={"decisions": [{"item_id": str(item.id), "decision": "skipped"}]},
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────
# POST /runs/{id}/execute
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_paper_creates_order_and_advisory_position(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """paper 모드 + 장중 + 승인 항목 → 주문 생성 + AdvisoryPosition 누적."""
    run = _make_ready_run(mock_user.id, paper_account)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(
        run.id,
        decision=AnalysisItemDecision.APPROVED,
        ref_price=Decimal("70000"),
        suggested_qty=Decimal("5"),
    )
    db_session.add(item)
    await db_session.commit()

    with patch("app.routers.analysis._is_market_hours", return_value=True):
        resp = await auth_client.post(
            f"/api/analysis/runs/{run.id}/execute",
            json={},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["executed"] == 1
    assert data["failed"] == 0

    # 주문 1건 + paper 모드는 즉시 FILLED
    orders = (await db_session.execute(
        select(TradingOrder).where(TradingOrder.analysis_run_item_id == item.id)
    )).scalars().all()
    assert len(orders) == 1
    assert orders[0].status == OrderStatus.FILLED
    # AdvisoryPosition 1건 (5주 @ 70000)
    pos = (await db_session.execute(
        select(AdvisoryPosition).where(
            AdvisoryPosition.account_id == paper_account.id,
            AdvisoryPosition.ticker == "005930",
        )
    )).scalar_one()
    assert decrypt_decimal(pos.quantity) == Decimal("5")
    # run 상태는 DONE
    await db_session.refresh(run)
    assert run.status == AnalysisRunStatus.DONE


@pytest.mark.asyncio
async def test_execute_blocked_off_market_hours(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """장외 시간엔 paper 도 차단."""
    run = _make_ready_run(mock_user.id, paper_account)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(run.id, decision=AnalysisItemDecision.APPROVED)
    db_session.add(item)
    await db_session.commit()

    with patch("app.routers.analysis._is_market_hours", return_value=False):
        resp = await auth_client.post(
            f"/api/analysis/runs/{run.id}/execute",
            json={},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_execute_blocked_when_expired(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """TTL 만료 → 410, run.status FAILED 마킹."""
    run = _make_ready_run(mock_user.id, paper_account, expires_in_minutes=-1)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(run.id, decision=AnalysisItemDecision.APPROVED)
    db_session.add(item)
    await db_session.commit()

    with patch("app.routers.analysis._is_market_hours", return_value=True):
        resp = await auth_client.post(
            f"/api/analysis/runs/{run.id}/execute",
            json={},
        )
    assert resp.status_code == 410
    await db_session.refresh(run)
    assert run.status == AnalysisRunStatus.FAILED


@pytest.mark.asyncio
async def test_execute_rejects_when_no_approved_items(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """승인된 항목이 없으면 400."""
    run = _make_ready_run(mock_user.id, paper_account)
    db_session.add(run)
    await db_session.flush()
    # PENDING 만 있음 — APPROVED 가 없음
    item = _make_item(run.id, decision=AnalysisItemDecision.PENDING)
    db_session.add(item)
    await db_session.commit()

    with patch("app.routers.analysis._is_market_hours", return_value=True):
        resp = await auth_client.post(
            f"/api/analysis/runs/{run.id}/execute",
            json={},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_execute_live_requires_totp(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    live_account: TradingAccount,
):
    """live 모드: totp_code 누락 시 400 (계좌 / 사용자 totp_enabled 모두 충족 가정)."""
    # 사용자 totp 활성화 + secret 세팅
    mock_user.totp_enabled = True
    mock_user.totp_secret = encrypt_value("JBSWY3DPEHPK3PXP")  # 평문 base32
    db_session.add(mock_user)
    run = _make_ready_run(mock_user.id, live_account)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(run.id, decision=AnalysisItemDecision.APPROVED)
    db_session.add(item)
    await db_session.commit()

    with patch("app.routers.analysis._is_market_hours", return_value=True):
        resp = await auth_client.post(
            f"/api/analysis/runs/{run.id}/execute",
            json={},  # totp_code 없음
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_execute_live_invalid_totp_rejected(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    live_account: TradingAccount,
):
    """live 모드: 잘못된 totp_code 는 403."""
    mock_user.totp_enabled = True
    mock_user.totp_secret = encrypt_value("JBSWY3DPEHPK3PXP")
    db_session.add(mock_user)
    run = _make_ready_run(mock_user.id, live_account)
    db_session.add(run)
    await db_session.flush()
    item = _make_item(run.id, decision=AnalysisItemDecision.APPROVED)
    db_session.add(item)
    await db_session.commit()

    with patch(
        "app.routers.analysis.verify_totp_code", return_value=False,
    ), patch("app.routers.analysis._is_market_hours", return_value=True):
        resp = await auth_client.post(
            f"/api/analysis/runs/{run.id}/execute",
            json={"totp_code": "000000"},
        )
    assert resp.status_code == 403


# ──────────────────────────────────────────────
# GET /runs (이력)
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_runs_returns_paginated_summaries(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    paper_account: TradingAccount,
):
    """GET /runs — 페이징 + items 요약 카운트."""
    runs = []
    for _ in range(3):
        r = _make_ready_run(mock_user.id, paper_account)
        runs.append(r)
        db_session.add(r)
    await db_session.flush()
    # 2번째 run 에 items 2개
    db_session.add(_make_item(runs[1].id, ticker="A"))
    db_session.add(_make_item(runs[1].id, ticker="B"))
    await db_session.commit()

    resp = await auth_client.get("/api/analysis/runs?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2
    # item_count 가 정상 매핑되는지
    counts_by_id = {it["id"]: it["item_count"] for it in data["items"]}
    if str(runs[1].id) in counts_by_id:
        assert counts_by_id[str(runs[1].id)] == 2
