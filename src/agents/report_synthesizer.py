"""Report Synthesizer -- valentino-boop style HTML report with Canvas 2D charts."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

from src.config import Config
from src.models import FullAnalysisResult

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


class ReportSynthesizer:
    """Generates valentino-boop style HTML reports from analysis results.

    Does NOT extend BaseAgent. Uses Jinja2 for HTML rendering,
    calls Claude CLI for executive summary generation,
    builds Canvas 2D chart data, and uploads to Cloudflare Pages.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._api_client: object | None = None

        if not config.use_cli_mode:
            import anthropic
            self._api_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    async def _generate_executive_summary(self, result: FullAnalysisResult) -> str:
        """Generate executive summary via Claude CLI or API."""
        summary_prompt = (
            "다음 분석 결과를 바탕으로 핵심 요약(Executive Summary)을 작성.\n\n"
            "출력 규칙:\n"
            "- 음슴체 사용 (미사여구 금지, 짧고 직관적인 문장만)\n"
            "- 불릿 포인트(*) 형태로 핵심 사실만 나열\n"
            "- 줄글 금지, 문장형 서술 금지\n"
            "- 3줄 이내\n\n"
            "출력 형식:\n"
            "* 사건 개요 : {핵심 내용}\n"
            "* 핵심 영향 : {주요 파급효과}\n"
            "* 리스크 수준 : {상/중/하 + 근거}\n\n"
            "분석 결과:\n"
        )

        analyses_data: dict = {}
        if result.context:
            analyses_data["context"] = result.context.model_dump()
        if result.players:
            analyses_data["players"] = result.players.model_dump()
        if result.dynamics:
            analyses_data["dynamics"] = result.dynamics.model_dump()
        if result.chain_reaction:
            analyses_data["chain_reaction"] = result.chain_reaction.model_dump()
        if result.scenarios:
            analyses_data["scenarios"] = result.scenarios.model_dump()

        user_message = summary_prompt + json.dumps(
            analyses_data, ensure_ascii=False, indent=2
        )

        if self.config.use_cli_mode:
            return await self._call_cli(user_message)
        return await self._call_api(user_message)

    async def _call_cli(self, prompt: str) -> str:
        """Call Claude CLI for text generation."""
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError(
                "claude CLI not found on PATH. "
                "Install it with: npm install -g @anthropic-ai/claude-code && claude login"
            )

        cmd = [
            claude_bin,
            "-p", prompt,
            "--output-format", "text",
            "--model", self.config.model_name,
            "--dangerously-skip-permissions",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "unknown error"
            raise RuntimeError(f"[report_synthesizer] CLI failed: {err_msg}")

        return stdout.decode().strip()

    async def _call_api(self, prompt: str) -> str:
        """Call Anthropic API for text generation."""
        assert self._api_client is not None, "API client not initialised"
        try:
            response = await self._api_client.messages.create(  # type: ignore[union-attr]
                model=self.config.model_name,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text  # type: ignore[index]
        except Exception as e:
            logger.error(f"[report_synthesizer] Summary generation failed: {e}")
            return "Executive summary unavailable."

    def _build_chart_data(self, result: FullAnalysisResult) -> dict:
        """Build JSON-serializable chart data for Canvas 2D radar chart."""
        confidence_scores: dict[str, float] = {}
        if result.context:
            confidence_scores["Context"] = result.context.confidence_score
        if result.players:
            confidence_scores["Players"] = result.players.confidence_score
        if result.dynamics:
            confidence_scores["Dynamics"] = result.dynamics.confidence_score
        if result.chain_reaction:
            confidence_scores["Chain Reaction"] = result.chain_reaction.confidence_score
        if result.scenarios:
            confidence_scores["Scenarios"] = result.scenarios.confidence_score

        return {
            "labels": list(confidence_scores.keys()),
            "values": list(confidence_scores.values()),
        }

    async def _upload_to_cloudflare(self, filepath: str) -> str:
        """Upload HTML report to Cloudflare Pages using wrangler CLI."""
        account_id = self.config.cloudflare_account_id
        api_token = self.config.cloudflare_api_token
        project_name = self.config.cloudflare_project_name

        if not account_id or not api_token:
            logger.warning("[report_synthesizer] Cloudflare credentials not set, skipping upload")
            return ""

        try:
            wrangler_bin = shutil.which("wrangler")
            if wrangler_bin is None:
                npx_bin = shutil.which("npx")
                if npx_bin is None:
                    logger.warning("[report_synthesizer] wrangler/npx not found, skipping upload")
                    return ""
                wrangler_cmd = [npx_bin, "wrangler"]
            else:
                wrangler_cmd = [wrangler_bin]

            # Create a temp directory with the report file
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_file = os.path.join(tmpdir, os.path.basename(filepath))
                shutil.copy2(filepath, tmp_file)

                cmd = wrangler_cmd + [
                    "pages", "deploy", tmpdir,
                    "--project-name", project_name,
                    "--commit-dirty=true",
                ]

                env = os.environ.copy()
                env["CLOUDFLARE_ACCOUNT_ID"] = account_id
                env["CLOUDFLARE_API_TOKEN"] = api_token

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, stderr = await proc.communicate()

                output = stdout.decode() + stderr.decode()

                if proc.returncode != 0:
                    logger.error(f"[report_synthesizer] Cloudflare upload failed: {output}")
                    return ""

                # Extract URL from wrangler output
                filename = os.path.basename(filepath)
                for line in output.split("\n"):
                    line = line.strip()
                    if "https://" in line and ".pages.dev" in line:
                        base_url = "https://" + line.split("https://")[1].split()[0]
                        base_url = base_url.rstrip("/")
                        full_url = f"{base_url}/{filename}"
                        logger.info(f"[report_synthesizer] Uploaded to Cloudflare: {full_url}")
                        return full_url

                # Fallback: construct URL
                filename = os.path.basename(filepath)
                fallback_url = f"https://{project_name}.pages.dev/{filename}"
                logger.info(f"[report_synthesizer] Using fallback URL: {fallback_url}")
                return fallback_url

        except Exception as e:
            logger.error(f"[report_synthesizer] Cloudflare upload exception: {e}")
            return ""

    async def synthesize(self, result: FullAnalysisResult) -> str:
        """Render HTML report, upload to Cloudflare, return URL or filepath."""
        # Generate executive summary
        if not result.executive_summary:
            result.executive_summary = await self._generate_executive_summary(result)

        # Build chart data
        chart_data = self._build_chart_data(result)

        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
        template = env.get_template("report.html")

        html = template.render(
            result=result,
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
        result.report_path = filepath

        # Upload to Cloudflare Pages
        report_url = await self._upload_to_cloudflare(filepath)
        if report_url:
            result.report_url = report_url
            return report_url

        return filepath
