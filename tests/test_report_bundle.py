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
                # v6.1.1 — compact strip(보조 시계열) 차트. display="strip" 매핑 대상.
                {"type": "line", "title": "코스피", "role": "compact", "data": [
                    {"x": "2026-03-02", "y": 2600}, {"x": "2026-03-09", "y": 2650},
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


def test_chart_display_strip_vs_full():
    """§12 (v6.1.1): role=='compact' → display='strip', 그 외 → 'full'."""
    b = build_report_bundle(_make_result())
    by_type = {c.type: c for c in b.charts}
    # 보조 시계열(compact strip)
    assert by_type["line"].display == "strip"
    # 본문 단일차트
    assert by_type["candle"].display == "full"
    assert by_type["bar"].display == "full"
    # 항상 존재 (default 'full', null/'' 금지)
    assert all(c.display in ("strip", "full") for c in b.charts)


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


def test_timeline_flow_backbone_and_graceful():
    """v5.5.2 — 결정론 backbone (context.timeline 과거 + watch_signals 미래) + graceful."""
    from src.timeline_flow import build_timeline_flow
    res = _make_result()
    res.context.timeline = [{"date": "2025-09-27", "event": "협정", "impact": "x"}]
    tf = build_timeline_flow(res.context, res.composed_report)
    phases = {p["phase"] for p in tf["points"]}
    assert "past" in phases and "present" in phases and "future" in phases
    # 미래 점은 watch_signals deadline 에서 옴 (note='감시')
    assert any(p["phase"] == "future" and p["note"] == "감시" for p in tf["points"])
    # 데이터 전무 → None (섹션 생략)
    res.context.timeline = []
    res.composed_report.watch_signals = []
    assert build_timeline_flow(res.context, res.composed_report) is None


def test_timeline_composer_enrichment_overrides():
    """v5.5.2 — composer timeline_flow.past/future 가 backbone 우선 (하이브리드)."""
    from src.timeline_flow import build_timeline_flow
    res = _make_result()
    res.composed_report.timeline_flow = {
        "heading": "정전의 시간표",
        "past": [{"date": "2025-09-27", "label": "협정 체결"}],
        "future": [{"date": "2026-07-01", "label": "정전 정착", "branch": "낙관"}],
    }
    tf = build_timeline_flow(res.context, res.composed_report)
    assert tf["heading"] == "정전의 시간표"
    fut = [p for p in tf["points"] if p["phase"] == "future"]
    assert fut and fut[0]["label"] == "정전 정착" and fut[0]["note"] == "낙관"


def test_bundle_carries_timeline():
    """v5.5.2 — ReportBundle.timeline (additive) populated from shared assembler."""
    res = _make_result()
    res.context.timeline = [{"date": "2025-09-27", "event": "협정", "impact": "x"}]
    b = build_report_bundle(res)
    assert b.timeline is not None
    assert {p.phase for p in b.timeline.points} >= {"past", "present"}
    assert "timeline" in b.model_dump(mode="json")


def test_section_video_mapping_and_guards():
    """§13 (v7.3.0): composer video emit → BundleSectionVideo + 결정적 가드."""
    res = _make_result()
    res.composed_report.sections[0].video = {
        "narration": ["삼성전자 주봉이 두 주 연속 올랐습니다.", "거래량은 공시 주에 집중됐습니다."],
        "highlights": ["두 주 연속 상승"],
        "emphasis": ["두 주 연속", "번들에 없는 문구"],  # 후자는 drop 대상
        "narration_tts": ["삼성전자 주봉이 두 주 연속 올랐습니다."],
    }
    b = build_report_bundle(res)
    v = b.sections[0].video
    assert v is not None
    assert len(v.narration) == 2 and len(v.highlights) == 1
    # emphasis: 정확한 부분 문자열만 보존, 불일치 drop
    assert v.emphasis == ["두 주 연속"]
    assert v.narration_tts == ["삼성전자 주봉이 두 주 연속 올랐습니다."]
    # video 없는 섹션은 null (§11 optional 객체)
    assert b.sections[1].video is None
    # JSON 직렬화에 키 존재
    dumped = b.model_dump(mode="json")
    assert dumped["sections"][0]["video"]["narration"]
    assert dumped["sections"][1]["video"] is None


def test_section_video_caps_and_empty():
    """§13: narration ≤4 / highlights ≤3 캡 + 빈 emit → None."""
    res = _make_result()
    res.composed_report.sections[0].video = {
        "narration": [f"문장 {i}입니다." for i in range(6)],
        "highlights": [f"문구 {i}" for i in range(5)],
    }
    # narration/highlights 둘 다 실질 비면 video=None (validator 가 이미 정규화)
    res.composed_report.sections[1].video = {"narration": ["", "  "], "emphasis": ["x"]}
    b = build_report_bundle(res)
    v = b.sections[0].video
    assert v is not None and len(v.narration) == 4 and len(v.highlights) == 3
    assert b.sections[1].video is None


def test_report_video_mapping():
    """§13: report.video (intro/outro) 매핑 + 부재 시 null."""
    res = _make_result()
    res.composed_report.video = {
        "intro_narration": ["오프닝입니다.", "두 번째 문장입니다.", "초과분입니다."],
        "outro_narration": ["클로징입니다."],
    }
    b = build_report_bundle(res)
    assert b.report.video is not None
    assert len(b.report.video.intro_narration) == 2  # ≤2 캡
    assert b.report.video.outro_narration == ["클로징입니다."]
    # 부재 시 null
    b2 = build_report_bundle(_make_result())
    assert b2.report.video is None


def test_report_video_tts_channel(caplog):
    """§13 v7.4.1: report.video 의 intro/outro 발화 채널 + 누락 warn."""
    import logging
    res = _make_result()
    res.composed_report.video = {
        "intro_narration": ["SpaceX가 컴퓨팅을 빌려주고 있습니다."],
        "outro_narration": ["다음 주에 정해집니다."],
        "intro_narration_tts": ["스페이스엑스가 컴퓨팅을 빌려주고 있습니다."],
    }
    with caplog.at_level(logging.WARNING):
        b = build_report_bundle(res)
    v = b.report.video
    assert v is not None
    assert v.intro_narration_tts == ["스페이스엑스가 컴퓨팅을 빌려주고 있습니다."]
    # outro 는 위험 표기 없음 → tts 생략해도 warn 없음
    assert v.outro_narration_tts == []
    assert not any("report.video(outro)" in r.message for r in caplog.records)
    # intro 에 위험 표기 있는데 tts 누락이면 warn
    caplog.clear()
    res2 = _make_result()
    res2.composed_report.video = {"intro_narration": ["IPO를 앞두고 있습니다."]}
    with caplog.at_level(logging.WARNING):
        build_report_bundle(res2)
    assert any("report.video(intro)" in r.message for r in caplog.records)


def test_tts_gap_warn(caplog):
    """§13 v7.4.0: narration 에 TTS 위험 표기 있는데 narration_tts 누락 시 warn."""
    import logging
    from src.handoff.bundle_builder import _section_video, _warn_tts_gap, _TTS_RISK_RE
    # 위험 표기 탐지
    assert _TTS_RISK_RE.search("7.68% 빠졌습니다")
    assert _TTS_RISK_RE.search("GPU를 빌렸습니다")
    assert _TTS_RISK_RE.search("14일 → 4일")
    assert not _TTS_RISK_RE.search("목표가는 그대로였습니다")
    # narration_tts 누락 → warn
    with caplog.at_level(logging.WARNING):
        v = _section_video({"narration": ["삼성전자가 6.06% 내렸습니다."]}, "s1")
    assert v is not None
    assert any("narration_tts 누락" in r.message for r in caplog.records)
    # 개수 불일치 → warn
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        _section_video({
            "narration": ["삼성전자가 6.06% 내렸습니다.", "코스피는 7,634.76입니다."],
            "narration_tts": ["삼성전자가 육 점 영육 퍼센트 내렸습니다."],
        }, "s2")
    assert any("불일치" in r.message for r in caplog.records)
    # 위험 표기 없는 순한 한국어 → warn 없음
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        _section_video({"narration": ["목표가는 그대로였습니다."]}, "s3")
    assert not any("narration_tts" in r.message for r in caplog.records)


def test_composed_video_normalization():
    """ComposedSection/ComposedReport.video 비정형 emit 회복 (validator)."""
    sec = ComposedSection(heading="h", prose="p", video={"narration": "단일 문자열입니다."})
    assert sec.video == {"narration": ["단일 문자열입니다."]}
    sec2 = ComposedSection(heading="h", prose="p", video={"narration": [None, 1, " "]})
    assert sec2.video is None
    rep = ComposedReport(headline="H", video={"intro_narration": ["인트로."], "junk": ["x"]})
    assert rep.video == {"intro_narration": ["인트로."]}


def test_timeline_video_mapping(caplog):
    """§13 v7.6.0: timeline_flow.video → BundleTimeline.video (타임라인 씬 대본)."""
    import logging
    res = _make_result()
    res.context.timeline = [{"date": "2025-09-27", "event": "협정", "impact": "x"}]
    res.composed_report.timeline_flow = {
        "video": {
            "narration": ["이 일이 어떻게 시작됐는지, 처음부터 따라가 보겠습니다.",
                          "다음 분기점은 9월 말로 예고된 공시입니다."],
            "narration_tts": ["이 일이 어떻게 시작됐는지, 처음부터 따라가 보겠습니다.",
                              "다음 분기점은 구월 말로 예고된 공시입니다."],
        },
    }
    with caplog.at_level(logging.WARNING):
        b = build_report_bundle(res)
    assert b.timeline is not None and b.timeline.video is not None
    assert len(b.timeline.video.narration) == 2
    assert b.timeline.video.narration_tts[1].startswith("다음 분기점은 구월")
    # tts 가 정확히 채워졌으므로 timeline.video gap warn 없음
    assert not any("timeline.video" in r.message for r in caplog.records)
    # 직렬화에 포함 (additive)
    assert b.model_dump(mode="json")["timeline"]["video"]["narration"]


def test_timeline_video_absent_caps_and_warn(caplog):
    """§13 v7.6.0: 부재 시 null + narration ≤4 캡 + TTS gap warn."""
    import logging
    res = _make_result()
    res.context.timeline = [{"date": "2025-09-27", "event": "협정", "impact": "x"}]
    b = build_report_bundle(res)
    assert b.timeline is not None and b.timeline.video is None
    # 캡 + 위험 표기(숫자) 있는데 tts 누락 → warn
    res.composed_report.timeline_flow = {
        "video": {"narration": [f"{i + 1}번째 분기점을 지나갑니다." for i in range(6)]},
    }
    with caplog.at_level(logging.WARNING):
        b2 = build_report_bundle(res)
    assert b2.timeline.video is not None
    assert len(b2.timeline.video.narration) == 4
    assert any("timeline.video" in r.message for r in caplog.records)


def test_narration_75_char_limit(caplog):
    """§13 v7.6.0: 문장 한도 58→75 완화 — 60자대 문장은 warn 없이 통과, 75자 초과만 warn."""
    import logging
    from src.handoff.bundle_builder import _section_video
    ok = "가" * 70 + "입니다."          # 74자 — v7.6.0 부터 합법
    too_long = "가" * 73 + "입니다."    # 77자 — warn
    with caplog.at_level(logging.WARNING):
        _section_video({"narration": [ok]}, "s1")
    assert not any("한도" in r.message for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        _section_video({"narration": [too_long]}, "s2")
    assert any("75자 한도" in r.message for r in caplog.records)


def test_bundle_reload_path():
    """/bundle 재emit: model_dump → model_validate → rebuild 동등."""
    res = _make_result()
    reloaded = FullAnalysisResult.model_validate(res.model_dump(mode="json"))
    b1 = build_report_bundle(res)
    b2 = build_report_bundle(reloaded)
    assert len(b1.charts) == len(b2.charts)
    assert b1.report.report_id == b2.report.report_id
