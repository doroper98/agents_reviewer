"""Archetype registry + matching policy.

V3 Step 2 도입 → Step 5-A (v2.9.0) 확장 → Step 5-C (v3.0.0) 매칭 우선순위 재설계.

신규 archetype 추가 절차:
1. ``src/archetypes/<name>.py`` 신설, ``ARCHETYPE`` 싱글턴 노출.
2. 본 파일의 ``_REGISTRY`` 에 등록.
3. (선택) ``select_archetype()`` 의 우선순위 매트릭스에 매핑 추가.
4. ``docs/CATALOGS.md §3`` archetype 표 갱신 (Anti-pattern #14).
"""

from __future__ import annotations

import logging

from src.archetypes.accident_forensic import ARCHETYPE as ACCIDENT_FORENSIC
from src.archetypes.base import ReportArchetype
from src.archetypes.decision_brief import ARCHETYPE as DECISION_BRIEF
from src.archetypes.financial_transmission import ARCHETYPE as FINANCIAL_TRANSMISSION
from src.archetypes.geopolitical_strategic import ARCHETYPE as GEOPOLITICAL_STRATEGIC
from src.archetypes.industry_value_chain import ARCHETYPE as INDUSTRY_VALUE_CHAIN
from src.archetypes.mechanism_decomp import ARCHETYPE as MECHANISM_DECOMP
from src.archetypes.policy_implementation import ARCHETYPE as POLICY_IMPLEMENTATION
from src.archetypes.scenario_first import ARCHETYPE as SCENARIO_FIRST
from src.archetypes.six_act_theater import ARCHETYPE as SIX_ACT_THEATER
from src.archetypes.tech_decomposition import ARCHETYPE as TECH_DECOMPOSITION
from src.archetypes.timeline_first import ARCHETYPE as TIMELINE_FIRST

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, ReportArchetype] = {
    # Step 2 (v2.6.0)
    SIX_ACT_THEATER.archetype_id: SIX_ACT_THEATER,
    FINANCIAL_TRANSMISSION.archetype_id: FINANCIAL_TRANSMISSION,
    TECH_DECOMPOSITION.archetype_id: TECH_DECOMPOSITION,
    # Step 5-A (v2.9.0)
    GEOPOLITICAL_STRATEGIC.archetype_id: GEOPOLITICAL_STRATEGIC,
    ACCIDENT_FORENSIC.archetype_id: ACCIDENT_FORENSIC,
    POLICY_IMPLEMENTATION.archetype_id: POLICY_IMPLEMENTATION,
    # Step 5-C (v3.0.0)
    DECISION_BRIEF.archetype_id: DECISION_BRIEF,
    TIMELINE_FIRST.archetype_id: TIMELINE_FIRST,
    SCENARIO_FIRST.archetype_id: SCENARIO_FIRST,
    MECHANISM_DECOMP.archetype_id: MECHANISM_DECOMP,
    INDUSTRY_VALUE_CHAIN.archetype_id: INDUSTRY_VALUE_CHAIN,
}

DEFAULT_ARCHETYPE_ID: str = SIX_ACT_THEATER.archetype_id


# ----------------------------------------------------------------------
# Event type taxonomy — 사용자 spec 의 정밀 매트릭스를 코드화하기 위한 키워드 셋.
# Strategy Planner 는 자유 텍스트 event_type 을 산출하므로, 본 분류로 정규화.
# ----------------------------------------------------------------------

_TECH_TYPES = {
    "tech", "ai", "it", "software", "model_release", "system_outage",
    "cyber_security", "infra", "platform", "ml",
}
_ACCIDENT_TYPES = {
    "accident", "disaster", "industrial", "natural_disaster",
    "fire", "explosion", "infra_failure", "safety",
}
_FINANCIAL_TYPES = {
    "financial", "market", "macro", "currency", "interest_rate",
    "asset_price", "monetary_policy", "credit", "real_estate",
}
_INDUSTRY_TYPES = {
    "industry", "company", "m_and_a", "value_chain", "competition",
    "supply_chain",
}
_GEOPOLITICAL_TYPES = {
    "war", "diplomacy", "political_conflict", "international_relations",
    "leadership_change", "election", "security", "geopolitical",
    "military_action", "alliance",
}


def _classify_event_type(event_type: str) -> str:
    """Free-text event_type → 정규화된 카테고리 한 단어. 분류 불가 시 ``"general"``."""
    et = (event_type or "").lower().strip()
    if et in _TECH_TYPES:
        return "tech"
    if et in _ACCIDENT_TYPES:
        return "accident"
    if et in _FINANCIAL_TYPES:
        return "financial"
    if et in _INDUSTRY_TYPES:
        return "industry"
    if et in _GEOPOLITICAL_TYPES:
        return "geopolitical"
    if et == "policy" or "policy" in et or "regulation" in et or et in {"law", "social", "labor", "tax", "subsidy"}:
        return "policy"
    return "general"


