"""LLM 어드바이저 — Stage 3 모듈 A 코어

Anthropic Claude API에 구조화 입력을 보내고 매수/매도/홀드 의사결정을 받는다.
- 출력은 엄격한 JSON 스키마. 파싱 실패 시 안전 모드(hold)로 폴백.

비용/지연이 있는 외부 호출이므로 호출자가 결과를 TradingDecision 행으로
저장하도록 분리되어 있다 — 본 모듈은 DB I/O를 수행하지 않는다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings
from app.services.decision_memory import DecisionMemory

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"

# 안전 폴백 — API 키 미설정/네트워크 실패/파싱 실패 시 사용
_SAFE_HOLD_REASON_PREFIX = "[안전 폴백] "


@dataclass
class LLMDecision:
    """LLM 의사결정 결과 (TradingDecision 행과 1:1 매핑)."""

    action: str  # "buy" | "sell" | "hold"
    confidence: int  # 0~100
    reason: str
    suggested_quantity: int | None = None
    suggested_amount: Decimal | None = None
    market_regime: str | None = None
    used_indicators: dict[str, Any] | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_response: str | None = None  # 디버그용


@dataclass
class PortfolioContext:
    """LLM에 주입할 계좌/포지션 스냅샷."""

    cash: Decimal
    total_eval: Decimal
    holdings: list[dict[str, Any]] = field(default_factory=list)
    # holdings 항목: {ticker, ticker_name, quantity, avg_buy_price, current_price, unrealized_pnl}


SYSTEM_PROMPT = """당신은 한국 주식 시장에서 10년 이상 경험을 쌓은 전문 트레이더이다.
주어진 종목의 가격/거래량 시계열, 사용자의 포트폴리오 상태, 가용 자본을 종합해
지금 이 순간 매수(buy)/매도(sell)/홀드(hold) 중 무엇을 해야 하는지 결정한다.

원칙:
- 확신이 없으면 hold. 무리한 거래는 금물.
- confidence 0~100. 70 미만은 시스템이 자동으로 발주를 차단한다.
- 매수 제안 시 suggested_quantity는 가용 현금과 적절한 비중(보통 5~15%)을 고려.
- 매도는 보유 중인 종목에만 가능. 보유 수량을 초과하지 마라.
- 단일 지표 맹신 금지. 가격/거래량 변화, 추세, 변동성을 종합 판단하라.
- 한국 시장 특성(개별 호재/공시 부재 시 추세 추종이 약함)을 감안하라.

