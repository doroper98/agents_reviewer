"""V5 Phase 0C — Pipeline State Compaction (6-tier).

REFACTOR_V5_PLAN.md §4 의 6-tier State 모델 SSOT. raw context 의 중복
입력을 차단해 token compounding 폭주를 방지한다.

Tier 구조:
    1. RawContext       — 원문, 검색결과, 출처. ContextAnalyst 만 본다.
    2. EvidencePack     — ContextAnalyst 의 압축 출력. 다음 단계가 받는다.
    3. AnalysisBrief    — ResearchDirector 출력 (Phase 1A). 분석 설계도.
    4. DraftReport      — Composer 출력. Editor 가 받는다.
    5. ExhibitPack      — VisualPlanner 출력. Renderer 가 받는다.
    6. PublishManifest  — Renderer 출력. DeskEditor 가 받는다.

각 LLM 호출이 *명시된 state 외* 다른 입력을 받으면 회귀 (AP-V5-30).

본 모듈은 V5 의 *데이터 계약* 만 정의한다. 실제 호출 경로 적용은
- Phase 0C : RawContext → EvidencePack 변환 함수 + guard (현재 commit).
- Phase 1A : ResearchDirector 가 AnalysisBrief 를 emit.
- Phase 1  : Editor 가 DraftReport + AnalysisBrief.thesis 만 본다.
- Phase 2  : VisualPlanner 가 EvidenceDataset[] (Phase 2A) 만 본다.
- Phase 7  : DeskEditor 가 PublishManifest + screenshots 만 본다.

Public API:
    from src.state import (
        RawContext, EvidencePack, AnalysisBrief, DraftReport,
        ExhibitPack, PublishManifest,
        compact_to_evidence_pack,
        evidence_pack_from_context_analysis,
    )
"""

from __future__ import annotations

from src.state.models import (
    AnalysisBrief,
    Actor,
    AnalysisMethod,
    Claim as StateClaim,
    Contradiction as StateContradiction,
    DraftReport,
    EvidenceDataset,
    EvidencePack,
    ExhibitPack,
    KeyNumber,
    PublishManifest,
    RawContext,
    RawSource,
    ReportShape,
    ScreenshotCapture,
    SearchHit,
    TimelineEvent,
    VisualConstraints,
)
from src.state.compaction import (
    compact_to_evidence_pack,
    evidence_pack_from_context_analysis,
    estimate_state_token_size,
)
from src.state.guards import (
    StateGuardError,
    assert_input_is,
    forbid_raw_context_in,
)

__all__ = [
    # 6-tier states
    "RawContext",
    "EvidencePack",
    "AnalysisBrief",
    "DraftReport",
    "ExhibitPack",
    "PublishManifest",
    # leaf models
    "RawSource",
    "SearchHit",
    "Actor",
    "TimelineEvent",
    "StateClaim",
    "StateContradiction",
    "AnalysisMethod",
    "ReportShape",
    "VisualConstraints",
    "KeyNumber",
    "EvidenceDataset",
    "ScreenshotCapture",
    # compaction
    "compact_to_evidence_pack",
    "evidence_pack_from_context_analysis",
    "estimate_state_token_size",
    # guards
    "StateGuardError",
    "assert_input_is",
    "forbid_raw_context_in",
]
