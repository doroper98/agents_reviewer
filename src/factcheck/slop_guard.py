"""AI 상투 문형 가드 — WRITE-AP-29 (v8.8.0, 사용자 지시 2026-10-28).

사용자 원문: "니가 작성하는 문구에 이런 내용이 없도록 강하게 쪼여. 정말 ai slop 느껴지는
문구들이거든." 사실 대신 비유·여운으로 문장을 끝내는 틀이다 — "세 겹의 문제가 눌려 있는
지점", "같은 자리로 돌아온다", "다음 계약서에 그대로 적힌다", "~로 읽힌다" 등.
발행본 666건 실측(2026-10-28): '~로 읽힌다' 111건에 269회, '청구서' 은유 30건,
문장 끝 '~가 남는다' 36건, 'N겹' 17건, '이유가 여기에 있다' 19건.

세 겹으로 막는다.
1. 작성 — ``prompt_block()`` 이 composer SYSTEM_PROMPT 에 금지 목록을 넣는다(이 모듈의
   ``SLOP_PATTERNS`` 가 목록 SSOT. 문체 정본 docs/REPORT_STYLE_GUIDE.md §2.4 와 정합 테스트).
2. 검출 — ``find_slop_flags()`` 가 사용자에게 보이는 텍스트에서 결정적으로 찾는다.
3. 교정 — orchestrator 가 검출 문장을 ``fix_instructions()`` 로 묶어 Opus 보완 패스에 넘긴다
   (Codex 사실 검수 *전* 이라 다시 쓴 문장도 검수를 받는다). 잔존은 로그로 남긴다.

정규식은 문형의 *틀* 을 잡는다. 같은 틀의 변형(숫자·명사 교체)도 걸리게 넓게 두되,
일상 서술과 겹치는 것은 문장 끝 위치로 좁혔다(예: '남는다' 는 문장 끝일 때만).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Awaitable, Callable

from pydantic import BaseModel

from src.factcheck.deterministic_guards import GuardFlag

if TYPE_CHECKING:
    from src.models import ComposedReport

logger = logging.getLogger(__name__)

FLAG = "ai_slop_phrase"


class SlopPattern(BaseModel):
    """금지 문형 1종. ``example`` 은 사용자가 지적한 원문(또는 실측 발행본 문장)."""

    name: str
    regex: str
    example: str
    instead: str


SLOP_PATTERNS: tuple[SlopPattern, ...] = (
    SlopPattern(
        name="converging_arrows",
        regex=(
            r"((화살|갈래|흐름)[^.?!\n]{0,20}한\s*(곳|점|지점|자리)(으)?로\s*(모인|모여|모이|수렴)"
            r"|(두|세|네|다섯|여섯|여러)\s*(개의\s*|가지\s*)?[가-힣]{1,6}[이가]\s*한\s*(곳|자리|지점)(에|으로|로))"
        ),
        example="N가지 화살이 한곳으로 모인다",
        instead="무엇과 무엇이 같은 결과로 이어지는지 주어와 사실로 쓴다",
    ),
    SlopPattern(
        name="shook_at_once",
        regex=r"한\s*번에[^.?!\n]{0,15}(흔들|들어왔|들어온|겹쳤|겹친|몰려|몰렸|터졌)",
        example="ㅁㅁㅁ가 한 번에 흔들었다",
        instead="무엇이 얼마나 움직였는지 수치로 쓴다",
    ),
    SlopPattern(
        name="n_layers",
        regex=r"(두|세|네|다섯|여러|몇)\s*겹",
        example="세 겹의 문제가 눌려 있는 지점",
        instead="문제를 '첫째·둘째' 나 이름으로 바로 나열한다",
    ),
    SlopPattern(
        name="pressed_point",
        regex=r"눌려\s*있는\s*(지점|자리|곳)",
        example="~가 눌려 있는 지점",
        instead="어떤 조건이 겹치는지 그대로 쓴다",
    ),
    SlopPattern(
        name="sets_direction",
        regex=r"(방향|향방)을\s*(정한다|가른다|결정한다)",
        example="앞으로 ㅁㅁㅁ가 ㅁㅁ의 방향을 정한다",
        instead="'X가 오르면 Y, 내리면 Z' 처럼 조건과 결과로 쓴다",
    ),
    SlopPattern(
        name="returns_same_place",
        regex=r"(같은|제)\s*자리로\s*돌아",
        example="같은 자리로 돌아온다",
        instead="결론을 한 번 더 말하지 말고 문단을 끝낸다",
    ),
    SlopPattern(
        name="read_this_way",
        regex=r"읽으면\s*이렇다",
        example="ㅁㅁ로 읽으면 이렇다",
        instead="해석 예고 없이 바로 내용을 쓴다",
    ),
    SlopPattern(
        name="decided_elsewhere",
        regex=r"아니라[^.?!\n]{0,40}에서\s*(난다|갈린다|결정된다)",
        example="승부는 이제 화면이 아니라 공정에서 난다",
        instead="'경쟁의 초점이 A에서 B로 옮겨 갔다' 처럼 근거와 함께 평서문으로",
    ),
    SlopPattern(
        name="why_its_news",
        regex=r"(진짜\s*뉴스인\s*이유|이유[도가는]\s*(바로\s*)?(거기|여기)(에)?\s*있다)",
        example="한국 부품 장비 회사에 이 발표가 진짜 뉴스인 이유도 거기 있다",
        instead="누구에게 어떤 영향(수주·매출·일정)이 있는지 직접 쓴다",
    ),
    SlopPattern(
        name="ledger_metaphor",
        regex=(
            r"((계약서|청구서|성적표|영수증|장부|명세서)에\s*(그대로\s*)?"
            r"(적힌다|찍힌다|올라간다|남는다)|줄의\s*청구서|청구서(가|는)?\s*"
            r"(한꺼번에\s*)?(도착|날아|돌아|쌓|기다))"
        ),
        example="다음 계약서에 그대로 적힌다 / ~가 말하고 있는 N줄의 청구서",
        instead="비용·계약 조건을 실제 항목과 수치로 쓴다",
    ),
    SlopPattern(
        name="where_it_stands",
        regex=r"서\s*있는\s*자리",
        example="서 있는 자리",
        instead="처지·위치를 지표(점유율·순위·실적)로 쓴다",
    ),
    SlopPattern(
        name="reads_as",
        regex=r"(으)?로\s*읽(힌|힐|히|혀)",
        example="~만 보면 ~로 읽힌다",
        instead="추정이면 '~로 보인다', 사실이면 단정형으로 쓴다",
    ),
    SlopPattern(
        name="says_and_unsaid",
        regex=r"말하지\s*않는\s*것",
        example="~이 말하는 것, 그리고 말하지 않는 것",
        instead="발표에 빠진 항목을 직접 짚는다",
    ),
    SlopPattern(
        name="what_remains",
        regex=r"남는다(?=\s*[.?!]|\s*$)",
        example="~의 NN 할이 남는다 / ~가 남는다",
        instead="남은 과제·수치를 주어와 함께 평서문으로 쓴다",
    ),
    SlopPattern(
        name="rises_up",
        regex=r"올라온다(?=\s*[.?!]|\s*$)",
        example="~가 올라온다",
        instead="무엇이 언제 발표·제출·부상했는지 쓴다",
    ),
)

_COMPILED: tuple[tuple[SlopPattern, re.Pattern[str]], ...] = tuple(
    (p, re.compile(p.regex)) for p in SLOP_PATTERNS
)
# 문장 경계 — 마침표·물음표·느낌표(소수점 제외)와 줄바꿈.
_SENT_END = re.compile(r"(?<!\d)[.?!](?!\d)|\n")


def _sentence_at(text: str, start: int, end: int) -> str:
    """매치가 든 문장 한 개를 돌려준다 (보완 지시에 그대로 인용)."""
    left = 0
    for m in _SENT_END.finditer(text, 0, start):
        left = m.end()
    right_m = _SENT_END.search(text, end)
    right = right_m.end() if right_m else len(text)
    return text[left:right].strip()


def _blocks(report: "ComposedReport") -> list[tuple[str, str]]:
    """검사 대상 — 보완 패스가 다시 쓸 수 있는 사용자 노출 텍스트."""
    out: list[tuple[str, str]] = []
    if report.headline:
        out.append(("headline", report.headline))
    if report.deck:
        out.append(("deck", report.deck))
    for i, sec in enumerate(report.sections):
        if sec.heading:
            out.append((f"sections[{i}].heading", sec.heading))
        if sec.prose:
            out.append((f"sections[{i}].prose", sec.prose))
    if report.contradictions_heading:
        out.append(("contradictions_heading", report.contradictions_heading))
    if report.closing:
        out.append(("closing", report.closing))
    if report.broadcast_summary:
        out.append(("broadcast_summary", report.broadcast_summary))
    return out


def find_slop_flags(report: "ComposedReport") -> list[GuardFlag]:
    """보고서에서 금지 문형을 찾는다. 같은 문장은 한 번만(첫 패턴으로) 기록."""
    flags: list[GuardFlag] = []
    for location, text in _blocks(report):
        seen: set[str] = set()
        for pat, rx in _COMPILED:
            for m in rx.finditer(text):
                sentence = _sentence_at(text, m.start(), m.end())
                if not sentence or sentence in seen:
                    continue
                seen.add(sentence)
                flags.append(GuardFlag(
                    guard="slop_guard",
                    flag=FLAG,
                    location=location,
                    quote=sentence,
                    detail=f"{pat.name}: «{m.group(0)}» — {pat.instead}",
                    severity="medium",
                ))
    return flags


def fix_instructions(flags: list[GuardFlag]) -> list[str]:
    """검출 문장 → Opus 보완 패스용 지시."""
    return [
        f"[문체·강제 WRITE-AP-29] {f.location}: «{f.quote}» — AI 상투 문형({f.detail}). "
        "이 문장만 다시 쓴다. 비유·여운 없이 주어와 사실(수치·날짜·주체)로 직설한다. "
        "추정이던 문장은 추정 표현('~로 보인다' 등)을 유지하고 단정으로 바꾸지 않는다. "
        "수치·사실을 새로 만들거나 바꾸지 않는다. 다른 상투 문형으로 갈아끼우지 않는다."
        for f in flags
    ]


def prompt_block() -> str:
    """composer SYSTEM_PROMPT 용 금지 목록 (SLOP_PATTERNS 에서 생성 — 사본 없음)."""
    lines = [
        "- **★ AI 상투 문형 절대 금지 (WRITE-AP-29, 사용자 최우선)**: 사실을 말하는 대신",
        "  비유·여운·예고로 문장을 끝내는 틀은 AI 가 쓴 글의 표지다. 아래 틀과 그 변형",
        "  (숫자·명사만 바꾼 것)을 본문·제목·부제·요약 어디에도 쓰지 않는다. 시스템이",
        "  결정적으로 검출해 다시 쓰게 한다. 대신 주어·사실·수치로 직설한다.",
    ]
    for p in SLOP_PATTERNS:
        lines.append(f"  · ✗ '{p.example}' → {p.instead}")
    return "\n".join(lines) + "\n"


def _prose_chars(report: "ComposedReport") -> int:
    return sum(len(s.prose or "") for s in report.sections)


async def enforce_slop_rewrite(
    report: "ComposedReport",
    context: object,
    reviser: object,
    *,
    publication_date: str,
    report_format: str = "",
    notify: "Callable[[str], Awaitable[None]] | None" = None,
) -> "tuple[ComposedReport, list[GuardFlag], list[GuardFlag]]":
    """검출 → Opus 보완 1회 → 재검출. (최종 보고서, 교정 전 지적, 교정 후 잔존) 반환.

    보완본이 원본보다 나빠지면(지적이 줄지 않음 / 본문이 15% 넘게 줄어듦 / 호출 실패)
    원본을 그대로 쓴다 — 문체 교정이 내용을 잃게 해선 안 된다.
    """
    before = find_slop_flags(report)
    if not before:
        return report, [], []
    if notify is not None:
        try:
            await notify(f"✍️ 문체 교정 (Opus): AI 상투 문형 {len(before)}곳 다시 쓰는 중…")
        except Exception:  # noqa: BLE001 — 알림 실패가 교정을 막지 않음
            pass
    try:
        revised = await reviser.revise_for_facts(  # type: ignore[attr-defined]
            report, context,
            fix_instructions=fix_instructions(before),
            publication_date=publication_date,
            report_format=report_format or "standard",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[slop_guard] 보완 호출 실패 — 원본 유지: %s", exc)
        return report, before, before
    if revised is report or not getattr(revised, "sections", None):
        return report, before, before
    after = find_slop_flags(revised)
    if len(after) >= len(before):
        logger.warning("[slop_guard] 보완 후에도 줄지 않음(%d→%d) — 원본 유지", len(before), len(after))
        return report, before, before
    if _prose_chars(revised) < 0.85 * _prose_chars(report):
        logger.warning(
            "[slop_guard] 보완본 본문이 15%% 넘게 줄어 원본 유지 (%d→%d자)",
            _prose_chars(report), _prose_chars(revised),
        )
        return report, before, before
    return revised, before, after
