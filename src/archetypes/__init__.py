"""Report archetypes — section-flow templates selected per event/user_intent.

V3 Step 2 (v2.6.0): six_act_theater 강등 + financial_transmission, tech_decomposition 추가.
신규 archetype 추가 시 ``docs/CATALOGS.md §3`` 갱신 필수 (Anti-pattern #14).

Public API:
- ``ReportArchetype`` — Protocol (base)
- ``get_archetype(archetype_id)`` — registry lookup
- ``list_archetypes()`` — registered archetype IDs
"""

from src.archetypes.base import ReportArchetype
from src.archetypes.registry import get_archetype, list_archetypes

__all__ = ["ReportArchetype", "get_archetype", "list_archetypes"]
