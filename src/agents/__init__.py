"""Agent definitions for the Event Analysis Team.

v5.2.9: 분석 페르소나 7개 모듈 (PlayerAnalyst / DynamicsAnalyst / ChainReactionAnalyst /
ScenarioArchitect / VisualAnalyst / QualityInspector / SynthesisJudge) 폐기.
v4.0.0 부터 호출되지 않던 dead code. lens 별칭 (StakeholderLens / StructuralLens /
CascadeLens) 도 함께 제거 — 호출처 없음.

현재 살아있는 에이전트는 ContextAnalyst (사실 수집) + NarrativeComposer (본문 작성) +
ReportSynthesizer (HTML 렌더) + ResearchDirector (V5 Phase 1A, opt-in).
"""

from .base import BaseAgent
from .context_analyst import ContextAnalyst
from .report_synthesizer import ReportSynthesizer

__all__ = [
    "BaseAgent",
    "ContextAnalyst",
    "ReportSynthesizer",
]
