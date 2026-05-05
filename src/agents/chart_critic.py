"""V5 Phase 6 Gate B — Chart-Topic Fit Critic (Plan §13.3).

차트 spec + 인접 prose 를 받아 keep / replace / drop 판정. Sonnet 4.6 LLM
1회 호출 (~1K 토큰). Editor 가 *글* 을 본다면 ChartCritic 은 *논거-차트 결합*
을 본다 — 책임 분리.

[Plan §13.3 의 7개 핵심 질문]
1. 본 차트를 빼면 섹션 논거가 약해지나? (선례 오염 차단 — AP-V5-7)
2. takeaway 가 prose thesis 와 다른 정보를 주나, 같은 말 반복인가?
3. 데이터 형태에 차트 type 이 *최적* 인가? (AP-8)
4. prose 가 차트 데이터를 *직접* 인용하는가? (AP-V5-7)
5. 다른 차트와 *중복 정보* 인가? (총량 가드)
6. 지도 — 본문이 그 지역을 *명시적* 으로 다루는가? (AP-14)
7. takeaway 가 *공허* 한가? (당연한 관찰)

[Plan §13.8 운영 정책 — 느슨하지 않게]
- score ≥ 4 만 keep (3 은 ambiguous → drop)
- 보고서당 차트 ≥ 5 면 score 가장 낮은 차트부터 drop
- Critic 호출 실패 시 *drop* (보수적 fallback)

[Public API]
    from src.agents.chart_critic import (
        ChartCritic,
        ChartVerdict,
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


# ─── SYSTEM_PROMPT (Plan §13.3 그대로) ────────────────────────────────

SYSTEM_PROMPT = """당신은 데이터 시각화 비평가다. 보고서에 박히려는 차트를 본다.
다음 7개 질문에 차례로 답하고 최종 판정 (keep / replace / drop).

1. 본 차트를 *빼면* 이 섹션의 논거가 실질적으로 약해지는가?
   → 약해지지 않으면 즉시 drop. (선례 오염 차단 — AP-V5-7)

2. 차트의 takeaway 한 줄이 인접 prose 의 thesis 와 *다른* 정보를 주는가,
   *같은 말* 의 반복인가?
   → 같으면 drop.

3. 이 데이터 형태에 이 차트 type 이 *최적* 인가?
   - 5+ phase 시간 흐름 → gantt 가 아니라 timeline_strip 또는 본문 list
   - 0~1 정규화 안 된 좌표 데이터 → bubble 부적합
   - 라벨 ≥ 14자 + 항목 5개 이상 → bar 부적합
   → 최적이 아니면 replace + suggested_type.

4. 이 차트의 데이터가 *이 보고서의 prose* 에서 직접 인용되거나 참조되는가?
   (예: prose 가 'Brent $112' 언급 → 차트에 brent 그래프)
   → 직접 참조 0건이면 drop. 차트가 "주제 비슷해서 박힌" 선례 오염의 신호다.

5. 이 차트가 다른 차트와 *중복 정보* 를 보여주는가?
   → 중복이면 drop (보고서당 차트 ≤ 5 강제).

6. 지도라면 — 이 보고서의 본문이 그 지역을 *명시적으로 다루는가*?
   → 안 다루면 drop. (AP-14: 무관 지리 annotation 차단)

7. takeaway 가 *공허* 한가? ('변동성이 크다' / '의존도가 높다' 같은 당연한 관찰)
   → 공허하면 drop.

판정:
- keep: 5/7 이상 통과 + 결정적 질문 (1, 4, 6) 모두 통과
- replace: type 만 부적합 (3번만 fail), 다른 type 으로 살릴 수 있음
- drop: 그 외 모두

JSON 출력만 (마크다운 fence 허용):

