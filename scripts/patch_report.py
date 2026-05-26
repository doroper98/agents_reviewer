#!/usr/bin/env python3
"""patch_report.py — v4.4.7
이미 생성된 보고서를 LLM 호출 없이 부분 수정하고 재렌더·재배포.

[배경]
보고서 1건당 Opus 4.7 호출 2회 (~$2-3). 차트 1개가 깨졌다고 전체 재생성하는 건
낭비. v4.4.1 부터 ReportSynthesizer 가 HTML 과 함께 ComposedReport JSON 도
저장 (analysis_<timestamp>.json) — 본 스크립트가 그걸 로드해 일부 수정 후
같은 timestamp 로 재렌더 + Cloudflare 재배포.

[사용]
  python scripts/patch_report.py 20260502_154823 --show
      섹션/차트/지도 마커 목록 출력 (수정 X). 다른 옵션 인덱스 알기 위함.

  python scripts/patch_report.py 20260502_154823 --remove-chart 2:0
      3번째 섹션의 1번째 차트 제거 (0-based)

  python scripts/patch_report.py 20260502_154823 --remove-section 4
      5번째 섹션 통째 제거

  python scripts/patch_report.py 20260502_154823 --map-zoom 5.5
      지도 zoom 변경 (큰 값일수록 확대)

  python scripts/patch_report.py 20260502_154823 --map-center "44.0,9.5"
      지도 중심점 변경. "lng,lat" — 경도 먼저, 위도 나중.

  python scripts/patch_report.py 20260502_154823 --remove-marker hargeisa
      지도 마커 1개 제거 (id 기준). --show 로 id 확인 가능.

  python scripts/patch_report.py 20260502_154823 \
      --deck "유엔 회원국 가운데 첫 공식 승인. 다음 도미노는 미국·UAE·에티오피아."
      composed_report 의 텍스트 필드 교체 (--deck/--headline/--closing/
      --confidence-summary). 한국어 따옴표 포함 시 셸 escape 주의.

  python scripts/patch_report.py 20260525_233612 \
      --replace "rate card=공시 요금표(기본 단가표)" \
      --replace "rate limit premium=처리 한도를 높이는 대가로 내는 웃돈"
      전문 용어·영어 표현을 평이한 우리말로 일괄 치환 (LLM 0). 보고서 전체의
      모든 텍스트 필드 (headline/deck/closing/섹션 prose·heading·lede·pull_quote/
      차트 title·subtitle·note·takeaway/모순·감시신호/각주) 를 훑어 OLD→NEW 치환.
      대소문자 구분. 여러 번 지정 가능. --dry-run 으로 먼저 매치 수 확인 권장.

  python scripts/patch_report.py 20260525_233612 \
      --add-footnote "1:rate limit premium=처리 한도를 평소보다 높여 달라고 요청할 때 추가로 내는 웃돈."
      특정 섹션(0-based) 본문 하단에 용어 풀이 각주 추가. "SEC:용어=설명" 형식.
      평이하게 못 바꾸는 핵심 용어를 본문에 남길 때 (WRITE-AP-10, v5.5.5).

  python scripts/patch_report.py 20260525_233612 --replace "rate card=공시 요금표" --dry-run
      치환/추가를 *적용하지 않고* 매치 수만 출력 (JSON·배포 변경 X). 검증용.

  python scripts/patch_report.py 20260525_233612 --recompose
      저장된 사실 데이터로 보고서를 통째로 재작성 (LLM 1회=composer). 현재 패치된
      프롬프트를 쓰므로 모든 전문 용어가 평이하게 바뀌고 불가피한 용어엔 문단 하단
      각주가 붙음. URL 동일 유지. 단어 단위 --replace 가 놓치는 용어 (premium
      request 등) ·대소문자 문제까지 해결. --mode 로 깊이 지정 가능 (기본=원본 유지).

  python scripts/patch_report.py 20260502_154823 --edit
      $EDITOR (vim/nano) 로 JSON 직접 편집

  python scripts/patch_report.py 20260502_154823 --rerender-only
      수정 없이 재렌더만 (정적 자산 + HTML 갱신용)

  python scripts/patch_report.py 20260502_154823 --no-deploy
      로컬 파일만 갱신, Cloudflare 배포 X

[주의]
- v4.4.0 이전에 생성된 보고서는 JSON 저장이 없어 patch 불가. 재분석 필요.
- 수정 후 URL 은 동일 (사용자가 받은 링크 그대로 작동).
- 여러 옵션 동시 가능: --remove-chart 0:0 --map-zoom 5 --map-center "44,9"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

# Add project root to path so `src.*` imports work.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.report_synthesizer import ReportSynthesizer
from src.archetypes.registry import get_archetype
from src.config import Config
from src.models import FullAnalysisResult


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="이미 생성된 보고서를 LLM 호출 없이 부분 수정·재렌더·재배포.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "report_id",
        help="reports/analysis_<report_id>.json 형식. 예: 20260502_154823",
    )
    p.add_argument(
        "--remove-chart",
        metavar="SEC:CHART",
        action="append",
        default=[],
        help="section_idx:chart_idx (0-based) 차트 제거. 여러 번 가능: "
        "--remove-chart 2:0 --remove-chart 0:1 (인덱스 shift 자동 처리).",
    )
    p.add_argument(
        "--remove-section",
        type=int,
        metavar="IDX",
        help="섹션 통째 제거 (0-based). 예: --remove-section 4",
    )
    p.add_argument(
        "--show",
        action="store_true",
        help="섹션/차트/지도 마커 목록 출력 (수정 X). 인덱스/id 확인용.",
    )
    p.add_argument(
        "--map-zoom",
        type=float,
        metavar="ZOOM",
        help="지도 zoom 변경 (예: 5.5). 큰 값일수록 확대.",
    )
    p.add_argument(
        "--map-center",
        metavar="LNG,LAT",
        help="지도 중심점 변경. \"lng,lat\" 형식 (예: \"44.0,9.5\").",
    )
    p.add_argument(
        "--remove-marker",
        metavar="MARKER_ID",
        help="지도 마커 1개 제거 (id 기준). --show 로 id 확인.",
    )
    p.add_argument(
        "--deck",
        metavar="TEXT",
        help="composed_report.deck (헤드라인 부제) 교체.",
    )
    p.add_argument(
        "--headline",
        metavar="TEXT",
        help="composed_report.headline 교체.",
    )
    p.add_argument(
        "--closing",
        metavar="TEXT",
        help="composed_report.closing (분석가의 한계) 교체.",
    )
    p.add_argument(
        "--confidence-summary",
        metavar="TEXT",
        help="composed_report.confidence_summary 교체.",
    )
    p.add_argument(
        "--replace",
        metavar="OLD=NEW",
        action="append",
        default=[],
        help="전문 용어·영어 표현을 평이한 우리말로 일괄 치환 (LLM 0). 보고서 전체의 "
             "모든 텍스트 필드를 훑어 OLD→NEW 치환. 대소문자 구분. 여러 번 가능. "
             "예: --replace \"rate card=공시 요금표\". --dry-run 으로 먼저 검증 권장.",
    )
    p.add_argument(
        "--add-footnote",
        metavar="SEC:TERM=EXPLANATION",
        action="append",
        default=[],
        help="특정 섹션(0-based) 본문 하단에 용어 풀이 각주 추가 (v5.5.5). "
             "예: --add-footnote \"1:rate limit premium=처리 한도를 높일 때 내는 웃돈.\".",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="--replace / --add-footnote 를 *적용하지 않고* 매치 수만 출력 "
             "(JSON·배포 변경 X). 치환 검증용.",
    )
    p.add_argument(
        "--edit",
        action="store_true",
        help="$EDITOR 로 JSON 직접 편집 (저장 후 재렌더).",
    )
    p.add_argument(
        "--ensure-time-series",
        action="store_true",
        help="(v5.2.0+) context.time_series 가 있는데 composer 가 시계열 차트를 "
             "0개 박았으면 첫 섹션에 자동 추가. 기존 차트 있으면 no-op. "
             "20260515_230117 같은 케이스 복구용.",
    )
    p.add_argument(
        "--regenerate-ts-takeaways",
        action="store_true",
        help="(v5.2.7+) 시계열 차트 (line/area/candle) 의 takeaway 필드만 "
             "현재 _format_ts_takeaway 로직으로 재계산. v5.2.6 이전 보고서가 "
             "모든 차트에 동일 takeaway (전역 summary 의 소수점 절단 회귀) "
             "박혔던 케이스 복구용. composer-emitted 비-시계열 차트 (network/"
             "donut/gantt 등) 의 takeaway 는 건드리지 않음.",
    )
    p.add_argument(
        "--recompose",
        action="store_true",
        help="(v5.5.5) 저장된 사실 데이터(context)로 보고서를 *통째로 재작성*. "
             "현재(패치된) composer 프롬프트를 쓰므로 모든 전문 용어가 평이하게 "
             "바뀌고 불가피한 용어엔 각주가 붙음. URL 동일 유지 (LLM 1회=composer). "
             "단어 단위 --replace 가 놓치는 용어(premium request 등)·대소문자까지 해결.",
    )
    p.add_argument(
        "--mode",
        choices=["fast", "standard", "deep"],
        help="--recompose 시 분석 깊이. 미지정 시 원본 보고서의 mode 유지.",
    )
    p.add_argument(
        "--rerender-only",
        action="store_true",
        help="수정 없이 재렌더만 (정적 자산 / 새 charts.js 적용용).",
    )
    p.add_argument(
        "--no-deploy",
        action="store_true",
        help="Cloudflare 배포 스킵 (로컬 파일만 갱신).",
    )
    return p.parse_args()


def patch_remove_chart(result: FullAnalysisResult, sec_chart: str) -> bool:
    try:
        sec_i, chart_i = (int(x) for x in sec_chart.split(":"))
    except ValueError:
        print(f"[patch] --remove-chart 형식 오류: {sec_chart} (예: 2:0)", file=sys.stderr)
        return False
    if not result.composed_report or not result.composed_report.sections:
        print("[patch] composed_report.sections 가 비어있음", file=sys.stderr)
        return False
    sections = result.composed_report.sections
    if sec_i < 0 or sec_i >= len(sections):
        print(
            f"[patch] section_idx {sec_i} 범위 초과 (0~{len(sections) - 1})",
            file=sys.stderr,
        )
        return False
    sec = sections[sec_i]
    charts = sec.charts or []
    if chart_i < 0 or chart_i >= len(charts):
        print(
            f"[patch] section '{sec.heading}' 의 chart_idx {chart_i} 범위 초과 "
            f"(charts {len(charts)}개)",
            file=sys.stderr,
        )
        return False
    removed = charts.pop(chart_i)
    print(
        f"[patch] section '{sec.heading[:30]}' 에서 차트 제거: "
        f"type={removed.get('type', '?')} title={removed.get('title', '?')[:40]}"
    )
    return True


def patch_remove_section(result: FullAnalysisResult, sec_i: int) -> bool:
    if not result.composed_report or not result.composed_report.sections:
        print("[patch] composed_report.sections 가 비어있음", file=sys.stderr)
        return False
    sections = result.composed_report.sections
    if sec_i < 0 or sec_i >= len(sections):
        print(
            f"[patch] section_idx {sec_i} 범위 초과 (0~{len(sections) - 1})",
            file=sys.stderr,
        )
        return False
    removed = sections.pop(sec_i)
    print(f"[patch] 섹션 제거: '{removed.heading[:50]}'")
    return True


def patch_map_zoom(result: FullAnalysisResult, zoom: float) -> bool:
    if not result.composed_report or not result.composed_report.embedded_map:
        print("[patch] embedded_map 이 없음 (지리적 사건 아님)", file=sys.stderr)
        return False
    old = result.composed_report.embedded_map.get("zoom")
    result.composed_report.embedded_map["zoom"] = zoom
    print(f"[patch] map zoom: {old} → {zoom}")
    return True


def patch_map_center(result: FullAnalysisResult, center_str: str) -> bool:
    if not result.composed_report or not result.composed_report.embedded_map:
        print("[patch] embedded_map 이 없음 (지리적 사건 아님)", file=sys.stderr)
        return False
    try:
        lng_str, lat_str = center_str.split(",")
        lng, lat = float(lng_str.strip()), float(lat_str.strip())
    except (ValueError, AttributeError):
        print(
            f"[patch] --map-center 형식 오류: {center_str} (예: \"44.0,9.5\")",
            file=sys.stderr,
        )
        return False
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
        print(
            f"[patch] center 범위 초과: lng={lng} (-180~180), lat={lat} (-90~90)",
            file=sys.stderr,
        )
        return False
    old = result.composed_report.embedded_map.get("center")
    result.composed_report.embedded_map["center"] = [lng, lat]
    print(f"[patch] map center: {old} → [{lng}, {lat}]")
    return True


def patch_remove_marker(result: FullAnalysisResult, marker_id: str) -> bool:
    if not result.composed_report or not result.composed_report.embedded_map:
        print("[patch] embedded_map 이 없음", file=sys.stderr)
        return False
    emap = result.composed_report.embedded_map
    markers = emap.get("markers") or []
    before = len(markers)
    kept = [m for m in markers if m.get("id") != marker_id]
    if len(kept) == before:
        ids = [m.get("id") for m in markers]
        print(
            f"[patch] marker id '{marker_id}' 없음. 현재 ids: {ids}",
            file=sys.stderr,
        )
        return False
    emap["markers"] = kept
    # marker 가 사라졌으면 해당 id 를 참조하는 arc 도 제거
    arcs = emap.get("arcs") or []
    arcs_kept = [
        a for a in arcs
        if a.get("from_id") != marker_id and a.get("to_id") != marker_id
    ]
    if len(arcs_kept) != len(arcs):
        print(
            f"[patch] 관련 arc {len(arcs) - len(arcs_kept)}개도 함께 제거"
        )
        emap["arcs"] = arcs_kept
    print(f"[patch] marker 제거: '{marker_id}' (남은 markers: {len(kept)})")
    return True


def patch_set_text(result: FullAnalysisResult, field: str, value: str) -> bool:
    """ComposedReport 의 단일 텍스트 필드 (deck/headline/closing/confidence_summary) 교체."""
    if not result.composed_report:
        print("[patch] composed_report 없음", file=sys.stderr)
        return False
    if not hasattr(result.composed_report, field):
        print(f"[patch] composed_report 에 '{field}' 필드 없음", file=sys.stderr)
        return False
    old = getattr(result.composed_report, field) or ""
    setattr(result.composed_report, field, value)
    snip_old = (old[:60] + "...") if len(old) > 60 else old
    snip_new = (value[:60] + "...") if len(value) > 60 else value
    print(f"[patch] {field}: '{snip_old}' → '{snip_new}'")
    return True


def patch_replace_terms(
    result: FullAnalysisResult,
    replacements: list[tuple[str, str]],
    dry_run: bool,
) -> bool:
    """전문 용어·영어 표현을 평이한 우리말로 일괄 치환 (LLM 0, 결정론).

    보고서의 *모든* 텍스트 필드 (headline/deck/closing/confidence_summary/
    contradictions_heading + 섹션 heading/kicker/lede/prose/pull_quote +
    analogy/fact_grid + charts 의 title/subtitle/note/takeaway/source +
    contradictions/watch_signals + footnotes) 를 훑어 OLD→NEW substring 치환.
    dry_run 이면 매치 수만 집계하고 텍스트는 안 바꿈. WRITE-AP-10 (v5.5.5).
    """
    cr = result.composed_report
    if not cr:
        print("[patch] composed_report 없음", file=sys.stderr)
        return False
    counts: dict[str, int] = {old: 0 for old, _ in replacements}

    def sub(text: str | None) -> str | None:
        if not text:
            return text
        for old, new in replacements:
            c = text.count(old)
            if c:
                counts[old] += c
                if not dry_run:
                    text = text.replace(old, new)
        return text

    cr.headline = sub(cr.headline)
    cr.deck = sub(cr.deck)
    cr.closing = sub(cr.closing)
    cr.confidence_summary = sub(cr.confidence_summary)
    cr.contradictions_heading = sub(cr.contradictions_heading)
    for c in (cr.contradictions or []):
        for k in ("side_a", "side_b", "evidence", "resolution"):
            if c.get(k):
                c[k] = sub(c[k])
    for w in (cr.watch_signals or []):
        for k in ("signal", "description", "indicates"):
            if w.get(k):
                w[k] = sub(w[k])
    for sec in (cr.sections or []):
        sec.heading = sub(sec.heading)
        sec.kicker = sub(sec.kicker)
        sec.lede = sub(sec.lede)
        sec.prose = sub(sec.prose)
        sec.pull_quote = sub(sec.pull_quote)
        if sec.analogy:
            for k in ("title", "body"):
                if sec.analogy.get(k):
                    sec.analogy[k] = sub(sec.analogy[k])
        for f in (sec.fact_grid or []):
            for k in ("label", "value", "sublabel"):
                if f.get(k):
                    f[k] = sub(f[k])
        for ch in (sec.charts or []):
            for k in ("title", "subtitle", "note", "takeaway", "source"):
                if ch.get(k):
                    ch[k] = sub(ch[k])
        for fn in (sec.footnotes or []):
            for k in ("term", "explanation"):
                if fn.get(k):
                    fn[k] = sub(fn[k])

    total = sum(counts.values())
    tag = "[dry-run] " if dry_run else ""
    for old, new in replacements:
        print(f"[patch] {tag}--replace '{old}' → '{new}': {counts[old]} matches")
    print(f"[patch] {tag}총 {total} matches")
    return (total > 0) and (not dry_run)


def patch_add_footnote(
    result: FullAnalysisResult, spec: str, dry_run: bool
) -> bool:
    """섹션 본문 하단 용어 풀이 각주 추가. spec = "SEC:term=explanation"."""
    cr = result.composed_report
    if not cr or not cr.sections:
        print("[patch] composed_report.sections 가 비어있음", file=sys.stderr)
        return False
    try:
        sec_part, rest = spec.split(":", 1)
        sec_i = int(sec_part)
        term, explanation = rest.split("=", 1)
    except ValueError:
        print(
            f"[patch] --add-footnote 형식 오류: {spec} "
            f'(예: "1:rate limit premium=처리 한도를 높일 때 내는 웃돈.")',
            file=sys.stderr,
        )
        return False
    term, explanation = term.strip(), explanation.strip()
    if sec_i < 0 or sec_i >= len(cr.sections):
        print(
            f"[patch] section_idx {sec_i} 범위 초과 (0~{len(cr.sections) - 1})",
            file=sys.stderr,
        )
        return False
    sec = cr.sections[sec_i]
    if any(fn.get("term") == term for fn in (sec.footnotes or [])):
        print(f"[patch] 섹션 [{sec_i}] 에 이미 '{term}' 각주 있음 — skip")
        return False
    tag = "[dry-run] " if dry_run else ""
    print(
        f"[patch] {tag}섹션 [{sec_i}] '{sec.heading[:30]}' 각주 추가: "
        f"{term} — {explanation[:40]}"
    )
    if dry_run:
        return False
    sec.footnotes = list(sec.footnotes or []) + [
        {"term": term, "explanation": explanation}
    ]
    return True


def show_report(result: FullAnalysisResult) -> None:
    cr = result.composed_report
    if not cr:
        print("[show] composed_report 없음")
        return
    print(f"[show] headline: {cr.headline}")
    print(f"[show] sections: {len(cr.sections)}")
    for i, sec in enumerate(cr.sections):
        charts = sec.charts or []
        chart_summary = (
            ", ".join(
                f"[{j}] {c.get('type', '?')}/{(c.get('title') or '')[:25]}"
                for j, c in enumerate(charts)
            )
            if charts
            else "(no charts)"
        )
        print(f"  [{i}] {sec.heading[:50]}")
        print(f"      charts: {chart_summary}")
        fns = sec.footnotes or []
        if fns:
            print(
                "      footnotes: "
                + ", ".join((fn.get("term") or "")[:20] for fn in fns)
            )
    if cr.embedded_map:
        emap = cr.embedded_map
        print("[show] embedded_map:")
        print(f"  center: {emap.get('center')}")
        print(f"  zoom:   {emap.get('zoom')}")
        markers = emap.get("markers") or []
        print(f"  markers ({len(markers)}):")
        for m in markers:
            hl = " *" if m.get("highlight") else ""
            print(
                f"    id={m.get('id')!s:<20} "
                f"name={m.get('name')!s:<20} "
                f"lng={m.get('lng')} lat={m.get('lat')}{hl}"
            )
        arcs = emap.get("arcs") or []
        if arcs:
            print(f"  arcs ({len(arcs)}):")
            for a in arcs:
                print(
                    f"    {a.get('from_id')} → {a.get('to_id')} "
                    f"label={a.get('label', '')}"
                )
    else:
        print("[show] embedded_map: (없음)")


def patch_edit_json(json_path: str) -> bool:
    editor = os.environ.get("EDITOR", "vi")
    print(f"[patch] $EDITOR={editor} 로 {json_path} 편집. 저장하고 종료하세요.")
    try:
        subprocess.run([editor, json_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[patch] editor 실행 실패: {e}", file=sys.stderr)
        return False
    return True


def write_json(result: FullAnalysisResult, json_path: str) -> None:
    """수정된 result 를 JSON 으로 다시 저장 (다음 patch 가능하게)."""
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            result.model_dump(mode="json"),
            f, ensure_ascii=False, indent=2,
        )


async def main() -> int:
    args = parse_args()
    config = Config()
    output_dir = config.report_output_dir
    json_path = os.path.join(output_dir, f"analysis_{args.report_id}.json")
    if not os.path.exists(json_path):
        print(
            f"[patch] JSON 없음: {json_path}\n"
            f"        v4.4.0 이전 보고서는 JSON 저장 안 됐음. 재분석 필요.",
            file=sys.stderr,
        )
        return 1

    # --edit 는 *load 전*에 적용 (사용자가 raw JSON 편집)
    if args.edit:
        if not patch_edit_json(json_path):
            return 1

    # JSON 로드 → Pydantic 검증
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    try:
        result = FullAnalysisResult.model_validate(data)
    except Exception as e:
        print(f"[patch] JSON validation 실패: {e}", file=sys.stderr)
        return 1

    # --show 는 출력만 하고 종료 (수정/재렌더 X)
    if args.show:
        show_report(result)
        return 0

    # 명령 적용
    mutated = False
    if args.remove_chart:
        # 다중 --remove-chart 시 인덱스 shift 방지 위해 (sec, chart) 내림차순.
        try:
            specs = sorted(
                ((int(s), int(c)) for s, c in (x.split(":") for x in args.remove_chart)),
                reverse=True,
            )
        except ValueError:
            print(
                f"[patch] --remove-chart 형식 오류: {args.remove_chart} (예: 2:0)",
                file=sys.stderr,
            )
            return 1
        for sec_i, chart_i in specs:
            if not patch_remove_chart(result, f"{sec_i}:{chart_i}"):
                return 1
        mutated = True
    if args.remove_section is not None:
        if not patch_remove_section(result, args.remove_section):
            return 1
        mutated = True
    if args.map_zoom is not None:
        if not patch_map_zoom(result, args.map_zoom):
            return 1
        mutated = True
    if args.map_center:
        if not patch_map_center(result, args.map_center):
            return 1
        mutated = True
    if args.remove_marker:
        if not patch_remove_marker(result, args.remove_marker):
            return 1
        mutated = True
    for field, val in (
        ("deck", args.deck),
        ("headline", args.headline),
        ("closing", args.closing),
        ("confidence_summary", args.confidence_summary),
    ):
        if val is not None:
            if not patch_set_text(result, field, val):
                return 1
            mutated = True

    # v5.5.5 — 전문 용어 평이화 (--replace) + 문단 하단 각주 (--add-footnote).
    if args.replace:
        try:
            pairs = [tuple(x.split("=", 1)) for x in args.replace]
            for pr in pairs:
                if len(pr) != 2:
                    raise ValueError(pr)
        except ValueError:
            print(
                f'[patch] --replace 형식 오류: {args.replace} (예: "OLD=NEW")',
                file=sys.stderr,
            )
            return 1
        if patch_replace_terms(result, pairs, args.dry_run):
            mutated = True
    for spec in args.add_footnote:
        if patch_add_footnote(result, spec, args.dry_run):
            mutated = True

    # --dry-run 은 검증만 — JSON/재렌더/배포 일절 변경 X.
    if args.dry_run:
        print("[patch] --dry-run: 변경 적용 안 함 (JSON·배포 그대로).")
        return 0

    # v5.5.5 — 통째 재작성. 패치된 composer 프롬프트로 모든 용어 평이화 + 각주.
    # 단어 단위 치환이 놓치는 용어·대소문자까지 LLM 이 일괄 처리. URL 동일.
    if args.recompose:
        if not result.context:
            print(
                "[patch] context(사실 데이터) 없음 — recompose 불가. "
                "재분석 필요.",
                file=sys.stderr,
            )
            return 1
        from src.agents.narrative_composer import NarrativeComposer

        recompose_mode = args.mode or (
            result.request.mode if result.request else "standard"
        )
        print(
            f"[patch] --recompose: 패치된 프롬프트로 보고서 재작성 "
            f"(mode={recompose_mode}, LLM 1회=composer)..."
        )
        composer = NarrativeComposer(config)
        new_composed = await composer.compose_unified(
            result.context, mode=recompose_mode
        )
        if new_composed is None:
            print(
                "[patch] recompose 실패 (composer 가 None 반환 — LLM 호출/파싱 실패).",
                file=sys.stderr,
            )
            return 1
        result.composed_report = new_composed
        mutated = True
        print(
            f"[patch] recompose 완료: {len(new_composed.sections)} 섹션, "
            f"headline={new_composed.headline[:40]!r}"
        )

    # v5.2.7 — 시계열 차트 takeaway 만 재계산 (모든 차트 동일 takeaway +
    # 소수점 절단 회귀 retro fix). composer-emitted 비-시계열 차트는 skip.
    if args.regenerate_ts_takeaways:
        from src.orchestrator import _format_ts_takeaway
        ts_types = {"line", "area", "candle"}
        n_updated = 0
        for sec in (result.composed_report.sections or []) if result.composed_report else []:
            for ch in (sec.charts or []):
                ctype = (ch.get("type") or "").lower()
                if ctype not in ts_types:
                    continue
                data = ch.get("data") or []
                if not data:
                    continue
                instrument = (ch.get("title") or "").split(" (")[0].strip()
                old = (ch.get("takeaway") or "").strip()
                new = _format_ts_takeaway(data, ctype, result.context, instrument=instrument)
                if new and new != old:
                    ch["takeaway"] = new
                    n_updated += 1
        print(f"[patch] --regenerate-ts-takeaways: 시계열 차트 takeaway {n_updated}개 갱신")
        if n_updated > 0:
            mutated = True

    # v5.2.2+ — 시계열 차트 자동 보충 (case C 복구). mockup 수준 quality —
    # title/subtitle/source/takeaway + 이벤트 마커 자동 부착.
    if args.ensure_time_series:
        from src.orchestrator import _ensure_time_series_chart
        before = sum(
            len(sec.charts or []) for sec in (result.composed_report.sections or [])
        )
        _ensure_time_series_chart(result.composed_report, result.context)
        after = sum(
            len(sec.charts or []) for sec in (result.composed_report.sections or [])
        )
        if after > before:
            print(f"[patch] --ensure-time-series: 시계열 차트 {after - before}개 추가")
            mutated = True
        else:
            print("[patch] --ensure-time-series: 변경 없음 (composer 가 이미 다 박았거나 time_series 비어있음)")

    # 수정 사항 있으면 JSON 다시 저장 + revision +1 (v4.5.5).
    # --rerender-only / --edit 만은 데이터 변경 X 라 revision 안 올림.
    # --edit 는 사용자가 raw JSON 직접 편집 → 변경 여부 모르니 안전하게 +1.
    if mutated or args.edit:
        result.revision = (getattr(result, "revision", 0) or 0) + 1
        write_json(result, json_path)
        print(f"[patch] JSON 갱신: {json_path} (revision = {result.revision})")

    # 재렌더
    synth = ReportSynthesizer(config)
    archetype_id = (
        result.strategy.report_archetype
        if result.strategy and result.strategy.report_archetype
        else "freeform_essay"
    )
    archetype = get_archetype(archetype_id)
    theme = result.report_theme or "burgundy_mono"

    print(
        f"[patch] 재렌더 — report_id={args.report_id}, theme={theme}, "
        f"archetype={archetype.archetype_id}"
    )

    # --no-deploy 면 cloudflare 자격 비워서 _upload_to_cloudflare 가 graceful
    # skip 하도록 임시 무력화 (config 변경 X — 환경 변수 한정 override)
    if args.no_deploy:
        original_token = config.cloudflare_api_token
        config.cloudflare_api_token = ""

    try:
        url_or_path = await synth.synthesize(
            result, theme=theme, archetype=archetype,
            report_id=args.report_id,
        )
    except Exception as e:
        print(f"[patch] 재렌더 실패: {e}", file=sys.stderr)
        return 1
    finally:
        if args.no_deploy:
            config.cloudflare_api_token = original_token

    if url_or_path.startswith("http"):
        print(f"[patch] 완료. URL: {url_or_path}")
    else:
        print(f"[patch] 완료. local: {url_or_path} (배포는 별도)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