반드시 아래 JSON 스키마로만 응답하라. 다른 텍스트 금지.
{
  "action": "buy" | "sell" | "hold",
  "confidence": 0~100 정수,
  "reason": "한국어 간결한 근거 (1~3문장)",
  "suggested_quantity": 정수 또는 null,
  "market_regime": "uptrend" | "downtrend" | "sideways" | "volatile" | null,
  "used_indicators": { "key": "value", ... }
}
"""


def _format_price_history(price_history: list[dict]) -> str:
    """프롬프트에 주입할 시세 요약 — 토큰 절약을 위해 최근 30일만."""
    recent = price_history[-30:]
    lines = ["date,open,high,low,close,volume"]
    for row in recent:
        lines.append(
            f"{row.get('date','')},"
            f"{row.get('open','')},"
            f"{row.get('high','')},"
            f"{row.get('low','')},"
            f"{row.get('close','')},"
            f"{row.get('volume','')}"
        )
    return "\n".join(lines)


def _build_user_message(
    ticker: str,
    ticker_name: str,
    price_history: list[dict],
    portfolio: PortfolioContext,
    memory: DecisionMemory | None,
    adaptive_rules: list[str] | None,
    similar_cases: str | None = None,
) -> str:
    """사용자 메시지 본문 작성."""
    held = next(
        (h for h in portfolio.holdings if h.get("ticker") == ticker), None
    )
    holding_block = (
        f"보유: {held['quantity']}주, 평단 {held['avg_buy_price']}원, "
        f"현재가 {held.get('current_price','?')}원, 평가손익 {held.get('unrealized_pnl','?')}원"
        if held
        else "현재 미보유"
    )

    sections = [
        f"## 종목\n{ticker_name or ticker} ({ticker})",
        f"## 일별 시세 (최근 30일)\n{_format_price_history(price_history)}",
        f"## 계좌 상태\n현금: {portfolio.cash:,.0f}원\n총평가: {portfolio.total_eval:,.0f}원\n{holding_block}",
        f"## 보유 종목 수\n{len(portfolio.holdings)}",
    ]

    if memory and not memory.is_empty:
        # 모듈 B: 최근 의사결정 + 집계
        if memory.summary:
            sections.append("## 최근 활동 요약\n" + memory.summary)
        if memory.recent:
            history_lines = []
            for d in memory.recent:
                exec_tag = "✓" if d.get("executed") else "·"
                blocked = d.get("blocked_reason")
                tail = f" [차단: {blocked}]" if blocked else ""
                history_lines.append(
                    f"- {exec_tag} {d.get('created_at','')[:19]} "
                    f"{d.get('ticker','')} {d.get('action','')} "
                    f"(conf={d.get('confidence','?')}) — {d.get('reason','')}{tail}"
                )
            sections.append(
                "## 최근 의사결정 이력 (최신순, ✓=발주됨, ·=차단/hold)\n"
                + "\n".join(history_lines)
                + "\n\n위 이력을 참고해 같은 종목에서 단기 반복 매매·"
                  "방금 차단된 신호를 무리하게 재시도하는 행동을 피하라."
            )

    if similar_cases:
        # 모듈 D: RAG 유사 과거 사례
        sections.append(
            "## 유사 과거 사례 (벡터 검색 결과)\n"
            + similar_cases
            + "\n\n위 유사 사례의 승패 기록을 참고해 현재 판단의 신뢰도를 조정하라."
        )

    if adaptive_rules:
        # 모듈 C: 누적 학습 규칙
        sections.append(
            "## 누적 학습 규칙 (반드시 준수)\n"
            + "\n".join(f"- {r}" for r in adaptive_rules)
        )

    sections.append(
        "위 정보를 바탕으로 지금 어떻게 행동할지 JSON으로만 답하라."
    )
    return "\n\n".join(sections)


def _parse_llm_json(text: str) -> dict[str, Any]:
    """LLM 응답에서 JSON 객체 추출.

    Claude는 보통 깔끔한 JSON을 반환하지만, 코드블록(```json)으로 감쌀 수 있어
    가장 바깥 중괄호 쌍을 추출하는 보수적 파서를 사용한다.
    """
    text = text.strip()
    # 코드블록 펜스 제거 — 내부 백틱은 보존하기 위해 줄 단위로 처리
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # 첫/마지막 중괄호로 잘라냄
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("응답에 JSON 객체가 없음")
    return json.loads(text[start : end + 1])


def _validate_decision(parsed: dict[str, Any]) -> LLMDecision:
    """파싱된 dict를 LLMDecision으로 검증/변환."""
    action = str(parsed.get("action", "")).lower().strip()
    if action not in ("buy", "sell", "hold"):
        raise ValueError(f"잘못된 action: {action!r}")

    raw_conf = parsed.get("confidence")
    try:
        confidence = int(raw_conf)
    except (TypeError, ValueError) as err:
        raise ValueError(f"잘못된 confidence: {raw_conf!r}") from err
    confidence = max(0, min(100, confidence))

    reason = str(parsed.get("reason", "")).strip() or "(이유 없음)"

    sq_raw = parsed.get("suggested_quantity")
    suggested_quantity: int | None = None
    if sq_raw is not None:
        try:
            sq = int(sq_raw)
            if sq > 0:
                suggested_quantity = sq
        except (TypeError, ValueError):
            suggested_quantity = None

    return LLMDecision(
        action=action,
        confidence=confidence,
        reason=reason[:1000],
        suggested_quantity=suggested_quantity,
        market_regime=parsed.get("market_regime"),
        used_indicators=parsed.get("used_indicators")
        if isinstance(parsed.get("used_indicators"), dict)
        else None,
    )


def _safe_hold(reason: str) -> LLMDecision:
    return LLMDecision(
        action="hold",
        confidence=0,
        reason=_SAFE_HOLD_REASON_PREFIX + reason,
    )


async def get_llm_decision(
    ticker: str,
    ticker_name: str,
    price_history: list[dict],
    portfolio: PortfolioContext,
    memory: DecisionMemory | None = None,
    adaptive_rules: list[str] | None = None,
    similar_cases: str | None = None,
) -> LLMDecision:
    """Claude API를 호출해 의사결정을 받는다.

    실패(API 키 없음, 네트워크 오류, 파싱 실패 등)는 모두 hold로 폴백한다.
    호출자(=trading_cycle)가 결과를 TradingDecision으로 저장한다.
    """
    if not settings.anthropic_api_key:
        return _safe_hold("ANTHROPIC_API_KEY 미설정")

    if not price_history:
        return _safe_hold("시세 데이터 없음")

    user_msg = _build_user_message(
        ticker, ticker_name, price_history, portfolio,
        memory, adaptive_rules, similar_cases,
    )

    body = {
        "model": settings.llm_advisor_model,
        "max_tokens": settings.llm_advisor_max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.llm_advisor_timeout_seconds
        ) as client:
            resp = await client.post(ANTHROPIC_API_URL, json=body, headers=headers)
    except httpx.HTTPError as e:
        logger.warning("LLM advisor HTTP error for %s: %s", ticker, e)
        return _safe_hold(f"HTTP 오류: {type(e).__name__}")

    if resp.status_code != 200:
        # 키/시크릿이 본문에 섞여 있을 수 있어 코드만 로깅
        logger.warning(
            "LLM advisor non-200 for %s: status=%s", ticker, resp.status_code,
        )
        return _safe_hold(f"API status={resp.status_code}")

    try:
        payload = resp.json()
        content_blocks = payload.get("content", [])
        text = "".join(
            b.get("text", "") for b in content_blocks if b.get("type") == "text"
        )
        parsed = _parse_llm_json(text)
        decision = _validate_decision(parsed)
        usage = payload.get("usage", {})
        decision.model = payload.get("model")
        decision.input_tokens = usage.get("input_tokens")
        decision.output_tokens = usage.get("output_tokens")
        decision.raw_response = text[:2000]
        return decision
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        logger.warning("LLM advisor parse error for %s: %s", ticker, e)
        return _safe_hold(f"파싱 실패: {type(e).__name__}")
