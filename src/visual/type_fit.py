"""차트 type-fit 파이프라인 — 데이터 모양에 안 맞는 type 을 맞는 type 으로 (v8.6.4).

SSOT: [docs/CHART_REDESIGN_V8_6_PLAN.md](../../docs/CHART_REDESIGN_V8_6_PLAN.md) §6.

**왜 있나.** 작성 모델이 고를 수 있는 type 이 늘어도, 늘기 전 습관대로 고른 차트가
남는다 — 연령대 구간을 `bar` 로, 부문→세부 2층 구성을 `donut` 으로, 일별 60일치를
`heatmap` 으로. 프롬프트 결정 트리가 1선이고 본 모듈은 *안전망* 이다. `_densify_ts_charts`
(CHART-AP-31) 나 `_reconcile_visual_references` (WRITE-AP-26) 와 같은 자리·같은 성격 —
0-LLM 결정적 변환, 디폴트 ON, 킬 스위치(`V8_TYPE_REFIT=0`).

**계약 (플랜 §6.1).**
- `refit_chart(chart, *, report_format) -> (chart_dict, rule_id | None)` — 순수 함수.
  바꿀 게 없으면 *원본 객체 그대로* 와 `None` 을 돌려준다(호출부가 identity 로 판별).
- `refit_charts(composed, *, report_format) -> list[RefitEvent]` — 보고서 전체를
  제자리 변환하고 적용 이력을 돌려준다. 변환된 섹션은 `ComposedSection.model_validate`
  로 재구성해 `_drop_invalid_charts` 를 한 번 더 태운다.

**안전 규칙 (플랜 §6.2 말미 — 예외 없음).**
1. **값·라벨을 만들지 않는다.** 규칙은 필드 이름 바꾸기·재그룹만 한다. 빈 구간을
   채우거나 그룹 이름을 지어내는 변환은 WRITE-AP-5 위반이라 애초에 규칙이 아니다.
2. **데이터를 버리지 않는다.** 일부 행만 옮겨야 하는 상황이면 변환하지 않는다.
3. **변환 후 `validate_chart_data` + `validate_chart_options` 에 실패하면 원본 유지.**
   "더 나빠지지 않기" 가 본 파이프라인의 최소 보장이다.

CLI (VM 의 발행본 코퍼스 실측)::

    python -m src.visual.type_fit --scan reports/ --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ─── 규칙 레지스트리 (플랜 §6.2 표와 1:1) ────────────────────────────────


@dataclass(frozen=True)
class RefitRule:
    """규칙 한 줄. `active=False` 는 *변환하지 않는* 규칙 (R6 no-op / R7 로그 전용)."""

    id: str
    source: str
    target: str
    summary: str
    active: bool = True


RULES: tuple[RefitRule, ...] = (
    RefitRule(
        "R1", "bar", "histogram",
        "구간 라벨(1~2 / 40대 / 20세 / 이상·이하·미만·초과) 4~24개 · 값이 0 이상 정수",
    ),
    RefitRule(
        "R2", "donut|stacked", "treemap",
        "라벨의 60% 이상이 'A · a1' / 'A/a1' / 'A > a1' · 그룹 2~8 · 그룹당 잎 ≥2 · 잎 6~40",
    ),
    RefitRule(
        "R3", "heatmap", "calendar_heat",
        "격자형 x 가 전부 ISO 날짜 60~400개(중복 없음) · y 가 단일 값",
    ),
    RefitRule(
        "R4", "slope", "range_bar",
        "items ≥8 (2시점 8개 이상은 기울기가 실타래) → before_after 덤벨",
    ),
    RefitRule(
        "R5", "bar", "bar",
        "표현만 — 항목 ≤8 · 라벨 ≤6자 · 셀 수 있는 값 · orientation/texture 미지정 "
        "→ orientation:'vertical' (세로 칸)",
    ),
    RefitRule(
        "R6", "line", "line",
        "명시적 no-op — 일별 ≤40 ISO line 의 '점 하나 = 하루' 는 v8.6.1 렌더러가 "
        "이미 데이터로 판정한다. 여기서 손대면 이중 소유가 된다",
        active=False,
    ),
    RefitRule(
        "R7", "gantt", "gantt",
        "구간 길이가 전부 0 인 gantt 는 CHART-AP-15 로 이미 drop 된다. 재배치 대상 "
        "type(event_timeline)이 아직 없으므로 본 Phase 는 'R7-pending' 로 세기만 한다",
        active=False,
    ),
)

RULE_IDS: frozenset[str] = frozenset(r.id for r in RULES) | {"R7-pending"}


@dataclass(frozen=True)
class RefitEvent:
    """규칙 1회 적용 기록. `usage_log` 의 `refit` 필드로 그대로 흘러간다."""

    rule: str
    from_type: str
    to_type: str
    section: int = 0
    index: int = 0
    title: str = ""
    report_format: str = "standard"

    def as_record(self) -> dict:
        """JSONL 계측용 최소 레코드 (플랜 §6.1 — `{from, to, rule}`)."""
        return {"from": self.from_type, "to": self.to_type, "rule": self.rule}


# ─── 패턴 ────────────────────────────────────────────────────────────────

# R1 — 순서 있는 구간 라벨 4종 (플랜 §6.2). *모든* 라벨이 하나라도 만족해야 한다.
_BIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*\d[\d,.]*\s*[~\-–—]\s*\d"),      # 1~2 · 10-20 · 3~5천
    re.compile(r"^\s*\d+\s*대\s*$"),                   # 40대
    re.compile(r"^\s*\d+\s*세"),                       # 20세 이상
    re.compile(r"(이상|이하|미만|초과)\s*$"),            # 1억 이상 · 5년 미만
)

# R2 — 2층 구성 분리자. 첫 번째 것에서만 자른다 ('A · a1 · b' 는 그룹 A / 잎 'a1 · b').
_GROUP_SPLIT = re.compile(r"\s*[·/>]\s*")

# R3 — ISO 날짜.
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 계약 상한 — 각 target type 의 가드와 같은 값 (여기서 먼저 걸러 실패 변환을 줄인다).
_HISTOGRAM_MIN, _HISTOGRAM_MAX = 4, 24
_HISTOGRAM_BIN_MAXLEN = 12
_TREEMAP_GROUPS_MIN, _TREEMAP_GROUPS_MAX = 2, 8
_TREEMAP_LEAVES_MIN, _TREEMAP_LEAVES_MAX = 6, 40
_CALENDAR_MIN, _CALENDAR_MAX = 60, 400
_SLOPE_TO_RANGE_MIN_ITEMS = 8
_VERTICAL_MAX_BARS = 8
_VERTICAL_MAX_LABEL = 6
_COUNTABLE_MAX = 500      # charts.js `isCountable` 과 같은 상한

# annotation 레이어가 없는 target — 옮겨봐야 렌더되지 않으므로 떼어낸다.
_NO_ANNOTATION_TARGETS: frozenset[str] = frozenset({"treemap", "calendar_heat"})


# ─── 작은 도우미 ─────────────────────────────────────────────────────────


def _num(v: Any) -> float | None:
    """유한 실수면 float, 아니면 None (bool 은 숫자로 치지 않는다)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _is_integer(v: float) -> bool:
    return abs(v - round(v)) < 1e-9


