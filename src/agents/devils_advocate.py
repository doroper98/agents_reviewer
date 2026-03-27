"""Devil's Advocate Agent -- 비판적 검증 및 감사."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import AuditResult

SYSTEM_PROMPT = (
    "당신은 비판적 감사관(Devil's Advocate)입니다. "
    "다른 에이전트들의 분석 결과를 검증하고 비판적으로 평가합니다. "
    "편향성, 논리적 오류, 누락된 관점, 과도한 확신을 찾아냅니다. "
    "PASS/REVISE/REJECT 판정을 내리며, "
    "REVISE의 경우 어떤 에이전트가 재분석해야 하는지 명시합니다.\n\n"
    "## Output Schema\n"
    "Respond ONLY with valid JSON matching this schema:\n"
    "```json\n"
    "{\n"
    '  "overall_verdict": "PASS|REVISE|REJECT",\n'
    '  "issues_found": [{"agent": "string", "issue": "string", "severity": "string"}],\n'
    '  "agents_to_revise": ["string"],\n'
    '  "credibility_score": 0.0-1.0,\n'
    '  "bias_detected": ["string"],\n'
    '  "logical_fallacies": ["string"],\n'
    '  "missing_perspectives": ["string"],\n'
    '  "summary": "string"\n'
    "}\n"
    "```"
)


class DevilsAdvocateAgent(BaseAgent):
    """Critically audits all other agents' analyses."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="devils_advocate",
            role="Devil's Advocate (비판적 검증자)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(self, all_analyses: dict) -> AuditResult:
        """Audit all analyses and return verdict."""
        raw_text = await super().analyze(all_analyses)
        return self._parse_json_response(raw_text, AuditResult)
