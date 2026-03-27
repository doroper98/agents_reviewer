"""Orchestrator -- 5-Phase analysis pipeline coordinator."""

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
from src.agents.investment_analyst import InvestmentAnalyst
from src.agents.history_ethics_analyst import HistoryEthicsAnalyst
from src.agents.devils_advocate import DevilsAdvocateAgent
from src.agents.report_synthesizer import ReportSynthesizer

logger = logging.getLogger(__name__)

MAX_REVISION_ROUNDS = 2

StatusCallback = Optional[Callable[[str], Coroutine[Any, Any, None]]]


class Orchestrator:
    """Coordinates the 5-phase analysis pipeline.

    Phase 1: Parse command -> AnalysisRequest
    Phase 2: Event Identifier -> EventProfile
    Phase 3: Parallel analysis (Macro + Geo + Micro + History/Ethics)
    Phase 4: Investment Analyst + Devil's Advocate audit
    Phase 5: Report Synthesizer -> HTML report
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.event_identifier = EventIdentifierAgent(config)
        self.macro_analyst = MacroAnalyst(config)
        self.geopolitical_analyst = GeopoliticalAnalyst(config)
        self.micro_analyst = MicroAnalyst(config)
        self.investment_analyst = InvestmentAnalyst(config)
        self.history_ethics_analyst = HistoryEthicsAnalyst(config)
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
        """Execute the full 5-phase analysis pipeline."""
        start_time = time.time()

        request = AnalysisRequest(
            event_description=event_description,
            chat_id=chat_id,
        )
        result = FullAnalysisResult(request=request)

        # -- Phase 1: Parse command --
        await self._notify(
            "Phase 1/5: Parsing command...", status_callback
        )

        # -- Phase 2: Event Identification --
        await self._notify(
            "Phase 2/5: Identifying event (5W1H)...", status_callback
        )
        result.event_profile = await self.event_identifier.analyze(request)
        await self._notify(
            f"Phase 2 complete -- Confidence: {result.event_profile.confidence_score}",
            status_callback,
        )

        # -- Phase 3: Parallel Analysis (Macro + Geo + Micro + History/Ethics) --
        await self._notify(
            "Phase 3/5: Running parallel analysis (4 agents)...",
            status_callback,
        )
        (
            result.macro_analysis,
            result.geopolitical_analysis,
            result.micro_analysis,
            result.history_ethics_analysis,
        ) = await asyncio.gather(
            self.macro_analyst.analyze(result.event_profile),
            self.geopolitical_analyst.analyze(result.event_profile),
            self.micro_analyst.analyze(result.event_profile),
            self.history_ethics_analyst.analyze(result.event_profile),
        )
        await self._notify(
            "Phase 3 complete -- All parallel analyses received",
            status_callback,
        )

        # -- Phase 4: Investment Analyst + Devil's Advocate --
        await self._notify(
            "Phase 4/5: Investment analysis + Devil's Advocate audit...",
            status_callback,
        )
        result.investment_analysis = await self.investment_analyst.analyze(
            result.event_profile,
            result.macro_analysis,
            result.geopolitical_analysis,
            result.micro_analysis,
        )

        all_analyses = {
            "event_profile": result.event_profile.model_dump(),
            "macro_analysis": result.macro_analysis.model_dump(),
            "geopolitical_analysis": result.geopolitical_analysis.model_dump(),
            "micro_analysis": result.micro_analysis.model_dump(),
            "investment_analysis": result.investment_analysis.model_dump(),
            "history_ethics_analysis": result.history_ethics_analysis.model_dump(),
        }
        result.audit_result = await self.devils_advocate.analyze(all_analyses)
        await self._notify(
            f"Phase 4 complete -- Verdict: {result.audit_result.overall_verdict}",
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
                f"Revision round {revision_round}: Re-running flagged agents...",
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
            if "history_ethics_analyst" in agents_to_revise:
                tasks.append(
                    self.history_ethics_analyst.analyze(result.event_profile)
                )
                task_names.append("history_ethics_analysis")

            if tasks:
                revised_results = await asyncio.gather(*tasks)
                for name, revised in zip(task_names, revised_results):
                    setattr(result, name, revised)

            # Re-run investment analyst if needed
            if "investment_analyst" in agents_to_revise:
                result.investment_analysis = await self.investment_analyst.analyze(
                    result.event_profile,
                    result.macro_analysis,
                    result.geopolitical_analysis,
                    result.micro_analysis,
                )

            # Re-audit
            all_analyses = {
                "event_profile": result.event_profile.model_dump(),
                "macro_analysis": result.macro_analysis.model_dump(),
                "geopolitical_analysis": result.geopolitical_analysis.model_dump(),
                "micro_analysis": result.micro_analysis.model_dump(),
                "investment_analysis": result.investment_analysis.model_dump(),
                "history_ethics_analysis": result.history_ethics_analysis.model_dump(),
            }
            result.audit_result = await self.devils_advocate.analyze(
                all_analyses
            )
            await self._notify(
                f"Revision {revision_round} -- Verdict: {result.audit_result.overall_verdict}",
                status_callback,
            )

        # -- Phase 5: Report Synthesis --
        await self._notify(
            "Phase 5/5: Generating report...", status_callback
        )

        result.total_duration_seconds = time.time() - start_time

        report_path = await self.report_synthesizer.synthesize(result)
        await self._notify(
            f"Analysis complete! Report: {report_path}", status_callback
        )

        return result
