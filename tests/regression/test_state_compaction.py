"""V5 Phase 0C — Pipeline State Compaction regression test.

Plan §4.5 의 인수 기준:
    1. 6-tier State 모델이 src/state/ 모듈에 정의되어야 한다.
    2. 각 LLM 호출의 입력이 명시된 state 외 다른 것을 받으면 fail.
    3. v4.5.x 와 동일 prompt 에서 V5 의 총 입력 토큰이 *압축 적용 전 단순
       합산 대비 30% 이상 감소* 해야 한다.
    4. 응답 정확도 (Golden Prompt 회귀) 가 압축으로 인해 떨어지지 않아야 한다.

본 모듈은 #1, #2, #3 을 결정적으로 검증. #4 는 Phase 1A 진입 후 본격 측정 —
record_baseline.py 의 Golden Prompt 통과율로 평가.
"""

from __future__ import annotations

from pathlib import Path

from tests.regression._pytest_compat import pytest

from src.state import (
    AnalysisBrief,
    DraftReport,
    EvidencePack,
    ExhibitPack,
    PublishManifest,
    RawContext,
    StateGuardError,
    assert_input_is,
    compact_to_evidence_pack,
    estimate_state_token_size,
    evidence_pack_from_context_analysis,
    forbid_raw_context_in,
)
from src.state.guards import list_known_stages
from src.state.models import (
    Actor,
    AnalysisMethod,
    Claim as StateClaim,
    Contradiction as StateContradiction,
    EvidenceDataset,
    KeyNumber,
    RawSource,
    ReportShape,
    ScreenshotCapture,
    SearchHit,
    TimelineEvent,
    VisualConstraints,
)


# ─── 인수 기준 #1 — 6-tier State 모델 정의 검증 ───────────────────────────


def test_six_tier_states_defined() -> None:
    """Plan §4.3 의 6 tier 가 모두 import 가능."""
    expected_classes = [
        RawContext, EvidencePack, AnalysisBrief, DraftReport, ExhibitPack, PublishManifest,
    ]
    for cls in expected_classes:
        assert cls is not None
        assert hasattr(cls, "model_dump"), f"{cls.__name__} 가 Pydantic 모델이 아님"


def test_evidence_pack_required_fields() -> None:
    """Plan §4.3 의 EvidencePack 필수 필드 보존."""
    fields = set(EvidencePack.model_fields.keys())
    required = {"claims", "actors", "timeline", "contradictions"}
    assert required <= fields, f"EvidencePack 필수 필드 누락: {required - fields}"


def test_analysis_brief_method_enum() -> None:
    """Plan §6.3 의 9종 분석기법 enum 검증."""
    expected_methods = {
        "ACH", "scenario_tree", "transmission_channel", "stakeholder_matrix",
        "fault_tree", "decision_matrix", "pre_mortem", "transmission_timeline",
        "comparative",
    }
    # AnalysisMethod 의 method 필드 Literal 확인.
    annotation = AnalysisMethod.model_fields["method"].annotation
    # typing.Literal 의 args 추출.
    from typing import get_args
    actual = set(get_args(annotation))
    assert actual == expected_methods, (
        f"AnalysisMethod enum drift from Plan §6.3: "
        f"missing={expected_methods - actual}, extra={actual - expected_methods}"
    )


def test_claim_requires_at_least_one_source() -> None:
    """Plan §4.3 의 Claim 모델은 source_ids ≥ 1 강제 (Anti-pattern #4 보존)."""
    # source_ids=[] 는 ValidationError.
    with pytest.raises(Exception):
        StateClaim(claim_id="C-1", statement="x", source_ids=[])


# ─── 인수 기준 #2 — guards (Plan §4.4) 검증 ─────────────────────────────


def test_known_stages_match_plan_4_4() -> None:
    """Plan §4.4 의 8개 단계 라벨 정확히 매칭."""
    expected_stages = [
        "chart_critic",
        "composer",
        "context_analyst",
        "desk_editor",
        "editor",
        "layout_typesetter",
        "research_director",
        "visual_planner",
    ]
    assert sorted(list_known_stages()) == expected_stages


def test_context_analyst_can_receive_raw_context() -> None:
    """ContextAnalyst 는 RawContext 가 *유일한 허용* 단계."""
    raw = RawContext(user_request="test")
    assert_input_is("context_analyst", raw)  # raises 없으면 OK.


def test_composer_must_not_receive_raw_context() -> None:
    """Composer 가 RawContext 받으면 AP-V5-30 fail."""
    raw = RawContext(user_request="test")
    with pytest.raises(StateGuardError):
        assert_input_is("composer", raw)


def test_editor_must_not_receive_evidence_pack() -> None:
    """Editor 는 DraftReport + AnalysisBrief.thesis 만 받음 — EvidencePack 금지."""
    pack = EvidencePack()
    with pytest.raises(StateGuardError):
        assert_input_is("editor", pack)


def test_desk_editor_must_not_receive_raw_context() -> None:
    """DeskEditor 가 RawContext 받으면 fail."""
    raw = RawContext(user_request="test")
    with pytest.raises(StateGuardError):
        assert_input_is("desk_editor", raw)


