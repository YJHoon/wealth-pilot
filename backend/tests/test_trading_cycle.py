"""매매 사이클 테스트 — 장 시간 체크, 사이클 로직 mock"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.tasks.trading_cycle import KST, _is_market_hours


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
