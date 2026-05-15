"""v5.2.0 — ComposedSection._drop_invalid_charts 회귀 테스트.

chart_gate 의 production 진입점. composer LLM 출력의 차트 dict 들이
src/visual/schemas.py 의 type 별 가드를 *실제로* 통과/탈락하는지 검증.
이 validator 가 디폴트 ON 이므로 운영 영향 큼.

검증 원칙:
- 합법 차트는 절대 안 건드림
- 위반 차트만 drop (warning log)
- 보고서 자체는 절대 reject 안 됨 (composer 토큰 비용 보호)
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.models import ComposedSection


def _section(charts: list[dict]) -> ComposedSection:
    return ComposedSection(
        heading="테스트 섹션",
        prose="본문 내용",
        charts=charts,
    )


# ─── 합법 차트는 보존 ─────────────────────────────────────────────


def test_keeps_valid_bar_chart() -> None:
    s = _section([
        {"type": "bar", "title": "OK", "data": [
            {"label": "A", "value": 10},
            {"label": "B", "value": 20},
        ]},
    ])
    assert len(s.charts) == 1
    assert s.charts[0]["title"] == "OK"


def test_keeps_valid_line_chart() -> None:
    s = _section([
        {"type": "line", "title": "추이", "data": [
            {"x": "2026-05-13", "y": 7900},
            {"x": "2026-05-15", "y": 8002.66},
        ]},
    ])
    assert len(s.charts) == 1


def test_keeps_valid_candle() -> None:
    s = _section([
        {"type": "candle", "title": "삼성전자", "data": [
            {"date": "2026-05-13", "open": 92000, "high": 93500, "low": 91500, "close": 93000},
            {"date": "2026-05-14", "open": 93000, "high": 94200, "low": 92800, "close": 94000},
        ]},
    ])
    assert len(s.charts) == 1


def test_keeps_valid_donut_3_segments() -> None:
    s = _section([
        {"type": "donut", "title": "구성", "data": [
            {"label": "반도체", "value": 16.8},
            {"label": "금융", "value": 1.2},
            {"label": "기타", "value": 2.2},
        ]},
    ])
    assert len(s.charts) == 1


# ─── 위반 차트는 drop ─────────────────────────────────────────────


def test_drops_2_segment_donut() -> None:
    """CHART-AP-16 의 실제 회귀 케이스 — composer 가 다시 emit 해도 자동 drop."""
    s = _section([
        {"type": "donut", "title": "구성", "data": [
            {"label": "반도체", "value": 16.8},
            {"label": "비반도체", "value": 3.4},
        ]},
    ])
    assert s.charts == []


def test_drops_zero_duration_gantt() -> None:
    """CHART-AP-15 — 모든 row 가 zero-duration 인 gantt."""
    s = _section([
        {"type": "gantt", "title": "타임라인", "data": [
            {"label": "A", "start": "2026-05-11", "end": "2026-05-11"},
            {"label": "B", "start": "2026-05-12", "end": "2026-05-12"},
            {"label": "C", "start": "2026-05-15", "end": "2026-05-15"},
        ]},
    ])
    assert s.charts == []


def test_drops_inverted_ohlc_candle() -> None:
    """OHLC 순서 위반 — low > high 등."""
    s = _section([
        {"type": "candle", "title": "삼전", "data": [
            {"date": "2026-05-14", "open": 100, "high": 110, "low": 95, "close": 105},
            {"date": "2026-05-15", "open": 100, "high": 90, "low": 95, "close": 105},
        ]},
    ])
    assert s.charts == []


def test_drops_negative_bar_value_passes() -> None:
    """음수 bar 는 BarChartGuard 가 finite 만 보고 음수 통과 — 보존됨."""
    s = _section([
        {"type": "bar", "title": "순매도", "data": [
            {"label": "A", "value": -100},
            {"label": "B", "value": 50},
        ]},
    ])
    assert len(s.charts) == 1


# ─── 혼합 — 합법 + 위반 mix ────────────────────────────────────────


def test_drops_only_invalid_keeps_rest() -> None:
    """3개 차트 중 1개만 invalid → 2개 보존."""
    s = _section([
        {"type": "bar", "title": "OK1", "data": [
            {"label": "A", "value": 10},
        ]},
        {"type": "donut", "title": "BAD", "data": [  # AP-16
            {"label": "X", "value": 50},
            {"label": "Y", "value": 50},
        ]},
        {"type": "line", "title": "OK2", "data": [
            {"x": "2026-05-13", "y": 100},
            {"x": "2026-05-15", "y": 110},
        ]},
    ])
    assert len(s.charts) == 2
    titles = [c["title"] for c in s.charts]
    assert "OK1" in titles and "OK2" in titles
    assert "BAD" not in titles


# ─── Edge cases — section 생성 자체는 절대 fail 하면 안 됨 ──────────


def test_empty_charts_passes() -> None:
    s = ComposedSection(heading="제목", prose="본문", charts=[])
    assert s.charts == []


def test_missing_type_preserves_chart() -> None:
    """type 누락 dict 는 downstream 호환 위해 보존."""
    s = _section([
        {"title": "type 없음", "data": [{"label": "A", "value": 1}]},
    ])
    assert len(s.charts) == 1


def test_non_dict_in_charts_rejected_by_field_validation() -> None:
    """charts: list[dict] — Pydantic field 가 비-dict 를 reject. 정상 동작 (composer LLM 은 dict 만 emit)."""
    with pytest.raises(Exception):
        ComposedSection(
            heading="제목", prose="본문",
            charts=["잘못된 항목"],  # type: ignore[list-item]
        )


def test_unknown_type_preserved() -> None:
    """guard_for_type 이 None 반환 → validate_chart_data 가 ok=True 반환 → 보존."""
    s = _section([
        {"type": "treemap", "title": "신규 type", "data": [
            {"name": "A", "value": 1},
        ]},
    ])
    assert len(s.charts) == 1


def test_validator_runs_only_once_not_on_each_attr_access() -> None:
    """model_validator(mode='after') 는 생성 시 1회만 — 이후 self.charts 접근에 영향 X."""
    s = _section([
        {"type": "donut", "title": "BAD", "data": [
            {"label": "X", "value": 50},
            {"label": "Y", "value": 50},
        ]},
    ])
    # 처음 접근 시 이미 drop 됨
    assert s.charts == []
    # 다시 접근해도 동일
    assert s.charts == []


# ─── _select_market_period (mode-aware) ───────────────────────────


def test_market_period_default_3m() -> None:
    from src.orchestrator import _select_market_period
    from src.models import AnalysisRequest, ContextAnalysis
    req = AnalysisRequest(event_description="코스피 8000 돌파")
    ctx = ContextAnalysis(event_name="코스피 8000 돌파", summary="사상 첫 돌파")
    assert _select_market_period(req, ctx) == "3M"


def test_market_period_daily_briefing() -> None:
    from src.orchestrator import _select_market_period
    from src.models import AnalysisRequest, ContextAnalysis
    req = AnalysisRequest(event_description="간밤 미국 증시 마감 분석")
    ctx = ContextAnalysis(event_name="간밤 산업 동향", summary="어제 발표")
    assert _select_market_period(req, ctx) == "1M"


def test_market_period_historical() -> None:
    from src.orchestrator import _select_market_period
    from src.models import AnalysisRequest, ContextAnalysis
    req = AnalysisRequest(event_description="IMF 외환위기 이후 처음")
    ctx = ContextAnalysis(event_name="역사적 회고", summary="10년 만에")
    assert _select_market_period(req, ctx) == "3Y"


def test_market_period_historical_keyword_priority() -> None:
    """historical 키워드가 daily 보다 우선 (먼저 매치)."""
    from src.orchestrator import _select_market_period
    from src.models import AnalysisRequest, ContextAnalysis
    req = AnalysisRequest(event_description="간밤 IMF 비교")
    ctx = ContextAnalysis()
    assert _select_market_period(req, ctx) == "3Y"
