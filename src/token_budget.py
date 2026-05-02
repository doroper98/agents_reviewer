"""Token budget + execution mode policy (v3.1.0).

분석 1건당 LLM 호출 수, lens 개수, 보조 LLM 단계의 사용 여부를 모드별로 제한.
주요 진입점은 ``resolve_mode(event_description)`` (키워드 → mode) 와
``TokenBudget.for_mode(mode)`` (mode → 정책 dataclass).

설계 원칙:
- 모든 사건에 모든 에이전트를 실행하지 않는다.
- 분석 품질은 "에이전트 수" 가 아니라 "사건에 맞는 렌즈 선택, 사실 검증, 반대가설 유지,
  근거 추적성" 으로 보장한다.
- 기본은 ``standard``. ``fast`` / ``deep`` 는 키워드 또는 명시적 호출로 진입.

SSOT: 본 정의. ``docs/ARCHITECTURE.md §3.1`` (토큰 사용량) 와
``docs/CATALOGS.md`` (lens cap 정책) 가 사람-친화 미러.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AnalysisMode = Literal["fast", "standard", "deep"]


# 키워드 → mode 매핑. 우선순위: deep 우선 (사용자가 둘 다 언급하면 깊게).
_DEEP_KEYWORDS: tuple[str, ...] = (
    "심층", "깊게", "자세히", "정밀", "deep", "상세하게", "면밀",
)
_FAST_KEYWORDS: tuple[str, ...] = (
    "짧게", "간략히", "간략하게", "빠르게", "요약", "간단히", "간단하게", "fast",
)


@dataclass(frozen=True)
class TokenBudget:
    """모드별 실행 정책. orchestrator 와 각 에이전트가 분기 기준으로 사용한다.

    필드 의미:
    - ``mode``: 모드 라벨 (로그/텔레메트리에 노출)
    - ``max_llm_calls``: 본 사건에서 허용되는 최대 LLM 호출 수 (소프트 가드 — telemetry 가
      초과 시 경고). orchestrator 는 이 값을 직접 강제하지 않으나, 테스트가 검증.
    - ``max_lenses``: lens pool 에서 실행할 최대 lens 수
    - ``use_llm_quality_gate``: gate_1 LLM judge 활성화 여부
    - ``use_llm_narrative_plan``: ReportSynthesizer 의 narrative plan LLM 호출 여부
    - ``use_llm_executive_summary``: deterministic summary 실패 시 LLM 으로 폴백할지
    - ``use_llm_visuals``: VisualAnalyst LLM 호출 여부 (False 면 deterministic 만)
    - ``use_llm_synthesis``: SynthesisJudge 의 LLM synthesis 활성화 여부
    - ``use_legacy_personas``: PlayerAnalyst/DynamicsAnalyst/ChainReactionAnalyst 호출 여부
      (deep 에서만 True — fast/standard 는 lens pool 로 대체)
    - ``allow_meta_lenses``: red_team / pre_mortem 자동 추가 여부
    - ``use_llm_narrative_composer``: v3.3.0 freeform editorial pass (Opus 4.7) 활성화
      (deep 에서만 True). 성공 시 archetype 이 ``freeform_essay`` 로 라우팅된다.
    """

    mode: AnalysisMode
    max_llm_calls: int
    max_lenses: int
    use_llm_quality_gate: bool
    use_llm_narrative_plan: bool
    use_llm_executive_summary: bool
    use_llm_visuals: bool
    use_llm_synthesis: bool
    use_legacy_personas: bool
    allow_meta_lenses: bool
    use_llm_narrative_composer: bool = False

    @classmethod
    def for_mode(cls, mode: AnalysisMode) -> "TokenBudget":
        """mode 키워드 → 정책 dataclass.

        v4.0.0 Tier 4: 멀티 에이전트 파이프라인 폐기. 모든 모드는 동일한 2-call
        파이프라인 (ContextAnalyst + UnifiedComposer). mode 는 composer 프롬프트의
        분석 깊이 지시 (fast 3~4 섹션 / standard 4~6 / deep 5~7 + 모순 필수) 에만
        영향. 다른 budget 플래그는 모두 비활성 (호출 안 됨).
        """
        common = dict(
            use_llm_quality_gate=False,
            use_llm_narrative_plan=False,
            use_llm_executive_summary=False,
            use_llm_visuals=False,
            use_llm_synthesis=False,
            use_legacy_personas=False,
            allow_meta_lenses=False,
            use_llm_narrative_composer=True,
        )
        if mode == "fast":
            return cls(mode="fast", max_llm_calls=2, max_lenses=0, **common)
        if mode == "deep":
            return cls(mode="deep", max_llm_calls=2, max_lenses=0, **common)
        return cls(mode="standard", max_llm_calls=2, max_lenses=0, **common)


def resolve_mode(event_description: str) -> AnalysisMode:
    """사용자 입력 → mode. 키워드가 없으면 ``standard``.

    deep 키워드 우선 (둘 다 있으면 deep). 케이스 무시 + 한국어 매칭.
    """
    text = (event_description or "").lower()
    for kw in _DEEP_KEYWORDS:
        if kw.lower() in text:
            return "deep"
    for kw in _FAST_KEYWORDS:
        if kw.lower() in text:
            return "fast"
    return "standard"
