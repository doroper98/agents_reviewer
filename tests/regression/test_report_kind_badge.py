"""v8.5.3 — 보고서 종류 배지 회귀 (사용자 요청 2026-08-01).

"전체보고서 목록에 장마감브리핑, 일일브리핑 헤더도 추가해놔."

브리핑은 요청 시점에 ``AnalysisRequest.report_kind`` 로 출처를 심고, 목록 2곳
(Cloudflare Pages 관리자 목록 / GitHub 미러 README)이 ``src/tools/report_kind.py``
라는 *하나의* 판별 로직으로 배지를 붙인다.

**제목·분류로 추측하지 않는 이유** — 둘 다 LLM 생성이라 같은 브리핑도 매번 다르게
나온다 (실측: '조간 종합 브리핑' / '아침 일일 브리핑' / '2026-07-21 한국 증시 마감'
/ 'market_close_daily / equity / KR'). 추측 판별은 오분류를 낳으므로 금지.

**구 발행분 소급** — v8.5.3 이전 브리핑에는 report_kind 가 없다. 대신 스케줄러가
만든 *고정 프롬프트 문구* 가 ``request.event_description`` 에 그대로 저장돼 있어
정확히 판별된다. 이 경로가 깨지면 이미 발행된 브리핑 100여 건이 배지를 잃는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.tools.report_kind import KIND_LABELS, badge_label, detect_report_kind

_ROOT = Path(__file__).resolve().parents[2]


def _write(dirp: Path, stem: str, *, kind_meta: str = "", theme: str = "editorial_cream",
           request: dict | None = None, title: str = "제목") -> None:
    meta = f'<meta name="report-kind" content="{kind_meta}">' if kind_meta else ""
    (dirp / f"{stem}.html").write_text(
        f'<!DOCTYPE html>\n<html lang="ko" data-theme="{theme}">\n<head><meta charset="UTF-8">'
        f"{meta}<title>{title}</title></head><body></body></html>",
        encoding="utf-8",
    )
    (dirp / f"{stem}.json").write_text(
        json.dumps({"request": request or {}}, ensure_ascii=False), encoding="utf-8"
    )


# --------------------------------------------------------------------------
# 1. 판별 — 신규 발행분
# --------------------------------------------------------------------------


def test_detect_from_html_meta(tmp_path: Path) -> None:
    for kind in ("daily_briefing", "market_briefing"):
        _write(tmp_path, f"analysis_x_{kind}", kind_meta=kind)
        head = (tmp_path / f"analysis_x_{kind}.html").read_text(encoding="utf-8")
        assert detect_report_kind(str(tmp_path), f"analysis_x_{kind}", html_head=head) == kind


def test_detect_from_json_report_kind(tmp_path: Path) -> None:
    """HTML 에 meta 가 없어도 JSON 의 report_kind 로 판별 (html_head 미전달 경로)."""
    _write(tmp_path, "analysis_j", request={"report_kind": "market_briefing"})
    assert detect_report_kind(str(tmp_path), "analysis_j") == "market_briefing"


# --------------------------------------------------------------------------
# 2. 판별 — 구 발행분 소급 (프롬프트 고정 문구)
# --------------------------------------------------------------------------


def test_legacy_daily_briefing_detected_by_prompt(tmp_path: Path) -> None:
    _write(tmp_path, "analysis_d", request={
        "event_description": "오늘 2026-07-31 (Fri) 아침 자동 일일 브리핑 (심층 분석).\n\n분석 대상: ...",
    })
    assert detect_report_kind(str(tmp_path), "analysis_d") == "daily_briefing"


def test_legacy_market_briefing_detected_behind_long_persona(tmp_path: Path) -> None:
    """★ 장마감 브리핑은 프롬프트 *앞* 에 페르소나(실측 ~8.8K자)가 붙는다.

    요청 문구가 9K자 뒤로 밀리므로, JSON 머리를 짧게 읽으면 못 잡는다 (실제로
    첫 구현이 4096자만 읽어 실 발행분 40건을 전부 놓쳤다). 페르소나 헤더 마커 +
    넉넉한 head 크기 둘 다 필요.
    """
    persona = "# 시장 구조 해석가 — Market Briefing Persona (v7.9.0)\n\n" + ("가" * 9000)
    _write(tmp_path, "analysis_m", request={
        "event_description": persona + "\n\n---\n\n오늘 한국 주식장 마감 후 자동 브리핑 (심층 구조 분석).",
    })
    assert detect_report_kind(str(tmp_path), "analysis_m") == "market_briefing"


def test_manual_report_has_no_kind(tmp_path: Path) -> None:
    """수동 /analyze 는 배지 없음 — 오부착 방지."""
    _write(tmp_path, "analysis_p", request={
        "event_description": "반도체 특별법 개정안 분석해줘",
    })
    assert detect_report_kind(str(tmp_path), "analysis_p") == ""
    assert badge_label("") == ""


def test_reportage_still_detected(tmp_path: Path) -> None:
    _write(tmp_path, "analysis_r", theme="reportage_noturno",
           request={"report_format": "reportage"})
    head = (tmp_path / "analysis_r.html").read_text(encoding="utf-8")
    assert detect_report_kind(str(tmp_path), "analysis_r", html_head=head) == "reportage"


# --------------------------------------------------------------------------
# 3. 프롬프트 마커 정합 — 스케줄러 문구가 바뀌면 소급 판별이 죽는다
# --------------------------------------------------------------------------


def test_prompt_markers_match_scheduler_sources() -> None:
    daily = (_ROOT / "src" / "scheduler" / "daily_briefing.py").read_text(encoding="utf-8")
    market = (_ROOT / "src" / "scheduler" / "market_briefing.py").read_text(encoding="utf-8")
    persona = (_ROOT / "prompts" / "market_briefing_persona.md").read_text(encoding="utf-8")
    assert "아침 자동 일일 브리핑" in daily, (
        "일일 브리핑 프롬프트 문구가 바뀜 — report_kind.py 의 _PROMPT_MARKS 도 갱신 필요"
    )
    assert "한국 주식장 마감 후 자동 브리핑" in market, (
        "장마감 브리핑 프롬프트 문구가 바뀜 — _PROMPT_MARKS 갱신 필요"
    )
    assert "Market Briefing Persona" in persona, (
        "페르소나 헤더가 바뀜 — _PROMPT_MARKS 의 페르소나 마커 갱신 필요"
    )


def test_schedulers_stamp_report_kind() -> None:
    """스케줄러가 report_kind 를 심지 않으면 신규 발행분이 배지를 못 받는다."""
    daily = (_ROOT / "src" / "scheduler" / "daily_briefing.py").read_text(encoding="utf-8")
    market = (_ROOT / "src" / "scheduler" / "market_briefing.py").read_text(encoding="utf-8")
    assert 'report_kind="daily_briefing"' in daily
    assert 'report_kind="market_briefing"' in market


def test_freeform_template_emits_kind_meta() -> None:
    """목록이 HTML 머리만 읽고 판별할 수 있도록 meta 를 찍어야 한다."""
    tpl = (_ROOT / "src" / "templates" / "archetypes" / "freeform_essay.html").read_text(
        encoding="utf-8")
    assert 'name="report-kind"' in tpl
    assert "report_kind" in tpl.split("</head>")[0], "meta 가 <head> 밖에 있음"


# --------------------------------------------------------------------------
# 4. 목록 2곳 통합 — 같은 판별, 같은 배지
# --------------------------------------------------------------------------


def _fixture_dir(tmp_path: Path) -> Path:
    _write(tmp_path, "analysis_20260801_060000_a", kind_meta="daily_briefing",
           request={"report_kind": "daily_briefing"}, title="아침 브리핑")
    _write(tmp_path, "analysis_20260801_185000_b", kind_meta="market_briefing",
           request={"report_kind": "market_briefing"}, title="마감 브리핑")
    _write(tmp_path, "analysis_20260730_130000_f", request={
        "event_description": "직접 물어본 주제"}, title="수동 보고서")
    for stem, t in (("analysis_20260801_060000_a", "아침 브리핑"),
                    ("analysis_20260801_185000_b", "마감 브리핑"),
                    ("analysis_20260730_130000_f", "수동 보고서")):
        (tmp_path / f"{stem}.md").write_text(f"# {t}\n\n**Category:** 종합\n", encoding="utf-8")
    return tmp_path


def test_pages_admin_index_badges_briefings(tmp_path: Path) -> None:
    from src.agents.report_synthesizer import ReportSynthesizer
    from src.config import Config

    d = _fixture_dir(tmp_path)
    cfg = Config(_env_file=None)
    object.__setattr__(cfg, "admin_index_token", "tkn")
    ReportSynthesizer(cfg)._generate_index(str(d))
    idx = (d / "tkn.html").read_text(encoding="utf-8")

    rows = {re.sub(r"<[^>]+>", " ", r): r
            for r in re.findall(r'<tr><td class="cell-title">(.*?)</td>', idx, re.S)}
    def row_for(title: str) -> str:
        return next(raw for txt, raw in rows.items() if title in txt)

    assert KIND_LABELS["daily_briefing"] in row_for("아침 브리핑")
    assert KIND_LABELS["market_briefing"] in row_for("마감 브리핑")
    assert "badge-rep" not in row_for("수동 보고서")


def test_github_mirror_index_badges_briefings(tmp_path: Path) -> None:
    from src.tools.github_mirror import build_reports_index

    md = build_reports_index(str(_fixture_dir(tmp_path)))
    daily = next(ln for ln in md.splitlines() if "아침 브리핑" in ln)
    market = next(ln for ln in md.splitlines() if "마감 브리핑" in ln)
    manual = next(ln for ln in md.splitlines() if "수동 보고서" in ln)
    assert f"[{KIND_LABELS['daily_briefing']}]" in daily
    assert f"[{KIND_LABELS['market_briefing']}]" in market
    assert "[" not in manual.split("|")[2], "수동 보고서에 배지 오부착"
