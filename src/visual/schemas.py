"""V5 Phase 6 Gate A — 타입별 Schema 가드 (Plan §13.2).

Vega-Lite spec 의 *형식* 검증은 src/visual/vega_adapter.py:validate_vega_spec
이 처리. 본 모듈은 *데이터 의미* 가드 — type 별 Pydantic 모델로 antipattern
의 *원천 차단*.

[Plan §13.2 의 가드 매핑]
    AP-3   (음수/0/극단값)        — _common_finite_validator
    AP-7   (빈 데이터 emit)        — *Guard.data Field(min_length=1)
    AP-12  (bubble 스케일 고정)    — BubbleChartGuard
    AP-13  (gantt 시간축 누락)     — GanttGuard
    AP-1   (group/category 분리)  — NetworkGuard 의 link 참조 검증

본 모듈의 가드는 *throw* 가 아니라 ``ValidationError`` (Pydantic) 로 fail.
Phase 6 chart_gate 가 try/except 로 처리해 Gate D fallback 으로 넘김.

Public API:
    from src.visual.schemas import (
        BubbleChartGuard, GanttGuard, NetworkGuard,
        BarChartGuard, LineChartGuard, HeatmapGuard,
        StackedBarGuard, DonutGuard, GANTT_TIME_PARSERS,
        guard_for_type,
    )
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─── 시간 파싱 (GanttGuard) ─────────────────────────────────────────────


_TIME_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%Y-%m",
    "%Y",
]

_NUMERIC_YEAR = re.compile(r"^-?\d{4}(?:\.\d+)?$")


def parse_time(value: Any) -> datetime | None:
    """GanttGuard 가 사용하는 시간 파싱.

    지원 형식: ISO 8601 / "YYYY-MM-DD" / "YYYY-MM" / "YYYY" / int year /
    float year. 실패 시 None — caller 가 ValueError 처리.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # 연도 단위 숫자 (예: 2026, 2026.5).
        if not math.isfinite(float(value)):
            return None
        year = int(value)
        if 1900 <= year <= 2100:
            return datetime(year, 1, 1)
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # numeric year string.
        if _NUMERIC_YEAR.match(s):
            try:
                year = int(float(s))
                if 1900 <= year <= 2100:
                    return datetime(year, 1, 1)
            except ValueError:
                pass
        for fmt in _TIME_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


GANTT_TIME_PARSERS = {
    "iso": "%Y-%m-%dT%H:%M:%S",
    "date": "%Y-%m-%d",
    "month": "%Y-%m",
    "year": "%Y",
}


# ─── Bubble (CHART-AP-12) ──────────────────────────────────────────────


class BubblePoint(BaseModel):
    x: float
    y: float
    size: float = 1.0
    label: str = ""
    group: str | None = None

    model_config = ConfigDict(extra="allow")


class BubbleChartGuard(BaseModel):
    """CHART-AP-12: bubble 스케일 자동 + finite 강제."""

    data: list[BubblePoint] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_finite_ranges(self) -> "BubbleChartGuard":
        xs = [p.x for p in self.data]
        ys = [p.y for p in self.data]
        sizes = [p.size for p in self.data]
        all_vals = xs + ys + sizes
        if not all(math.isfinite(v) for v in all_vals):
            raise ValueError(
                "CHART-AP-12 가드: bubble data 에 NaN/inf 포함"
            )
        # 범위가 매우 비대칭이면 의심 — 정규화 권장.
        if len(xs) >= 2:
            x_range = max(xs) - min(xs)
            y_range = max(ys) - min(ys)
            # 한 축이 0 이고 다른 축이 큰 경우 — 1차원 데이터.
            if x_range == 0 and y_range == 0:
                raise ValueError(
                    "CHART-AP-12 가드: bubble x/y 모두 동일값 (1점 차트)"
                )
        if any(s <= 0 for s in sizes):
            raise ValueError(
                "CHART-AP-12 가드: bubble size ≤ 0 (음수 또는 0)"
            )
        return self


