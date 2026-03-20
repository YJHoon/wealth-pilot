"""대시보드 스키마 — Pydantic v2"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class HistoryPeriod(str, Enum):
    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    ONE_YEAR = "1Y"


class TypeBreakdown(BaseModel):
    """자산 유형별 소계"""
    value_krw: Decimal
    ratio: Decimal = Field(description="비중 (0~1)")


class GroupBreakdown(BaseModel):
    """포트폴리오 그룹별 소계"""
    name: str
    value_krw: Decimal
    ratio: Decimal = Field(description="비중 (0~1)")


class PnlSummary(BaseModel):
    """손익 요약"""
    total: Decimal = Field(description="합산 (실현 + 미실현)")
    realized: Decimal = Field(description="실현 손익")
    unrealized: Decimal = Field(description="미실현 손익")
    total_ratio: Decimal = Field(description="총 수익률 (0~1)")


class DailyChange(BaseModel):
    """전일 대비 변동"""
    amount: Decimal
    ratio: Decimal


class DashboardSummaryResponse(BaseModel):
    """GET /api/dashboard/summary 응답"""
    total_value_krw: Decimal
    by_type: dict[str, TypeBreakdown]
    by_group: dict[str, GroupBreakdown]
    pnl: PnlSummary
    previous_day_change: DailyChange
    updated_at: datetime


class HistoryDataPoint(BaseModel):
    """일별 자산 추이 데이터 포인트"""
    date: str = Field(description="YYYY-MM-DD")
    total_value_krw: Decimal
    breakdown: dict | None = None


class DashboardHistoryResponse(BaseModel):
    """GET /api/dashboard/history 응답"""
    period: str
    data_points: list[HistoryDataPoint]
    total_count: int


class SnapshotResponse(BaseModel):
    """POST /api/dashboard/snapshot 응답"""
    id: str
    snapshot_date: str
    total_value_krw: Decimal
    breakdown: dict | None
    created_at: datetime
