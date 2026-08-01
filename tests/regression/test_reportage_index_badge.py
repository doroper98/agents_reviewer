"""v8.5.2 — 르포 등록·표기 회귀 (사용자 확인 요청 2026-08-01).

사용자 질문: "르포도 보고서 저장되는 웹사이트에 등록되나? 등록될 때 [르포] 헤더를
달고 등록되게 해달라."

확인 결과 — 저장·등록 자체는 이미 정상이었다. 르포도 일반 보고서와 *같은* 경로로
``analysis_<id>.html`` 로 저장되고, Cloudflare Pages 목록(``_generate_index``)이
``analysis_*.html`` 를 glob 하므로 목록에도 뜬다. 빠져 있던 것은 **표기**:

  · GitHub 미러 README(``build_reports_index``)  → [르포] 배지 있었음 (v8.0.0)
  · Cloudflare Pages 관리자 목록                  → 배지 **없었음** ← v8.5.2 추가
  · 르포 보고서 전문 헤더(``.rep-top``)           → 배지 **없었음** ← v8.5.2 추가

두 번째·세 번째는 CLAUDE.md v8.0.0 이 "보고서 전문 헤더 + 리스트에 [르포] 배지"
라고 적어둔 설계가 코드에 구현돼 있지 않던 문서-코드 drift 였다.

판별 근거는 HTML 머리 3000자 안에서 끝난다 (제목 추출 read 재사용, 추가 IO 0):
  ① ``<meta name="report-format" content="reportage">`` — v8.5.2~ 신규 발행분
  ② ``data-theme="reportage_*"`` 폴백 — v8.0.0~v8.5.1 사이 이미 발행돼 meta 가
     없는 르포도 *재렌더 없이* 배지가 붙는다.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.agents.report_synthesizer import ReportSynthesizer
from src.config import Config

_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _ROOT / "src" / "templates" / "archetypes"
_REPORTAGE = (_TEMPLATE_DIR / "reportage.html").read_text(encoding="utf-8")
_FREEFORM = (_TEMPLATE_DIR / "freeform_essay.html").read_text(encoding="utf-8")

_META = '<meta name="report-format" content="reportage">'


# --------------------------------------------------------------------------
# 1. 르포 템플릿 — 기계 마커 + 전문 헤더 배지
# --------------------------------------------------------------------------


def test_reportage_template_emits_format_meta() -> None:
    """목록이 읽을 기계 판별 마커가 <head> 에 있어야 한다."""
    assert _META in _REPORTAGE, "report-format meta 마커 누락 — 목록 배지 판별 불가"
    head = _REPORTAGE.split("</head>")[0]
    assert _META in head, "meta 마커가 <head> 밖에 있음 (머리 3000자 판별에서 놓칠 수 있음)"


def test_reportage_header_shows_badge() -> None:
    """르포 전문 헤더(.rep-top)에 [르포] 배지 (CLAUDE.md v8.0.0 설계)."""
    assert 'class="rep-badge"' in _REPORTAGE, "전문 헤더의 르포 배지 누락"
    m = re.search(r'<div class="rep-top">(.*?)</div>', _REPORTAGE, re.S)
    assert m and "rep-badge" in m.group(1), ".rep-top 안에 배지가 없음"
    assert ".rep-badge{" in _REPORTAGE, "rep-badge 스타일 정의 누락"


def test_freeform_never_claims_reportage_format() -> None:
    """일반 보고서 템플릿이 르포 마커를 달면 목록 전체가 오분류된다."""
    assert _META not in _FREEFORM
    assert 'data-theme="reportage' not in _FREEFORM


# --------------------------------------------------------------------------
# 2. Pages 관리자 목록 — 르포만 배지
# --------------------------------------------------------------------------


def _html(theme: str, title: str, *, meta: bool) -> str:
    return (
        f'<!DOCTYPE html>\n<html lang="ko" data-theme="{theme}">\n<head><meta charset="UTF-8">'
        + (_META if meta else "")
        + f"<title>{title}</title></head><body></body></html>"
    )


def _build_index(tmp_path: Path) -> str:
    (tmp_path / "analysis_20260801_090000_aaa.html").write_text(
        _html("editorial_cream", "일반 보고서", meta=False), encoding="utf-8")
    (tmp_path / "analysis_20260801_100000_bbb.html").write_text(
        _html("reportage_noturno", "신규 르포", meta=True), encoding="utf-8")
    (tmp_path / "analysis_20260731_080000_ccc.html").write_text(
        _html("reportage_ember", "구 발행 르포", meta=False), encoding="utf-8")

    cfg = Config(_env_file=None)
    object.__setattr__(cfg, "admin_index_token", "tkn")
    ReportSynthesizer(cfg)._generate_index(str(tmp_path))
    return (tmp_path / "tkn.html").read_text(encoding="utf-8")


def _row_of(index_html: str, title: str) -> str:
    for row in re.findall(r'<tr><td class="cell-title">(.*?)</td>', index_html, re.S):
        if title in row:
            return row
    raise AssertionError(f"목록에 '{title}' 행이 없음 — 등록 자체가 안 된 회귀")


def test_index_registers_reportage_reports(tmp_path: Path) -> None:
    """등록(저장) 자체 가드 — 르포도 일반 보고서와 같이 목록에 올라야 한다."""
    idx = _build_index(tmp_path)
    for title in ("일반 보고서", "신규 르포", "구 발행 르포"):
        _row_of(idx, title)  # 없으면 AssertionError


def test_index_badges_only_reportage(tmp_path: Path) -> None:
    """르포 행에만 [르포] 배지. 신규(meta)·구 발행분(data-theme 폴백) 모두."""
    idx = _build_index(tmp_path)
    assert "badge-rep" in _row_of(idx, "신규 르포"), "meta 마커 르포에 배지 없음"
    assert "badge-rep" in _row_of(idx, "구 발행 르포"), (
        "data-theme 폴백 실패 — v8.5.2 이전 발행 르포가 재렌더 없이는 배지를 못 받음"
    )
    assert "badge-rep" not in _row_of(idx, "일반 보고서"), "일반 보고서에 르포 배지 오부착"
    assert ".badge-rep{" in idx, "배지 스타일이 목록 페이지에 없음"


def test_github_mirror_index_keeps_badge(tmp_path: Path) -> None:
    """GitHub 미러 README 의 [르포] 배지(v8.0.0)도 유지 — 두 목록 표기 정합.

    v8.5.3 에서 판별이 src/tools/report_kind.py 로 통합되며 소스 문자열이 바뀌었다.
    소스 grep 대신 *실제 README 를 생성해* 검증한다 (리팩토링에 안 깨짐).
    """
    from src.tools.github_mirror import build_reports_index

    # GitHub 미러 목록은 .md(제목) + .json(종류)을 읽는다 — 실제 발행분과 동일 구성.
    import json

    (tmp_path / "analysis_20260801_100000_bbb.html").write_text(
        _html("reportage_noturno", "르포 제목", meta=True), encoding="utf-8")
    (tmp_path / "analysis_20260801_100000_bbb.md").write_text(
        "# 르포 제목\n\n**Category:** 종합\n", encoding="utf-8")
    (tmp_path / "analysis_20260801_100000_bbb.json").write_text(
        json.dumps({"request": {"report_format": "reportage"}}, ensure_ascii=False),
        encoding="utf-8")
    (tmp_path / "analysis_20260801_090000_aaa.md").write_text(
        "# 일반 제목\n\n**Category:** 종합\n", encoding="utf-8")
    (tmp_path / "analysis_20260801_090000_aaa.json").write_text(
        json.dumps({"request": {"event_description": "직접 물어본 주제"}}, ensure_ascii=False),
        encoding="utf-8")

    md = build_reports_index(str(tmp_path))
    rep_line = next(ln for ln in md.splitlines() if "르포 제목" in ln)
    gen_line = next(ln for ln in md.splitlines() if "일반 제목" in ln)
    assert "[르포]" in rep_line, "GitHub 미러 README 의 르포 배지가 사라짐"
    assert "[르포]" not in gen_line, "일반 보고서에 르포 배지 오부착"
