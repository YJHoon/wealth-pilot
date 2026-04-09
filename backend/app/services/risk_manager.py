"""리스크 관리 — 포지션 사이징, 손절, 일일 손실 한도"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    """리스크 체크 결과."""
    allowed: bool
    reason: str


class RiskManager:
    """매매 리스크 관리.

    Args:
        max_position_pct: 단일 종목 최대 비중 (기본 20%)
        stop_loss_pct: 종목별 손절 비율 (기본 5%)
        daily_loss_limit: 일일 최대 손실액 (기본 0 = 무제한)
        max_positions: 최대 동시 보유 종목 수 (기본 10)
    """

    def __init__(
        self,
        max_position_pct: Decimal = Decimal("0.20"),
        stop_loss_pct: Decimal = Decimal("0.05"),
        daily_loss_limit: Decimal = Decimal("0"),
        max_positions: int = 10,
        kill_switch_pct: Decimal = Decimal("0"),
        max_daily_trades: int = 0,
    ):
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.daily_loss_limit = daily_loss_limit
        self.max_positions = max_positions
        self.kill_switch_pct = kill_switch_pct
        self.max_daily_trades = max_daily_trades

    @classmethod
    def from_params(cls, params: dict) -> RiskManager:
        """전략 파라미터에서 리스크 설정 추출."""
        return cls(
            max_position_pct=Decimal(str(params.get("max_position_pct", "0.20"))),
            stop_loss_pct=Decimal(str(params.get("stop_loss_pct", "0.05"))),
            daily_loss_limit=Decimal(str(params.get("daily_loss_limit", "0"))),
            max_positions=params.get("max_positions", 10),
            kill_switch_pct=Decimal(str(params.get("kill_switch_pct", "0"))),
            max_daily_trades=params.get("max_daily_trades", 0),
        )

    def check_can_buy(
        self,
        portfolio_value: Decimal,
        order_amount: Decimal,
        current_position_count: int,
    ) -> RiskCheck:
        """매수 가능 여부 체크.

        Args:
            portfolio_value: 총 포트폴리오 가치 (현금 + 평가액)
            order_amount: 이번 매수 금액
            current_position_count: 현재 보유 종목 수
        """
        if portfolio_value <= 0:
            return RiskCheck(allowed=False, reason="포트폴리오 가치가 0 이하입니다.")

        # 최대 종목 수 체크
        if current_position_count >= self.max_positions:
            return RiskCheck(
                allowed=False,
                reason=f"최대 보유 종목 수({self.max_positions})에 도달했습니다.",
            )

        # 단일 종목 비중 체크
        position_pct = order_amount / portfolio_value
        if position_pct > self.max_position_pct:
            return RiskCheck(
                allowed=False,
                reason=f"주문 비중({position_pct:.1%})이 최대 허용({self.max_position_pct:.1%})을 초과합니다.",
            )

        return RiskCheck(allowed=True, reason="매수 가능")

    def check_stop_loss(
        self,
        avg_buy_price: Decimal,
        current_price: Decimal,
    ) -> RiskCheck:
        """손절 여부 체크.

        Args:
            avg_buy_price: 평균 매입가
            current_price: 현재가
        """
        if avg_buy_price <= 0:
            return RiskCheck(allowed=False, reason="매입가가 0 이하입니다.")

        loss_rate = (avg_buy_price - current_price) / avg_buy_price

        if loss_rate >= self.stop_loss_pct:
            return RiskCheck(
                allowed=True,  # 손절 발동 = 매도 허용
                reason=f"손절 발동: 손실률 {loss_rate:.1%} >= 기준 {self.stop_loss_pct:.1%}",
            )

        return RiskCheck(
            allowed=False,  # 손절 미발동
            reason=f"손절 미발동: 손실률 {loss_rate:.1%} < 기준 {self.stop_loss_pct:.1%}",
        )

    def check_daily_loss(
        self,
        today_realized_pnl: Decimal,
    ) -> RiskCheck:
        """일일 손실 한도 체크.

        Args:
            today_realized_pnl: 오늘 실현 손익 (음수 = 손실)
        """
        if self.daily_loss_limit <= 0:
            return RiskCheck(allowed=True, reason="일일 손실 한도 미설정")

        if today_realized_pnl < -self.daily_loss_limit:
            return RiskCheck(
                allowed=False,
                reason=f"일일 손실 한도 초과: {today_realized_pnl:,.0f}원 (한도: -{self.daily_loss_limit:,.0f}원)",
            )

        return RiskCheck(allowed=True, reason="일일 손실 한도 이내")

    def check_kill_switch(
        self,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal,
        initial_capital: Decimal,
    ) -> RiskCheck:
        """누적 손실률이 kill_switch_pct 이상이면 전략 중단 권고.

        Args:
            realized_pnl: 누적 실현 손익
            unrealized_pnl: 미실현 손익 합계
            initial_capital: 전략 초기 자본
        """
        if self.kill_switch_pct <= 0 or initial_capital <= 0:
            return RiskCheck(allowed=True, reason="킬 스위치 미설정")

        total_pnl = realized_pnl + unrealized_pnl
        loss_rate = -total_pnl / initial_capital  # 양수가 손실률

        if loss_rate >= self.kill_switch_pct:
            return RiskCheck(
                allowed=False,
                reason=(
                    f"킬 스위치 발동: 누적 손실률 {loss_rate:.1%} >= "
                    f"기준 {self.kill_switch_pct:.1%} "
                    f"(실현 {realized_pnl:,.0f} + 미실현 {unrealized_pnl:,.0f} / "
                    f"초기자본 {initial_capital:,.0f})"
                ),
            )

        return RiskCheck(allowed=True, reason="킬 스위치 이내")

    def check_daily_trades(self, today_trade_count: int) -> RiskCheck:
        """일일 거래 횟수 한도 체크.

        Args:
            today_trade_count: 오늘 체결된 거래 수
        """
        if self.max_daily_trades <= 0:
            return RiskCheck(allowed=True, reason="일일 거래 횟수 한도 미설정")

        if today_trade_count >= self.max_daily_trades:
            return RiskCheck(
                allowed=False,
                reason=(
                    f"일일 거래 횟수 한도 도달: "
                    f"{today_trade_count}건 >= {self.max_daily_trades}건"
                ),
            )

        return RiskCheck(allowed=True, reason="일일 거래 횟수 이내")

    def calculate_position_size(
        self,
        available_cash: Decimal,
        portfolio_value: Decimal,
        price_per_share: Decimal,
    ) -> int:
        """매수 가능 수량 계산 (최대 비중 고려).

        Returns:
            매수 가능 주수 (정수)
        """
        if price_per_share <= 0:
            return 0

        # 최대 투자 가능 금액 = min(현금, 포트폴리오 * max_position_pct)
        max_amount = min(available_cash, portfolio_value * self.max_position_pct)

        if max_amount <= 0:
            return 0

        return int(max_amount / price_per_share)
