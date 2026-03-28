"""Orchestrator -- 4-Phase analysis pipeline coordinator."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Coroutine, Optional

from src.config import Config
from src.models import AnalysisRequest, FullAnalysisResult
from src.agents.context_analyst import ContextAnalyst
from src.agents.player_analyst import PlayerAnalyst
from src.agents.dynamics_analyst import DynamicsAnalyst
from src.agents.chain_reaction_analyst import ChainReactionAnalyst
from src.agents.scenario_architect import ScenarioArchitect
from src.agents.visual_analyst import VisualAnalyst
from src.agents.report_synthesizer import ReportSynthesizer

logger = logging.getLogger(__name__)

VERSION = "v1.5.0"

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
        """Execute the full 4-phase analysis pipeline."""
        start_time = time.time()

        request = AnalysisRequest(
            event_description=event_description,
            chat_id=chat_id,
        )
        result = FullAnalysisResult(request=request)

        # -- Phase 1: 상황인식 분석관 --
        await self._notify(
            f"🔍 상황인식 분석관: \"{event_description}\"에 대한 상황을 인식하고 있습니다.\n"
            f"Analysis Team {VERSION}",
            status_callback,
        )
        result.context = await self.context_analyst.analyze(request)

        event_name = result.context.event_name or event_description[:30]
        timeline_count = len(result.context.timeline)
        figures_count = len(result.context.key_figures)
        await self._notify(
            f"📋 상황인식 분석관: \"{event_name}\"의 배경과 타임라인을 분석하였습니다.\n"
            f"  · 사건 분류: {result.context.category}\n"
            f"  · 타임라인 {timeline_count}건, 핵심 지표 {figures_count}건 수집\n"
            f"  · 신뢰도: {result.context.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(1)}",
            status_callback,
        )

        # -- Phase 2: 이해관계자 분석관 + 구조 및 상호작용 분석관 --
        player_context = result.context.summary[:50] if result.context.summary else event_name
        await self._notify(
            f"👥 이해관계자 분석관: \"{player_context}\"와 관련된 핵심 행위자들을 식별하고 있습니다.",
            status_callback,
        )
        result.players = await self.player_analyst.analyze(result.context)

        player_names = ", ".join(
            [p.get("name", "") for p in result.players.players[:5]]
        )
        await self._notify(
            f"👥 이해관계자 분석관: {player_names} 등 {len(result.players.players)}개 행위자의 입장과 전략을 분석하였습니다.\n"
            f"  · {result.players.power_dynamics[:150]}\n"
            f"  · 신뢰도: {result.players.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(2)}",
            status_callback,
        )

        await self._notify(
            f"⚡ 구조 및 상호작용 분석관: {player_names} 간의 구조적 상호작용에 대해 분석하고 있습니다.",
            status_callback,
        )
        result.dynamics = await self.dynamics_analyst.analyze(
            result.context, result.players
        )
        await self._notify(
            f"⚡ 구조 및 상호작용 분석관: {result.dynamics.framework} 프레임워크를 적용하여 분석하였습니다.\n"
            f"  · 핵심 통찰: {result.dynamics.key_insight[:200]}\n"
            f"  · 신뢰도: {result.dynamics.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(3)}",
            status_callback,
        )

        # -- Phase 3: 연쇄반응 분석관 + 향후 시나리오 분석관 --
        await self._notify(
            f"🔗 연쇄반응 분석관: \"{event_name}\"에서 비롯되는 연쇄반응과 파급효과를 추적하고 있습니다.",
            status_callback,
        )
        result.chain_reaction = await self.chain_reaction_analyst.analyze(
            result.context, result.players, result.dynamics
        )
        chain_summary = " → ".join(
            [s.get("title", "") for s in result.chain_reaction.chain[:4]]
        )
        await self._notify(
            f"🔗 연쇄반응 분석관: {len(result.chain_reaction.chain)}단계 인과 사슬을 분석하였습니다.\n"
            f"  · {chain_summary}\n"
            f"  · 차단점 {len(result.chain_reaction.break_points)}건 식별\n"
            f"  · 신뢰도: {result.chain_reaction.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(4)}",
            status_callback,
        )

        await self._notify(
            f"🎲 향후 시나리오 분석관: 향후 전개 가능한 시나리오를 설계하고 있습니다.",
            status_callback,
        )
        result.scenarios = await self.scenario_architect.analyze(
            result.context, result.players, result.dynamics, result.chain_reaction
        )
        scenario_names = " / ".join(
            [s.get("name", "") for s in result.scenarios.scenarios]
        )
        await self._notify(
            f"🎲 향후 시나리오 분석관: {len(result.scenarios.scenarios)}개 시나리오를 설계하였습니다.\n"
            f"  · {scenario_names}\n"
            f"  · 감시 신호 {len(result.scenarios.watch_signals)}건 식별\n"
            f"  · 신뢰도: {result.scenarios.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(5)}",
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

        report_url = await self.report_synthesizer.synthesize(result)
        result.report_url = report_url

        return result
