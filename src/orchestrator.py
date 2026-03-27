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
    """Coordinates the 4-phase analysis pipeline.

    Phase 1: Context Analyst (situation board)
    Phase 2: Player Analyst + Dynamics Analyst (sequential)
    Phase 3: Chain Reaction Analyst + Scenario Architect (sequential)
    Phase 4: Report Synthesizer (report generation + Cloudflare upload)
    """

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

        # Context
        if result.context:
            lines.append("[상황판]")
            lines.append(result.context.summary)
            for fig in result.context.key_figures[:5]:
                label = fig.get("label", "")
                value = fig.get("value", "")
                lines.append(f"  {label}: {value}")
            lines.append("")

        # Players
        if result.players:
            lines.append("[플레이어]")
            for p in result.players.players[:6]:
                name = p.get("name", "")
                risk = p.get("risk_level", "")
                lines.append(f"  {name} [{risk}]")
            lines.append("")

        # Dynamics
        if result.dynamics:
            lines.append("[역학]")
            lines.append(f"  프레임: {result.dynamics.framework}")
            lines.append(f"  긴장: {result.dynamics.core_tension[:80]}")
            lines.append(f"  통찰: {result.dynamics.key_insight[:80]}")
            lines.append("")

        # Chain Reaction
        if result.chain_reaction:
            lines.append("[연쇄반응]")
            chain_parts: list[str] = []
            for step in result.chain_reaction.chain[:6]:
                num = step.get("step", "")
                title = step.get("title", "")
                chain_parts.append(f"\u2460{title}" if num == 1 else f"{title}")
            lines.append(" \u2192 ".join(chain_parts))
            lines.append("")

        # Scenarios
        if result.scenarios:
            lines.append("[시나리오]")
            circled = ["\u2460", "\u2461", "\u2462", "\u2463"]
            for i, sc in enumerate(result.scenarios.scenarios[:4]):
                c = circled[i] if i < len(circled) else f"{i+1}."
                name = sc.get("name", "")
                prob = sc.get("probability", "")
                lines.append(f"{c} {name} ({prob})")
            lines.append("")

        # Watch Signals
        if result.scenarios and result.scenarios.watch_signals:
            lines.append("[감시 신호]")
            for ws in result.scenarios.watch_signals[:5]:
                icon = ws.get("icon", "\u25cf")
                signal = ws.get("signal", "")
                lines.append(f"  {icon} {signal}")
            lines.append("")

        # Sources
        if result.context and result.context.sources:
            lines.append(f"\ucd9c\ucc98: {', '.join(result.context.sources[:5])}")

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

        # -- Phase 1: Context Analyst --
        await self._notify(
            "\U0001f50d Context Analyst: \uc0c1\ud669\ud310 \uad6c\uc131 \uc911...",
            status_callback,
        )
        result.context = await self.context_analyst.analyze(request)
        await self._notify(
            f"\U0001f4cb Context Analyst:\n"
            f"  \uc0ac\uac74: {result.context.event_name}\n"
            f"  \ubd84\ub958: {result.context.category}\n"
            f"  \ud0c0\uc784\ub77c\uc778 {len(result.context.timeline)}\uac74 \uc218\uc9d1\n"
            f"  \uc2e0\ub8b0\ub3c4: {result.context.confidence_score}",
            status_callback,
        )

        # -- Phase 2: Player Analyst + Dynamics Analyst (sequential) --
        await self._notify(
            "\U0001f465 Player Analyst: \ud50c\ub808\uc774\uc5b4 \uc2dd\ubcc4 \uc911...",
            status_callback,
        )
        result.players = await self.player_analyst.analyze(result.context)
        player_names = ", ".join(
            [p.get("name", "") for p in result.players.players[:5]]
        )
        await self._notify(
            f"\U0001f465 Player Analyst:\n"
            f"  \uc2dd\ubcc4\ub41c \ud50c\ub808\uc774\uc5b4: {player_names}\n"
            f"  {result.players.power_dynamics[:80]}\n"
            f"  \uc2e0\ub8b0\ub3c4: {result.players.confidence_score}",
            status_callback,
        )

        await self._notify(
            "\u26a1 Dynamics Analyst: \uad6c\uc870 \uc5ed\ud559 \ubd84\uc11d \uc911...",
            status_callback,
        )
        result.dynamics = await self.dynamics_analyst.analyze(
            result.context, result.players
        )
        await self._notify(
            f"\u26a1 Dynamics Analyst:\n"
            f"  \ud504\ub808\uc784: {result.dynamics.framework}\n"
            f"  \ud575\uc2ec: {result.dynamics.key_insight[:80]}\n"
            f"  \uc2e0\ub8b0\ub3c4: {result.dynamics.confidence_score}",
            status_callback,
        )

        # -- Phase 3: Chain Reaction Analyst + Scenario Architect (sequential) --
        await self._notify(
            "\U0001f517 Chain Reaction Analyst: \uc5f0\uc1c4\ubc18\uc751 \ucd94\uc801 \uc911...",
            status_callback,
        )
        result.chain_reaction = await self.chain_reaction_analyst.analyze(
            result.context, result.players, result.dynamics
        )
        await self._notify(
            f"\U0001f517 Chain Reaction Analyst:\n"
            f"  \uc778\uacfc \uc0ac\uc2ac {len(result.chain_reaction.chain)}\ub2e8\uacc4\n"
            f"  \ucc28\ub2e8\uc810 {len(result.chain_reaction.break_points)}\uac74\n"
            f"  \uc2e0\ub8b0\ub3c4: {result.chain_reaction.confidence_score}",
            status_callback,
        )

        await self._notify(
            "\U0001f3b2 Scenario Architect: \uc2dc\ub098\ub9ac\uc624 \uc124\uacc4 \uc911...",
            status_callback,
        )
        result.scenarios = await self.scenario_architect.analyze(
            result.context, result.players, result.dynamics, result.chain_reaction
        )
        scenario_names = " / ".join(
            [s.get("name", "") for s in result.scenarios.scenarios]
        )
        await self._notify(
            f"\U0001f3b2 Scenario Architect:\n"
            f"  \uc2dc\ub098\ub9ac\uc624: {scenario_names}\n"
            f"  \uac10\uc2dc \uc2e0\ud638 {len(result.scenarios.watch_signals)}\uac74\n"
            f"  \uc2e0\ub8b0\ub3c4: {result.scenarios.confidence_score}",
            status_callback,
        )

        # -- Phase 4: Report Synthesizer --
        await self._notify(
            "\U0001f4dd Report Synthesizer: \ubcf4\uace0\uc11c \uc0dd\uc131 \uc911...",
            status_callback,
        )

        result.total_duration_seconds = time.time() - start_time

        report_url = await self.report_synthesizer.synthesize(result)
        result.report_url = report_url

        # Build text report for Telegram
        text_report = self._build_text_report(result)
        await self._notify(
            f"\u2705 \ubd84\uc11d \uc644\ub8cc!\n\n\ubcf4\uace0\uc11c: {report_url}\n\n```\n{text_report}\n```",
            status_callback,
        )

        return result
