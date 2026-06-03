"""V6 Phase V6-6 — 자율 보강 (critique 적립 → 소프트가드 → 승격) 회귀.

REFACTOR_V6_PLAN.md §3 Phase V6-6 + AP-V6-9 (적립↔적용 분리). 적립은 자동,
소프트가드는 log-only 자동등재, 정식 승격은 사람 게이트(표면화만).
"""

from __future__ import annotations

from pathlib import Path

from src.factcheck import critique_log as cl


def _records(error_class: str, n: int) -> None:
    pass  # helper placeholder (unused)


def test_signature_is_error_class() -> None:
    assert cl.signature("unsourced_number", "발표 요지") == "unsourced_number"
    assert cl.signature("") == "unknown"


def test_append_and_analyze_recurring(tmp_path: Path) -> None:
    log = tmp_path / "critique_log.jsonl"
    # unsourced 3회, causal 1회 적립.
    for i in range(3):
        cl.append_critique(f"r{i}", [{"error_class": "unsourced_number", "location": "s", "quote": "27년 만"}], path=log)
    cl.append_critique("rc", [{"error_class": "causal_overreach", "location": "s", "quote": "직격탄"}], path=log)
    rec = cl.analyze_recurring(threshold=3, path=log)
    sigs = {r["signature"]: r["count"] for r in rec}
    assert sigs.get("unsourced_number") == 3
    assert "causal_overreach" not in sigs  # threshold 3 미만


def test_append_empty_is_noop(tmp_path: Path) -> None:
    log = tmp_path / "critique_log.jsonl"
    cl.append_critique("r", [], path=log)
    assert not log.exists()


def test_analyze_missing_file_graceful(tmp_path: Path) -> None:
    assert cl.analyze_recurring(path=tmp_path / "nope.jsonl") == []


def test_auto_register_soft_guards(tmp_path: Path) -> None:
    log = tmp_path / "critique_log.jsonl"
    guards = tmp_path / "soft_guards.yaml"
    for i in range(3):
        cl.append_critique(f"r{i}", [{"error_class": "market_data_mismatch", "location": "s", "quote": "코스피"}], path=log)
    newly = cl.auto_register_soft_guards(threshold=3, log_path=log, guards_path=guards)
    assert "market_data_mismatch" in newly
    loaded = cl.load_soft_guards(path=guards)
    g = next(x for x in loaded if x["signature"] == "market_data_mismatch")
    assert g["mode"] == "log_only"  # AP-V6-9 — 정규 가드 아님
    # 재실행 idempotent — 이미 등재된 건 다시 안 넣음.
    again = cl.auto_register_soft_guards(threshold=3, log_path=log, guards_path=guards)
    assert again == []


def test_promotion_candidates_higher_threshold(tmp_path: Path) -> None:
    log = tmp_path / "critique_log.jsonl"
    # 3회만 → 소프트가드는 되지만 승격 후보(8)는 아님.
    for i in range(3):
        cl.append_critique(f"r{i}", [{"error_class": "scope_misattribution", "location": "s", "quote": "보드"}], path=log)
    assert cl.analyze_recurring(threshold=3, path=log)  # 소프트가드 임계 통과
    assert cl.promotion_candidates(threshold=8, path=log) == []  # 승격 임계 미달
    # 8회 채우면 승격 후보로 표면화 (단 자동 편입은 안 함 — 사람 게이트).
    for i in range(3, 8):
        cl.append_critique(f"r{i}", [{"error_class": "scope_misattribution", "location": "s", "quote": "보드"}], path=log)
    cands = cl.promotion_candidates(threshold=8, path=log)
    assert any(c["signature"] == "scope_misattribution" for c in cands)
