#!/usr/bin/env python3
"""V5 Phase 0B — Regression test runner (pytest 미설치 환경 호환).

REFACTOR_V5_PLAN.md §3 Phase 0B 의 5종 회귀 테스트를 한 번에 실행한다.
pytest 가 설치되어 있으면 그쪽으로 위임 (``python -m pytest tests/regression``)
하는 것이 우선이지만, pytest 미설치 / CI 단순화 / 빠른 피드백 용으로 본
runner 를 제공한다.

사용:
    python scripts/run_regression.py                  # 5종 모두 실행
    python scripts/run_regression.py --tests golden,completeness
    python scripts/run_regression.py --json out.json  # 결과를 JSON 으로 저장
    python scripts/run_regression.py --report-dir ./reports/v5_run_a
        # visual_regression 시 reports/v5_run_a/<id>.html 을 입력으로 사용
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# tests.regression 을 import 가능하게 — repo root 를 sys.path 에 추가.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.regression.helpers import RegressionResult  # noqa: E402


def _lazy_import(module_path: str):
    """테스트 모듈을 *호출 시점* 에 import — pydantic 등 의존성 미설치 환경에서
    sandbox graceful degrade. 실패 시 None 반환."""
    try:
        import importlib
        return importlib.import_module(module_path)
    except Exception as e:
        print(f"  [skip] {module_path} import failed: {e}")
        return None


def _run_module(module_path: str, *args) -> list[RegressionResult]:
    mod = _lazy_import(module_path)
    if mod is None:
        return []
    if not hasattr(mod, "run_all"):
        # unit-style test 모듈 (test_evidence_dataset 등) — pytest 직접 호출.
        print(f"  [info] {module_path} has no run_all(); use 'pytest {module_path.replace('.', '/')}.py'")
        return []
    return mod.run_all(*args)


# 테스트 라벨 → 모듈 경로. lazy import 라 sandbox 에서도 다른 테스트가 SKIP 만 발생.
_TEST_MODULES = {
    "golden":       "tests.regression.test_golden_prompts",
    "visual":       "tests.regression.test_visual_regression",
    "semantic":     "tests.regression.test_semantic_regression",
    "cost":         "tests.regression.test_cost_regression",
    "completeness": "tests.regression.test_completeness_regression",
    # V5 Phase 1A — ResearchDirector / Method Router (Plan §6.6 #4 ≥80% 일치).
    "director":     "tests.regression.test_research_director",
    # V5 Phase 2A — EvidenceDataset Contract (Plan §8.7 #1~#4 / AP-V5-24/25/26).
    "dataset":      "tests.regression.test_evidence_dataset",
    # V5 Phase 2 — Visualization Decoupling (Plan §7.8 #4·#5 / Vega-Lite + design token).
    "phase2vega":   "tests.regression.test_phase2_vega",
    # V5 Phase 2B — Capability Registry (Plan §9.5 / AP-V5-27).
    "registry":     "tests.regression.test_capability_registry",
    # V5 Phase 6 — Chart Correctness Gate (Plan §13 4중 게이트).
    "chartgate":    "tests.regression.test_chart_correctness",
    # V5 Phase 6A — Exhibit Priority Policy (Plan §14 / AP-V5-28).
    "priority":     "tests.regression.test_exhibit_priority",
    # V5 Phase 7A — Deterministic Publish Gate (Plan §15 / AP-V5-29).
    "detgate":      "tests.regression.test_deterministic_gate",
    # V5 Phase 7 — Desk Editor (Plan §16 / AP-V5-11/12/13/14/15/16).
    "desk":         "tests.regression.test_desk_editor",
    # V5 Phase 8 + 8A — Strategic Mode (Plan §17 + §18 / AP-V5-18~23).
    "strategic":    "tests.regression.test_strategic_mode",
    # V5 Phase 1 — Editor Pass (Plan §5 / AP-V5-1).
    "editor":       "tests.regression.test_editor",
    # V5 Phase 3 — Layout Primitives (Plan §10 / AP-V5-3).
    "layout":       "tests.regression.test_layout_typesetter",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V5 Phase 0B regression runner")
    parser.add_argument(
        "--tests",
        default="golden,director,dataset,phase2vega,registry,chartgate,priority,detgate,desk,strategic,editor,layout,visual,semantic,cost,completeness",
        help=(
            "콤마 구분 테스트 목록. 기본: 5종 + V5 Phase 1A (director) + "
            "V5 Phase 2A (dataset) + V5 Phase 2 (phase2vega) + "
            "V5 Phase 2B (registry) + V5 Phase 6 (chartgate) + "
            "V5 Phase 6A (priority) + V5 Phase 7A (detgate) + "
            "V5 Phase 7 (desk) 13종 모두."
        ),
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="결과를 JSON 파일로 저장",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="visual_regression 시 입력 HTML 디렉토리 (Phase 0B 시점 SKIP 가능)",
    )
    parser.add_argument(
        "--telemetry",
        type=Path,
        default=None,
        help=(
            "cost_regression 입력 — telemetry JSON 파일. "
            "{'<prompt_id>': {total_input_tokens, total_output_tokens, llm_call_count, total_elapsed_seconds}, ...}"
        ),
    )
    args = parser.parse_args(argv)

    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = set(selected) - set(_TEST_MODULES)
    if unknown:
        parser.error(f"unknown tests: {sorted(unknown)}")

    all_results: list[RegressionResult] = []

    for name in selected:
        print(f"\n=== {name} ===")
        module_path = _TEST_MODULES[name]
        if name == "visual":
            mod = _lazy_import(module_path)
            results = mod.run_all(args.report_dir) if mod else []
        elif name == "cost":
            telemetry_by_id = {}
            if args.telemetry and args.telemetry.exists():
                telemetry_by_id = json.loads(args.telemetry.read_text(encoding="utf-8"))
            mod = _lazy_import(module_path)
            results = mod.run_all(telemetry_by_id) if mod else []
        else:
            results = _run_module(module_path)
        all_results.extend(results)
        _print_summary(name, results)

    # 종합 요약
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    by_test: dict[str, dict[str, int]] = {}
    for r in all_results:
        bucket = by_test.setdefault(r.test_name, {"pass": 0, "fail": 0, "skip": 0})
        if not r.passed:
            bucket["fail"] += 1
        elif r.metrics.get("sample_missing") or r.metrics.get("status", "").startswith("skipped"):
            bucket["skip"] += 1
        else:
            bucket["pass"] += 1
    total_fail = 0
    for test_name, b in by_test.items():
        print(f"  {test_name:30s} pass={b['pass']:3d}  fail={b['fail']:3d}  skip={b['skip']:3d}")
        total_fail += b["fail"]

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps([asdict(r) for r in all_results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON results saved to: {args.json}")

    return 0 if total_fail == 0 else 1


def _print_summary(name: str, results: list[RegressionResult]) -> None:
    if not results:
        print("  (no results)")
        return
    failed = [r for r in results if not r.passed]
    skipped = [
        r for r in results
        if r.passed and (r.metrics.get("sample_missing") or r.metrics.get("status", "").startswith("skipped"))
    ]
    passed = [r for r in results if r not in failed and r not in skipped]
    print(f"  total={len(results)}, pass={len(passed)}, fail={len(failed)}, skip={len(skipped)}")
    for r in failed:
        print(f"  ✗ {r.prompt_id}: {'; '.join(r.issues)}")


if __name__ == "__main__":
    raise SystemExit(main())
