"""Archetype registry — string ID → ReportArchetype instance.

V3 Step 2 (v2.6.0). Anti-pattern #1 (이번 Step 한정): if/elif 하드코딩 금지 — 본 registry 사용.

신규 archetype 추가 절차:
1. ``src/archetypes/<name>.py`` 신설, ``ARCHETYPE`` 싱글턴 노출.
2. 본 파일의 ``_REGISTRY`` 에 등록.
3. ``docs/CATALOGS.md §3`` archetype 표 갱신 (Anti-pattern #14).
"""

from __future__ import annotations

import logging

from src.archetypes.base import ReportArchetype
from src.archetypes.financial_transmission import ARCHETYPE as FINANCIAL_TRANSMISSION
from src.archetypes.six_act_theater import ARCHETYPE as SIX_ACT_THEATER
from src.archetypes.tech_decomposition import ARCHETYPE as TECH_DECOMPOSITION

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, ReportArchetype] = {
    SIX_ACT_THEATER.archetype_id: SIX_ACT_THEATER,
    FINANCIAL_TRANSMISSION.archetype_id: FINANCIAL_TRANSMISSION,
    TECH_DECOMPOSITION.archetype_id: TECH_DECOMPOSITION,
}

DEFAULT_ARCHETYPE_ID: str = SIX_ACT_THEATER.archetype_id


def get_archetype(archetype_id: str) -> ReportArchetype:
    """Resolve archetype_id to instance. Unknown IDs fall back to ``six_act_theater``.

    Fallback is intentional — Strategy Planner may emit a mistaken ID during early V3
    rollout. The default preserves the legacy report flow rather than crashing.
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
