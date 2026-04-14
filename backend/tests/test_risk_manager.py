"""리스크 관리 테스트 — 경계값 중심"""

from decimal import Decimal

import pytest

from app.services.risk_manager import RiskCheck, RiskManager


class TestCheckCanBuy:
    def test_allowed_within_limits(self):
        rm = RiskManager(max_position_pct=Decimal("0.20"), max_positions=10)
        result = rm.check_can_buy(
            portfolio_value=Decimal("10000000"),
            order_amount=Decimal("1000000"),  # 10%
            current_position_count=3,
        )
        assert result.allowed is True

    def test_blocked_by_max_position_pct(self):
        rm = RiskManager(max_position_pct=Decimal("0.20"))
        result = rm.check_can_buy(
            portfolio_value=Decimal("10000000"),
            order_amount=Decimal("3000000"),  # 30% > 20%
            current_position_count=0,
        )
        assert result.allowed is False
        assert "비중" in result.reason

    def test_blocked_by_max_positions(self):
        rm = RiskManager(max_positions=5)
        result = rm.check_can_buy(
            portfolio_value=Decimal("10000000"),
            order_amount=Decimal("100000"),
            current_position_count=5,
        )
        assert result.allowed is False
        assert "종목 수" in result.reason

    def test_blocked_by_zero_portfolio(self):
        rm = RiskManager()
        result = rm.check_can_buy(
            portfolio_value=Decimal("0"),
            order_amount=Decimal("100000"),
            current_position_count=0,
        )
        assert result.allowed is False

    def test_exact_max_position_pct(self):
        rm = RiskManager(max_position_pct=Decimal("0.20"))
        result = rm.check_can_buy(
            portfolio_value=Decimal("10000000"),
            order_amount=Decimal("2000000"),  # exactly 20%
            current_position_count=0,
        )
        assert result.allowed is True

    def test_blocked_by_max_order_amount(self):
        rm = RiskManager(max_order_amount=Decimal("5000000"))
        result = rm.check_can_buy(
            portfolio_value=Decimal("100000000"),
            order_amount=Decimal("6000000"),  # 6% < 20% but > 500만원
            current_position_count=0,
        )
        assert result.allowed is False
        assert "주문 금액" in result.reason

    def test_allowed_within_max_order_amount(self):
        rm = RiskManager(max_order_amount=Decimal("5000000"))
        result = rm.check_can_buy(
            portfolio_value=Decimal("100000000"),
            order_amount=Decimal("4000000"),
            current_position_count=0,
        )
        assert result.allowed is True

    def test_max_order_amount_zero_means_unlimited(self):
        rm = RiskManager(max_order_amount=Decimal("0"))
        result = rm.check_can_buy(
            portfolio_value=Decimal("100000000"),
            order_amount=Decimal("50000000"),  # 50% > 20% → 비중으로 차단
            current_position_count=0,
        )
        # 금액 한도는 통과하지만 비중 초과로 차단
        assert result.allowed is False
        assert "비중" in result.reason

    def test_order_amount_equal_to_max_order_amount(self):
        rm = RiskManager(max_order_amount=Decimal("5000000"))
        result = rm.check_can_buy(
            portfolio_value=Decimal("100000000"),
            order_amount=Decimal("5000000"),  # exactly == max
            current_position_count=0,
        )
        assert result.allowed is True

    def test_negative_max_order_amount_raises(self):
        with pytest.raises(ValueError, match="max_order_amount must be >= 0"):
            RiskManager(max_order_amount=Decimal("-1"))


