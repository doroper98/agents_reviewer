#!/usr/bin/env python3
"""v5.2.3 결함 4건을 *이미 생성된* 보고서에 소급 적용하는 일회용 패치 스크립트.

배경:
- v5.2.2 에서 생성된 보고서들은 다음 4건 결함을 그대로 떠안고 있다.
  #1 영역 그라데이션 누락 / #2 좌측 치우침 / #3 raw float 노출 / #4 모든 차트
  동일 1-5 사건.
- #1/#2/#3 은 charts.js 함수(drawLine) 로직 결함 — charts.js 하나만 v5.2.3
  새 버전으로 덮어쓰면 즉시 해소.
- #4 는 HTML 안에 inline 으로 박힌 chart payload (``<script
  class="chart-payload-inline">``) 의 ``data[].event`` 필드 자체가 잘못 박힌
  것이라, HTML 을 직접 다시 써야 한다.

용법::

    # 보고서 출력 디렉터리 단위 (charts.js + 모든 analysis_*.html 일괄 패치)
    python scripts/patch_existing_reports.py reports/

    # 또는 단일 HTML 만 (charts.js 는 안 건드림)
    python scripts/patch_existing_reports.py reports/analysis_20260515_230117.html

원본은 같은 위치에 ``*.bak`` 으로 보존한다. 운영자가 결과를 눈으로 확인한 뒤
직접 ``wrangler pages deploy`` 로 재배포하면 된다.

별도 스크립트인 ``scripts/patch_report.py`` 와 혼동 주의: 그건 ComposedReport
JSON 을 로드해서 ReportSynthesizer 로 *재렌더* 하는 도구이고, 본 스크립트는
HTML inline JSON 만 직접 손대는 더 가벼운 도구이다.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

# repo root 를 sys.path 에 — `python scripts/patch_existing_reports.py` 형태
# 실행에서 ``from src.orchestrator import`` 가 동작하도록.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.orchestrator import _event_relevant_to  # noqa: E402


# 보고서 HTML 의 chart 제목 → instrument 추정. composer 가 박는 title 패턴
# (``_format_ts_title``) 과 정합. 확장은 여기서.
_INSTRUMENT_TITLE_HINTS: tuple[tuple[str, str], ...] = (
    ("코스피", "코스피"),
    ("코스닥", "코스닥"),
    ("삼성전자", "삼성전자"),
    ("SK하이닉스", "SK하이닉스"),
    ("달러인덱스", "달러인덱스"),
    ("WTI", "WTI"),
    ("브렌트", "브렌트유"),
    ("미국채 1Y", "미국채 1Y"),
    ("미국채 2Y", "미국채 2Y"),
    ("미국채 10Y", "미국채 10Y"),
    ("미국채 30Y", "미국채 30Y"),
    ("국고채 3Y", "국고채 3Y"),
    ("국고채 10Y", "국고채 10Y"),
    ("원/달러", "원/달러"),
    ("엔/달러", "엔/달러"),
    ("비트코인", "비트코인"),
    ("이더리움", "이더리움"),
)


def _detect_instrument(title: str) -> str:
    """차트 title 에서 instrument 이름 추정. 미탐지 시 빈 문자열."""
    for hint, inst in _INSTRUMENT_TITLE_HINTS:
        if hint in title:
            return inst
    return ""


# freeform_essay.html 의 emit 패턴과 byte-equal.
_PAYLOAD_PATTERN = re.compile(
    r'<script type="application/json" class="chart-payload-inline">(.*?)</script>',
    re.DOTALL,
)
_TS_TYPES = {"line", "candle", "area"}


def _filter_chart_payload(payload: dict) -> tuple[dict, int]:
    """단일 chart payload 의 ``data[].event`` 를 instrument-aware filter 로 재계산.

    Returns:
        (수정된 payload, 사라진 event 개수). event 자체는 제거 — 차트의 다른
        값(close/x/high/low)은 보존.
    """
    if payload.get("type") not in _TS_TYPES:
        return payload, 0
    title = payload.get("title", "") or ""
    instrument = _detect_instrument(title)
    if not instrument:
        return payload, 0
    data = payload.get("data") or []
    if not isinstance(data, list):
        return payload, 0
    removed = 0
    new_rows = []
    for row in data:
        if not isinstance(row, dict):
            new_rows.append(row)
            continue
        ev_text = row.get("event")
        if ev_text and not _event_relevant_to(str(ev_text), instrument):
            # event 필드만 제거. 가격/날짜 등 다른 필드는 그대로.
            new_row = {k: v for k, v in row.items() if k != "event"}
            new_rows.append(new_row)
            removed += 1
        else:
            new_rows.append(row)
    if removed:
        payload = {**payload, "data": new_rows}
    return payload, removed


def patch_html_file(html_path: Path) -> int:
    """HTML 안 모든 chart-payload-inline 의 event 필드를 instrument-aware 로 재계산.

    Returns:
        제거된 event 의 총 개수 (정보용).
    """
    original = html_path.read_text(encoding="utf-8")
    total_removed = 0

    def repl(m: re.Match) -> str:
        nonlocal total_removed
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        new_payload, removed = _filter_chart_payload(payload)
        total_removed += removed
        if not removed:
            return m.group(0)
        # ``tojson`` (Jinja) 와 ``json.dumps`` 의 escape 정책이 약간 다르지만
        # 브라우저 ``JSON.parse`` 는 둘 다 받음.
        new_json = json.dumps(new_payload, ensure_ascii=False)
        return (
            '<script type="application/json" class="chart-payload-inline">'
            + new_json + '</script>'
        )

    new_html = _PAYLOAD_PATTERN.sub(repl, original)
    if total_removed > 0 and new_html != original:
        backup = html_path.with_suffix(html_path.suffix + ".bak")
        if not backup.exists():  # 첫 패치만 백업 (idempotent)
            backup.write_text(original, encoding="utf-8")
        html_path.write_text(new_html, encoding="utf-8")
    return total_removed


def sync_charts_js(reports_dir: Path, repo_root: Path) -> bool:
    """reports_dir/charts.js 를 v5.2.3 의 src/templates/static/charts.js 로 덮어쓰기."""
    src = repo_root / "src" / "templates" / "static" / "charts.js"
    if not src.exists():
        print(f"[ERR] {src} 없음. repo_root 가 맞는지 확인.", file=sys.stderr)
        return False
    dst = reports_dir / "charts.js"
    if dst.exists():
        backup = dst.with_suffix(".js.bak")
        if not backup.exists():
            shutil.copy(dst, backup)
    shutil.copy(src, dst)
    return True


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 1
    target = Path(argv[0]).resolve()
    if not target.exists():
        print(f"[ERR] {target} 없음", file=sys.stderr)
        return 1

    repo_root = _REPO_ROOT

    # 단일 HTML 인지 디렉터리인지 분기
    if target.is_file() and target.suffix == ".html":
        n = patch_html_file(target)
        print(f"[OK] {target.name}: chart payload 의 event {n}개 instrument-aware 필터 적용")
        if n:
            print(f"     원본은 {target.name}.bak 으로 백업")
        return 0

    if not target.is_dir():
        print(f"[ERR] {target} — HTML 파일 또는 디렉터리여야 함", file=sys.stderr)
        return 1

    # 디렉터리: charts.js 동기화 + 모든 analysis_*.html 패치
    print(f"== Patching report dir: {target} ==")
    if sync_charts_js(target, repo_root):
        print(f"[OK] {target / 'charts.js'} ← v5.2.3 (#1/#2/#3 결함 해소)")

    htmls = sorted(target.glob("analysis_*.html"))
    if not htmls:
        print(f"[WARN] {target} 에 analysis_*.html 없음")
        return 0

    total_charts = 0
    for h in htmls:
        n = patch_html_file(h)
        if n:
            print(f"[OK] {h.name}: event {n}개 제거 (#4 결함 해소)")
            total_charts += 1
        else:
            print(f"[SKIP] {h.name}: instrument 미탐지 또는 이미 필터됨")
    print(
        f"\n총 {len(htmls)}개 보고서 중 {total_charts}개 HTML 의 chart payload 재계산 완료. "
        f"원본은 *.html.bak 로 백업."
    )
    print(
        "\n다음 단계: 'wrangler pages deploy reports/ --project-name <name>' 로 재배포 — "
        "Cloudflare Pages 의 캐시가 새 charts.js + HTML 로 갱신."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
