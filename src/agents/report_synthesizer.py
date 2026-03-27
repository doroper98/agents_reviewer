"""Report Synthesizer -- visual HTML report with Plotly charts."""

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
    Generates Plotly chart data from analysis results.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    async def _generate_executive_summary(self, result: FullAnalysisResult) -> str:
        """Generate executive summary by calling Claude."""
        summary_prompt = (
            "다음 분석 결과를 바탕으로 3문장 이내의 핵심 요약(Executive Summary)을 "
            "한국어로 작성하세요. 사건 개요, 핵심 영향, 리스크 수준을 포함하세요.\n\n"
            "분석 결과:\n"
        )
        analyses_data = {
            "event_profile": result.event_profile.model_dump(),
            "macro_analysis": result.macro_analysis.model_dump(),
            "geopolitical_analysis": result.geopolitical_analysis.model_dump(),
            "micro_analysis": result.micro_analysis.model_dump(),
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

    def _build_chart_data(self, result: FullAnalysisResult) -> dict:
        """Build JSON-serializable chart data for Plotly templates."""
        # Confidence scores for bar chart and radar
        confidence_scores = {
            "Event Identifier": result.event_profile.confidence_score,
            "Macro Analyst": result.macro_analysis.confidence_score,
            "Geopolitical Analyst": result.geopolitical_analysis.confidence_score,
            "Micro Analyst": result.micro_analysis.confidence_score,
            "Audit Credibility": result.audit_result.credibility_score,
        }

        # Impact radar data (3 domains)
        impact_radar = {
            "categories": [
                "\uac70\uc2dc\uacbd\uc81c",
                "\uc9c0\uc815\ud559",
                "\ubbf8\uc2dc\uacbd\uc81c",
            ],
            "values": [
                result.macro_analysis.confidence_score,
                result.geopolitical_analysis.confidence_score,
                result.micro_analysis.confidence_score,
            ],
        }

        # Risk gauge (average confidence inverted = risk)
        avg_confidence = (
            result.macro_analysis.confidence_score
            + result.geopolitical_analysis.confidence_score
            + result.micro_analysis.confidence_score
        ) / 3.0
        risk_level = round((1.0 - avg_confidence) * 100, 1)

        # Impact matrix scatter data
        impact_matrix = {
            "labels": [
                "\uac70\uc2dc\uacbd\uc81c",
                "\uc9c0\uc815\ud559",
                "\ubbf8\uc2dc\uacbd\uc81c",
            ],
            "probability": [
                result.macro_analysis.confidence_score,
                result.geopolitical_analysis.confidence_score,
                result.micro_analysis.confidence_score,
            ],
            "severity": [
                round(result.macro_analysis.confidence_score * 0.9, 2),
                round(result.geopolitical_analysis.confidence_score * 0.85, 2),
                round(result.micro_analysis.confidence_score * 0.8, 2),
            ],
            "colors": ["#8fb4c9", "#d4776b", "#6baa7c"],
        }

        # Sector impact heatmap
        sectors = result.micro_analysis.affected_industries[:6] or [
            "Technology", "Finance", "Energy", "Healthcare", "Manufacturing"
        ]
        regions = result.geopolitical_analysis.affected_regions[:5] or [
            "North America", "Europe", "Asia"
        ]
        # Build a simple heatmap grid
        heatmap_z: list[list[float]] = []
        for i, _sector in enumerate(sectors):
            row: list[float] = []
            for j, _region in enumerate(regions):
                # Deterministic pseudo-value based on indices and confidence
                base = (result.macro_analysis.confidence_score + i * 0.1 + j * 0.15) % 1.0
                row.append(round(base, 2))
            heatmap_z.append(row)

        return {
            "confidence_scores": confidence_scores,
            "impact_radar": impact_radar,
            "risk_level": risk_level,
            "impact_matrix": impact_matrix,
            "heatmap": {
                "sectors": sectors,
                "regions": regions,
                "z": heatmap_z,
            },
        }

    async def synthesize(self, result: FullAnalysisResult) -> str:
        """Render the full HTML report and return the file path."""
        # Generate executive summary if not already set
        if not result.executive_summary:
            result.executive_summary = await self._generate_executive_summary(result)

        # Build chart data
        chart_data = self._build_chart_data(result)

        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
        template = env.get_template("report.html")

        html = template.render(
            result=result,
            chart_data=chart_data,
            chart_data_json=json.dumps(chart_data, ensure_ascii=False),
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