def _text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _is_bin_label(label: str) -> bool:
    return any(p.search(label) for p in _BIN_PATTERNS)


def _countable(values: list[float], unit_label: str) -> bool:
    """charts.js `isCountable` 의 파이썬 미러 — 전부 정수 · |max| ≤ 500 · 단위에 % 없음."""
    if "%" in unit_label:
        return False
    if not values:
        return False
    return all(_is_integer(v) for v in values) and max(abs(v) for v in values) <= _COUNTABLE_MAX


def _option_fields(chart_type: str) -> frozenset[str]:
    try:
        from src.visual.schemas import option_fields
    except ImportError:  # pragma: no cover — schemas 없는 환경
        return frozenset()
    return option_fields(chart_type)


def _rebuild_payload(
    chart: dict, *, target: str, data: Any, extra: dict | None = None,
) -> dict:
    """원본 payload 를 그대로 물려주되 type/data 를 갈아끼운다.

    떼는 것은 두 가지뿐 — ⑴ 원본 type 에만 있는 표현 옵션(새 type 의 가드가 모르는
    키라 뜻 없이 남는다) ⑵ annotation 레이어가 없는 target 의 `annotations`.
    `title` / `subtitle` / `unit_line` / `source` / `note` / `takeaway` 는 전부 계승
    한다 — 이것들은 작성 모델이 쓴 *글* 이라 우리가 만들지도 버리지도 않는다.
    """
    src_type = (chart.get("type") or "").lower()
    drop = set(_option_fields(src_type)) - set(_option_fields(target))
    if target in _NO_ANNOTATION_TARGETS:
        drop.add("annotations")
    out = {k: v for k, v in chart.items() if k not in drop}
    out["type"] = target
    out["data"] = data
    if extra:
        out.update(extra)
    return out


