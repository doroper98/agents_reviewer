"""V5 Phase 1 — Editor Pass (Plan §5).

Drafting + Editing 2 호출. NarrativeComposer (drafting) 직후에 같은 Opus 4.7
이 *editor 페르소나* 로 다시 들어가 자기 글을 비평·재집필.

[Plan §5.2 의 Why]
- 같은 LLM 도 *editor 페르소나* 로 다시 들어가면 자기 글의 약점을 본다.
- 작성 중에는 *생산* 모드, 편집 중에는 *축약/날카롭게* 모드 — 인지 경제 분리.
- 토큰: composer 1회 + editor 1회 = 약 30~40K. 단일 호출 32K 와 거의 동일.

[Plan §5.4 — 7-rubric]
1. 군더더기 (Padding)         — 같은 결론 반복, "주목할 만한 점은" 진부어
2. 결론의 칼날 (Punch)         — 섹션 끝이 결론인가 요약인가
3. 모순 봉합 (Anti-pattern #5) — contradictions 가 *대립* 으로 살아있는가
4. 차트-본문 결합 (Binding)    — 차트 직전 thesis + 직후 해석
5. 분량 비대칭 (Asymmetry)     — peak 섹션이 충분히 긴가
6. 신선함 (Originality)        — 일반 readout 외 독자적 통찰
7. 외래어 / 전문용어 풀이      — 약어 / 외래어 첫 등장 시 한 줄 풀이

[Plan §5.6 인수 기준]
- 2-call → 3-call (Context → Compose → Edit) — opt-in flag 시점에 활성
- Editor 호출 실패 시 graceful fallback — DraftReport 그대로 사용
- 기존 사건 5건 재실행, watch_signal / contradictions 개수 동일 유지

[활성화 정책 — Phase 1 시점]
- v4.5.7 호출 경로 byte-equal 보존: ``Config.enable_editor_pass`` (env:
  ``V5_EDITOR_PASS=1``) opt-in flag. 디폴트 OFF.
- 켜진 환경 — Composer (drafting) 직후 Editor 호출. AnalysisBrief.thesis
  와 Composer 출력만 입력 (RawContext / EvidencePack 미입력 — Plan §4.4
  의 입력 제한 강제).

Public API:
    from src.agents.editor import (
        Editor,
        EditedReport,
        EditorCritique,
        SectionScore,
        SECTION_SCORE_RUBRICS,
        SYSTEM_PROMPT,
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import BaseAgent
from src.config import Config

logger = logging.getLogger(__name__)


# ─── 7-rubric SSOT (Plan §5.4) ─────────────────────────────────────


SECTION_SCORE_RUBRICS: list[str] = [
    "padding",        # 군더더기
    "punch",          # 결론의 칼날
    "contradiction",  # 모순 봉합 여부
    "binding",        # 차트-본문 결합도
    "asymmetry",      # 분량 비대칭 (전체 평가)
    "originality",    # 신선함
    "vocabulary",     # 외래어 / 전문용어 풀이
]


# ─── SYSTEM_PROMPT (Plan §5.4 그대로) ──────────────────────────────


SYSTEM_PROMPT = """당신은 *카피 에디터 / 시니어 에디터* 다. 편집장 (composer) 이 짠 보고서
초고를 받아 *비평하고 재집필* 한다. 같은 Opus 4.7 모델이지만 *드라프팅*
모드에서 *편집* 모드로 들어와 자기 글의 약점을 본다.

[7-rubric — 각 섹션을 다음 7개 항목으로 점수화 + 수정 지시]

1. 군더더기 (Padding)
   - 같은 결론을 다른 표현으로 두 번 말하는가
   - "주목할 만한 점은", "결론적으로" 같은 진부어가 살아있는가
   - 한 단락이 두 주장을 섞고 있는가
   → 잘라낼 문장과 단락을 *명시* 한다.

2. 결론의 칼날 (Punch)
   - 각 섹션 마지막 문장이 *결론* 인가 *요약* 인가
   - 섹션이 끝났을 때 독자가 "그래서?" 라고 묻게 하는가
   → 결론 문장을 재집필한다.

