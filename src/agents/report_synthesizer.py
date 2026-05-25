"""Report Synthesizer -- HTML report generation with Canvas 2D charts."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone, timedelta

from jinja2 import Environment, FileSystemLoader

from src.archetypes import ReportArchetype, get_archetype
from src.config import Config
from src.models import (
    AnalysisBlock, FullAnalysisResult, NarrativePlan, NarrativeSection,
    ReportSectionPlan,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
CSS_PATH = os.path.join(TEMPLATE_DIR, "report.css")
STATIC_DIR = os.path.join(TEMPLATE_DIR, "static")
KST = timezone(timedelta(hours=9))

# v3.2.0 — 정적 자산 (d3 + charts.js + charts.css). 보고서 디렉토리에 한 번만 복사.
STATIC_ASSETS = ("d3.v7.min.js", "charts.js", "charts.css", "maps.js", "maps.css")


def _inline_static_assets(html: str) -> str:
    """`<link href="X.css">` / `<script src="X.js">` 를 inline content 로 치환."""
    for asset in STATIC_ASSETS:
        src = os.path.join(STATIC_DIR, asset)
        if not os.path.exists(src):
            continue
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
        if asset.endswith(".css"):
            patterns = [
                f'<link rel="stylesheet" href="{asset}">',
                f"<link rel='stylesheet' href='{asset}'>",
                f'<link href="{asset}" rel="stylesheet">',
            ]
            replacement = f"<style>\n{content}\n</style>"
            for p in patterns:
                if p in html:
                    html = html.replace(p, replacement, 1)
                    break
        elif asset.endswith(".js"):
            patterns = [
                f'<script src="{asset}"></script>',
                f"<script src='{asset}'></script>",
                f'<script src="{asset}" defer></script>',
            ]
            replacement = f"<script>\n{content}\n</script>"
            for p in patterns:
                if p in html:
                    html = html.replace(p, replacement, 1)
                    break
    return html


class ReportSynthesizer:
    """Generates HTML reports from analysis results.

    Does NOT extend BaseAgent. Uses Jinja2 for HTML rendering,
    calls Claude CLI for executive summary generation,
    builds Canvas 2D chart data, and uploads to Cloudflare Pages.

    v3.1.0:
    - ``use_llm_narrative_plan`` (default False) — fast/standard 는 default plan 사용.
    - ``use_llm_executive_summary`` (default False) — deterministic builder 우선,
      실패 또는 deep 일 때만 LLM.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._api_client: object | None = None
        # v3.1.0: orchestrator 가 mode 별로 주입.
        self.use_llm_narrative_plan: bool = False
        self.use_llm_executive_summary: bool = False

        if not config.use_cli_mode:
            import anthropic
            self._api_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    # ------------------------------------------------------------------
    # v3.1.0 — Deterministic executive summary builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_deterministic_summary(
        result: FullAnalysisResult,
    ) -> tuple[str, list[str]]:
        """LLM 호출 없이 ``judgment.main_judgment`` + ``biggest_uncertainty`` +
        top findings 로 governance + key items 생성.

        반환값: (governance_text, key_summary_items)
        실패하면 ("", []) 반환 → 호출자가 LLM 폴백 결정.
        """
        ctx = result.context
        judgment = result.judgment

        governance_pieces: list[str] = []
        if ctx and ctx.event_name:
            governance_pieces.append(f"{ctx.event_name}.")
        if ctx and ctx.summary:
            governance_pieces.append(ctx.summary.strip().split("\n", 1)[0][:200])
        elif judgment and judgment.main_judgment:
            governance_pieces.append(judgment.main_judgment.strip()[:200])
        governance = " ".join(p for p in governance_pieces if p).strip()

        key_items: list[str] = []
        if judgment and judgment.main_judgment:
            key_items.append(judgment.main_judgment.strip()[:160])
        if judgment and judgment.base_scenario and judgment.base_scenario.strip():
            key_items.append(f"기준 시나리오: {judgment.base_scenario.strip()[:140]}")
        # Top finding (highest confidence) — 종합 판단과 다른 각도 보강.
        if result.findings:
            top = max(result.findings, key=lambda f: f.confidence.aggregate)
            stmt = top.main_claim.statement.strip()
            if stmt and stmt not in (judgment.main_judgment if judgment else ""):
                key_items.append(stmt[:160])
        if judgment and judgment.counter_hypothesis:
            key_items.append(
                f"반대 가설: {judgment.counter_hypothesis.strip()[:140]}"
            )
        if judgment and judgment.biggest_uncertainty:
            key_items.append(
                f"가장 큰 불확실성: {judgment.biggest_uncertainty.strip()[:140]}"
            )

        # 최소 검증 — governance/key_items 둘 다 비어있으면 실패 신호.
        if not governance and not key_items:
            return "", []
        if not key_items:
            # judgment 없이 context 만 있을 때 — context 핵심 1~2개 fallback.
            if ctx and ctx.summary:
                key_items.append(ctx.summary.strip().split("\n", 1)[0][:160])
        return governance, key_items[:5]

    async def _generate_executive_summary(
        self, result: FullAnalysisResult
    ) -> tuple[str, list[str]]:
        """Generate governance text + key summary items via Claude CLI or API.

        Returns:
            (governance_text, key_summary_items) tuple.
        """
        summary_prompt = (
            "다음 분석 결과를 바탕으로 두 가지를 작성.\n\n"
            "=== 1. 거버넌스 메시지 ===\n"
            "- 보고서 상단에 들어갈 사건 개요 한 문장\n"
            "- 음슴체 사용, 반드시 완결된 문장으로 끝낼 것 (중간에 끊기면 안 됨)\n"
            "- 사건의 핵심 팩트와 수치를 포함\n"
            "- 200자 내외\n\n"
            "=== 2. 핵심 요약 ===\n"
            "- 보고서 전체 내용을 번호로 요약\n"
            "- 각 항목은 한 문장, 음슴체\n"
            "- 3~5개 항목\n\n"
            "출력 형식 (반드시 이 형식 준수):\n"
            "[GOVERNANCE]\n"
            "사건 요약 문장\n\n"
            "[KEY_SUMMARY]\n"
            "1) 첫 번째 핵심\n"
            "2) 두 번째 핵심\n"
            "3) 세 번째 핵심\n\n"
            "분석 결과:\n"
        )

        analyses_data: dict = {}
        if result.context:
            analyses_data["context"] = result.context.model_dump()
        if result.players:
            analyses_data["players"] = result.players.model_dump()
        if result.dynamics:
            analyses_data["dynamics"] = result.dynamics.model_dump()
        if result.chain_reaction:
            analyses_data["chain_reaction"] = result.chain_reaction.model_dump()
        if result.scenarios:
            analyses_data["scenarios"] = result.scenarios.model_dump()

        user_message = summary_prompt + json.dumps(
            analyses_data, ensure_ascii=False, indent=2
        )

        if self.config.use_cli_mode:
            raw = await self._call_cli(user_message)
        else:
            raw = await self._call_api(user_message)

        return self._parse_summary(raw)

    @staticmethod
    def _parse_summary(raw: str) -> tuple[str, list[str]]:
        """Parse raw text into (governance, key_summary_items)."""
        governance = ""
        key_items: list[str] = []
        if "[GOVERNANCE]" in raw and "[KEY_SUMMARY]" in raw:
            parts = raw.split("[KEY_SUMMARY]")
            governance = parts[0].replace("[GOVERNANCE]", "").strip()
            for line in parts[1].strip().split("\n"):
                line = line.strip()
                if line and re.match(r"^\d+\)", line):
                    # Strip the "N) " prefix — template adds its own numbering
                    key_items.append(re.sub(r"^\d+\)\s*", "", line))
        else:
            # Fallback: use entire text as governance
            governance = raw.strip()
        return governance, key_items

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Strip markdown emphasis from raw dict text fields (WRITE-AP-1 fallback).

        v4.4.7: ``_format_structured_text`` 의 strip 부분만 떼어낸 lightweight 변형.
        prose 외 dict 필드 (contradictions.side_a/side_b/evidence/resolution,
        watch_signals.*, deck, headline, closing, confidence_summary 등) 에
        적용. ``<br>`` 변환이나 section header 처리는 안 함.

        composer prompt 에 마크다운 강조 금지를 명시했지만 실수로 emit 됐을 때의
        템플릿-side 마지막 방어선. WRITE-AP-1 회귀가 prose 외 영역에서 재발한
        것을 v4.4.7 사용자 피드백으로 발견 → 모든 raw text 필드에 적용.
        """
        if not text:
            return text
        text = re.sub(r"\*\*([^*\n]{1,300})\*\*", r"\1", text)
        text = re.sub(r"\*([^*\n]{1,300})\*", r"\1", text)
        text = re.sub(r"__([^_\n]{1,300})__", r"\1", text)
        text = re.sub(r"(?<!\w)_([^_\n]{1,300})_(?!\w)", r"\1", text)
        text = re.sub(r"^> ?", "", text, flags=re.MULTILINE)
        return text

    @staticmethod
    def _format_structured_text(text: str) -> str:
        """Convert numbered patterns (첫째/둘째/N층 etc.) into <br> separated lines.

        Also splits the text into paragraphs on:
        - Explicit double-newline breaks
        - [N단락] / [핵심 판단] style block headers
        - Section headers like '핵심 판단:', '상방/하방 비대칭:', '변수 민감도:', '한계:' etc.
        """
        if not text:
            return text

        # v4.4.4 (WRITE-AP-1): composer prompt 에 마크다운 강조 금지를 명시했지만,
        # 실수로 emit 했을 경우의 *fallback strip*. raw 마크다운 기호가 보고서에
        # 노출되어 'AI 작성 흔적' 으로 보이는 회귀 차단.
        # **bold** / *italic* / __bold__ / _italic_ 모두 가운데 텍스트만 남김.
        text = re.sub(r"\*\*([^*\n]{1,300})\*\*", r"\1", text)
        text = re.sub(r"\*([^*\n]{1,300})\*", r"\1", text)
        text = re.sub(r"__([^_\n]{1,300})__", r"\1", text)
        text = re.sub(r"(?<!\w)_([^_\n]{1,300})_(?!\w)", r"\1", text)
        # Markdown blockquote `> ...` 도 한국어 본문에 어울리지 않으니 제거 (선행 `> `만 strip)
        text = re.sub(r"^> ?", "", text, flags=re.MULTILINE)

        # Block headers like [1단락] / [핵심 판단] -> bold heading on a new paragraph
        text = re.sub(
            r"\[([^\[\]\n]{1,30})\]\s*",
            r"<br><br><strong>\1</strong><br>",
            text,
        )

        # Inline section headers ending with colon (e.g. '핵심 판단:', '변수 민감도:')
        section_keywords = (
            r"핵심 판단|상방/하방 비대칭|상방·하방 비대칭|상하방 비대칭|"
            r"변수 민감도|민감도 분석|분석가의 한계|한계와 유보|유보사항|"
            r"전제 조건|결론|시사점|권고|요약"
        )
        # After sentence terminator
        text = re.sub(
            rf"(?<=[.。!?])\s*({section_keywords})\s*[:：]\s*",
            r"<br><br><strong>\1.</strong><br>",
            text,
        )
        # At start of string
        text = re.sub(
            rf"^\s*({section_keywords})\s*[:：]\s*",
            r"<strong>\1.</strong><br>",
            text,
        )

        # N층: patterns
        text = re.sub(r"(?<=[.。])\s*(\d+층\s*[:：])", r"<br><br><strong>\1</strong>", text)
        # 첫째/둘째/셋째/넷째/다섯째 patterns
        text = re.sub(
            r"(?<=[.。,])\s*(첫째|둘째|셋째|넷째|다섯째|여섯째)\s*[,，]",
            r"<br><br><strong>\1,</strong>",
            text,
        )
        # ①②③ patterns
        text = re.sub(r"(?<=[.。])\s*([①②③④⑤⑥])", r"<br><br>\1", text)

        # Generic paragraph break on \n\n
        text = re.sub(r"\n{2,}", "<br><br>", text)
        # Single newlines -> single <br>
        text = re.sub(r"(?<!>)\n", "<br>", text)

        # Clean up duplicate leading <br> and collapse 3+ consecutive <br>
        text = re.sub(r"^(?:<br>\s*)+", "", text)
        text = re.sub(r"(?:<br>\s*){3,}", "<br><br>", text)
        return text

    # ------------------------------------------------------------------
    # V3 Step 3 — AnalysisBlock builders (per BlockType)
    # ------------------------------------------------------------------
    #
    # Each builder maps existing v2 analysis data (FullAnalysisResult fields) into
    # a typed payload dict for an AnalysisBlock. Block templates read ONLY
    # ``block.payload`` (Anti-pattern #8). Builders are pure functions and return
    # ``None`` when the source data is unavailable — the caller skips those.
    #
    # Step 4 will introduce claim/evidence and replace the placeholder builders for
    # claim_card / evidence_table / qna with proper data.

    @staticmethod
    def _payload_narrative(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        # Pick the most relevant text source for this section purpose.
        sources = []
        if result.context and result.context.background:
            sources.append(result.context.background)
        if result.dynamics and result.dynamics.summary:
            sources.append(result.dynamics.summary)
        if not sources:
            return None
        return {"text": "\n\n".join(sources[:2]), "tone": "neutral"}

    @staticmethod
    def _payload_actor_cards(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.players or not result.players.players:
            return None
        return {"actors": result.players.players}

    @staticmethod
    def _payload_flow_chain(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.chain_reaction or not result.chain_reaction.chain:
            return None
        return {"steps": result.chain_reaction.chain}

    @staticmethod
    def _payload_scenario_table(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.scenarios or not result.scenarios.scenarios:
            return None
        scenarios = []
        for sc in result.scenarios.scenarios:
            impacts = sc.get("impact_by_player", [])
            impact_text = " · ".join(f"{i.get('player','')}: {i.get('impact','')}" for i in impacts[:3])
            scenarios.append({
                "name": sc.get("name", ""),
                "tag": sc.get("tag", ""),
                "probability": sc.get("probability", ""),
                "description": sc.get("description", ""),
                "impact": impact_text or sc.get("trigger", ""),
            })
        return {"scenarios": scenarios}

    @staticmethod
    def _payload_timeline(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.context or not result.context.timeline:
            return None
        return {"events": result.context.timeline}

    @staticmethod
    def _payload_data_series(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        # Map visuals.chart_config (Canvas series) into a generic data_series payload.
        if not result.visuals:
            return None
        cfg = result.visuals.chart_config or {}
        if not cfg.get("enabled"):
            return None
        series: list[dict] = []
        for ch in (cfg.get("charts") or []):
            pts = ch.get("points") or []
            series.append({
                "label": ch.get("title") or ch.get("type", "series"),
                "points": [{"x": p.get("label", ""), "y": p.get("value", "")} for p in pts],
            })
        if not series:
            return None
        return {"series": series, "unit": ""}

    @staticmethod
    def _payload_watchlist(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.scenarios or not result.scenarios.watch_signals:
            return None
        return {"signals": result.scenarios.watch_signals}

    @staticmethod
    def _payload_counter_hypothesis(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.dynamics:
            return None
        if not result.dynamics.counter_view and not result.dynamics.key_insight:
            return None
        return {
            "base_judgment": result.dynamics.key_insight or result.dynamics.summary or "",
            "counter": result.dynamics.counter_view or "(반대 가설 없음)",
            "required_evidence": result.dynamics.cognitive_biases or [],
        }

    @staticmethod
    def _payload_callout(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if result.dynamics and result.dynamics.key_insight:
            return {"title": "핵심 통찰", "body": result.dynamics.key_insight, "style": "insight"}
        if result.chain_reaction and result.chain_reaction.worst_case:
            return {"title": "최악의 경우", "body": result.chain_reaction.worst_case, "style": "warning"}
        return None

    @staticmethod
    def _payload_decomposition(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.dynamics or not result.dynamics.asymmetries:
            return None
        return {
            "root": result.dynamics.framework or section.title,
            "branches": [
                {"label": a.get("type", ""), "detail": a.get("description", "")}
                for a in result.dynamics.asymmetries
            ],
        }

    @staticmethod
    def _payload_matrix(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        # Placeholder: no native matrix data in v2 models. Builders will populate this
        # when V3 lens runners produce cross-cutting comparisons (Step 5).
        return None

    @staticmethod
    def _payload_map(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        """v3.4.0 — maplibre-gl + d3-geo 지도 블록.

        기존 visual_analyst 가 산출한 ``result.visuals.leaflet_config`` 를 데이터 소스로 사용.
        없으면 None — 지리 차원이 없는 사건에는 블록을 만들지 않는다 (Anti-pattern #4).
        """
        from src.visual_builder import build_map_payload  # 지연 import: circular 방지
        if not result.visuals or not result.visuals.leaflet_config:
            return None
        cfg = result.visuals.leaflet_config or {}
        if not cfg.get("enabled"):
            return None
        theme = "burgundy_mono" if (result.report_theme or "burgundy") == "burgundy" else "light_mono"
        return build_map_payload(cfg, theme=theme)

    @staticmethod
    def _payload_risk_matrix(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.chain_reaction or not result.chain_reaction.wildcards:
            return None
        risks = []
        for w in result.chain_reaction.wildcards:
            risks.append({
                "risk": w.get("event", ""),
                "probability": w.get("probability", ""),
                "impact": "high",
                "mitigation": "",
            })
        return {"risks": risks} if risks else None

    @staticmethod
    def _payload_argument_pair(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        if not result.dynamics:
            return None
        a = result.dynamics.key_insight or result.dynamics.summary
        b = result.dynamics.counter_view
        if not a or not b:
            return None
        return {"hypothesis_a": a, "hypothesis_b": b, "evidence_alignment": {}}

    @staticmethod
    def _payload_decision_matrix(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        # Placeholder: requires explicit option/criterion data. Step 4+ once the
        # decision_brief archetype lands.
        return None

    @staticmethod
    def _payload_claim_card(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        # Step 4 (Claim/Evidence) 미도입 → 빈 placeholder 렌더 금지. 데이터 없으면 블록 skip.
        # 빈 카드를 매번 렌더하던 것이 보고서 단조로움의 직접 원인이었음.
        return None

    @staticmethod
    def _payload_evidence_table(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        return None

    @staticmethod
    def _payload_qna(result: FullAnalysisResult, section: ReportSectionPlan) -> dict | None:
        return None

    _BLOCK_BUILDERS: dict = {}  # populated below to avoid forward-ref issues

    def _build_all_available_blocks(
        self, result: FullAnalysisResult,
    ) -> list[AnalysisBlock]:
        """v3.3.0 — freeform_essay 용. 가용한 BlockType 마다 1개씩 빌드.

        composer 의 ``embedded_blocks: [block_type]`` 가 type 으로 referencing 하므로
        section_plan 무관하게 *지금 가용한* 블록을 모두 채워둔다. 데이터 없는 type 은
        builder 가 None 반환 → 자동 스킵.
        """
        # 더미 ReportSectionPlan — 빌더 시그니처 호환용. composer 가 section_id 를 쓰지
        # 않으므로 모두 "freeform" 으로 통일.
        dummy_section = ReportSectionPlan(
            section_id="freeform",
            title="",
            purpose="",
            block_types=[],
        )
        blocks: list[AnalysisBlock] = []
        seq = 0
        for btype, builder in self._BLOCK_BUILDERS.items():
            payload = builder(result, dummy_section)
            if payload is None:
                continue
            seq += 1
            blocks.append(AnalysisBlock(
                block_id=f"B-{seq:03d}",
                block_type=btype,
                title="",
                purpose="",
                payload=payload,
                section_id="freeform",
            ))
        logger.info(
            "[report_synthesizer] freeform_essay: built %d available blocks (%s)",
            len(blocks), [b.block_type for b in blocks],
        )
        return blocks

    def _build_blocks(
        self, result: FullAnalysisResult, archetype: ReportArchetype,
    ) -> list[AnalysisBlock]:
        """Build AnalysisBlock list from archetype.section_plan(strategy).

        Returns empty list for the legacy six_act_theater path (caller does not use).
        For freeform_essay (v3.3.0), build one block per available BlockType so
        composer's ``embedded_blocks`` references resolve regardless of section_plan.
        For other archetypes, walk each ReportSectionPlan and build one AnalysisBlock
        per requested block_type.

        PR3 (v3.4.6): AMC enforcement.
        - archetype.contract().forbidden_blocks 에 등재된 block_type 은 reject
          (placeholder 회귀 차단).
        - 빌드 후 contract().mandatory_stages 미달 시 경고 로그 + 첫 섹션 메타에
          missing_stages 기록 (템플릿이 시각화).
        """
        if archetype.archetype_id == "six_act_theater":
            return []
        if archetype.archetype_id == "freeform_essay":
            return self._build_all_available_blocks(result)
        if result.strategy is None:
            return []
        plan = archetype.section_plan(result.strategy)
        # Spec: dispatcher reads result.strategy.section_plan. archetype.section_plan()
        # is the SSOT for the per-archetype layout, but strategy is what the dispatcher
        # iterates — so we mirror it here.
        result.strategy.section_plan = plan

        # PR3: AMC 읽기 (contract() 미선언 archetype 은 default_contract — 느슨한 계약)
        contract = self._archetype_contract(archetype)
        forbidden = set(contract.forbidden_blocks or [])

        # PR4: required_inputs 검증 — 빠진 input 이 있으면 경고. 라우팅 자체는 거부하지
        # 않음 (archetype 선택은 select_archetype 영역). 빠진 정보를 사용자에게 가시화
        # 하기 위해 missing_inputs 도 메타에 기록.
        missing_inputs = self._check_required_inputs(result, contract.required_inputs)
        if missing_inputs:
            logger.warning(
                "[report_synthesizer] AMC %s: required_inputs missing %s — archetype 결과 빈약 가능",
                contract.method_id, missing_inputs,
            )

        builders = self._BLOCK_BUILDERS
        blocks: list[AnalysisBlock] = []
        block_seq = 0
        covered_stages: set[str] = set()
        for section in plan:
            for btype in (section.block_types or []):
                if btype in forbidden:
                    logger.info(
                        "[report_synthesizer] AMC forbids block_type=%s in archetype=%s; skipping",
                        btype, archetype.archetype_id,
                    )
                    continue
                builder = builders.get(btype)
                if builder is None:
                    logger.warning(
                        "[report_synthesizer] No builder for block_type=%s; skipping",
                        btype,
                    )
                    continue
                payload = builder(result, section)
                if payload is None:
                    continue
                block_seq += 1
                blocks.append(AnalysisBlock(
                    block_id=f"B-{block_seq:03d}",
                    block_type=btype,
                    title="",
                    purpose=section.purpose,
                    payload=payload,
                    section_id=section.section_id,
                ))
            # 이 섹션의 narrative_stage 가 *실제로 블록을 1개 이상 만들었으면* 커버됨으로 간주
            if section.narrative_stage and any(
                b.section_id == section.section_id for b in blocks
            ):
                covered_stages.add(section.narrative_stage)

        # PR3: mandatory_stages 검증 — 미달 stage 가 있으면 contract.method_id 와 함께 경고.
        # 메타데이터로 result.strategy 에 부착 (템플릿/디버그 가시화).
        missing = [s for s in contract.mandatory_stages if s not in covered_stages]
        if missing:
            logger.warning(
                "[report_synthesizer] AMC %s: mandatory stages missing %s — only covered %s",
                contract.method_id, missing, sorted(covered_stages),
            )
        # strategy 에 매번 새 attribute 를 박는 건 Pydantic 에서 안전하지 않으므로
        # 첫 블록 메타에 결과 기록 (있을 때만)
        if blocks:
            blocks[0].payload = dict(blocks[0].payload or {})
            blocks[0].payload.setdefault("__amc__", {})
            blocks[0].payload["__amc__"] = {
                "method_id": contract.method_id,
                "mandatory_stages": list(contract.mandatory_stages),
                "covered_stages": sorted(covered_stages),
                "missing_stages": missing,
                "required_inputs": list(contract.required_inputs),
                "missing_inputs": missing_inputs,
            }

        logger.info(
            "[report_synthesizer] Built %d blocks for archetype=%s across %d sections "
            "(stages covered: %s)",
            len(blocks), archetype.archetype_id, len(plan), sorted(covered_stages),
        )
        return blocks

    @staticmethod
    def _archetype_contract(archetype: ReportArchetype):
        """archetype.contract() 호출. 미선언 archetype 은 default 반환."""
        from src.archetypes.base import default_contract
        getter = getattr(archetype, "contract", None)
        if callable(getter):
            try:
                return getter()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[report_synthesizer] archetype.%s.contract() raised %s; using default",
                    getattr(archetype, "archetype_id", "?"), exc,
                )
        return default_contract(getattr(archetype, "archetype_id", "unknown"))

    @staticmethod
    def _check_required_inputs(
        result: FullAnalysisResult, required: list[str],
    ) -> list[str]:
        """PR4: contract.required_inputs 가 result 에 실제로 채워졌는지 검증.

        FullAnalysisResult 의 attribute 가 None 이거나 (모델 인스턴스인 경우) 해당
        모델의 핵심 list/dict 필드가 비어있으면 missing 으로 간주.

        예:
        - 'context' 가 None 또는 ContextAnalysis() 빈 인스턴스 → missing
        - 'scenarios' 가 None 또는 ScenarioAnalysis(scenarios=[]) → missing
        - 'players' 가 None 또는 PlayerAnalysis(players=[]) → missing
        """
        missing: list[str] = []
        for field in required:
            obj = getattr(result, field, None)
            if obj is None:
                missing.append(field)
                continue
            # Pydantic 모델일 수 있음 — 핵심 list/dict 필드가 비어있는지 검사
            cls = type(obj)
            if hasattr(cls, "model_fields"):
                has_any = False
                for fname in cls.model_fields:
                    val = getattr(obj, fname, None)
                    if isinstance(val, (list, dict)) and len(val) > 0:
                        has_any = True
                        break
                    if isinstance(val, str) and val.strip():
                        has_any = True
                        break
                if not has_any:
                    missing.append(field)
        return missing

    async def _call_cli(self, prompt: str) -> str:
        """Call Claude CLI for text generation."""
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError(
                "claude CLI not found on PATH. "
                "Install it with: npm install -g @anthropic-ai/claude-code && claude login"
            )

        cmd = [
            claude_bin,
            "-p", prompt,
            "--output-format", "text",
            "--model", self.config.model_name_light,
            "--dangerously-skip-permissions",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "unknown error"
            raise RuntimeError(f"[report_synthesizer] CLI failed: {err_msg}")

        return stdout.decode().strip()

    async def _call_api(self, prompt: str) -> str:
        """Call Anthropic API for text generation."""
        assert self._api_client is not None, "API client not initialised"
        try:
            response = await self._api_client.messages.create(  # type: ignore[union-attr]
                model=self.config.model_name_light,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text  # type: ignore[index]
        except Exception as e:
            logger.error(f"[report_synthesizer] Summary generation failed: {e}")
            return "Executive summary unavailable."

    # ------------------------------------------------------------------
    # Narrative Plan generation
    # ------------------------------------------------------------------

    _DATA_SOURCE_CHECKS: dict[str, str] = {
        "context": "context",
        "players": "players",
        "dynamics": "dynamics",
        "chain_reaction": "chain_reaction",
        "scenarios": "scenarios",
        "watch_signals": "scenarios",
    }

    def _has_data(self, result: FullAnalysisResult, source: str) -> bool:
        """Check if a data_source has meaningful data."""
        field = self._DATA_SOURCE_CHECKS.get(source)
        if not field:
            return False
        obj = getattr(result, field, None)
        if obj is None:
            return False
        if source == "players":
            return bool(obj.players)
        if source == "chain_reaction":
            return bool(obj.chain)
        if source == "scenarios":
            return bool(obj.scenarios)
        if source == "watch_signals":
            return bool(getattr(obj, "watch_signals", None))
        return True

    def _get_available_sources(self, result: FullAnalysisResult) -> list[str]:
        """Return list of data_sources that have actual data."""
        return [s for s in self._DATA_SOURCE_CHECKS if self._has_data(result, s)]

    @staticmethod
    def _default_narrative_plan(result: FullAnalysisResult) -> NarrativePlan:
        """Fallback: traditional 6-act structure."""
        defaults = [
            ("context", "PART I", "상황인식"),
            ("players", "PART II", "이해관계자"),
            ("dynamics", "PART III", "구조 및 상호작용"),
            ("chain_reaction", "PART IV", "연쇄반응"),
            ("scenarios", "PART V", "향후 시나리오"),
            ("watch_signals", "PART VI", "시그널"),
        ]
        sections: list[NarrativeSection] = []
        for i, (src, act, title) in enumerate(defaults):
            field = "scenarios" if src == "watch_signals" else src
            obj = getattr(result, field, None)
            if obj is None:
                continue
            if src == "players" and not obj.players:
                continue
            if src == "chain_reaction" and not obj.chain:
                continue
            if src == "scenarios" and not obj.scenarios:
                continue
            if src == "watch_signals" and not getattr(obj, "watch_signals", None):
                continue
            sections.append(NarrativeSection(
                section_id=f"s{i + 1}",
                act_label=act,
                title=title,
                data_source=src,
            ))
        return NarrativePlan(sections=sections)

    async def _generate_narrative_plan(
        self, result: FullAnalysisResult
    ) -> NarrativePlan:
        """Ask Claude for the optimal section ordering for this event."""
        available = self._get_available_sources(result)
        if not available:
            return self._default_narrative_plan(result)

        # Build condensed summaries for the prompt
        summaries: dict[str, str] = {}
        if result.context:
            summaries["context"] = (
                f"사건: {result.context.event_name}. "
                f"요약: {result.context.summary[:200]}"
            )
        if result.players and result.players.players:
            names = [p.get("name", "") for p in result.players.players[:6]]
            summaries["players"] = f"주요 행위자: {', '.join(names)}"
        if result.dynamics:
            summaries["dynamics"] = (
                f"프레임워크: {result.dynamics.framework}. "
                f"{result.dynamics.summary[:150]}"
            )
        if result.chain_reaction and result.chain_reaction.chain:
            titles = [s.get("title", "") for s in result.chain_reaction.chain[:5]]
            summaries["chain_reaction"] = f"연쇄단계: {' → '.join(titles)}"
        if result.scenarios and result.scenarios.scenarios:
            names = [s.get("name", "") for s in result.scenarios.scenarios[:4]]
            summaries["scenarios"] = f"시나리오: {', '.join(names)}"
        if result.scenarios and result.scenarios.watch_signals:
            sigs = [s.get("signal", "") for s in result.scenarios.watch_signals[:4]]
            summaries["watch_signals"] = f"감시 시그널: {', '.join(sigs)}"

        prompt = (
            "당신은 사건 분석 보고서의 내러티브 구조를 설계하는 편집장.\n\n"
            "아래 분석 결과를 검토하고, 이 사건에 가장 적합한 보고서 섹션 순서를 결정.\n\n"
            "사용 가능한 데이터 소스:\n"
        )
        for src in available:
            desc = summaries.get(src, src)
            prompt += f"- {src}: {desc}\n"

        prompt += (
            "\n규칙:\n"
            "1. 4~7개 섹션, 각 data_source 최대 1회 사용\n"
            "2. 사건 성격에 맞게 순서와 제목 자유 결정\n"
            "3. act_label은 영어 (예: PART I — THE TRIGGER), title은 한국어\n"
            "4. narrative_bridge: 이전 섹션→이 섹션 전환 1문장, 한국어, 음슴체\n"
            "5. 첫 섹션의 narrative_bridge는 빈 문자열\n\n"
            "반드시 아래 JSON만 출력 (다른 텍스트 없이):\n"
            '{"report_theme":"핵심 서사 한 문장","sections":['
            '{"section_id":"s1","act_label":"PART I — ...","title":"...",'
            '"data_source":"context","narrative_bridge":"","subsections":[]},'
            "...]}\n"
        )

        try:
            if self.config.use_cli_mode:
                raw = await self._call_cli(prompt)
            else:
                raw = await self._call_api(prompt)

            # Extract JSON from response
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                logger.warning("[report_synthesizer] No JSON in narrative plan response")
                return self._default_narrative_plan(result)

            plan = NarrativePlan.model_validate_json(match.group())

            # Validate: filter invalid/duplicate sources
            seen: set[str] = set()
            valid: list[NarrativeSection] = []
            for i, sec in enumerate(plan.sections):
                if sec.data_source not in available or sec.data_source in seen:
                    continue
                seen.add(sec.data_source)
                sec.section_id = f"s{i + 1}"
                valid.append(sec)

            plan.sections = valid
            if not plan.sections:
                return self._default_narrative_plan(result)

            logger.info(
                f"[report_synthesizer] Narrative plan: "
                f"{[s.data_source for s in plan.sections]}"
            )
            return plan

        except Exception as e:
            logger.warning(f"[report_synthesizer] Narrative plan failed: {e}")
            return self._default_narrative_plan(result)

    def _build_chart_data(self, result: FullAnalysisResult) -> dict:
        """Build JSON-serializable chart data for Canvas 2D radar chart."""
        confidence_scores: dict[str, float] = {}
        if result.context:
            confidence_scores["Context"] = result.context.confidence_score
        if result.players:
            confidence_scores["Players"] = result.players.confidence_score
        if result.dynamics:
            confidence_scores["Dynamics"] = result.dynamics.confidence_score
        if result.chain_reaction:
            confidence_scores["Chain Reaction"] = result.chain_reaction.confidence_score
        if result.scenarios:
            confidence_scores["Scenarios"] = result.scenarios.confidence_score

        return {
            "labels": list(confidence_scores.keys()),
            "values": list(confidence_scores.values()),
        }

    async def _upload_to_cloudflare(self, filepath: str) -> str:
        """Upload HTML report to Cloudflare Pages using wrangler CLI."""
        account_id = self.config.cloudflare_account_id
        api_token = self.config.cloudflare_api_token
        project_name = self.config.cloudflare_project_name

        if not account_id or not api_token:
            logger.warning("[report_synthesizer] Cloudflare credentials not set, skipping upload")
            return ""

        try:
            wrangler_bin = shutil.which("wrangler")
            if wrangler_bin is None:
                npx_bin = shutil.which("npx")
                if npx_bin is None:
                    logger.warning("[report_synthesizer] wrangler/npx not found, skipping upload")
                    return ""
                wrangler_cmd = [npx_bin, "wrangler"]
            else:
                wrangler_cmd = [wrangler_bin]

            # Deploy the entire reports directory (includes index.html)
            deploy_dir = os.path.dirname(filepath)

            cmd = wrangler_cmd + [
                "pages", "deploy", deploy_dir,
                "--project-name", project_name,
                "--branch", "main",
                "--commit-message", "deploy report",
            ]

            env = os.environ.copy()
            env["CLOUDFLARE_ACCOUNT_ID"] = account_id
            env["CLOUDFLARE_API_TOKEN"] = api_token

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode() + stderr.decode()

            if proc.returncode != 0:
                logger.error(f"[report_synthesizer] Cloudflare upload failed: {output}")
                return ""

            # Always use production URL (not deployment-specific snapshot URL)
            # Deployment URLs (e.g. abc123.project.pages.dev) are frozen snapshots
            # Production URL (project.pages.dev) always reflects the latest deployment
            filename = os.path.basename(filepath)
            production_url = f"https://{project_name}.pages.dev/{filename}"
            logger.info(f"[report_synthesizer] Uploaded to Cloudflare: {production_url}")
            return production_url

        except Exception as e:
            logger.error(f"[report_synthesizer] Cloudflare upload exception: {e}")
            return ""

    async def synthesize(
        self,
        result: FullAnalysisResult,
        theme: str = "burgundy",
        archetype: ReportArchetype | None = None,
        *,
        report_id: str | None = None,
        standalone: bool = False,
    ) -> str:
        """Render HTML report, upload to Cloudflare, return URL or filepath.

        v4.4.1: ``report_id`` 인자 추가. 지정 시 timestamp 생성 대신 그 ID 를 그대로
        사용 (= 기존 파일 덮어쓰기). ``scripts/patch_report.py`` 에서 LLM 호출 없이
        보고서 일부 수정 후 재렌더할 때 사용.

        V3 Step 2 (v2.6.0): ``archetype`` 인자 추가. 미지정 시 ``six_act_theater`` 로 폴백 →
        기존 흐름과 byte-equal 출력 보장. ``six_act_theater`` 가 아닌 경우 archetype 객체의
        ``template_path()`` 로 분기. 본격 블록 렌더링은 Step 3 에서 도입.
        """
        if archetype is None:
            archetype = get_archetype("six_act_theater")
        is_legacy_six_act = archetype.archetype_id == "six_act_theater"

        # v3.4.0 — theme 을 결과에 기록해 block builder 가 읽을 수 있게 함.
        # (`_payload_map` 등이 ``result.report_theme`` 으로 light/burgundy 분기.)
        result.report_theme = theme

        # v4.5.5 — 시스템 추적성. 보고서 자체에 생성/재렌더 시점 버전 노출.
        # 재렌더 (--rerender-only) 도 본 메서드 거치므로 매번 *현재 시점 VERSION* 으로
        # 갱신. revision 은 patch_report.py 가 책임 (본 메서드는 안 건드림).
        try:
            from src.orchestrator import VERSION as _SYSTEM_VERSION
            result.system_version = _SYSTEM_VERSION
        except Exception:
            pass  # VERSION import 실패해도 보고서 생성은 계속

        # v3.1.0: deterministic-first executive summary + conditional narrative plan.
        key_summary_items: list[str] = []
        narrative_plan: NarrativePlan | None = None

        # 1) Executive summary — deterministic builder 우선.
        if result.executive_summary:
            governance, key_items = result.executive_summary, []
        else:
            governance, key_items = self._build_deterministic_summary(result)
            if (not governance or not key_items) and self.use_llm_executive_summary:
                # deterministic 실패 + LLM 허용 시에만 폴백.
                logger.info(
                    "[report_synthesizer] deterministic summary insufficient; "
                    "falling back to LLM executive summary",
                )
                try:
                    governance, key_items = await self._generate_executive_summary(result)
                except Exception as e:
                    logger.warning(
                        "[report_synthesizer] LLM executive summary failed: %s; "
                        "using deterministic placeholder", e,
                    )
            if not governance:
                governance = (
                    result.context.event_name if result.context else ""
                ) or "(요약 미생성 — 분석 데이터 부족)"
            if not result.executive_summary:
                result.executive_summary = governance
                key_summary_items = key_items

        # 2) Narrative plan — fast/standard 는 default, deep 만 LLM.
        if self.use_llm_narrative_plan:
            try:
                narrative_plan = await self._generate_narrative_plan(result)
            except Exception as e:
                logger.warning(
                    "[report_synthesizer] LLM narrative plan failed: %s; "
                    "using default plan", e,
                )
                narrative_plan = self._default_narrative_plan(result)
        else:
            narrative_plan = self._default_narrative_plan(result)

        # Build chart data & confidence text
        chart_data = self._build_chart_data(result)
        confidence_parts: list[str] = []
        for label, val in zip(chart_data["labels"], chart_data["values"]):
            confidence_parts.append(f"{label} {val*100:.0f}%")
        confidence_text = "Confidence: " + " · ".join(confidence_parts) if confidence_parts else ""

        # Load CSS content to inline into HTML
        css_content = ""
        if os.path.exists(CSS_PATH):
            with open(CSS_PATH, "r", encoding="utf-8") as f:
                css_content = f.read()

        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
        env.filters["structured"] = self._format_structured_text
        # v4.4.7 (WRITE-AP-1 확장): dict 필드용 lightweight strip — markdown
        # 강조만 제거하고 다른 변환은 안 함. contradictions / watch_signals /
        # deck / headline / closing 등 raw text dict 에 적용.
        env.filters["strip_md"] = self._strip_markdown

        # v5.4.1 — 보고서 이미지 로컬라이즈.
        # composed_report 의 hero_image + 각 sec.images 의 image_url (외부 매체
        # CDN URL) 을 봇이 직접 다운로드해 reports/img/ 에 저장 + image_url 을
        # 상대 경로 ('img/<hash>.jpg') 로 swap. 메이저 매체의 hotlink 차단
        # (referrer / origin 검증으로 외부 도메인 `<img>` 가 403 받는 v5.4.0
        # 회귀) 우회. 동시에 영구 보존 효과 — 원본 URL 만료해도 보고서 안전.
        # Cloudflare Pages 가 reports/ 디렉토리 통째로 업로드하므로 동일 출처.
        await self._localize_report_images(result, output_dir=self.config.report_output_dir)

        # Branch by archetype. six_act_theater = unchanged legacy path (byte-equal output guarantee).
        # New archetypes (financial_transmission, tech_decomposition) render placeholder templates;
        # full block rendering arrives in Step 3.
        template = env.get_template(archetype.template_path())
        if is_legacy_six_act:
            html = template.render(
                result=result,
                css_content=css_content,
                chart_data_json=json.dumps(chart_data, ensure_ascii=False),
                generated_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
                key_summary_items=key_summary_items,
                confidence_text=confidence_text,
                sections=narrative_plan.sections,
                narrative_theme=narrative_plan.report_theme,
                report_theme=theme,
            )
        else:
            # V3 Step 3 (v2.7.0): Block dispatcher path.
            # 1) build AnalysisBlocks from archetype.section_plan(strategy)
            # 2) attach to result.blocks
            # 3) render via report_block.html (archetype.template_path() returns this)
            blocks = self._build_blocks(result, archetype)
            result.blocks = blocks
            block_types_used = sorted({b.block_type for b in blocks})
            logger.info(
                "[report_synthesizer] Archetype branch entered: %s "
                "(template=%s, sections=%d, blocks=%d, types_used=%s)",
                archetype.archetype_id, archetype.template_path(),
                len(result.strategy.section_plan) if result.strategy and result.strategy.section_plan else 0,
                len(blocks), block_types_used,
            )
            from src.timeline_flow import build_timeline_flow
            html = template.render(
                result=result,
                css_content=css_content,
                generated_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
                key_summary_items=key_summary_items,
                confidence_text=confidence_text,
                report_theme=theme,
                archetype_id=archetype.archetype_id,
                archetype_name=archetype.name,
                report_timeline=build_timeline_flow(result.context, result.composed_report),
            )

        if standalone:
            html = _inline_static_assets(html)

        # Save HTML to file
        output_dir = self.config.report_output_dir
        os.makedirs(output_dir, exist_ok=True)

        # v4.4.1: report_id 가 주어지면 그대로 사용 (patch 시 기존 파일 덮어쓰기).
        timestamp = report_id if report_id else datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        filename = f"analysis_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"[report_synthesizer] Report saved: {filepath}")
        result.report_path = filepath

        # Generate markdown version for AI consumption
        md_filename = f"analysis_{timestamp}.md"
        md_filepath = os.path.join(output_dir, md_filename)
        md_content = self._build_markdown(
            result,
            key_summary_items=key_summary_items,
            sections=narrative_plan.sections,
            generated_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        )
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info(f"[report_synthesizer] Markdown saved: {md_filepath}")

        # v4.4.1: FullAnalysisResult JSON 저장 — patch_report.py 가 LLM 호출 없이
        # 보고서 부분 수정 후 재렌더할 수 있게. composer 출력 (composed_report) +
        # 메타데이터 (theme, context, etc.) 포함.
        json_filename = f"analysis_{timestamp}.json"
        json_filepath = os.path.join(output_dir, json_filename)
        try:
            with open(json_filepath, "w", encoding="utf-8") as f:
                json.dump(
                    result.model_dump(mode='json'),
                    f, ensure_ascii=False, indent=2,
                )
            logger.info(f"[report_synthesizer] JSON saved: {json_filepath}")
        except Exception as e:
            logger.warning(f"[report_synthesizer] JSON save failed: {e}")

        # v5.5.0 — ReportBundle 핸드오프 emit (osint_generator 계약 v1).
        # v5.5.3 — 항상 emit (config.enable_report_bundle kill-switch 만 게이트).
        # 영상 제작용으로 모든 보고서에 동반. --bundle 플래그는 이제 no-op (호환 유지).
        # deploy *전* 에 써야 Pages 에 함께 업로드됨. 실패해도 보고서 정상 진행.
        if getattr(self.config, "enable_report_bundle", True):
            try:
                from src.handoff.bundle_builder import build_report_bundle
                project = getattr(self.config, "cloudflare_project_name", "") or ""
                predicted_html_url = (
                    f"https://{project}.pages.dev/{filename}" if project
                    else (result.report_url or "")
                )
                # v5.5.7 — to_thread: prerender 가 sync Playwright 라 async 루프
                # 밖(워커 스레드)에서 실행해야 함 (루프 블로킹·sync-in-asyncio 예외 방지).
                bundle = await asyncio.to_thread(
                    build_report_bundle,
                    result, html_url=predicted_html_url,
                    system_version=result.system_version or "",
                    prerender_svg=getattr(self.config, "enable_bundle_prerender", True),
                )
                bundle_filename = f"analysis_{timestamp}.bundle.json"
                bundle_filepath = os.path.join(output_dir, bundle_filename)
                with open(bundle_filepath, "w", encoding="utf-8") as f:
                    json.dump(bundle.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
                logger.info(f"[report_synthesizer] Bundle saved: {bundle_filepath}")
            except Exception as e:
                logger.warning(f"[report_synthesizer] Bundle emit failed: {e}")

        # Generate index.html (report listing page)
        self._generate_index(output_dir)

        # v3.2.0 — 정적 자산 (d3 + charts.js + charts.css) 복사.
        self._sync_static_assets(output_dir)

        # Ensure _headers file exists for proper MIME type on .md files
        headers_path = os.path.join(output_dir, "_headers")
        headers_content = (
            "/*.md\n"
            "  Content-Type: text/plain; charset=utf-8\n"
            "  Access-Control-Allow-Origin: *\n"
        )
        if not os.path.exists(headers_path) or open(headers_path).read() != headers_content:
            with open(headers_path, "w", encoding="utf-8") as f:
                f.write(headers_content)

        # Upload entire reports directory to Cloudflare Pages
        report_url = await self._upload_to_cloudflare(filepath)
        if report_url:
            result.report_url = report_url
            return report_url

        return filepath

    def _build_markdown(
        self,
        result: FullAnalysisResult,
        key_summary_items: list[str],
        sections: list,
        generated_at: str,
    ) -> str:
        """Generate clean markdown version of the report for AI consumption."""
        lines: list[str] = []
        ctx = result.context

        # Title + metadata
        event_name = (ctx.event_name if ctx else "") or (ctx.event_name_en if ctx else "") or "Analysis"
        lines.append(f"# {event_name}\n")
        if ctx and ctx.category:
            lines.append(f"**Category:** {ctx.category}  ")
        lines.append(f"**Generated:** {generated_at}  \n")

        # Executive Summary
        if result.executive_summary:
            lines.append("## Executive Summary\n")
            lines.append(f"{result.executive_summary}\n")

        # Key Summary
        if key_summary_items:
            lines.append("## Key Points\n")
            for i, item in enumerate(key_summary_items, 1):
                lines.append(f"{i}. {item}")
            lines.append("")

        # Render each narrative section using agent data
        source_map = {
            "context": self._md_context,
            "players": self._md_players,
            "dynamics": self._md_dynamics,
            "chain_reaction": self._md_chain_reaction,
            "scenarios": self._md_scenarios,
            "watch_signals": self._md_watch_signals,
        }
        for sec in sections:
            renderer = source_map.get(sec.data_source)
            if not renderer:
                continue
            content = renderer(result)
            if not content:
                continue
            lines.append(f"## {sec.act_label} — {sec.title}\n")
            if sec.narrative_bridge:
                lines.append(f"_{sec.narrative_bridge}_\n")
            lines.append(content)
            lines.append("")

        # Sources
        if ctx and ctx.sources:
            lines.append("## Sources\n")
            for s in ctx.sources:
                lines.append(f"- {s}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"Generated by Event Analysis Team · Duration: {result.total_duration_seconds:.1f}s")

        return "\n".join(lines)

    @staticmethod
    def _md_context(result: FullAnalysisResult) -> str:
        ctx = result.context
        if not ctx:
            return ""
        parts: list[str] = []
        if ctx.summary:
            parts.append(ctx.summary + "\n")
        if ctx.background:
            parts.append(f"**Background:** {ctx.background}\n")
        if ctx.key_figures:
            parts.append("**Key Figures:**\n")
            for fig in ctx.key_figures:
                label = fig.get("label", "")
                value = fig.get("value", "")
                ctx_note = fig.get("context", "")
                note = f" ({ctx_note})" if ctx_note else ""
                parts.append(f"- **{label}**: {value}{note}")
            parts.append("")
        if ctx.timeline:
            parts.append("**Timeline:**\n")
            for item in ctx.timeline:
                date = item.get("date", "")
                event = item.get("event", "")
                impact = item.get("impact", "")
                line = f"- `{date}` — {event}"
                if impact:
                    line += f" → *{impact}*"
                parts.append(line)
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _md_players(result: FullAnalysisResult) -> str:
        if not result.players or not result.players.players:
            return ""
        parts: list[str] = []
        if result.players.power_dynamics:
            parts.append(result.players.power_dynamics + "\n")
        parts.append("| Name | Role | Risk | Position | Strategy | Vulnerability |")
        parts.append("|------|------|------|----------|----------|---------------|")
        for p in result.players.players:
            name = p.get("name", "").replace("|", "\\|")
            role = p.get("role_tag", "").replace("|", "\\|")
            risk = p.get("risk_level", "").replace("|", "\\|")
            pos = (p.get("position", "") or "").replace("|", "\\|").replace("\n", " ")
            strat = (p.get("strategy", "") or "").replace("|", "\\|").replace("\n", " ")
            vuln = (p.get("vulnerability", "") or "").replace("|", "\\|").replace("\n", " ")
            parts.append(f"| {name} | {role} | {risk} | {pos} | {strat} | {vuln} |")
        parts.append("")
        if result.players.alliances:
            parts.append("**Alliances & Relations:**\n")
            for a in result.players.alliances:
                group = " — ".join(a.get("group", []))
                nature = a.get("nature", "")
                parts.append(f"- {group}: *{nature}*")
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _md_dynamics(result: FullAnalysisResult) -> str:
        d = result.dynamics
        if not d:
            return ""
        parts: list[str] = []
        if d.framework:
            parts.append(f"**Framework:** {d.framework}\n")
        if d.core_tension:
            parts.append(f"**Core Tension:** {d.core_tension}\n")
        if d.asymmetries:
            parts.append("**Asymmetries:**\n")
            for a in d.asymmetries:
                atype = a.get("type", "")
                desc = a.get("description", "")
                adv = a.get("advantage_to", "")
                line = f"- **{atype}**: {desc}"
                if adv:
                    line += f" (advantage: {adv})"
                parts.append(line)
            parts.append("")
        if d.feedback_loops:
            parts.append("**Feedback Loops:**\n")
            for fl in d.feedback_loops:
                ftype = fl.get("type", "")
                desc = fl.get("description", "")
                parts.append(f"- [{ftype}] {desc}")
            parts.append("")
        if d.tipping_points:
            parts.append("**Tipping Points:**\n")
            for tp in d.tipping_points:
                tl = tp.get("timeline", "")
                cond = tp.get("condition", "")
                cons = tp.get("consequence", "")
                parts.append(f"- `{tl}` — {cond} → *{cons}*")
            parts.append("")
        if d.why_unresolved:
            parts.append(f"**Why Unresolved:** {d.why_unresolved}\n")
        if d.counter_view:
            parts.append(f"**Counter View:** {d.counter_view}\n")
        if d.cognitive_biases:
            parts.append(f"**Cognitive Biases to Watch:** {' · '.join(d.cognitive_biases)}\n")
        if d.key_insight:
            parts.append(f"> **Key Insight:** {d.key_insight}\n")
        return "\n".join(parts)

    @staticmethod
    def _md_chain_reaction(result: FullAnalysisResult) -> str:
        c = result.chain_reaction
        if not c or not c.chain:
            return ""
        parts: list[str] = []
        if c.summary:
            parts.append(c.summary + "\n")
        parts.append("**Chain of Effects:**\n")
        for i, step in enumerate(c.chain, 1):
            title = step.get("title", "")
            desc = step.get("description", "")
            severity = step.get("severity", "")
            affected = step.get("affected", [])
            line = f"{i}. **{title}** ({severity}) — {desc}"
            if affected:
                line += f"\n   - Affected: {', '.join(affected)}"
            parts.append(line)
        parts.append("")
        if c.feedback_loops:
            parts.append("**Feedback Loops:**\n")
            for fl in c.feedback_loops:
                parts.append(f"- {fl.get('description', '')}")
            parts.append("")
        if c.break_points:
            parts.append("**Break Points:**\n")
            for bp in c.break_points:
                step = bp.get("at_step", "")
                cond = bp.get("condition", "")
                parts.append(f"- Step {step}: {cond}")
            parts.append("")
        if c.wildcards:
            parts.append("**Wildcards:**\n")
            for w in c.wildcards:
                ev = w.get("event", "")
                pr = w.get("probability", "")
                parts.append(f"- {ev}" + (f" (prob: {pr})" if pr else ""))
            parts.append("")
        if c.worst_case:
            parts.append(f"> **Worst Case:** {c.worst_case}\n")
        return "\n".join(parts)

    @staticmethod
    def _md_scenarios(result: FullAnalysisResult) -> str:
        s = result.scenarios
        if not s or not s.scenarios:
            return ""
        parts: list[str] = []
        if s.base_case_summary:
            parts.append(s.base_case_summary + "\n")
        for i, sc in enumerate(s.scenarios, 1):
            name = sc.get("name", "")
            tag = sc.get("tag", "")
            prob = sc.get("probability", "")
            desc = sc.get("description", "")
            trigger = sc.get("trigger", "")
            parts.append(f"### Scenario {i}: {name} [{tag}] — {prob}")
            parts.append(f"{desc}")
            preconds = sc.get("preconditions", [])
            if preconds:
                parts.append("**Preconditions:**")
                for pc in preconds:
                    parts.append(f"- {pc}")
            if trigger:
                parts.append(f"**Trigger:** {trigger}")
            impacts = sc.get("impact_by_player", [])
            if impacts:
                parts.append("**Impact by Player:**")
                for imp in impacts:
                    player = imp.get("player", "")
                    impact = imp.get("impact", "")
                    sentiment = imp.get("sentiment", "")
                    parts.append(f"- {player} ({sentiment}): {impact}")
            parts.append("")
        if s.summary:
            parts.append("### 균형 분석\n")
            parts.append(s.summary.strip() + "\n")
        if s.invalidation_conditions:
            parts.append("**분석 무효화 조건:**")
            for cond in s.invalidation_conditions:
                parts.append(f"- {cond}")
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _md_watch_signals(result: FullAnalysisResult) -> str:
        if not result.scenarios or not result.scenarios.watch_signals:
            return ""
        parts: list[str] = []
        parts.append("핵심 전제를 무효화하는 조건과 시나리오 분기를 판별하는 핵심 시그널.\n")
        for ws in result.scenarios.watch_signals:
            signal = ws.get("signal", "")
            desc = ws.get("description", "")
            indicates = ws.get("indicates", "")
            line = f"- **{signal}**: {desc}"
            if indicates:
                line += f" → *{indicates}*"
            parts.append(line)
        parts.append("")
        return "\n".join(parts)

    @staticmethod
    async def _localize_report_images(result, output_dir: str) -> None:
        """v5.4.1 — composed_report 의 외부 image_url 을 로컬 파일로 다운로드 + 상대 경로 swap.

        composer 가 emit 한 og:image URL (FT/Reuters/Bloomberg 등 매체 CDN) 은
        외부 hotlink 차단으로 보고서 HTML 에서 직접 `<img src>` 로 박으면 403/
        broken image 가 됨 — v5.4.0 회귀. 해결: 봇이 직접 다운로드 → reports/
        img/<hash>.<ext> 에 저장 → composed_report 의 image_url 을 'img/<hash>.
        <ext>' 상대 경로로 swap. Cloudflare Pages 가 reports/ 통째로 업로드하므로
        보고서 HTML 과 이미지가 *동일 출처* → hotlink 검사 자체 무관.

        Graceful degrade: 다운로드 실패한 URL 은 원본 URL 그대로 유지 (안 보이는
        것보단 깨진 img 가 낫다는 가정). 모든 URL 실패해도 보고서 렌더 정상 진행.
        """
        composed = getattr(result, "composed_report", None)
        if composed is None:
            return

        # 모든 image URL 수집 — hero + 섹션 inline
        urls: list[str] = []
        hero = getattr(composed, "hero_image", None)
        if hero and isinstance(hero, dict) and hero.get("image_url"):
            urls.append(hero["image_url"])
        for sec in (composed.sections or []):
            for img in (getattr(sec, "images", None) or []):
                if isinstance(img, dict) and img.get("image_url"):
                    urls.append(img["image_url"])

        if not urls:
            return

        try:
            from src.tools.image_fetcher import localize_image_urls
        except ImportError as e:
            logger.warning("[report_synthesizer] image_fetcher unavailable: %s", e)
            return

        img_subdir = os.path.join(output_dir, "img")
        mapping = await localize_image_urls(urls, img_subdir, url_prefix="img")

        if not mapping:
            logger.warning(
                "[report_synthesizer] image localize: %d URLs tried, 0 downloaded — "
                "보고서 HTML 에 원본 URL 유지 (broken image 가능, hotlink 차단 의심)",
                len(set(urls)),
            )
            return

        # composed_report 의 image_url 들을 상대 경로로 swap
        if hero and isinstance(hero, dict):
            local = mapping.get(hero.get("image_url"))
            if local:
                hero["image_url"] = local
        for sec in (composed.sections or []):
            new_imgs = []
            for img in (getattr(sec, "images", None) or []):
                if isinstance(img, dict):
                    local = mapping.get(img.get("image_url"))
                    if local:
                        img["image_url"] = local
                    new_imgs.append(img)
            if hasattr(sec, "images"):
                sec.images = new_imgs

        logger.info(
            "[report_synthesizer] image localize: %d/%d downloaded → reports/img/",
            len(mapping), len(set(urls)),
        )

    @staticmethod
    def _sync_static_assets(output_dir: str) -> None:
        """v3.2.0 — d3, charts.js, charts.css 를 reports/ 로 복사.

        파일이 같으면 스킵 (mtime + size 비교). 다르거나 없으면 덮어씀.
        Cloudflare Pages 가 같은 버전 파일을 캐시하도록 helps.
        """
        import shutil as _sh
        for asset in STATIC_ASSETS:
            src = os.path.join(STATIC_DIR, asset)
            dst = os.path.join(output_dir, asset)
            if not os.path.exists(src):
                logger.warning(
                    "[report_synthesizer] Static asset missing: %s", src,
                )
                continue
            try:
                if os.path.exists(dst):
                    if (os.path.getsize(src) == os.path.getsize(dst)
                            and os.path.getmtime(dst) >= os.path.getmtime(src)):
                        continue  # already up to date
                _sh.copyfile(src, dst)
                logger.info(f"[report_synthesizer] Synced static asset: {asset}")
            except OSError as e:
                logger.warning(
                    "[report_synthesizer] Failed to copy %s: %s", asset, e,
                )

    def _generate_index(self, output_dir: str) -> None:
        """Generate index.html listing all reports."""
        import glob
        reports = sorted(glob.glob(os.path.join(output_dir, "analysis_*.html")), reverse=True)

        rows = []
        for rpath in reports[:50]:
            fname = os.path.basename(rpath)
            # Extract date from filename: analysis_20260328_041426.html
            parts = fname.replace("analysis_", "").replace(".html", "").split("_")
            if len(parts) >= 2:
                date_str = parts[0]
                time_str = parts[1]
                display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
            else:
                display_date = fname

            # Try to extract title from HTML
            title = fname
            try:
                with open(rpath, "r", encoding="utf-8") as f:
                    content = f.read(3000)
                    if "<title>" in content and "</title>" in content:
                        title = content.split("<title>")[1].split("</title>")[0].strip()
                        if not title or title == "Analysis":
                            title = fname
            except Exception:
                pass

            rows.append(
                f'<tr>'
                f'<td class="cell-title"><a href="{fname}">{title}</a></td>'
                f'<td class="cell-date">{display_date}</td>'
                f'</tr>'
            )

        empty_row = (
            '<tr><td colspan="2" class="cell-empty">보고서가 없습니다</td></tr>'
        )
        index_html = f'''<!DOCTYPE html>
<html lang="ko" data-theme="editorial_cream">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Analysis Reports</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,700;6..72,800&family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@500;600;700&family=Noto+Serif+KR:wght@400;700;900&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:#F2EBDB; --card:#ECE3D0; --card-hover:#E5DBC4;
  --border:#D4C8B0; --border-soft:rgba(212,200,176,0.55);
  --text:#1F1814; --text-2:#2E2620; --muted:#6B5C4A;
  --accent:#B05A38;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:'IBM Plex Sans KR','Noto Sans KR',sans-serif;
  background:var(--bg); color:var(--text-2);
  font-size:14.5px; line-height:1.7;
  word-break:keep-all; overflow-wrap:break-word;
  -webkit-font-smoothing:antialiased;
}}
.wrap{{max-width:880px;margin:0 auto;padding:48px 24px 64px}}
.eyebrow{{
  font-family:'IBM Plex Mono',monospace;
  font-size:11px;font-weight:700;letter-spacing:2.4px;
  text-transform:uppercase;color:var(--accent);margin-bottom:12px;
}}
h1{{
  font-family:'Newsreader','Noto Serif KR',serif;
  font-size:38px;font-weight:800;line-height:1.15;
  color:var(--text);margin-bottom:10px;letter-spacing:-0.6px;
}}
.sub{{
  font-size:13px;color:var(--muted);margin-bottom:28px;
  padding-bottom:18px;border-bottom:1px solid var(--border-soft);
  font-family:'IBM Plex Mono',monospace;letter-spacing:0.3px;
}}
.sub strong{{color:var(--accent);font-weight:700}}
table{{
  width:100%;border-collapse:collapse;
  background:var(--card);border:1px solid var(--border-soft);
  border-radius:8px;overflow:hidden;
}}
thead th{{
  background:var(--card-hover);color:var(--muted);
  padding:12px 16px;text-align:left;
  font-family:'IBM Plex Mono',monospace;
  font-size:10.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:1.4px;
  border-bottom:1px solid var(--border-soft);
}}
tbody tr{{transition:background .15s}}
tbody tr:hover{{background:var(--card-hover)}}
.cell-title{{padding:14px 16px;border-bottom:1px solid var(--border-soft)}}
.cell-title a{{
  font-family:'Newsreader','Noto Serif KR',serif;
  color:var(--text);text-decoration:none;font-weight:700;
  font-size:15.5px;line-height:1.4;
  border-bottom:1px solid transparent;transition:border-color .15s,color .15s;
}}
.cell-title a:hover{{color:var(--accent);border-bottom-color:var(--accent)}}
.cell-date{{
  padding:14px 16px;border-bottom:1px solid var(--border-soft);
  color:var(--muted);font-size:12px;
  font-family:'IBM Plex Mono',monospace;letter-spacing:0.3px;
  white-space:nowrap;
}}
tbody tr:last-child .cell-title,
tbody tr:last-child .cell-date{{border-bottom:none}}
.cell-empty{{
  padding:36px 20px;text-align:center;color:var(--muted);
  font-style:italic;font-size:14px;
}}
.foot{{
  margin-top:24px;padding-top:16px;
  border-top:1px solid var(--border-soft);
  font-family:'IBM Plex Mono',monospace;
  font-size:11px;color:var(--muted);letter-spacing:0.3px;
  text-align:center;
}}
.foot a{{color:var(--accent);text-decoration:none;border-bottom:1px dotted rgba(176,90,56,0.4)}}
.foot a:hover{{color:var(--text);border-bottom-color:var(--text)}}
@media (max-width:640px){{
  .wrap{{padding:32px 16px 48px}}
  h1{{font-size:30px}}
  .cell-title a{{font-size:14px}}
  .cell-date{{font-size:11px;padding:14px 10px}}
  thead th{{padding:10px 12px;font-size:10px}}
}}
</style>
</head>
<body>
<div class="wrap">
<div class="eyebrow">Event Analysis Team</div>
<h1>Analysis Reports</h1>
<div class="sub">총 <strong>{len(reports)}</strong>건의 보고서 · 최신 50건</div>
<table>
<thead><tr><th>보고서</th><th style="width:170px">생성일시</th></tr></thead>
<tbody>
{"".join(rows) if rows else empty_row}
</tbody>
</table>
<div class="foot">editorial_cream · <a href="https://doroper98.github.io/agents_reviewer/samples/">samples</a> · <a href="https://github.com/doroper98/agents_reviewer">github</a></div>
</div>
</body>
</html>'''

        index_path = os.path.join(output_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_html)
        logger.info(f"[report_synthesizer] Index page updated: {index_path}")


# Populate the block builder registry after class definition.
# Mapping: BlockType (17) → method on ReportSynthesizer.
# Step 3 covers builders that have v2 data sources; the rest return None
# placeholders so block tests render successfully.
ReportSynthesizer._BLOCK_BUILDERS = {
    "narrative":          ReportSynthesizer._payload_narrative,
    "claim_card":         ReportSynthesizer._payload_claim_card,
    "evidence_table":     ReportSynthesizer._payload_evidence_table,
    "timeline":           ReportSynthesizer._payload_timeline,
    "matrix":             ReportSynthesizer._payload_matrix,
    "actor_cards":        ReportSynthesizer._payload_actor_cards,
    "flow_chain":         ReportSynthesizer._payload_flow_chain,
    "scenario_table":     ReportSynthesizer._payload_scenario_table,
    "decomposition":      ReportSynthesizer._payload_decomposition,
    "argument_pair":      ReportSynthesizer._payload_argument_pair,
    "data_series":        ReportSynthesizer._payload_data_series,
    "watchlist":          ReportSynthesizer._payload_watchlist,
    "qna":                ReportSynthesizer._payload_qna,
    "callout":            ReportSynthesizer._payload_callout,
    "counter_hypothesis": ReportSynthesizer._payload_counter_hypothesis,
    "decision_matrix":    ReportSynthesizer._payload_decision_matrix,
    "risk_matrix":        ReportSynthesizer._payload_risk_matrix,
    "map":                ReportSynthesizer._payload_map,
}
