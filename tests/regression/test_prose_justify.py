"""v8.5.1 — 일반 보고서 줄글 양끝 정렬 회귀 (사용자 요청 2026-08-01).

회귀 배경: 일반 보고서(freeform_essay) 본문은 왼쪽 정렬이라 오른쪽 끝단이
들쭉날쭉했다("뒤죽박죽"). 르포(reportage) 템플릿은 v8.2.15 부터 `.rep-prose`
에 양끝 정렬이 걸려 있어 단정한데, 일반 보고서만 빠져 있었다.

가드 대상 — 줄글 블록마다 3종 조합이 *함께* 걸려 있어야 한다:
  ① text-align:justify      — 양끝 정렬
  ② text-align-last:left    — 문단 마지막 줄은 늘리지 않음 (justify 전형 결함 차단)
  ③ word-break:keep-all     — 한글은 어절 단위로만 줄바꿈 (단어 중간 절단 금지)
①만 걸고 ②를 빠뜨리면 마지막 줄이 억지로 벌어지고, ③을 빠뜨리면 한글 단어가
줄바꿈에서 잘린다. 셋 중 하나라도 빠지면 본 테스트가 실패한다.

비-줄글(제목·라벨·사진 캡션·인용 디스플레이)은 양끝 정렬 대상이 아니다 —
figcaption 은 v5.5.11 에서 명시적 left 로 고정된 이력이 있어 함께 가드한다.
"""

from __future__ import annotations

import re
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "src" / "templates" / "archetypes"
_FREEFORM = (_TEMPLATE_DIR / "freeform_essay.html").read_text(encoding="utf-8")
_REPORTAGE = (_TEMPLATE_DIR / "reportage.html").read_text(encoding="utf-8")

# 일반 보고서의 *줄글* 블록 — 본문/모순/머리글/비유/맺음말/감시신호 설명.
JUSTIFIED_BLOCKS = [
    ".freeform-prose",
    ".contradiction-prose",
    ".freeform-lede",
    ".freeform-analogy-body",
    ".freeform-closing-body",
    ".epilogue-watch-desc",
]


def _rule_body(css: str, selector: str) -> str:
    """`selector{...}` 의 선언 블록만 추출 (첫 매치, 자식 셀렉터 제외)."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"셀렉터 {selector} 규칙을 템플릿에서 찾지 못함"
    return m.group(1)


def test_prose_blocks_are_justified() -> None:
    """줄글 6종 모두 양끝 정렬 3종 조합을 갖춰야 한다."""
    for sel in JUSTIFIED_BLOCKS:
        body = _rule_body(_FREEFORM, sel)
        assert "text-align:justify" in body, f"{sel}: 양끝 정렬(text-align:justify) 누락"
        assert "text-align-last:left" in body, (
            f"{sel}: text-align-last:left 누락 — 문단 마지막 줄이 억지로 벌어진다"
        )
        assert "word-break:keep-all" in body, (
            f"{sel}: word-break:keep-all 누락 — 한글 단어가 줄바꿈에서 잘린다"
        )


def test_prose_paragraph_children_keep_justify() -> None:
    """p / li 는 자체 text-align 을 갖는 규칙이 있어 부모 상속만으론 부족하다."""
    for sel in (".freeform-prose p", ".freeform-prose li", ".contradiction-prose p"):
        body = _rule_body(_FREEFORM, sel)
        assert "text-align:justify" in body, f"{sel}: 자식 규칙에 양끝 정렬 누락"
        assert "text-align-last:left" in body, f"{sel}: 자식 규칙에 text-align-last 누락"


def test_reportage_prose_still_justified() -> None:
    """르포도 같은 규칙 유지 — 두 템플릿의 본문 정렬은 항상 정합 (v8.2.15/v8.5.1)."""
    body = _rule_body(_REPORTAGE, ".rep-prose")
    assert "text-align:justify" in body
    assert "text-align-last:left" in body
    assert "word-break:keep-all" in body


def test_figcaption_stays_left() -> None:
    """사진 캡션은 줄글이 아니다 — v5.5.11 의 명시적 left 고정이 유지돼야 한다."""
    body = _rule_body(_FREEFORM, ".freeform-figure figcaption")
    assert "text-align:left" in body, "figcaption 의 명시적 left 가 사라짐 (v5.5.11 회귀)"
    assert "text-align:justify" not in body
