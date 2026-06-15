"""Unit tests for v3.3.0 narrative_composer + freeform_essay archetype + chart catalog.

Run:
    python -m pytest src/tests/test_narrative_composer.py -v
"""

from __future__ import annotations

import json

import pytest

from src.agents.narrative_composer import NarrativeComposer
from src.archetypes.registry import get_archetype, list_archetypes
from src.models import (
    AnalysisRequest,
    AnalysisStrategy,
    AnalyticalFinding,
    ChainReactionAnalysis,
    Claim,
    ComposedReport,
    ComposedSection,
    ConfidenceProfile,
    ContextAnalysis,
    Evidence,
    FullAnalysisResult,
    JudgmentVerdict,
    PlayerAnalysis,
    ScenarioAnalysis,
    VisualAnalysis,
)
from src.visual_builder import (
    build_chart_catalog,
    build_chart_payload,
    chart_id_to_payload_key,
)


# ----------------------------------------------------------------------
# 1. Chart catalog
# ----------------------------------------------------------------------

def test_chart_catalog_filters_to_available_only():
    """Catalog 는 데이터 있는 차트만 노출해야 함."""
    payload = {
        "scenarios": [{"name": "기본선", "prob": 50}],
        "key_figures": [{"label": "점유율", "value": 30}],
        # severity_chain, confidence, etc. 없음
    }
    catalog = build_chart_catalog(payload)
    ids = {c["id"] for c in catalog}
    assert "chart-scenarios" in ids
    assert "chart-figures" in ids
    assert "chart-severity" not in ids
    assert "chart-network" not in ids


def test_chart_catalog_empty_payload_returns_empty():
    assert build_chart_catalog({}) == []
    assert build_chart_catalog(None) == []  # type: ignore[arg-type]


def test_chart_catalog_entries_have_required_fields():
    payload = {"scenarios": [{"name": "x"}]}
    catalog = build_chart_catalog(payload)
    assert len(catalog) == 1
    entry = catalog[0]
    assert "id" in entry
    assert "title" in entry
    assert "hint" in entry
    assert entry["id"].startswith("chart-")


def test_chart_id_to_payload_key_roundtrip():
    assert chart_id_to_payload_key("chart-scenarios") == "scenarios"
    assert chart_id_to_payload_key("chart-network") == "network"
    assert chart_id_to_payload_key("chart-bogus") is None


# ----------------------------------------------------------------------
# 2. ComposedReport / ComposedSection model
# ----------------------------------------------------------------------

def test_composed_section_minimal_construction():
    sec = ComposedSection(heading="제목", prose="본문 내용임.")
    assert sec.heading == "제목"
    assert sec.kicker == ""
    assert sec.embedded_charts == []
    assert sec.embedded_blocks == []
    assert sec.cited_claim_ids == []
    assert sec.footnotes == []


def test_composed_section_footnotes_normalized():
    # v5.5.5 (WRITE-AP-10): 전문 용어 문단 하단 주석. None / 비정형 항목은 정규화.
    sec = ComposedSection(
        heading="요금 구조",
        prose="rate card 를 그대로 둘 수밖에 없는 핵심 용어가 있다.",
        footnotes=[
            {"term": "rate limit premium", "explanation": "처리 한도를 높이는 대가로 내는 웃돈."},
            {},                      # term/explanation 둘 다 없음 → drop
            {"junk": 1},             # 무관 키 → drop
            "bad",                   # dict 아님 → drop
        ],
    )
    assert len(sec.footnotes) == 1
    assert sec.footnotes[0]["term"] == "rate limit premium"

    # composer 가 null 을 emit 해도 빈 list 로 회복 (검증 reject 방지).
    sec_none = ComposedSection(heading="h", prose="p", footnotes=None)
    assert sec_none.footnotes == []


def test_composed_report_minimal_construction():
    report = ComposedReport(
        headline="사건 본질",
        deck="짧은 부제",
        sections=[
            ComposedSection(
                heading="첫 섹션",
                prose="본문",
                embedded_charts=["chart-scenarios"],
                cited_claim_ids=["C-001"],
            ),
        ],
    )
    assert report.headline == "사건 본질"
    assert len(report.sections) == 1
    assert report.sections[0].embedded_charts == ["chart-scenarios"]


