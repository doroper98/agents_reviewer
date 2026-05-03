"""Lens selection policy (v3.1.0).

LLM Strategy Planner 의 ``recommended_lenses`` 출력에 의존하지 않고, 코드 규칙으로
``(event_type, user_intent, mode)`` → lens 목록을 결정한다. LLM 출력이 들어오면 추천으로
참고만 하고, 본 정책이 최종 결정자.

매핑 원칙:
- fast: 분야 lens 1개 (사건의 핵심 영역)
- standard: 분야 lens 2개 또는 분야 1 + 메타 1
- deep: 최대 4개 (분야 1~2 + 메타 1~2)
- red_team / pre_mortem 같은 메타 lens 는 모든 사건에 자동 추가하지 않음.
  · pre_mortem: ``what_next`` / ``what_to_do`` / ``where_vulnerable`` 의도에서만 추가
  · red_team: ``what_to_do`` / ``where_vulnerable`` 의도에서만 추가

본 모듈은 LLM 호출 없이 100% 결정적.
"""

from __future__ import annotations

import logging

from src.archetypes.registry import _classify_event_type
from src.lenses.registry import list_lenses
from src.token_budget import AnalysisMode

logger = logging.getLogger(__name__)


# 정규화된 event 카테고리 → 분야 lens 우선순위 (앞이 높음)
_DOMAIN_LENSES_BY_CATEGORY: dict[str, list[str]] = {
    "tech": ["tech_architecture", "structural"],
    "accident": ["accident_causality", "structural", "cascade"],
    "financial": ["financial_transmission", "market_structure", "cascade"],
    "industry": ["market_structure", "stakeholder", "structural"],
    "policy": ["policy_implementation", "stakeholder"],
    "geopolitical": ["geopolitical", "stakeholder", "structural"],
    "general": ["stakeholder", "structural"],
}


_INTENT_TO_META_LENS: dict[str, str] = {
    "what_to_do": "red_team",
    "where_vulnerable": "red_team",
    "what_next": "pre_mortem",
}


def _meta_lens_for_intent(intent: str) -> str | None:
    """의사결정/취약점/전망 의도일 때만 메타 lens 추가. 나머지는 None."""
    return _INTENT_TO_META_LENS.get(intent)


def select_lenses(
    event_type: str,
    user_intent: str,
    mode: AnalysisMode,
    *,
    llm_recommended: list[str] | None = None,
) -> list[str]:
    """``(event_type, user_intent, mode)`` → 실행할 lens_id 목록.

    Args:
        event_type: Strategy Planner 가 산출한 자유 텍스트 event_type.
        user_intent: ``UserIntent`` Literal 중 하나.
        mode: ``token_budget.AnalysisMode``.
        llm_recommended: LLM 이 권장한 lens 목록 (있으면 우선순위 보정에만 사용).

    Returns:
        등록된 lens_id 만 포함한 list. 길이 cap 은 mode 별:
        - fast: 1
        - standard: 2
        - deep: 4
    """
    from src.token_budget import TokenBudget

    budget = TokenBudget.for_mode(mode)
    cap = budget.max_lenses

    category = _classify_event_type(event_type)
    domain_candidates = list(_DOMAIN_LENSES_BY_CATEGORY.get(
        category, _DOMAIN_LENSES_BY_CATEGORY["general"],
    ))

    # LLM 추천 중 *분야 lens* 만 우선순위 앞으로 보정 (메타 lens 는 정책으로 결정).
    if llm_recommended:
        registered = set(list_lenses())
        meta_set = {"red_team", "pre_mortem"}
        recommended_domain = [
            lid for lid in llm_recommended
            if lid in registered and lid not in meta_set
        ]
        # 추천된 lens 가 후보에 있으면 앞으로 당김.
        if recommended_domain:
            seen: set[str] = set()
            new_order: list[str] = []
            for lid in recommended_domain:
                if lid not in seen:
                    new_order.append(lid)
                    seen.add(lid)
            for lid in domain_candidates:
                if lid not in seen:
                    new_order.append(lid)
                    seen.add(lid)
            domain_candidates = new_order

    selected: list[str] = []
    for lid in domain_candidates:
        if lid not in selected:
            selected.append(lid)
        if len(selected) >= cap:
            break

    # fast 는 메타 lens 를 추가하지 않음 (정책: 1개만).
    if budget.allow_meta_lenses and len(selected) < cap:
        meta = _meta_lens_for_intent(user_intent)
        if meta and meta not in selected:
            selected.append(meta)

    # deep 에서 cap 여유가 있으면 추가 메타 lens 1개 더 (반대편 메타).
    if mode == "deep" and len(selected) < cap:
        for meta in ("red_team", "pre_mortem"):
            if meta not in selected:
                selected.append(meta)
                if len(selected) >= cap:
                    break

    # 등록된 lens 만 통과.
    registered = set(list_lenses())
    final = [lid for lid in selected if lid in registered][:cap]
    if not final:
        logger.warning(
            "[lens_policy] No lens selected for event_type=%s user_intent=%s mode=%s; "
            "falling back to stakeholder",
            event_type, user_intent, mode,
        )
        final = ["stakeholder"]
    return final


# Theme 결정도 코드 규칙으로 처리 (Strategy Planner 프롬프트에서 분리).
# v4.5.0: editorial_cream (cream + terracotta) 디폴트 채택. burgundy_mono 는
# 위기·분쟁·사고 등 무게감이 필요한 사건 한정. light_mono 는 legacy 보존.
# 디폴트 cream 의 근거: 평어체·비유·dropcap 등 v4.5.0 인터랙션 패턴이
# 편집자형 톤이라 cream 배경과 시각적으로 정합 (LG 보고서 벤치마크 차용).
_THEME_BY_CATEGORY: dict[str, str] = {
    "tech": "editorial_cream",
    "financial": "editorial_cream",
    "geopolitical": "burgundy_mono",   # 외교·분쟁·전쟁 — gravitas
    "accident": "burgundy_mono",       # 재난·사고 — 무게감
    "policy": "editorial_cream",       # 정책·법안 — 편집 톤
    "industry": "editorial_cream",
    "general": "editorial_cream",
}


def select_theme(event_type: str) -> str:
    """event_type → 보고서 테마. LLM 호출 없이 결정.
    v4.5.0: editorial_cream 디폴트, burgundy_mono 는 위기/분쟁 한정."""
    category = _classify_event_type(event_type)
    return _THEME_BY_CATEGORY.get(category, "editorial_cream")
