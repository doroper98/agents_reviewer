"""보고서 종류 판별 — 목록 배지 SSOT (v8.5.3).

보고서 목록은 두 곳에 있고 지금까지 배지 판별 로직이 따로 놀았다:
  · Cloudflare Pages 관리자 목록 — ``report_synthesizer._generate_index``
  · GitHub 미러 README        — ``github_mirror.build_reports_index``
같은 판별을 두 번 쓰면 반드시 어긋나므로(v8.5.2 의 르포 배지가 실제로 한쪽에만
있었다) 본 모듈이 유일한 판별 진입점이다.

**판별 우선순위** — 위에서 걸리면 아래는 보지 않는다.

1. HTML ``<meta name="report-kind" content="...">`` — v8.5.3~ 발행분.
2. HTML 의 르포 표식 (``report-format`` meta / ``data-theme="reportage_*"``).
3. JSON ``request.report_kind`` / ``request.report_format`` — v8.5.3~ / v8.0.0~.
4. JSON ``request.event_description`` 의 **스케줄러 프롬프트 고정 문구** —
   v8.5.3 이전에 이미 발행된 브리핑을 *재렌더 없이* 소급 판별하는 경로.

4번이 추측이 아니라 정확한 이유: 브리핑 프롬프트는 스케줄러가 만든 고정 문자열
이고 그대로 ``request.event_description`` 에 저장된다. 반면 제목·분류는 LLM 이
매번 다르게 쓰므로(실측: '조간 종합 브리핑' / '아침 일일 브리핑' /
'market_close_daily / equity / KR') 그쪽으로 추측하면 오분류가 난다 — 쓰지 않는다.

JSON 은 **머리 일부만** 읽는다. ``request`` 가 최상위 첫 키이고
``event_description`` 이 그 첫 필드라 앞부분에서 판별이 끝난다 (목록 1회 생성에
보고서 200건까지 스캔하므로 전체 파싱은 낭비).
"""

from __future__ import annotations

import os

# 종류 → 목록 배지 라벨. 사용자 지정 문구 (2026-08-01).
KIND_LABELS: dict[str, str] = {
    "reportage": "르포",
    "daily_briefing": "일일브리핑",
    "market_briefing": "장마감브리핑",
}

# 스케줄러 프롬프트의 고정 문구 (src/scheduler/*.py 의 _build_*_prompt 와 정합).
# 문구를 바꾸면 여기도 바꿔야 구 발행분 소급 판별이 유지된다.
#
# 장마감 브리핑은 프롬프트 *앞* 에 페르소나가 붙는다(market_briefing.py:121,
# 실측 ~8.8K자) — 요청 문구가 9K자 뒤로 밀리므로 페르소나 헤더도 마커로 둔다.
# 버전 표기가 바뀌어도 살아남게 버전 없는 부분 문자열을 쓴다
# (prompts/market_briefing_persona.md:1 "… — Market Briefing Persona (v7.9.0)").
# 페르소나 파일이 없어 graceful degrade 된 경우엔 요청 문구가 앞으로 오므로 둘 중
# 하나는 반드시 걸린다.
_PROMPT_MARKS: tuple[tuple[str, str], ...] = (
    ("아침 자동 일일 브리핑", "daily_briefing"),
    ("한국 주식장 마감 후 자동 브리핑", "market_briefing"),
    ("Market Briefing Persona", "market_briefing"),
)

# 페르소나가 앞에 붙은 장마감 브리핑도 요청 문구까지 닿도록 넉넉히 (실측 9.2K).
# 목록 1회 생성에 최대 200건을 훑으므로 상한을 둔다 (전체 파싱 회피).
_JSON_HEAD_BYTES = 16384


def _from_html(head: str) -> str:
    """HTML 머리에서 판별. 목록이 제목 추출용으로 이미 읽은 문자열을 재사용."""
    if not head:
        return ""
    for kind in KIND_LABELS:
        if f'name="report-kind" content="{kind}"' in head:
            return kind
    # 르포는 v8.5.2 의 기존 2단 판별 (meta + 테마 폴백) 유지.
    if 'name="report-format" content="reportage"' in head or 'data-theme="reportage' in head:
        return "reportage"
    return ""


def _from_json_head(path: str) -> str:
    """보고서 JSON 머리에서 판별 (구 발행분 소급 경로 포함)."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            head = f.read(_JSON_HEAD_BYTES)
    except OSError:
        return ""
    for kind in KIND_LABELS:
        if f'"report_kind": "{kind}"' in head or f'"report_kind":"{kind}"' in head:
            return kind
    if '"report_format": "reportage"' in head or '"report_format":"reportage"' in head:
        return "reportage"
    for mark, kind in _PROMPT_MARKS:
        if mark in head:
            return kind
    return ""


def detect_report_kind(reports_dir: str, stem: str, *, html_head: str = "") -> str:
    """보고서 종류를 반환. 판별 불가·일반 보고서면 빈 문자열.

    Args:
        reports_dir: 보고서 산출물 디렉토리 (html/json 이 같이 있는 곳).
        stem: 확장자 없는 파일명 (예: ``analysis_20260801_061745_0fc535a015``).
        html_head: 이미 읽어둔 HTML 머리 문자열. 있으면 파일 IO 없이 먼저 판별.
    """
    kind = _from_html(html_head)
    if kind:
        return kind
    return _from_json_head(os.path.join(reports_dir, f"{stem}.json"))


def badge_label(kind: str) -> str:
    """종류 → 배지 라벨 (없으면 빈 문자열)."""
    return KIND_LABELS.get(kind, "")
