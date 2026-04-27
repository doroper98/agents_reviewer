"""Agent definitions for the Event Analysis Team.

V3 Step 5-C (v3.0.0): Player/Dynamics/ChainReaction 페르소나는 deprecated. 신규 코드는
``src.lenses.{stakeholder, structural, cascade}_lens`` 사용. 기존 import 경로는 v4.0.0 까지
보존 (GOAL.md FUT-LEGACY-001). 본 모듈을 통해 deprecated 페르소나를 import 하면 모듈
top 레벨에서 ``DeprecationWarning`` 이 한 번 발화한다.
"""

from .base import BaseAgent
from .context_analyst import ContextAnalyst
from .player_analyst import PlayerAnalyst       # DEPRECATED — use src.lenses.StakeholderLens
from .dynamics_analyst import DynamicsAnalyst   # DEPRECATED — use src.lenses.StructuralLens
from .chain_reaction_analyst import ChainReactionAnalyst  # DEPRECATED — use src.lenses.CascadeLens
from .scenario_architect import ScenarioArchitect
from .visual_analyst import VisualAnalyst
from .report_synthesizer import ReportSynthesizer
from .quality_inspector import QualityInspector
from .synthesis_judge import SynthesisJudge

# V3 Step 5-C (v3.0.0) — 페르소나 → lens 이전 매핑.
# 신규 코드는 src.lenses.* 를 직접 import 할 것.
from src.lenses.stakeholder_lens import StakeholderLens
from src.lenses.structural_lens import StructuralLens
from src.lenses.cascade_lens import CascadeLens

__all__ = [
    "BaseAgent",
    "ContextAnalyst",
    # Deprecated personas (v3.0.0~v4.0.0 임시 호환):
    "PlayerAnalyst", "DynamicsAnalyst", "ChainReactionAnalyst",
    # 보존되는 에이전트:
    "ScenarioArchitect", "VisualAnalyst", "ReportSynthesizer",
    "QualityInspector", "SynthesisJudge",
    # 신규 lens 별칭 (페르소나 대체):
    "StakeholderLens", "StructuralLens", "CascadeLens",
]
