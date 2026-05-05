"""V5 Phase 7 — Desk Editor (Plan §16).

신문사 데스크 등급의 *시스템 QA*. Phase 1~6 의 부분 책임자들이 못 보는
*전체 패키지* 의 일관성·발행 적격성을 판정. **publish / hold / KILL** 권한.

[Plan §16.3 — Logical 7-rubric] (원고 검토, JSON 입력)
1. Headline-Body 정합
2. Deck-Conclusion 정합
3. 섹션 흐름의 수렴성
4. 차트 횡적 중복 (ChartCritic 이 못 잡음)
5. Watch_signal 의 예측력
6. 출처-주장 비율
7. Smell test (출판 적격성)

[Plan §16.4 — Visual 8-rubric] (페이지 프루프, screenshots 입력)
SSOT: docs/DESK_VISUAL_RUBRIC.md (append-only).

[Plan §16.6 — 자동 KILL_RULES (Logical 5종 + Visual 3종)]
다음 중 *둘 이상* 충족 시 자동 KILL (LLM 판단 X, 결정적 룰):

    Logical:
      insufficient_sources       — len(sources) < 2
      insufficient_prose         — total_chars < lower_bound * 0.5
      contradiction_overload     — len(contradictions) > len(sections) / 2
      watch_signals_useless      — 모두 ambiguous 또는 빈 list
      core_intent_unanswered     — user_intent 가 어느 섹션도 다루지 않음

    Visual:
      majority_charts_visually_broken  — visual fail 비율 ≥ 50%
      mobile_layout_broken             — 시각-7 score ≤ 1
      theme_token_mismatch             — 시각-5 score ≤ 1

[Plan §16.7 — KILL 처리]
- Cloudflare 배포 차단 (HTML 만 dev/ 보존).
- 텔레그램 봇이 *명시적으로* 알림 (사유 + 권장 행동).
- Watchlist 등록 X.
- AP-V5-12 강제 — KILL 의 조용한 처리 금지.

[Plan §16.8 — HOLD 처리]
- 1회 재호출 cap (AP-V5-13 강제).
- 2번째 HOLD 시 publish-with-warning.
- HOLD_DISPATCH 매트릭스 (논리 issue + 시각 issue → lower editor 재호출).

[활성화 정책 — Phase 7 시점]
- v4.5.7 byte-equal 보존: ``Config.enable_desk_editor`` (env:
  ``V5_DESK_EDITOR=1``) opt-in flag. 디폴트 OFF.
- 꺼진 환경 — DeskEditor 호출 X. v4.5.7 의 minimal fallback 정책 그대로.
- 켜진 환경 — Phase 7A (Deterministic Gate) 통과 후 호출. Hard fail
  시 LLM 호출 안 됨 (AP-V5-29 강제).

Public API:
    from src.agents.desk_editor import (
        DeskEditor,
        DeskVerdict,
        DeskIssue,
        run_logical_kill_rules,
        run_visual_kill_rules,
        SYSTEM_PROMPT,
    )
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import BaseAgent
from src.config import Config

logger = logging.getLogger(__name__)


# ─── Visual Rubric SSOT 로더 (DESK_VISUAL_RUBRIC.md) ────────────────


_VISUAL_RUBRIC_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs" / "DESK_VISUAL_RUBRIC.md"
)


def _load_visual_rubric_excerpt() -> str:
    """DESK_VISUAL_RUBRIC.md 의 §1 + §2 (rubric 본문) 를 SYSTEM_PROMPT 에 포함.

    파일 미존재 시 minimal stub 반환 — 운영은 가능하지만 self-improving
    rubric 누적 항목 없이.
    """
    if not _VISUAL_RUBRIC_PATH.exists():
        return "(visual rubric file missing — fallback to Plan §16.4 8-rubric)"
    try:
        text = _VISUAL_RUBRIC_PATH.read_text(encoding="utf-8")
        # §1 Visual 8-rubric + §2 append-only 만 추출.
        if "## 1." in text:
            start = text.index("## 1.")
            end = text.index("## 3.") if "## 3." in text else len(text)
            return text[start:end]
        return text
    except Exception as e:
        logger.warning("[desk_editor] DESK_VISUAL_RUBRIC.md 로드 실패: %s", e)
        return ""


# ─── SYSTEM_PROMPT (Plan §16.3 + §16.4) ──────────────────────────────


_LOGICAL_7_RUBRIC = """[Logical 7-rubric — 원고 검토, JSON 입력]

각 항목 1~5 점수. score ≤ 2 면 issue 발생.

