#!/usr/bin/env python3
"""patch_report.py — v4.4.5
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
        "--edit",
        action="store_true",
        help="$EDITOR 로 JSON 직접 편집 (저장 후 재렌더).",
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

    # 수정 사항 있으면 JSON 다시 저장 (--rerender-only / --edit 만이면 이미 변경 X)
    if mutated:
        write_json(result, json_path)
        print(f"[patch] JSON 갱신: {json_path}")

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
