"""Unit tests for v3.2.0 chart builders + scenario layout.

Run:
    python -m pytest src/tests/test_chart_builders.py -v
"""

from __future__ import annotations

import os

import pytest

from src.models import (
    AnalysisRequest,
    ChainReactionAnalysis,
    ConfidenceProfile,
    ContextAnalysis,
    FullAnalysisResult,
    JudgmentVerdict,
    PlayerAnalysis,
    ScenarioAnalysis,
)
from src.visual_builder import (
    build_bubble_chart_data,
    build_chart_payload,
    build_confidence_chart_data,
    build_gantt_chart_data,
    build_key_figures_chart_data,
    build_network_chart_data,
    build_scenario_chart_data,
    build_scenario_table,
    build_severity_chart_data,
    build_stacked_chart_data,
    build_visuals,
)


# ----------------------------------------------------------------------
# 1. Scenario chart data
# ----------------------------------------------------------------------


class TestScenarioTable:
    """PR2 (v3.4.5) — confidence + driver_signals 통과."""

    def test_passes_confidence_as_float(self) -> None:
        sa = ScenarioAnalysis(scenarios=[
            {"name": "S1", "probability": "30%", "confidence": 0.72},
        ])
        out = build_scenario_table(sa)
        assert out[0]["confidence"] == {"raw": 72, "label": "중간"}

    def test_passes_confidence_as_percent(self) -> None:
        # > 1 이면 0~100 으로 간주
        sa = ScenarioAnalysis(scenarios=[
            {"name": "S1", "confidence": 85},
        ])
        out = build_scenario_table(sa)
        assert out[0]["confidence"]["raw"] == 85
        assert out[0]["confidence"]["label"] == "높음"

    def test_omits_confidence_when_missing(self) -> None:
        sa = ScenarioAnalysis(scenarios=[{"name": "S1"}])
        out = build_scenario_table(sa)
        assert out[0]["confidence"] is None

    def test_extracts_driver_signals_from_string_list(self) -> None:
        sa = ScenarioAnalysis(scenarios=[
            {"name": "S1", "driver_signals": ["유가 5% 추가 상승", "이란 외무 발언"]},
        ])
        out = build_scenario_table(sa)
        assert out[0]["driver_signals"] == ["유가 5% 추가 상승", "이란 외무 발언"]

    def test_extracts_driver_signals_from_dict_list(self) -> None:
        sa = ScenarioAnalysis(scenarios=[
            {"name": "S1", "driver_signals": [
                {"signal": "유가 급등"},
                {"name": "외환 개입"},
            ]},
        ])
        out = build_scenario_table(sa)
        assert "유가 급등" in out[0]["driver_signals"]
        assert "외환 개입" in out[0]["driver_signals"]

    def test_summarizes_impact_by_player(self) -> None:
        sa = ScenarioAnalysis(scenarios=[{
            "name": "S1",
            "impact_by_player": [
                {"player": "중국", "impact": "긍정적"},
                {"player": "미국", "impact": "부정적"},
            ],
        }])
        out = build_scenario_table(sa)
        assert "중국" in out[0]["impact"]
        assert "미국" in out[0]["impact"]


class TestScenarioChartData:
    def test_parses_percentage_strings(self) -> None:
        sa = ScenarioAnalysis(scenarios=[
            {"name": "여름의 그랜드 바겐", "tag": "최선", "probability": "20%"},
            {"name": "연출된 교착", "tag": "기본선", "probability": "35%"},
        ])
        out = build_scenario_chart_data(sa)
        assert len(out) == 2
        assert out[0]["prob"] == 20
        assert out[1]["prob"] == 35
        assert out[0]["tag"] == "최선"

    def test_parses_decimal_probability(self) -> None:
        sa = ScenarioAnalysis(scenarios=[{"name": "S1", "probability": 0.42}])
        out = build_scenario_chart_data(sa)
        assert out[0]["prob"] == 42

    def test_returns_empty_for_no_scenarios(self) -> None:
        assert build_scenario_chart_data(None) == []
        assert build_scenario_chart_data(ScenarioAnalysis()) == []


# ----------------------------------------------------------------------
# 2. Key figures donut data
# ----------------------------------------------------------------------


