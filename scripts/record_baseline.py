#!/usr/bin/env python3
"""V5 Phase 0B — v4.5.7 baseline recording script.

REFACTOR_V5_PLAN.md §3.5 의 인수 기준 #3 ("v4.5.x baseline 의 회귀 테스트
통과율이 측정되어 박혀 있어야 한다") 를 충족하기 위해, *실제 v4.5.7 환경*
(Anthropic API 키 또는 Claude Code CLI 가용) 에서 본 스크립트를 1회 실행하면
다음을 박는다.

  1. tests/regression/fixtures/sample_composed_reports/<id>.json
       — 각 Golden Prompt 의 실제 ComposedReport 출력
  2. tests/regression/fixtures/baseline_v4_5_7.json
       — 측정 메트릭 (total_tokens / llm_call_count / elapsed_seconds /
         truncation_detected / per-test pass/fail)

본 스크립트는 *실제 LLM 호출* 을 일으키므로 비용 발생. 1회 baseline 박은 후엔
재실행 불필요. V5 의 각 Phase 진입 전 회귀 테스트의 *비교 기준점* 으로 사용.

사용:
    python scripts/record_baseline.py                       # 20개 모두
    python scripts/record_baseline.py --only geo_forecast_01,fin_transmission_01
    python scripts/record_baseline.py --dry-run             # 호출 없이 형식만 검증

주의:
    src.orchestrator 와 src.config 를 import 하므로 .env 가 설정되어
    있어야 한다 (ANTHROPIC_API_KEY 또는 Claude Code CLI 가용).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.regression.helpers import (  # noqa: E402
    BASELINE_PATH,
    SAMPLE_REPORTS_DIR,
    load_golden_prompts,
)

logger = logging.getLogger(__name__)


def _to_dict(model: Any) -> dict[str, Any]:
    """Pydantic 모델 또는 dict 를 JSON-serializable dict 로."""
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if isinstance(model, dict):
        return model
    return dict(model)


async def record_one(orchestrator: Any, entry: dict[str, Any]) -> dict[str, Any]:
    """1 prompt 실행 → sample 저장 + cost 메트릭 반환."""
    pid = entry["id"]
    prompt = entry["prompt"]
    expected_mode = entry["expected"]["mode"]

    SAMPLE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    start = time.time()
    result = await orchestrator.run_analysis(
        event_description=prompt,
        chat_id=0,
        status_callback=None,
        mode=expected_mode,
    )
    elapsed = time.time() - start

    # composed_report 만 sample 로 저장 (테스트가 입력으로 받는 형식).
    composed = _to_dict(getattr(result, "composed_report", None))
    sample_path = SAMPLE_REPORTS_DIR / f"{pid}.json"
    sample_path.write_text(
        json.dumps(composed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # telemetry 메트릭 수집.
    telemetry = getattr(orchestrator, "telemetry", None)
    metrics: dict[str, Any] = {
        "total_elapsed_seconds": round(elapsed, 2),
        "llm_call_count": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "system_version": getattr(result, "system_version", "") or "",
        "revision": getattr(result, "revision", 0),
    }
    if telemetry is not None:
        # RunTelemetry 의 export_dict / fields 가능한 항목 — 안전 access.
        for attr, key in [
            ("total_input_tokens", "total_input_tokens"),
            ("total_output_tokens", "total_output_tokens"),
            ("llm_call_count", "llm_call_count"),
        ]:
            val = getattr(telemetry, attr, None)
            if val is not None:
                metrics[key] = val
    metrics["total_tokens"] = (
        metrics["total_input_tokens"] + metrics["total_output_tokens"]
    )
    return metrics


async def amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="v4.5.7 baseline recorder for V5 Phase 0B regression harness"
    )
    parser.add_argument(
        "--only",
        default=None,
        help="콤마 구분 prompt id 목록 (예: geo_forecast_01,fin_transmission_01)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="LLM 호출 없이 형식만 검증",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )

    prompts = load_golden_prompts()
    if args.only:
        wanted = {p.strip() for p in args.only.split(",")}
        prompts = [p for p in prompts if p["id"] in wanted]
        if not prompts:
            print(f"no prompts matched --only={args.only}")
            return 1

    if args.dry_run:
        print(f"[dry-run] {len(prompts)} prompts to record")
        for p in prompts:
            print(f"  - {p['id']:30s} mode={p['expected']['mode']:8s} prompt={p['prompt'][:50]!r}")
        return 0

    # src.orchestrator 는 .env / config 가 갖춰진 환경에서만 동작.
    try:
        from src.config import Config
        from src.orchestrator import Orchestrator, VERSION
    except ImportError as e:
        print(f"src import failed — .env 와 의존성을 확인하세요: {e}")
        return 2

    config = Config()
    orchestrator = Orchestrator(config)

    if VERSION != "v4.5.7":
        print(f"WARNING: orchestrator.VERSION={VERSION}, but Phase 0B baseline 은 v4.5.7 가정.")

    results: dict[str, Any] = {}
    for entry in prompts:
        pid = entry["id"]
        print(f"\n[{pid}] mode={entry['expected']['mode']} — recording...")
        try:
            metrics = await record_one(orchestrator, entry)
            results[pid] = metrics
            print(f"  ✓ {metrics}")
        except Exception as e:  # pragma: no cover  — 실 환경에서만 발생
            logger.exception("[%s] failed", pid)
            results[pid] = {"error": str(e)}

    # baseline 갱신
    baseline = {
        "_comment": "v4.5.7 baseline 측정 결과. Phase 0B 회귀 테스트 비교 기준.",
        "_spec": "REFACTOR_V5_PLAN.md §3 (Phase 0B) — 인수 기준 #3.",
        "recorded": True,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "version": "v4.5.7",
        "system_version_actual": VERSION,
        "results": results,
    }
    BASELINE_PATH.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nbaseline saved: {BASELINE_PATH}")
    print(f"sample reports saved: {SAMPLE_REPORTS_DIR}")
    return 0


def main() -> int:  # noqa: D401  — entry point wrapper
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
