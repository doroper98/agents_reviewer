"""Orchestrator -- 4-Phase analysis pipeline coordinator."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from typing import Any, Callable, Coroutine, Optional

from src.archetypes.registry import get_archetype, list_archetypes
from src.config import Config
from src.models import AnalysisRequest, AnalysisStrategy, FullAnalysisResult
from src.agents.context_analyst import ContextAnalyst
from src.agents.player_analyst import PlayerAnalyst
from src.agents.dynamics_analyst import DynamicsAnalyst
from src.agents.chain_reaction_analyst import ChainReactionAnalyst
from src.agents.scenario_architect import ScenarioArchitect
from src.agents.visual_analyst import VisualAnalyst
from src.agents.report_synthesizer import ReportSynthesizer

logger = logging.getLogger(__name__)

VERSION = "v2.7.0"

QUICK_MODE_KEYWORDS = {"짧게", "간략히", "간략하게", "빠르게", "요약", "간단히", "간단하게"}

StatusCallback = Optional[Callable[[str], Coroutine[Any, Any, None]]]


class Orchestrator:
    """Coordinates the 4-phase analysis pipeline."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.context_analyst = ContextAnalyst(config)
        self.player_analyst = PlayerAnalyst(config)
        self.dynamics_analyst = DynamicsAnalyst(config)
        self.chain_reaction_analyst = ChainReactionAnalyst(config)
        self.scenario_architect = ScenarioArchitect(config)
        self.visual_analyst = VisualAnalyst(config)
        self.report_synthesizer = ReportSynthesizer(config)

    @staticmethod
    def _progress_bar(step: int, total: int = 7) -> str:
        """Generate a text progress bar."""
        pct = int(step / total * 100)
        filled = int(step / total * 20)
        bar = "▓" * filled + "░" * (20 - filled)
        return f"{bar} {pct}%"

    @staticmethod
    def _empty_strategy_fallback() -> AnalysisStrategy:
        """LLM 호출 실패 또는 파싱 실패 시 사용할 최소 유효 AnalysisStrategy.

        Anti-pattern #3 (dict 회귀) 방지를 위해 빈 dict 가 아닌 빈 객체로 폴백.
        Pydantic validator 를 통과해야 하므로 core_questions/recommended_lenses 에
        한 항목씩 더미를 채운다.
        """
        return AnalysisStrategy(
            event_type="unknown",
            user_intent="what_happened",
            intent_confidence=0.5,
            core_questions=["사건의 핵심 사실을 파악한다"],
            recommended_lenses=["context"],
            evidence_plan=[],
            report_archetype="six_act_theater",
            section_plan=[],
            visualization_plan=[],
            theme="burgundy",
            legacy_directives={},
        )

    async def _generate_analysis_strategy(
        self, event_name: str, category: str, summary: str
    ) -> AnalysisStrategy:
        """Generate AnalysisStrategy based on the event context.

        Step 1 (v2.5.0): dict 반환에서 정식 Pydantic 모델 (AnalysisStrategy) 반환으로 승격.
        실패 시 ``_empty_strategy_fallback()`` 을 반환 (Anti-pattern #3 방지).
        per-agent directive 문자열은 ``strategy.legacy_directives`` 에 보존된다.
        """
        prompt = (
            "당신은 세계 최고 수준의 분석 전략 기획자. 아래 사건을 보고 다음을 결정:\n"
            "1) user_intent — 사용자가 가장 알고 싶어 하는 질문 유형 (7종 중 1)\n"
            "2) core_questions — 이 사건이 답해야 할 핵심 질문 (1~5개)\n"
            "3) recommended_lenses — 적용할 분석 렌즈 ID (1~4개)\n"
            "4) report_archetype — 이 사건에 가장 적합한 보고서 아키타입 (3종 중 1)\n"
            "5) 각 에이전트에게 이 사건을 발골할 최적의 분석 기법 지시\n"
            "6) 이 사건에 불필요한 에이전트는 스킵 지정\n"
            "7) 보고서 테마 선택\n\n"
            "사건명: " + event_name + "\n"
            "분류: " + category + "\n"
            "요약: " + summary[:500] + "\n\n"
            "=== user_intent 7종 (이 중 정확히 1개 선택) ===\n"
            "what_happened: 사실 파악 — 무슨 일이 있었나\n"
            "why_happened: 원인 분석 — 왜 그런 일이 있었나\n"
            "who_benefits: 이해관계 분석 — 누가 이득/손해를 보나\n"
            "where_spreads: 파급효과 — 이 사건이 어디로 번지나\n"
            "what_next: 시나리오/전망 — 앞으로 어떻게 될 것인가\n"
            "where_vulnerable: 취약점 분석 — 어디가 약한 고리인가\n"
            "what_to_do: 의사결정 — 어떻게 대응해야 하나\n\n"
            "=== report_archetype 3종 (정확히 1개 선택, archetype_id 그대로 출력) ===\n"
            "six_act_theater (기본값): 인물극형 사건 (전쟁, 외교, 정치 갈등, 리더십, 선거).\n"
            "  · suitable_intents: 7종 모두 가능. 분류가 애매하면 이걸로 간다.\n"
            "  · 섹션 흐름: 상황 → 행위자 → 구조 → 인과 → 시나리오 → 감시 신호 (6막)\n"
            "financial_transmission: 시장/거시 사건 (환율, 금리, 자산 가격, 통화 정책, 신용 시장).\n"
            "  · suitable_intents: where_spreads, where_vulnerable, what_next 우선.\n"
            "  · suitable_event_types: financial, market, macro, currency, interest_rate, asset_price 등.\n"
            "  · 섹션 흐름: 가격 반응 → 포지션·자금흐름 → 전이 경로 → 취약 고리 → 스트레스 시나리오 → 관찰 지표\n"
            "tech_decomposition: 기술/AI/IT 사건 (모델 출시, 시스템 장애, 사이버 보안, 인프라).\n"
            "  · suitable_intents: where_vulnerable, what_to_do, why_happened 우선.\n"
            "  · suitable_event_types: tech, ai, it, software, model_release, system_outage, cyber_security 등.\n"
            "  · 섹션 흐름: 문제 정의 → 시스템 구조 → 병목 → 성능·비용·리스크 → 대안 비교 → 실행 권고\n\n"
            "선택 매트릭스 (강한 가이드):\n"
            "- user_intent='where_spreads' AND event_type∈{financial, market, macro, currency, interest_rate} → financial_transmission\n"
            "- event_type∈{tech, ai, it, software, model_release, system_outage} → tech_decomposition\n"
            "- 그 외 (인물극, 외교, 갈등, 정치, 일반) → six_act_theater\n\n"
            "=== 분석 기법 레퍼런스 ===\n"
            "[인텔리전스] ACH(경쟁가설분석), Red Team, Key Assumptions Check, I&W(징후경보)\n"
            "[지정학/전략] DIME(외교·정보·군사·경제), PMESII(6차원환경), Escalation Ladder, Center of Gravity\n"
            "[경제/금융] Transmission Channel(전이경로), Stress Test, Input-Output(산업연관), Flow of Funds\n"
            "[구조/시스템] Systems Dynamics(피드백루프), Network Analysis, Fault Tree, Bow-Tie\n"
            "[의사결정/전망] Decision Tree, Cone of Plausibility, Pre-mortem, Bayesian Updating\n\n"
            "=== 보고서 테마 ===\n"
            "burgundy: 기본 버건디 (범용)\n"
            "geopolitical: 다크 네이비+레드 (지정학, 안보, 군사, 전쟁)\n"
            "financial: 딥 블루+그린/레드 (금융, 경제, 시장, 투자)\n"
            "tech: 다크 슬레이트+시안 (기술, AI, IT, 사이버)\n"
            "nature: 다크 그린+앰버 (환경, 에너지, 기후, 농업)\n"
            "liquidglass: iOS Liquid Glass (프리미엄, 미래적, 혁신, 디자인, 문화, 트렌드)\n\n"
            "=== 5개 에이전트 ===\n"
            "1. players: 이해관계자 식별, 입장·전략 분석\n"
            "2. dynamics: 구조적 원인, 힘의 역학 분석\n"
            "3. chain_reaction: 인과 사슬, 파급효과 추적\n"
            "4. scenarios: 향후 전개 경로 설계\n"
            "5. visuals: 시각화 (SVG 관계도, 지도, 차트)\n\n"
            "각 에이전트 지시사항:\n"
            "- 위 레퍼런스에서 이 사건에 최적인 기법을 골라 구체적으로 지시 (1~2문장)\n"
            "- 레퍼런스에 없는 기법도 적합하면 자유롭게 사용 가능\n"
            "- 이 사건에 맞지 않는 분석 함정도 명시\n\n"
            "스킵 판단: 가치를 못 더하면 skip. context/visuals는 스킵 불가.\n\n"
            "반드시 아래 JSON만 출력 (event_type/user_intent/intent_confidence/core_questions/recommended_lenses/report_archetype 필수):\n"
            '{"event_type":"사건 유형 한 단어 (예: financial, tech, war, diplomacy, currency, model_release, cyber_security)",'
            '"user_intent":"what_happened|why_happened|who_benefits|where_spreads|what_next|where_vulnerable|what_to_do",'
            '"intent_confidence":0.0~1.0,'
            '"core_questions":["질문1","질문2"],'
            '"recommended_lenses":["lens_id1","lens_id2"],'
            '"report_archetype":"six_act_theater|financial_transmission|tech_decomposition",'
            '"players":"지시","dynamics":"지시","chain_reaction":"지시",'
            '"scenarios":"지시","visuals":"지시",'
            '"skip":["스킵할 에이전트명"],"theme":"burgundy|geopolitical|financial|tech|nature|liquidglass"}\n'
        )

        try:
            claude_bin = shutil.which("claude")
            if claude_bin is None:
                logger.warning("[orchestrator] claude CLI not found; using empty strategy")
                return self._empty_strategy_fallback()

            cmd = [
                claude_bin,
                "-p", prompt,
                "--output-format", "text",
                "--model", self.config.model_name,
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
                logger.warning("[orchestrator] Strategy generation failed; using empty strategy")
                return self._empty_strategy_fallback()

            raw = stdout.decode().strip()
            import re
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                logger.warning("[orchestrator] No JSON in strategy response; using empty strategy")
                return self._empty_strategy_fallback()

            raw_dict = json.loads(match.group())

            # Pull per-agent directive strings into legacy_directives shim.
            legacy_keys = ("players", "dynamics", "chain_reaction", "scenarios", "visuals")
            legacy_directives: dict[str, str] = {
                k: raw_dict.pop(k, "") for k in legacy_keys
            }
            raw_dict["legacy_directives"] = legacy_directives

            # Validate archetype_id against registry; unknown values fall back to default.
            requested_archetype = raw_dict.get("report_archetype", "")
            if requested_archetype and requested_archetype not in list_archetypes():
                logger.warning(
                    "[orchestrator] LLM emitted unknown archetype_id=%r; "
                    "falling back to six_act_theater (registered: %s)",
                    requested_archetype, list_archetypes(),
                )
                raw_dict["report_archetype"] = "six_act_theater"

            strategy = AnalysisStrategy.model_validate(raw_dict)

            logger.info(
                "[orchestrator] AnalysisStrategy generated for: %s\n"
                "  user_intent: %s (confidence=%.2f)\n"
                "  event_type: %s\n"
                "  core_questions: %s\n"
                "  recommended_lenses: %s\n"
                "  report_archetype: %s\n"
                "  theme: %s\n"
                "  skip_agents: %s",
                event_name,
                strategy.user_intent, strategy.intent_confidence,
                strategy.event_type,
                strategy.core_questions,
                strategy.recommended_lenses,
                strategy.report_archetype,
                strategy.theme,
                strategy.skip_agents,
            )
            return strategy

        except Exception as e:
            logger.warning(
                "[orchestrator] Strategy generation error: %s; using empty strategy", e
            )
            return self._empty_strategy_fallback()

    async def _notify(
        self, message: str, status_callback: StatusCallback
    ) -> None:
        """Send status update via callback if available."""
        logger.info(message)
        if status_callback:
            await status_callback(message)

    def _build_text_report(self, result: FullAnalysisResult) -> str:
        """Build a clean text summary for Telegram (without glossary)."""
        lines: list[str] = []

        event_name = ""
        if result.context:
            event_name = result.context.event_name or result.context.event_name_en
        lines.append(f"<{event_name or 'Event Analysis'}>")
        lines.append("")

        if result.context:
            lines.append("[상황인식]")
            lines.append("")
            lines.append(result.context.summary)
            lines.append("")
            for fig in result.context.key_figures[:6]:
                label = fig.get("label", "")
                value = fig.get("value", "")
                context = fig.get("context", "")
                ctx_str = f" ({context})" if context else ""
                lines.append(f" -> {label}: {value}{ctx_str}")
            lines.append("")

        if result.players:
            lines.append("[이해관계자]")
            lines.append("")
            for i, p in enumerate(result.players.players[:8], 1):
                name = p.get("name", "")
                role = p.get("role_tag", "")
                lines.append(f"{i}) {name} : {role}")
            lines.append("")

        if result.dynamics:
            lines.append("[구조 및 상호작용]")
            lines.append("")
            lines.append(f"a. 프레임: {result.dynamics.framework}")
            lines.append(f"b. 긴장: {result.dynamics.core_tension}")
            lines.append(f"c. 통찰: {result.dynamics.key_insight}")
            lines.append("")

        if result.chain_reaction:
            lines.append("[연쇄반응]")
            lines.append("")
            for step in result.chain_reaction.chain[:12]:
                title = step.get("title", "")
                desc = step.get("description", "")
                if desc:
                    lines.append(f"→ {title}")
                else:
                    lines.append(f"→ {title}")
            lines.append("")

        if result.scenarios:
            lines.append("[향후 시나리오]")
            lines.append("")
            circled = ["①", "②", "③", "④"]
            for i, sc in enumerate(result.scenarios.scenarios[:4]):
                c = circled[i] if i < len(circled) else f"{i+1}."
                name = sc.get("name", "")
                prob = sc.get("probability", "")
                lines.append(f"{c} {name} ({prob})")
            lines.append("")

        if result.scenarios and result.scenarios.watch_signals:
            lines.append("[지켜봐야 할 시그널]")
            lines.append("")
            for ws in result.scenarios.watch_signals[:5]:
                icon = ws.get("icon", "●")
                signal = ws.get("signal", "")
                lines.append(f"{icon} {signal}")
            lines.append("")

        if result.context and result.context.sources:
            lines.append(f"출처: {', '.join(result.context.sources[:8])}")

        return "\n".join(lines)

    def _build_glossary_text(self, result: FullAnalysisResult) -> str:
        """Build glossary as a separate text for Telegram."""
        all_terms: list[dict] = []
        for section in [result.context, result.players, result.dynamics, result.chain_reaction, result.scenarios]:
            if section and hasattr(section, "glossary") and section.glossary:
                all_terms.extend(section.glossary)
        seen: set[str] = set()
        unique_terms: list[dict] = []
        for t in all_terms:
            term = t.get("term", "")
            if term and term not in seen:
                seen.add(term)
                unique_terms.append(t)
        if not unique_terms:
            return ""
        lines: list[str] = ["[용어 정의]", ""]
        for t in unique_terms:
            lines.append(f"  {t.get('term', '')} : {t.get('definition', '')}")
        return "\n".join(lines)

    async def run_analysis(
        self,
        event_description: str,
        chat_id: int,
        status_callback: StatusCallback = None,
    ) -> FullAnalysisResult:
        """Execute the full analysis pipeline."""
        start_time = time.time()

        # Detect quick mode from keywords
        quick_mode = any(kw in event_description for kw in QUICK_MODE_KEYWORDS)
        if quick_mode:
            # Switch all agents to Sonnet for speed
            for agent in [
                self.context_analyst, self.player_analyst,
                self.dynamics_analyst, self.chain_reaction_analyst,
                self.scenario_architect, self.visual_analyst,
            ]:
                agent.model_name = self.config.model_name_light
            logger.info("[orchestrator] Quick mode enabled — all agents using Sonnet")

        request = AnalysisRequest(
            event_description=event_description,
            chat_id=chat_id,
        )
        result = FullAnalysisResult(request=request)

        mode_label = " ⚡빠른분석" if quick_mode else ""

        # -- Phase 1: 상황 분석관 --
        await self._notify(
            f"🔍 상황 분석관: \"{event_description}\"에 대한 상황을 인식하고 있습니다.\n"
            f"Analysis Team {VERSION}{mode_label}",
            status_callback,
        )
        result.context = await self.context_analyst.analyze(request)

        event_name = result.context.event_name or event_description[:30]
        timeline_count = len(result.context.timeline)
        figures_count = len(result.context.key_figures)
        await self._notify(
            f"📋 상황 분석관: \"{event_name}\"의 배경과 타임라인을 분석하였습니다.\n"
            f"  · 사건 분류: {result.context.category}\n"
            f"  · 타임라인 {timeline_count}건, 핵심 지표 {figures_count}건 수집\n"
            f"  · 신뢰도: {result.context.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(1)}",
            status_callback,
        )

        # -- Strategic Planning: 분석 전략 기획 --
        if quick_mode:
            # Quick mode: 전략기획 스킵, 핵심 에이전트만 실행. AnalysisStrategy 는 빈 폴백 + skip 지정.
            strategy = self._empty_strategy_fallback()
            strategy.skip_agents = ["players", "dynamics", "chain_reaction"]
            skip_agents = set(strategy.skip_agents)
            logger.info("[orchestrator] Quick mode: skipping players, dynamics, chain_reaction")
            await self._notify(
                f"⚡ 빠른분석: 상황분석 → 시나리오 → 시각화 → 보고서",
                status_callback,
            )
        else:
            await self._notify(
                f"🧭 전략 기획: \"{event_name}\"에 최적화된 분석 전략을 수립하고 있습니다.",
                status_callback,
            )
            strategy = await self._generate_analysis_strategy(
                event_name,
                result.context.category,
                result.context.summary,
            )
            skip_agents = set(strategy.skip_agents)
            if skip_agents:
                logger.info(f"[orchestrator] Skipping agents: {skip_agents}")
                await self._notify(
                    f"🧭 전략 기획 완료. 스킵: {', '.join(skip_agents) or '없음'}",
                    status_callback,
                )

        # Persist the strategy onto the result so downstream consumers (template, logs) can read it.
        result.strategy = strategy

        step = 1

        # -- Phase 2: 이해관계자 분석관 + 구조 분석관 --
        if "players" not in skip_agents:
            player_context = result.context.summary[:50] if result.context.summary else event_name
            await self._notify(
                f"👥 이해관계자 분석관: \"{player_context}\"와 관련된 핵심 행위자들을 식별하고 있습니다.",
                status_callback,
            )
            result.players = await self.player_analyst.analyze(
                result.context, directive=strategy.legacy_directives.get("players", "")
            )
            player_names = ", ".join(
                [p.get("name", "") for p in result.players.players[:5]]
            )
            step += 1
            await self._notify(
                f"👥 이해관계자 분석관: {player_names} 등 {len(result.players.players)}개 행위자 분석 완료.\n"
                f"  · 신뢰도: {result.players.confidence_score * 100:.0f}%\n"
                f"{self._progress_bar(step)}",
                status_callback,
            )

        if "dynamics" not in skip_agents:
            await self._notify(
                f"⚡ 구조 분석관: 구조적 원인과 힘의 역학을 분석하고 있습니다.",
                status_callback,
            )
            result.dynamics = await self.dynamics_analyst.analyze(
                result.context, result.players, directive=strategy.legacy_directives.get("dynamics", "")
            )
            step += 1
            await self._notify(
                f"⚡ 구조 분석관: {result.dynamics.framework} 관점으로 분석 완료.\n"
                f"  · 핵심 통찰: {result.dynamics.key_insight[:200]}\n"
                f"  · 신뢰도: {result.dynamics.confidence_score * 100:.0f}%\n"
                f"{self._progress_bar(step)}",
                status_callback,
            )

        # -- Phase 3: 연쇄반응 분석관 + 향후 시나리오 분석관 --
        if "chain_reaction" not in skip_agents:
            await self._notify(
                f"🔗 연쇄반응 분석관: \"{event_name}\"에서 비롯되는 파급효과를 추적하고 있습니다.",
                status_callback,
            )
            result.chain_reaction = await self.chain_reaction_analyst.analyze(
                result.context, result.players, result.dynamics,
                directive=strategy.legacy_directives.get("chain_reaction", ""),
            )
            chain_summary = " → ".join(
                [s.get("title", "") for s in result.chain_reaction.chain[:4]]
            )
            step += 1
            await self._notify(
                f"🔗 연쇄반응 분석관: {len(result.chain_reaction.chain)}단계 인과 사슬 분석 완료.\n"
                f"  · {chain_summary}\n"
                f"  · 신뢰도: {result.chain_reaction.confidence_score * 100:.0f}%\n"
                f"{self._progress_bar(step)}",
                status_callback,
            )

        if "scenarios" not in skip_agents:
            await self._notify(
                f"🎲 시나리오 설계관: 향후 전개 가능한 시나리오를 설계하고 있습니다.",
                status_callback,
            )
            result.scenarios = await self.scenario_architect.analyze(
                result.context, result.players, result.dynamics, result.chain_reaction,
                directive=strategy.legacy_directives.get("scenarios", ""),
            )
            scenario_names = " / ".join(
                [s.get("name", "") for s in result.scenarios.scenarios]
            )
            step += 1
            await self._notify(
                f"🎲 시나리오 설계관: {len(result.scenarios.scenarios)}개 시나리오 설계 완료.\n"
                f"  · {scenario_names}\n"
                f"  · 감시 신호 {len(result.scenarios.watch_signals)}건 식별\n"
                f"  · 신뢰도: {result.scenarios.confidence_score * 100:.0f}%\n"
                f"{self._progress_bar(step)}",
                status_callback,
            )

        # -- Visual Analyst: 시각화 생성 --
        await self._notify(
            "🎨 시각화 분석관: 분석 결과를 시각적 요소로 변환하고 있습니다.",
            status_callback,
        )
        result.visuals = await self.visual_analyst.analyze(
            result.context, result.players, result.dynamics,
            result.chain_reaction, result.scenarios,
            directive=strategy.legacy_directives.get("visuals", ""),
        )
        visual_types: list[str] = []
        if result.visuals.svg_content:
            visual_types.append("관계도")
        if result.visuals.mermaid_code:
            visual_types.append("플로우차트")
        if result.visuals.leaflet_config.get("enabled"):
            visual_types.append("지도")
        if result.visuals.chart_config.get("enabled"):
            visual_types.append("차트")
        await self._notify(
            f"🎨 시각화 분석관: {', '.join(visual_types) or '인포그래픽'} 생성 완료.\n"
            f"  · 핵심 지표 {len(result.visuals.key_metrics)}건\n"
            f"  · 신뢰도: {result.visuals.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(6)}",
            status_callback,
        )

        # -- Phase 4: 보고서 생성 --
        await self._notify(
            f"📝 보고서를 생성하고 있습니다.\n"
            f"{self._progress_bar(6)}",
            status_callback,
        )

        result.total_duration_seconds = time.time() - start_time

        report_theme = strategy.theme or "burgundy"
        archetype = get_archetype(strategy.report_archetype)
        logger.info(
            "[orchestrator] Routing report through archetype=%s (template=%s)",
            archetype.archetype_id, archetype.template_path(),
        )
        report_url = await self.report_synthesizer.synthesize(
            result, theme=report_theme, archetype=archetype,
        )
        result.report_url = report_url

        # Restore original model assignments after quick mode
        if quick_mode:
            self.context_analyst.model_name = self.config.model_name_light
            self.player_analyst.model_name = self.config.model_name_light
            self.dynamics_analyst.model_name = self.config.model_name
            self.chain_reaction_analyst.model_name = self.config.model_name_light
            self.scenario_architect.model_name = self.config.model_name
            self.visual_analyst.model_name = self.config.model_name

        return result
