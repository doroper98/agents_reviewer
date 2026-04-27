"""Market Structure lens — Network Analysis / Game Theory / Regime Shift Analysis.

Spec: REFACTOR_V3_PLAN.md Appendix C.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class MarketStructureLens(LensRunner):
    lens_id: str = "market_structure"
    name: str = "Market Structure Lens"
    suitable_intents: list = ["who_benefits", "where_spreads", "what_next"]
    suitable_event_types: list[str] = [
        "market", "competition", "industry", "m_and_a",
        "supply_chain", "platform", "regulation",
    ]
    method_steps: list[str] = [
        "Network Analysis: 행위자·자산·자금 노드의 연결성 + 중심성 점수",
        "Game Theory: 핵심 행위자 간 게임 형식 — 죄수 딜레마/치킨/협상 균형 중 어느 것에 가까운가",
        "Regime Shift Analysis: 현재 시장 레짐 (low-vol vs stress vs crisis) 식별 + 전환 트리거",
    ]
    failure_modes: list[str] = [
        "비공개 거래·다크풀 정보 부족",
        "정치적 외부 충격 모델링 약함",
        "단기 미세구조(HFT) 와 장기 구조 변화의 분리 어려움",
    ]
    system_prompt: str = (
        "당신은 시장 구조 분석가. Network Analysis / Game Theory / Regime Shift Analysis 를 "
        "적용해 시장의 연결성·전략 균형·레짐 전환 가능성을 짚는다. 현재 어떤 game 에 가까운지, "
        "현재 어떤 레짐에 있고 다음 레짐으로의 트리거가 무엇인지 명시한다. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
