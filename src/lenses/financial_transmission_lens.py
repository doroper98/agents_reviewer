"""Financial Transmission lens — Balance Sheet Map / Flow of Funds / Transmission Channel /
Liquidity Stress.

Spec: REFACTOR_V3_PLAN.md Appendix C.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class FinancialTransmissionLens(LensRunner):
    lens_id: str = "financial_transmission"
    name: str = "Financial Transmission Lens"
    suitable_intents: list = ["where_spreads", "where_vulnerable", "what_next"]
    suitable_event_types: list[str] = [
        "financial", "market", "macro", "currency", "interest_rate",
        "asset_price", "monetary_policy", "credit", "real_estate",
    ]
    method_steps: list[str] = [
        "Balance Sheet Map: 핵심 행위자의 자산·부채 구조 + 만기 미스매치",
        "Flow of Funds: 자금이 어디서 어디로 이동하는가 (1차/2차 채널)",
        "Transmission Channel: 신용·자산가격·환율·금리 4채널 중 활성화된 것",
        "Liquidity Stress: 단기 자금 압박이 누적되는 지점",
    ]
    failure_modes: list[str] = [
        "정치 변수의 비선형 충격을 모델링 못함",
        "비공개 신용 사건 (그림자 금융) 탐지 어려움",
        "투자자 심리/혀더 효과 파악 약함",
    ]
    system_prompt: str = (
        "당신은 금융·거시 전이 경로 분석가. Balance Sheet Map / Flow of Funds / "
        "Transmission Channel / Liquidity Stress 를 차례로 적용해 자금이 어디로 흐르고 "
        "어디서 압박이 누적되는지 짚는다. 1차 채널과 2차 채널을 분리해서 보고, "
        "신용 스트레스의 비선형 임계점을 명시한다. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