1. Headline-Body 정합 (Headline-Body Match)
   - 헤드라인이 주장한 것을 본문이 *실제로* 입증하는가
   - 회귀 사례: 헤드라인 'X가 결정적 변곡' → 결론 'X는 작은 변화 중 하나' → 과장
   - score 2 이하: severity=major, action="rewrite_headline"

2. Deck-Conclusion 정합 (Deck-Conclusion Match)
   - 부제(deck) 가 미리 보여준 결론이 마지막 섹션에서 *그대로* 도출되는가
   - 회귀 사례: 부제 단호한데 결론 양손잡이
   - score 2 이하: action="rewrite_deck" 또는 "rewrite_conclusion"

3. 섹션 흐름의 수렴성 (Section Flow Coherence)
   - 각 섹션이 *앞 섹션을 이어받아* 다음 섹션의 토대가 되는가
   - score 2 이하: action="reorder_sections" 또는 "add_bridge_paragraph"

4. 차트 횡적 중복 (Chart Cross-Redundancy)
   - 차트 두 개 이상이 *같은 사실을 다른 그림으로* 보여주는가
   - ChartCritic 은 차트 하나씩만 봐서 *못 잡음* — Desk 가 처음 보는 항목
   - score 2 이하: action="drop_chart_N"

5. Watch_signal 의 예측력 (Watch Signal Predictivity)
   - 모든 signal 이 'ambiguous' 면 *예측 가치 0*
   - 적어도 하나는 confirms_base 또는 rejects_base 여야
   - score 2 이하: action="rewrite_watch_signals"

6. 출처-주장 비율 (Source-Claim Ratio)
   - 강한 주장 (judgment / prediction) 의 evidence 충분한가
   - 회귀 사례: '5년 내 위기 70%' 강주장에 출처 1건만
   - score 2 이하: action="add_source_or_soften_claim"

7. Smell test (출판 적격성)
   - Foreign Affairs / FT / Bloomberg 데스크가 이 보고서를 *그대로 발행* 할까
   - 정량화 어려운 종합 판단. score 1~2 면 즉시 hold 또는 kill 후보
   - score 2 이하: action="kill_or_major_revision"
"""


def _build_system_prompt() -> str:
    visual_rubric = _load_visual_rubric_excerpt()
    return f"""당신은 신문사의 *데스크 / 매니징 에디터* 다. Phase 1~6 의 부분 편집자
(Composer / Editor / VisualPlanner / ChartCritic / LayoutTypesetter) 가 만든
완성된 보고서 패키지를 *전체적 정합성* 과 *시각 결함* 관점에서 검수하고
**publish / hold / KILL** 판정을 내린다.

두 갈래 입력:
- composed (JSON): 원고 검토 (논리·정합·발행 적격성).
- screenshots (image): 페이지 프루프 검수 (렌더된 HTML 시각 결함).

권한 위계:
- Revise 권한: lower editor (Editor / ChartCritic / Layout) 만. 발행 거부 권한 X.
- KILL 권한: 본 데스크 *단독*. 전체 보고서 publish/hold/KILL 판정.

발행 가치 없는 보고서는 *조용히 발행하지 않는다* — KILL 판정. v4.5.7 의
"어떻게든 발행 + minimal fallback" 정책의 정반대다.

{_LOGICAL_7_RUBRIC}

[Visual 8-rubric — 페이지 프루프 검수, screenshots 입력]
{visual_rubric}

판정 규칙:
- Logical 7 + Visual 8 = 15 항목 중 score ≤ 2 인 항목이 issue 로 등록.
- issue 가 0 + 모든 자동 KILL_RULES 미발화 → ``decision="publish"``.
- issue 가 있지만 fixable (대부분 lower editor 재호출 가능) → ``decision="hold"``.
- 자동 KILL_RULES 둘 이상 발화 또는 smell test (Logical 7) score 1 → ``decision="kill"``.

응답 JSON 스키마:

```json
{{
  "decision": "publish|hold|kill",
  "logical_rubric_scores": {{
    "headline_body": 1-5, "deck_conclusion": 1-5,
    "section_flow": 1-5, "chart_redundancy": 1-5,
    "watch_signal_predictivity": 1-5, "source_claim_ratio": 1-5,
    "smell_test": 1-5
  }},
  "visual_rubric_scores": {{
    "labels_clipping": 1-5, "map_zoom": 1-5,
    "marks_in_viewport": 1-5, "text_overflow": 1-5,
    "color_consistency": 1-5, "prose_chart_alignment": 1-5,
    "mobile_responsive": 1-5, "aesthetic_balance": 1-5
  }},
  "issues": [
    {{
      "severity": "minor|major|blocker",
      "domain": "logical|visual",
      "rubric": "headline_body|...",
      "description": "1문장",
      "suggested_action": "rewrite_headline|drop_chart_N|...",
      "target_module": "composer|editor|chart_critic|layout|renderer",
      "visual_evidence_idx": null
    }}
  ],
  "kill_reason": "decision='kill' 일 때만 1문장 사유"
}}
```