# ----------------------------------------------------------------------
# 3. Composer parser + reference validator (no LLM call)
# ----------------------------------------------------------------------

def test_composer_parse_response_extracts_json_block():
    raw = '''여기는 추가 설명 (무시되어야 함).
```json
{
  "headline": "테스트",
  "deck": "부제",
  "sections": [
    {"heading": "섹션 1", "prose": "본문", "embedded_charts": [], "embedded_blocks": [], "cited_claim_ids": []}
  ],
  "closing": ""
}
```
'''
    parsed = NarrativeComposer._parse_response(raw)
    assert parsed is not None
    assert parsed.headline == "테스트"
    assert len(parsed.sections) == 1


def test_composer_parse_response_extracts_bare_json():
    raw = '{"headline":"X","deck":"","sections":[],"closing":""}'
    parsed = NarrativeComposer._parse_response(raw)
    assert parsed is not None
    assert parsed.headline == "X"


def test_composer_parse_response_returns_none_on_invalid():
    assert NarrativeComposer._parse_response("not json at all") is None


def test_composer_parse_response_tolerates_trailing_extra_data():
    # v5.5.10 회귀 — "Extra data: line 1 column N" (객체 뒤 꼬리 텍스트) 에 죽던 케이스.
    raw = (
        '{"headline":"끝맺음","deck":"","sections":'
        '[{"heading":"S","prose":"P"}],"closing":""}'
        "\n\n위 JSON 외 모델이 덧붙인 잡설 (무시되어야 함)."
    )
    parsed = NarrativeComposer._parse_response(raw)
    assert parsed is not None
    assert parsed.headline == "끝맺음"
    assert len(parsed.sections) == 1


def test_composer_parse_response_tolerates_leading_prose_no_fence():
    raw = '서두 설명입니다.\n{"headline":"Y","deck":"","sections":[],"closing":""}'
    parsed = NarrativeComposer._parse_response(raw)
    assert parsed is not None
    assert parsed.headline == "Y"


def test_composer_validate_references_filters_invalid_chart_ids():
    composed = ComposedReport(
        headline="X",
        sections=[
            ComposedSection(
                heading="s",
                prose="p",
                embedded_charts=["chart-scenarios", "chart-bogus", "chart-network"],
                embedded_blocks=["actor_cards", "made_up_block"],
            )
        ],
    )
    catalog = [
        {"id": "chart-scenarios", "title": "x", "hint": "y"},
        {"id": "chart-network", "title": "x", "hint": "y"},
    ]
    cleaned = NarrativeComposer._validate_references(composed, catalog)
    assert cleaned.sections[0].embedded_charts == ["chart-scenarios", "chart-network"]
    assert cleaned.sections[0].embedded_blocks == ["actor_cards"]


# ----------------------------------------------------------------------
# 4. Freeform_essay archetype registration
# ----------------------------------------------------------------------

def test_freeform_essay_registered():
    assert "freeform_essay" in list_archetypes()


def test_freeform_essay_template_path():
    arch = get_archetype("freeform_essay")
    assert arch.archetype_id == "freeform_essay"
    assert arch.template_path() == "archetypes/freeform_essay.html"


def test_freeform_essay_section_plan_is_empty():
    arch = get_archetype("freeform_essay")
    strategy = AnalysisStrategy(
        event_type="general",
        user_intent="what_happened",
        intent_confidence=0.5,
        core_questions=["q"],
        recommended_lenses=["context"],
    )
    plan = arch.section_plan(strategy)
    assert plan == []


# ----------------------------------------------------------------------
# 5. Token budget — narrative_composer flag wiring
# ----------------------------------------------------------------------

def test_token_budget_composer_only_in_deep():
    from src.token_budget import TokenBudget
    assert TokenBudget.for_mode("fast").use_llm_narrative_composer is False
    assert TokenBudget.for_mode("standard").use_llm_narrative_composer is False
    assert TokenBudget.for_mode("deep").use_llm_narrative_composer is True


# ----------------------------------------------------------------------
# 6. Composer payload builder — sanity check (no LLM)
# ----------------------------------------------------------------------

