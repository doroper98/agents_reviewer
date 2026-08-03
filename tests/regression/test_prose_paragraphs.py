"""v8.5.7 — 본문 문단 구분 (WRITE-AP-27, 사용자 catch 2026-08-01).

"일반 보고서의 본문에서 단락 구분이 없으니 너무 읽기가 어려워. 단락, 문단 구분이
적절히 이뤄지면 훨씬 읽기 좋을거 같아. 적절한 들여쓰기도 있으면 좋겠어."

발행본 실물에서 한 섹션 본문이 **30줄짜리 벽** 으로 나왔다. 원인 두 겹:

  ① **렌더러** — ``_format_structured_text`` 가 문단 경계를 ``<br><br>`` 로만 냈다.
     ``<p>`` 가 하나도 안 생기니 CSS 의 ``.freeform-prose p{margin:...}`` 이 통째로
     죽은 규칙이었고(따라서 ``has-dropcap`` 의 ``p:first-child::first-letter`` 도
     한 번도 작동한 적이 없다), 문단 사이는 빈 줄 하나뿐이었다.
  ② **작성** — composer 가 ``\\n\\n`` 자체를 안 냈다. 프롬프트에 '한 문단 3~5문장'
     규칙이 *있었는데도* 지켜지지 않았다.

그래서 프롬프트 강화 + **결정적 분할**(문장 수 상한 초과 시 강제로 쪼갬)을 같이 건다.
프롬프트만 믿으면 같은 회귀가 반복된다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.agents.report_synthesizer import ReportSynthesizer as R

_ROOT = Path(__file__).resolve().parents[2]
_TPL = (_ROOT / "src" / "templates" / "archetypes" / "freeform_essay.html").read_text(
    encoding="utf-8"
)
_COMPOSER = (_ROOT / "src" / "agents" / "narrative_composer.py").read_text(encoding="utf-8")
_REPORTAGE_TPL = (_ROOT / "src" / "templates" / "archetypes" / "reportage.html").read_text(
    encoding="utf-8"
)


def _paras(text: str) -> list[str]:
    return re.findall(r"<p>(.*?)</p>", R._format_structured_text(text), re.S)


def _sentences(n: int) -> str:
    return " ".join(f"문장{i}이다." for i in range(1, n + 1))


# --------------------------------------------------------------------------
# ① 실제 <p> 를 만든다
# --------------------------------------------------------------------------


def test_emits_real_paragraph_elements() -> None:
    out = R._format_structured_text("앞 문단이다. 여기까지.\n\n뒤 문단이다. 끝이다.")
    assert out.count("<p>") == 2, (
        "문단이 <p> 로 안 나옴 — CSS 의 .freeform-prose p 규칙이 죽어 간격이 안 붙는다"
    )
    assert "<br><br>" not in out, "문단 경계가 아직 <br><br> 로 남음"


def test_single_newline_stays_inside_paragraph() -> None:
    """단일 줄바꿈은 문단 *안의* 개행이다 (문단을 쪼개면 안 된다)."""
    out = R._format_structured_text("한 줄.\n같은 문단 다음 줄.")
    assert out.count("<p>") == 1
    assert "<br>" in out


# --------------------------------------------------------------------------
# ② 문장 보존 — 유실·중복 금지 (실제로 밟은 버그)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 2, 5, 6, 9, 13, 21])
def test_no_sentence_lost_or_duplicated(n: int) -> None:
    """★ 고아 문장 병합에서 리스트를 mutate 하다 앞 문단을 덮어써 문장이 통째로
    사라지고 다른 문단이 복제된 버그가 있었다. 문장 집합은 항상 보존돼야 한다."""
    joined = " ".join(_paras(_sentences(n)))
    for i in range(1, n + 1):
        assert f"문장{i}이다." in joined, f"n={n}: 문장{i} 유실"
    assert joined.count("문장") == n, f"n={n}: 문장 중복 (기대 {n}, 실제 {joined.count('문장')})"


# --------------------------------------------------------------------------
# ③ 벽은 쪼개고, 이미 짧은 건 두고
# --------------------------------------------------------------------------


def test_wall_of_text_is_split() -> None:
    assert len(_paras(_sentences(20))) >= 4, "20문장 벽이 안 쪼개짐"


def test_short_prose_untouched() -> None:
    assert len(_paras(_sentences(R._MAX_SENTENCES_PER_P))) == 1, (
        "상한 이하인데 쪼갬 — 이미 잘 쓴 본문을 건드리면 안 된다"
    )


def test_no_orphan_single_sentence_paragraph() -> None:
    """마지막에 한 문장짜리 고아 문단이 남으면 안 된다."""
    for n in range(6, 30):
        last = _paras(_sentences(n))[-1]
        assert len(R._SENTENCE_SPLIT.split(last)) >= 2, f"n={n}: 고아 문단"


# --------------------------------------------------------------------------
# ④ 숫자를 문장 끝으로 오인하지 않는다
# --------------------------------------------------------------------------


def test_decimals_are_not_sentence_boundaries() -> None:
    src = ("가장 최근 WTI 가격은 7월 27일 종가 84.25달러이며, 그날 하루로는 8.16% 내렸다. "
           "브렌트유는 90.12달러로 마감했다. 한 달 약 24% 올랐다. 오늘 장이 검증 자리다. "
           "지수는 3,180.55로 마쳤다. 환율은 1,392.40원이었다. 금리는 2.75%다.")
    out = " ".join(_paras(src))
    for token in ("84.25달러", "8.16%", "90.12달러", "3,180.55", "1,392.40원", "2.75%"):
        assert token in out, f"{token} 가 깨짐"


# --------------------------------------------------------------------------
# ⑤ 블록 헤더는 본문과 붙어 있어야
# --------------------------------------------------------------------------


def test_block_header_keeps_its_body() -> None:
    paras = _paras("도입 문장이다. [핵심 판단] 그래서 이러하다.")
    hdr = [p for p in paras if "<strong>" in p]
    assert hdr, "블록 헤더 문단 없음"
    assert "그래서 이러하다." in hdr[0], "헤더와 본문이 다른 문단으로 갈라짐"


def test_empty_input_unchanged() -> None:
    assert R._format_structured_text("") == ""
    assert R._format_structured_text("   ").strip() == ""


# --------------------------------------------------------------------------
# ⑥ CSS — 간격 + 들여쓰기
# --------------------------------------------------------------------------


def _rule(selector: str, css: str | None = None) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css if css is not None else _TPL)
    assert m, f"{selector} 규칙 없음"
    return m.group(1)


@pytest.mark.parametrize("sel", [".freeform-prose p", ".contradiction-prose p"])
def test_paragraph_has_spacing_and_indent(sel: str) -> None:
    body = _rule(sel)
    assert "text-indent:1em" in body, f"{sel}: 첫 줄 들여쓰기 누락 (사용자 요청)"
    assert re.search(r"margin:0 0 1em", body), f"{sel}: 문단 아래 여백 누락"


def test_first_paragraph_is_also_indented() -> None:
    """v8.5.9 — 첫 문단도 들여쓴다 (사용자 지적: 왜 첫 문단만 안 되나).

    v8.5.7 은 '제목 아래라 어긋나 보인다'는 판단으로 `p:first-child{text-indent:0}`
    예외를 뒀으나, 문단마다 일관되게 들여쓰는 쪽으로 사용자가 결정했다.
    """
    for css, sel in ((_TPL, ".freeform-prose p:first-child"),
                     (_TPL, ".contradiction-prose p:first-child"),
                     (_REPORTAGE_TPL, ".rep-prose p:first-child")):
        assert re.search(re.escape(sel) + r"\s*\{[^}]*text-indent:0", css) is None, (
            f"{sel}: 첫 문단 들여쓰기 예외가 남아 있음 — 전 문단 일관 적용해야 한다"
        )


def test_dropcap_paragraph_stays_flush() -> None:
    """드롭캡은 첫 글자를 float 로 띄운다 — 들여쓰기를 주면 드롭캡이 밀려 깨진다.

    이건 취향이 아니라 렌더링 제약이므로 예외를 유지한다.
    """
    assert "text-indent:0" in _rule(".freeform-prose.has-dropcap p:first-child")


# --------------------------------------------------------------------------
# ⑦ 작성 단계 — 프롬프트 강령
# --------------------------------------------------------------------------


def test_composer_prompt_mandates_paragraph_breaks() -> None:
    assert "WRITE-AP-27" in _COMPOSER, "문단 강령이 프롬프트에 없음"
    for marker in ("3~5 문장", "\\n\\n", "최소 3문단"):
        assert marker in _COMPOSER, f"프롬프트에 '{marker}' 지시 누락"


# --------------------------------------------------------------------------
# ⑧ 르포도 같은 처우 (v8.5.8)
#
# 문단 분할은 v8.5.7 에서 공용 필터로 이미 적용됐다 (르포도 같은 `structured` 를
# 탄다 — 그 전까지 `.rep-prose p` 규칙이 <p> 부재로 죽어 있었다). 들여쓰기만 v8.5.8.
# --------------------------------------------------------------------------


def test_reportage_prose_has_spacing_and_indent() -> None:
    body = _rule(".rep-prose p", _REPORTAGE_TPL)
    assert "text-indent:1em" in body, "르포 첫 줄 들여쓰기 누락 (사용자 요청)"
    assert "margin:0 0 1.15em" in body, "르포 문단 아래 여백 누락"


def test_reportage_shares_the_paragraph_filter() -> None:
    """르포 템플릿이 같은 필터를 타야 문단 분할이 공짜로 따라온다."""
    assert "| structured" in _REPORTAGE_TPL, (
        "르포가 structured 필터를 안 쓰면 문단 분할이 일반 보고서에만 적용된다"
    )


def test_reportage_prompt_keeps_paragraph_mandate() -> None:
    """르포 작성 강령의 문단 규칙(일반보다 강함)이 유지돼야 한다."""
    assert "한 문단은 다섯 문장을 넘기지 않는다" in _COMPOSER
    assert "문단 서넛 이상" in _COMPOSER
