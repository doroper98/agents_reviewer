"""V6 Phase V6-6 — 자율 보강: critique 적립 → 소프트가드 → 승격 후보.

REFACTOR_V6_PLAN.md §3 Phase V6-6. "Codex 가 매번 잡는 패턴이 시스템에 누적돼
스스로 강해진다." 단 **적립↔적용 분리** (AP-V6-9):

  A. 적립 (자동·완전 안전) — 모든 verdict claim 을 ``critique_log.jsonl`` 에 영구
     적립. 코드/프롬프트 무변경.
  B-1. 소프트가드 자동 등재 (near-자율) — 동일 시그니처 재발 ≥임계 → ``soft_guards.yaml``
     에 자동 등재 + 로그. **log-only** — 본문 프롬프트/정규 가드 불변. 오판이어도
     drop 아니라 피해 없음.
  B-2. 정식 승격 (사람 게이트) — 추가 재발 시 *후보 표면화* 만. live 프롬프트/정규
     가드/fixture 편입은 **사람 확인 1줄** 후에만 (자동 편입 금지, byte-equal·오염 방지).

flag ``V6_AUTOLEARN`` default OFF. usage_log.py 와 동일한 JSONL/graceful 패턴.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# 재발 임계 (시그니처가 이만큼 누적되면 소프트가드 자동 등재 / 승격 후보 표면화).
SOFT_GUARD_THRESHOLD = 3      # B-1: 소프트가드 자동 등재
PROMOTION_THRESHOLD = 8       # B-2: 정식 승격 후보 (사람 게이트)
DEFAULT_WINDOW = 200          # 분석 대상 최근 N 적립


def _log_path() -> Path:
    raw = os.environ.get("V6_CRITIQUE_LOG_PATH")
    return Path(raw) if raw else Path("logs") / "critique_log.jsonl"


def _guards_path() -> Path:
    raw = os.environ.get("V6_SOFT_GUARDS_PATH")
    # logs/ 하위 (critique_log.jsonl 와 함께, gitignore — 런타임 적립물). src/factcheck 와 무관.
    return Path(raw) if raw else Path("logs") / "soft_guards.yaml"


def signature(error_class: str, location: str = "") -> str:
    """패턴 시그니처. error_class 가 1차 축 (재발의 actionable 단위)."""
    return (error_class or "unknown").strip()


# --------------------------------------------------------------------------
# A. 적립 (자동·안전)
# --------------------------------------------------------------------------


def append_critique(
    report_id: str, claim_records: list[dict], *, path: Path | None = None,
) -> None:
    """한 보고서의 codex 지적들을 critique_log.jsonl 에 영구 적립 (graceful)."""
    if not claim_records:
        return
    target = path or _log_path()
    today = date.today().isoformat()
    rows = [
        {
            "ts": int(time.time()),
            "date": today,
            "report_id": report_id,
            "error_class": r.get("error_class", "unknown"),
            "location": r.get("location", ""),
            "quote": r.get("quote", ""),
            "signature": signature(r.get("error_class", ""), r.get("location", "")),
        }
        for r in claim_records
    ]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("[critique_log] append fail: %s", exc)


def _read_records(path: Path, window: int) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("[critique_log] read fail: %s", exc)
        return []
    out: list[dict] = []
    for ln in lines[-window:] if window > 0 else lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def analyze_recurring(
    *, window: int = DEFAULT_WINDOW, threshold: int = SOFT_GUARD_THRESHOLD,
    path: Path | None = None,
) -> list[dict]:
    """최근 ``window`` 적립에서 ≥threshold 재발한 시그니처 목록 (count 내림차순)."""
    records = _read_records(path or _log_path(), window)
    counter: Counter[str] = Counter(r.get("signature", "") for r in records if r.get("signature"))
    return [
        {"signature": sig, "count": n}
        for sig, n in counter.most_common()
        if n >= threshold
    ]


# --------------------------------------------------------------------------
# B-1. 소프트가드 자동 등재 (log-only) / B-2. 승격 후보 (사람 게이트)
# --------------------------------------------------------------------------


def load_soft_guards(*, path: Path | None = None) -> list[dict]:
    target = path or _guards_path()
    if not target.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        return list(data.get("soft_guards", []))
    except Exception as exc:  # noqa: BLE001 — yaml 없거나 깨져도 graceful
        logger.warning("[soft_guards] load fail: %s", exc)
        return []


def auto_register_soft_guards(
    *, window: int = DEFAULT_WINDOW, threshold: int = SOFT_GUARD_THRESHOLD,
    log_path: Path | None = None, guards_path: Path | None = None,
) -> list[str]:
    """재발 ≥threshold 시그니처를 soft_guards.yaml 에 자동 등재. 신규 등재분 반환.

    **log-only** — 등재는 시그니처를 *기록* 할 뿐 본문/프롬프트/정규가드를 바꾸지 않는다
    (AP-V6-9). 정식 편입은 사람 게이트(promotion_candidates → 수동).
    """
    recurring = analyze_recurring(window=window, threshold=threshold, path=log_path)
    if not recurring:
        return []
    target = guards_path or _guards_path()
    existing = {g.get("signature") for g in load_soft_guards(path=target)}
    new_guards = [r for r in recurring if r["signature"] not in existing]
    if not new_guards:
        return []
    try:
        import yaml
        current = load_soft_guards(path=target)
        today = date.today().isoformat()
        for r in new_guards:
            current.append({
                "signature": r["signature"],
                "first_registered": today,
                "count_at_register": r["count"],
                "mode": "log_only",  # AP-V6-9 — 정규 가드 아님
            })
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(
                {"soft_guards": current}, allow_unicode=True, sort_keys=False,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[soft_guards] auto-register fail: %s", exc)
        return []
    return [r["signature"] for r in new_guards]


def promotion_candidates(
    *, window: int = DEFAULT_WINDOW, threshold: int = PROMOTION_THRESHOLD,
    path: Path | None = None,
) -> list[dict]:
    """정식 승격 후보 (재발 ≥PROMOTION_THRESHOLD) — *표면화만*, 편입은 사람 게이트."""
    return analyze_recurring(window=window, threshold=threshold, path=path)
