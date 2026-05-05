"""V5 Phase 2 — VisualPlanner agent (Plan §7.3).

REFACTOR_V5_PLAN.md §7 의 핵심:
    "VisualPlanner 가 *완성된 prose 를 읽고* 시각화를 결정하면, 차트가
    *논거를 강화하는 도구* 로 위치 정립."

[Phase 2 의 책임]
- 편집된 prose + EvidenceDataset[] + visual_constraints + thesis 를 받아
  Vega-Lite spec list 를 emit.
- 어느 섹션에 차트가 필요한지 판정 (필요 없으면 emit X — 사건당 0~3개).
- type / data / annotation 결정. 단 *V5 design token (색·폰트) 은 emit 안 함*
  — vega_adapter._apply_v5_theme 가 강제 (AP-V5-2).

[활성화 정책 — Phase 2 시점]
- v4.5.7 호출 경로 byte-equal 보존: opt-in flag.
- Config.enable_visual_planner (env: V5_VISUAL_PLANNER=1) 켜진 환경에서만
  Editor 후 단계로 호출.
- 디폴트 OFF — composer 의 chart emit 이 그대로 작동.

[Plan §20.3 Fallback]
- VisualPlanner 가 LLM 호출 / 파싱 실패 시: composer 가 emit 한 chart spec
  을 *그대로* 사용. 단 EvidenceDataset 검증 (Phase 2A) 는 여전히 적용 —
  source_id 가 없으면 drop.
- 본 모듈은 ``plan_or_passthrough()`` 로 fallback 경로 제공.

[Plan §7.6 차트 종류 — 무제한]
SYSTEM_PROMPT 가 다음 type 을 *예시* 로 명시:
- 기존 11종 (bar / donut / line / gantt / network / stacked / bubble /
  heatmap / dual_line / forecast / choropleth)
- 새 type (Sankey / Chord / Treemap / Streamgraph / Parallel Coordinates /
  Slope / Bump / Calendar heatmap / Radar / Bullet / Waterfall / Funnel /
  Density / Boxplot / Violin / Scatterplot matrix / Lollipop / Beeswarm)

단 mono 톤 + 45° 패턴 + 단일 액센트 규칙 강제 (vega_adapter 가 처리).

Public API:
    from src.agents.visual_planner import (
        VisualPlanner,
        plan_via_heuristics,
        SYSTEM_PROMPT,
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent
from src.config import Config
from src.state.models import (
    DraftReport,
    EvidenceDataset,
    VisualConstraints,
)
from src.visual.evidence_dataset import EvidenceDatasetGuard
from src.visual.vega_adapter import VegaSpecError, validate_vega_spec

logger = logging.getLogger(__name__)


# ─── SYSTEM_PROMPT (Plan §7.3 그대로) ────────────────────────────────────

SYSTEM_PROMPT = """당신은 사진 에디터 / 시각화 디자이너다. 편집장 (composer) 이 짠
prose 를 *완성된 후* 읽고, 어느 섹션에 어떤 시각화를 박을지 결정한다.

원칙:
- *prose 가 차트를 정당화* 해야 한다. 차트가 thesis 를 *강화* 하지 않으면 emit 하지 않는다.
- 사건당 차트 0~3개 권장. 4개 이상은 시각 피로 신호.
- 차트 type 은 *데이터 형태* 가 정한다. 다음 type 중 데이터에 가장 적합한 것:
  · 기존 안정 (Vega-Lite safe): bar / line / area / stacked / bubble / heatmap /
    donut / gantt / dual_line / forecast / choropleth.
  · 신규 가능 (Vega-Lite expressible): Sankey / Treemap / Slope / Bump /
    Streamgraph / Parallel Coordinates / Calendar heatmap / Radar / Bullet /
    Waterfall / Funnel / Density / Boxplot / Violin / Scatterplot matrix /
    Lollipop / Beeswarm.
- 데이터 출처 강제 — 차트 spec 의 ``data.values`` 는 *반드시* 입력으로 받은
  EvidenceDataset 의 rows 또는 그 transform 결과여야 한다 (AP-V5-24/26).
- spec 의 ``data.values[*].source_id`` 또는 spec 의 ``"source_ids"`` 필드에
  EvidenceDataset.source_ids 를 *명시* 한다.
- 색·폰트는 *결정하지 않는다*. spec 에 ``color`` / ``fill`` / ``font`` 필드를
  박지 않는다 — V5 vega_adapter 가 design token 으로 덮어쓴다 (AP-V5-2).