3. 모순 봉합 여부 (Anti-pattern #5)
   - contradictions 가 본문에서 *대립* 으로 살아있는가, *둘 다 맞다* 식 봉합인가
   - 어느 쪽 손을 들었는지 명시되었는가
   → 봉합되었으면 분리해 날카롭게 다듬는다.

4. 차트-본문 결합도 (Chart-Prose Binding)
   - 차트 직전 단락이 thesis 한 줄을 미리 제시하는가
   - 차트 직후 단락이 패턴을 한 단계 *해석* 하는가 (반복 X)
   - 차트가 본문 흐름 *없이* 단독으로 박혀있는가
   → 결합이 약하면 본문 단락을 신설하거나 재작성한다.

5. 분량 비대칭 (Length Asymmetry)
   - 결정적 섹션이 보조 섹션보다 *충분히 긴가*
   - 균질 분포 (모든 섹션이 비슷한 길이) 면 *감점*
   → 짧게 할 섹션과 길게 할 섹션을 명시한다.

6. 신선함 (Originality)
   - 일반 뉴스 readout 으로도 도출 가능한 결론만 있는가
   - 특정 데이터·메커니즘에서만 나오는 *독자적* 통찰이 있는가
   - "공식 narrative 의 빈틈" 을 짚었는가
   → 평범한 결론이 박힌 섹션은 더 깊이 파거나 잘라낸다.

7. 외래어 / 전문용어 풀이 (Vocabulary Discipline)
   - 영어 약어·외래어 첫 등장 시 한 줄 풀이가 있는가
   - 학부생이 막힘없이 읽을 수 있는가
   → 막히는 지점에 풀이를 신설한다.

[보존 규칙]
- contradictions 의 *개수* 는 줄이지 않는다 (Anti-pattern #5 보호).
- watch_signals 의 *개수* 는 줄이지 않는다.
- 사실 / 출처 / 수치를 임의로 *추가* 또는 *제거* 하지 않는다 — 글 다듬기만.
- 새 LLM 호출 / 추가 사실 검색 X.

응답 JSON 스키마:

```json
{
  "critique": [
    {
      "section_idx": 0,
      "scores": {
        "padding": 1-10, "punch": 1-10, "contradiction": 1-10,
        "binding": 1-10, "asymmetry": "(전체 평가 1줄)",
        "originality": 1-10, "vocabulary": 1-10
      },
      "issues": ["1줄 진단 ×N"],
      "actions": ["rewrite_paragraph_3", "sharpen_conclusion"]
    }
  ],
  "revisions": [
    {
      "section_idx": 0,
      "action": "rewrite|cut|keep",
      "new_heading": "...",
      "new_kicker": "...",
      "new_prose": "재집필 본문",
      "cuts": ["문단 5 통째로 삭제 (섹션 2 와 중복)"]
    }
  ],
  "final": {
    "headline": "...",
    "deck": "...",
    "sections": [
      {"heading": "...", "kicker": "...", "prose": "...", "charts": [...]}
    ],
    "closing": "...",
    "watch_signals": [...],
    "contradictions": [...]
  }
}
```

JSON 외 텍스트 출력 금지.
"""


# ─── 결과 모델 ────────────────────────────────────────────────────


class SectionScore(BaseModel):
    """Plan §5.4 의 7-rubric 섹션별 점수."""

    section_idx: int
    padding: int = Field(ge=0, le=10, default=5)
    punch: int = Field(ge=0, le=10, default=5)
    contradiction: int = Field(ge=0, le=10, default=5)
    binding: int = Field(ge=0, le=10, default=5)
    asymmetry: str = ""             # 전체 평가 1줄
    originality: int = Field(ge=0, le=10, default=5)
    vocabulary: int = Field(ge=0, le=10, default=5)
    issues: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class SectionRevision(BaseModel):
    section_idx: int
    action: Literal["rewrite", "cut", "keep"] = "keep"
    new_heading: str = ""
    new_kicker: str = ""
    new_prose: str = ""
    cuts: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class EditorCritique(BaseModel):
    """Editor 의 분석 결과 — critique + revisions + final."""

    critique: list[SectionScore] = Field(default_factory=list)
    revisions: list[SectionRevision] = Field(default_factory=list)
    final: dict = Field(default_factory=dict)   # ComposedReport-like dict

    model_config = ConfigDict(extra="allow")


class EditedReport(BaseModel):
    """Phase 1 Editor 의 최종 산출. Composer DraftReport 의 *재집필본*.

    구조는 ComposedReport 와 동일 — 후속 단계 (VisualPlanner / Renderer)
    가 그대로 받아 처리.
    """

    headline: str = ""
    deck: str = ""
    sections: list[dict] = Field(default_factory=list)
    closing: str = ""
    watch_signals: list[dict] = Field(default_factory=list)
    contradictions: list[dict] = Field(default_factory=list)
    confidence_summary: str = ""
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    embedded_map: dict | None = None

    # Editor 메타 — 개수 보존 검증 + telemetry.
    editor_critique: EditorCritique | None = None
    editor_pass_applied: bool = False

    model_config = ConfigDict(extra="allow")


# ─── Plan §5.6 인수 기준 — 보존 검증 헬퍼 ────────────────────────


def assert_signal_count_preserved(
    draft: dict[str, Any],
    edited: dict[str, Any],
) -> tuple[bool, str]:
    """watch_signals 의 *개수* 보존 검증. Editor 가 신호를 *축소* 하지 않게.

    Plan §5.6 인수 기준 — "watch_signal_개수·contradictions 개수 동일 유지".

    Returns:
        (passed, reason)
    """
    n_draft_ws = len(draft.get("watch_signals", []) or [])
    n_edited_ws = len(edited.get("watch_signals", []) or [])
    if n_edited_ws < n_draft_ws:
        return False, (
            f"watch_signals 개수 감소: draft {n_draft_ws} → edited {n_edited_ws}. "
            f"Plan §5.6 의 인수 기준 위반."
        )

    n_draft_cn = len(draft.get("contradictions", []) or [])
    n_edited_cn = len(edited.get("contradictions", []) or [])
    if n_edited_cn < n_draft_cn:
        return False, (
            f"contradictions 개수 감소: draft {n_draft_cn} → edited {n_edited_cn}. "
            f"Anti-pattern #5 (모순 봉합) 회귀."
        )
    return True, "preserved"


# ─── Anti-pattern 진부어 차단 (보너스 — 결정적 후처리) ───────────


_CLICHE_PHRASES = [
    "주목할 만한 점은",
    "결론적으로",
    "주지하다시피",
    "이는 매우 중요하며",
    "전반적으로",
    "대체로",
    "전체적으로 볼 때",
]


def detect_cliches(text: str) -> list[str]:
    """Plan §5.4 의 padding rubric (Q1) 의 결정적 보조 — 진부어 매칭."""
    if not text:
        return []
    out = []
    for phrase in _CLICHE_PHRASES:
        if phrase in text:
            out.append(phrase)
    return out


# ─── Editor agent ────────────────────────────────────────────────


class Editor(BaseAgent):
    """Plan §5.3 의 Editor — composer 와 *동일* 모델 (Opus 4.7), system prompt
    만 다름.

    [모델·예산 — Plan §5.3]
        EDITOR_MODEL = "claude-opus-4-7"
        MAX_TOKENS = 16000   (편집은 분량 *유지 또는 축소*. 32K 불필요)
    """

    EDITOR_MODEL = "claude-opus-4-7"
    MAX_TOKENS = 16000

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="editor",
            role="Editor (카피 에디터)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=False,
        )
        self.model_name = self.EDITOR_MODEL

    async def critique_and_revise(
        self,
        draft: dict[str, Any],
        thesis: str = "",
        mode: str = "standard",
    ) -> EditedReport:
        """Plan §5.3 시그니처.

        Args:
            draft: Composer 의 출력 (ComposedReport dict 또는 DraftReport).
            thesis: AnalysisBrief.thesis (Phase 1A 의 출력) — 짧게 (<300자).
                EvidencePack 미입력 — Plan §4.4 의 입력 제한 강제.
            mode: fast / standard / deep — max_tokens 미세 조정.

        Returns:
            EditedReport — critique 적용된 재집필본. 실패 시 draft 그대로.
        """
        # mode 별 토큰 — 편집은 항상 16K 충분.
        self._max_tokens_override = self.MAX_TOKENS

        context = {
            "draft": draft,
            "thesis": (thesis or "")[:300],   # 짧게.
            "mode": mode,
        }

        try:
            raw_text = await super().analyze(context)
            critique = self._parse_critique(raw_text)
        except Exception as e:
            logger.warning(
                "[editor] LLM call or parse failed: %s. Falling back to draft "
                "(Plan §5.6 graceful fallback).", e,
            )
            if self.telemetry is not None:
                setattr(self.telemetry, "editor_skipped", True)
            return _draft_to_edited(draft, applied=False)

        # final 추출 — critique 의 final 필드.
        final = critique.final if isinstance(critique.final, dict) else {}
        if not final:
            logger.warning("[editor] critique.final 비어있음 — draft fallback.")
            return _draft_to_edited(draft, applied=False)

        # 보존 검증 (Plan §5.6 인수 기준).
        ok, reason = assert_signal_count_preserved(draft, final)
        if not ok:
            logger.warning(
                "[editor] 인수 기준 위반: %s — draft fallback.", reason,
            )
            if self.telemetry is not None:
                setattr(self.telemetry, "editor_signal_loss", reason)
            return _draft_to_edited(draft, applied=False)

        # 성공 — final 을 EditedReport 로 변환 + critique 보존.
        edited = EditedReport.model_validate({
            **final,
            "editor_critique": critique.model_dump(),
            "editor_pass_applied": True,
        })
        return edited

    def _parse_critique(self, raw_text: str) -> EditorCritique:
        text = (raw_text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"EditorCritique JSON parse failed: {e}") from e

        if not isinstance(data, dict):
            raise ValueError("EditorCritique root must be JSON object")
        return EditorCritique.model_validate(data)


def _draft_to_edited(draft: dict[str, Any], *, applied: bool) -> EditedReport:
    """draft 를 그대로 EditedReport 로 변환 (graceful fallback 경로)."""
    return EditedReport.model_validate({
        **draft,
        "editor_pass_applied": applied,
    })