class TestKeyFiguresChartData:
    def test_extracts_numeric_value(self) -> None:
        # Insight Gate (PR1'): donut 은 ≥3 항목 + variance>0 일 때만 생성.
        ctx = ContextAnalysis(key_figures=[
            {"label": "유가", "value": "$108", "context": "WTI"},
            {"label": "환율", "value": "1,420원", "context": "KRW"},
            {"label": "수입", "value": "320억", "context": "월"},
        ])
        out = build_key_figures_chart_data(ctx)
        assert len(out) == 3
        assert out[0]["value"] == 108.0
        assert out[1]["value"] == 1420.0
        assert out[2]["value"] == 320.0

    def test_skips_when_no_number(self) -> None:
        # Insight Gate: 숫자 추출 실패 시 1.0 폴백 금지 (= 균등 도넛 안티패턴).
        # 그 항목은 skip; 결과가 < 3 항목이면 빈 list 반환.
        ctx = ContextAnalysis(key_figures=[
            {"label": "긴장도", "value": "높음"},
            {"label": "위험", "value": "심각"},
        ])
        assert build_key_figures_chart_data(ctx) == []

    def test_skips_when_uniform_values(self) -> None:
        # Insight Gate: 모든 값이 같으면 도넛 미생성 (균등 슬라이스 = 의미 없음).
        ctx = ContextAnalysis(key_figures=[
            {"label": "A", "value": "100"},
            {"label": "B", "value": "100"},
            {"label": "C", "value": "100"},
        ])
        assert build_key_figures_chart_data(ctx) == []


# ----------------------------------------------------------------------
# 3. Severity heatmap
# ----------------------------------------------------------------------


class TestSeverityChartData:
    def test_passes_severity_through(self) -> None:
        chain = ChainReactionAnalysis(chain=[
            {"title": "긴장 격화", "severity": "high"},
            {"title": "외교 채널", "severity": "medium"},
        ])
        out = build_severity_chart_data(chain)
        assert len(out) == 2
        assert out[0]["severity"] == "high"
        assert out[0]["title"] == "긴장 격화"


# ----------------------------------------------------------------------
# 4. Confidence triple
# ----------------------------------------------------------------------


class TestConfidenceChartData:
    def test_extracts_three_axes(self) -> None:
        verdict = JudgmentVerdict(
            confidence=ConfidenceProfile(
                source_diversity=0.8,
                data_freshness=0.6,
                expert_consensus=0.5,
            ),
        )
        out = build_confidence_chart_data(verdict)
        assert out["source_diversity"] == 0.8
        assert out["data_freshness"] == 0.6
        assert out["expert_consensus"] == 0.5

    def test_returns_none_for_no_judgment(self) -> None:
        assert build_confidence_chart_data(None) is None


# ----------------------------------------------------------------------
# 5. Bubble (risk matrix)
# ----------------------------------------------------------------------


class TestBubbleChartData:
    def test_maps_impact_strings(self) -> None:
        chain = ChainReactionAnalysis(wildcards=[
            {"event": "전면 봉쇄", "probability": "20%", "impact": "극심"},
            {"event": "외교 중재", "probability": "60%", "impact": "낮음"},
        ])
        out = build_bubble_chart_data(chain)
        assert len(out) == 2
        assert out[0]["x"] == 0.2
        assert out[0]["y"] >= 0.9
        assert out[1]["y"] <= 0.3

    def test_returns_none_when_no_wildcards(self) -> None:
        assert build_bubble_chart_data(None) is None
        assert build_bubble_chart_data(ChainReactionAnalysis()) is None


# ----------------------------------------------------------------------
# 6. Gantt timeline
# ----------------------------------------------------------------------


class TestGanttChartData:
    def test_builds_from_timeline(self) -> None:
        ctx = ContextAnalysis(timeline=[
            {"date": "2026-04-01", "event": "초기 긴장"},
            {"date": "2026-04-15", "event": "1차 회의"},
            {"date": "2026-04-30", "event": "발표"},
        ])
        out = build_gantt_chart_data(ctx)
        assert out is not None
        assert len(out) == 3
        assert out[0]["label"] == "초기 긴장"

    def test_returns_none_for_single_item(self) -> None:
        ctx = ContextAnalysis(timeline=[{"date": "2026-04-01", "event": "X"}])
        assert build_gantt_chart_data(ctx) is None


# ----------------------------------------------------------------------
# 7. Network graph
# ----------------------------------------------------------------------