각 섹션에 대해 다음을 결정:
1. 차트가 필요한가? (수치 비교가 본문 이해에 결정적일 때만)
2. 어떤 type 이 *데이터 형태* 에 가장 적합한가?
3. 어느 단락 직후에 박을 것인가? (anchor_paragraph_idx)
4. Vega-Lite spec — $schema / data.values / mark / encoding / source_ids.

응답은 *반드시* 아래 JSON 스키마:

```json
{
  "exhibits": [
    {
      "section_idx": 0,
      "anchor_paragraph_idx": 2,
      "title": "차트 제목",
      "subtitle": "부제 (선택)",
      "takeaway": "이 차트가 보여주는 한 줄",
      "spec": {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": {"text": "...", "subtitle": "..."},
        "width": 560,
        "height": 280,
        "data": {"values": [{...}, {...}]},
        "mark": "...",
        "encoding": {...}
      },
      "source_ids": ["S-001", "S-002"]
    }
  ]
}
```

차트가 필요 없으면 ``exhibits: []``. 사건당 차트 ≤ 3 권고. JSON 외 텍스트
출력 금지.
"""


# ─── 결정적 fallback — heuristic visual planner (LLM 0) ─────────────────


def plan_via_heuristics(
    edited_report: DraftReport,
    datasets: list[EvidenceDataset],
    visual_constraints: VisualConstraints | None = None,
) -> list[dict[str, Any]]:
    """LLM 호출 없이 v4.5.7 의 ``ComposedSection.charts`` 를 그대로 통과시키는
    fallback. Phase 2 의 *opt-in flag 가 꺼진 환경* 에서 사용.

    각 차트 dict 를 *EvidenceDataset Guard* 통과 기준으로만 필터. type/data
    재해석은 하지 않음.

    Args:
        edited_report: Editor 또는 Composer 의 출력 (DraftReport.sections).
        datasets: Phase 2A 의 EvidenceDataset 목록.
        visual_constraints: ResearchDirector (Phase 1A) 의 must_have/forbidden.

    Returns:
        chart spec list — 각 element 는 v4.5.7 ComposedSection.charts 형식
        ({type, title, data, note?}). VisualPlanner LLM 의 emit 와 *호환*
        형식이지만 spec 자체는 v4.5.7 그대로.
    """
    out: list[dict[str, Any]] = []
    forbidden = set((visual_constraints.forbidden if visual_constraints else []) or [])

    sections = getattr(edited_report, "sections", None) or []
    guard = EvidenceDatasetGuard(datasets=datasets)

    for sec_idx, section in enumerate(sections):
        sec = section if isinstance(section, dict) else getattr(section, "model_dump", lambda: {})()
        charts = (sec or {}).get("charts") or []
        prose = (sec or {}).get("prose") or ""
        for chart in charts:
            if not isinstance(chart, dict):
                continue
            chart_type = (chart.get("type") or "").lower()
            if chart_type in forbidden:
                logger.info(
                    "[visual_planner] heuristic drop: section=%d type=%s — visual_constraints.forbidden",
                    sec_idx, chart_type,
                )
                continue
            # AP-V5-24/26 — Phase 2A guard 가 결정.
            verdict = guard.evaluate_chart(chart, prose=prose, require_prose_citation=False)
            if not verdict["passed"]:
                logger.info(
                    "[visual_planner] heuristic drop: section=%d type=%s — %s",
                    sec_idx, chart_type, "; ".join(verdict["issues"]),
                )
                continue
            out.append({
                "section_idx": sec_idx,
                "title": chart.get("title", ""),
                "type": chart_type,
                "data": chart.get("data"),
                "note": chart.get("note", ""),
                "source_ids": chart.get("source_ids") or chart.get("source_id") or [],
            })
    return out


# ─── VisualPlanner — LLM 호출 ──────────────────────────────────────────


class VisualPlanner(BaseAgent):
    """Plan §7.3 의 VisualPlanner.

    Phase 2 시점 — opt-in flag (`Config.enable_visual_planner`) 가 켜진
    환경에서만 호출. 꺼져 있으면 plan_via_heuristics 가 fallback.

    [모델·예산]
        PLANNER_MODEL = "claude-opus-4-7"
        MAX_TOKENS = 12000  (Plan §7.3)
    """

    PLANNER_MODEL = "claude-opus-4-7"
    MAX_TOKENS = 12000

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="visual_planner",
            role="Visual Planner (사진 에디터)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=False,
        )
        self.model_name = self.PLANNER_MODEL

    async def plan(
        self,
        edited_report: DraftReport,
        datasets: list[EvidenceDataset],
        visual_constraints: VisualConstraints | None = None,
        thesis: str = "",
    ) -> list[dict[str, Any]]:
        """Plan §8.4 의 VisualPlanner 시그니처.

        Returns:
            list of exhibit dict — 각 element 는 SYSTEM_PROMPT 의 응답 스키마.
            spec 은 Vega-Lite v5 형식 그대로. apply_theme_to_spec 후
            render_vega_lite 가 SVG 로 변환.
        """
        self._max_tokens_override = self.MAX_TOKENS

        # 입력 직렬화 — DraftReport / Datasets / Constraints.
        report_dump = (
            edited_report.model_dump(mode="json")
            if hasattr(edited_report, "model_dump")
            else dict(edited_report or {})
        )
        datasets_dump = [
            ds.model_dump(mode="json") if hasattr(ds, "model_dump") else dict(ds)
            for ds in (datasets or [])
        ]
        constraints_dump = (
            visual_constraints.model_dump(mode="json")
            if hasattr(visual_constraints, "model_dump")
            else dict(visual_constraints or {})
        )

        context = {
            "edited_report": {
                "headline": report_dump.get("headline", ""),
                "deck": report_dump.get("deck", ""),
                "sections": report_dump.get("sections", []),
                "closing": report_dump.get("closing", ""),
            },
            "datasets": datasets_dump,
            "visual_constraints": constraints_dump,
            "thesis": thesis,
        }

        try:
            raw_text = await super().analyze(context)
            return self._parse_exhibits(raw_text, datasets=datasets)
        except Exception as e:
            logger.warning(
                "[visual_planner] LLM call or parse failed: %s. "
                "Falling back to plan_via_heuristics (Plan §20.3).",
                e,
            )
            if self.telemetry is not None:
                setattr(self.telemetry, "visual_planner_fallback", True)
            return plan_via_heuristics(edited_report, datasets, visual_constraints)

    async def plan_or_passthrough(
        self,
        edited_report: DraftReport,
        datasets: list[EvidenceDataset],
        visual_constraints: VisualConstraints | None = None,
        thesis: str = "",
    ) -> list[dict[str, Any]]:
        """opt-in flag 가 꺼진 환경에서도 *모든 사건* 에 exhibit list 를 emit.

        Phase 2 인수 기준 #2 ("VisualPlanner 가 prose 를 읽고 1종 새 chart
        type 을 사건에 맞게 emit 하는 사례 1건 demo") 의 *측정 가능 형태*.
        """
        try:
            return await self.plan(
                edited_report=edited_report,
                datasets=datasets,
                visual_constraints=visual_constraints,
                thesis=thesis,
            )
        except Exception:
            return plan_via_heuristics(edited_report, datasets, visual_constraints)

    def _parse_exhibits(
        self,
        raw_text: str,
        *,
        datasets: list[EvidenceDataset] | None = None,
    ) -> list[dict[str, Any]]:
        """LLM 응답 → exhibit list. spec 검증 + EvidenceDataset Guard 적용."""
        text = (raw_text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"VisualPlanner JSON parse failed: {e}") from e

        if not isinstance(data, dict):
            raise ValueError("VisualPlanner root must be a JSON object")

        exhibits = data.get("exhibits") or []
        if not isinstance(exhibits, list):
            raise ValueError("VisualPlanner.exhibits must be list")

        # 각 exhibit 검증 — Vega-Lite spec + EvidenceDataset Guard.
        guard = EvidenceDatasetGuard(datasets=datasets or [])
        out: list[dict[str, Any]] = []
        for ex in exhibits:
            if not isinstance(ex, dict):
                continue
            spec = ex.get("spec")
            if not isinstance(spec, dict):
                logger.info("[visual_planner] drop: exhibit spec 없음")
                continue

            # Phase 6 Gate A 의 사전 가드.
            try:
                validate_vega_spec(spec)
            except VegaSpecError as e:
                logger.info("[visual_planner] drop: spec 검증 실패 — %s", e)
                continue

            # Phase 2A — source_ids 필수.
            chart_for_guard = {
                **spec,
                "source_ids": ex.get("source_ids") or [],
                "title": (spec.get("title") or {}).get("text") if isinstance(spec.get("title"), dict) else spec.get("title", ""),
            }
            verdict = guard.evaluate_chart(chart_for_guard, prose="", require_prose_citation=False)
            if not verdict["passed"]:
                logger.info(
                    "[visual_planner] drop: %s — %s",
                    ex.get("title", ""), "; ".join(verdict["issues"]),
                )
                continue

            out.append(ex)

        return out
