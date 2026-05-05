"""V5 Phase 8 + 8A — Strategic Mode Router.

REFACTOR_V5_PLAN.md §17.2 + §18.2 의 전략 질의 감지 + KILL_RULES_STRATEGIC.

[감지 — 3-경로 우선순위]
    1. 명시 prefix (Plan §18.2)     — `?전략 ...` / `?분석 ...` 등 7종
    2. STRATEGIC_PATTERNS (§17.2)    — 8종 정규식
    3. LLM intent classifier         — fallback (ContextAnalyst 와 함께)

prefix 가 있으면 *나머지 경로 무시*. AP-V5-23 — 모호 시 분석 모드 기본값.

[KILL_RULES_STRATEGIC — Plan §17.6 + §18.4]
전략 모드는 분석 모드 KILL_RULES (논리 5 + 시각 3) 외에 추가:
- options_too_few              (< 3 — 단 옵션 0 은 hold + 안내, AP-V5-18 갱신)
- no_decision_matrix
- recommendation_absent        (rationale < 50자)
- premortem_missing_deep
- criteria_not_user_aligned
- decision_statement_missing   (Plan §18.4)
- action_plan_missing
- kill_switch_missing
- matrix_score_uniform         (가중치 무관 동일 점수)

전략 모드 KILL 은 *단독 발화* (분석 모드의 "둘 이상" 정책과 다름).

Public API:
    from src.agents.strategic_router import (
        EXPLICIT_PREFIXES,
        STRATEGIC_PATTERNS,
        ModeRouting,
        detect_strategic_intent,
        parse_explicit_prefix,
        route_query,
        run_strategic_kill_rules,
        evaluate_strategic_mode,
    )
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from src.state.models import StrategicReport

logger = logging.getLogger(__name__)


# ─── Plan §18.2 — 명시 Prefix 7종 SSOT ─────────────────────────────


PrefixMode = Literal[
    "strategic", "analytical", "forecast", "comparative",
    "geo_priority", "fast", "deep",
]


# 정규식 매칭은 *prefix 시작* 전용 — 본문 안에 박혀 있으면 무시.
EXPLICIT_PREFIXES: dict[str, PrefixMode] = {
    "?전략": "strategic",
    "/strategy": "strategic",
    "?분석": "analytical",
    "?예측": "forecast",
    "?비교": "comparative",
    "?지도": "geo_priority",
    "?짧게": "fast",
    "?심층": "deep",
}


_PREFIX_PATTERN = re.compile(
    r"^\s*(\?(?:전략|분석|예측|비교|지도|짧게|심층)|/strategy)\b\s*",
    re.UNICODE,
)


# ─── Plan §17.2 — STRATEGIC_PATTERNS 8종 SSOT ──────────────────────


STRATEGIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"어떤 전략"),
    re.compile(r"어떻게 해야"),
    re.compile(r"어떤 (선택|결정|판단|길)"),
    re.compile(r"취해야 (하|할)"),
    re.compile(r"(고려|반영)했을 때.{0,30}(전략|결정|선택)"),
    re.compile(r"옵션.{0,10}(평가|비교|선택)"),
    re.compile(r"(어느 쪽|어디로|어느 방향)으로"),
    re.compile(r"vs[.\s]"),
]


# ─── ModeRouting 결과 ─────────────────────────────────────────────


@dataclass
class ModeRouting:
    """route_query() 의 결과 — 어떤 mode 로 분기할지 + 신호."""

    mode: Literal["strategic", "analytical"] = "analytical"
    fast_or_deep: Literal["fast", "standard", "deep"] | None = None
    geo_priority: bool = False
    forecast_hint: bool = False
    comparative_hint: bool = False
    detection_source: Literal[
        "explicit_prefix", "pattern", "llm_intent", "default",
    ] = "default"
    matched_prefix: str = ""
    matched_patterns: list[str] = field(default_factory=list)
    cleaned_query: str = ""              # prefix 제거된 본문


# ─── Detection 함수 ───────────────────────────────────────────────


def parse_explicit_prefix(user_request: str) -> tuple[PrefixMode | None, str, str]:
    """Plan §18.2 — 명시 prefix 파싱.

    Returns:
        (prefix_mode, matched_prefix, cleaned_query).
        prefix 없으면 (None, "", user_request).
    """
    if not user_request:
        return None, "", ""
    m = _PREFIX_PATTERN.match(user_request)
    if not m:
        return None, "", user_request
    matched = m.group(1)
    mode = EXPLICIT_PREFIXES.get(matched)
    if mode is None:
        return None, "", user_request
    cleaned = user_request[m.end():].strip()
    return mode, matched, cleaned


def detect_strategic_intent(user_request: str) -> tuple[bool, list[str]]:
    """Plan §17.2 (나) — STRATEGIC_PATTERNS 8종 결정적 매칭.

    Returns:
        (is_strategic, matched_pattern_strings).
    """
    if not user_request:
        return False, []
    matched: list[str] = []
    for pat in STRATEGIC_PATTERNS:
        if pat.search(user_request):
            matched.append(pat.pattern)
    return bool(matched), matched


def route_query(
    user_request: str,
    *,
    llm_user_intent: str | None = None,
) -> ModeRouting:
    """Plan §17.2 + §18.2 의 통합 router.

    우선순위:
        1. 명시 prefix → 즉시 그 mode
        2. 패턴 매칭 + (LLM intent 가 strategic 또는 None) → strategic
        3. LLM intent="what_to_do" → strategic
        4. 그 외 → analytical (AP-V5-23 fallback)

    Args:
        user_request: 텔레그램 사용자 메시지 원문.
        llm_user_intent: ContextAnalyst 의 intent classifier 결과 (선택).
            "what_to_do" / "what_happened" / "what_next" 등.
    """
    routing = ModeRouting(cleaned_query=user_request or "")

    # 1. 명시 prefix
    prefix_mode, matched_prefix, cleaned = parse_explicit_prefix(user_request)
    if prefix_mode is not None:
        routing.matched_prefix = matched_prefix
        routing.cleaned_query = cleaned
        routing.detection_source = "explicit_prefix"

        if prefix_mode == "strategic":
            routing.mode = "strategic"
        elif prefix_mode == "analytical":
            routing.mode = "analytical"
        elif prefix_mode == "forecast":
            routing.mode = "analytical"
            routing.forecast_hint = True
        elif prefix_mode == "comparative":
            routing.mode = "analytical"
            routing.comparative_hint = True
        elif prefix_mode == "geo_priority":
            routing.mode = "analytical"
            routing.geo_priority = True
        elif prefix_mode == "fast":
            routing.mode = "analytical"
            routing.fast_or_deep = "fast"
        elif prefix_mode == "deep":
            routing.mode = "analytical"
            routing.fast_or_deep = "deep"
        return routing

    # 2. 패턴 매칭.
    pattern_strategic, matched = detect_strategic_intent(user_request or "")
    routing.matched_patterns = matched

    # 3. LLM intent.
    intent = (llm_user_intent or "").lower().strip()
    intent_strategic = intent == "what_to_do"

    # 결정 — 패턴 또는 intent 가 strategic 신호.
    if pattern_strategic and intent_strategic:
        routing.mode = "strategic"
        routing.detection_source = "explicit_prefix" if False else (
            "pattern" if pattern_strategic else "llm_intent"
        )
    elif pattern_strategic:
        routing.mode = "strategic"
        routing.detection_source = "pattern"
    elif intent_strategic:
        routing.mode = "strategic"
        routing.detection_source = "llm_intent"
    else:
        # AP-V5-23 — 모호 시 분석 모드 기본값.
        routing.mode = "analytical"
        routing.detection_source = "default"

    return routing


# ─── Plan §17.6 + §18.4 — KILL_RULES_STRATEGIC ────────────────────


# 옵션 매트릭스의 모든 점수가 동일 → 분석 무의미.
def _is_matrix_uniform(scores: list[list[float]]) -> bool:
    """모든 옵션 × 모든 기준 의 점수가 정확히 동일 → KILL."""
    if not scores:
        return False
    flat = [v for row in scores for v in row if isinstance(v, (int, float))]
    if not flat:
        return False
    return len(set(flat)) == 1


def _all_user_criteria_present(
    criteria: list[Any],
    user_provided: list[str],
) -> bool:
    """사용자 명시 기준 (A, B, C) 가 평가 매트릭스에 *모두* 있는지."""
    if not user_provided:
        return True
    matrix_names = set()
    for c in criteria:
        if isinstance(c, str):
            matrix_names.add(c.lower())
        else:
            name = getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
            if name:
                matrix_names.add(str(name).lower())
    for u in user_provided:
        if u.lower() not in matrix_names:
            return False
    return True


def run_strategic_kill_rules(
    report: StrategicReport | dict[str, Any],
    *,
    mode: str = "standard",
) -> list[str]:
    """Plan §17.6 + §18.4 — 전략 모드 KILL_RULES.

    분석 모드와 다른 정책 — *단독 발화* 시 KILL (둘 이상 불필요).

    Args:
        report: StrategicReport 인스턴스 또는 dict.
        mode: fast / standard / deep — premortem_missing_deep 임계.

    Returns:
        triggered rule 이름 list. 빈 list = 통과.
    """
    triggered: list[str] = []

    # dict / model 양쪽 지원.
    def _get(field_name: str, default: Any = None) -> Any:
        if isinstance(report, dict):
            return report.get(field_name, default)
        return getattr(report, field_name, default)

    options = _get("options", []) or []
    n_opts = len(options)

    # AP-V5-18 갱신 (Plan §18.4) — 옵션 정책 완화.
    # 0개 → hold (KILL 아님). 1~5개 → 허용. 6+ → KILL.
    if n_opts >= 6:
        triggered.append("options_too_many")
    elif n_opts == 0:
        # KILL 이 아닌 hold 신호 — 별도 marker.
        triggered.append("options_zero_hold")
    elif 1 <= n_opts < 3:
        # AP-V5-18 갱신 — 1~2개도 허용 (단 1개는 단일 옵션 권고 명시 필요).
        # KILL 발화 X.
        pass

    # decision_matrix 부재.
    dm = _get("decision_matrix")
    if dm is None:
        triggered.append("no_decision_matrix")
    else:
        # dict / model 양쪽.
        scores = (
            dm.get("scores") if isinstance(dm, dict)
            else getattr(dm, "scores", None)
        ) or []
        if not scores:
            triggered.append("no_decision_matrix")
        elif _is_matrix_uniform(scores):
            triggered.append("matrix_score_uniform")

    # 권고 부재 / rationale < 50자.
    rec = _get("recommendation")
    if rec is None:
        triggered.append("recommendation_absent")
    else:
        rationale = (
            rec.get("rationale") if isinstance(rec, dict)
            else getattr(rec, "rationale", "")
        )
        if not rationale or len(rationale.strip()) < 50:
            triggered.append("recommendation_absent")

    # premortem_missing_deep
    if mode == "deep":
        any_premortem = any(
            (
                opt.get("pre_mortem") if isinstance(opt, dict)
                else getattr(opt, "pre_mortem", [])
            )
            for opt in options
        )
        if not any_premortem:
            triggered.append("premortem_missing_deep")

    # criteria_not_user_aligned
    user_criteria = _get("user_provided_criteria", []) or []
    criteria = _get("criteria", []) or []
    if user_criteria and not _all_user_criteria_present(criteria, user_criteria):
        triggered.append("criteria_not_user_aligned")

    # Plan §18.4 추가 KILL_RULES.
    if not _get("decision_statement", "").strip():
        triggered.append("decision_statement_missing")

    action_plan = _get("action_plan_30_60_90")
    if action_plan is None:
        triggered.append("action_plan_missing")
    else:
        d30 = (
            action_plan.get("days_30") if isinstance(action_plan, dict)
            else getattr(action_plan, "days_30", [])
        ) or []
        d60 = (
            action_plan.get("days_60") if isinstance(action_plan, dict)
            else getattr(action_plan, "days_60", [])
        ) or []
        d90 = (
            action_plan.get("days_90") if isinstance(action_plan, dict)
            else getattr(action_plan, "days_90", [])
        ) or []
        if not (d30 or d60 or d90):
            triggered.append("action_plan_missing")

    if not (_get("kill_switch_conditions", []) or []):
        triggered.append("kill_switch_missing")

    return triggered


# ─── 통합 entry — evaluate_strategic_mode ────────────────────────


@dataclass
class StrategicEvaluation:
    """전략 모드 보고서의 KILL 평가 결과."""

    decision: Literal["publish", "hold", "kill"]
    triggered_rules: list[str] = field(default_factory=list)
    hold_reason: str = ""


def evaluate_strategic_mode(
    report: StrategicReport | dict[str, Any],
    *,
    mode: str = "standard",
) -> StrategicEvaluation:
    """전략 모드 보고서의 KILL_RULES 통합 평가.

    옵션 0개 → hold (Plan §18.4 갱신).
    그 외 KILL_RULE 발화 시 → kill.
    아무 발화 없으면 publish.
    """
    triggered = run_strategic_kill_rules(report, mode=mode)

    if "options_zero_hold" in triggered:
        # 옵션 도출 불가 — hold + 사용자 안내.
        return StrategicEvaluation(
            decision="hold",
            triggered_rules=triggered,
            hold_reason=(
                "전략 질의 성립 불가 — 옵션 0개. 질의를 더 구체화하거나 "
                "?분석 prefix 로 재시도 권장."
            ),
        )

    # AP-V5-18 갱신 — options_too_many (>=6) 도 KILL.
    # KILL 발화는 options_zero_hold 외 다른 rule 이 1건이라도.
    real_triggered = [r for r in triggered if r != "options_zero_hold"]
    if real_triggered:
        return StrategicEvaluation(
            decision="kill",
            triggered_rules=triggered,
        )

    return StrategicEvaluation(
        decision="publish",
        triggered_rules=[],
    )