```json
{
  "score": 1~5,
  "verdict": "keep|replace|drop",
  "reason": "1문장. 어느 질문에서 fail 했는지 명시.",
  "suggested_type": "replace 일 때만"
}
```
"""


# ─── ChartVerdict 모델 ────────────────────────────────────────────────


class ChartVerdict(BaseModel):
    """Plan §13.3 의 ChartVerdict."""

    score: int = Field(ge=1, le=5)
    verdict: Literal["keep", "replace", "drop"]
    reason: str = ""
    suggested_type: str | None = None

    model_config = ConfigDict(extra="forbid")


# Plan §13.8 — score ≥ 4 만 keep, 3 은 ambiguous → drop.
KEEP_SCORE_THRESHOLD = 4


def is_score_keep(score: int, verdict: str) -> bool:
    """Plan §13.8 운영 정책 — score ≥ 4 + verdict='keep' 만 진짜 keep."""
    return score >= KEEP_SCORE_THRESHOLD and verdict == "keep"


# ─── ChartCritic agent ───────────────────────────────────────────────


class ChartCritic(BaseAgent):
    """Plan §13.3 의 Sonnet 4.6 Critic.

    [모델·예산]
        CRITIC_MODEL = "claude-sonnet-4-6"  (Plan §13.3 명시)
        MAX_TOKENS = 1024                   (1차트당 ~1K, 보고서당 ~5K)

    [호출 정책]
        Critic 호출 실패 (timeout / parse error) 시 Plan §13.8 의 *drop*
        fallback. composer 가 emit 한 차트를 무조건 통과시키지 않는다.
    """

    CRITIC_MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 1024

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="chart_critic",
            role="Chart Critic (시각화 비평가)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=True,             # Sonnet 4.6 — light_model_name.
        )
        # config.model_name_light 가 sonnet-4-6 이라 그대로 사용.

    async def critique(
        self,
        chart_spec: dict[str, Any],
        section_prose: str,
        report_thesis: str = "",
    ) -> ChartVerdict:
        """Plan §13.3 시그니처.

        Args:
            chart_spec: Vega-Lite spec 또는 ComposedSection.charts dict.
            section_prose: 차트가 박힐 섹션의 prose.
            report_thesis: 보고서 전체 thesis (deck).

        Returns:
            ChartVerdict — score / verdict / reason / suggested_type.

        [Fallback]
            LLM 호출 / 파싱 실패 시 Plan §13.8 의 *보수적 drop* 판정 반환.
        """
        self._max_tokens_override = self.MAX_TOKENS

        context = {
            "chart_spec": chart_spec,
            "section_prose": (section_prose or "")[:1500],
            "report_thesis": (report_thesis or "")[:300],
        }

        try:
            raw_text = await super().analyze(context)
            return self._parse_verdict(raw_text)
        except Exception as e:
            logger.warning(
                "[chart_critic] LLM call or parse failed: %s. Defaulting to drop "
                "(Plan §13.8 보수적 fallback).",
                e,
            )
            if self.telemetry is not None:
                setattr(self.telemetry, "chart_critic_fallback", True)
            return ChartVerdict(
                score=1,
                verdict="drop",
                reason=f"critic call failed → drop (Plan §13.8): {e}",
            )

    def _parse_verdict(self, raw_text: str) -> ChartVerdict:
        """LLM 응답 → ChartVerdict."""
        text = (raw_text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"ChartVerdict JSON parse failed: {e}") from e

        if not isinstance(data, dict):
            raise ValueError("ChartVerdict root must be JSON object")
        return ChartVerdict.model_validate(data)


# ─── 결정적 fallback critique (LLM 0 — 회귀 테스트용) ─────────────────


def critique_via_heuristics(
    chart_spec: dict[str, Any],
    section_prose: str,
    report_thesis: str = "",
) -> ChartVerdict:
    """Plan §13.3 의 7개 질문 중 *결정적으로 답할 수 있는 4개* (1, 4, 5, 7)
    만 휴리스틱으로 평가.

    LLM 미호출 환경 / 회귀 테스트의 경계값 검증에 사용.
    """
    # Question 4 — prose 가 차트 데이터의 수치를 인용하나?
    from src.visual.evidence_dataset import (
        ensure_chart_data_cited_in_prose,
        extract_chart_numbers,
    )

    numbers = extract_chart_numbers(chart_spec)
    if numbers:
        ok, _ = ensure_chart_data_cited_in_prose(
            chart_spec, section_prose, min_citation_ratio=0.20
        )
        if not ok:
            return ChartVerdict(
                score=2,
                verdict="drop",
                reason="Q4 fail (heuristic): prose 가 차트 수치 인용 < 20% — 선례 오염 의심.",
            )

    # Question 7 — takeaway 공허도 (단순 키워드 매칭).
    title = (chart_spec.get("title") or "")
    if isinstance(title, dict):
        title = (title.get("text") or "") + " " + (title.get("subtitle") or "")
    note = chart_spec.get("note") or chart_spec.get("takeaway") or ""
    text_blob = (str(title) + " " + str(note)).lower()
    vacuous_phrases = [
        "변동성이 크다", "의존도가 높다", "중요하다", "주목할 만",
        "지속적으로", "대체로", "전반적으로",
    ]
    if any(p in text_blob for p in vacuous_phrases) and len(text_blob.strip()) < 30:
        return ChartVerdict(
            score=2,
            verdict="drop",
            reason="Q7 fail (heuristic): takeaway 공허 — 당연한 관찰.",
        )

    # 결정적 휴리스틱 통과 — score 4 keep.
    return ChartVerdict(
        score=4,
        verdict="keep",
        reason="heuristic pass (Q4 + Q7). LLM Critic 으로 본격 검수 필요.",
    )
