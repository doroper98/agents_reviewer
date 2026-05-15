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
        else:
            # bar / line / donut / bubble / heatmap — list[dict]
            if isinstance(data, list):
                guard(data=data)  # type: ignore[arg-type]
            else:
                return False, f"{chart_type} 는 list[dict] 형식 필요"
    except Exception as e:
        return False, str(e)

    return True, "ok"