def test_unknown_stage_rejected() -> None:
    """등록되지 않은 단계 라벨은 즉시 fail."""
    with pytest.raises(StateGuardError):
        assert_input_is("not_a_real_stage")


def test_forbid_raw_context_in_simple_check() -> None:
    """forbid_raw_context_in 단순화된 가드."""
    raw = RawContext(user_request="test")
    pack = EvidencePack()
    forbid_raw_context_in([pack], "composer")  # OK
    with pytest.raises(StateGuardError):
        forbid_raw_context_in([raw], "composer")
    # context_analyst 는 RawContext 허용.
    forbid_raw_context_in([raw], "context_analyst")  # OK


# ─── 인수 기준 #3 — 30% 이상 토큰 절감 ────────────────────────────────


def _make_realistic_raw_context(size_kb: int = 50) -> RawContext:
    """Plan §4.2 의 ~50KB raw_sources 시나리오 재현 — synthetic 한국어 텍스트."""
    chunk = "한국어 출처 원문 텍스트. 이 사건은 2026년 5월에 발생했고 영향은 광범위하다. " * 50
    sources = []
    for i in range(size_kb // 5):
        sources.append(
            RawSource(
                url=f"https://example.com/article_{i}",
                title=f"기사 {i}",
                publisher="언론사",
                published_at="2026-05-01",
                raw_text=chunk * 2,
                reliability="primary" if i % 3 == 0 else "secondary",
            )
        )
    return RawContext(
        user_request="테스트 사건 분석",
        raw_sources=sources,
        search_results=[
            SearchHit(query="q", title=f"hit {i}", url=f"https://e.com/{i}", snippet=chunk[:200])
            for i in range(8)
        ],
    )


def test_compaction_reduces_tokens_by_at_least_30_percent() -> None:
    """Plan §4.5 인수 기준 #3 — 압축 후 ≥30% 감소."""
    raw = _make_realistic_raw_context(size_kb=50)
    raw_tokens = estimate_state_token_size(raw)

    pack = compact_to_evidence_pack(raw, summarize_quote_max_chars=280)
    pack_tokens = estimate_state_token_size(pack)

    reduction = (raw_tokens - pack_tokens) / max(raw_tokens, 1)
    assert reduction >= 0.30, (
        f"Plan §4.5 인수 기준 #3 미달: "
        f"raw={raw_tokens}, pack={pack_tokens}, reduction={reduction:.1%} < 30%"
    )


def test_compaction_preserves_source_ids() -> None:
    """압축이 source_index 매핑을 보존 — claim 의 source_ids 가 가리키는 키 모두 존재."""
    raw = _make_realistic_raw_context(size_kb=20)
    pack = compact_to_evidence_pack(raw)
    for claim in pack.claims:
        for sid in claim.source_ids:
            assert sid in pack.source_index, f"claim {claim.claim_id} 의 source_id {sid} 미정의"


def test_estimate_state_token_size_sanity() -> None:
    """추정 함수의 sanity — 빈 모델은 작고, 큰 모델은 크다."""
    empty = EvidencePack()
    small = estimate_state_token_size(empty)
    big_raw = _make_realistic_raw_context(size_kb=50)
    big = estimate_state_token_size(big_raw)
    assert small < 100, f"empty EvidencePack token estimate too high: {small}"
    assert big > small * 10


# ─── ContextAnalysis adapter (orchestrator 에서 호출되는 경로) ────────────


def test_evidence_pack_from_context_analysis_basic() -> None:
    """v4.5.7 ContextAnalysis 모양 → EvidencePack 변환."""
    # src.models.ContextAnalysis 와 동일 모양의 mock object.
    class _MockContext:
        event_name = "테스트 사건"
        category = "geopolitical"
        summary = "사건 요약 본문 한 단락."
        timeline = [{"date": "2026-05-01", "event": "이벤트 1", "impact": "영향 A"}]
        key_figures = [{"label": "지표", "value": 100, "context": "맥락"}]
        sources = ["https://example.com/1", "https://example.com/2"]
        recommended_persona = {"tone": "analytic"}

    pack = evidence_pack_from_context_analysis(_MockContext())
    assert pack.category == "geopolitical"
    assert pack.recommended_persona == {"tone": "analytic"}
    assert len(pack.source_index) >= 2
    assert len(pack.timeline) == 1
    assert pack.timeline[0].what == "이벤트 1"
    assert any("지표" in c.statement for c in pack.claims)


def test_evidence_pack_from_empty_context() -> None:
    """ContextAnalysis 가 거의 비어 있어도 변환 성공 (fallback 보고서 시나리오)."""
    class _MockContext:
        event_name = ""
        category = ""
        summary = ""
        timeline = []
        key_figures = []
        sources = []
        recommended_persona = {}

    pack = evidence_pack_from_context_analysis(_MockContext())
    assert isinstance(pack, EvidencePack)
    assert pack.claims == []
    assert pack.timeline == []
