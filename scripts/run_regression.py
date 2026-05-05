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

from tests.regression import (  # noqa: E402
    test_completeness_regression as test_completeness,
    test_cost_regression as test_cost,
    test_golden_prompts as test_golden,
    test_semantic_regression as test_semantic,
    test_visual_regression as test_visual,
)
from tests.regression.helpers import RegressionResult  # noqa: E402


TEST_REGISTRY = {
    "golden": test_golden.run_all,
    "visual": None,           # 별도 처리 (report_dir 인자 필요)
    "semantic": test_semantic.run_all,
    "cost": test_cost.run_all,
    "completeness": test_completeness.run_all,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V5 Phase 0B regression runner")
    parser.add_argument(
        "--tests",
        default="golden,visual,semantic,cost,completeness",
        help="콤마 구분 테스트 목록. 기본: 5종 모두",
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
    unknown = set(selected) - set(TEST_REGISTRY)
    if unknown:
        parser.error(f"unknown tests: {sorted(unknown)}")

    all_results: list[RegressionResult] = []

    for name in selected:
        print(f"\n=== {name} ===")
        if name == "visual":
            results = test_visual.run_all(args.report_dir)
        elif name == "cost":
            telemetry_by_id = {}
            if args.telemetry and args.telemetry.exists():
                telemetry_by_id = json.loads(args.telemetry.read_text(encoding="utf-8"))
            results = test_cost.run_all(telemetry_by_id)
        else:
            runner = TEST_REGISTRY[name]
            assert runner is not None
            results = runner()
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
