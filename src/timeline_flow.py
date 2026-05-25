"""v5.5.2 — 보고서 시간 척추 (시계열 흐름도) 조립.

하이브리드: 결정론 backbone + composer 선택적 윤색.
- backbone (항상): context.timeline (과거) + context.date (현재 앵커) +
  composed.watch_signals deadline (미래).
- 윤색 (있으면 우선): composed.timeline_flow.{heading, past[], future[]} —
  composer 가 서사 아크에 맞춰 milestone 라벨 + 시나리오 미래 분기 emit.

render (report_synthesizer) 와 emit (handoff.bundle_builder) 가 *같은* 조립을
쓰도록 공유. 과거=confirmed(실선), 미래=투사(점선/감시) — 정직성은 phase 로 전달.

future 는 토픽이 받쳐줄 때만 (watch_signals 또는 composer 미래 분기 존재 시).
없으면 과거→현재만. 둘 다 없으면 None (섹션 자체 생략).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_date(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def build_timeline_flow(context: Any, composed: Any) -> dict | None:
    """ComposedReport + ContextAnalysis → 시간 흐름도 dict 또는 None.

    반환: ``{"heading": str, "points": [{"date","label","phase","note"}]}``
    phase ∈ {"past","present","future"}. points 는 date 오름차순.
    """
    if context is None or composed is None:
        return None

    present_dt = _parse_date(getattr(context, "date", "") or "")

    tf = getattr(composed, "timeline_flow", None)
    if not isinstance(tf, dict):
        tf = {}

    # --- 과거 소스: composer 윤색 우선, 없으면 context.timeline ---
    raw_past = tf.get("past")
    if isinstance(raw_past, list) and raw_past:
        past_src = [
            {"date": p.get("date", ""), "label": p.get("label", ""), "note": p.get("note", "")}
            for p in raw_past if isinstance(p, dict)
        ]
    else:
        past_src = [
            {"date": e.get("date", ""), "label": e.get("event", ""), "note": e.get("impact", "")}
            for e in (getattr(context, "timeline", None) or []) if isinstance(e, dict)
        ]

    # --- 미래 소스: composer 시나리오 분기 우선, 없으면 watch_signals deadline ---
    raw_future = tf.get("future")
    if isinstance(raw_future, list) and raw_future:
        future_src = [
            {"date": p.get("date", ""), "label": p.get("label", ""),
             "note": (p.get("note") or p.get("branch") or "예상")}
            for p in raw_future if isinstance(p, dict)
        ]
    else:
        future_src = [
            {"date": s.get("deadline", ""), "label": (s.get("signal") or s.get("description") or ""),
             "note": "감시"}
            for s in (getattr(composed, "watch_signals", None) or [])
            if isinstance(s, dict) and s.get("deadline")
        ]

    points: list[dict] = []
    for src, default_phase in (
        [(p, "past") for p in past_src] + [(p, "future") for p in future_src]
    ):
        dt = _parse_date(src.get("date", ""))
        label = (src.get("label") or "").strip()
        if dt is None or not label:
            continue  # 축에 못 박는 점은 제외 (날짜 모호 / 라벨 없음)
        phase = default_phase
        if present_dt is not None:
            if dt < present_dt:
                phase = "past"
            elif dt > present_dt:
                phase = "future"
            else:
                phase = "present"
        points.append({
            "date": dt.strftime("%Y-%m-%d"),
            "label": label,
            "phase": phase,
            "note": (src.get("note") or "").strip(),
        })

    if not points:
        return None

    # 현재 앵커 (정확히 present 날짜의 점이 없을 때만 추가)
    if present_dt is not None and not any(p["phase"] == "present" for p in points):
        points.append({
            "date": present_dt.strftime("%Y-%m-%d"),
            "label": "현재", "phase": "present", "note": "",
        })

    points.sort(key=lambda p: p["date"])
    heading = (tf.get("heading") or "").strip() or "사건의 궤적"
    return {"heading": heading, "points": points}
