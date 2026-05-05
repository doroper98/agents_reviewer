"""V5 Phase 0C — State 입력 제한 강제 규칙 SSOT.

Plan §4.4 의 표 그대로:

    ContextAnalyst    → RawContext
    ResearchDirector  → EvidencePack + user_request           (RawContext 금지)
    Composer          → AnalysisBrief + EvidencePack 의 압축   (RawContext 금지)
    VisualPlanner     → DraftReport + EvidenceDataset[] +
                        VisualConstraints                     (RawContext 금지)
    Editor            → DraftReport + AnalysisBrief.thesis    (RawContext 금지,
                                                               EvidencePack 전체 금지)
    LayoutTypesetter  → DraftReport + ExhibitPack             (RawContext, EvidencePack 금지)
    ChartCritic       → 단일 chart spec + 인접 prose + thesis (RawContext 금지)
    DeskEditor        → PublishManifest + DraftReport(final)
                        + screenshots                         (RawContext, raw EvidencePack 금지)

본 모듈의 역할은 *런타임 가드* 가 아니라 *회귀 테스트의 검증 함수*. 즉
회귀 테스트가 ``forbid_raw_context_in(call_args, "composer")`` 를 호출하면
호출 인자에 RawContext 가 섞여 있으면 실패한다.

V5 의 어떤 단계에서도 본 가드를 *비활성* 하는 경로 (try/except pass 또는
직접 RawContext 인입) 를 신설하지 않는다 (AP-V5-30).
"""

from __future__ import annotations

from typing import Any, Iterable

from src.state.models import (
    AnalysisBrief,
    DraftReport,
    EvidencePack,
    ExhibitPack,
    PublishManifest,
    RawContext,
)


# Plan §4.4 의 표를 코드로 박은 SSOT.
# (호출 단계 라벨, 허용 state 타입 집합, 금지 state 타입 집합)
_ALLOWED_INPUTS: dict[str, dict[str, set[type]]] = {
    "context_analyst": {
        "allowed": {RawContext},
        "forbidden": set(),
    },
    "research_director": {                      # Phase 1A
        "allowed": {EvidencePack},
        "forbidden": {RawContext},
    },
    "composer": {                                # Phase 2 (drafting)
        "allowed": {AnalysisBrief, EvidencePack},
        "forbidden": {RawContext},
    },
    "visual_planner": {                          # Phase 2
        "allowed": {DraftReport, ExhibitPack, AnalysisBrief},
        "forbidden": {RawContext},
    },
    "editor": {                                  # Phase 1
        "allowed": {DraftReport, AnalysisBrief},
        "forbidden": {RawContext, EvidencePack},
    },
    "layout_typesetter": {                       # Phase 3
        "allowed": {DraftReport, ExhibitPack},
        "forbidden": {RawContext, EvidencePack},
    },
    "chart_critic": {                            # Phase 6 Gate B
        "allowed": {AnalysisBrief, ExhibitPack},  # spec + thesis (AnalysisBrief.thesis)
        "forbidden": {RawContext, EvidencePack},
    },
    "desk_editor": {                             # Phase 7
        "allowed": {PublishManifest, DraftReport},
        "forbidden": {RawContext, EvidencePack},
    },
}


class StateGuardError(AssertionError):
    """입력 제한 위반. 회귀 테스트가 fail 처리."""


def assert_input_is(call_stage: str, *args: Any) -> None:
    """`call_stage` 단계의 LLM 호출 인자가 명시된 state 만 받는지 검증.

    Args:
        call_stage: Plan §4.4 의 단계 라벨 (``context_analyst`` ~ ``desk_editor``).
        args: 실제 호출에 전달되는 인자들. 각 인자의 타입을 검사.

    Raises:
        StateGuardError: 허용되지 않은 state 타입이 인자로 전달된 경우.
    """
    rules = _ALLOWED_INPUTS.get(call_stage)
    if rules is None:
        raise StateGuardError(
            f"unknown call_stage: {call_stage!r} — Plan §4.4 의 8개 단계만 허용"
        )
    forbidden = rules["forbidden"]
    allowed = rules["allowed"]

    for arg in args:
        # state 모델 인스턴스만 검사 — primitive (str, dict, list) 은 통과.
        for ftype in forbidden:
            if isinstance(arg, ftype):
                raise StateGuardError(
                    f"AP-V5-30 위반: '{call_stage}' 단계에 {ftype.__name__} 입력 — "
                    f"Plan §4.4 의 forbidden 규칙."
                )
        # 명시적 state 타입을 받는 경우엔 allowed 안에 포함되어야.
        is_state = any(
            isinstance(arg, klass)
            for klass in (RawContext, EvidencePack, AnalysisBrief, DraftReport, ExhibitPack, PublishManifest)
        )
        if is_state:
            if not any(isinstance(arg, k) for k in allowed):
                raise StateGuardError(
                    f"AP-V5-30 위반: '{call_stage}' 단계에 {type(arg).__name__} 입력 — "
                    f"허용: {sorted(c.__name__ for c in allowed)}"
                )


def forbid_raw_context_in(args: Iterable[Any], call_stage: str) -> None:
    """단순화된 가드 — RawContext 만 검사 (Plan §4.4 의 가장 핵심 규칙).

    회귀 테스트가 호출 인자 (예: ``call_args_list``) 를 받아 일괄 검증할 때 사용.
    """
    if call_stage == "context_analyst":
        return  # ContextAnalyst 는 RawContext 가 *허용된* 유일한 단계.
    for a in args:
        if isinstance(a, RawContext):
            raise StateGuardError(
                f"AP-V5-30 위반: '{call_stage}' 가 RawContext 를 입력으로 받음 — "
                f"ContextAnalyst 외 어떤 단계도 RawContext 를 보지 못한다."
            )


def list_known_stages() -> list[str]:
    """Plan §4.4 의 8개 단계 라벨 — 회귀 테스트의 분포 가드용."""
    return sorted(_ALLOWED_INPUTS.keys())