def _accept(candidate: dict) -> bool:
    """변환 결과가 가드를 통과하는가 (실패면 원본 유지 — 플랜 §6.2 안전 규칙 ③)."""
    try:
        from src.visual.schemas import validate_chart_data, validate_chart_options
    except ImportError:  # pragma: no cover
        return False
    ctype = (candidate.get("type") or "").lower()
    try:
        ok, reason = validate_chart_data(ctype, candidate.get("data"))
        if ok:
            ok, reason = validate_chart_options(ctype, candidate)
    except Exception as e:  # noqa: BLE001 — 가드 버그가 보고서를 막지 않게
        logger.warning("[type_fit] 가드 예외로 변환 취소: %s", e)
        return False
    if not ok:
        logger.info("[type_fit] 변환 후 가드 실패 → 원본 유지 (%s): %s", ctype, reason)
    return bool(ok)


# ─── 규칙 구현 ───────────────────────────────────────────────────────────


def _r1_bar_to_histogram(chart: dict) -> dict | None:
    """bar → histogram. 라벨이 전부 *순서 있는 구간* 이고 값이 0 이상 정수일 때만."""
    rows = chart.get("data")
    if not isinstance(rows, list) or not (_HISTOGRAM_MIN <= len(rows) <= _HISTOGRAM_MAX):
        return None
    bins: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            return None
        label = _text(raw.get("label"))
        if not label or len(label) > _HISTOGRAM_BIN_MAXLEN or not _is_bin_label(label):
            return None
        value = _num(raw.get("value"))
        if value is None or value < 0 or not _is_integer(value):
            return None
        row: dict = {"bin": label, "count": float(round(value))}
        note = _text(raw.get("note"))
        if note:
            row["note"] = note
        bins.append(row)
    if sum(b["count"] for b in bins) <= 0:
        return None
    return _rebuild_payload(chart, target="histogram", data=bins)