# ─── Gantt (CHART-AP-13) ───────────────────────────────────────────────


class GanttRow(BaseModel):
    label: str
    start: Any                       # 시간 또는 숫자
    end: Any
    note: str = ""
    group: str | None = None

    model_config = ConfigDict(extra="allow")


class GanttGuard(BaseModel):
    """CHART-AP-13: gantt 시간축 + 행 라벨/note 충돌 차단."""

    rows: list[GanttRow] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_ranges(self) -> "GanttGuard":
        for r in self.rows:
            t_start = parse_time(r.start)
            t_end = parse_time(r.end)
            if t_start is None or t_end is None:
                raise ValueError(
                    f"CHART-AP-13 가드: {r.label!r} start/end 파싱 실패 "
                    f"(start={r.start!r}, end={r.end!r})"
                )
            if t_start > t_end:
                raise ValueError(
                    f"CHART-AP-13 가드: {r.label!r} start > end "
                    f"({r.start} > {r.end})"
                )
        # 중복 row label 도 시각 혼란 — 거절.
        labels = [r.label for r in self.rows]
        if len(set(labels)) != len(labels):
            duplicates = sorted({l for l in labels if labels.count(l) > 1})
            raise ValueError(
                f"CHART-AP-13 가드: gantt rows 의 중복 label — {duplicates}"
            )
        return self

    @model_validator(mode="after")
    def validate_durations(self) -> "GanttGuard":
        """CHART-AP-15: gantt 는 *기간* 차트. point-in-time 이벤트 모음이면 부적합.

        zero-duration ratio (start == end 인 row 비율) > 0.7 이면 거절.
        gantt 본질이 duration 시각화인데 모든 행이 점이면 막대 폭 ≈ 0px →
        라벨만 떠 있는 빈 차트로 보임. timeline_strip / line + event marker /
        본문 list 로 대체.
        """
        zero_count = 0
        for r in self.rows:
            t_start = parse_time(r.start)
            t_end = parse_time(r.end)
            if t_start is not None and t_end is not None:
                # parse_time 은 datetime 반환 — timedelta 의 total_seconds() 비교.
                # 일/월 단위 정밀도 차이 무시: 같은 날(또는 미만)이면 zero-duration.
                if abs((t_end - t_start).total_seconds()) < 86400:
                    zero_count += 1
        ratio = zero_count / len(self.rows)
        if ratio > 0.7:
            raise ValueError(
                f"CHART-AP-15 가드: gantt zero-duration ratio {ratio:.0%} > 70% "
                f"({zero_count}/{len(self.rows)} rows). gantt 는 *기간* 차트이므로 "
                "point-in-time 이벤트 모음에는 부적합. timeline_strip / "
                "line + event marker / 본문 list 로 대체할 것."
            )
        return self


# ─── Network (CHART-AP-7 + AP-1) ──────────────────────────────────────


class NetworkNode(BaseModel):
    id: str
    label: str = ""
    group: str | None = None
    weight: float = 1.0

    model_config = ConfigDict(extra="allow")


class NetworkLink(BaseModel):
    source: str
    target: str
    weight: float = 1.0
    label: str = ""

    model_config = ConfigDict(extra="allow")