class TestNetworkChartData:
    def test_builds_nodes_and_links(self) -> None:
        players = PlayerAnalysis(
            players=[
                {"name": "미국", "role_tag": "주요", "risk_level": "높음"},
                {"name": "이란", "role_tag": "대립", "risk_level": "극심"},
                {"name": "사우디", "role_tag": "동맹", "risk_level": "보통"},
            ],
            alliances=[
                {"group": ["미국", "사우디"], "nature": "동맹"},
                {"group": ["미국", "이란"], "nature": "대립"},
            ],
        )
        out = build_network_chart_data(players)
        assert out is not None
        assert len(out["nodes"]) == 3
        assert len(out["links"]) == 2
        link_types = {l["type"] for l in out["links"]}
        assert "동맹" in link_types
        assert "대립" in link_types


# ----------------------------------------------------------------------
# 8. Stacked bar
# ----------------------------------------------------------------------


class TestStackedChartData:
    def test_builds_segments_with_varied_magnitudes(self) -> None:
        # Insight Gate (PR1'): segment value 는 _impact_magnitude() 로 추출.
        # variance>0 + ≥4 segment 일 때만 차트 생성.
        sa = ScenarioAnalysis(scenarios=[
            {
                "name": "S1",
                "impact_by_player": [
                    {"player": "A", "impact": "극심한 타격"},
                    {"player": "B", "impact": "낮은 영향"},
                ],
            },
            {
                "name": "S2",
                "impact_by_player": [
                    {"player": "A", "impact": "중간 영향"},
                    {"player": "B", "impact": "높은 충격"},
                ],
            },
        ])
        out = build_stacked_chart_data(sa)
        assert out is not None
        assert len(out["scenarios"]) == 2
        # 모든 segment 의 value 가 정량 magnitude (0~1) 에서 추출됨
        all_vals = [s["value"] for sc in out["scenarios"] for s in sc["segments"]]
        assert max(all_vals) - min(all_vals) > 0  # variance>0

    def test_returns_none_when_uniform_magnitudes(self) -> None:
        # Insight Gate: 모든 segment 가 동일 magnitude → 균등 누적 막대 = 의미 없음.
        sa = ScenarioAnalysis(scenarios=[
            {"name": "S1", "impact_by_player": [
                {"player": "A", "impact": "중간"},
                {"player": "B", "impact": "중간"},
            ]},
            {"name": "S2", "impact_by_player": [
                {"player": "A", "impact": "중간"},
                {"player": "B", "impact": "중간"},
            ]},
        ])
        assert build_stacked_chart_data(sa) is None

    def test_returns_none_when_no_impacts(self) -> None:
        sa = ScenarioAnalysis(scenarios=[{"name": "S1"}])
        assert build_stacked_chart_data(sa) is None


# ----------------------------------------------------------------------
# 9. Combined chart payload
# ----------------------------------------------------------------------


class TestChartPayload:
    def test_omits_empty_chart_types(self) -> None:
        # PR1' Insight Gate: key_figures 는 ≥3 항목 + variance 있을 때만 생성.
        # 1개만 주면 key_figures 도 omit. scenarios 는 1개만 있어도 OK.
        payload = build_chart_payload(
            context=ContextAnalysis(
                event_name="x",
                key_figures=[{"label": "v", "value": "10"}],
            ),
            players=None,
            dynamics=None,
            chain_reaction=None,
            scenarios=ScenarioAnalysis(scenarios=[
                {"name": "S1", "tag": "최선", "probability": "30%"},
            ]),
            judgment=None,
        )
        assert "scenarios" in payload
        assert "key_figures" not in payload  # Insight Gate: <3 항목이라 skip
        assert "severity_chain" not in payload
        assert "confidence" not in payload
        assert "network" not in payload
        assert "bubble" not in payload

    def test_full_payload_with_all_data(self) -> None:
        # PR1' Insight Gate 충족: ≥3 varied key_figures, ≥4 varied stacked segments.
        payload = build_chart_payload(
            context=ContextAnalysis(
                event_name="x",
                key_figures=[
                    {"label": "유가", "value": "108"},
                    {"label": "환율", "value": "1420"},
                    {"label": "수입", "value": "320"},
                ],
                timeline=[
                    {"date": "1", "event": "A"},
                    {"date": "2", "event": "B"},
                ],
            ),
            players=PlayerAnalysis(
                players=[
                    {"name": "P1", "role_tag": "X", "risk_level": "높음"},
                    {"name": "P2", "role_tag": "Y", "risk_level": "낮음"},
                ],
                alliances=[{"group": ["P1", "P2"], "nature": "동맹"}],
            ),
            dynamics=None,
            chain_reaction=ChainReactionAnalysis(
                chain=[{"title": "C1", "severity": "high"}],
                wildcards=[{"event": "W1", "probability": "30%", "impact": "high"}],
            ),
            scenarios=ScenarioAnalysis(scenarios=[
                {
                    "name": "S1", "tag": "최선", "probability": "30%",
                    "impact_by_player": [
                        {"player": "P1", "impact": "극심한 타격"},
                        {"player": "P2", "impact": "낮은 영향"},
                    ],
                },
                {
                    "name": "S2", "tag": "악화", "probability": "40%",
                    "impact_by_player": [
                        {"player": "P1", "impact": "높은 충격"},
                        {"player": "P2", "impact": "중간"},
                    ],
                },
            ]),
            judgment=JudgmentVerdict(
                confidence=ConfidenceProfile(
                    source_diversity=0.7, data_freshness=0.7, expert_consensus=0.7,
                ),
            ),
        )
        # All applicable charts present.
        for key in ("scenarios", "key_figures", "severity_chain", "confidence",
                    "stacked", "bubble", "gantt", "network"):
            assert key in payload, f"missing chart payload: {key}"