class TestCheckStopLoss:
    def test_stop_loss_triggered(self):
        rm = RiskManager(stop_loss_pct=Decimal("0.05"))
        result = rm.check_stop_loss(
            avg_buy_price=Decimal("10000"),
            current_price=Decimal("9400"),  # -6% > 5%
        )
        assert result.allowed is True  # allowed = 매도 허용
        assert "손절 발동" in result.reason

    def test_stop_loss_not_triggered(self):
        rm = RiskManager(stop_loss_pct=Decimal("0.05"))
        result = rm.check_stop_loss(
            avg_buy_price=Decimal("10000"),
            current_price=Decimal("9600"),  # -4% < 5%
        )
        assert result.allowed is False  # 미발동
        assert "미발동" in result.reason

    def test_price_increase_no_stop_loss(self):
        rm = RiskManager(stop_loss_pct=Decimal("0.05"))
        result = rm.check_stop_loss(
            avg_buy_price=Decimal("10000"),
            current_price=Decimal("11000"),  # +10%
        )
        assert result.allowed is False

    def test_zero_avg_price(self):
        rm = RiskManager()
        result = rm.check_stop_loss(
            avg_buy_price=Decimal("0"),
            current_price=Decimal("10000"),
        )
        assert result.allowed is False
        assert "매입가" in result.reason

    def test_exact_threshold(self):
        rm = RiskManager(stop_loss_pct=Decimal("0.05"))
        result = rm.check_stop_loss(
            avg_buy_price=Decimal("10000"),
            current_price=Decimal("9500"),  # exactly -5%
        )
        assert result.allowed is True


class TestCheckDailyLoss:
    def test_no_limit_always_allowed(self):
        rm = RiskManager(daily_loss_limit=Decimal("0"))
        result = rm.check_daily_loss(today_realized_pnl=Decimal("-999999"))
        assert result.allowed is True

    def test_within_limit(self):
        rm = RiskManager(daily_loss_limit=Decimal("100000"))
        result = rm.check_daily_loss(today_realized_pnl=Decimal("-50000"))
        assert result.allowed is True

    def test_exceeds_limit(self):
        rm = RiskManager(daily_loss_limit=Decimal("100000"))
        result = rm.check_daily_loss(today_realized_pnl=Decimal("-150000"))
        assert result.allowed is False
        assert "한도" in result.reason

    def test_positive_pnl_allowed(self):
        rm = RiskManager(daily_loss_limit=Decimal("100000"))
        result = rm.check_daily_loss(today_realized_pnl=Decimal("50000"))
        assert result.allowed is True


class TestCalculatePositionSize:
    def test_basic_calculation(self):
        rm = RiskManager(max_position_pct=Decimal("0.20"))
        qty = rm.calculate_position_size(
            available_cash=Decimal("5000000"),
            portfolio_value=Decimal("10000000"),
            price_per_share=Decimal("65000"),
        )
        # max_amount = min(5000000, 10000000 * 0.20) = min(5000000, 2000000) = 2000000
        # qty = 2000000 / 65000 = 30
        assert qty == 30

    def test_limited_by_cash(self):
        rm = RiskManager(max_position_pct=Decimal("0.50"))
        qty = rm.calculate_position_size(
            available_cash=Decimal("100000"),
            portfolio_value=Decimal("10000000"),
            price_per_share=Decimal("65000"),
        )
        # max_amount = min(100000, 5000000) = 100000
        # qty = 100000 / 65000 = 1
        assert qty == 1

    def test_zero_price(self):
        rm = RiskManager()
        qty = rm.calculate_position_size(
            available_cash=Decimal("5000000"),
            portfolio_value=Decimal("10000000"),
            price_per_share=Decimal("0"),
        )
        assert qty == 0

    def test_no_cash(self):
        rm = RiskManager()
        qty = rm.calculate_position_size(
            available_cash=Decimal("0"),
            portfolio_value=Decimal("10000000"),
            price_per_share=Decimal("65000"),
        )
        assert qty == 0


class TestFromParams:
    def test_custom_params(self):
        rm = RiskManager.from_params({
            "max_position_pct": "0.30",
            "stop_loss_pct": "0.10",
            "daily_loss_limit": "500000",
            "max_positions": 5,
            "max_order_amount": "10000000",
        })
        assert rm.max_position_pct == Decimal("0.30")
        assert rm.stop_loss_pct == Decimal("0.10")
        assert rm.daily_loss_limit == Decimal("500000")
        assert rm.max_positions == 5
        assert rm.max_order_amount == Decimal("10000000")

    def test_default_params(self):
        rm = RiskManager.from_params({})
        assert rm.max_position_pct == Decimal("0.20")
        assert rm.stop_loss_pct == Decimal("0.05")
        assert rm.daily_loss_limit == Decimal("0")
        assert rm.max_positions == 10