def _r2_to_treemap(chart: dict) -> dict | None:
    """donut / stacked(시나리오 1개) → treemap. 라벨이 이미 2층을 품고 있을 때만.

    분리자가 없는 라벨은 *자기 자신을 그룹으로 하는 잎 1개* 로 취급한다 — 그러면
    "그룹당 잎 ≥2" 제약에 자동으로 걸려 변환이 취소된다. 데이터를 버리지 않으면서
    (안전 규칙 ②) 애매한 경우를 배제하는 가장 단순한 방법이다.
    """
    ctype = (chart.get("type") or "").lower()
    if ctype == "donut":
        rows = chart.get("data")
    elif ctype in ("stacked", "stacked_bar"):
        d = chart.get("data")
        if not isinstance(d, dict):
            return None
        scenarios = d.get("scenarios")
        if not isinstance(scenarios, list) or len(scenarios) != 1:
            return None
        first = scenarios[0]
        rows = first.get("segments") if isinstance(first, dict) else None
    else:
        return None
    if not isinstance(rows, list) or len(rows) < _TREEMAP_LEAVES_MIN:
        return None

    split_hits = 0
    parsed: list[tuple[str, str, float]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            return None
        label = _text(raw.get("label"))
        value = _num(raw.get("value"))
        if not label or value is None or value <= 0:
            return None
        parts = _GROUP_SPLIT.split(label, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            parsed.append((parts[0].strip(), parts[1].strip(), value))
            split_hits += 1
        else:
            parsed.append((label, label, value))
    if split_hits < 0.6 * len(rows):
        return None

    groups: dict[str, list[dict]] = {}
    for grp, leaf, value in parsed:
        groups.setdefault(grp, []).append({"label": leaf, "value": value})
    if not (_TREEMAP_GROUPS_MIN <= len(groups) <= _TREEMAP_GROUPS_MAX):
        return None
    if any(len(kids) < 2 for kids in groups.values()):
        return None
    leaves = sum(len(kids) for kids in groups.values())
    if not (_TREEMAP_LEAVES_MIN <= leaves <= _TREEMAP_LEAVES_MAX):
        return None

    data: dict = {"children": [
        {"label": grp, "children": kids} for grp, kids in groups.items()
    ]}
    unit_label = _text(chart.get("unit_label"))
    if unit_label:
        data["unit_label"] = unit_label
    return _rebuild_payload(chart, target="treemap", data=data)


def _r3_heatmap_to_calendar(chart: dict) -> dict | None:
    """격자형 heatmap → calendar_heat. x 가 전부 ISO 날짜이고 y 가 한 종류일 때만.

    400행을 넘으면 변환하지 않는다 — 가드 상한에 맞추려면 행을 잘라야 하는데 그건
    데이터를 버리는 것이라 안전 규칙 ② 위반이다.
    """
    rows = chart.get("data")
    if not isinstance(rows, list) or not (_CALENDAR_MIN <= len(rows) <= _CALENDAR_MAX):
        return None
    ys: set[str] = set()
    seen: set[str] = set()
    values: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict) or "severity" in raw:
            return None       # 강도 트랙형 heatmap 은 날짜 축이 아니다
        x = raw.get("x")
        if not isinstance(x, str) or not _ISO_DATE.match(x) or x in seen:
            return None
        value = _num(raw.get("value"))
        if value is None or value < 0:
            return None
        seen.add(x)
        ys.add(str(raw.get("y")))
        values.append({"date": x, "value": value})
    if len(ys) != 1:
        return None

    data: dict = {"values": values}
    metric = _text(next(iter(ys)))
    if metric:
        data["metric_label"] = metric      # 있던 y 라벨 재사용 (생성 아님)
    unit_label = _text(chart.get("unit_label"))
    if unit_label:
        data["unit_label"] = unit_label
    return _rebuild_payload(chart, target="calendar_heat", data=data)


def _r4_slope_to_range_bar(chart: dict) -> dict | None:
    """slope → range_bar(before_after). 2 시점 8항목이 넘으면 기울기가 실타래가 된다."""
    d = chart.get("data")
    if not isinstance(d, dict):
        return None
    items = d.get("items")
    if not isinstance(items, list) or len(items) < _SLOPE_TO_RANGE_MIN_ITEMS:
        return None
    rows: list[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            return None
        label = _text(raw.get("label"))
        a, b = _num(raw.get("a")), _num(raw.get("b"))
        if not label or a is None or b is None:
            return None
        rows.append({"label": label, "before": a, "after": b})
    extra: dict = {"mode": "before_after"}
    left, right = _text(d.get("left_label")), _text(d.get("right_label"))
    if left:
        extra["before_label"] = left
    if right:
        extra["after_label"] = right
    return _rebuild_payload(chart, target="range_bar", data=rows, extra=extra)


def _r5_bar_vertical(chart: dict) -> dict | None:
    """bar → bar(세로 칸). *표현만* 바꾼다 — data 는 한 글자도 안 건드린다.

    charts.js `drawBar` 의 rung 게이트(항목 ≤8 · 라벨 ≤6자 · countable)와 같은 조건.
    게이트를 못 넘을 값을 넣으면 렌더러가 가로로 강등할 뿐이라 여기서 미리 막는다.
    """
    if chart.get("orientation") is not None or chart.get("texture") is not None:
        return None       # 작성 모델이 이미 표현을 지정했으면 존중한다
    rows = chart.get("data")
    if not isinstance(rows, list) or not (2 <= len(rows) <= _VERTICAL_MAX_BARS):
        return None
    values: list[float] = []
    for raw in rows:
        if not isinstance(raw, dict):
            return None
        label = _text(raw.get("label"))
        if not label or len(label) > _VERTICAL_MAX_LABEL:
            return None
        value = _num(raw.get("value"))
        if value is None:
            return None
        values.append(value)
    unit_label = _text(chart.get("unit_label")) or _text(chart.get("unit_line"))
    if not _countable(values, unit_label):
        return None
    out = dict(chart)
    out["orientation"] = "vertical"
    return out


def _r7_gantt_zero_duration(chart: dict) -> bool:
    """구간 길이가 전부 0 인 gantt 인가 (CHART-AP-15 — 변환은 안 하고 세기만)."""
    rows = chart.get("data")
    if not isinstance(rows, list) or len(rows) < 2:
        return False
    for raw in rows:
        if not isinstance(raw, dict):
            return False
        start, end = raw.get("start"), raw.get("end")
        if start is None or end is None or start != end:
            return False
    return True


# ─── 공개 API ────────────────────────────────────────────────────────────


def refit_chart(chart: dict, *, report_format: str = "standard") -> tuple[dict, str | None]:
    """차트 1개를 데이터 모양에 맞는 type 으로 (플랜 §6.1).

    Args:
        chart: `{type, title, data, ...}` payload.
        report_format: "standard" | "reportage". 현재 어떤 규칙도 포맷으로 갈리지
            않지만, 계측(`RefitEvent.report_format`)에 실려 `--scan` 이 포맷별로
            오배치를 나눠 볼 수 있게 한다.

    Returns:
        `(payload, rule_id)`. 바꿀 게 없으면 `(원본 객체, None)` — 호출부는 identity
        (`out is chart`) 로 변경 여부를 판별한다. `rule_id` 가 있는데 payload 가
        원본 그대로일 수 있다 (R7-pending — 세기만 하는 규칙).
    """
    if not isinstance(chart, dict):
        return chart, None
    ctype = (chart.get("type") or "").lower()
    if not ctype:
        return chart, None

    if ctype == "bar":
        for rule_id, fn in (("R1", _r1_bar_to_histogram), ("R5", _r5_bar_vertical)):
            candidate = fn(chart)
            if candidate is not None and _accept(candidate):
                return candidate, rule_id
        return chart, None

    if ctype in ("donut", "stacked", "stacked_bar"):
        candidate = _r2_to_treemap(chart)
        if candidate is not None and _accept(candidate):
            return candidate, "R2"
        return chart, None

    if ctype == "heatmap":
        candidate = _r3_heatmap_to_calendar(chart)
        if candidate is not None and _accept(candidate):
            return candidate, "R3"
        return chart, None

    if ctype == "slope":
        candidate = _r4_slope_to_range_bar(chart)
        if candidate is not None and _accept(candidate):
            return candidate, "R4"
        return chart, None

    if ctype == "gantt" and _r7_gantt_zero_duration(chart):
        # 재배치할 type 이 아직 없다 (V9 event_timeline 대기). 세기만 한다.
        return chart, "R7-pending"

    # R6 — line 은 명시적 no-op. '점 하나 = 하루' 판정은 v8.6.1 렌더러 소유.
    return chart, None


def _revalidate_section(section: Any) -> Any | None:
    """변환된 섹션을 `_drop_invalid_charts` 에 한 번 더 태운다 (플랜 §6.1).

    이전에 드롭된 기록(`_dropped_charts`)은 재구성으로 사라지므로 다시 이어 붙인다
    — usage_log 의 emit/kept 2단 집계(CHART-AP-44)가 이 기록에 기댄다.
    """
    try:
        from src.models import ComposedSection
    except ImportError:  # pragma: no cover
        return None
    try:
        rebuilt = ComposedSection.model_validate(section.model_dump())
    except Exception as e:  # noqa: BLE001 — 재검증 실패가 보고서를 막지 않게
        logger.warning("[type_fit] 섹션 재검증 실패 → 원본 유지: %s", e)
        return None
    prev = list(getattr(section, "_dropped_charts", None) or [])
    if prev:
        rebuilt._dropped_charts = prev + list(rebuilt._dropped_charts)
    return rebuilt


def refit_charts(composed: Any, *, report_format: str = "standard") -> list[RefitEvent]:
    """보고서의 모든 차트를 제자리 type-fit 하고 적용 이력을 돌려준다."""
    events: list[RefitEvent] = []
    sections = list(getattr(composed, "sections", None) or [])
    if not sections:
        return events
    for si, section in enumerate(sections):
        charts = list(getattr(section, "charts", None) or [])
        if not charts:
            continue
        new_charts: list[dict] = []
        changed = False
        for ci, chart in enumerate(charts):
            out, rule = refit_chart(chart, report_format=report_format)
            if rule:
                events.append(RefitEvent(
                    rule=rule,
                    from_type=(chart.get("type") or "").lower() if isinstance(chart, dict) else "",
                    to_type=(out.get("type") or "").lower() if isinstance(out, dict) else "",
                    section=si, index=ci,
                    title=(chart.get("title") or "") if isinstance(chart, dict) else "",
                    report_format=report_format,
                ))
            if out is not chart:
                changed = True
            new_charts.append(out)
        if not changed:
            continue
        section.charts = new_charts
        rebuilt = _revalidate_section(section)
        if rebuilt is not None:
            composed.sections[si] = rebuilt
    if events:
        logger.info(
            "[type_fit] %d건 재배치: %s",
            len(events),
            ", ".join(f"{e.rule} {e.from_type}→{e.to_type}" for e in events[:6]),
        )
    return events


def refit_records(events: Iterable[RefitEvent]) -> list[dict]:
    """`usage_log.append_run(refit=...)` 에 넘길 최소 레코드 리스트."""
    return [e.as_record() for e in events]


# ─── CLI — 발행본 코퍼스 실측 (읽기 전용) ────────────────────────────────


def scan_reports(directory: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    """`reports/analysis_*.json` 을 훑어 규칙별 적중 수와 보고서 id 를 센다.

    Pydantic 으로 로드하지 않고 raw JSON 을 훑는다 — 옛 스키마의 발행본도 세어야
    하기 때문이다(코퍼스 실측이 목적). 파일은 **한 글자도 쓰지 않는다**.
    """
    hits: dict[str, int] = {}
    where: dict[str, list[str]] = {}
    for path in sorted(directory.glob("analysis_*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("[type_fit] 읽기 실패 %s: %s", path.name, e)
            continue
        composed = (doc.get("composed_report") or {}) if isinstance(doc, dict) else {}
        fmt = ((doc.get("request") or {}).get("report_format")
               if isinstance(doc.get("request"), dict) else None) or "standard"
        report_id = path.stem[len("analysis_"):] if path.stem.startswith("analysis_") else path.stem
        for section in (composed.get("sections") or []):
            if not isinstance(section, dict):
                continue
            for chart in (section.get("charts") or []):
                if not isinstance(chart, dict):
                    continue
                _, rule = refit_chart(chart, report_format=str(fmt))
                if not rule:
                    continue
                hits[rule] = hits.get(rule, 0) + 1
                ids = where.setdefault(rule, [])
                if report_id not in ids:
                    ids.append(report_id)
    return hits, where


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.visual.type_fit",
        description="차트 type-fit 규칙의 발행본 코퍼스 적중 현황 (읽기 전용).",
    )
    parser.add_argument(
        "--scan", metavar="DIR", default=None,
        help="발행본 JSON 디렉토리 (예: reports/). --rules 만 볼 때는 생략 가능.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="본 CLI 는 언제나 읽기 전용이다. 의도를 분명히 하려는 플래그로, "
             "붙여도 안 붙여도 동작이 같다 (파일을 쓰지 않는다).",
    )
    parser.add_argument(
        "--rules", action="store_true",
        help="규칙표만 출력하고 종료.",
    )
    args = parser.parse_args(argv)

    if args.rules:
        for rule in RULES:
            mark = " " if rule.active else "*"
            print(f"{mark}{rule.id:<4} {rule.source:>16} → {rule.target:<14} {rule.summary}")
        print("\n* = 변환하지 않는 규칙 (R6 명시적 no-op · R7 계측 전용)")
        return 0

    if not args.scan:
        parser.error("--scan DIR 이 필요하다 (규칙표만 보려면 --rules).")
    directory = Path(args.scan)
    if not directory.is_dir():
        print(f"[type_fit] 디렉토리가 아니다: {directory}", file=sys.stderr)
        return 2
    hits, where = scan_reports(directory)
    total_files = len(list(directory.glob("analysis_*.json")))
    print(f"[type_fit] --scan {directory} (읽기 전용) — 보고서 {total_files}건")
    if not hits:
        print("  적중 0 — 재배치할 차트가 없다.")
        return 0
    for rule in RULES:
        for rid in (rule.id, f"{rule.id}-pending"):
            if rid not in hits:
                continue
            ids = where.get(rid, [])
            head = ", ".join(ids[:5]) + (f" 외 {len(ids) - 5}건" if len(ids) > 5 else "")
            print(f"  {rid:<12} {hits[rid]:>4}건  ({rule.source} → {rule.target})  {head}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    raise SystemExit(main())
