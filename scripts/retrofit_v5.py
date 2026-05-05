#!/usr/bin/env python3
"""V5 Retrofit MVP — 기존 v4.5.7 보고서를 V5 게이트로 dry-run 진단.

기존 ``reports/<id>.html`` 을 *읽기만* 하고 V5 의 결정적 게이트
(Phase 5 truncation / Phase 6 chart count / Phase 7A Hard fail 일부) 를
적용해서 "v4.5.7 시절에 V5 게이트가 있었다면 어떻게 판정했을지" 를
CSV 로 출력한다.

사용:
    python scripts/retrofit_v5.py
    python scripts/retrofit_v5.py --reports-dir /path/to/reports
    python scripts/retrofit_v5.py --csv reports/v5_diagnosis.csv

설계 원칙 (Plan §0.3 + AP-V5-32):
- read-only — 보고서 HTML 을 절대 수정하지 않음.
- 결정적 — LLM 호출 0. 휴리스틱 + 정규식 + 카운트만.
- v4.5.7 보고서엔 V5 마커 (`[[ex:N]]`, EvidenceDataset 등) 가 *없음*.
  retrofit 은 *수정* 이 아닌 *측정* — V5 가 어디서 KILL/HOLD 했을지 진단.

출력 컬럼:
    report_id, total_chars, last_char, ends_with_punct, chart_count,
    map_count, truncation_suspected, deterministic_hard_fail_count,
    estimated_v5_decision (publish / hold / kill)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Plan §15.4 의 Hard fail 중 *결정적으로 측정 가능한* 부분만.
# (LLM 호출이 필요한 항목 — narrative_contradiction 등 — 은 제외).
HARD_FAIL_RULES_DETERMINISTIC = [
    "total_chars_below_lower_bound",  # mode lower bound 미달
    "no_closing",                     # closing 누락
    "ends_without_punctuation",        # 마지막 prose 가 문장부호 없음
    "exhibit_ref_broken",              # [[ex:N]] 미해결 잔존
    "chart_count_exceeds_limit",       # mode 별 chart 상한 초과
    "placeholder_unresolved",          # TODO / [FILL_IN] 잔존
]

# Phase 5 의 truncation signal 중 결정적으로 측정 가능한 것.
TRUNCATION_SIGNALS = [
    "ends_without_punctuation",
    "total_chars_below_70_percent_of_lower",
    "trailing_ellipsis_or_dash",
    "html_unclosed_tag",
]

# Plan §12.3 — mode 별 lower bound (helpers.py 와 byte-equal).
MODE_TARGET_CHARS_LOWER = {"fast": 1500, "standard": 3500, "deep": 6000}

# Plan §15.4 — mode 별 chart 상한.
MODE_CHART_LIMIT = {"fast": 2, "standard": 4, "deep": 6}

PUNCTUATION_TAIL = re.compile(r'[.!?。？！\)\]"\'”’]\s*$')
PLACEHOLDER_PATTERN = re.compile(r"(TODO|\[FILL_IN\]|\{\{[^}]+\}\}|\[\[ex(?:r)?:\s*\d+\s*\]\])")
EXHIBIT_REF_PATTERN = re.compile(r"\[\[(ex|exr|exs):[^\]]*\]\]")
CHART_PAYLOAD_PATTERN = re.compile(r'<script[^>]+id="chart-payload-[^"]+"[^>]*>')
MAP_PAYLOAD_PATTERN = re.compile(r'<script[^>]+id="map-payload"[^>]*>')
PROSE_TAG_PATTERN = re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL)


@dataclass
class RetrofitDiagnosis:
    report_id: str
    file_path: str
    total_chars: int
    last_char: str
    ends_with_punct: bool
    chart_count: int
    map_count: int
    truncation_suspected: bool
    truncation_signals: list[str]
    hard_fail_signals: list[str]
    estimated_decision: str  # publish / hold / kill

    @property
    def hard_fail_count(self) -> int:
        return len(self.hard_fail_signals)


def _detect_mode_from_html(html: str) -> str:
    m = re.search(r"data-mode=['\"](\w+)['\"]", html)
    if m and m.group(1) in MODE_TARGET_CHARS_LOWER:
        return m.group(1)
    if "deep" in html[:5000].lower():
        return "deep"
    if "fast" in html[:5000].lower() or "summary" in html[:5000].lower():
        return "fast"
    return "standard"


def _extract_prose_text(html: str) -> str:
    paragraphs = PROSE_TAG_PATTERN.findall(html)
    text = " ".join(re.sub(r"<[^>]+>", "", p) for p in paragraphs)
    return re.sub(r"\s+", " ", text).strip()


def _check_html_unclosed(html: str) -> bool:
    if not html.rstrip().endswith("</html>") and not html.rstrip().endswith("</body>"):
        return True
    return False


def diagnose_report(report_path: Path) -> RetrofitDiagnosis:
    html = report_path.read_text(encoding="utf-8", errors="replace")
    mode = _detect_mode_from_html(html)
    prose = _extract_prose_text(html)
    total_chars = len(prose)
    last_char = prose[-1] if prose else ""
    ends_with_punct = bool(PUNCTUATION_TAIL.search(prose)) if prose else False

    chart_count = len(CHART_PAYLOAD_PATTERN.findall(html))
    map_count = len(MAP_PAYLOAD_PATTERN.findall(html))

    lower_bound = MODE_TARGET_CHARS_LOWER[mode]
    chart_limit = MODE_CHART_LIMIT[mode]

    truncation_signals: list[str] = []
    if not ends_with_punct:
        truncation_signals.append("ends_without_punctuation")
    if total_chars < lower_bound * 0.7:
        truncation_signals.append("total_chars_below_70_percent_of_lower")
    if prose.endswith(("...", "—", "…")):
        truncation_signals.append("trailing_ellipsis_or_dash")
    if _check_html_unclosed(html):
        truncation_signals.append("html_unclosed_tag")

    truncation_suspected = len(truncation_signals) >= 2

    hard_fail_signals: list[str] = []
    if total_chars < lower_bound:
        hard_fail_signals.append("total_chars_below_lower_bound")
    if "결론" not in html and "Closing" not in html and "마무리" not in html:
        hard_fail_signals.append("no_closing")
    if not ends_with_punct and total_chars > 100:
        hard_fail_signals.append("ends_without_punctuation")
    if EXHIBIT_REF_PATTERN.search(html):
        hard_fail_signals.append("exhibit_ref_broken")
    if chart_count > chart_limit:
        hard_fail_signals.append("chart_count_exceeds_limit")
    if PLACEHOLDER_PATTERN.search(prose):
        hard_fail_signals.append("placeholder_unresolved")

    if hard_fail_signals:
        decision = "kill"
    elif truncation_suspected or len(truncation_signals) >= 1:
        decision = "hold"
    else:
        decision = "publish"

    return RetrofitDiagnosis(
        report_id=report_path.stem,
        file_path=str(report_path.relative_to(REPO_ROOT) if REPO_ROOT in report_path.parents else report_path),
        total_chars=total_chars,
        last_char=last_char,
        ends_with_punct=ends_with_punct,
        chart_count=chart_count,
        map_count=map_count,
        truncation_suspected=truncation_suspected,
        truncation_signals=truncation_signals,
        hard_fail_signals=hard_fail_signals,
        estimated_decision=decision,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V5 Retrofit MVP — read-only diagnosis")
    parser.add_argument("--reports-dir", type=Path, default=REPO_ROOT / "reports")
    parser.add_argument("--csv", type=Path, default=None, help="결과 CSV 출력 경로")
    parser.add_argument("--json", type=Path, default=None, help="결과 JSON 출력 경로")
    args = parser.parse_args(argv)

    if not args.reports_dir.exists():
        print(f"[error] reports directory not found: {args.reports_dir}", file=sys.stderr)
        print(f"  VM 의 reports/ 디렉토리에서 실행하거나 --reports-dir 로 경로 지정.", file=sys.stderr)
        return 2

    html_files = sorted(args.reports_dir.glob("*.html"))
    if not html_files:
        print(f"[info] no HTML files in {args.reports_dir}")
        return 0

    diagnoses: list[RetrofitDiagnosis] = []
    for html_path in html_files:
        try:
            diag = diagnose_report(html_path)
        except Exception as e:
            print(f"  [skip] {html_path.name}: {e}", file=sys.stderr)
            continue
        diagnoses.append(diag)

    print("\n" + "=" * 80)
    print(f"V5 Retrofit Diagnosis — {len(diagnoses)} reports")
    print("=" * 80)
    by_decision = {"publish": 0, "hold": 0, "kill": 0}
    for d in diagnoses:
        by_decision[d.estimated_decision] += 1
        marker = {"publish": "✓", "hold": "⚠", "kill": "✗"}[d.estimated_decision]
        signals = "; ".join(d.hard_fail_signals + d.truncation_signals) or "—"
        print(f"  {marker} {d.report_id:40s} chars={d.total_chars:5d} charts={d.chart_count} {d.estimated_decision:7s} {signals}")

    print(f"\n  publish: {by_decision['publish']:3d}")
    print(f"  hold:    {by_decision['hold']:3d}")
    print(f"  kill:    {by_decision['kill']:3d}")
    print(f"  total:   {len(diagnoses):3d}")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "report_id", "file_path", "total_chars", "last_char", "ends_with_punct",
                "chart_count", "map_count", "truncation_suspected", "truncation_signals",
                "hard_fail_count", "hard_fail_signals", "estimated_decision",
            ])
            for d in diagnoses:
                w.writerow([
                    d.report_id, d.file_path, d.total_chars, d.last_char, d.ends_with_punct,
                    d.chart_count, d.map_count, d.truncation_suspected,
                    ";".join(d.truncation_signals),
                    d.hard_fail_count, ";".join(d.hard_fail_signals),
                    d.estimated_decision,
                ])
        print(f"\nCSV saved to: {args.csv}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps([d.__dict__ for d in diagnoses], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON saved to: {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
