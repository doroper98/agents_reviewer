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
from src.agents.report_synthesizer import ReportSynthesizer

logger = logging.getLogger(__name__)

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
        self.report_synthesizer = ReportSynthesizer(config)

    async def _notify(
        self, message: str, status_callback: StatusCallback
    ) -> None:
        """Send status update via callback if available."""
        logger.info(message)
        if status_callback:
            await status_callback(message)

    def _build_text_report(self, result: FullAnalysisResult) -> str:
        """Build a clean code-block text summary for Telegram."""
        lines: list[str] = []
        sep = "\u2501" * 30

        event_name = ""
        if result.context:
            event_name = result.context.event_name or result.context.event_name_en
        lines.append(sep)
        lines.append(event_name or "Event Analysis")
        lines.append(sep)
        lines.append("")

        if result.context:
            lines.append("[상황판]")
            lines.append(result.context.summary)
            for fig in result.context.key_figures[:5]:
                label = fig.get("label", "")
                value = fig.get("value", "")
                lines.append(f"  {label}: {value}")
            lines.append("")

        if result.players:
            lines.append("[이해관계자]")
            for p in result.players.players[:6]:
                name = p.get("name", "")
                risk = p.get("risk_level", "")
                role = p.get("role_tag", "")
                lines.append(f"  {name} [{risk}] {role}")
            lines.append("")

        if result.dynamics:
            lines.append("[구조 및 역학관계]")
            lines.append(f"  프레임: {result.dynamics.framework}")
            lines.append(f"  긴장: {result.dynamics.core_tension[:80]}")
            lines.append(f"  통찰: {result.dynamics.key_insight[:80]}")
            lines.append("")

        if result.chain_reaction:
            lines.append("[파급효과]")
            chain_parts: list[str] = []
            for step in result.chain_reaction.chain[:6]:
                title = step.get("title", "")
                chain_parts.append(title)
            lines.append(" → ".join(chain_parts))
            lines.append("")

        if result.scenarios:
            lines.append("[시나리오]")
            circled = ["①", "②", "③", "④"]
            for i, sc in enumerate(result.scenarios.scenarios[:4]):
                c = circled[i] if i < len(circled) else f"{i+1}."
                name = sc.get("name", "")
                prob = sc.get("probability", "")
                lines.append(f"{c} {name} ({prob})")
            lines.append("")

        if result.scenarios and result.scenarios.watch_signals:
            lines.append("[감시 신호]")
            for ws in result.scenarios.watch_signals[:5]:
                icon = ws.get("icon", "●")
                signal = ws.get("signal", "")
                lines.append(f"  {icon} {signal}")
            lines.append("")

        if result.context and result.context.sources:
            lines.append(f"출처: {', '.join(result.context.sources[:5])}")

        lines.append(sep)
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

        # -- Phase 1: 맥락 분석관 --
        await self._notify(
            f"🔍 맥락 분석관: \"{event_description}\"에 대한 상황판을 구성하고 있습니다.",
            status_callback,
        )
        result.context = await self.context_analyst.analyze(request)

        event_name = result.context.event_name or event_description[:30]
        timeline_count = len(result.context.timeline)
        figures_count = len(result.context.key_figures)
        await self._notify(
            f"📋 맥락 분석관: \"{event_name}\"의 배경과 타임라인을 분석하였습니다.\n"
            f"  · 사건 분류: {result.context.category}\n"
            f"  · 타임라인 {timeline_count}건, 핵심 지표 {figures_count}건 수집\n"
            f"  · 신뢰도: {result.context.confidence_score * 100:.0f}%",
            status_callback,
        )

        # -- Phase 2: 이해관계자 분석관 + 구조 및 역학관계 분석관 --
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
            f"  · {result.players.power_dynamics[:100]}\n"
            f"  · 신뢰도: {result.players.confidence_score * 100:.0f}%",
            status_callback,
        )

        await self._notify(
            f"⚡ 구조 및 역학관계 분석관: {player_names} 간의 구조적 역학관계에 대해 분석하고 있습니다.",
            status_callback,
        )
        result.dynamics = await self.dynamics_analyst.analyze(
            result.context, result.players
        )
        await self._notify(
            f"⚡ 구조 및 역학관계 분석관: {result.dynamics.framework} 프레임워크를 적용하여 분석하였습니다.\n"
            f"  · 핵심 통찰: {result.dynamics.key_insight[:120]}\n"
            f"  · 신뢰도: {result.dynamics.confidence_score * 100:.0f}%",
            status_callback,
        )

        # -- Phase 3: 파급효과 분석관 + 시나리오 구조 분석관 --
        await self._notify(
            f"🔗 파급효과 분석관: \"{event_name}\"에서 비롯되는 연쇄반응과 도미노 효과를 추적하고 있습니다.",
            status_callback,
        )
        result.chain_reaction = await self.chain_reaction_analyst.analyze(
            result.context, result.players, result.dynamics
        )
        chain_summary = " → ".join(
            [s.get("title", "") for s in result.chain_reaction.chain[:4]]
        )
        await self._notify(
            f"🔗 파급효과 분석관: {len(result.chain_reaction.chain)}단계 인과 사슬을 분석하였습니다.\n"
            f"  · {chain_summary}\n"
            f"  · 차단점 {len(result.chain_reaction.break_points)}건 식별\n"
            f"  · 신뢰도: {result.chain_reaction.confidence_score * 100:.0f}%",
            status_callback,
        )

        await self._notify(
            f"🎲 시나리오 구조 분석관: 향후 전개 가능한 시나리오를 설계하고 있습니다.",
            status_callback,
        )
        result.scenarios = await self.scenario_architect.analyze(
            result.context, result.players, result.dynamics, result.chain_reaction
        )
        scenario_names = " / ".join(
            [s.get("name", "") for s in result.scenarios.scenarios]
        )
        await self._notify(
            f"🎲 시나리오 구조 분석관: {len(result.scenarios.scenarios)}개 시나리오를 설계하였습니다.\n"
            f"  · {scenario_names}\n"
            f"  · 감시 신호 {len(result.scenarios.watch_signals)}건 식별\n"
            f"  · 신뢰도: {result.scenarios.confidence_score * 100:.0f}%",
            status_callback,
        )

        # -- Phase 4: 보고서 생성 --
        await self._notify(
            "📝 보고서를 생성하고 있습니다.",
            status_callback,
        )

        result.total_duration_seconds = time.time() - start_time

        report_url = await self.report_synthesizer.synthesize(result)
        result.report_url = report_url

        return result
