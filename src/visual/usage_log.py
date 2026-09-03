"""Chart type usage log — starvation alarm SSOT (v5.2.14).

캔들 차트 회귀 (v5.2.0 에 추가했으나 거의 emit X) 교훈을 받아 신설.
각 보고서 생성 시 emit 된 chart type 분포를 JSONL 로 영구 기록하고,
누적 N 보고서 동안 0회 emit 된 type 을 starved 로 표시한다.

스토리지:
- 기본 경로: ``$CHART_USAGE_LOG_PATH`` 또는 ``logs/chart_usage.jsonl``
- 한 줄 = 한 보고서. JSON: ``{ts, event, mode, types: list[str]}``
- append-only. 회전 / truncate 없음 (수명 동안 < 1 MB)

CLI::

    python -m src.visual.usage_log analyze [--window 100]
    python -m src.visual.usage_log analyze --window 30 --known-types bar,line,...

5-Layer Usage Guarantee 의 Layer 1.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import Counter
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


# Production 차트 21종 SSOT — 캔들 회귀 방지 목적의 starvation 점검 대상.
# 20종 (ComposedSection.charts) + 1종 (ComposedReport.embedded_map). map 은
# 별도 채널이지만 사용자 관점의 시각화 type 이므로 starvation 분모에 포함.
# v5.3.0 — FT/Economist 스타일 신규 7종 추가 (scatter / stacked_area /
# lollipop / slope / small_multiples / waterfall / range_bar).
# 신규 type 추가 시 본 리스트와 ``src/visual/schemas.py:_TYPE_TO_GUARD``,
# ``docs/VISUAL_CAPABILITY_REGISTRY.yaml``,
# ``tests/regression/fixtures/chart_type_scenarios.yaml`` 함께 갱신.
KNOWN_CHART_TYPES: tuple[str, ...] = (
    # 기존 12종 (v5.2.13 까지; network 는 v7.9.17 CHART-AP-36 으로 폐기)
    "bar", "donut", "line", "gantt", "stacked",
    "bubble", "heatmap", "dual_line", "forecast", "choropleth",
    "candle", "area",
    # v5.3.0 — FT/Economist 스타일 신규 7종
    "scatter", "stacked_area", "lollipop", "slope",
    "small_multiples", "waterfall", "range_bar",
    # v5.3.0 — Sankey (재무 분해 / 자본 배분, registry orphan 해결)
    "sankey",
    # v7.0.0 — Track A 신규 3종 (REFACTOR_V7_PLAN.md §1.3)
    "bump", "bullet", "connected_scatter",
    # v7.5.0 — 이중 축 결합 + 사회 이슈 어휘 4종
    "combo", "diverging_bar", "pyramid", "dot_matrix",
    # v7.9.9 — 좌축 비율 line + 우축 지수 candle (장마감 브리핑 breadth 전용, 결정적 주입)
    "combo_candle",
    # v7.9.10 — 옵션 데스크 전용 (결정적 주입): 변동성 스큐 곡선 + 부호 한 줄 지표
    "iv_skew", "indicator",
    # v8.0.0 — 르포 전용 행위자 관계도 (진영 칼럼 결정적 배치, force 금지)
    "stakeholder_map",
    # v8.6.2 — 위계 2종 (2층 구성 / 소속)
    "treemap", "tree",
    # embedded_map (별도 채널)
    "map",
)

# 누적 N 보고서 동안 0회 emit 시 starved 로 표시. 운영 경험으로 조정.
DEFAULT_STARVATION_WINDOW = 30

# v8.3.0 — composer 가 *스스로 선택할 수 없는* type. 재균형 힌트에서 제외:
#  · candle — available_time_series OHLC 데이터가 있을 때만 (데이터 의존, 창작 금지)
#  · combo_candle / iv_skew / indicator — 장마감 브리핑의 결정적 주입 전용
#  · stakeholder_map — 르포(reportage) 전용
#  · map — embedded_map 별도 채널 (charts 배열 type 아님)
NON_NARRATIVE_TYPES: frozenset = frozenset(
    {"candle", "combo_candle", "iv_skew", "indicator", "stakeholder_map", "map"}
)

# 힌트로 넘길 최대 type 수 — 프롬프트 토큰 경제 + 한 보고서에서 소화 가능한 양.
REBALANCE_HINT_MAX_TYPES = 6


def _default_path() -> Path:
    raw = os.environ.get("CHART_USAGE_LOG_PATH")
    if raw:
        return Path(raw)
    return Path("logs") / "chart_usage.jsonl"


def append_run(
    event: str,
    mode: str,
    chart_types: Iterable[str],
    *,
    dropped_types: Iterable[str] | None = None,
    path: Path | None = None,
) -> None:
    """한 보고서의 chart type 분포를 JSONL 한 줄로 append.

    Orchestrator 가 보고서 완성 직후 호출. 파일 IO 실패는 warning 만, raise 안 함
    (보고서 생성을 막지 않기 위해).

    v8.5.12 — **emit / kept 2단 기록**. ``types`` 는 살아남아 발행된 type(구 필드,
    하위호환), ``dropped`` 는 ``_drop_invalid_charts`` 가 버린 type. 이 둘을 분리해야
    "가드가 100% 버려서 0회" 인 배관 이상(CHART-AP-44)과 "composer 가 안 골라서 0회"
    인 진짜 기아를 구분할 수 있다. 구분 전에는 드롭된 type 이 기아로 위장돼 재균형
    힌트가 *깨진 type 을 더 밀어넣고 다시 전부 버리는* 악순환을 돌렸다.
    """
    target = path or _default_path()
    record = {
        "ts": int(time.time()),
        "event": event,
        "mode": mode,
        "types": list(chart_types),
    }
    dropped_list = [t for t in (dropped_types or []) if isinstance(t, str)]
    if dropped_list:
        record["dropped"] = dropped_list
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("[chart_usage] append fail: %s", e)


def _read_last_n(path: Path, n: int) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        logger.warning("[chart_usage] read fail: %s", e)
        return []
    tail = lines[-n:] if n > 0 else lines
    out: list[dict] = []
    for ln in tail:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def analyze(
    window: int = DEFAULT_STARVATION_WINDOW,
    known_types: tuple[str, ...] = KNOWN_CHART_TYPES,
    *,
    path: Path | None = None,
) -> dict:
    """최근 ``window`` 개 보고서의 chart type 분포 분석.

    Returns dict::

        {
            "window": 30,
            "reports_analyzed": 28,
            "distribution": {"bar": 18, "line": 14, ...},
            "starved_types": ["candle", "heatmap"],  # 0회 emit
            "rare_types": ["sankey"],                  # 1회 emit (window>=10일 때만)
        }

    Orchestrator 가 보고서마다 호출하지 않음 — 별도 CLI 또는 cron 으로 점검.
    """
    target = path or _default_path()
    records = _read_last_n(target, window)
    counter: Counter[str] = Counter()
    dropped_counter: Counter[str] = Counter()
    for r in records:
        for t in r.get("types", []):
            if isinstance(t, str):
                counter[t] += 1
        for t in r.get("dropped", []):
            if isinstance(t, str):
                dropped_counter[t] += 1
    starved = sorted(t for t in known_types if counter.get(t, 0) == 0)
    rare = sorted(
        t for t in known_types
        if 0 < counter.get(t, 0) <= max(1, len(records) // 20)
        and t not in starved
    ) if len(records) >= 10 else []
    # v8.5.12 — 배관 이상: composer 가 emit 했는데 가드가 전량 버린 type.
    # 기아(starved)와 *반드시* 구분한다 — 재균형 힌트가 깨진 type 을 더 밀어넣는
    # 악순환의 근원 (CHART-AP-44 의 자기증폭 고리).
    plumbing = sorted(
        t for t, n in dropped_counter.items() if n > 0 and counter.get(t, 0) == 0
    )
    return {
        "window": window,
        "reports_analyzed": len(records),
        "distribution": dict(counter.most_common()),
        "dropped_distribution": dict(dropped_counter.most_common()),
        "starved_types": starved,
        "rare_types": rare,
        "plumbing_suspect_types": plumbing,
    }


def composer_rebalance_hint(
    window: int = DEFAULT_STARVATION_WINDOW,
    *,
    max_types: int = REBALANCE_HINT_MAX_TYPES,
    path: Path | None = None,
) -> list[str]:
    """v8.3.0 — 시각 다양성 자기교정 루프의 '적용' 절반.

    최근 ``window`` 개 보고서에서 굶주린(0회 emit) + 희귀(rare) *서사* type 을
    composer 프롬프트 힌트용으로 반환. 사용자 결정(2026-07-02): starvation 을
    관리자에게 알리는 대신 봇이 스스로 발생 빈도를 높인다 — orchestrator 가
    보고서마다 본 힌트를 composer 프롬프트에 주입 (제어 0-LLM).

    - 표본 <10 보고서면 빈 리스트 (신뢰 불가 — 힌트 미주입 = 프롬프트 byte-equal)
    - composer 가 선택할 수 없는 type (NON_NARRATIVE_TYPES) 제외
    - starved 우선, 이어 rare, 최대 ``max_types`` 개
    """
    result = analyze(window, path=path)
    if result["reports_analyzed"] < 10:
        return []
    # v8.5.12 — 배관 이상 type 은 힌트에서 제외. emit 은 되는데 가드가 전량 버리는
    # type 을 "더 자주 쓰라" 고 밀어넣으면 전부 다시 버려질 뿐이다 (CHART-AP-44).
    # 고칠 곳은 프롬프트가 아니라 가드·렌더러 계약 — warn_if_starved 가 그렇게 경고한다.
    broken = set(result.get("plumbing_suspect_types") or [])
    excluded = NON_NARRATIVE_TYPES | broken
    pool = [t for t in result["starved_types"] if t not in excluded]
    pool += [t for t in result["rare_types"] if t not in excluded]
    return pool[:max_types]


def warn_if_starved(
    window: int = DEFAULT_STARVATION_WINDOW,
    known_types: tuple[str, ...] = KNOWN_CHART_TYPES,
    *,
    path: Path | None = None,
) -> None:
    """``analyze()`` 결과 starved type 이 있으면 WARNING 로그.

    Orchestrator 가 보고서마다 1회 호출 (cheap — 단순 파일 tail 읽기).
    분석 가능 표본 (>=10 reports) 모인 후에만 실제 경고.
    """
    result = analyze(window, known_types, path=path)
    if result["reports_analyzed"] < 10:
        return
    starved = result["starved_types"]
    rare = result["rare_types"]
    plumbing = result.get("plumbing_suspect_types") or []
    if plumbing:
        # 기아가 아니라 *배관 이상* — composer 는 만들었는데 가드가 전량 버렸다.
        # 프롬프트를 손댈 게 아니라 프롬프트↔가드↔렌더러 계약을 맞춰야 한다
        # (CHART-AP-44. parity 테스트: tests/regression/test_prompt_guard_parity.py).
        logger.error(
            "[chart_usage] PLUMBING FAULT — emit 됐으나 가드가 전량 drop 한 type "
            "(최근 %d 보고서): %s. 프롬프트↔가드↔렌더러 계약 불일치 의심 (CHART-AP-44)",
            result["reports_analyzed"], ", ".join(plumbing),
        )
    if starved:
        logger.warning(
            "[chart_usage] STARVED chart types (0 emit in last %d reports): %s",
            result["reports_analyzed"], ", ".join(starved),
        )
    if rare:
        logger.warning(
            "[chart_usage] RARE chart types (<=5%% in last %d reports): %s",
            result["reports_analyzed"], ", ".join(rare),
        )


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Chart type usage log analyzer")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_analyze = sub.add_parser("analyze", help="최근 N 보고서의 type 분포 분석")
    p_analyze.add_argument("--window", type=int, default=DEFAULT_STARVATION_WINDOW)
    p_analyze.add_argument(
        "--known-types", type=str, default=",".join(KNOWN_CHART_TYPES),
        help="comma-separated list of expected chart types",
    )
    p_analyze.add_argument("--path", type=str, default=None)
    args = parser.parse_args()
    if args.cmd == "analyze":
        known = tuple(t.strip() for t in args.known_types.split(",") if t.strip())
        result = analyze(
            window=args.window,
            known_types=known,
            path=Path(args.path) if args.path else None,
        )
        print(f"window={result['window']} reports_analyzed={result['reports_analyzed']}")
        print("distribution:")
        for t, n in result["distribution"].items():
            print(f"  {t:20s} {n}")
        if result["starved_types"]:
            print(f"STARVED ({len(result['starved_types'])}): "
                  f"{', '.join(result['starved_types'])}")
        if result["rare_types"]:
            print(f"RARE    ({len(result['rare_types'])}): "
                  f"{', '.join(result['rare_types'])}")
        if not result["starved_types"] and not result["rare_types"]:
            print("(all known types emitted in window)")


if __name__ == "__main__":
    _cli()