# ----------------------------------------------------------------------
# 10. build_visuals integration
# ----------------------------------------------------------------------


class TestBuildVisualsIntegration:
    def test_chart_config_payload_attached(self) -> None:
        v = build_visuals(
            context=ContextAnalysis(event_name="x"),
            players=None,
            dynamics=None,
            chain_reaction=None,
            scenarios=ScenarioAnalysis(scenarios=[
                {"name": "S1", "tag": "최선", "probability": "20%"},
            ]),
            judgment=None,
        )
        assert v.chart_config["enabled"] is True
        assert "scenarios" in v.chart_config["payload"]

    def test_chart_config_disabled_when_empty(self) -> None:
        v = build_visuals(
            context=None, players=None, dynamics=None,
            chain_reaction=None, scenarios=None, judgment=None,
        )
        assert v.chart_config["enabled"] is False


# ----------------------------------------------------------------------
# 11. Static assets exist + scenario_table card layout
# ----------------------------------------------------------------------


class TestStaticAssets:
    def test_d3_minified_present(self) -> None:
        path = os.path.join(
            os.path.dirname(__file__), "..", "templates", "static", "d3.v7.min.js",
        )
        assert os.path.exists(path), "d3.v7.min.js missing in templates/static"
        assert os.path.getsize(path) > 100_000  # ~270KB expected

    def test_charts_js_present(self) -> None:
        path = os.path.join(
            os.path.dirname(__file__), "..", "templates", "static", "charts.js",
        )
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        # Verify all 9 chart types are exposed.
        for name in (
            "drawScenarioBar", "drawKeyFiguresDonut", "drawSeverityHeatmap",
            "drawConfidenceTriple", "drawTimeseriesLine", "drawStackedBar",
            "drawBubble", "drawGantt",
        ):
            assert name in content, f"charts.js missing function: {name}"

    def test_charts_css_present(self) -> None:
        path = os.path.join(
            os.path.dirname(__file__), "..", "templates", "static", "charts.css",
        )
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        for cls in (".scenario-grid", ".scenario-card", ".chart-card", ".chart-tooltip"):
            assert cls in content, f"charts.css missing class: {cls}"


class TestScenarioCardTemplate:
    def test_block_template_uses_card_grid(self) -> None:
        path = os.path.join(
            os.path.dirname(__file__), "..", "templates", "blocks", "scenario_table.html",
        )
        with open(path) as f:
            content = f.read()
        assert "scenario-grid" in content
        assert "scenario-card" in content
        # Old <table> markup should be gone.
        assert "<table" not in content

    def test_main_report_uses_card_grid(self) -> None:
        path = os.path.join(
            os.path.dirname(__file__), "..", "templates", "report.html",
        )
        with open(path) as f:
            content = f.read()
        # The render_scenarios macro should now use scenario-grid (not data-table).
        # Search just in the macro region.
        macro_start = content.find("{% macro render_scenarios")
        macro_end = content.find("{% endmacro %}", macro_start)
        macro_body = content[macro_start:macro_end]
        assert "scenario-grid" in macro_body
        assert "<table" not in macro_body
