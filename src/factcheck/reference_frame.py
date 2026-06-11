"""V7 Track C — 기준시점 계약(reference frame) 빌더 (REFACTOR_V7_PLAN.md §3.3).

"이 보고서가 어느 시점의 사실을 필요로 하는가" 를 결정적(0-LLM)으로 조립해
composer 작성 / codex 검수 / Opus 보완 3곳에 *동일하게* 주입한다. 6/1↔6/5 회귀
(사실로서 정확하지만 보고서 기준 시점과 다른 날짜의 시장 수치가 검수를 통과)의
근본 원인 = 루프 양 패스가 이 계약 없이 같은 맹점을 공유 — 의 교정 장치.

flag ``V7_REF_FRAME`` (Config.enable_ref_frame) OFF 면 호출 자체가 안 일어나
v6.2.0 byte-equal. 데이터 소스는 ContextAnalysis.time_series (market_fetcher 가
채운 OHLCBar dict 들) — 외부 호출 없음.
"""

from __future__ import annotations

from src.models import ContextAnalysis


def build_reference_frame(context: ContextAnalysis) -> dict:
    """ContextAnalysis.time_series → 종목별 최신 가용 시점 계약 dict.

    형태::

        {"instruments": [
            {"name": "코스피", "last_available_date": "2026-06-04",
             "last_close": 2948.12, "last_day_change_pct": 0.43}
        ]}

    - 시계열이 비었거나 date/close 없는 항목뿐이면 ``{"instruments": []}`` (inert).
    - 정렬·최댓값은 ISO 날짜 문자열 비교 (시계열이 오름차순이 아니어도 안전).
    - 본 dict 는 *데이터만* 담는다 — 해석 규칙(어느 시점을 기본으로 삼을지)은
      각 주입처의 프롬프트 블록이 갖는다 (drift 방지: 데이터 1곳, 규칙은 호출처).
    """
    instruments: list[dict] = []
    for ts in getattr(context, "time_series", []) or []:
        if not isinstance(ts, dict):
            continue
        name = ts.get("instrument") or ts.get("name")
        bars = [
            d for d in (ts.get("data") or [])
            if isinstance(d, dict) and d.get("date") and d.get("close")
        ]
        if not name or not bars:
            continue
        bars = sorted(bars, key=lambda d: str(d["date"]))
        last = bars[-1]
        entry: dict = {
            "name": name,
            "last_available_date": str(last["date"]),
            "last_close": float(last["close"]),
        }
        if len(bars) > 1:
            prior = float(bars[-2]["close"])
            if prior:
                entry["last_day_change_pct"] = round(
                    (float(last["close"]) - prior) / prior * 100, 2,
                )
        instruments.append(entry)
    return {"instruments": instruments}
