"""v5.5.0 — ReportBundle 빌더 + 계약 v1 회귀 테스트.

계약 SSOT: docs/CONTRACTS/report_bundle_v1.md.
검증: 결정론 provenance (§2/§3) · 참조 무결성 (§8) · 테마 토큰 파싱 (§Q4) ·
예시 번들 round-trip · /bundle 재emit 경로.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.handoff.bundle_builder import build_report_bundle
from src.models import (
    AnalysisRequest,
    ComposedReport,
    ComposedSection,
    ContextAnalysis,
    FullAnalysisResult,
    ReportBundle,
)

_EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "CONTRACTS" / "report_bundle_v1.example.json"


def _make_result() -> FullAnalysisResult:
    ctx = ContextAnalysis(
        date="2026-05-25",
        sources=["https://www.ft.com/a", "https://reuters.com/b"],
        time_series=[{"instrument": "삼성전자", "source": "KRX", "code": "005930", "unit": "원", "data": []}],
    )
    comp = ComposedReport(
        headline="H", deck="D", closing="C",
        confidence_score=0.7, confidence_summary="요약",
        sections=[
            ComposedSection(heading="시세", prose="본문", kicker="FACT", charts=[
                {"type": "candle", "title": "삼성전자 주봉", "data": [
                    {"date": "2026-03-02", "open": 1, "high": 2, "low": 1, "close": 2},
                    {"date": "2026-03-09", "open": 2, "high": 3, "low": 2, "close": 3},
                ]},
            ]),
            ComposedSection(heading="점유율", prose="본문2", charts=[
                {"type": "bar", "title": "점유율", "data": [{"label": "a", "value": 1}]},
            ]),
        ],
        watch_signals=[{"signal": "공시", "description": "d", "indicates": "i", "deadline": "2026-09-30"}],
        contradictions=[{"side_a": "A", "side_b": "B", "resolution": "분기"}],
        embedded_map={"center": [127.0, 37.5], "zoom": 5, "markers": [{"id": "mk-1", "name": "x", "lng": 127.1, "lat": 37.0}]},
    )
    return FullAnalysisResult(
        request=AnalysisRequest(event_description="x", mode="deep", emit_bundle=True),
        composed_report=comp, context=ctx,
        report_path="/r/analysis_TEST.html", report_theme="editorial_cream",
        system_version="v5.5.0",
    )


def test_example_bundle_round_trips():
    """예시 번들이 ReportBundle 스키마 + §8 참조 무결성 통과."""
    data = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    b = ReportBundle.model_validate(data)
    assert b.schema_version == 1
    # §10: section.map_ref 가 map.id 로 resolve.
    assert b.map is not None and b.map.id == "map-1"
    assert any(s.map_ref == "map-1" for s in b.sections)


def test_deterministic_provenance():
    """§2: market 매칭 차트 → measured/confirmed + source; 그 외 → inferred."""
    b = build_report_bundle(_make_result())
    by_type = {c.type: c for c in b.charts}
    assert by_type["candle"].provenance.origin == "measured"
    assert by_type["candle"].provenance.verification == "confirmed"
    assert by_type["candle"].provenance.sources[0].provider == "KRX"
    assert by_type["bar"].provenance.origin == "narrative_inference"
    assert by_type["bar"].provenance.verification == "inferred"


def test_theme_tokens_from_css():
    """§Q4: report.css [data-theme] 블록에서 8개 토큰 추출."""
    b = build_report_bundle(_make_result())
    assert b.report.theme is not None
    tokens = b.report.theme.tokens
    for key in ("bg", "card", "text", "muted", "accent", "up", "down", "border"):
        assert key in tokens and tokens[key].startswith("#")


def test_v55_limits():
    """v5.5.0 한계: claims 비어있음, map_ref null, prerendered_svg null (계약 명시)."""
    b = build_report_bundle(_make_result())
    assert b.claims == []
    assert all(s.map_ref is None for s in b.sections)
    assert all(c.prerendered_svg is None for c in b.charts)


def test_ref_integrity_guard():
    """§8: 미해결 chart_ref → ValidationError."""
    data = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    data["sections"][0]["chart_refs"] = ["does-not-exist"]
    with pytest.raises(Exception):
        ReportBundle.model_validate(data)


def test_bundle_reload_path():
    """/bundle 재emit: model_dump → model_validate → rebuild 동등."""
    res = _make_result()
    reloaded = FullAnalysisResult.model_validate(res.model_dump(mode="json"))
    b1 = build_report_bundle(res)
    b2 = build_report_bundle(reloaded)
    assert len(b1.charts) == len(b2.charts)
    assert b1.report.report_id == b2.report.report_id