def _make_minimal_result_with_findings() -> FullAnalysisResult:
    """Helper — minimal FullAnalysisResult with a valid finding."""
    request = AnalysisRequest(event_description="테스트 사건", chat_id=0)
    ev = Evidence(evidence_id="E-001", quote_or_data="dummy", reliability="secondary")
    claim = Claim(
        claim_id="C-001",
        statement="핵심 주장",
        claim_type="inference",
        evidence_ids=["E-001"],
    )
    finding = AnalyticalFinding(
        finding_id="F-001",
        lens_id="context",
        answers_question="무슨 일이 있었는가?",
        main_claim=claim,
        evidence=[ev],
        confidence=ConfidenceProfile(
            source_diversity=0.5, data_freshness=0.7, expert_consensus=0.6,
        ),
    )
    return FullAnalysisResult(
        request=request,
        context=ContextAnalysis(event_name="테스트", summary="요약"),
        findings=[finding],
        judgment=JudgmentVerdict(main_judgment="판단", base_scenario="기본"),
    )


def test_composer_payload_includes_claims_catalog():
    result = _make_minimal_result_with_findings()
    catalog = [{"id": "chart-scenarios", "title": "x", "hint": "y"}]
    payload = NarrativeComposer._build_user_payload(result, catalog)
    assert "claims" in payload
    assert payload["claims"][0]["claim_id"] == "C-001"
    assert "available_charts" in payload
    assert payload["available_charts"][0]["id"] == "chart-scenarios"
    # JSON serializable
    json.dumps(payload, ensure_ascii=False)


def test_composer_payload_omits_empty_sections():
    request = AnalysisRequest(event_description="테스트", chat_id=0)
    result = FullAnalysisResult(request=request)  # 거의 모든 필드 None
    payload = NarrativeComposer._build_user_payload(result, [])
    # 빈 섹션은 키 자체가 없어야 함 (토큰 절약)
    assert "event" not in payload
    assert "players" not in payload
    assert "available_charts" not in payload


def test_revert_phonetic_in_broadcast_summary():
    """v7.6.4 — broadcast_summary 의 TTS 발음 표기 누수를 결정적 복원 (사용자 지적).

    더블유티아이→WTI, 디램→D램 등 *명확한* 약어만 복원. 숫자·%는 손대지 않음
    (프롬프트가 처리 — 결정적 변환은 오역 위험).
    """
    c = ComposedReport(
        headline="H",
        broadcast_summary=(
            "발효가 더 늦어지면 더블유티아이가 95달러 선에서 위로 튈 여지가 남습니다. "
            "한국 양사 디램 월 생산의 75퍼센트 수준이고, 에이치비엠 포 양산이 변수입니다."
        ),
        sections=[ComposedSection(heading="시세", prose="본문")],
    )
    NarrativeComposer._revert_phonetic_in_text(c)
    bs = c.broadcast_summary
    assert "더블유티아이" not in bs and "WTI" in bs
    assert "디램" not in bs and "D램" in bs
    assert "에이치비엠 포" not in bs and "HBM4" in bs
    # 숫자·%는 결정적 복원 대상 아님 (프롬프트 처리)
    assert "75퍼센트" in bs


def test_revert_phonetic_skips_ambiguous_and_preserves_prose():
    """v7.6.4 — 모호어(에스원=S-1 보안회사) 미복원 + prose 는 warn-only(편집체 보존)."""
    c = ComposedReport(
        headline="에스원 실적",  # 보안회사 명 — 복원 금지
        broadcast_summary="에스원이 분기 실적을 냈습니다.",
        sections=[ComposedSection(heading="x", prose="지피유 수요가 늘었습니다.")],
    )
    NarrativeComposer._revert_phonetic_in_text(c)
    # 에스원은 매핑에 없으므로 그대로 (오역 방지)
    assert "에스원" in c.broadcast_summary
    # prose 는 복원 안 함 (warn only) — 편집체 보존
    assert "지피유" in c.sections[0].prose


def test_revert_phonetic_noop_when_clean():
    """v7.6.4 — 발음 표기 없으면 무변경 (idempotent·부작용 없음)."""
    bs = "WTI가 95달러 선에서 움직이고 D램 수요는 견조합니다."
    c = ComposedReport(headline="H", broadcast_summary=bs,
                       sections=[ComposedSection(heading="x", prose="정상 본문입니다.")])
    NarrativeComposer._revert_phonetic_in_text(c)
    assert c.broadcast_summary == bs
