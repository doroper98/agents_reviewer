"""Report Synthesizer -- HTML report generation with Canvas 2D charts."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone, timedelta

from jinja2 import Environment, FileSystemLoader

from src.config import Config
from src.models import FullAnalysisResult, NarrativePlan, NarrativeSection

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
CSS_PATH = os.path.join(TEMPLATE_DIR, "report.css")
KST = timezone(timedelta(hours=9))


class ReportSynthesizer:
    """Generates HTML reports from analysis results.

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

    async def _generate_executive_summary(
        self, result: FullAnalysisResult
    ) -> tuple[str, list[str]]:
        """Generate governance text + key summary items via Claude CLI or API.

        Returns:
            (governance_text, key_summary_items) tuple.
        """
        summary_prompt = (
            "다음 분석 결과를 바탕으로 두 가지를 작성.\n\n"
            "=== 1. 거버넌스 메시지 ===\n"
            "- 보고서 상단에 들어갈 사건 개요 한 문장\n"
            "- 음슴체 사용, 반드시 완결된 문장으로 끝낼 것 (중간에 끊기면 안 됨)\n"
            "- 사건의 핵심 팩트와 수치를 포함\n"
            "- 200자 내외\n\n"
            "=== 2. 핵심 요약 ===\n"
            "- 보고서 전체 내용을 번호로 요약\n"
            "- 각 항목은 한 문장, 음슴체\n"
            "- 3~5개 항목\n\n"
            "출력 형식 (반드시 이 형식 준수):\n"
            "[GOVERNANCE]\n"
            "사건 요약 문장\n\n"
            "[KEY_SUMMARY]\n"
            "1) 첫 번째 핵심\n"
            "2) 두 번째 핵심\n"
            "3) 세 번째 핵심\n\n"
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
            raw = await self._call_cli(user_message)
        else:
            raw = await self._call_api(user_message)

        return self._parse_summary(raw)

    @staticmethod
    def _parse_summary(raw: str) -> tuple[str, list[str]]:
        """Parse raw text into (governance, key_summary_items)."""
        governance = ""
        key_items: list[str] = []
        if "[GOVERNANCE]" in raw and "[KEY_SUMMARY]" in raw:
            parts = raw.split("[KEY_SUMMARY]")
            governance = parts[0].replace("[GOVERNANCE]", "").strip()
            for line in parts[1].strip().split("\n"):
                line = line.strip()
                if line and re.match(r"^\d+\)", line):
                    # Strip the "N) " prefix — template adds its own numbering
                    key_items.append(re.sub(r"^\d+\)\s*", "", line))
        else:
            # Fallback: use entire text as governance
            governance = raw.strip()
        return governance, key_items

    @staticmethod
    def _format_structured_text(text: str) -> str:
        """Convert numbered patterns (첫째/둘째/N층 etc.) into <br> separated lines."""
        # N층: patterns
        text = re.sub(r"(?<=[.。])\s*(\d+층\s*[:：])", r"<br><br><strong>\1</strong>", text)
        # 첫째/둘째/셋째/넷째/다섯째 patterns
        text = re.sub(
            r"(?<=[.。,])\s*(첫째|둘째|셋째|넷째|다섯째|여섯째)\s*[,，]",
            r"<br><br><strong>\1,</strong>",
            text,
        )
        # ①②③ patterns
        text = re.sub(r"(?<=[.。])\s*([①②③④⑤⑥])", r"<br><br>\1", text)
        return text

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
            "--model", self.config.model_name_light,
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
                model=self.config.model_name_light,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text  # type: ignore[index]
        except Exception as e:
            logger.error(f"[report_synthesizer] Summary generation failed: {e}")
            return "Executive summary unavailable."

    # ------------------------------------------------------------------
    # Narrative Plan generation
    # ------------------------------------------------------------------

    _DATA_SOURCE_CHECKS: dict[str, str] = {
        "context": "context",
        "players": "players",
        "dynamics": "dynamics",
        "chain_reaction": "chain_reaction",
        "scenarios": "scenarios",
        "watch_signals": "scenarios",
    }

    def _has_data(self, result: FullAnalysisResult, source: str) -> bool:
        """Check if a data_source has meaningful data."""
        field = self._DATA_SOURCE_CHECKS.get(source)
        if not field:
            return False
        obj = getattr(result, field, None)
        if obj is None:
            return False
        if source == "players":
            return bool(obj.players)
        if source == "chain_reaction":
            return bool(obj.chain)
        if source == "scenarios":
            return bool(obj.scenarios)
        if source == "watch_signals":
            return bool(getattr(obj, "watch_signals", None))
        return True

    def _get_available_sources(self, result: FullAnalysisResult) -> list[str]:
        """Return list of data_sources that have actual data."""
        return [s for s in self._DATA_SOURCE_CHECKS if self._has_data(result, s)]

    @staticmethod
    def _default_narrative_plan(result: FullAnalysisResult) -> NarrativePlan:
        """Fallback: traditional 6-act structure."""
        defaults = [
            ("context", "PART I", "상황인식"),
            ("players", "PART II", "이해관계자"),
            ("dynamics", "PART III", "구조 및 상호작용"),
            ("chain_reaction", "PART IV", "연쇄반응"),
            ("scenarios", "PART V", "향후 시나리오"),
            ("watch_signals", "PART VI", "시그널"),
        ]
        sections: list[NarrativeSection] = []
        for i, (src, act, title) in enumerate(defaults):
            field = "scenarios" if src == "watch_signals" else src
            obj = getattr(result, field, None)
            if obj is None:
                continue
            if src == "players" and not obj.players:
                continue
            if src == "chain_reaction" and not obj.chain:
                continue
            if src == "scenarios" and not obj.scenarios:
                continue
            if src == "watch_signals" and not getattr(obj, "watch_signals", None):
                continue
            sections.append(NarrativeSection(
                section_id=f"s{i + 1}",
                act_label=act,
                title=title,
                data_source=src,
            ))
        return NarrativePlan(sections=sections)

    async def _generate_narrative_plan(
        self, result: FullAnalysisResult
    ) -> NarrativePlan:
        """Ask Claude for the optimal section ordering for this event."""
        available = self._get_available_sources(result)
        if not available:
            return self._default_narrative_plan(result)

        # Build condensed summaries for the prompt
        summaries: dict[str, str] = {}
        if result.context:
            summaries["context"] = (
                f"사건: {result.context.event_name}. "
                f"요약: {result.context.summary[:200]}"
            )
        if result.players and result.players.players:
            names = [p.get("name", "") for p in result.players.players[:6]]
            summaries["players"] = f"주요 행위자: {', '.join(names)}"
        if result.dynamics:
            summaries["dynamics"] = (
                f"프레임워크: {result.dynamics.framework}. "
                f"{result.dynamics.summary[:150]}"
            )
        if result.chain_reaction and result.chain_reaction.chain:
            titles = [s.get("title", "") for s in result.chain_reaction.chain[:5]]
            summaries["chain_reaction"] = f"연쇄단계: {' → '.join(titles)}"
        if result.scenarios and result.scenarios.scenarios:
            names = [s.get("name", "") for s in result.scenarios.scenarios[:4]]
            summaries["scenarios"] = f"시나리오: {', '.join(names)}"
        if result.scenarios and result.scenarios.watch_signals:
            sigs = [s.get("signal", "") for s in result.scenarios.watch_signals[:4]]
            summaries["watch_signals"] = f"감시 시그널: {', '.join(sigs)}"

        prompt = (
            "당신은 사건 분석 보고서의 내러티브 구조를 설계하는 편집장.\n\n"
            "아래 분석 결과를 검토하고, 이 사건에 가장 적합한 보고서 섹션 순서를 결정.\n\n"
            "사용 가능한 데이터 소스:\n"
        )
        for src in available:
            desc = summaries.get(src, src)
            prompt += f"- {src}: {desc}\n"

        prompt += (
            "\n규칙:\n"
            "1. 4~7개 섹션, 각 data_source 최대 1회 사용\n"
            "2. 사건 성격에 맞게 순서와 제목 자유 결정\n"
            "3. act_label은 영어 (예: PART I — THE TRIGGER), title은 한국어\n"
            "4. narrative_bridge: 이전 섹션→이 섹션 전환 1문장, 한국어, 음슴체\n"
            "5. 첫 섹션의 narrative_bridge는 빈 문자열\n\n"
            "반드시 아래 JSON만 출력 (다른 텍스트 없이):\n"
            '{"report_theme":"핵심 서사 한 문장","sections":['
            '{"section_id":"s1","act_label":"PART I — ...","title":"...",'
            '"data_source":"context","narrative_bridge":"","subsections":[]},'
            "...]}\n"
        )

        try:
            if self.config.use_cli_mode:
                raw = await self._call_cli(prompt)
            else:
                raw = await self._call_api(prompt)

            # Extract JSON from response
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                logger.warning("[report_synthesizer] No JSON in narrative plan response")
                return self._default_narrative_plan(result)

            plan = NarrativePlan.model_validate_json(match.group())

            # Validate: filter invalid/duplicate sources
            seen: set[str] = set()
            valid: list[NarrativeSection] = []
            for i, sec in enumerate(plan.sections):
                if sec.data_source not in available or sec.data_source in seen:
                    continue
                seen.add(sec.data_source)
                sec.section_id = f"s{i + 1}"
                valid.append(sec)

            plan.sections = valid
            if not plan.sections:
                return self._default_narrative_plan(result)

            logger.info(
                f"[report_synthesizer] Narrative plan: "
                f"{[s.data_source for s in plan.sections]}"
            )
            return plan

        except Exception as e:
            logger.warning(f"[report_synthesizer] Narrative plan failed: {e}")
            return self._default_narrative_plan(result)

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

            # Deploy the entire reports directory (includes index.html)
            deploy_dir = os.path.dirname(filepath)

            cmd = wrangler_cmd + [
                "pages", "deploy", deploy_dir,
                "--project-name", project_name,
                "--branch", "main",
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

            # Always use production URL (not deployment-specific snapshot URL)
            # Deployment URLs (e.g. abc123.project.pages.dev) are frozen snapshots
            # Production URL (project.pages.dev) always reflects the latest deployment
            filename = os.path.basename(filepath)
            production_url = f"https://{project_name}.pages.dev/{filename}"
            logger.info(f"[report_synthesizer] Uploaded to Cloudflare: {production_url}")
            return production_url

        except Exception as e:
            logger.error(f"[report_synthesizer] Cloudflare upload exception: {e}")
            return ""

    async def synthesize(self, result: FullAnalysisResult) -> str:
        """Render HTML report, upload to Cloudflare, return URL or filepath."""
        # Generate executive summary + narrative plan in parallel
        key_summary_items: list[str] = []
        narrative_plan: NarrativePlan | None = None

        async def _gen_summary() -> tuple[str, list[str]]:
            if result.executive_summary:
                return result.executive_summary, []
            return await self._generate_executive_summary(result)

        async def _gen_plan() -> NarrativePlan:
            return await self._generate_narrative_plan(result)

        (governance, key_items), plan = await asyncio.gather(
            _gen_summary(), _gen_plan()
        )
        if not result.executive_summary:
            result.executive_summary = governance
            key_summary_items = key_items
        narrative_plan = plan

        # Build chart data & confidence text
        chart_data = self._build_chart_data(result)
        confidence_parts: list[str] = []
        for label, val in zip(chart_data["labels"], chart_data["values"]):
            confidence_parts.append(f"{label} {val*100:.0f}%")
        confidence_text = "Confidence: " + " · ".join(confidence_parts) if confidence_parts else ""

        # Load CSS content to inline into HTML
        css_content = ""
        if os.path.exists(CSS_PATH):
            with open(CSS_PATH, "r", encoding="utf-8") as f:
                css_content = f.read()

        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
        env.filters["structured"] = self._format_structured_text
        template = env.get_template("report.html")

        html = template.render(
            result=result,
            css_content=css_content,
            chart_data_json=json.dumps(chart_data, ensure_ascii=False),
            generated_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            key_summary_items=key_summary_items,
            confidence_text=confidence_text,
            sections=narrative_plan.sections,
            report_theme=narrative_plan.report_theme,
        )

        # Save HTML to file
        output_dir = self.config.report_output_dir
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        filename = f"analysis_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"[report_synthesizer] Report saved: {filepath}")
        result.report_path = filepath

        # Generate index.html (report listing page)
        self._generate_index(output_dir)

        # Upload entire reports directory to Cloudflare Pages
        report_url = await self._upload_to_cloudflare(filepath)
        if report_url:
            result.report_url = report_url
            return report_url

        return filepath

    def _generate_index(self, output_dir: str) -> None:
        """Generate index.html listing all reports."""
        import glob
        reports = sorted(glob.glob(os.path.join(output_dir, "analysis_*.html")), reverse=True)

        rows = []
        for rpath in reports[:50]:
            fname = os.path.basename(rpath)
            # Extract date from filename: analysis_20260328_041426.html
            parts = fname.replace("analysis_", "").replace(".html", "").split("_")
            if len(parts) >= 2:
                date_str = parts[0]
                time_str = parts[1]
                display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
            else:
                display_date = fname

            # Try to extract title from HTML
            title = fname
            try:
                with open(rpath, "r", encoding="utf-8") as f:
                    content = f.read(3000)
                    if "<title>" in content and "</title>" in content:
                        title = content.split("<title>")[1].split("</title>")[0].strip()
                        if not title or title == "Analysis":
                            title = fname
            except Exception:
                pass

            rows.append(f'<tr><td style="padding:10px 12px;border-bottom:1px solid #3D2828">'
                        f'<a href="{fname}" style="color:#C9A84C;text-decoration:none;font-weight:600">{title}</a>'
                        f'</td><td style="padding:10px 12px;border-bottom:1px solid #3D2828;color:#A89880;'
                        f'font-size:12px">{display_date}</td></tr>')

        index_html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Analysis Reports</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&family=Noto+Serif+KR:wght@700;900&display=swap" rel="stylesheet">
<style>
body{{font-family:'Noto Sans KR',sans-serif;background:#2B1A1A;color:#D4C4AA;margin:0;padding:0}}
.wrap{{max-width:800px;margin:0 auto;padding:20px 14px}}
h1{{font-family:'Noto Serif KR',serif;font-size:20px;font-weight:900;margin-bottom:4px;color:#F0E2CC}}
.sub{{font-size:12px;color:#A89880;margin-bottom:20px}}
table{{width:100%;border-collapse:collapse;background:#3D2828;border:1px solid #5A4A3A;border-radius:8px;overflow:hidden}}
th{{background:#2B1A1A;color:#A89880;padding:10px 12px;text-align:left;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px}}
tr:hover{{background:#4A3232}}
</style>
</head>
<body>
<div class="wrap">
<h1>Analysis Reports</h1>
<div class="sub">총 {len(reports)}건의 보고서</div>
<table>
<thead><tr><th>보고서</th><th style="width:160px">생성일시</th></tr></thead>
<tbody>
{"".join(rows) if rows else '<tr><td colspan="2" style="padding:20px;text-align:center;color:#7A6E5E">보고서가 없습니다</td></tr>'}
</tbody>
</table>
</div>
</body>
</html>'''

        index_path = os.path.join(output_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_html)
        logger.info(f"[report_synthesizer] Index page updated: {index_path}")
