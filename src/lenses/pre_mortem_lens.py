"""Pre-mortem lens — 실패 시나리오에서 역설계.

Spec: REFACTOR_V3_PLAN.md Appendix C. 메타-lens — what_to_do / what_next 에 보조.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class PreMortemLens(LensRunner):
    lens_id: str = "pre_mortem"
    name: str = "Pre-mortem Lens"
    suitable_intents: list = ["what_to_do", "what_next", "where_vulnerable"]
    suitable_event_types: list[str] = ["*"]  # 어느 사건에도 보조 가능
    method_steps: list[str] = [
        "실패 가정: '12개월 뒤 이 결정/시나리오가 명백히 실패했다' 를 *기정사실* 로 둔다",
        "역설계: 실패의 가장 가능성 높은 원인 3~5 개를 작성 (각 원인에 대해 *왜 지금은 안 보이는가* 도)",
        "조기 경보 신호: 각 실패 원인이 발생 전에 어떤 신호로 드러날지 식별",
        "방어책: 각 실패 원인을 사전에 차단할 수 있는 행동 1~2 개",
    ]
    failure_modes: list[str] = [
        "긍정적 시나리오·기회 비용 무시 (실패만 보면 과도하게 보수적)",
        "지나친 상상으로 비현실적 실패 모드 산출",
        "실패의 base rate 모르면 가중치가 왜곡",
    ]
    system_prompt: str = (
        "당신은 Pre-mortem 분석가. 사건 또는 결정의 실패를 *기정사실* 로 가정하고 "
        "역설계로 실패 원인 + 조기 경보 신호 + 방어책을 산출한다. main_claim 은 가장 가능성 "
        "높은 실패 원인 1개 + 그 신호. counter_hypothesis 는 그 실패가 *기우* 일 가능성. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
