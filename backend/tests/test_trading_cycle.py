"""매매 사이클 테스트 — 장 시간 체크, 사이클 로직 mock"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.risk_manager import RiskManager
from app.tasks.trading_cycle import KST, _is_market_hours, decide_buy_quantity


class TestIsMarketHours:
    @patch("app.tasks.trading_cycle.datetime")
    def test_weekday_market_open(self, mock_dt):
        # 화요일 10:00 KST
        now = datetime(2024, 1, 2, 10, 0, tzinfo=KST)  # Tuesday
        mock_dt.now.return_value = now
        assert _is_market_hours() is True

    @patch("app.tasks.trading_cycle.datetime")
    def test_weekday_before_open(self, mock_dt):
        now = datetime(2024, 1, 2, 8, 30, tzinfo=KST)
        mock_dt.now.return_value = now
        assert _is_market_hours() is False

    @patch("app.tasks.trading_cycle.datetime")
    def test_weekday_after_close(self, mock_dt):
        now = datetime(2024, 1, 2, 15, 31, tzinfo=KST)
        mock_dt.now.return_value = now
        assert _is_market_hours() is False

    @patch("app.tasks.trading_cycle.datetime")
    def test_weekend_saturday(self, mock_dt):
        now = datetime(2024, 1, 6, 10, 0, tzinfo=KST)  # Saturday
        mock_dt.now.return_value = now
        assert _is_market_hours() is False

    @patch("app.tasks.trading_cycle.datetime")
    def test_weekend_sunday(self, mock_dt):
        now = datetime(2024, 1, 7, 10, 0, tzinfo=KST)  # Sunday
        mock_dt.now.return_value = now
        assert _is_market_hours() is False

    @patch("app.tasks.trading_cycle.datetime")
    def test_market_open_boundary(self, mock_dt):
        now = datetime(2024, 1, 2, 9, 0, tzinfo=KST)
        mock_dt.now.return_value = now
        assert _is_market_hours() is True

    @patch("app.tasks.trading_cycle.datetime")
    def test_market_close_boundary(self, mock_dt):
        now = datetime(2024, 1, 2, 15, 30, tzinfo=KST)
        mock_dt.now.return_value = now
        assert _is_market_hours() is True

    @patch("app.tasks.trading_cycle.datetime")
    def test_korean_holiday_closed(self, mock_dt):
        # 2026-03-01 삼일절 (일요일이 아닌 해의 삼일절)
        # 2025-03-01은 토요일이므로 2024-03-01 금요일 사용
        now = datetime(2024, 3, 1, 10, 0, tzinfo=KST)  # 삼일절, 금요일
        mock_dt.now.return_value = now
        assert _is_market_hours() is False

    @patch("app.tasks.trading_cycle.datetime")
    def test_non_holiday_weekday_open(self, mock_dt):
        # 2024-04-15 월요일, 공휴일 아님
        now = datetime(2024, 4, 15, 10, 0, tzinfo=KST)
        mock_dt.now.return_value = now
        assert _is_market_hours() is True


class TestDecideBuyQuantity:
    """decide_buy_quantity — 매수 수량 결정 로직.

    risk_mgr가 상한을 강제하고, LLM 전략은 suggested_quantity를 우선하되 clamp.
    """

    def _mgr(self, max_position_pct="1.0") -> RiskManager:
        # 비중 한도를 기본 100%로 느슨하게 두어 가용현금만으로 상한이 결정되도록.
        return RiskManager(max_position_pct=Decimal(max_position_pct))

    def test_rule_based_returns_risk_max(self):
        # 룰베이스: LLM 제안 무시하고 risk_max_qty 반환.
        qty = decide_buy_quantity(
            risk_mgr=self._mgr(),
            available_cash=Decimal("100000"),
            total_eval=Decimal("100000"),
            current_price=Decimal("10000"),
            is_llm_strategy=False,
            llm_suggested_quantity=5,  # 룰베이스라 무시돼야 함
        )
        assert qty == 10  # 100,000 / 10,000

    def test_llm_suggested_under_cap_applied(self):
        # LLM 제안이 상한 이하 → 제안값 그대로 사용.
        qty = decide_buy_quantity(
            risk_mgr=self._mgr(),
            available_cash=Decimal("100000"),
            total_eval=Decimal("100000"),
            current_price=Decimal("10000"),
            is_llm_strategy=True,
            llm_suggested_quantity=3,
        )
        assert qty == 3

    def test_llm_suggested_over_cap_clamped(self):
        # LLM이 환각으로 거대 주문 제안해도 상한으로 clamp.
        qty = decide_buy_quantity(
            risk_mgr=self._mgr(),
            available_cash=Decimal("100000"),
            total_eval=Decimal("100000"),
            current_price=Decimal("10000"),
            is_llm_strategy=True,
            llm_suggested_quantity=9999,
        )
        assert qty == 10  # 상한

    def test_llm_suggested_none_falls_back_to_risk_max(self):
        qty = decide_buy_quantity(
            risk_mgr=self._mgr(),
            available_cash=Decimal("100000"),
            total_eval=Decimal("100000"),
            current_price=Decimal("10000"),
            is_llm_strategy=True,
            llm_suggested_quantity=None,
        )
        assert qty == 10

    def test_llm_suggested_zero_falls_back_to_risk_max(self):
        # suggested_quantity=0은 "의견 없음"으로 간주 → 상한 사용.
        qty = decide_buy_quantity(
            risk_mgr=self._mgr(),
            available_cash=Decimal("100000"),
            total_eval=Decimal("100000"),
            current_price=Decimal("10000"),
            is_llm_strategy=True,
            llm_suggested_quantity=0,
        )
        assert qty == 10

    def test_price_exceeds_cash_returns_zero(self):
        # 1주 400,000원 > 가용현금 100,000원 → 소수점 불가로 0.
        qty = decide_buy_quantity(
            risk_mgr=self._mgr(),
            available_cash=Decimal("100000"),
            total_eval=Decimal("100000"),
            current_price=Decimal("400000"),
            is_llm_strategy=False,
            llm_suggested_quantity=None,
        )
        assert qty == 0

    def test_llm_suggested_clamped_to_zero_when_cash_short(self):
        # LLM이 1주 제안해도 가용현금 부족이면 상한이 0 → clamp 후 0.
        qty = decide_buy_quantity(
            risk_mgr=self._mgr(),
            available_cash=Decimal("100000"),
            total_eval=Decimal("100000"),
            current_price=Decimal("400000"),
            is_llm_strategy=True,
            llm_suggested_quantity=1,
        )
        assert qty == 0

    def test_max_position_pct_is_the_cap(self):
        # max_position_pct=20%면 포트폴리오 100만 × 0.2 = 20만 상한.
        # 가용현금 100만이어도 비중 한도가 더 타이트하면 그쪽이 적용.
        mgr = RiskManager(max_position_pct=Decimal("0.20"))
        qty = decide_buy_quantity(
            risk_mgr=mgr,
            available_cash=Decimal("1000000"),
            total_eval=Decimal("1000000"),
            current_price=Decimal("10000"),
            is_llm_strategy=False,
            llm_suggested_quantity=None,
        )
        assert qty == 20  # 200,000 / 10,000