def select_archetype(strategy: "AnalysisStrategy") -> ReportArchetype:  # type: ignore[name-defined]
    """우선순위 기반 archetype 선택. V3 Step 5-C (v3.0.0).

    매칭 우선순위 (위에서 아래로, 첫 매칭 채택):

    1순위 — 분야 특화 event_type + 매칭 의도 조합:
      · tech       + (where_vulnerable, what_happened, why_happened) → tech_decomposition
      · tech       + what_next                                         → scenario_first
      · tech       + what_to_do                                        → decision_brief
      · accident   + (where_vulnerable, what_happened, why_happened)   → accident_forensic
      · accident   + what_to_do                                        → decision_brief
      · financial  + (where_spreads, where_vulnerable)                 → financial_transmission
      · financial  + what_next                                         → scenario_first
      · industry   + (who_benefits, where_vulnerable)                  → industry_value_chain
      · industry   + what_to_do                                        → decision_brief
      · policy     + (who_benefits, what_to_do, where_vulnerable)      → policy_implementation

    2순위 — 의도 전용 archetype (event_type 미분류):
      · what_to_do      → decision_brief
      · what_next       → scenario_first
      · why_happened    → mechanism_decomp
      · what_happened   → timeline_first

    3순위 — geopolitical 사건 유형 매칭:
      · geopolitical + (who_benefits, what_happened) → six_act_theater  (인물극형 specialty)
      · geopolitical + 그 외                          → geopolitical_strategic

    4순위 — 최종 fallback: six_act_theater + warning 로그
    """
    # Lazy import to avoid circular reference (models imports archetypes via finding builders).
    from src.models import AnalysisStrategy

    if not isinstance(strategy, AnalysisStrategy):
        logger.warning(
            "[archetypes] select_archetype called with non-AnalysisStrategy %r; "
            "falling back to %s", type(strategy), DEFAULT_ARCHETYPE_ID,
        )
        return _REGISTRY[DEFAULT_ARCHETYPE_ID]

    intent = strategy.user_intent
    category = _classify_event_type(strategy.event_type)

    # ------------------------------------------------------------------
    # 1순위 — 분야 특화 event_type + 매칭 의도 조합
    # ------------------------------------------------------------------
    if category == "tech":
        if intent in ("where_vulnerable", "what_happened", "why_happened"):
            return _REGISTRY["tech_decomposition"]
        if intent == "what_next":
            return _REGISTRY["scenario_first"]
        if intent == "what_to_do":
            return _REGISTRY["decision_brief"]
    if category == "accident":
        if intent in ("where_vulnerable", "what_happened", "why_happened"):
            return _REGISTRY["accident_forensic"]
        if intent == "what_to_do":
            return _REGISTRY["decision_brief"]
    if category == "financial":
        if intent in ("where_spreads", "where_vulnerable"):
            return _REGISTRY["financial_transmission"]
        if intent == "what_next":
            return _REGISTRY["scenario_first"]
    if category == "industry":
        if intent in ("who_benefits", "where_vulnerable"):
            return _REGISTRY["industry_value_chain"]
        if intent == "what_to_do":
            return _REGISTRY["decision_brief"]
    if category == "policy":
        if intent in ("who_benefits", "what_to_do", "where_vulnerable"):
            return _REGISTRY["policy_implementation"]

    # ------------------------------------------------------------------
    # 2순위 — 의도 전용 archetype (event_type 미분류 또는 1순위 미매칭)
    # ------------------------------------------------------------------
    intent_only_map = {
        "what_to_do": "decision_brief",
        "what_next": "scenario_first",
        "why_happened": "mechanism_decomp",
        "what_happened": "timeline_first",
    }
    if intent in intent_only_map and category == "general":
        return _REGISTRY[intent_only_map[intent]]

    # ------------------------------------------------------------------
    # 3순위 — geopolitical 사건 유형 매칭
    # ------------------------------------------------------------------
    if category == "geopolitical":
        if intent in ("who_benefits", "what_happened"):
            return _REGISTRY["six_act_theater"]  # 인물극형 specialty
        return _REGISTRY["geopolitical_strategic"]

    # ------------------------------------------------------------------
    # 2순위 보충 — event_type 이 분류됐지만 1순위 매칭 실패한 경우, 의도 전용으로 폴
    # ------------------------------------------------------------------
    if intent in intent_only_map:
        return _REGISTRY[intent_only_map[intent]]

    # ------------------------------------------------------------------
    # 4순위 — 최종 fallback
    # ------------------------------------------------------------------
    logger.warning(
        "[archetypes] No specific archetype matched (intent=%s, event_type=%s/%s); "
        "falling back to %s",
        intent, strategy.event_type, category, DEFAULT_ARCHETYPE_ID,
    )
    return _REGISTRY[DEFAULT_ARCHETYPE_ID]


def get_archetype(archetype_id: str) -> ReportArchetype:
    """Resolve archetype_id to instance. Unknown IDs fall back to ``six_act_theater``.

    Fallback is intentional — Strategy Planner may emit a mistaken ID. The default
    preserves the legacy report flow rather than crashing.
    """
    archetype = _REGISTRY.get(archetype_id)
    if archetype is None:
        logger.warning(
            "[archetypes] Unknown archetype_id=%r; falling back to %s",
            archetype_id, DEFAULT_ARCHETYPE_ID,
        )
        return _REGISTRY[DEFAULT_ARCHETYPE_ID]
    return archetype


def list_archetypes() -> list[str]:
    """Return registered archetype IDs (for prompts / diagnostics)."""
    return list(_REGISTRY.keys())
