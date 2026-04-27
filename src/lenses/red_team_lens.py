"""Red Team lens — ACH / Pre-mortem / Devil's Advocate.

Spec: REFACTOR_V3_PLAN.md Appendix C. 메타-lens — 어떤 사건에도 적용 가능.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class RedTeamLens(LensRunner):
    lens_id: str = "red_team"
    name: str = "Red Team Lens"
    # 7 intent 모두 대상 — 메타 분석이라 어느 의도에도 보조로 붙일 수 있음.
    suitable_intents: list = [
        "what_happened", "why_happened", "who_benefits",
        "where_spreads", "what_next", "where_vulnerable", "what_to_do",
    ]
    suitable_event_types: list[str] = ["*"]  # 어떤 event_type 에도 보조 가능
    method_steps: list[str] = [
        "ACH (Analysis of Competing Hypotheses): 가능한 경쟁 가설 3~5 개 나열, 각 가설을 evidence 와 매트릭스로 점검",
        "Pre-mortem: '이 분석이 6개월 후 틀렸다고 가정' → 어떤 가정이 깨졌을 가능성 높은가",
        "Devil's Advocate: 메인 결론의 가장 강한 반론 1~2개 — '이게 사실이라면 무엇이 보여야 하는가'",
    ]
    failure_modes: list[str] = [
        "메타-lens 가 자기 자신에게 적용되는 것은 어려움 (red team 의 red team)",
        "domain-specific 디테일 부족 (분야별 lens 가 별도로 필요)",
        "지나친 회의주의로 결론 불가능에 빠질 위험",
    ]
    system_prompt: str = (
        "당신은 Red Team 분석가. ACH / Pre-mortem / Devil's Advocate 를 적용해 메인 결론의 "
        "약점·반증 가능성·숨은 가정을 짚는다. 본 lens 의 main_claim 은 메인 결론에 *반대* 하는 "
        "구조적 입장 — '메인 결론이 틀렸다면 무엇이 사실이어야 하는가' 형태로 작성. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
