"""v8.3.0 — 차트 다양성 회복 4종 세트 회귀 (사용자 catch 2026-07-02).

2026-06 event 보고서에서 line 비중 35%→53%, 8종(heatmap/range_bar/lollipop/area/
forecast/stacked/dual_line/choropleth) 0회 emit 로 확인된 다양성 붕괴의 재발 방지:

① 서사/시장 차트 분리 + 필수 하한 (composer SYSTEM_PROMPT)
② 자기교정 루프 — 굶주린 type 재균형 힌트 (usage_log → orchestrator → composer)
③ 다양성 쿼터 게이트 production log-only 배선 (deterministic_gate public 진입점)
④ 시계열 행수 상한 — 751행 3년 일봉 차단 (orchestrator downsample)
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.visual.usage_log import (
    KNOWN_CHART_TYPES,
    DATA_GATED_TYPES,
    NON_NARRATIVE_TYPES,
    composer_rebalance_hint,
)


REPO = Path(__file__).resolve().parents[2]


# ── ① 프롬프트 필수 하한 + 서사/시장 분리 ─────────────────────────────


def test_system_prompt_has_mandatory_diversity_floor() -> None:
    from src.agents.narrative_composer import SYSTEM_PROMPT
    assert "서사 차트" in SYSTEM_PROMPT           # 두 부류 구분 어휘
    assert "필수 하한" in SYSTEM_PROMPT           # 권장→필수 격상
    assert "다양성 하한은 서사 차트만 센다" in SYSTEM_PROMPT
    # 기존 '권장 (강제 X)' 완화 문구가 남아있으면 회귀
    assert "강제 X" not in SYSTEM_PROMPT


def test_system_prompt_line_is_last_resort() -> None:
    from src.agents.narrative_composer import SYSTEM_PROMPT
    assert "마지막 수단) → line" in SYSTEM_PROMPT


# ── ② 자기교정 루프 (starvation → 재균형 힌트) ────────────────────────


def _write_usage(path: Path, n_reports: int, types_per_report: list[str]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i in range(n_reports):
            f.write(json.dumps({"event": f"e{i}", "mode": "deep",
                                "types": types_per_report}) + "\n")


def test_rebalance_hint_empty_below_sample_floor(tmp_path: Path) -> None:
    p = tmp_path / "usage.jsonl"
    _write_usage(p, 9, ["line"])
    assert composer_rebalance_hint(path=p) == []


def test_rebalance_hint_returns_starved_narrative_types(tmp_path: Path) -> None:
    p = tmp_path / "usage.jsonl"
    _write_usage(p, 20, ["line", "bar"])
    hint = composer_rebalance_hint(path=p)
    assert hint, "line/bar 만 20건이면 굶주린 type 이 나와야"
    assert len(hint) <= 6
    # composer 가 선택할 수 없는 type 은 힌트에 절대 포함 금지
    assert not set(hint) & NON_NARRATIVE_TYPES
    # v8.6.3 — 데이터 의존 type 도 금지. 일별 값 60일치가 없는 보고서에
    # "calendar_heat 를 더 써라" 는 힌트는 없는 데이터를 지어내게 한다.
    assert not set(hint) & DATA_GATED_TYPES
    # 실제 6월 소멸 8종 계열이 포함돼야 (알파벳순 상위 6개 안에서)
    assert set(hint) <= set(KNOWN_CHART_TYPES)


def test_rebalance_hint_excludes_used_types(tmp_path: Path) -> None:
    p = tmp_path / "usage.jsonl"
    _write_usage(p, 20, ["heatmap", "forecast"])
    hint = composer_rebalance_hint(path=p)
    assert "heatmap" not in hint and "forecast" not in hint


def test_compose_system_prompt_byte_equal_without_hint() -> None:
    """힌트가 비면 프롬프트 byte-equal (기존 경로 무영향)."""
    from src.agents.narrative_composer import NarrativeComposer
    nc = NarrativeComposer.__new__(NarrativeComposer)
    nc.config = SimpleNamespace()
    base = nc._compose_system_prompt("standard")
    assert nc._compose_system_prompt("standard", []) == base
    assert nc._compose_system_prompt("standard", None) == base


def test_compose_system_prompt_injects_hint_block() -> None:
    from src.agents.narrative_composer import NarrativeComposer
    nc = NarrativeComposer.__new__(NarrativeComposer)
    nc.config = SimpleNamespace()
    out = nc._compose_system_prompt("standard", ["heatmap", "forecast"])
    assert "시각 다양성 재균형" in out
    assert "heatmap, forecast" in out
    assert "억지로 끼워 넣는 것은 금지" in out   # 오남용 가드 문구


def test_orchestrator_wires_rebalance_hint() -> None:
    src = (REPO / "src" / "orchestrator.py").read_text(encoding="utf-8")
    assert "composer_rebalance_hint" in src
    assert "starved_chart_types=_starved_hint" in src


# ── ③ 다양성 쿼터 게이트 log-only 배선 ────────────────────────────────


def test_monotony_gate_public_entrypoint() -> None:
    from src.visual.deterministic_gate import check_chart_type_monotony
    composed = {"sections": [{"charts": [
        {"type": "line", "data": []}, {"type": "line", "data": []},
        {"type": "line", "data": []}, {"type": "line", "data": []},
        {"type": "line", "data": []},
    ]}]}
    flag, cnt, distinct = check_chart_type_monotony(composed, "deep")
    assert flag is True and cnt == 5 and distinct == 1
    flag2, _, _ = check_chart_type_monotony(composed, "fast")
    assert flag2 is False   # fast 는 skip


def test_orchestrator_wires_monotony_gate() -> None:
    src = (REPO / "src" / "orchestrator.py").read_text(encoding="utf-8")
    assert "check_chart_type_monotony" in src


# ── ④ 시계열 행수 상한 (751행 3년 일봉 차단) ─────────────────────────


def test_downsample_caps_rows_and_keeps_last() -> None:
    from src.orchestrator import _DENSIFY_MAX_ROWS, _downsample_rows
    rows = [{"date": f"d{i}", "close": i} for i in range(751)]
    out = _downsample_rows(rows)
    assert len(out) <= _DENSIFY_MAX_ROWS + 1
    assert out[-1] is rows[-1]              # 마지막 봉(현재가) 보존
    assert out[0] is rows[0]
    short = [{"date": "a"}, {"date": "b"}]
    assert _downsample_rows(short) is short  # 상한 이하는 무변경


def test_densify_respects_cap() -> None:
    """3년 창을 가리키는 듬성 차트가 751행이 아닌 상한 이내로 치환돼야."""
    from src.orchestrator import _DENSIFY_MAX_ROWS, _densify_ts_charts
    days = [f"2024-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}" for i in range(700)]
    days = sorted(set(days)) * 3                       # 대충 700+ 거래일
    days = [f"{2023 + i // 336}-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}"
            for i in range(751)]
    series = {"instrument": "코스피", "data": [
        {"date": d, "close": 100 + i} for i, d in enumerate(sorted(set(days)))
    ]}
    n_series = len(series["data"])
    chart = {"type": "line", "title": "코스피 3년", "data": [
        {"x": series["data"][0]["date"], "y": 1},
        {"x": series["data"][n_series // 2]["date"], "y": 2},
        {"x": series["data"][-1]["date"], "y": 3},
    ]}
    composed = SimpleNamespace(sections=[SimpleNamespace(charts=[chart])])
    context = SimpleNamespace(time_series=[series])
    _densify_ts_charts(composed, context)
    assert 3 < len(chart["data"]) <= _DENSIFY_MAX_ROWS + 1
    assert chart["data"][-1]["x"] == series["data"][-1]["date"]