JSON 외 텍스트 출력 금지.
"""


# 모듈 로드 시 1회 빌드.
SYSTEM_PROMPT = _build_system_prompt()


# ─── DeskVerdict / DeskIssue 모델 ────────────────────────────────────


class DeskIssue(BaseModel):
    severity: Literal["minor", "major", "blocker"] = "major"
    domain: Literal["logical", "visual"] = "logical"
    rubric: str = ""
    description: str = ""
    suggested_action: str = ""
    target_module: Literal[
        "composer", "editor", "chart_critic", "layout",
        "renderer", "visual_planner",
    ] = "composer"
    visual_evidence_idx: int | None = None

    model_config = ConfigDict(extra="allow")


class DeskVerdict(BaseModel):
    decision: Literal["publish", "hold", "kill"]
    logical_rubric_scores: dict[str, int] = Field(default_factory=dict)
    visual_rubric_scores: dict[str, int] = Field(default_factory=dict)
    issues: list[DeskIssue] = Field(default_factory=list)
    kill_reason: str = ""
    # 자동 KILL_RULES 발화 추적 (Plan §16.6).
    auto_kill_rules_triggered: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# ─── Plan §16.6 — 결정적 KILL_RULES (LLM 호출 X) ─────────────────────


def run_logical_kill_rules(composed: dict[str, Any], mode: str = "standard") -> list[str]:
    """Logical 5종 자동 KILL_RULES (Plan §16.6).

    LLM 호출 0. composed dict 만 보고 결정적 판정. 둘 이상 발화 시
    DeskEditor 가 즉시 KILL.
    """
    triggered: list[str] = []

    # insufficient_sources — Plan §16.6
    sources = composed.get("sources") or []
    if len(sources) < 2:
        triggered.append("insufficient_sources")

    # insufficient_prose
    sections = composed.get("sections") or []
    total_chars = sum(len(((s or {}).get("prose") or "")) for s in sections)
    lower_bound = {"fast": 1500, "standard": 3500, "deep": 6000}.get(mode, 3500)
    if total_chars < lower_bound * 0.5:
        triggered.append("insufficient_prose")

    # contradiction_overload
    contradictions = composed.get("contradictions") or []
    if sections and len(contradictions) > len(sections) / 2:
        triggered.append("contradiction_overload")

    # watch_signals_useless
    signals = composed.get("watch_signals") or []
    if not signals:
        triggered.append("watch_signals_useless")
    else:
        all_ambiguous = all(
            isinstance(s, dict) and (s.get("direction") or "") == "ambiguous"
            for s in signals
        )
        if all_ambiguous:
            triggered.append("watch_signals_useless")

    return triggered


def run_visual_kill_rules(
    visual_rubric_scores: dict[str, int],
    *,
    chart_total: int = 0,
    chart_visual_fail_count: int = 0,
) -> list[str]:
    """Visual 3종 자동 KILL_RULES (Plan §16.6)."""
    triggered: list[str] = []

    # majority_charts_visually_broken
    if chart_total > 0 and chart_visual_fail_count >= chart_total * 0.5:
        triggered.append("majority_charts_visually_broken")

    # mobile_layout_broken — 시각-7 score ≤ 1
    mobile_score = visual_rubric_scores.get("mobile_responsive", 5)
    if mobile_score <= 1:
        triggered.append("mobile_layout_broken")

    # theme_token_mismatch — 시각-5 score ≤ 1
    color_score = visual_rubric_scores.get("color_consistency", 5)
    if color_score <= 1:
        triggered.append("theme_token_mismatch")

    return triggered


def evaluate_auto_kill(
    composed: dict[str, Any],
    visual_rubric_scores: dict[str, int],
    mode: str = "standard",
    *,
    chart_total: int = 0,
    chart_visual_fail_count: int = 0,
) -> tuple[bool, list[str]]:
    """Plan §16.6 의 통합 — 둘 이상 발화 시 자동 KILL.

    Returns:
        (should_kill, triggered_rules_list)
    """
    logical = run_logical_kill_rules(composed, mode)
    visual = run_visual_kill_rules(
        visual_rubric_scores,
        chart_total=chart_total,
        chart_visual_fail_count=chart_visual_fail_count,
    )
    triggered = logical + visual
    # Plan §16.6 — *둘 이상* 충족 시 자동 KILL.
    should_kill = len(triggered) >= 2
    return should_kill, triggered


# ─── Plan §16.8 — HOLD_DISPATCH 매트릭스 ─────────────────────────────


HOLD_DISPATCH: dict[str, tuple[str, str]] = {
    # Logical issue → composer / editor / chart_critic 재호출
    "rewrite_headline":           ("composer", "headline_only"),
    "rewrite_deck":               ("composer", "deck_only"),
    "rewrite_conclusion":         ("editor", "section_last"),
    "reorder_sections":           ("editor", "structural"),
    "add_bridge_paragraph":       ("editor", "specific_section"),
    "drop_chart_N":               ("chart_critic", "force_drop"),
    "rewrite_watch_signals":      ("composer", "signals_only"),
    "add_source_or_soften_claim": ("composer", "section_specific"),
    "kill_or_major_revision":     ("composer", "full_rerun"),
    # Visual issue → renderer / chart_critic / layout 재호출
    "rerender_chart":              ("renderer", "chart_only"),
    "drop_chart":                  ("chart_critic", "force_drop"),
    "adjust_map_zoom_center":      ("visual_planner", "map_only"),
    "adjust_chart_scale":          ("renderer", "chart_only"),
    "adjust_layout":               ("layout", "specific_section"),
    "shorten_text":                ("editor", "section_specific"),
    "reapply_theme":               ("renderer", "css_rebuild"),
    "adjust_responsive_breakpoints": ("layout", "responsive_review"),
    "major_layout_revision":       ("layout", "full_rerun"),
}


def dispatch_hold_action(action: str) -> tuple[str, str] | None:
    """suggested_action → (target_module, mode) 매핑. 미등재 시 None."""
    return HOLD_DISPATCH.get(action)


# ─── DeskEditor agent ────────────────────────────────────────────────


class DeskEditor(BaseAgent):
    """Plan §16.2 의 DeskEditor — Opus 4.7 vision (이미지 입력).

    [모델·예산 — Plan §16.2]
        DESK_MODEL = "claude-opus-4-7"  (vision capability 필수)
        MAX_TOKENS = 8000                (Logical only ~7K, Visual 추가 ~6K)
    """

    DESK_MODEL = "claude-opus-4-7"
    MAX_TOKENS = 8000

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="desk_editor",
            role="Desk Editor (편집장 / 매니징 에디터)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=False,
        )
        self.model_name = self.DESK_MODEL

    async def review(
        self,
        composed: dict[str, Any],
        rendered_html_path: str | Path | None = None,
        screenshots: list[Any] | None = None,
        mode: str = "standard",
        *,
        chart_total: int = 0,
        chart_visual_fail_count: int = 0,
    ) -> DeskVerdict:
        """Plan §16.2 시그니처.

        Phase 7A 가 이미 통과한 가정 (Hard fail 없음). 본 함수는 LLM 호출.
        Phase 7A 의 결정적 가드를 *우회* 하는 경로는 신설 X (AP-V5-29).

        [Fallback]
            LLM 호출 / 파싱 실패 시 publish-with-warning (Plan §20.3).
        """
        self._max_tokens_override = self.MAX_TOKENS

        # 입력 직렬화.
        context = {
            "composed_json": composed,
            "screenshots_count": len(screenshots or []),
            "mode": mode,
        }

        try:
            raw_text = await super().analyze(context)
            verdict = self._parse_verdict(raw_text)
        except Exception as e:
            logger.warning(
                "[desk_editor] LLM call or parse failed: %s. publish-with-warning.",
                e,
            )
            verdict = DeskVerdict(
                decision="publish",
                kill_reason=f"desk_editor_call_failed: {e}",
            )

        # Plan §16.6 — 결정적 KILL_RULES 가 *LLM 결과를 무관* 하게 발화.
        # AP-V5-14 (KILL_RULES 임의 약화 금지) 강제.
        should_kill, triggered = evaluate_auto_kill(
            composed,
            verdict.visual_rubric_scores,
            mode=mode,
            chart_total=chart_total,
            chart_visual_fail_count=chart_visual_fail_count,
        )
        if should_kill:
            verdict.decision = "kill"
            verdict.auto_kill_rules_triggered = triggered
            if not verdict.kill_reason:
                verdict.kill_reason = (
                    f"auto_kill_rules: {', '.join(triggered)}"
                )

        return verdict

    def _parse_verdict(self, raw_text: str) -> DeskVerdict:
        text = (raw_text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"DeskVerdict JSON parse failed: {e}") from e

        if not isinstance(data, dict):
            raise ValueError("DeskVerdict root must be JSON object")

        return DeskVerdict.model_validate(data)
