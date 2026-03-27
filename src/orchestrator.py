"""Orchestrator — 5-Phase analysis pipeline coordinator."""

from __future__ import annotations

import asyncio
import json
import logging

from src.models import (
    AnalysisRequest,
    AuditVerdict,
    FullAnalysisResult,
)
from src.agents import (
    EventIdentifierAgent,
    MacroAnalystAgent,
    GeopoliticalAnalystAgent,
    MicroAnalystAgent,
    InvestmentAnalystAgent,
    HistoryEthicsAnalystAgent,
    DevilsAdvocateAgent,
    ReportSynthesizerAgent,
)

logger = logging.getLogger(__name__)

MAX_REVISION_ROUNDS = 2


class Orchestrator:
    """Coordinates the 5-phase analysis pipeline.

    Phase 1: Parse command → determine analysis scope
    Phase 2: Event Identification (sequential)
    Phase 3: Parallel Analysis (5 agents concurrently)
    Phase 4: Audit / Devil's Advocate
    Phase 5: Report Synthesis
    """

    def __init__(self, status_callback=None) -> None:
        self.event_identifier = EventIdentifierAgent()
        self.macro_analyst = MacroAnalystAgent()
        self.geopolitical_analyst = GeopoliticalAnalystAgent()
        self.micro_analyst = MicroAnalystAgent()
        self.investment_analyst = InvestmentAnalystAgent()
        self.history_ethics_analyst = HistoryEthicsAnalystAgent()
        self.devils_advocate = DevilsAdvocateAgent()
        self.report_synthesizer = ReportSynthesizerAgent()
        self._status_callback = status_callback

    async def _notify(self, message: str) -> None:
        """Send status update via callback if available."""
        logger.info(message)
        if self._status_callback:
            await self._status_callback(message)

    async def run(self, request: AnalysisRequest) -> FullAnalysisResult:
        """Execute the full 5-phase analysis pipeline."""
        result = FullAnalysisResult(request=request)
        event_text = request.raw_text

        # ── Phase 1: Command Parsing ──
        await self._notify("Phase 1/5: Parsing command...")
        # (Simple pass-through for now; future: classify event type)

        # ── Phase 2: Event Identification ──
        await self._notify("Phase 2/5: Identifying event (5W1H)...")
        result.event_profile = await self.event_identifier.analyze(event_text)
        event_profile_json = result.event_profile.model_dump_json(indent=2)
        await self._notify(
            f"Phase 2 complete — Confidence: {result.event_profile.confidence.value}"
        )

        # ── Phase 3: Parallel Analysis ──
        await self._notify("Phase 3/5: Running parallel analysis (5 agents)...")
        (
            result.macro,
            result.geopolitical,
            result.micro,
            result.investment,
            result.history_ethics,
        ) = await asyncio.gather(
            self.macro_analyst.analyze(event_text, event_profile_json),
            self.geopolitical_analyst.analyze(event_text, event_profile_json),
            self.micro_analyst.analyze(event_text, event_profile_json),
            self.investment_analyst.analyze(event_text, event_profile_json),
            self.history_ethics_analyst.analyze(event_text, event_profile_json),
        )
        await self._notify("Phase 3 complete — All 5 analyses received")

        # ── Phase 4: Audit ──
        await self._notify("Phase 4/5: Devil's Advocate audit...")
        all_analyses_json = json.dumps(
            {
                "event_profile": result.event_profile.model_dump(),
                "macro": result.macro.model_dump(),
                "geopolitical": result.geopolitical.model_dump(),
                "micro": result.micro.model_dump(),
                "investment": result.investment.model_dump(),
                "history_ethics": result.history_ethics.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )

        result.audit = await self.devils_advocate.audit(event_text, all_analyses_json)
        await self._notify(
            f"Phase 4 complete — Verdict: {result.audit.verdict.value}"
        )

        # Handle REVISE verdict (up to MAX_REVISION_ROUNDS)
        revision_round = 0
        while (
            result.audit.verdict == AuditVerdict.REVISE
            and revision_round < MAX_REVISION_ROUNDS
        ):
            revision_round += 1
            await self._notify(
                f"Revision round {revision_round}: Re-running flagged analyses..."
            )
            # Re-run all parallel analyses with audit feedback
            feedback = "\n".join(result.audit.revision_requests)
            enriched_text = f"{event_text}\n\n[Audit Feedback]\n{feedback}"

            (
                result.macro,
                result.geopolitical,
                result.micro,
                result.investment,
                result.history_ethics,
            ) = await asyncio.gather(
                self.macro_analyst.analyze(enriched_text, event_profile_json),
                self.geopolitical_analyst.analyze(enriched_text, event_profile_json),
                self.micro_analyst.analyze(enriched_text, event_profile_json),
                self.investment_analyst.analyze(enriched_text, event_profile_json),
                self.history_ethics_analyst.analyze(enriched_text, event_profile_json),
            )

            all_analyses_json = json.dumps(
                {
                    "event_profile": result.event_profile.model_dump(),
                    "macro": result.macro.model_dump(),
                    "geopolitical": result.geopolitical.model_dump(),
                    "micro": result.micro.model_dump(),
                    "investment": result.investment.model_dump(),
                    "history_ethics": result.history_ethics.model_dump(),
                },
                ensure_ascii=False,
                indent=2,
            )
            result.audit = await self.devils_advocate.audit(
                event_text, all_analyses_json
            )
            await self._notify(
                f"Revision {revision_round} audit — Verdict: {result.audit.verdict.value}"
            )

        # ── Phase 5: Report Synthesis ──
        await self._notify("Phase 5/5: Generating report...")
        result.executive_summary = await self.report_synthesizer.generate_summary(
            event_text, all_analyses_json
        )
        result.overall_confidence = result.audit.data_quality_grade

        report_path = await self.report_synthesizer.generate_report(result)
        await self._notify(f"Analysis complete! Report: {report_path}")

        return result, report_path
