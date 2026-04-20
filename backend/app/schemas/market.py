"""시장 공통 스키마 — 종목 검색 결과 등."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StockSearchItem(BaseModel):
    ticker: str = Field(description="6자리 종목코드")
    name: str = Field(description="종목명")
    market: str = Field(description="KOSPI | KOSDAQ | KONEX")


class StockSearchResponse(BaseModel):
    query: str
    results: list[StockSearchItem]
