"""Lens registry — lens_id → LensRunner factory.

V3 Step 5-A (v2.9.0). 각 lens 모듈은 클래스만 노출 (singleton 인스턴스화는 registry 가 담당
— config 의존성이 있어 archetype 처럼 module-level 싱글턴을 두지 않는다).

미등록 lens_id 는 fallback 으로 ``red_team`` 으로 매핑 (메타-lens 라 모든 사건에 적용 가능).
"""

from __future__ import annotations

import logging
from typing import Type

from src.config import Config
from src.lenses.base import LensRunner

# Lazy imports — lens 모듈은 LensRunner 를 상속하므로 base 가 먼저 로드되어야 함.
from src.lenses.geopolitical_lens import GeopoliticalLens
from src.lenses.financial_transmission_lens import FinancialTransmissionLens
from src.lenses.tech_architecture_lens import TechArchitectureLens
from src.lenses.policy_implementation_lens import PolicyImplementationLens
from src.lenses.accident_causality_lens import AccidentCausalityLens
from src.lenses.market_structure_lens import MarketStructureLens
from src.lenses.red_team_lens import RedTeamLens
from src.lenses.pre_mortem_lens import PreMortemLens
# V3 Step 5-C (v3.0.0) — 페르소나 이전 3종
from src.lenses.stakeholder_lens import StakeholderLens
from src.lenses.structural_lens import StructuralLens
from src.lenses.cascade_lens import CascadeLens

logger = logging.getLogger(__name__)


_LENS_CLASSES: dict[str, Type[LensRunner]] = {
    # Step 5-A (v2.9.0) — 분야 6 + 메타 2
    "geopolitical": GeopoliticalLens,
    "financial_transmission": FinancialTransmissionLens,
    "tech_architecture": TechArchitectureLens,
    "policy_implementation": PolicyImplementationLens,
    "accident_causality": AccidentCausalityLens,
    "market_structure": MarketStructureLens,
    "red_team": RedTeamLens,
    "pre_mortem": PreMortemLens,
    # Step 5-C (v3.0.0) — 페르소나 이전 3종
    "stakeholder": StakeholderLens,
    "structural": StructuralLens,
    "cascade": CascadeLens,
}

DEFAULT_LENS_ID = "red_team"  # 메타 — 어떤 사건에도 적용 가능한 fallback


def get_lens(lens_id: str, config: Config) -> LensRunner:
    """Resolve lens_id → fresh LensRunner instance with given config.

    Unknown ID 는 ``DEFAULT_LENS_ID`` (red_team) 로 폴백 + warning 로그.
    """
    cls = _LENS_CLASSES.get(lens_id)
    if cls is None:
        logger.warning(
            "[lenses] Unknown lens_id=%r; falling back to %s "
            "(registered: %s)",
            lens_id, DEFAULT_LENS_ID, list(_LENS_CLASSES.keys()),
        )
        cls = _LENS_CLASSES[DEFAULT_LENS_ID]
    return cls(config)


def list_lenses() -> list[str]:
    """Registered lens IDs (for prompt construction + diagnostics)."""
    return list(_LENS_CLASSES.keys())
