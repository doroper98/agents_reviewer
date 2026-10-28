"""WRITE-AP-29 — AI 상투 문형 가드 회귀 (v8.8.0, 사용자 지시 2026-10-28).

사용자 원문: "니가 작성하는 문구에 이런 내용이 없도록 강하게 쪼여. 정말 ai slop 느껴지는
문구들이거든." 사용자가 든 문형 전부와 발행본 실측 문장이 검출돼야 하고, 평범한 사실
문장은 걸리면 안 된다. 금지 목록은 작성 프롬프트·문체 정본(STYLE_GUIDE)과 어긋나면 안 된다.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from src.factcheck.slop_guard import (
    SLOP_PATTERNS,
    enforce_slop_rewrite,
    find_slop_flags,
    fix_instructions,
)
from src.models import ComposedReport, ComposedSection, ContextAnalysis

# (문장, 걸려야 할 패턴) — 앞쪽은 사용자 지적 원문, 뒤쪽은 발행본 실측 문장.
SLOP_SENTENCES = [
    ("규제와 금리, 환율이라는 세 가지 화살이 한곳으로 모인다.", "converging_arrows"),
    ("엔비디아 발표가 반도체 지수를 한 번에 흔들었다.", "shook_at_once"),
    ("세 겹의 문제가 눌려 있는 지점이다.", "n_layers"),
    ("수출 규제가 눌려 있는 지점을 건드렸다.", "pressed_point"),
    ("앞으로 환율이 외국인 수급의 방향을 정한다.", "sets_direction"),
    ("결국 논쟁은 같은 자리로 돌아온다.", "returns_same_place"),
    ("이번 실적을 수급으로 읽으면 이렇다.", "read_this_way"),
    ("그래서 이 카테고리 승부는 이제 화면이 아니라 공정에서 난다.", "decided_elsewhere"),
    ("한국 부품 장비 회사에 이 발표가 진짜 뉴스인 이유도 거기 있다.", "why_its_news"),
    ("저 수준의 공정을 누가 대량으로 받아 주느냐가 다음 계약서에 그대로 적힌다.", "ledger_metaphor"),
    ("한국 반도체가 서 있는 자리는 좁아졌다.", "where_it_stands"),
    ("지수만 보면 강세장으로 읽힌다.", "reads_as"),
    ("발표문이 말하는 것, 그리고 말하지 않는 것.", "says_and_unsaid"),
    ("결국 이익의 7할이 남는다.", "what_remains"),
    ("결국 비용 문제가 남는다.", "what_remains"),
    ("이제 재고 문제가 올라온다.", "rises_up"),
    ("관세가 말하고 있는 세 줄의 청구서.", "ledger_metaphor"),
    # 발행본 실측 (2026-07~10)
    ("이 변화는 우연이 아니라 세 겹의 압력이 누적된 결과다.", "n_layers"),
    ("메모리 슈퍼사이클의 끝이 단기간에 오지 않는 구조적 이유가 여기에 있다.", "why_its_news"),
    ("반등을 사면서도 하락 대비를 놓지 않은 상태로 읽힌다.", "reads_as"),
    ("4월의 세 사건은 그 청구서가 한꺼번에 도착한 결과다.", "ledger_metaphor"),
    ("따라서 판별은 채널 자체의 존재 여부가 아니라 그 운영 방식에서 갈린다.", "decided_elsewhere"),
    # 발행본 섹션 제목에서 본 변형 (같은 틀, 다른 명사)
    ("세 충격이 한 자리에 쌓였다.", "converging_arrows"),
    ("오늘의 좌표, 네 흐름이 한 번에 들어왔다.", "shook_at_once"),
    ("주말 한 번에 네 개의 변곡이 겹쳤다.", "shook_at_once"),
]

CLEAN_SENTENCES = [
    "삼성전자 주가는 3.5% 올라 7만 2,300원에 마감했다.",
    "재고는 지난 분기보다 12% 줄었다.",
    "남는 현금은 배당과 자사주 매입에 쓴다고 회사는 밝혔다.",
    "회사는 3분기 실적을 30일 발표한다.",
    "그는 회의에서 아무 말도 하지 않았다.",
    "외국인은 이날 코스피에서 4,120억 원을 순매도했다.",
    "환율이 오르면 수출주에 유리하고, 내리면 내수주에 유리하다.",
    "코스피는 한 번에 3% 넘게 올랐다.",
    "세 회사가 한 컨소시엄을 꾸렸다.",
]


def _report(*prose: str, headline: str = "코스피 3% 반등", summary: str = "") -> ComposedReport:
    return ComposedReport(
        headline=headline,
        deck="외국인 순매수 전환",
        sections=[ComposedSection(heading=f"섹션{i}", prose=p) for i, p in enumerate(prose)],
        broadcast_summary=summary,
    )


@pytest.mark.parametrize(("sentence", "pattern"), SLOP_SENTENCES)
def test_each_slop_form_is_caught(sentence: str, pattern: str) -> None:
    flags = find_slop_flags(_report("앞 문장은 평범하다. " + sentence + " 뒤 문장도 평범하다."))
    assert len(flags) == 1, flags
    assert flags[0].detail.startswith(pattern)
    assert flags[0].quote == sentence  # 보완 지시에 문장 하나만 정확히 인용


@pytest.mark.parametrize("sentence", CLEAN_SENTENCES)
def test_plain_sentences_are_not_flagged(sentence: str) -> None:
    assert find_slop_flags(_report(sentence)) == []


def test_every_pattern_has_a_case() -> None:
    covered = {p for _, p in SLOP_SENTENCES}
    assert covered == {p.name for p in SLOP_PATTERNS}


def test_headline_and_broadcast_summary_are_checked() -> None:
    flags = find_slop_flags(_report(
        "평범한 본문이다.", headline="한국이 서 있는 자리",
        summary="오늘 시장은 강세장으로 읽힌다.",
    ))
    assert {f.location for f in flags} == {"headline", "broadcast_summary"}


def test_fix_instruction_quotes_sentence_and_keeps_certainty() -> None:
    [instr] = fix_instructions(find_slop_flags(_report("지수만 보면 강세장으로 읽힌다.")))
    assert "«지수만 보면 강세장으로 읽힌다.»" in instr
    assert "추정" in instr and "바꾸지 않는다" in instr


# ── 프롬프트·문체 정본 정합 ─────────────────────────────────────


def test_composer_prompt_lists_every_banned_form() -> None:
    from src.agents.narrative_composer import SYSTEM_PROMPT, NarrativeComposer

    for p in SLOP_PATTERNS:
        assert p.example in SYSTEM_PROMPT, p.name
    assert "WRITE-AP-29" in NarrativeComposer.REVISE_SYSTEM_PROMPT


def test_style_guide_lists_every_banned_form() -> None:
    guide = Path("docs/REPORT_STYLE_GUIDE.md").read_text(encoding="utf-8")
    for p in SLOP_PATTERNS:
        assert p.example in guide, p.name


def test_reportage_block_does_not_model_slop() -> None:
    # 르포 블록의 예문이 상투 문형을 *가르치고* 있었다 ('…로 읽힐 여지가 크다', '한 겹씩 벗긴 뒤').
    from src.agents.narrative_composer import _REPORTAGE_BLOCK

    hits = [p.name for p in SLOP_PATTERNS if re.search(p.regex, _REPORTAGE_BLOCK)]
    assert hits == []
    assert "겹씩" not in _REPORTAGE_BLOCK


# ── 교정 패스 ──────────────────────────────────────────────────


class _Reviser:
    def __init__(self, fn):
        self.fn = fn
        self.calls: list[list[str]] = []

    async def revise_for_facts(self, report, context, *, fix_instructions, publication_date, report_format):
        self.calls.append(fix_instructions)
        return self.fn(report)


def _run(coro):
    return asyncio.run(coro)


def _replace_prose(report: ComposedReport, prose: str) -> ComposedReport:
    new = report.model_copy(deep=True)
    new.sections[0].prose = prose
    return new


SLOPPY = "외국인이 돌아왔다. 지수만 보면 강세장으로 읽힌다. 거래대금은 12조 원이었다."
FIXED = "외국인이 돌아왔다. 지수만 보면 강세장으로 보인다. 거래대금은 12조 원이었다."


def test_enforce_rewrites_flagged_sentences() -> None:
    rev = _Reviser(lambda r: _replace_prose(r, FIXED))
    out, before, after = _run(enforce_slop_rewrite(
        _report(SLOPPY), ContextAnalysis(), rev, publication_date="2026-10-28",
    ))
    assert out.sections[0].prose == FIXED
    assert len(before) == 1 and after == []
    assert "읽힌다" in rev.calls[0][0]


def test_enforce_skips_llm_when_clean() -> None:
    rev = _Reviser(lambda r: r)
    out, before, after = _run(enforce_slop_rewrite(
        _report(FIXED), ContextAnalysis(), rev, publication_date="2026-10-28",
    ))
    assert rev.calls == [] and before == [] and after == []


def test_enforce_keeps_original_when_revision_is_worse() -> None:
    report = _report(SLOPPY)
    # 지적이 줄지 않음 → 원본
    rev = _Reviser(lambda r: _replace_prose(r, SLOPPY + " 결국 비용 문제가 남는다."))
    out, _, _ = _run(enforce_slop_rewrite(report, ContextAnalysis(), rev, publication_date="x"))
    assert out is report
    # 본문을 크게 잘라냄 → 원본 (문체 교정이 내용을 잃게 하면 안 된다)
    rev = _Reviser(lambda r: _replace_prose(r, "외국인이 돌아왔다."))
    out, _, _ = _run(enforce_slop_rewrite(report, ContextAnalysis(), rev, publication_date="x"))
    assert out is report


def test_enforce_survives_reviser_failure() -> None:
    def boom(_r):
        raise RuntimeError("cli down")

    report = _report(SLOPPY)
    out, before, after = _run(enforce_slop_rewrite(
        report, ContextAnalysis(), _Reviser(boom), publication_date="x",
    ))
    assert out is report and len(before) == len(after) == 1


def test_revision_merge_carries_broadcast_summary() -> None:
    from src.agents.narrative_composer import NarrativeComposer

    merged = NarrativeComposer._merge_text_revision(
        _report("본문", summary="강세장으로 읽힌다."),
        {"broadcast_summary": "강세장으로 보인다."},
    )
    assert merged.broadcast_summary == "강세장으로 보인다."


def test_orchestrator_runs_style_pass_before_codex_loop() -> None:
    src = Path("src/orchestrator.py").read_text(encoding="utf-8")
    style = src.index("enforce_slop_rewrite(")
    codex = src.index("# -- Phase 2.5 (V6): Codex fact-critic 루프")
    assert style < codex  # 다시 쓴 문장도 Codex 사실 검수를 받는다
