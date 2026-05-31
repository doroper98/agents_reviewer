"""Token budget + execution mode policy (v3.1.0).

분석 1건당 LLM 호출 수, lens 개수, 보조 LLM 단계의 사용 여부를 모드별로 제한.
주요 진입점은 ``resolve_mode(event_description)`` (키워드 → mode) 와
``TokenBudget.for_mode(mode)`` (mode → 정책 dataclass).

설계 원칙:
- 모든 사건에 모든 에이전트를 실행하지 않는다.
- 분석 품질은 "에이전트 수" 가 아니라 "사건에 맞는 렌즈 선택, 사실 검증, 반대가설 유지,
  근거 추적성" 으로 보장한다.
- 기본은 ``deep`` (v5.8.2). 사용자가 "빠르게/짧게/요약" 등 fast 키워드를 명시하지
  않는 한 깊게 분석. ``fast`` 는 키워드로, ``standard`` 는 호출부 명시로만 진입.

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
    - ``allow_meta_lenses``: red_team / pre_mortem 자동 추가 여부 (lens_policy 검사)
    - ``use_llm_narrative_composer``: v3.3.0 freeform editorial pass (Opus 4.7) 활성화.
      v4.0.0 부터 모든 모드 True (단일 본문 작성 경로).

    v5.2.9: dead flag 6종 (use_llm_quality_gate / use_llm_narrative_plan /
    use_llm_executive_summary / use_llm_visuals / use_llm_synthesis /
    use_legacy_personas) 삭제. v4.0.0 부터 모든 모드 False 였고, 호출되는 dead
    agent 가 함께 폐기됨.
    """

    mode: AnalysisMode
    max_llm_calls: int
    max_lenses: int
    allow_meta_lenses: bool
    use_llm_narrative_composer: bool = False

    @classmethod
    def for_mode(cls, mode: AnalysisMode) -> "TokenBudget":
        """mode 키워드 → 정책 dataclass.

        v4.0.0 Tier 4: 멀티 에이전트 파이프라인 폐기. 모든 모드는 동일한 2-call
        파이프라인 (ContextAnalyst + NarrativeComposer). mode 는 composer 프롬프트의
        분석 깊이 지시 (fast 3~4 섹션 / standard 4~6 / deep 5~7 + 모순 필수) 에만
        영향.
        """
        common = dict(
            allow_meta_lenses=False,
            use_llm_narrative_composer=True,
        )
        if mode == "fast":
            return cls(mode="fast", max_llm_calls=2, max_lenses=0, **common)
        if mode == "deep":
            return cls(mode="deep", max_llm_calls=2, max_lenses=0, **common)
        return cls(mode="standard", max_llm_calls=2, max_lenses=0, **common)


def resolve_mode(event_description: str) -> AnalysisMode:
    """사용자 입력 → mode. 키워드가 없으면 ``deep`` (v5.8.2 기본 변경).

    v5.8.2: 기본 모드를 standard → deep 으로 변경. 사용자가 "빠르게/짧게/요약"
    같은 fast 키워드를 명시하지 않는 한 항상 깊게 분석한다. standard 는 이제
    명시 키워드 없을 때의 기본이 아니라 *호출부가 직접 지정* 할 때만 진입.

    우선순위는 그대로: deep 키워드 우선 (fast·deep 키워드가 함께 오면 deep).
    fast 키워드만 있으면 fast. 둘 다 없으면 deep (← 변경점, 기존 standard).
    케이스 무시 + 한국어 매칭.
    """
    text = (event_description or "").lower()
    for kw in _DEEP_KEYWORDS:
        if kw.lower() in text:
            return "deep"
    for kw in _FAST_KEYWORDS:
        if kw.lower() in text:
            return "fast"
    return "deep"
