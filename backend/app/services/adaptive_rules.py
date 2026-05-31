"""모듈 C — Adaptive Rules 서비스

주간 메타 분석으로 자동 진화 규칙을 생성하고,
매 트레이딩 사이클에서 LLM 프롬프트에 활성 규칙을 주입한다.

CRUD 함수 + `run_weekly_meta_analysis` (핵심 분석 로직).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trading import (
    AdaptiveRule,
    StrategyType,
    TradingDecision,
    TradingStrategy,
)
from app.services.alert_service import send_telegram_message
from app.services.crypto_service import decrypt_decimal_optional
from app.services.llm_advisor import (
    LLMAPIError,
    LLMConfigError,
    _parse_llm_json,
    call_llm,
    llm_provider_configured,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────


async def get_active_rules(db: AsyncSession, strategy_id: UUID) -> list[str]:
    """활성 + 미만료 규칙의 rule_text 리스트.

    trading_cycle에서 LLM 프롬프트에 주입하는 용도.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(AdaptiveRule.rule_text)
        .where(
            AdaptiveRule.strategy_id == strategy_id,
            AdaptiveRule.is_active.is_(True),
        )
        .where(
            # expires_at이 NULL이면 무기한 유효
            (AdaptiveRule.expires_at.is_(None)) | (AdaptiveRule.expires_at > now)
        )
        .order_by(AdaptiveRule.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_rules(
    db: AsyncSession,
    strategy_id: UUID,
    active_only: bool = False,
) -> list[AdaptiveRule]:
    """전략별 규칙 목록 조회."""
    stmt = (
        select(AdaptiveRule)
        .where(AdaptiveRule.strategy_id == strategy_id)
    )
    if active_only:
        now = datetime.now(timezone.utc)
        stmt = stmt.where(
            AdaptiveRule.is_active.is_(True),
            (AdaptiveRule.expires_at.is_(None)) | (AdaptiveRule.expires_at > now),
        )
    stmt = stmt.order_by(AdaptiveRule.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def deactivate_rule(db: AsyncSession, rule_id: UUID) -> AdaptiveRule | None:
    """단건 비활성화 (사용자 수동)."""
    rule = await db.get(AdaptiveRule, rule_id)
    if rule is None:
        return None
    rule.is_active = False
    return rule


async def deactivate_expired_rules(db: AsyncSession, strategy_id: UUID) -> int:
    """만료된 규칙 일괄 비활성화. 비활성화 건수 반환."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(AdaptiveRule)
        .where(
            AdaptiveRule.strategy_id == strategy_id,
            AdaptiveRule.is_active.is_(True),
            AdaptiveRule.expires_at.isnot(None),
            AdaptiveRule.expires_at <= now,
        )
    )
    result = await db.execute(stmt)
    expired = result.scalars().all()
    for rule in expired:
        rule.is_active = False
    return len(expired)


async def create_rules(
    db: AsyncSession,
    strategy_id: UUID,
    rules: list[dict[str, str]],
    generated_from: str = "weekly_meta_analysis",
) -> list[AdaptiveRule]:
    """메타 분석 결과 규칙 일괄 생성.

    Args:
        rules: [{"rule_text": "...", "rationale": "..."}, ...]
        generated_from: 규칙 출처 태그
    """
    # 전략 행을 FOR UPDATE로 잠가 동시 create_rules 호출 간 version 경합 방지.
    # 같은 트랜잭션 내에서 max(version) 조회 → INSERT가 원자적으로 수행된다.
    from app.models.trading import TradingStrategy
    await db.execute(
        select(TradingStrategy.id)
        .where(TradingStrategy.id == strategy_id)
        .with_for_update()
    )
    version_stmt = (
        select(func.coalesce(func.max(AdaptiveRule.version), 0))
        .where(AdaptiveRule.strategy_id == strategy_id)
    )
    current_max = (await db.execute(version_stmt)).scalar() or 0
    version = current_max + 1

    ttl = timedelta(days=settings.adaptive_rule_ttl_days)
    now = datetime.now(timezone.utc)

    created: list[AdaptiveRule] = []
    for item in rules:
        rule_text = item.get("rule_text", "").strip()
        if not rule_text:
            continue
        rule = AdaptiveRule(
            strategy_id=strategy_id,
            version=version,
            rule_text=rule_text,
            rationale=item.get("rationale", "").strip() or None,
            generated_from=generated_from,
            is_active=True,
            expires_at=now + ttl,
        )
        db.add(rule)
        created.append(rule)
    return created


# ──────────────────────────────────────────────
# 주간 메타 분석
# ──────────────────────────────────────────────

META_SYSTEM_PROMPT = """당신은 한국 주식 자동매매 시스템의 성과 분석 전문가이다.

지난 7일간의 매매 의사결정 기록을 분석해 다음 주에 적용할 규칙을 제안한다.

원칙:
- 반복되는 손실 패턴을 식별하라. (특정 종목, 시간대, 지표 조합 등)
- 성공 패턴도 식별해 강화하라.
- 규칙은 구체적이고 실행 가능해야 한다. ("주의하라" 같은 추상적 규칙 금지)
- 기존 활성 규칙과 중복되거나 모순되는 규칙은 제안하지 마라.
- 데이터가 부족하면(매매 건수 5건 미만) 규칙을 줄이거나 빈 배열을 반환하라.

반드시 아래 JSON 배열로만 응답하라. 다른 텍스트 금지.
[
  {
    "rule_text": "구체적인 규칙 내용 (한국어, 1~2문장)",
    "rationale": "이 규칙을 제안하는 이유 (데이터 근거 포함)"
  }
]
최대 {max_rules}개까지. 데이터 부족 시 빈 배열 [] 허용.
"""


# 프롬프트에 포함할 최대 의사결정 상세 건수 (토큰 절약)
_MAX_DECISION_DETAIL = 50


def _build_meta_analysis_message(
    decisions: list[TradingDecision],
    active_rules: list[str],
    strategy_name: str,
) -> str:
    """메타 분석 프롬프트의 사용자 메시지 구성."""
    # 전체 집계 (모든 건 대상)
    total = len(decisions)
    executed_count = 0
    buy_count = 0
    sell_count = 0
    hold_count = 0
    blocked_count = 0
    confidence_sum = 0

    for d in decisions:
        confidence_sum += d.confidence
        if d.executed:
            executed_count += 1
        if d.blocked_reason:
            blocked_count += 1
        if d.action == "buy":
            buy_count += 1
        elif d.action == "sell":
            sell_count += 1
        elif d.action == "hold":
            hold_count += 1

    avg_confidence = confidence_sum / total if total > 0 else 0

    # 상세 목록은 최근 N건만 (프롬프트 크기 제한)
    shown = decisions[:_MAX_DECISION_DETAIL]
    decision_lines: list[str] = []
    for d in shown:
        exec_tag = "✓" if d.executed else "·"
        blocked = f" [차단: {d.blocked_reason}]" if d.blocked_reason else ""
        decision_lines.append(
            f"- {exec_tag} {d.created_at.strftime('%m-%d %H:%M')} "
            f"{d.ticker} {d.action} (conf={d.confidence}) "
            f"— {(d.reason or '')[:120]}{blocked}"
        )

    detail_header = "## 의사결정 상세 (최신순"
    if total > _MAX_DECISION_DETAIL:
        detail_header += f", 최근 {_MAX_DECISION_DETAIL}건 / 전체 {total}건"
    detail_header += ")\n" + "\n".join(decision_lines)

    sections = [
        f"## 전략: {strategy_name}",
        f"## 7일간 집계\n"
        f"총 {total}건: buy {buy_count} / sell {sell_count} / hold {hold_count}\n"
        f"실제 발주 {executed_count}건, 차단 {blocked_count}건\n"
        f"평균 confidence: {avg_confidence:.1f}",
        detail_header,
    ]

    if active_rules:
        sections.append(
            "## 현재 활성 규칙 (중복/모순 금지)\n"
            + "\n".join(f"- {r}" for r in active_rules)
        )
    else:
        sections.append("## 현재 활성 규칙\n없음")

    sections.append(
        "위 데이터를 분석해 다음 주에 적용할 규칙을 JSON 배열로 제안하라."
    )
    return "\n\n".join(sections)


async def run_weekly_meta_analysis(
    db: AsyncSession,
    strategy: TradingStrategy,
) -> list[AdaptiveRule]:
    """단일 전략에 대한 주간 메타 분석 실행.

    1. 지난 7일 TradingDecision 조회
    2. 만료 규칙 비활성화
    3. LLM API로 신규 규칙 생성
    4. DB 저장 + 텔레그램 알림

    Returns:
        생성된 AdaptiveRule 리스트 (빈 리스트 가능)
    """
    if not llm_provider_configured():
        logger.warning(
            "Meta-analysis skipped: LLM provider %r key not set",
            settings.llm_provider,
        )
        return []

    # 1. 만료 규칙 비활성화 (의사결정 유무와 무관하게 항상 실행)
    expired_count = await deactivate_expired_rules(db, strategy.id)
    if expired_count > 0:
        logger.info(
            "Deactivated %d expired rules: strategy=%s",
            expired_count, strategy.id,
        )

    # 2. 지난 7일 의사결정 조회
    window_start = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = (
        select(TradingDecision)
        .where(
            TradingDecision.strategy_id == strategy.id,
            TradingDecision.created_at >= window_start,
        )
        .order_by(TradingDecision.created_at.desc())
    )
    decisions = list((await db.execute(stmt)).scalars().all())

    if not decisions:
        logger.info(
            "Meta-analysis skipped (no decisions): strategy=%s", strategy.id,
        )
        return []

    # 3. 현재 활성 규칙 조회 (프롬프트에 중복 방지용)
    active_rules = await get_active_rules(db, strategy.id)

    # 4. LLM API 호출
    max_rules = settings.meta_analysis_max_rules
    system_prompt = META_SYSTEM_PROMPT.format(max_rules=max_rules)
    user_msg = _build_meta_analysis_message(
        decisions, active_rules, strategy.name,
    )

    try:
        response = await call_llm(
            system_prompt=system_prompt,
            user_message=user_msg,
            model=settings.meta_analysis_model,
            max_tokens=1024,
            timeout_seconds=30.0,
        )
    except LLMConfigError as e:
        logger.warning(
            "Meta-analysis config error: strategy=%s err=%s", strategy.id, e,
        )
        return []
    except LLMAPIError as e:
        logger.warning(
            "Meta-analysis API error: strategy=%s status=%s",
            strategy.id, e.status_code,
        )
        return []
    except httpx.HTTPError as e:
        logger.warning("Meta-analysis HTTP error: strategy=%s err=%s", strategy.id, e)
        return []

    # 5. 응답 파싱
    try:
        parsed = _parse_meta_response(response.text)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        logger.warning(
            "Meta-analysis parse error: strategy=%s err=%s", strategy.id, e,
        )
        return []

    # 6. 규칙 생성
    if not parsed:
        logger.info("Meta-analysis returned no rules: strategy=%s", strategy.id)
        return []

    # max_rules 초과 방지
    parsed = parsed[:max_rules]
    created = await create_rules(db, strategy.id, parsed)

    # 7. 텔레그램 알림
    if created:
        rules_text = "\n".join(
            f"- {r.rule_text}" for r in created
        )
        try:
            await send_telegram_message(
                f"📊 [주간 메타 분석 완료]\n"
                f"전략: {strategy.name}\n"
                f"분석 대상: {len(decisions)}건 (7일)\n"
                f"만료 규칙 정리: {expired_count}건\n"
                f"신규 규칙 {len(created)}건:\n{rules_text}"
            )
        except Exception:
            logger.exception("Failed to send meta-analysis telegram alert")

    logger.info(
        "Meta-analysis completed: strategy=%s decisions=%d new_rules=%d expired=%d",
        strategy.id, len(decisions), len(created), expired_count,
    )
    return created


def _parse_meta_response(text: str) -> list[dict[str, str]]:
    """메타 분석 LLM 응답에서 규칙 배열 추출.

    배열 응답(`[...]`)과 객체 래핑(`{"rules": [...]}`) 모두 처리.
    """
    text = text.strip()
    # 코드블록 펜스 제거
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 배열 직접 파싱 시도
    if text.startswith("["):
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return _validate_rules(parsed)

    # 객체 래핑 시도 ({"rules": [...]})
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            for key in ("rules", "adaptive_rules"):
                if isinstance(obj.get(key), list):
                    return _validate_rules(obj[key])
    except json.JSONDecodeError:
        pass

    # 마지막 폴백: 중괄호/대괄호 범위 추출
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, list):
            return _validate_rules(parsed)

    raise ValueError("응답에 규칙 배열이 없음")


def _validate_rules(items: list) -> list[dict[str, str]]:
    """규칙 배열 유효성 검증."""
    valid: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rule_text = str(item.get("rule_text", "")).strip()
        if not rule_text:
            continue
        valid.append({
            "rule_text": rule_text[:500],
            "rationale": str(item.get("rationale", "")).strip()[:500],
        })
    return valid
