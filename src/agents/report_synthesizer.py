"""Report Synthesizer Agent — 비주얼 HTML 보고서 생성."""

from __future__ import annotations

import os
import logging
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

from src.agents.base import BaseAgent
from src.config import REPORT_OUTPUT_DIR
from src.models import FullAnalysisResult

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


class ReportSynthesizerAgent(BaseAgent):
    name = "report_synthesizer"
    role = "Report Synthesizer (보고서 합성자)"
    system_prompt = """You are the Report Synthesizer agent. Your role is to create
a concise executive summary that captures the key findings from all analyses.

Produce a JSON object with a single "executive_summary" field containing a 3-5 sentence
summary in Korean that covers:
1. What happened (사건 요약)
2. The most critical impact area
3. The key investment implication
4. The historical pattern insight
5. The overall confidence/risk assessment

Output ONLY valid JSON: {"executive_summary": "string"}"""

    async def generate_summary(self, event_text: str, all_analyses: str) -> str:
        """Generate executive summary via Claude."""
        message = self.build_context_message(
            event_text, AllAnalyses=all_analyses
        )
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=self.system_prompt,
            messages=[{"role": "user", "content": message}],
        )
        raw = response.content[0].text
        try:
            import json
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            data = json.loads(raw)
            return data.get("executive_summary", raw[:500])
        except Exception:
            return raw[:500]

    async def generate_report(self, result: FullAnalysisResult) -> str:
        """Render the full HTML report from analysis results."""
        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)

        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
        template = env.get_template("report.html")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"analysis_{timestamp}.html"
        filepath = os.path.join(REPORT_OUTPUT_DIR, filename)

        html = template.render(
            result=result,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            impact_levels={
                "macro": result.macro.impact_level,
                "geopolitical": result.geopolitical.impact_level,
                "micro": result.micro.impact_level,
                "investment": result.investment.impact_level,
            },
        )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"[report_synthesizer] Report saved: {filepath}")
        return filepath
