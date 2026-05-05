"""V5 Phase 3 — Layout Typesetter (Plan §10).

편집된 보고서 + 시각화 spec → 섹션별 layout primitive 결정.

[Plan §10.2 — 9종 layout (정본 동결, AP-V5-3 강제)]
    standard / hero_map / hero_chart / split_2col / sidebar_callout /
    qna_panel / timeline_strip / signature_summary / exhibit_grid

[Plan §10.3 — 결정 가이드]
- 보고서당 standard 가 60~70% 비중. 그 외는 *액센트* 로만.
- hero_map / hero_chart 는 보고서당 최대 1~2개. 도입부 또는 결정적 섹션.
- signature_summary 는 첫 또는 마지막 섹션 1개로 한정.
- 같은 layout 을 *연속 2섹션* 에 배치 금지 (리듬).
- 사건이 지리적이면 hero_map 을 1~2번째 섹션에 배치 권장.
- exhibit_grid 는 차트 3개 이상 모인 섹션로 한정.

[Plan §10.5 인수 기준]
- 9종 layout 모두 데모 가능 (단 HTML 템플릿은 별도 작업).
- LayoutTypesetter 호출 실패 시 모든 섹션이 'standard' fallback.

[활성화 정책 — Phase 3 시점]
- v4.5.7 호출 경로 byte-equal 보존: ``Config.enable_layout_typesetter``
  (env: ``V5_LAYOUT_TYPESETTER=1``) opt-in flag. 디폴트 OFF.
- HTML 템플릿 (templates/layouts/) 은 별도 작업 — 본 모듈은 *결정 로직* 만.

Public API:
    from src.agents.layout_typesetter import (
        LayoutTypesetter,
        SYSTEM_PROMPT,
        plan_layouts_via_heuristics,
        LAYOUT_VOCAB,
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent
from src.config import Config
from src.state.models import LayoutAssignment, LayoutPrimitive

logger = logging.getLogger(__name__)


# Plan §10.2 — 9종 vocab SSOT (AP-V5-3 강제 동결).
LAYOUT_VOCAB: list[str] = [
    "standard",
    "hero_map",
    "hero_chart",
    "split_2col",
    "sidebar_callout",
    "qna_panel",
    "timeline_strip",
    "signature_summary",
    "exhibit_grid",
]


# ─── SYSTEM_PROMPT (Plan §10.3 그대로) ─────────────────────────────


SYSTEM_PROMPT = """당신은 *레이아웃 디자이너 / 식자공* 이다. Editor 가 다듬은 보고서 + 시각화
spec 을 받아 *각 섹션의 layout primitive* 를 결정한다.

[9종 layout primitive — 이 안에서만 선택]
- standard            : 기본 (kicker / heading / lede / prose / charts).
- hero_map            : 풀-bleed 지도 + 짧은 caption + 본문 별 섹션.
                        지리 사건 도입에 적합 (호르무즈, 대만 해협 등).
- hero_chart          : 풀-bleed 차트 1개 + 짧은 caption.
                        결정적 단일 차트 (Brent 30일 등).
- split_2col          : 좌측 prose / 우측 차트 또는 fact_grid.
                        비교·대조 (한국 vs 일본 의존도 등).
- sidebar_callout     : 본문 80% + 우측 사이드바 (analogy 또는 pull_quote).
                        어려운 개념 풀이 동반 분석.
- qna_panel           : Q&A 형식 (질문 → 짧은 답변 ×3~5).
                        '흔한 오해' / FAQ 톤.
- timeline_strip      : 가로 또는 세로 타임라인 + 사건별 미니 코멘트.
                        사건 경과 압축.
- signature_summary   : 큰 글씨 헤드라인 + 부제 1문장 + 본문 X.
                        챕터 표지 / 보고서 결론.
- exhibit_grid        : 차트 2~4개 그리드 + 짧은 종합 caption.
                        멀티-앵글 데이터 비교.

[결정 원칙]
- 보고서당 standard 가 60~70% 비중. 그 외 layout 은 *액센트* 로만.
- hero_map / hero_chart 는 보고서당 최대 1~2개. 도입부 또는 결정적 섹션.
- signature_summary 는 보고서 첫 또는 마지막 섹션 1개로 한정.
- 같은 layout 을 *연속 2섹션* 에 배치 금지 (리듬).
- 사건이 지리적이면 hero_map 을 1~2번째 섹션에 배치 권장.
- exhibit_grid 는 차트 3개 이상 모인 섹션로 한정.
- *전략 모드* 보고서는 'decision_brief' 를 받지만 그건 별도 vocab —
  본 prompt 에선 분석 모드 9종만 다룬다.

