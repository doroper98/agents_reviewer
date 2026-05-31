"""V5 Phase 0B — Regression test helpers.

Pure functions only. No pytest dependency at import time so the helpers
can be reused by ``scripts/run_regression.py`` and ``scripts/record_baseline.py``
without forcing pytest install.

Master spec: REFACTOR_V5_PLAN.md §3 (Phase 0B).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ─── 경로 SSOT ──────────────────────────────────────────────────────────
REGRESSION_ROOT = Path(__file__).resolve().parent
FIXTURES_DIR = REGRESSION_ROOT / "fixtures"
GOLDEN_PROMPTS_PATH = FIXTURES_DIR / "golden_prompts.yaml"
SAMPLE_REPORTS_DIR = FIXTURES_DIR / "sample_composed_reports"
BASELINE_PATH = FIXTURES_DIR / "baseline_v4_5_7.json"


# ─── Fixture 로더 ───────────────────────────────────────────────────────


def load_golden_prompts() -> list[dict[str, Any]]:
    """fixtures/golden_prompts.yaml 의 prompts 배열을 dict 로 반환."""
    with GOLDEN_PROMPTS_PATH.open(encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    return list(data.get("prompts", []))


def load_distribution() -> dict[str, int]:
    """fixtures/golden_prompts.yaml 의 distribution 섹션 (8개 카테고리 분포)."""
    with GOLDEN_PROMPTS_PATH.open(encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    return dict(data.get("distribution", {}))


def load_sample_composed_report(prompt_id: str) -> dict[str, Any] | None:
    """sample_composed_reports/<id>.json 이 있으면 dict 로 반환, 없으면 None.

    Phase 0B 시점엔 sample 이 없을 수 있다 (실제 v4.5.7 baseline 은 사용자가
    record_baseline.py 로 채운다). 없을 때 graceful 하게 None.
    """
    path = SAMPLE_REPORTS_DIR / f"{prompt_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_baseline() -> dict[str, Any]:
    """baseline_v4_5_7.json 을 로드. 없으면 빈 stub 반환.

    baseline 파일은 사용자가 ``scripts/record_baseline.py`` 를 실행할 때
    생성된다. Phase 0B 시점엔 stub 이 ``recorded: false`` 로 들어 있어
    회귀 테스트가 *형태만* 검증하고 통과한다.
    """
    if not BASELINE_PATH.exists():
        return {"recorded": False, "version": "v4.5.7", "results": {}}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


# ─── 결과 자료구조 (5종 회귀 테스트 공통) ────────────────────────────────


@dataclass
class RegressionResult:
    """회귀 테스트 1건의 결과. test runner 가 누적해 baseline 과 비교."""

    test_name: str
    prompt_id: str
    passed: bool
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


# ─── ComposedReport 검증 유틸 (Plan §3.4 가/마 기반) ──────────────────────


def total_prose_chars(composed: dict[str, Any]) -> int:
    """composed_report.sections[*].prose 의 자수 합산. 절단 검출의 핵심 지표."""
    sections = composed.get("sections", []) or []
    return sum(len((s or {}).get("prose") or "") for s in sections)


def section_count(composed: dict[str, Any]) -> int:
    return len(composed.get("sections", []) or [])


def collect_chart_types(composed: dict[str, Any]) -> set[str]:
    """모든 섹션의 charts[*].type 을 set 으로. forbidden_chart_types 검증용."""
    types: set[str] = set()
    for sec in composed.get("sections", []) or []:
        for chart in (sec or {}).get("charts", []) or []:
            t = (chart or {}).get("type")
            if isinstance(t, str):
                types.add(t)
    return types


def has_embedded_map(composed: dict[str, Any]) -> bool:
    m = composed.get("embedded_map")
    return bool(m) and isinstance(m, dict)


def collect_geo_legend_labels(composed: dict[str, Any]) -> set[str]:
    """embedded_map.legend[*].label 을 set 으로. forbidden_geo_annotations 검증용 (CHART-AP-14)."""
    labels: set[str] = set()
    m = composed.get("embedded_map") or {}
    for entry in (m.get("legend") or []):
        label = (entry or {}).get("label")
        if isinstance(label, str):
            labels.add(label)
    return labels


# ─── Phase 0C 의 절단 검출 (Plan §6.4 — Phase 5 절단 회귀 해결의 1차 가드) ──
#
# 본 함수는 Phase 0B 에서 Completeness Regression 의 핵심 검증 함수로 *먼저*
# 구현해두고, V5 Phase 5 가 본격 도입될 때 ``src/`` 로 이전될 *예비 SSOT* 다.

# Plan §6.4 의 MODE_TARGET_CHARS_LOWER 와 동일.
MODE_TARGET_CHARS_LOWER = {
    "fast": 1500,
    "standard": 3500,
    "deep": 6000,
}


def detect_truncation(
    composed: dict[str, Any] | None,
    mode: str,
    raw_response: str = "",
) -> dict[str, Any]:
    """composer 출력의 절단 여부를 결정적 (LLM 0) 규칙으로 판정.

    Plan §6.4 의 5가지 시그널을 모두 검사:
      1. JSON 파싱 실패 → composed is None
      2. 마지막 섹션 prose 가 문장부호 없이 끝남
      3. closing 필드가 비어있음 (epilogue 작성 전 끊김)
      4. deep 모드에서 watch_signals / contradictions 비어있음
      5. 총 분량이 mode 별 하한의 70% 미만

    Returns:
        {"truncated": bool, "reason": str, "issues": [str], "raw_tail": str | None}
    """
    issues: list[str] = []

    # 1. JSON 파싱 실패는 가장 명확한 절단 신호.
    if composed is None:
        return {
            "truncated": True,
            "reason": "json_parse_failed",
            "issues": ["json_parse_failed"],
            "raw_tail": raw_response[-500:] if raw_response else None,
        }

    # 2. 마지막 섹션의 prose 가 문장 부호 없이 끝나면 잘렸다고 판정.
    sections = composed.get("sections", []) or []
    if sections:
        last_prose = ((sections[-1] or {}).get("prose") or "").rstrip()
        if last_prose and last_prose[-1] not in ".!?。·":
            issues.append("last_section_unfinished")

    # 3. closing 필드가 비어 있으면 epilogue 작성 전에 끊겼다.
    if not (composed.get("closing") or "").strip():
        issues.append("closing_missing")

    # 4. deep 모드에서 watch_signals 또는 contradictions 가 비어 있으면 절단 가능성.
    if mode == "deep":
        if not composed.get("watch_signals"):
            issues.append("watch_signals_missing_in_deep")
        if not composed.get("contradictions"):
            issues.append("contradictions_missing_in_deep")

    # 5. 총 분량이 mode 별 하한의 70% 미만이면 부족.
    target_total = MODE_TARGET_CHARS_LOWER.get(mode, 3500)
    actual_total = total_prose_chars(composed)
    if actual_total < target_total * 0.7:
        issues.append(f"underweight_{actual_total}_vs_{int(target_total * 0.7)}")

    return {
        "truncated": bool(issues),
        "reason": "; ".join(issues) if issues else "",
        "issues": issues,
        "raw_tail": None,
    }


# ─── Mode 결정 휴리스틱 (orchestrator.resolve_mode 와 *동일 결과* 기대) ──────
#
# 회귀 테스트가 src.token_budget.resolve_mode 를 import 할 수 없는 환경에서도
# fallback 으로 동작하도록 사본을 둔다. 두 함수 결과가 다르면 그 자체가 회귀.

_FAST_KEYWORDS = {
    "짧게", "간략히", "간략하게", "빠르게", "요약",
    "간단히", "간단하게", "fast",
}
_DEEP_KEYWORDS = {
    "심층", "깊게", "자세히", "정밀", "면밀",
    "상세하게", "deep",
}


def resolve_mode_fallback(prompt: str) -> str:
    """orchestrator 의 mode 결정 규칙을 fixture-friendly 하게 재현.

    v5.8.2: 기본 폴백 standard → deep (token_budget.resolve_mode 와 동일). 두 함수
    결과가 다르면 그 자체가 회귀.
    """
    has_deep = any(k in prompt for k in _DEEP_KEYWORDS)
    has_fast = any(k in prompt for k in _FAST_KEYWORDS)
    if has_deep:
        return "deep"
    if has_fast:
        return "fast"
    return "deep"


# ─── Semantic regression — 결정적 휴리스틱 (Plan §3.4 다) ────────────────


def headline_body_match_score(composed: dict[str, Any]) -> float:
    """headline / deck 의 명사·키워드가 본문 prose 에 등장하는 비율.

    가벼운 휴리스틱 — 한국어 토큰화는 공백+구두점 분리. 0.0~1.0 점.
    DeskEditor (Phase 7) 의 LLM 검수가 본격적으로 잡지만, Phase 0B 에선
    *최저선만 잡는* 사후 가드.
    """
    headline = (composed.get("headline") or "") + " " + (composed.get("deck") or "")
    body = " ".join(
        ((s or {}).get("prose") or "") for s in (composed.get("sections") or [])
    )
    tokens = {t for t in _tokenize(headline) if len(t) >= 2}
    if not tokens:
        return 0.0
    body_tokens = set(_tokenize(body))
    matched = sum(1 for t in tokens if t in body_tokens)
    return matched / len(tokens)


def deck_conclusion_alignment(composed: dict[str, Any]) -> float:
    """deck 과 마지막 섹션 prose / closing 의 어휘 중첩.

    deck 은 결론을 미리 보여준다. closing / 마지막 섹션이 *그 결론과 어휘적으로*
    가까워야 일관성. 0.0~1.0 점.
    """
    deck = composed.get("deck") or ""
    sections = composed.get("sections") or []
    last_prose = (sections[-1] or {}).get("prose", "") if sections else ""
    closing = composed.get("closing") or ""
    tail = last_prose + " " + closing
    deck_tokens = {t for t in _tokenize(deck) if len(t) >= 2}
    if not deck_tokens:
        return 0.0
    tail_tokens = set(_tokenize(tail))
    matched = sum(1 for t in deck_tokens if t in tail_tokens)
    return matched / len(deck_tokens)


def watch_signal_actionability(composed: dict[str, Any]) -> float:
    """watch_signals 가 *예측 가치* 있는지 0.0~1.0 점.

    direction 이 ambiguous 만 있는 경우 0. confirms_base / rejects_base 가
    포함되면 그 비율로 점수.
    """
    signals = composed.get("watch_signals") or []
    if not signals:
        return 0.0
    actionable = 0
    for s in signals:
        d = (s or {}).get("direction") or ""
        if d in {"confirms_base", "rejects_base"}:
            actionable += 1
    return actionable / len(signals)


def contradiction_preservation_check(composed: dict[str, Any]) -> bool:
    """contradictions 필드 형식 + 봉합 금지 정책 (Anti-pattern #5) 미니 가드.

    각 contradiction 이 ``{side_a, side_b, ...}`` 형태이고, side_a / side_b 가
    *서로 다른* 텍스트인지만 검사. resolution 이 두 입장을 모두 채택하는
    문구는 별도 LLM Critic 영역.
    """
    cons = composed.get("contradictions") or []
    for c in cons:
        if not isinstance(c, dict):
            return False
        a = (c.get("side_a") or "").strip()
        b = (c.get("side_b") or "").strip()
        if not a or not b or a == b:
            return False
    return True


# ─── 토큰화 유틸 ────────────────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """공백 + 구두점 단순 분리. 한국어 형태소 분석 X (휴리스틱)."""
    if not text:
        return []
    out: list[str] = []
    buf = ""
    for ch in text:
        if ch.isalnum() or 0xAC00 <= ord(ch) <= 0xD7A3 or ch in "_-":
            buf += ch
        else:
            if buf:
                out.append(buf)
                buf = ""
    if buf:
        out.append(buf)
    return out
