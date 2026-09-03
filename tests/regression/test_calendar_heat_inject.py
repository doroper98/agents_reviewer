"""calendar_heat 시장 시계열 자동 주입 회귀 가드 (v8.6.3).

기능 SSOT: [docs/CHART_REDESIGN_V8_6_PLAN.md](../../docs/CHART_REDESIGN_V8_6_PLAN.md) §5.4.
구현: ``src/orchestrator.py`` 의 ``_daily_move_values`` / ``_ensure_calendar_heat`` /
``_find_full_ts_card`` + ``src/config.py`` 의 ``enable_calendar_heat_inject``.

주입 규칙(플랜 §5.4 ①~⑦)이 회귀하면 여기서 잡힌다:
① 주제 우선 instrument 1개의 풀 카드 *바로 뒤* 같은 섹션
② 값 = ``|close_t / close_{t-1} - 1| × 100``, 60행 미만이면 no-op
③ chart dict 계약 (title / subtitle / unit_line / source / metric_label / data.values)
④ composer 가 이미 calendar_heat 를 emit 했으면 no-op
⑤ ``ChartCountLimits`` 초과면 no-op
⑥ 르포는 호출 자체가 안 일어난다 (시장차트 자동 주입 블록 밖)
⑦ ``ENABLE_CALENDAR_HEAT_INJECT=0`` 이면 호출 자체가 안 일어난다 (byte-equal)
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from src.orchestrator import (
    _daily_move_values,
    _ensure_calendar_heat,
)
from src.visual.schemas import validate_chart_data


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ORCH = _REPO_ROOT / "src" / "orchestrator.py"


# ─── fixture helpers ────────────────────────────────────────────────────

def _series(n: int, *, instrument: str = "코스피") -> dict:
    """등락이 있는 결정적 일봉 series (거래일 가정 — 주말도 그냥 이어 붙인다)."""
    d0 = date(2026, 3, 2)
    rows = []
    close = 2700.0
    for i in range(n):
        close = round(close * (1 + ((i % 7) - 3) * 0.004), 2)
        rows.append({
            "date": (d0 + timedelta(days=i)).isoformat(),
            "open": close, "high": close, "low": close, "close": close,
        })
    return {
        "instrument": instrument, "source": "KRX", "code": "1001",
        "chart_type": "line", "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"], "data": rows,
    }


def _composed(charts: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(sections=[SimpleNamespace(charts=list(charts))])


def _context(series_list: list[dict], *, event_name: str = "코스피 급변동") -> SimpleNamespace:
    return SimpleNamespace(
        time_series=list(series_list), event_name=event_name, summary="",
    )


def _full_card(instrument: str = "코스피") -> dict:
    return {"type": "line", "title": f"{instrument} 추이 (KRX)", "data": [{"x": "2026-03-02", "y": 2700}]}


# ─── ① 정상 주입 ────────────────────────────────────────────────────────

def test_injects_calendar_heat_right_after_topic_full_card() -> None:
    """주제 종목 풀 카드 바로 뒤에 1개. 계약대로 채워지고 가드도 통과한다."""
    composed = _composed([_full_card(), {"type": "bar", "title": "업종별", "data": []}])
    _ensure_calendar_heat(composed, _context([_series(70)]), mode="deep")

    charts = composed.sections[0].charts
    assert len(charts) == 3, "정확히 1개만 주입되어야 한다"
    assert charts[0]["type"] == "line" and charts[2]["type"] == "bar", (
        "풀 카드 *바로 뒤* 삽입 — 앞뒤 차트 순서가 밀리면 안 된다"
    )
    cal = charts[1]
    assert cal["type"] == "calendar_heat"
    assert cal["title"] == "코스피 일별 변동 강도"
    assert cal["subtitle"] == "거래일만 표시 · 주말·휴장일은 속빈 점"
    assert cal["unit_line"] == "단위: |일간 등락률| %"
    assert cal["metric_label"] == "등락 폭"
    assert "KRX" in cal["source"]
    assert cal["data"]["metric_label"] == "등락 폭"
    assert len(cal["data"]["values"]) == 69, "첫 봉은 기준일 — 등락률이 없다"
    ok, reason = validate_chart_data("calendar_heat", cal["data"])
    assert ok, f"주입한 payload 가 가드를 통과해야 한다: {reason}"


def test_topic_priority_picks_headline_instrument() -> None:
    """제목에 등장한 종목이 우선 (``_topic_priority_key`` 와 같은 순서)."""
    composed = _composed([_full_card("삼성전자"), _full_card("코스피")])
    context = _context([_series(70, instrument="삼성전자"), _series(70)],
                       event_name="코스피 급변동")
    _ensure_calendar_heat(composed, context, mode="deep")

    charts = composed.sections[0].charts
    cal = [c for c in charts if c["type"] == "calendar_heat"]
    assert len(cal) == 1
    assert cal[0]["title"] == "코스피 일별 변동 강도"
    assert charts.index(cal[0]) == 2, "'코스피' 풀 카드(index 1) 바로 뒤"


# ─── ② 60행 미만 no-op ──────────────────────────────────────────────────

def test_no_op_when_series_shorter_than_60_rows() -> None:
    """59개 값(60행)이면 격자가 서지 않는다 — 가드 하한과 같은 임계."""
    composed = _composed([_full_card()])
    _ensure_calendar_heat(composed, _context([_series(40)]), mode="deep")
    assert [c["type"] for c in composed.sections[0].charts] == ["line"]

    composed = _composed([_full_card()])
    _ensure_calendar_heat(composed, _context([_series(60)]), mode="deep")
    assert [c["type"] for c in composed.sections[0].charts] == ["line"], (
        "60행 = 값 59개 — 하한 미달이므로 주입 금지"
    )

    composed = _composed([_full_card()])
    _ensure_calendar_heat(composed, _context([_series(61)]), mode="deep")
    assert [c["type"] for c in composed.sections[0].charts] == ["line", "calendar_heat"]


def test_no_op_when_no_full_card_to_attach_to() -> None:
    """달력은 풀 카드에 붙는 보조 시각물 — compact strip 만 있으면 붙일 자리가 없다."""
    composed = _composed([
        {"type": "line", "role": "compact", "instrument": "코스피", "data": []},
    ])
    _ensure_calendar_heat(composed, _context([_series(70)]), mode="deep")
    assert len(composed.sections[0].charts) == 1


# ─── ④ 중복 no-op ───────────────────────────────────────────────────────

def test_no_op_when_composer_already_emitted_calendar_heat() -> None:
    composed = _composed([
        _full_card(),
        {"type": "calendar_heat", "title": "공습 횟수", "data": {"values": []}},
    ])
    _ensure_calendar_heat(composed, _context([_series(70)]), mode="deep")
    assert len(composed.sections[0].charts) == 2, "composer emit 이 있으면 손대지 않는다"


# ─── ⑤ 차트 상한 초과 no-op ─────────────────────────────────────────────

def test_no_op_when_chart_count_limit_exceeded() -> None:
    """``ChartCountLimits`` (standard 4 / deep 5) 와 같은 집계."""
    from src.visual.deterministic_gate import ChartCountLimits

    assert (ChartCountLimits.standard, ChartCountLimits.deep) == (4, 5)

    charts = [_full_card()] + [
        {"type": "bar", "title": f"보조 {i}", "data": []} for i in range(3)
    ]
    composed = _composed(charts)             # 총 4개 = standard 상한
    _ensure_calendar_heat(composed, _context([_series(70)]), mode="standard")
    assert len(composed.sections[0].charts) == 4, "standard 4 + 1 > 4 → 주입 생략"

    composed = _composed(charts)             # 같은 4개를 deep 으로
    _ensure_calendar_heat(composed, _context([_series(70)]), mode="deep")
    assert len(composed.sections[0].charts) == 5, "deep 은 5까지 허용"


# ─── 값 계산 정합 (수기 검산) ───────────────────────────────────────────

def test_daily_move_values_match_manual_arithmetic() -> None:
    """|close_t / close_{t-1} - 1| × 100 — 3행 수기 검산."""
    series = {"data": [
        {"date": "2026-03-02", "close": 100.0},
        {"date": "2026-03-03", "close": 101.0},   # +1.00%
        {"date": "2026-03-04", "close": 99.0},    # -1.980198...%
        {"date": "2026-03-05", "close": 99.0},    # 0%
    ]}
    assert _daily_move_values(series) == [
        {"date": "2026-03-03", "value": 1.0},
        {"date": "2026-03-04", "value": 1.98},
        {"date": "2026-03-05", "value": 0.0},
    ]


def test_daily_move_values_skip_nan_bars_and_duplicate_dates() -> None:
    """CHART-AP-29 — NaN 봉은 건너뛰고 남은 인접 두 봉으로 잇는다. 날짜 중복 금지."""
    series = {"data": [
        {"date": "2026-03-02", "close": 100.0},
        {"date": "2026-03-03", "close": None},        # NaN 봉 — 건너뜀
        {"date": "2026-03-04", "close": float("nan")},
        {"date": "2026-03-05", "close": 101.0},       # 100 대비 +1.00%
        {"date": "2026-03-05", "close": 105.0},       # 같은 날짜 재등장 — 버림
    ]}
    assert _daily_move_values(series) == [{"date": "2026-03-05", "value": 1.0}]


def test_daily_move_values_fall_back_to_value_then_y() -> None:
    """close 가 없으면 value → y 순 (market_fetcher 외 경로 호환)."""
    assert _daily_move_values({"data": [
        {"date": "2026-03-02", "value": 50.0},
        {"date": "2026-03-03", "value": 55.0},
    ]}) == [{"date": "2026-03-03", "value": 10.0}]
    assert _daily_move_values({"data": [
        {"date": "2026-03-02", "y": 50.0},
        {"date": "2026-03-03", "y": 45.0},
    ]}) == [{"date": "2026-03-03", "value": 10.0}]


def test_daily_move_values_clamped_to_renderer_window() -> None:
    """400행 가드 상한 안으로 — 렌더러 클램프(371)와 같은 창."""
    values = _daily_move_values(_series(800))
    assert len(values) == 371
    ok, reason = validate_chart_data("calendar_heat", {"values": values})
    assert ok, reason


# ─── ⑥ 르포 no-op · ⑦ flag OFF byte-equal (호출부 배선) ─────────────────

def _call_site_block() -> str:
    """``if request.report_format != "reportage":`` 블록 본문만 잘라 돌려준다."""
    src = _ORCH.read_text(encoding="utf-8")
    m = re.search(r'^(\s*)if request\.report_format != "reportage":\s*$', src, re.M)
    assert m, "시장차트 자동 주입 블록을 못 찾음 — 호출부 구조가 바뀌었다"
    indent = len(m.group(1))
    lines = src[m.end():].split("\n")
    body: list[str] = []
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
    return "\n".join(body)


def test_reportage_skips_calendar_heat_injection() -> None:
    """르포는 시장차트 자동 주입 자체를 건너뛴다 (v8.0.0 규칙 계승)."""
    block = _call_site_block()
    assert "_ensure_calendar_heat(" in block, (
        "_ensure_calendar_heat 호출이 report_format != 'reportage' 블록 밖으로 "
        "새면 르포에도 시장 달력이 박힌다"
    )
    src = _ORCH.read_text(encoding="utf-8")
    assert src.count("_ensure_calendar_heat(") == 2, (
        "정의 1 + 호출 1 이어야 한다 — 다른 경로에서 또 부르면 중복 주입 위험"
    )


def test_flag_off_is_byte_equal_no_call() -> None:
    """``ENABLE_CALENDAR_HEAT_INJECT=0`` 이면 호출 자체를 안 한다 → v8.6.2 와 동일."""
    from src.config import Config

    assert Config().enable_calendar_heat_inject is True, "기본 ON"
    assert Config(ENABLE_CALENDAR_HEAT_INJECT="0").enable_calendar_heat_inject is False

    block = _call_site_block()
    guard = 'if getattr(self.config, "enable_calendar_heat_inject", True):'
    assert guard in block, "flag 게이트 누락 — OFF 로 되돌릴 수 없다"
    assert block.index(guard) < block.index("_ensure_calendar_heat("), (
        "게이트가 호출보다 앞서야 flag OFF 가 byte-equal"
    )
