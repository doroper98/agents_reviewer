"""Report Synthesizer -- 비주얼 HTML 보고서 생성."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import anthropic
from jinja2 import Environment, FileSystemLoader

from src.config import Config
from src.models import FullAnalysisResult

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


class ReportSynthesizer:
    """Generates HTML reports from analysis results.

    Does NOT extend BaseAgent. Uses Jinja2 for HTML rendering
    and optionally calls Claude for executive summary generation.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    async def _generate_executive_summary(self, result: FullAnalysisResult) -> str:
        """Generate executive summary by calling Claude."""
        summary_prompt = (
            "다음 분석 결과를 바탕으로 3-5문장의 핵심 요약(Executive Summary)을 "
            "한국어로 작성하세요. 사건 개요, 핵심 영향, 투자 시사점, 리스크 수준을 포함하세요.\n\n"
            "분석 결과:\n"
        )
        analyses_data = {
            "event_profile": result.event_profile.model_dump(),
            "macro_analysis": result.macro_analysis.model_dump(),
            "geopolitical_analysis": result.geopolitical_analysis.model_dump(),
            "micro_analysis": result.micro_analysis.model_dump(),
            "investment_analysis": result.investment_analysis.model_dump(),
            "history_ethics_analysis": result.history_ethics_analysis.model_dump(),
            "audit_result": result.audit_result.model_dump(),
        }
        user_message = summary_prompt + json.dumps(
            analyses_data, ensure_ascii=False, indent=2
        )

        try:
            response = await self.client.messages.create(
                model=self.config.model_name,
                max_tokens=1024,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"[report_synthesizer] Summary generation failed: {e}")
            return result.macro_analysis.summary or "Executive summary unavailable."

    async def synthesize(self, result: FullAnalysisResult) -> str:
        """Render the full HTML report and return the HTML string."""
        # Generate executive summary if not already set
        if not result.executive_summary:
            result.executive_summary = await self._generate_executive_summary(result)

        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
        template = env.get_template("report.html")

        html = template.render(
            result=result,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Save HTML to file
        output_dir = self.config.report_output_dir
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"analysis_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"[report_synthesizer] Report saved: {filepath}")
        return filepath
