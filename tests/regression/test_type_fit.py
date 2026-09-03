"""차트 type-fit 파이프라인 회귀 가드 (v8.6.4).

기능 SSOT: [docs/CHART_REDESIGN_V8_6_PLAN.md](../../docs/CHART_REDESIGN_V8_6_PLAN.md) §6.
구현: `src/visual/type_fit.py` (규칙 R1~R7) + `src/orchestrator.py` 호출부 +
`src/config.py:enable_type_refit` (`V8_TYPE_REFIT`) + `src/visual/usage_log.py` 의
`refit` 필드 · `refit_distribution`.

본 파일이 지키는 것:
1. 규칙별 positive 1건 이상 · negative 2건 이상 (확신 없으면 안 건드린다)
2. 값·라벨을 만들지 않는다 (플랜 §6.2 안전 규칙 ①·②)
3. 변환 후 가드 실패면 원본 유지 (안전 규칙 ③)
4. flag OFF 면 호출 자체가 없다 (byte-equal)
5. orchestrator 배선이 `_densify_ts_charts` 뒤 · `_reconcile_visual_references` 앞
6. `append_run(refit=...)` JSONL additive
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from src.visual.type_fit import (
    RULES,
    RefitEvent,
    refit_chart,
    refit_charts,
    refit_records,
    scan_reports,
)
from src.visual.schemas import validate_chart_data


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ORCH = _REPO_ROOT / "src" / "orchestrator.py"


def _rule(chart: dict, fmt: str = "standard") -> str | None:
    return refit_chart(chart, report_format=fmt)[1]


def _out(chart: dict, fmt: str = "standard") -> dict:
    return refit_chart(chart, report_format=fmt)[0]


# ─── 규칙표 자체 ────────────────────────────────────────────────────────

def test_rules_table_matches_plan_6_2() -> None:
    """R1~R7 이 전부 있고, R6/R7 은 *변환하지 않는* 규칙으로 표시돼 있다."""
    ids = [r.id for r in RULES]
    assert ids == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    by_id = {r.id: r for r in RULES}
    assert by_id["R6"].active is False, "R6 은 명시적 no-op (플랜 §6.2)"
    assert by_id["R7"].active is False, "R7 은 계측 전용 (event_timeline 대기)"
    assert all(r.active for r in RULES if r.id in {"R1", "R2", "R3", "R4", "R5"})


# ─── R1 bar → histogram ─────────────────────────────────────────────────

def _bins(labels: list[str], counts: list[float]) -> dict:
    return {"type": "bar", "title": "구간별", "unit_label": "만 명",
            "data": [{"label": l, "value": v} for l, v in zip(labels, counts)]}


def test_r1_converts_range_labelled_bar() -> None:
    chart = _bins(["1~2천", "2~3천", "3~5천", "5~7천"], [9, 15, 22, 14])
    out, rule = refit_chart(chart, report_format="standard")
    assert rule == "R1"
    assert out["type"] == "histogram"
    assert out["data"] == [
        {"bin": "1~2천", "count": 9.0}, {"bin": "2~3천", "count": 15.0},
        {"bin": "3~5천", "count": 22.0}, {"bin": "5~7천", "count": 14.0},
    ]
    assert out["unit_label"] == "만 명", "payload 는 그대로 계승"
    assert validate_chart_data("histogram", out["data"])[0]


def test_r1_accepts_all_four_bin_patterns() -> None:
    assert _rule(_bins(["20대", "30대", "40대", "50대"], [4, 9, 15, 8])) == "R1"
    assert _rule(_bins(["20세", "30세", "40세", "50세"], [4, 9, 15, 8])) == "R1"
    assert _rule(_bins(
        ["1억 미만", "2억 이하", "3억 초과", "5억 이상"], [4, 9, 15, 8])) == "R1"
    assert _rule(_bins(["10-20", "20-30", "30-40", "40-50"], [4, 9, 15, 8])) == "R1"


def test_r1_negative_plain_category_bar_untouched() -> None:
    """negative ① — 평범한 범주 비교는 순서 있는 구간이 아니다."""
    chart = {"type": "bar", "title": "점유율", "unit_label": "%", "data": [
        {"label": "TSMC", "value": 58.1}, {"label": "삼성", "value": 12.4},
        {"label": "인텔", "value": 4.0}, {"label": "SMIC", "value": 3.2}]}
    out, rule = refit_chart(chart, report_format="standard")
    assert rule is None and out is chart, "원본 객체 그대로여야 한다"


def test_r1_negative_non_integer_and_negative_values() -> None:
    """negative ② — 도수는 셀 수 있는 값이다. 소수·음수는 histogram 이 아니다.

    라벨이 구간 모양이어도 값이 도수가 아니면 R1 은 적용되지 않는다. 짧은 라벨 ·
    정수 값이면 표현 규칙 R5 가 대신 잡을 수 있는데(세로 칸), 그건 type 을 바꾸는
    변환이 아니라 같은 bar 의 표현이므로 별개다 — 여기서 막아야 하는 것은 R1 이다.
    """
    frac = _rule(_bins(["1~2천", "2~3천", "3~5천", "5~7천"], [9.4, 15, 22, 14]))
    assert frac is None, "소수 도수는 어떤 규칙도 안 잡는다"
    neg = _rule(_bins(["1~2천", "2~3천", "3~5천", "5~7천"], [-1, 15, 22, 14]))
    assert neg != "R1", "음수는 도수가 아니다"


def test_r1_negative_too_few_bins_and_long_label() -> None:
    """negative ③ — 구간 4개 미만, 또는 bin 라벨이 12자를 넘으면 가드가 거절한다."""
    assert _rule(_bins(["1~2천", "2~3천", "3~5천"], [9, 15, 22])) != "R1"
    long_bin = "1~2천만원 미만 대출 구간"          # 13자 초과 → HistogramRow 가 거절
    assert len(long_bin) > 12
    assert _rule(_bins([long_bin, "2~3천", "3~5천", "5~7천"], [9, 15, 22, 14])) != "R1"


def test_r1_does_not_invent_empty_bins() -> None:
    """안전 규칙 ① — 변환은 필드 이름만 바꾼다. 행 수가 늘거나 줄면 안 된다."""
    chart = _bins(["1~2천", "2~3천", "3~5천", "5~7천", "7~9천"], [9, 0, 22, 14, 3])
    out = _out(chart)
    assert len(out["data"]) == 5
    assert [r["count"] for r in out["data"]] == [9.0, 0.0, 22.0, 14.0, 3.0]


# ─── R2 donut / stacked(1) → treemap ────────────────────────────────────

_TWO_LAYER = [
    ("반도체 · 메모리", 40), ("반도체 · 시스템", 20),
    ("자동차 · 완성차", 25), ("자동차 · 부품", 10),
    ("석유화학 · 기초", 8), ("석유화학 · 정밀", 6),
]


def _donut(rows: list[tuple[str, float]]) -> dict:
    return {"type": "donut", "title": "수출 구성", "unit_label": "억달러",
            "data": [{"label": l, "value": v} for l, v in rows]}


def test_r2_converts_two_layer_donut() -> None:
    out, rule = refit_chart(_donut(_TWO_LAYER), report_format="standard")
    assert rule == "R2"
    assert out["type"] == "treemap"
    groups = {g["label"]: [k["label"] for k in g["children"]] for g in out["data"]["children"]}
    assert groups == {
        "반도체": ["메모리", "시스템"],
        "자동차": ["완성차", "부품"],
        "석유화학": ["기초", "정밀"],
    }
    assert out["data"]["unit_label"] == "억달러"
    assert validate_chart_data("treemap", out["data"])[0]


def test_r2_accepts_slash_and_gt_separators() -> None:
    slash = [(l.replace(" · ", "/"), v) for l, v in _TWO_LAYER]
    gt = [(l.replace(" · ", " > "), v) for l, v in _TWO_LAYER]
    assert _rule(_donut(slash)) == "R2"
    assert _rule(_donut(gt)) == "R2"


def test_r2_converts_single_scenario_stacked() -> None:
    chart = {"type": "stacked", "title": "구성", "data": {"scenarios": [
        {"name": "2026", "segments": [{"label": l, "value": v} for l, v in _TWO_LAYER]}]}}
    out, rule = refit_chart(chart, report_format="standard")
    assert rule == "R2" and out["type"] == "treemap"


def test_r2_negative_flat_donut_untouched() -> None:
    """negative ① — 1층 라벨은 여전히 donut 자리다."""
    flat = _donut([("메모리", 40), ("시스템", 20), ("완성차", 25),
                   ("부품", 10), ("기초", 8), ("정밀", 6)])
    out, rule = refit_chart(flat, report_format="standard")
    assert rule is None and out is flat


def test_r2_negative_partial_separator_is_not_converted() -> None:
    """negative ② — 분리자 없는 라벨은 잎 1개짜리 그룹이 되어 제약에 걸린다.

    데이터를 버리지 않으면서(안전 규칙 ②) 애매한 경우를 배제하는 방식이다.
    """
    mixed = list(_TWO_LAYER) + [("기타", 5)]
    assert _rule(_donut(mixed)) is None


def test_r2_negative_single_group_or_too_few_leaves() -> None:
    """negative ③ — 그룹이 하나뿐이면 2층이 아니고, 잎 6개 미만은 donut 이 낫다."""
    one_group = _donut([("반도체 · 메모리", 40), ("반도체 · 시스템", 20),
                        ("반도체 · 파운드리", 15), ("반도체 · 기타", 5)])
    assert _rule(one_group) is None
    few = _donut([("반도체 · 메모리", 40), ("반도체 · 시스템", 20),
                  ("자동차 · 완성차", 25), ("자동차 · 부품", 10)])
    assert _rule(few) is None, "잎 4개는 treemap 이 아니다"


def test_r2_negative_multi_scenario_stacked_untouched() -> None:
    """negative ④ — 시나리오가 여럿이면 시점 비교라 treemap 이 아니다."""
    chart = {"type": "stacked", "title": "분기별", "data": {"scenarios": [
        {"name": "1Q", "segments": [{"label": l, "value": v} for l, v in _TWO_LAYER]},
        {"name": "2Q", "segments": [{"label": l, "value": v} for l, v in _TWO_LAYER]}]}}
    out, rule = refit_chart(chart, report_format="standard")
    assert rule is None and out is chart


def test_r2_preserves_every_value() -> None:
    """안전 규칙 ② — 잎의 값 합이 원본 합과 같다."""
    out = _out(_donut(_TWO_LAYER))
    total = sum(k["value"] for g in out["data"]["children"] for k in g["children"])
    assert total == sum(v for _, v in _TWO_LAYER)


# ─── R3 heatmap → calendar_heat ─────────────────────────────────────────

def _daily_heatmap(n: int, y: str = "코스피", *, start=date(2026, 3, 2)) -> dict:
    return {"type": "heatmap", "title": "일별 변동", "data": [
        {"x": (start + timedelta(days=i)).isoformat(), "y": y, "value": (i % 9) * 0.4}
        for i in range(n)]}


def test_r3_converts_daily_grid_heatmap() -> None:
    out, rule = refit_chart(_daily_heatmap(70), report_format="standard")
    assert rule == "R3"
    assert out["type"] == "calendar_heat"
    assert len(out["data"]["values"]) == 70
    assert out["data"]["metric_label"] == "코스피", "있던 y 라벨 재사용 (생성 아님)"
    assert validate_chart_data("calendar_heat", out["data"])[0]


def test_r3_negative_non_date_axis_untouched() -> None:
    """negative ① — x 가 날짜가 아니면 그냥 격자 heatmap 이다."""
    chart = {"type": "heatmap", "title": "요일×시간", "data": [
        {"x": f"{d}요일", "y": f"{h}시", "value": (d + h) % 5}
        for d in range(5) for h in range(14)]}
    out, rule = refit_chart(chart, report_format="standard")
    assert rule is None and out is chart


def test_r3_negative_multiple_y_series_untouched() -> None:
    """negative ② — y 가 여럿이면 진짜 2축 격자다 (달력은 한 지표만 그린다)."""
    rows = _daily_heatmap(70)["data"] + _daily_heatmap(70, "코스닥")["data"]
    assert _rule({"type": "heatmap", "title": "두 지수", "data": rows}) is None


def test_r3_negative_short_series_and_severity_form() -> None:
    """negative ③ — 60일 미만은 격자가 안 서고, 강도 트랙형은 날짜 축이 아니다."""
    assert _rule(_daily_heatmap(40)) is None
    severity = {"type": "heatmap", "title": "위험도", "data": [
        {"title": f"항목{i}", "severity": "high"} for i in range(6)]}
    assert _rule(severity) is None


def test_r3_negative_over_400_rows_not_truncated() -> None:
    """안전 규칙 ② — 상한(400)을 맞추려고 행을 자르지 않는다. 그냥 변환하지 않는다."""
    chart = _daily_heatmap(420)
    out, rule = refit_chart(chart, report_format="standard")
    assert rule is None
    assert out is chart and len(out["data"]) == 420


# ─── R4 slope → range_bar(before_after) ─────────────────────────────────

def _slope(n: int) -> dict:
    return {"type": "slope", "title": "2 시점", "data": {
        "left_label": "2024", "right_label": "2026",
        "items": [{"label": f"항목{i}", "a": float(i), "b": float(i * 2 + 1)}
                  for i in range(1, n + 1)]}}


def test_r4_converts_crowded_slope() -> None:
    out, rule = refit_chart(_slope(9), report_format="standard")
    assert rule == "R4"
    assert out["type"] == "range_bar" and out["mode"] == "before_after"
    assert out["before_label"] == "2024" and out["after_label"] == "2026"
    assert out["data"][0] == {"label": "항목1", "before": 1.0, "after": 3.0}
    assert len(out["data"]) == 9
    assert validate_chart_data("range_bar", out["data"])[0]


def test_r4_negative_seven_items_untouched() -> None:
    """negative ① — 7개까지는 기울기가 읽힌다 (플랜 §6.2 의 임계)."""
    chart = _slope(7)
    out, rule = refit_chart(chart, report_format="standard")
    assert rule is None and out is chart


def test_r4_negative_equal_before_after_reverts_to_original() -> None:
    """negative ② + 안전 규칙 ③ — before == after 행은 range_bar 가드가 거절한다.

    변환은 시도되지만 가드에서 막히므로 *원본이 살아남아야* 한다 ('더 나빠지지 않기').
    """
    chart = _slope(9)
    chart["data"]["items"][0]["b"] = chart["data"]["items"][0]["a"]
    out, rule = refit_chart(chart, report_format="standard")
    assert rule is None, "가드 실패 → 규칙 미적용"
    assert out is chart, "원본 객체 그대로"


# ─── R5 bar → 세로 칸 (표현만) ──────────────────────────────────────────

def _short_bar(n: int = 3, *, unit: str = "건") -> dict:
    labels = ["한국", "미국", "일본", "독일", "중국", "인도", "영국", "대만"][:n]
    return {"type": "bar", "title": "건수", "unit_label": unit,
            "data": [{"label": l, "value": float(i + 3)} for i, l in enumerate(labels)]}


def test_r5_sets_vertical_orientation_only() -> None:
    chart = _short_bar(4)
    out, rule = refit_chart(chart, report_format="standard")
    assert rule == "R5"
    assert out["type"] == "bar", "type 은 그대로 — 표현만 바뀐다"
    assert out["orientation"] == "vertical"
    assert out["data"] == chart["data"], "data 는 한 글자도 안 건드린다"


def test_r5_negative_long_labels_and_too_many_bars() -> None:
    """negative ① — charts.js rung 게이트(라벨 ≤6자 · 항목 ≤8)와 같은 조건."""
    long_label = _short_bar(3)
    long_label["data"][0]["label"] = "대한민국 반도체 산업"
    assert _rule(long_label) is None
    assert _rule(_short_bar(8)) == "R5"
    nine = _short_bar(8)
    nine["data"].append({"label": "호주", "value": 11.0})
    assert _rule(nine) is None


def test_r5_negative_percent_and_non_integer_values() -> None:
    """negative ② — 비율·소수는 셀 수 없다 (칸이 아니라 캡슐이 맞다)."""
    assert _rule(_short_bar(3, unit="%")) is None
    frac = _short_bar(3)
    frac["data"][1]["value"] = 4.5
    assert _rule(frac) is None


def test_r5_negative_explicit_option_is_respected() -> None:
    """negative ③ — 작성 모델이 표현을 지정했으면 존중한다."""
    fixed = _short_bar(3)
    fixed["orientation"] = "horizontal"
    assert _rule(fixed) is None
    textured = _short_bar(3)
    textured["texture"] = "capsule"
    assert _rule(textured) is None


# ─── R6 no-op · R7 계측 전용 ────────────────────────────────────────────

def test_r6_line_is_never_touched() -> None:
    """R6 — '점 하나 = 하루' 는 v8.6.1 렌더러 소유. 여기서 손대면 이중 소유."""
    chart = {"type": "line", "title": "추세", "data": [
        {"x": f"2026-03-{d:02d}", "y": 100.0 + d} for d in range(1, 29)]}
    out, rule = refit_chart(chart, report_format="standard")
    assert rule is None and out is chart


def test_r7_zero_duration_gantt_is_logged_not_changed() -> None:
    chart = {"type": "gantt", "title": "사건", "data": [
        {"label": "a", "start": "2026-01-01", "end": "2026-01-01"},
        {"label": "b", "start": "2026-02-01", "end": "2026-02-01"}]}
    out, rule = refit_chart(chart, report_format="standard")
    assert rule == "R7-pending"
    assert out is chart, "R7 은 세기만 한다 (변환 대상 type 이 아직 없다)"


def test_r7_negative_real_gantt_untouched() -> None:
    chart = {"type": "gantt", "title": "일정", "data": [
        {"label": "a", "start": "2026-01-01", "end": "2026-02-01"},
        {"label": "b", "start": "2026-02-01", "end": "2026-03-01"}]}
    assert _rule(chart) is None


# ─── refit_charts (보고서 단위) ─────────────────────────────────────────

def test_refit_charts_rewrites_sections_and_reports_events() -> None:
    from src.models import ComposedReport, ComposedSection

    report = ComposedReport(headline="H", deck="D", sections=[
        ComposedSection(heading="A", prose="p", charts=[
            _bins(["1~2천", "2~3천", "3~5천", "5~7천"], [9, 15, 22, 14]),
            {"type": "line", "title": "추세", "data": [
                {"x": "2026-03-01", "y": 1.0}, {"x": "2026-03-02", "y": 2.0}]},
        ]),
        ComposedSection(heading="B", prose="p", charts=[_donut(_TWO_LAYER)]),
    ])
    events = refit_charts(report, report_format="standard")
    assert [e.rule for e in events] == ["R1", "R2"]
    assert [c["type"] for c in report.sections[0].charts] == ["histogram", "line"]
    assert [c["type"] for c in report.sections[1].charts] == ["treemap"]
    assert refit_records(events) == [
        {"from": "bar", "to": "histogram", "rule": "R1"},
        {"from": "donut", "to": "treemap", "rule": "R2"},
    ]


def test_refit_charts_reruns_drop_invalid_charts() -> None:
    """플랜 §6.1 — 변환된 섹션은 `_drop_invalid_charts` 를 다시 탄다."""
    from src.models import ComposedSection

    section = ComposedSection(heading="A", prose="p", charts=[
        _bins(["1~2천", "2~3천", "3~5천", "5~7천"], [9, 15, 22, 14])])
    report = SimpleNamespace(sections=[section])
    refit_charts(report, report_format="standard")
    rebuilt = report.sections[0]
    assert isinstance(rebuilt, ComposedSection)
    assert rebuilt is not section, "재검증된 새 객체로 교체된다"
    assert rebuilt.charts[0]["type"] == "histogram"


def test_refit_charts_no_op_report_keeps_section_objects() -> None:
    """바꿀 게 없으면 섹션 객체까지 그대로 (불필요한 재검증 없음)."""
    from src.models import ComposedSection

    section = ComposedSection(heading="A", prose="p", charts=[
        {"type": "line", "title": "추세", "data": [
            {"x": "2026-03-01", "y": 1.0}, {"x": "2026-03-02", "y": 2.0}]}])
    report = SimpleNamespace(sections=[section])
    assert refit_charts(report, report_format="standard") == []
    assert report.sections[0] is section


def test_refit_event_record_shape() -> None:
    ev = RefitEvent(rule="R1", from_type="bar", to_type="histogram",
                    section=0, index=2, title="구간별", report_format="reportage")
    assert ev.as_record() == {"from": "bar", "to": "histogram", "rule": "R1"}


# ─── usage_log 계측 ─────────────────────────────────────────────────────

def test_append_run_writes_refit_field_additively(tmp_path: Path) -> None:
    from src.visual.usage_log import analyze, append_run

    log = tmp_path / "usage.jsonl"
    append_run("e1", "deep", ["histogram"], refit=[
        {"from": "bar", "to": "histogram", "rule": "R1"}], path=log)
    append_run("e2", "deep", ["line"], path=log)          # refit 없음
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["refit"] == [{"from": "bar", "to": "histogram", "rule": "R1"}]
    assert "refit" not in lines[1], "빈 refit 은 필드 자체를 안 쓴다 (JSONL additive)"
    assert analyze(path=log)["refit_distribution"] == {"R1": 1}


# ─── orchestrator 배선 · flag OFF byte-equal ────────────────────────────

def _call_site() -> tuple[str, int, int, int]:
    src = _ORCH.read_text(encoding="utf-8")
    return (
        src,
        src.index("_densify_ts_charts(result.composed_report"),
        src.index("refit_charts(") if "refit_charts(" in src else -1,
        src.index("_reconcile_visual_references(result.composed_report"),
    )


def test_orchestrator_calls_refit_between_densify_and_reconcile() -> None:
    """플랜 §6.1 — `_densify_ts_charts` 직후 · `_reconcile_visual_references` 직전."""
    src, densify, refit, reconcile = _call_site()
    assert refit > 0, "orchestrator 가 type_fit 을 호출하지 않는다"
    assert densify < refit < reconcile, (
        "호출 순서가 어긋났다 — 밀도 보정 뒤에 type 을 정해야 하고, "
        "시각물 약속 정리(본문 대조)는 최종 type 이 정해진 뒤여야 한다"
    )


def test_orchestrator_gates_refit_behind_flag() -> None:
    """flag OFF 면 호출 자체를 안 한다 → v8.6.3 과 byte-equal."""
    src, _, refit, _ = _call_site()
    guard = 'if getattr(self.config, "enable_type_refit", True):'
    assert guard in src
    assert src.index(guard) < refit, "게이트가 호출보다 앞서야 한다"


def test_orchestrator_passes_refit_records_to_usage_log() -> None:
    src = _ORCH.read_text(encoding="utf-8")
    assert re.search(r"refit=refit_records\(refit_events\)", src), (
        "type-fit 이력이 usage_log 로 안 흘러가면 오배치 빈도를 관측할 수 없다"
    )


def test_orchestrator_sequence_end_to_end_mocked(tmp_path: Path) -> None:
    """orchestrator 가 실제로 하는 순서를 그대로 밟아 본다 (LLM·네트워크 없이).

    ① flag 확인 → ② `refit_charts` → ③ 살아남은 type 집계 → ④ `append_run(refit=...)`.
    보고서 하나가 통과하면 차트 type 이 바뀌고 그 이력이 JSONL 한 줄에 남아야 한다.
    """
    from src.config import Config
    from src.models import ComposedReport, ComposedSection
    from src.visual.usage_log import analyze, append_run

    report = ComposedReport(headline="H", deck="D", sections=[
        ComposedSection(heading="A", prose="p", charts=[
            _bins(["1~2천", "2~3천", "3~5천", "5~7천"], [9, 15, 22, 14]),
            _donut(_TWO_LAYER),
        ])])
    log = tmp_path / "usage.jsonl"

    config = Config(V8_TYPE_REFIT="1")
    events = (refit_charts(report, report_format="standard")
              if config.enable_type_refit else [])
    emitted = [c["type"] for sec in report.sections for c in (sec.charts or [])]
    append_run("event", "deep", emitted, refit=refit_records(events), path=log)

    assert emitted == ["histogram", "treemap"]
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert record["types"] == ["histogram", "treemap"]
    assert record["refit"] == [
        {"from": "bar", "to": "histogram", "rule": "R1"},
        {"from": "donut", "to": "treemap", "rule": "R2"},
    ]
    assert analyze(path=log)["refit_distribution"] == {"R1": 1, "R2": 1}


def test_orchestrator_sequence_with_flag_off_is_byte_equal(tmp_path: Path) -> None:
    """flag OFF 면 차트도 로그도 v8.6.3 과 동일하다."""
    from src.config import Config
    from src.models import ComposedReport, ComposedSection
    from src.visual.usage_log import append_run

    chart = _bins(["1~2천", "2~3천", "3~5천", "5~7천"], [9, 15, 22, 14])
    report = ComposedReport(headline="H", deck="D", sections=[
        ComposedSection(heading="A", prose="p", charts=[chart])])
    log = tmp_path / "usage.jsonl"

    config = Config(V8_TYPE_REFIT="0")
    events = (refit_charts(report, report_format="standard")
              if config.enable_type_refit else [])
    emitted = [c["type"] for sec in report.sections for c in (sec.charts or [])]
    append_run("event", "deep", emitted, refit=refit_records(events), path=log)

    assert events == [] and emitted == ["bar"], "flag OFF 면 type 이 안 바뀐다"
    assert "refit" not in json.loads(log.read_text(encoding="utf-8").splitlines()[0])


def test_config_flag_defaults_on_and_can_be_disabled() -> None:
    from src.config import Config

    assert Config().enable_type_refit is True
    assert Config(V8_TYPE_REFIT="0").enable_type_refit is False


# ─── patch_report --refit · CLI ─────────────────────────────────────────

def test_patch_report_exposes_refit_flag() -> None:
    src = (_REPO_ROOT / "scripts" / "patch_report.py").read_text(encoding="utf-8")
    assert '"--refit"' in src
    assert "from src.visual.type_fit import refit_charts" in src
    assert "refit_applied" in src and "args.rerender_only or strip_arc_applied or refit_applied" in src, (
        "표현 변경이므로 render_revision(소수부) +1 분기에 합류해야 한다"
    )


def test_scan_reports_counts_rule_hits(tmp_path: Path) -> None:
    """CLI `--scan` 이 발행본 JSON 을 훑어 규칙별 적중 수를 센다 (읽기 전용)."""
    doc = {"request": {"report_format": "standard"}, "composed_report": {"sections": [
        {"heading": "a", "prose": "p", "charts": [
            _bins(["1~2천", "2~3천", "3~5천", "5~7천"], [9, 15, 22, 14]),
            _donut(_TWO_LAYER),
            {"type": "line", "title": "추세", "data": [{"x": "2026-03-01", "y": 1}]},
        ]}]}}
    (tmp_path / "analysis_20260901_120000_aaaa.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    hits, where = scan_reports(tmp_path)
    assert hits == {"R1": 1, "R2": 1}
    assert where["R1"] == ["20260901_120000_aaaa"]
    # 파일을 건드리지 않았는지 (읽기 전용)
    assert json.loads((tmp_path / "analysis_20260901_120000_aaaa.json")
                      .read_text(encoding="utf-8")) == doc
