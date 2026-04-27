"""Analysis Lens Pool — V3 Step 5-A (v2.9.0).

각 LensRunner 는 Evidence 풀과 directive 를 받아 ``list[AnalyticalFinding]`` 을 산출.
사건당 동시 실행 한도 = 4 (Anti-pattern #6). lens 후보는 ``AnalysisStrategy.recommended_lenses``
가 결정 (Strategy Planner 산출).

신규 lens 추가 절차:
1. ``src/lenses/<name>_lens.py`` 신설, ``LENS`` 싱글턴 노출
2. ``src/lenses/registry.py`` 의 ``_REGISTRY`` 에 등록
3. ``docs/CATALOGS.md §2`` 의 lens 표 갱신 (Anti-pattern #14 회피)
4. ``GOAL.md`` 에 ``REQ-LENS-*`` 추가 (Appendix C 규칙)
"""

from src.lenses.base import LensRunner
from src.lenses.registry import get_lens, list_lenses

__all__ = ["LensRunner", "get_lens", "list_lenses"]
