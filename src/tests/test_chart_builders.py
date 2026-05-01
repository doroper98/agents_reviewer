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
    build_severity_chart_data,
    build_stacked_chart_data,
    build_visuals,
)


# ----------------------------------------------------------------------
# 1. Scenario chart data
# ----------------------------------------------------------------------


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
        ctx = ContextAnalysis(key_figures=[
            {"label": "유가", "value": "$108", "context": "WTI"},
            {"label": "환율", "value": "1,420원", "context": "KRW"},
        ])
        out = build_key_figures_chart_data(ctx)
        assert len(out) == 2
        assert out[0]["value"] == 108.0
        assert out[1]["value"] == 1420.0

    def test_falls_back_to_one_when_no_number(self) -> None:
        ctx = ContextAnalysis(key_figures=[{"label": "긴장도", "value": "높음"}])
        out = build_key_figures_chart_data(ctx)
        assert out[0]["value"] == 1.0


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
    def test_builds_segments_per_scenario(self) -> None:
        sa = ScenarioAnalysis(scenarios=[
            {
                "name": "S1",
                "impact_by_player": [
                    {"player": "A", "impact": "긍정"},
                    {"player": "B", "impact": "부정"},
                ],
            },
            {
                "name": "S2",
                "impact_by_player": [{"player": "A", "impact": "중립"}],
            },
        ])
        out = build_stacked_chart_data(sa)
        assert out is not None
        assert len(out["scenarios"]) == 2
        assert len(out["scenarios"][0]["segments"]) == 2

    def test_returns_none_when_no_impacts(self) -> None:
        sa = ScenarioAnalysis(scenarios=[{"name": "S1"}])
        assert build_stacked_chart_data(sa) is None


# ----------------------------------------------------------------------
# 9. Combined chart payload
# ----------------------------------------------------------------------


class TestChartPayload:
    def test_omits_empty_chart_types(self) -> None:
        # Only context + scenarios → only those keys present.
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
        assert "key_figures" in payload
        assert "severity_chain" not in payload
        assert "confidence" not in payload
        assert "network" not in payload
        assert "bubble" not in payload

    def test_full_payload_with_all_data(self) -> None:
        payload = build_chart_payload(
            context=ContextAnalysis(
                event_name="x",
                key_figures=[{"label": "유가", "value": "108"}],
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
                    "impact_by_player": [{"player": "P1", "impact": "긍정"}],
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
            "drawBubble", "drawGantt", "drawNetwork",
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
