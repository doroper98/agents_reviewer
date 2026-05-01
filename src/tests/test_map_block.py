"""Unit tests for v3.4.0 map block — BlockType + payload builder + builder registry.

Run:
    python -m pytest src/tests/test_map_block.py -v
"""

from __future__ import annotations

import pytest

from src.models import AnalysisBlock
from src.visual_builder import build_map_payload


# ----------------------------------------------------------------------
# 1. BlockType Literal includes "map"
# ----------------------------------------------------------------------


class TestMapBlockType:
    def test_block_type_accepts_map(self) -> None:
        # AnalysisBlock(block_type="map") must validate.
        b = AnalysisBlock(
            block_id="B-001",
            block_type="map",
            title="동북아 항만 지도",
            payload={
                "theme": "burgundy_mono",
                "center": [122.0, 22.0],
                "zoom": 3.0,
                "markers": [],
                "arcs": [],
            },
        )
        assert b.block_type == "map"
        assert b.payload["theme"] == "burgundy_mono"

    def test_invalid_block_type_rejected(self) -> None:
        with pytest.raises(Exception):
            AnalysisBlock(block_id="B-001", block_type="not_a_real_type")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# 2. build_map_payload — leaflet_config → MAP block payload
# ----------------------------------------------------------------------


class TestBuildMapPayload:
    def test_returns_none_for_disabled_config(self) -> None:
        assert build_map_payload({"enabled": False}) is None
        assert build_map_payload({}) is None
        assert build_map_payload(None) is None  # type: ignore[arg-type]

    def test_returns_none_for_empty_markers_and_lines(self) -> None:
        cfg = {"enabled": True, "center": [0, 0], "zoom": 3, "markers": [], "lines": []}
        assert build_map_payload(cfg) is None

    def test_converts_lat_lng_to_lng_lat_for_center(self) -> None:
        cfg = {
            "enabled": True,
            "center": [37.56, 126.97],  # leaflet [lat, lng]
            "zoom": 4,
            "markers": [{"lat": 37.56, "lng": 126.97, "label": "서울"}],
            "lines": [],
        }
        out = build_map_payload(cfg)
        assert out is not None
        assert out["center"] == [126.97, 37.56]  # maplibre [lng, lat]
        assert out["zoom"] == 4.0

    def test_marker_with_color_marked_highlight(self) -> None:
        cfg = {
            "enabled": True,
            "center": [0, 0],
            "zoom": 3,
            "markers": [
                {"lat": 1, "lng": 2, "label": "강조", "color": "#C9A84C"},
                {"lat": 3, "lng": 4, "label": "보통", "color": ""},
            ],
            "lines": [],
        }
        out = build_map_payload(cfg)
        assert out is not None
        m_hl = next(m for m in out["markers"] if m["name"] == "강조")
        m_no = next(m for m in out["markers"] if m["name"] == "보통")
        assert m_hl["highlight"] is True
        assert m_no["highlight"] is False

    def test_line_with_color_marked_highlight(self) -> None:
        cfg = {
            "enabled": True,
            "center": [0, 0],
            "zoom": 3,
            "markers": [
                {"lat": 1, "lng": 2, "label": "A"},
                {"lat": 3, "lng": 4, "label": "B"},
                {"lat": 5, "lng": 6, "label": "C"},
            ],
            "lines": [
                {"from": [1, 2], "to": [3, 4], "color": "#C9A84C"},
                {"from": [3, 4], "to": [5, 6], "color": ""},
            ],
        }
        out = build_map_payload(cfg)
        assert out is not None
        assert len(out["arcs"]) == 2
        assert out["arcs"][0]["highlight"] is True
        assert out["arcs"][1]["highlight"] is False

    def test_lng_lat_order_in_markers(self) -> None:
        cfg = {
            "enabled": True,
            "center": [0, 0],
            "zoom": 3,
            "markers": [{"lat": 37.56, "lng": 126.97, "label": "서울"}],
            "lines": [],
        }
        out = build_map_payload(cfg)
        assert out is not None
        m = out["markers"][0]
        assert m["lat"] == 37.56
        assert m["lng"] == 126.97

    def test_theme_default_burgundy_mono(self) -> None:
        cfg = {
            "enabled": True,
            "center": [0, 0],
            "zoom": 3,
            "markers": [{"lat": 1, "lng": 2, "label": "X"}],
            "lines": [],
        }
        out = build_map_payload(cfg)
        assert out is not None
        assert out["theme"] == "burgundy_mono"

    def test_theme_light_mono_explicit(self) -> None:
        cfg = {
            "enabled": True,
            "center": [0, 0],
            "zoom": 3,
            "markers": [{"lat": 1, "lng": 2, "label": "X"}],
            "lines": [],
        }
        out = build_map_payload(cfg, theme="light_mono")
        assert out is not None
        assert out["theme"] == "light_mono"

    def test_legend_built_from_arcs_and_markers(self) -> None:
        cfg = {
            "enabled": True,
            "center": [0, 0],
            "zoom": 3,
            "markers": [
                {"lat": 1, "lng": 2, "label": "A", "color": "#C9A84C"},
                {"lat": 3, "lng": 4, "label": "B"},
            ],
            "lines": [
                {"from": [1, 2], "to": [3, 4], "color": "#C9A84C"},
                {"from": [3, 4], "to": [1, 2], "color": ""},
            ],
        }
        out = build_map_payload(cfg)
        assert out is not None
        labels = [item["label"] for item in out["legend"]]
        assert "중점 회랑" in labels
        assert "일반 항로" in labels
        assert "관측 노드" in labels

    def test_unmatched_line_endpoint_synthesizes_marker(self) -> None:
        # Line endpoint not in markers list → builder synthesizes a placeholder node.
        cfg = {
            "enabled": True,
            "center": [0, 0],
            "zoom": 3,
            "markers": [{"lat": 1, "lng": 2, "label": "A"}],
            "lines": [{"from": [1, 2], "to": [9, 9], "color": ""}],
        }
        out = build_map_payload(cfg)
        assert out is not None
        assert len(out["arcs"]) == 1
        # Should have synthesized a node for [9, 9]
        synth = [m for m in out["markers"] if m["id"].startswith("_pt_")]
        assert len(synth) == 1


# ----------------------------------------------------------------------
# 3. Builder registry — _BLOCK_BUILDERS contains "map"
# ----------------------------------------------------------------------


class TestMapBuilderRegistry:
    def test_map_registered_in_block_builders(self) -> None:
        from src.agents.report_synthesizer import ReportSynthesizer
        assert "map" in ReportSynthesizer._BLOCK_BUILDERS
        builder = ReportSynthesizer._BLOCK_BUILDERS["map"]
        assert callable(builder)
