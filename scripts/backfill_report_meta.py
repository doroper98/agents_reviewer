#!/usr/bin/env python3
"""backfill_report_meta.py — v5.8.5

옛 보고서의 ``report_meta`` 백필 — LLM 호출 0, 저장된 JSON 만으로 복원.

[배경]
v5.4.9~v5.5.6 구간(또는 v5.5.7 이전)의 ``MAX_CHAIN_DEPTH=0`` 가드 +
``result.composed_report.scenarios`` AttributeError silent 사이드이펙트로,
그 시기에 생성된 보고서들은 HTML·감시신호는 정상이지만 ``report_meta``
(부모 맥락 메타) 등록이 누락됐다. 그 결과 [▶ 후속 보고 생성] 버튼을 누르면
``_activate_followup`` 이 메타를 못 찾아 "후속 분석 불가" 로 중단된다
(telegram_bot.py:493).

본 스크립트는 ``reports/analysis_*.json`` (FullAnalysisResult.model_dump) 에
이미 저장된 필드만 꺼내 ``register_report_meta`` 로 백필한다. 보고서 내용을
재분석하지 않는다 — orchestrator.py:1716 과 *동일한* 추출 경로:
  - event_description ← request.event_description
  - report_title     ← composed_report.headline   (v5.8.0)
  - scenarios        ← scenarios.scenarios (없으면 [])

[사용]
  python scripts/backfill_report_meta.py
      dry-run (기본) — 메타 누락된 보고서 목록 + 백필 예정 건수만 출력. DB 무변경.

  python scripts/backfill_report_meta.py --apply
      실제 백필. report_meta 에 *없는* 보고서만 등록 (idempotent — 기존 메타
      보존, 여러 번 돌려도 무해).

  python scripts/backfill_report_meta.py --reports-dir reports --db reports/watchlist.db
      경로 override (기본은 config.report_output_dir + watchlist.db).

[주의]
- 기본은 dry-run. ``--apply`` 없이는 DB 를 절대 건드리지 않는다.
- "메타 없는 것만" 백필 — v5.5.7+ 의 정상 등록 메타는 건드리지 않는다.
- JSON 이 없는(v4.4.0 이전) 보고서는 백필 불가 — skip + 사유 출력.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# repo 루트를 path 에 추가 (scripts/ 에서 직접 실행 대응).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config  # noqa: E402
from src.models import FullAnalysisResult  # noqa: E402
from src.watchlist.registry import WatchlistRegistry  # noqa: E402

DEFAULT_WATCHLIST_DB_NAME = "watchlist.db"


def _extract_meta(result: FullAnalysisResult) -> tuple[str, str, list[dict]]:
    """orchestrator.py:1707-1721 과 *동일한* 추출 로직.

    Returns (event_description, report_title, scenarios).
    """
    event_description = ""
    if result.request and result.request.event_description:
        event_description = result.request.event_description

    report_title = ""
    if result.composed_report and result.composed_report.headline:
        report_title = result.composed_report.headline

    scenarios: list[dict] = []
    if result.scenarios is not None and result.scenarios.scenarios:
        scenarios = list(result.scenarios.scenarios)

    return event_description, report_title, scenarios


def main() -> int:
    parser = argparse.ArgumentParser(
        description="옛 보고서의 report_meta 백필 (LLM 0, 저장 JSON 기반).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="실제 백필 적용 (기본은 dry-run — 목록만 출력).",
    )
    parser.add_argument(
        "--reports-dir", default=None,
        help="보고서 JSON 디렉터리 (기본: config.report_output_dir).",
    )
    parser.add_argument(
        "--db", default=None,
        help="watchlist.db 경로 (기본: <reports-dir>/watchlist.db).",
    )
    args = parser.parse_args()

    config = Config()
    reports_dir = args.reports_dir or config.report_output_dir
    db_path = args.db or os.path.join(reports_dir, DEFAULT_WATCHLIST_DB_NAME)

    if not os.path.isdir(reports_dir):
        print(f"[backfill] ✗ 보고서 디렉터리 없음: {reports_dir}")
        return 1
    if not os.path.exists(db_path):
        print(f"[backfill] ✗ watchlist DB 없음: {db_path}")
        print("           봇이 한 번이라도 떠서 DB 를 만든 뒤 실행하세요.")
        return 1

    mode_label = "APPLY" if args.apply else "DRY-RUN"
    print(f"[backfill] mode={mode_label}  reports={reports_dir}  db={db_path}")

    registry = WatchlistRegistry(db_path)

    # analysis_*.json 중 *.bundle.json 은 제외 — ReportBundle (v5.5.0, 다른 스키마)
    # 이라 FullAnalysisResult 로 검증 안 됨. 진짜 보고서는 같은 ts 의 analysis_*.json
    # 으로 따로 존재. glob 패턴으로 못 거르므로 (bundle 도 analysis_ 로 시작) 명시 제외.
    json_paths = sorted(
        p for p in glob.glob(os.path.join(reports_dir, "analysis_*.json"))
        if not p.endswith(".bundle.json")
    )
    if not json_paths:
        print(f"[backfill] analysis_*.json 없음 — 백필 대상 0.")
        return 0

    # 옛 보고서엔 깨진 차트가 있어 로드 시 ComposedSection._drop_invalid_charts 가
    # pydantic 에러 트리를 logger.warning 으로 stderr 에 흘린다 (보고서 로드 자체는
    # 정상 — 위반 차트만 drop). 백필 출력만 보이게 src.models 로거를 ERROR 로 올려
    # 그 노이즈를 잠재운다. 백필 결과엔 영향 없음.
    import logging
    logging.getLogger("src.models").setLevel(logging.ERROR)

    total = len(json_paths)
    already = 0          # 이미 메타 있음 (skip)
    to_backfill = 0      # 메타 없음 → 백필 대상
    backfilled = 0       # 실제 등록 성공
    skipped_bad = 0      # JSON 파싱 실패 / event_description 없음

    for path in json_paths:
        # report_id = 파일명에서 .json 떼기 (analysis_ 접두 포함 — signal 의
        # parent_report_id 와 동일 형식).
        report_id = os.path.splitext(os.path.basename(path))[0]

        existing = registry.get_report_meta(report_id)
        if existing and existing.get("event_description"):
            already += 1
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = FullAnalysisResult.model_validate(data)
        except Exception as e:
            skipped_bad += 1
            print(f"  ✗ skip {report_id}: JSON 로드/검증 실패 ({str(e)[:80]})")
            continue

        event_description, report_title, scenarios = _extract_meta(result)
        if not event_description:
            skipped_bad += 1
            print(f"  ✗ skip {report_id}: event_description 비어있음 (백필 불가)")
            continue

        to_backfill += 1
        title_preview = (report_title or "(제목 없음)")[:40]
        print(f"  • {report_id}  ← \"{title_preview}\"  (시나리오 {len(scenarios)}건)")

        if args.apply:
            ok = registry.register_report_meta(
                report_id=report_id,
                event_description=event_description,
                scenarios=scenarios,
                chain_depth=0,
                report_title=report_title,
            )
            if ok:
                backfilled += 1
            else:
                print(f"    ⚠️ register 실패: {report_id}")

    print("─" * 60)
    print(f"[backfill] 총 {total}건 스캔 — 이미 메타 있음 {already} / "
          f"백필 대상 {to_backfill} / skip {skipped_bad}")
    if args.apply:
        print(f"[backfill] ✓ {backfilled}건 백필 완료. "
              f"이제 해당 보고서의 [▶ 후속 보고 생성] 버튼이 동작합니다.")
    else:
        print(f"[backfill] dry-run — DB 무변경. 실제 적용하려면 --apply 추가.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