class NetworkGuard(BaseModel):
    """CHART-AP-7 (빈 data) + CHART-AP-1 (group/category 분리) 가드."""

    nodes: list[NetworkNode] = Field(min_length=2)
    links: list[NetworkLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_link_refs(self) -> "NetworkGuard":
        node_ids = {n.id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("CHART-AP-7 가드: network node id 중복")
        for link in self.links:
            if link.source not in node_ids:
                raise ValueError(
                    f"CHART-AP-7/AP-1 가드: link source {link.source!r} 가 "
                    f"nodes 에 없음"
                )
            if link.target not in node_ids:
                raise ValueError(
                    f"CHART-AP-7/AP-1 가드: link target {link.target!r} 가 "
                    f"nodes 에 없음"
                )
            if not math.isfinite(link.weight):
                raise ValueError(
                    f"CHART-AP-3 가드: link weight 가 NaN/inf"
                )
        return self


# ─── Bar / Line / Stacked / Heatmap / Donut — 공통 finite 가드 ────────


class BarRow(BaseModel):
    label: str
    value: float
    group: str | None = None

    model_config = ConfigDict(extra="allow")


class BarChartGuard(BaseModel):
    """CHART-AP-3 + AP-7 기본 가드."""
    data: list[BarRow] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_finite(self) -> "BarChartGuard":
        if not all(math.isfinite(r.value) for r in self.data):
            raise ValueError("CHART-AP-3 가드: bar value 에 NaN/inf")
        return self


class LinePoint(BaseModel):
    x: Any
    y: float
    series: str | None = None

    model_config = ConfigDict(extra="allow")


class AreaPoint(LinePoint):
    """Area 차트는 line 과 동일 schema (gradient fill 만 다름)."""
    pass


class OHLCBar(BaseModel):
    """v5.2.0 — Candle 차트의 일간 OHLC."""

    date: Any
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    event: str | None = None

    model_config = ConfigDict(extra="allow")


class CandleChartGuard(BaseModel):
    """v5.2.0 — Candle 차트 가드.

    검증:
    - data ≥ 2 (1점 candle 은 의미 X)
    - OHLC 모두 finite, ≥0
    - low ≤ open ≤ high  /  low ≤ close ≤ high (intra-day 순서 일관성)
    """

    data: list[OHLCBar] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_ohlc_consistency(self) -> "CandleChartGuard":
        for i, b in enumerate(self.data):
            for fld_name, v in (("open", b.open), ("high", b.high),
                                ("low", b.low), ("close", b.close)):
                if not math.isfinite(v):
                    raise ValueError(
                        f"CHART-AP-3 가드: candle row {i} {fld_name} NaN/inf"
                    )
                if v < 0:
                    raise ValueError(
                        f"CHART-AP-3 가드: candle row {i} {fld_name} 음수 — {v}"
                    )
            if not (b.low <= b.open <= b.high):
                raise ValueError(
                    f"CHART-AP-3 가드: candle row {i} low≤open≤high 위반 "
                    f"({b.low}/{b.open}/{b.high})"
                )
            if not (b.low <= b.close <= b.high):
                raise ValueError(
                    f"CHART-AP-3 가드: candle row {i} low≤close≤high 위반 "
                    f"({b.low}/{b.close}/{b.high})"
                )
        return self


class AreaChartGuard(BaseModel):
    """v5.2.0 — Area 차트 가드 (line 과 동일 + finite)."""

    data: list[AreaPoint] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_finite(self) -> "AreaChartGuard":
        if not all(math.isfinite(p.y) for p in self.data):
            raise ValueError("CHART-AP-3 가드: area y 에 NaN/inf")
        return self


class LineChartGuard(BaseModel):
    data: list[LinePoint] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_finite(self) -> "LineChartGuard":
        if not all(math.isfinite(p.y) for p in self.data):
            raise ValueError("CHART-AP-3 가드: line y 에 NaN/inf")
        return self


class HeatmapCell(BaseModel):
    x: Any
    y: Any
    value: float

    model_config = ConfigDict(extra="allow")


class HeatmapGuard(BaseModel):
    data: list[HeatmapCell] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_finite(self) -> "HeatmapGuard":
        if not all(math.isfinite(c.value) for c in self.data):
            raise ValueError("CHART-AP-3 가드: heatmap value 에 NaN/inf")
        return self


class StackedBarGuard(BaseModel):
    """stacked: categories[] × series[*].values[]."""

    categories: list[str] = Field(min_length=1)
    series: list[dict] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_shape(self) -> "StackedBarGuard":
        n = len(self.categories)
        for s in self.series:
            if not isinstance(s, dict):
                raise ValueError("CHART-AP-1 가드: series 항목이 dict 가 아님")
            values = s.get("values") or []
            if len(values) != n:
                raise ValueError(
                    f"CHART-AP-1 가드: series {s.get('name')!r} 의 values 개수 "
                    f"({len(values)}) ≠ categories ({n})"
                )
            for v in values:
                if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                    raise ValueError(
                        f"CHART-AP-3 가드: stacked value 에 비-finite 값 — {v!r}"
                    )
        return self


class DonutSlice(BaseModel):
    label: str
    value: float

    model_config = ConfigDict(extra="allow")


class DonutGuard(BaseModel):
    # CHART-AP-16 가 ≥3 강제 — 여기선 비어있지 않게만 막고, 정확한 메시지는
    # validate_segment_count 에서 발생시킴 (field 레벨 "too_short" 가 AP 번호를 가림).
    data: list[DonutSlice] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_finite_positive(self) -> "DonutGuard":
        for s in self.data:
            if not math.isfinite(s.value):
                raise ValueError(f"CHART-AP-3 가드: donut value NaN/inf — {s.label}")
            if s.value < 0:
                raise ValueError(
                    f"CHART-AP-3 가드: donut value 음수 — {s.label} = {s.value}"
                )
        total = sum(s.value for s in self.data)
        if total <= 0:
            raise ValueError("CHART-AP-7 가드: donut 총합 0 — 차트 의미 없음")
        return self

    @model_validator(mode="after")
    def validate_segment_count(self) -> "DonutGuard":
        """CHART-AP-16: 도넛 segment < 3 = 정보 손실 + subtitle 잉여.

        2 segment 도넛은 (a) "기타" 같은 잡탕 segment 가 강제로 생기거나,
        (b) subtitle 의 % 표현이 같은 정보를 이미 전달함. 둘 다 비율 카드 또는
        본문 한 문장으로 대체. 1 segment 는 도넛 자체가 의미 없음.
        """
        if len(self.data) < 3:
            raise ValueError(
                f"CHART-AP-16 가드: donut segment {len(self.data)} 개 — 3 미만은 "
                "정보 손실 (잡탕 'others' segment) + subtitle 잉여. "
                "비율 카드 또는 본문 한 문장으로 대체할 것."
            )
        return self


# ─── v5.2.14 — production 가드 보강 3종 (dual_line / forecast / choropleth) ─


class XYSeriesPoint(BaseModel):
    x: float | str | int
    y: float

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_y_finite(self) -> "XYSeriesPoint":
        if not math.isfinite(self.y):
            raise ValueError(f"CHART-AP-3 가드: y NaN/inf — x={self.x}")
        return self


class DualLineAxis(BaseModel):
    label: str
    unit: str = ""
    series: list[XYSeriesPoint] = Field(min_length=2)

    model_config = ConfigDict(extra="allow")


class DualLineGuard(BaseModel):
    """dual_line: 두 시리즈의 동조/괴리 비교.

    composer SYSTEM_PROMPT: left/right 각각 {label, unit, series: [{x, y}]}.
    각 series ≥2 포인트, ≤200 포인트.
    """
    left: DualLineAxis
    right: DualLineAxis

    @model_validator(mode="after")
    def validate_size(self) -> "DualLineGuard":
        for side, axis in (("left", self.left), ("right", self.right)):
            if len(axis.series) > 200:
                raise ValueError(
                    f"CHART-AP-7 가드: dual_line {side}.series {len(axis.series)} "
                    f"포인트 — 200 초과는 line 가시성 손상"
                )
        return self


class ForecastActual(BaseModel):
    x: float | str | int
    y: float

    model_config = ConfigDict(extra="allow")


class ForecastFuture(BaseModel):
    x: float | str | int
    mid: float
    low: float
    high: float

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_band(self) -> "ForecastFuture":
        for fld_name in ("mid", "low", "high"):
            v = getattr(self, fld_name)
            if not math.isfinite(v):
                raise ValueError(
                    f"CHART-AP-3 가드: forecast {fld_name} NaN/inf — x={self.x}"
                )
        if not (self.low <= self.mid <= self.high):
            raise ValueError(
                f"CHART-AP-3 가드: forecast x={self.x} low≤mid≤high 위반 "
                f"(low={self.low}, mid={self.mid}, high={self.high})"
            )
        return self


class ForecastGuard(BaseModel):
    """forecast: 실측 + 예측 + 신뢰구간.

    composer SYSTEM_PROMPT: {actual: [{x, y}], forecast: [{x, mid, low, high}], fork_at}.
    actual ≥2, forecast ≥1, low ≤ mid ≤ high.
    """
    actual: list[ForecastActual] = Field(min_length=2)
    forecast: list[ForecastFuture] = Field(min_length=1)
    fork_at: str | float | int | None = None

    model_config = ConfigDict(extra="allow")


# ISO-3166-1 alpha-2 country code (느슨한 — 2 대문자만 검증, 사전 매칭 X)
_ISO_ALPHA2 = re.compile(r"^[A-Z]{2}$")


class ChoroplethRow(BaseModel):
    country_code: str
    value: float

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_row(self) -> "ChoroplethRow":
        if not _ISO_ALPHA2.match(self.country_code):
            raise ValueError(
                f"CHART-AP-3 가드: choropleth country_code "
                f"'{self.country_code}' — ISO-3166-1 alpha-2 (2 대문자) 필요"
            )
        if not math.isfinite(self.value):
            raise ValueError(
                f"CHART-AP-3 가드: choropleth value NaN/inf — {self.country_code}"
            )
        return self


class ChoroplethGuard(BaseModel):
    """choropleth: 국가별 색농도 지도.

    composer SYSTEM_PROMPT: [{country_code:"KR", value:12.4}, ...].
    ≥3 국가 (그 미만은 bar 가 적절).
    """
    data: list[ChoroplethRow] = Field(min_length=3)


# ─── v5.2.14 — 신규 7종 (FT/Economist 스타일) ─────────────────────────────


class ScatterPoint(BaseModel):
    label: str = Field(min_length=1)
    x: float
    y: float

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_finite(self) -> "ScatterPoint":
        for fld in ("x", "y"):
            v = getattr(self, fld)
            if not math.isfinite(v):
                raise ValueError(f"CHART-AP-3 가드: scatter {fld} NaN/inf — {self.label}")
        return self


class ScatterGuard(BaseModel):
    """scatter: 라벨 산점도 (FT 좌측 스타일).

    [{label, x, y}]. ≥3 포인트 (그 미만은 본문 한 줄로 충분).
    bubble 과 구분: bubble 은 size 인코딩 있음, scatter 는 균일.
    """
    data: list[ScatterPoint] = Field(min_length=3)


class StackedAreaSeries(BaseModel):
    name: str = Field(min_length=1)
    values: list[XYSeriesPoint] = Field(min_length=5)

    model_config = ConfigDict(extra="allow")


class StackedAreaGuard(BaseModel):
    """stacked_area: 시계열 누적 영역 (FT 우측 스타일).

    {series: [{name, values: [{x, y}]}]}.
    ≤5 시리즈, 각 시리즈 ≥5 포인트, 모든 시리즈 x 축 정합.
    """
    series: list[StackedAreaSeries] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_x_alignment(self) -> "StackedAreaGuard":
        if not self.series:
            return self
        xs_ref = [p.x for p in self.series[0].values]
        for s in self.series[1:]:
            xs = [p.x for p in s.values]
            if xs != xs_ref:
                raise ValueError(
                    f"CHART-AP-3 가드: stacked_area 시리즈 '{s.name}' 의 x 축이 "
                    f"기준 시리즈와 불일치 — 모든 시리즈가 동일한 x 격자 필요"
                )
        return self


class LollipopRow(BaseModel):
    label: str = Field(min_length=1)
    value: float

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_value(self) -> "LollipopRow":
        if not math.isfinite(self.value):
            raise ValueError(f"CHART-AP-3 가드: lollipop value NaN/inf — {self.label}")
        return self


class LollipopGuard(BaseModel):
    """lollipop: bar 의 우아한 대안.

    [{label, value}]. 8-15 항목 (그 미만이면 bar, 초과면 본문 + heatmap).
    """
    data: list[LollipopRow] = Field(min_length=8, max_length=15)


class SlopeItem(BaseModel):
    label: str = Field(min_length=1)
    a: float
    b: float

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_finite(self) -> "SlopeItem":
        for fld in ("a", "b"):
            v = getattr(self, fld)
            if not math.isfinite(v):
                raise ValueError(f"CHART-AP-3 가드: slope {fld} NaN/inf — {self.label}")
        return self


class SlopeGuard(BaseModel):
    """slope (slopegraph): 2 시점 비교, 순위 변화.

    {left_label, right_label, items: [{label, a, b}]}. 3-10 항목.
    """
    left_label: str = Field(min_length=1)
    right_label: str = Field(min_length=1)
    items: list[SlopeItem] = Field(min_length=3, max_length=10)


class SmallMultiplesPanel(BaseModel):
    label: str = Field(min_length=1)
    series: list[XYSeriesPoint] = Field(min_length=5)

    model_config = ConfigDict(extra="allow")


class SmallMultiplesGuard(BaseModel):
    """small_multiples: 같은 차트 4-9면 그리드.

    {panels: [{label, series: [{x, y}]}]}.
    """
    panels: list[SmallMultiplesPanel] = Field(min_length=4, max_length=9)


class WaterfallRow(BaseModel):
    label: str = Field(min_length=1)
    value: float
    type: str  # 'total' | 'pos' | 'neg'

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_row(self) -> "WaterfallRow":
        if not math.isfinite(self.value):
            raise ValueError(f"CHART-AP-3 가드: waterfall value NaN/inf — {self.label}")
        if self.type not in ("total", "pos", "neg"):
            raise ValueError(
                f"CHART-AP-3 가드: waterfall type '{self.type}' — "
                f"'total'|'pos'|'neg' 중 하나여야 함"
            )
        return self


class WaterfallGuard(BaseModel):
    """waterfall: 증감 누적 분해 (P&L 스타일).

    [{label, value, type}]. 첫·끝 row 는 반드시 type='total'.
    중간 row 는 pos/neg. ≥3 항목.
    """
    data: list[WaterfallRow] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_endpoints(self) -> "WaterfallGuard":
        if self.data[0].type != "total":
            raise ValueError(
                "CHART-AP-3 가드: waterfall 첫 row 는 type='total' 이어야 함 "
                "(시작값)"
            )
        if self.data[-1].type != "total":
            raise ValueError(
                "CHART-AP-3 가드: waterfall 마지막 row 는 type='total' 이어야 함 "
                "(종료값)"
            )
        return self


class RangeBarRow(BaseModel):
    label: str = Field(min_length=1)
    low: float
    high: float

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_row(self) -> "RangeBarRow":
        for fld in ("low", "high"):
            v = getattr(self, fld)
            if not math.isfinite(v):
                raise ValueError(f"CHART-AP-3 가드: range_bar {fld} NaN/inf — {self.label}")
        if self.low >= self.high:
            raise ValueError(
                f"CHART-AP-3 가드: range_bar '{self.label}' low >= high "
                f"(low={self.low}, high={self.high}) — 의미 있는 갭 필요"
            )
        return self


class RangeBarGuard(BaseModel):
    """range_bar (dumbbell): 두 값 사이 갭.

    [{label, low, high}]. low < high, 3-15 항목.
    """
    data: list[RangeBarRow] = Field(min_length=3, max_length=15)


# ─── v5.3.0 — Sankey (재무 분해 / 자본 배분) ─────────────────────────────


class SankeyNode(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    accent: bool = False
    value_label: str | None = None  # 옵션 — 노드 옆에 표시될 caption (예: "$117B")

    model_config = ConfigDict(extra="allow")


class SankeyLink(BaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    value: float
    negative: bool = False  # 적자 / 손실 flow (사용자 이미지의 빨간 흐름)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_value(self) -> "SankeyLink":
        if not math.isfinite(self.value):
            raise ValueError(
                f"CHART-AP-3 가드: sankey link {self.source}→{self.target} "
                f"value NaN/inf"
            )
        if self.source == self.target:
            raise ValueError(
                f"CHART-AP-3 가드: sankey self-loop 금지 "
                f"({self.source}→{self.target})"
            )
        return self


class SankeyGuard(BaseModel):
    """sankey: 다단계 흐름 분해 (재무제표 / 자본 배분 / 수익성 분석).

    {nodes: [{id, label, accent?, value_label?}],
     links: [{source, target, value, negative?}]}.

    가드:
    - 노드 2-12 (그 미만은 본문 한 문장, 초과는 시각 피로 — 본 가드는 12 강제)
    - 링크 ≥1
    - 모든 link 의 source/target 이 nodes.id 안에 존재 (참조 무결성)
    - self-loop 금지
    - DAG 구조 (순환 금지)

    재무 분해 예시:
    - 손익계산서: 매출 → COGS / 판관비 / R&D / 영업이익
    - 세그먼트: 총매출 → 사업부 → 지역 → 마진
    - 자본 배분: 영업CF → 배당 / 자사주 / CAPEX / M&A
    """
    nodes: list[SankeyNode] = Field(min_length=2, max_length=12)
    links: list[SankeyLink] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_link_references(self) -> "SankeyGuard":
        node_ids = {n.id for n in self.nodes}
        for l in self.links:
            if l.source not in node_ids:
                raise ValueError(
                    f"CHART-AP-1 가드: sankey link source '{l.source}' 가 "
                    f"nodes 에 미존재"
                )
            if l.target not in node_ids:
                raise ValueError(
                    f"CHART-AP-1 가드: sankey link target '{l.target}' 가 "
                    f"nodes 에 미존재"
                )
        # 순환 감지 — BFS 로 토폴로지 정렬 시도, 모든 노드 처리 못 하면 순환 존재
        from collections import defaultdict, deque
        in_deg: dict[str, int] = defaultdict(int)
        adj: dict[str, list[str]] = defaultdict(list)
        for l in self.links:
            adj[l.source].append(l.target)
            in_deg[l.target] += 1
        q = deque(n.id for n in self.nodes if in_deg[n.id] == 0)
        seen = 0
        while q:
            cur = q.popleft()
            seen += 1
            for nxt in adj[cur]:
                in_deg[nxt] -= 1
                if in_deg[nxt] == 0:
                    q.append(nxt)
        if seen < len(self.nodes):
            raise ValueError(
                "CHART-AP-3 가드: sankey 가 순환 그래프 — DAG 만 허용. "
                "재무 분해는 단방향 흐름이어야 함."
            )
        return self


# ─── Type → Guard 매핑 ────────────────────────────────────────────────


_TYPE_TO_GUARD: dict[str, type[BaseModel]] = {
    "bar":          BarChartGuard,
    "line":         LineChartGuard,
    "stacked":      StackedBarGuard,
    "stacked_bar":  StackedBarGuard,
    "donut":        DonutGuard,
    "bubble":       BubbleChartGuard,
    "heatmap":      HeatmapGuard,
    "gantt":        GanttGuard,
    "network":      NetworkGuard,
    # v5.2.0 — 시계열 OHLC 차트
    "candle":       CandleChartGuard,
    "area":         AreaChartGuard,
    # v5.2.14 — production 가드 보강 3종
    "dual_line":    DualLineGuard,
    "forecast":     ForecastGuard,
    "choropleth":   ChoroplethGuard,
    # v5.2.14 — 신규 7종 (FT/Economist 스타일)
    "scatter":      ScatterGuard,
    "stacked_area": StackedAreaGuard,
    "lollipop":     LollipopGuard,
    "slope":        SlopeGuard,
    "small_multiples": SmallMultiplesGuard,
    "waterfall":    WaterfallGuard,
    "range_bar":    RangeBarGuard,
    # v5.3.0 — Sankey (재무 분해 / 자본 배분). registry orphan 해결.
    "sankey":       SankeyGuard,
}


def guard_for_type(chart_type: str) -> type[BaseModel] | None:
    """차트 type → Pydantic guard 모델 클래스. 없으면 None."""
    return _TYPE_TO_GUARD.get((chart_type or "").lower())


def validate_chart_data(chart_type: str, data: Any) -> tuple[bool, str]:
    """type 별 가드를 실행해 (passed, reason) 반환.

    Args:
        chart_type: 'bar' / 'line' / 'gantt' 등.
        data: chart["data"] 또는 spec["data"]["values"].

    Returns:
        (True, "") if pass, (False, error_message) if fail.
    """
    guard = guard_for_type(chart_type)
    if guard is None:
        # 가드 없는 type 은 통과 (validate_vega_spec 가 처리).
        return True, "no_typed_guard"

    try:
        # gantt 는 rows 키 / network 는 nodes+links / stacked 는 categories+series.
        if chart_type in ("gantt",):
            if isinstance(data, list):
                guard(rows=data)  # type: ignore[arg-type]
            elif isinstance(data, dict) and "rows" in data:
                guard(**data)
            else:
                guard(rows=[data] if isinstance(data, dict) else [])  # type: ignore[arg-type]
        elif chart_type == "network":
            if isinstance(data, dict):
                guard(**data)
            else:
                return False, "network 는 {nodes, links} dict 형식 필요"
        elif chart_type in ("stacked", "stacked_bar"):
            if isinstance(data, dict):
                guard(**data)
            else:
                return False, "stacked 는 {categories, series} dict 형식 필요"
        elif chart_type == "dual_line":
            # {left: {...}, right: {...}}
            if isinstance(data, dict):
                guard(**data)
            else:
                return False, "dual_line 는 {left, right} dict 형식 필요"
        elif chart_type == "forecast":
            # {actual, forecast, fork_at}
            if isinstance(data, dict):
                guard(**data)
            else:
                return False, "forecast 는 {actual, forecast, fork_at} dict 형식 필요"
        elif chart_type == "stacked_area":
            # {series: [{name, values}]}
            if isinstance(data, dict):
                guard(**data)
            else:
                return False, "stacked_area 는 {series: [...]} dict 형식 필요"
        elif chart_type == "slope":
            # {left_label, right_label, items}
            if isinstance(data, dict):
                guard(**data)
            else:
                return False, "slope 는 {left_label, right_label, items} dict 형식 필요"
        elif chart_type == "small_multiples":
            # {panels: [{label, series}]}
            if isinstance(data, dict):
                guard(**data)
            else:
                return False, "small_multiples 는 {panels: [...]} dict 형식 필요"
        elif chart_type == "sankey":
            # {nodes: [{id, label, ...}], links: [{source, target, value, ...}]}
            if isinstance(data, dict):
                guard(**data)
            else:
                return False, "sankey 는 {nodes, links} dict 형식 필요"
        else:
            # bar / line / donut / bubble / heatmap / choropleth / scatter /
            # lollipop / waterfall / range_bar — list[dict]
            if isinstance(data, list):
                guard(data=data)  # type: ignore[arg-type]
            else:
                return False, f"{chart_type} 는 list[dict] 형식 필요"
    except Exception as e:
        return False, str(e)

    return True, "ok"
