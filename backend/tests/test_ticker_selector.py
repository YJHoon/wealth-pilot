"""자동 종목 선정 파이프라인 단위 테스트 — 경계값 중심."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.ticker_selector import (
    DEFAULT_MIN_VOLUME_VALUE,
    DEFAULT_TOP_N,
    MAX_TOP_N,
    MIN_TOP_N,
    RULE_VERSION,
    SelectorConfig,
    StockCandidate,
    filter_by_blacklist,
    filter_by_min_volume,
    filter_by_seed,
    filter_universe_type,
    rank_and_top,
    select_tickers,
)


def _c(
    ticker: str,
    name: str,
    *,
    price: int = 10_000,
    volume_value: int = 100_000_000_000,
    market: str = "KOSPI",
    market_cap: int = 1_000_000_000_000,
) -> StockCandidate:
    return StockCandidate(
        ticker=ticker,
        name=name,
        market=market,  # type: ignore[arg-type]
        price=Decimal(str(price)),
        volume_value=volume_value,
        market_cap=market_cap,
    )


class TestFilterUniverseType:
    def test_excludes_preferred_shares(self):
        cs = [_c("005930", "삼성전자"), _c("005935", "삼성전자우")]
        kept, ex = filter_universe_type(cs)
        assert [c.ticker for c in kept] == ["005930"]
        assert ex[0].reason == "preferred"

    def test_excludes_preferred_B_suffix(self):
        cs = [_c("003540", "현대엘리베이우B")]
        kept, ex = filter_universe_type(cs)
        assert kept == []
        assert ex[0].reason == "preferred"

    def test_excludes_spac(self):
        cs = [_c("405560", "미래에셋드림스팩1호")]
        kept, ex = filter_universe_type(cs)
        assert kept == []
        assert ex[0].reason == "spac"

    def test_keeps_regular(self):
        cs = [_c("005930", "삼성전자"), _c("000660", "SK하이닉스")]
        kept, _ = filter_universe_type(cs)
        assert len(kept) == 2


class TestFilterByMinVolume:
    def test_drops_below_min(self):
        cs = [
            _c("A", "aa", volume_value=5_000_000_000),
            _c("B", "bb", volume_value=50_000_000_000),
        ]
        kept, ex = filter_by_min_volume(cs, min_volume_value=10_000_000_000)
        assert [c.ticker for c in kept] == ["B"]
        assert ex[0].reason == "below_min_volume"

    def test_zero_threshold_passes_all(self):
        cs = [_c("A", "aa", volume_value=1)]
        kept, ex = filter_by_min_volume(cs, min_volume_value=0)
        assert len(kept) == 1
        assert ex == []


class TestFilterBySeed:
    def test_excludes_price_over_limit(self):
        cs = [_c("A", "aa", price=50_000), _c("B", "bb", price=2_000_000)]
        kept, ex = filter_by_seed(
            cs,
            available_cash=Decimal("1000000"),
            total_eval=Decimal("5000000"),
            max_position_pct=Decimal("0.20"),
        )
        # limit = min(100만, 500만 × 0.20 = 100만) = 100만 → B(200만) 제외
        assert [c.ticker for c in kept] == ["A"]
        assert ex[0].reason == "price_over_seed"

    def test_position_cap_tighter_than_cash(self):
        cs = [_c("A", "aa", price=300_000)]
        kept, _ = filter_by_seed(
            cs,
            available_cash=Decimal("10000000"),
            total_eval=Decimal("1000000"),
            max_position_pct=Decimal("0.20"),
        )
        # limit = min(1000만, 1000만 × 0.2 = 20만) = 20만 → 30만원 제외
        assert kept == []

    def test_total_eval_zero_uses_cash(self):
        cs = [_c("A", "aa", price=500_000)]
        kept, _ = filter_by_seed(
            cs,
            available_cash=Decimal("1000000"),
            total_eval=Decimal("0"),
            max_position_pct=Decimal("0.20"),
        )
        assert [c.ticker for c in kept] == ["A"]

    def test_zero_limit_excludes_all(self):
        cs = [_c("A", "aa", price=100)]
        kept, ex = filter_by_seed(
            cs,
            available_cash=Decimal("0"),
            total_eval=Decimal("0"),
            max_position_pct=Decimal("0.20"),
        )
        assert kept == []
        assert ex[0].reason == "price_over_seed"


class TestFilterByBlacklist:
    def test_removes_blacklisted(self):
        cs = [_c("005930", "삼성전자"), _c("000660", "SK하이닉스")]
        kept, ex = filter_by_blacklist(cs, ["005930"])
        assert [c.ticker for c in kept] == ["000660"]
        assert ex[0].reason == "blacklist"

    def test_empty_blacklist_noop(self):
        cs = [_c("005930", "삼성전자")]
        kept, ex = filter_by_blacklist(cs, [])
        assert len(kept) == 1
        assert ex == []

    def test_strips_whitespace_and_blanks(self):
        cs = [_c("005930", "삼성전자"), _c("000660", "SK하이닉스")]
        kept, _ = filter_by_blacklist(cs, ["  005930  ", "", "   "])
        assert [c.ticker for c in kept] == ["000660"]


class TestRankAndTop:
    def test_sorts_by_volume_value_desc(self):
        cs = [
            _c("A", "aa", volume_value=100),
            _c("B", "bb", volume_value=300),
            _c("C", "cc", volume_value=200),
        ]
        picks = rank_and_top(cs, top_n=3)
        assert [p.ticker for p in picks] == ["B", "C", "A"]
        # 정규화 점수 — 최고 = 1.0
        assert picks[0].score == pytest.approx(1.0)
        assert picks[1].score == pytest.approx(200 / 300)

    def test_top_n_truncates(self):
        cs = [_c(f"T{i}", f"n{i}", volume_value=i) for i in range(1, 6)]
        picks = rank_and_top(cs, top_n=2)
        assert len(picks) == 2

    def test_empty_or_zero_top_n(self):
        assert rank_and_top([], 5) == []
        assert rank_and_top([_c("A", "a")], 0) == []

    def test_rank_reason_text(self):
        cs = [_c("A", "a", volume_value=10), _c("B", "b", volume_value=20)]
        picks = rank_and_top(cs, top_n=2)
        assert picks[0].reason == "거래대금 1위"
        assert picks[1].reason == "거래대금 2위"


class TestSelectorConfig:
    def test_defaults_on_empty(self):
        c = SelectorConfig.from_dict(None)
        assert c.top_n == DEFAULT_TOP_N
        assert c.market == "ALL"
        assert c.min_volume_value == DEFAULT_MIN_VOLUME_VALUE
        assert c.blacklist == ()

    def test_top_n_clamped(self):
        assert SelectorConfig.from_dict({"top_n": 0}).top_n == MIN_TOP_N
        assert SelectorConfig.from_dict({"top_n": 999}).top_n == MAX_TOP_N

    def test_invalid_market_falls_back(self):
        assert SelectorConfig.from_dict({"market": "NASDAQ"}).market == "ALL"

    def test_lowercase_market_upper(self):
        assert SelectorConfig.from_dict({"market": "kospi"}).market == "KOSPI"

    def test_blacklist_normalization(self):
        c = SelectorConfig.from_dict({"blacklist": [" 005930 ", "", "000660"]})
        assert c.blacklist == ("005930", "000660")


@pytest.mark.asyncio
class TestSelectTickers:
    async def test_end_to_end_top_n(self):
        universe = [
            _c("005930", "삼성전자", price=70_000, volume_value=500_000_000_000),
            _c("005935", "삼성전자우", price=55_000, volume_value=200_000_000_000),
            _c("000660", "SK하이닉스", price=180_000, volume_value=400_000_000_000),
            _c("035420", "NAVER", price=200_000, volume_value=150_000_000_000),
            _c("LOW", "저거래", price=10_000, volume_value=1_000_000_000),
        ]

        async def loader(_market):
            return universe

        result = await select_tickers(
            SelectorConfig.from_dict({"top_n": 3, "min_volume_value": 10_000_000_000}),
            available_cash=Decimal("500000"),
            total_eval=Decimal("5000000"),
            max_position_pct=Decimal("0.20"),
            loader=loader,
        )
        # limit = min(50만, 500만×0.2=100만) = 50만.
        # 우선주(005935) 제외, 저거래(LOW) 컷. 나머지 3종목은 모두 50만 이하.
        # 거래대금 순: 삼성(5000억), SK(4000억), NAVER(1500억).
        assert result.rule_version == RULE_VERSION
        assert [s.ticker for s in result.selected] == ["005930", "000660", "035420"]
        assert any(e.reason == "preferred" for e in result.excluded_sample)
        assert any(e.reason == "below_min_volume" for e in result.excluded_sample)

    async def test_blacklist_excluded(self):
        universe = [
            _c("005930", "삼성전자", volume_value=500_000_000_000),
            _c("000660", "SK하이닉스", volume_value=400_000_000_000),
        ]

        async def loader(_m):
            return universe

        result = await select_tickers(
            SelectorConfig.from_dict(
                {"top_n": 5, "blacklist": ["005930"], "min_volume_value": 0}
            ),
            available_cash=Decimal("10000000"),
            total_eval=Decimal("10000000"),
            max_position_pct=Decimal("0.50"),
            loader=loader,
        )
        assert [s.ticker for s in result.selected] == ["000660"]
        assert any(
            e.ticker == "005930" and e.reason == "blacklist"
            for e in result.excluded_sample
        )

    async def test_seed_too_small_empty_result(self):
        universe = [_c("005930", "삼성전자", price=70_000, volume_value=10**12)]

        async def loader(_m):
            return universe

        result = await select_tickers(
            SelectorConfig.from_dict({"top_n": 5, "min_volume_value": 0}),
            available_cash=Decimal("1000"),  # 너무 작음
            total_eval=Decimal("1000"),
            max_position_pct=Decimal("0.20"),
            loader=loader,
        )
        assert result.selected == []
        assert any(e.reason == "price_over_seed" for e in result.excluded_sample)