응답 JSON 스키마:

```json
{
  "assignments": [
    {
      "section_idx": 0,
      "layout": "standard|hero_map|hero_chart|split_2col|sidebar_callout|qna_panel|timeline_strip|signature_summary|exhibit_grid",
      "why": "1줄 정당화 (예: '도입부 + 호르무즈 지리 사건')"
    }
  ]
}
```

JSON 외 텍스트 출력 금지.
"""


# ─── 결정적 heuristic fallback (LLM 0) ────────────────────────────


def plan_layouts_via_heuristics(
    sections: list[dict[str, Any]],
    *,
    has_map: bool = False,
    is_strategic: bool = False,
    section_count: int | None = None,
) -> list[LayoutAssignment]:
    """LLM 호출 없이 결정적 layout 부여. 회귀 테스트의 기준값.

    Plan §10.3 의 결정 원칙을 결정적으로 따름. 60~70% standard + 액센트.
    """
    if not sections:
        return []

    n = section_count or len(sections)
    out: list[LayoutAssignment] = []
    used: list[str] = []          # 연속 배치 차단용
    hero_count = 0                 # hero_* 보고서당 ≤ 2

    for idx, section in enumerate(sections):
        sec = section if isinstance(section, dict) else {}
        charts = sec.get("charts") or []
        n_charts = len(charts)
        prose = sec.get("prose") or ""
        kicker = sec.get("kicker") or ""
        heading = sec.get("heading") or ""

        layout: LayoutPrimitive = "standard"   # type: ignore[assignment]
        why = "default"

        # 1. 첫 섹션 + 지리 사건 → hero_map.
        if idx == 0 and has_map and hero_count < 2:
            if used and used[-1] != "hero_map":
                layout = "hero_map"; why = "지리 사건 도입부"; hero_count += 1
            elif not used:
                layout = "hero_map"; why = "지리 사건 도입부"; hero_count += 1

        # 2. 마지막 섹션 + 결론 키워드 → signature_summary (보고서당 1개).
        elif idx == n - 1 and (
            "결론" in heading or "결론" in kicker or "summary" in heading.lower()
        ) and "signature_summary" not in used:
            layout = "signature_summary"; why = "보고서 결론 섹션"

        # 3. 차트 ≥ 3 → exhibit_grid.
        elif n_charts >= 3:
            if not used or used[-1] != "exhibit_grid":
                layout = "exhibit_grid"; why = f"차트 {n_charts}개 그리드"

        # 4. Q&A 패턴 (?, 묻는다, 의문) → qna_panel.
        elif (kicker.startswith("Q") or "?" in heading or "흔한 오해" in heading
              or "FAQ" in heading.upper()):
            if not used or used[-1] != "qna_panel":
                layout = "qna_panel"; why = "Q&A 패턴"

        # 5. 타임라인 키워드 → timeline_strip.
        elif any(k in heading for k in ["흐름", "타임라인", "경과"]) or any(
            k in kicker for k in ["타임라인", "단계"]
        ):
            if not used or used[-1] != "timeline_strip":
                layout = "timeline_strip"; why = "사건 경과 압축"

        # 6. 비교·대조 키워드 → split_2col (차트 1~2개와 함께).
        elif any(k in heading for k in ["vs", "비교", "대조"]) and n_charts >= 1:
            if not used or used[-1] != "split_2col":
                layout = "split_2col"; why = "비교·대조 섹션"

        # 7. 단일 결정적 차트 → hero_chart.
        elif n_charts == 1 and idx in (1, 2) and hero_count < 2:
            if not used or used[-1] != "hero_chart":
                # 보조 — 본문 prose 가 짧은 경우만 (차트가 핵심).
                if len(prose) < 800:
                    layout = "hero_chart"; why = "단일 결정적 차트"; hero_count += 1

        # 8. analogy 또는 pull_quote 동반 → sidebar_callout.
        elif sec.get("analogy") or sec.get("pull_quote"):
            if not used or used[-1] != "sidebar_callout":
                layout = "sidebar_callout"; why = "analogy / pull_quote 동반"

        # 9. 그 외 → standard.
        # (이미 default)

        # 연속 배치 차단 — 같은 layout 이 직전과 같으면 standard 로 강등.
        if used and used[-1] == layout and layout != "standard":
            layout = "standard"
            why = f"연속 배치 차단 (직전 {used[-1]})"

        out.append(LayoutAssignment(
            section_idx=idx,
            layout=layout,
            why=why,
            assigned_by="heuristic",
        ))
        used.append(layout)

    return out


def fallback_all_standard(n: int) -> list[LayoutAssignment]:
    """LayoutTypesetter 호출 실패 시 모든 섹션 standard (Plan §10.5)."""
    return [
        LayoutAssignment(section_idx=i, layout="standard", why="fallback", assigned_by="default")
        for i in range(n)
    ]


# ─── LayoutTypesetter agent ──────────────────────────────────────


class LayoutTypesetter(BaseAgent):
    """Plan §10.3 의 LayoutTypesetter — Sonnet 4.6, 빠른 결정.

    [모델·예산]
        TYPESETTER_MODEL = "claude-sonnet-4-6"  (light_model_name)
        MAX_TOKENS = 2048                       (단순 분류 작업)

    [Fallback]
        LLM 호출 실패 시 모든 섹션 'standard' (Plan §10.5).
    """

    TYPESETTER_MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 2048

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="layout_typesetter",
            role="Layout Typesetter (식자공)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=True,                   # Sonnet 4.6
        )

    async def assign_layouts(
        self,
        sections: list[dict[str, Any]],
        *,
        has_map: bool = False,
        is_strategic: bool = False,
    ) -> list[LayoutAssignment]:
        """각 섹션에 layout primitive 부여.

        Args:
            sections: EditedReport.sections (또는 ComposedReport.sections).
            has_map: ComposedReport.embedded_map 이 채워졌는가.
            is_strategic: 전략 모드 보고서인가 (decision_brief 분기 신호).

        Returns:
            list[LayoutAssignment].
        """
        self._max_tokens_override = self.MAX_TOKENS

        if not sections:
            return []

        # 전략 모드는 별도 vocab (decision_brief) — 본 함수는 분석 모드만.
        if is_strategic:
            logger.info(
                "[layout_typesetter] strategic mode — decision_brief 단일 layout 적용 "
                "(분석 모드 9종 vocab 미사용)."
            )
            # decision_brief 는 별도 분기 — 본 함수는 분석 모드 9종 vocab 만.
            # 호출자가 strategic mode 시 별도 처리 필요. 현재는 standard fallback.
            return fallback_all_standard(len(sections))

        context = {
            "sections": [
                {
                    "idx": i,
                    "heading": (s or {}).get("heading", ""),
                    "kicker": (s or {}).get("kicker", ""),
                    "prose_len": len(((s or {}).get("prose") or "")),
                    "n_charts": len(((s or {}).get("charts") or [])),
                    "has_analogy": bool((s or {}).get("analogy")),
                    "has_pull_quote": bool((s or {}).get("pull_quote")),
                }
                for i, s in enumerate(sections)
            ],
            "has_map": has_map,
            "section_count": len(sections),
        }

        try:
            raw_text = await super().analyze(context)
            return self._parse_assignments(raw_text, n=len(sections))
        except Exception as e:
            logger.warning(
                "[layout_typesetter] LLM call or parse failed: %s. "
                "Falling back to all-standard (Plan §10.5).", e,
            )
            if self.telemetry is not None:
                setattr(self.telemetry, "layout_fallback", True)
            return fallback_all_standard(len(sections))

    def _parse_assignments(self, raw_text: str, *, n: int) -> list[LayoutAssignment]:
        """LLM 응답 → list[LayoutAssignment]. 미등재 layout 또는 누락 시 standard."""
        text = (raw_text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LayoutTypesetter JSON parse failed: {e}") from e

        assignments_data = (
            data.get("assignments") if isinstance(data, dict) else data
        ) or []

        result: list[LayoutAssignment] = []
        seen_idx: set[int] = set()
        for item in assignments_data:
            if not isinstance(item, dict):
                continue
            idx = item.get("section_idx")
            if not isinstance(idx, int) or idx < 0 or idx >= n:
                continue
            layout = item.get("layout", "standard")
            if layout not in LAYOUT_VOCAB:
                logger.info(
                    "[layout_typesetter] unknown layout '%s' for section %d — "
                    "fallback to 'standard'.", layout, idx,
                )
                layout = "standard"
            seen_idx.add(idx)
            result.append(LayoutAssignment(
                section_idx=idx,
                layout=layout,    # type: ignore[arg-type]
                why=item.get("why", ""),
                assigned_by="layout_typesetter",
            ))

        # 누락된 섹션 채우기 — standard.
        for i in range(n):
            if i not in seen_idx:
                result.append(LayoutAssignment(
                    section_idx=i, layout="standard",
                    why="미할당 → standard fallback",
                    assigned_by="default",
                ))

        result.sort(key=lambda a: a.section_idx)
        return result
