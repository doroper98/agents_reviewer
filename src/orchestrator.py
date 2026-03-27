"""Orchestrator -- 4-Phase analysis pipeline coordinator."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

from src.config import Config
from src.models import AnalysisRequest, FullAnalysisResult
from src.agents.event_identifier import EventIdentifierAgent
from src.agents.macro_analyst import MacroAnalyst
from src.agents.geopolitical_analyst import GeopoliticalAnalyst
from src.agents.micro_analyst import MicroAnalyst
from src.agents.devils_advocate import DevilsAdvocateAgent
from src.agents.report_synthesizer import ReportSynthesizer

logger = logging.getLogger(__name__)

MAX_REVISION_ROUNDS = 2

StatusCallback = Optional[Callable[[str], Coroutine[Any, Any, None]]]


class Orchestrator:
    """Coordinates the 4-phase analysis pipeline.

    Phase 1: Parse command -> AnalysisRequest
    Phase 2: Event Identifier -> EventProfile (5W1H)
    Phase 3: Sequential analysis (Macro -> Geo -> Micro)
    Phase 4: Devil's Advocate audit + Report generation
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.event_identifier = EventIdentifierAgent(config)
        self.macro_analyst = MacroAnalyst(config)
        self.geopolitical_analyst = GeopoliticalAnalyst(config)
        self.micro_analyst = MicroAnalyst(config)
        self.devils_advocate = DevilsAdvocateAgent(config)
        self.report_synthesizer = ReportSynthesizer(config)

    async def _notify(
        self, message: str, status_callback: StatusCallback
    ) -> None:
        """Send status update via callback if available."""
        logger.info(message)
        if status_callback:
            await status_callback(message)

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

        # -- Phase 1: Parse command --
        await self._notify(
            f"\U0001f50d Orchestrator: \ubd84\uc11d \uc2dc\uc791 \u2014 \"{event_description}\"",
            status_callback,
        )

        # -- Phase 2: Event Identification (5W1H) --
        await self._notify(
            "\U0001f4cb Event Identifier: \uc0ac\uac74 \uc2dd\ubcc4 \uc911...",
            status_callback,
        )
        result.event_profile = await self.event_identifier.analyze(request)
        ep = result.event_profile
        await self._notify(
            f"\U0001f4cb Event Identifier:\n"
            f"\u2192 \ubd84\ub958: {ep.category}\n"
            f"\u2192 \uc8fc\uccb4: {ep.who}\n"
            f"\u2192 \uc2e0\ub8b0\ub3c4: {ep.confidence_score}",
            status_callback,
        )

        # -- Phase 3: Sequential Analysis (Macro -> Geo -> Micro) --
        await self._notify(
            "\U0001f4ca Macro Analyst: \uac70\uc2dc\uacbd\uc81c \ubd84\uc11d \uc911...",
            status_callback,
        )
        result.macro_analysis = await self.macro_analyst.analyze(result.event_profile)
        macro_summary = result.macro_analysis.summary[:100] if result.macro_analysis.summary else ""
        await self._notify(
            f"\U0001f4ca Macro Analyst:\n"
            f"\u2192 {macro_summary}\n"
            f"\u2192 \uc2e0\ub8b0\ub3c4: {result.macro_analysis.confidence_score}",
            status_callback,
        )

        await self._notify(
            "\U0001f30d Geopolitical Analyst: \uc9c0\uc815\ud559 \ubd84\uc11d \uc911...",
            status_callback,
        )
        result.geopolitical_analysis = await self.geopolitical_analyst.analyze(result.event_profile)
        geo_summary = result.geopolitical_analysis.summary[:100] if result.geopolitical_analysis.summary else ""
        await self._notify(
            f"\U0001f30d Geopolitical Analyst:\n"
            f"\u2192 {geo_summary}\n"
            f"\u2192 \uc2e0\ub8b0\ub3c4: {result.geopolitical_analysis.confidence_score}",
            status_callback,
        )

        await self._notify(
            "\U0001f3ed Micro Analyst: \ubbf8\uc2dc\uacbd\uc81c \ubd84\uc11d \uc911...",
            status_callback,
        )
        result.micro_analysis = await self.micro_analyst.analyze(result.event_profile)
        micro_summary = result.micro_analysis.summary[:100] if result.micro_analysis.summary else ""
        await self._notify(
            f"\U0001f3ed Micro Analyst:\n"
            f"\u2192 {micro_summary}\n"
            f"\u2192 \uc2e0\ub8b0\ub3c4: {result.micro_analysis.confidence_score}",
            status_callback,
        )

        # -- Phase 4: Devil's Advocate audit + Report generation --
        await self._notify(
            "\U0001f50e Devil's Advocate: \uac10\uc0ac \uc911...",
            status_callback,
        )

        all_analyses = {
            "event_profile": result.event_profile.model_dump(),
            "macro_analysis": result.macro_analysis.model_dump(),
            "geopolitical_analysis": result.geopolitical_analysis.model_dump(),
            "micro_analysis": result.micro_analysis.model_dump(),
        }
        result.audit_result = await self.devils_advocate.analyze(all_analyses)
        audit_summary = result.audit_result.summary[:100] if result.audit_result.summary else ""
        await self._notify(
            f"\U0001f50e Devil's Advocate:\n"
            f"\u2192 \ud310\uc815: {result.audit_result.overall_verdict} "
            f"(\uc2e0\ub8b0\ub3c4: {result.audit_result.credibility_score})\n"
            f"\u2192 {audit_summary}",
            status_callback,
        )

        # Handle REVISE verdict
        revision_round = 0
        while (
            result.audit_result.overall_verdict == "REVISE"
            and revision_round < MAX_REVISION_ROUNDS
        ):
            revision_round += 1
            await self._notify(
                f"\U0001f504 Revision round {revision_round}: Re-running flagged agents...",
                status_callback,
            )
            agents_to_revise = result.audit_result.agents_to_revise

            tasks = []
            task_names: list[str] = []

            if "macro_analyst" in agents_to_revise:
                tasks.append(self.macro_analyst.analyze(result.event_profile))
                task_names.append("macro_analysis")
            if "geopolitical_analyst" in agents_to_revise:
                tasks.append(
                    self.geopolitical_analyst.analyze(result.event_profile)
                )
                task_names.append("geopolitical_analysis")
            if "micro_analyst" in agents_to_revise:
                tasks.append(self.micro_analyst.analyze(result.event_profile))
                task_names.append("micro_analysis")

            if tasks:
                revised_results = await asyncio.gather(*tasks)
                for name, revised in zip(task_names, revised_results):
                    setattr(result, name, revised)

            # Re-audit
            all_analyses = {
                "event_profile": result.event_profile.model_dump(),
                "macro_analysis": result.macro_analysis.model_dump(),
                "geopolitical_analysis": result.geopolitical_analysis.model_dump(),
                "micro_analysis": result.micro_analysis.model_dump(),
            }
            result.audit_result = await self.devils_advocate.analyze(
                all_analyses
            )
            await self._notify(
                f"\U0001f504 Revision {revision_round} \u2014 \ud310\uc815: "
                f"{result.audit_result.overall_verdict}",
                status_callback,
            )

        # Report generation
        await self._notify(
            "\U0001f4dd Report Synthesizer: \ubcf4\uace0\uc11c \uc0dd\uc131 \uc911...",
            status_callback,
        )

        result.total_duration_seconds = time.time() - start_time

        report_path = await self.report_synthesizer.synthesize(result)
        await self._notify(
            f"\u2705 \uc644\ub8cc! \ubcf4\uace0\uc11c: {report_path}",
            status_callback,
        )

        return result
