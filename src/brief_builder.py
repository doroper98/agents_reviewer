"""Compact context builder (v3.1.0).

``FullAnalysisResult`` → ``AnalysisBrief``. fast/standard 모드에서 후속 에이전트와 lens 가
이전 분석 *전체* 를 재투입하지 않도록 한다. 각 list 필드는 길이 제한 (BRIEF_MAX_*) 을
적용해 회귀를 방지한다.

본 모듈은 LLM 호출 없이 100% 결정적. 누락 데이터는 빈 list/문자열로 반환.
"""

from __future__ import annotations

from src.models import (
    BRIEF_MAX_FACTS,
    BRIEF_MAX_TIMELINE,
    BRIEF_MAX_ACTORS,
    BRIEF_MAX_CAUSAL,
    BRIEF_MAX_SCENARIOS,
    BRIEF_MAX_UNCERTAINTIES,
    BRIEF_MAX_SOURCES,
    AnalysisBrief,
    FullAnalysisResult,
)


def _trim(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    return text.strip()[:limit]


def _facts_from_context(result: FullAnalysisResult) -> list[str]:
    facts: list[str] = []
    ctx = result.context
    if not ctx:
        return facts
    if ctx.summary:
        facts.append(_trim(ctx.summary, 240))
    if ctx.background:
        facts.append(_trim(ctx.background, 200))
    for fig in (ctx.key_figures or [])[:6]:
        label = fig.get("label", "")
        value = fig.get("value", "")
        ctx_note = fig.get("context", "")
        if label and value:
            piece = f"{label}: {value}"
            if ctx_note:
                piece += f" ({_trim(ctx_note, 60)})"
            facts.append(piece[:160])
    return facts[:BRIEF_MAX_FACTS]


def _timeline_from_context(result: FullAnalysisResult) -> list[dict]:
    ctx = result.context
    if not ctx or not ctx.timeline:
        return []
    out: list[dict] = []
    for item in ctx.timeline[:BRIEF_MAX_TIMELINE]:
        out.append({
            "date": (item.get("date") or "")[:20],
            "event": _trim(item.get("event", ""), 120),
        })
    return out


def _actors_from_players(result: FullAnalysisResult) -> list[dict]:
    if not result.players or not result.players.players:
        return []
    out: list[dict] = []
    for p in result.players.players[:BRIEF_MAX_ACTORS]:
        out.append({
            "name": (p.get("name") or "")[:60],
            "role": (p.get("role_tag") or "")[:60],
            "position": _trim(p.get("position", ""), 100),
        })
    return out


def _causal_claims(result: FullAnalysisResult) -> list[str]:
    out: list[str] = []
    if result.dynamics:
        if result.dynamics.key_insight:
            out.append(_trim(result.dynamics.key_insight, 200))
        if result.dynamics.core_tension:
            out.append(_trim(result.dynamics.core_tension, 160))
    if result.chain_reaction and result.chain_reaction.chain:
        for step in result.chain_reaction.chain[:4]:
            title = step.get("title", "")
            if title:
                out.append(_trim(title, 120))
    return out[:BRIEF_MAX_CAUSAL]


def _scenarios_compact(result: FullAnalysisResult) -> list[dict]:
    if not result.scenarios or not result.scenarios.scenarios:
        return []
    out: list[dict] = []
    for sc in result.scenarios.scenarios[:BRIEF_MAX_SCENARIOS]:
        out.append({
            "name": (sc.get("name") or "")[:60],
            "prob": (sc.get("probability") or "")[:20],
            "summary": _trim(sc.get("description", ""), 140),
        })
    return out


def _uncertainties(result: FullAnalysisResult) -> list[str]:
    out: list[str] = []
    if result.judgment and result.judgment.biggest_uncertainty:
        out.append(_trim(result.judgment.biggest_uncertainty, 200))
    if result.dynamics and result.dynamics.counter_view:
        out.append(_trim(result.dynamics.counter_view, 200))
    if result.scenarios and result.scenarios.invalidation_conditions:
        for cond in result.scenarios.invalidation_conditions[:2]:
            out.append(_trim(cond, 160))
    return out[:BRIEF_MAX_UNCERTAINTIES]


def build_analysis_brief(result: FullAnalysisResult) -> AnalysisBrief:
    """``FullAnalysisResult`` 의 핵심 요약을 ``AnalysisBrief`` 로 압축.

    누락된 단계는 빈 값으로 두며 계속 진행 (fast 모드에서는 일부 단계가 비어있을 수 있음).
    """
    ctx = result.context
    strategy = result.strategy
    sources: list[str] = []
    if ctx and ctx.sources:
        sources = [s for s in ctx.sources if s][:BRIEF_MAX_SOURCES]

    return AnalysisBrief(
        event_name=(ctx.event_name if ctx else "") or "",
        event_type=(strategy.event_type if strategy else "") or "",
        user_intent=(strategy.user_intent if strategy else "") or "",
        date=(ctx.date if ctx else "") or "",
        facts=_facts_from_context(result),
        timeline=_timeline_from_context(result),
        actors=_actors_from_players(result),
        causal_claims=_causal_claims(result),
        scenarios=_scenarios_compact(result),
        uncertainties=_uncertainties(result),
        sources=sources,
    )
