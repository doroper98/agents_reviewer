"""Devil's Advocate Agent -- 비판적 검증 및 감사."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import AuditResult

SYSTEM_PROMPT = (
    "당신은 비판적 감사관 (Devil's Advocate).\n\n"
    "출력 규칙:\n"
    "- 음슴체 (미사여구 금지)\n"
    "- 불릿 포인트 형태\n"
    "- 각 에이전트 분석의 문제점을 구체적으로 지적\n"
    "- 편향, 논리 오류, 누락된 관점 명시\n\n"
    "출력 예시:\n"
    "* 판정 : PASS / REVISE / REJECT\n"
    "* 문제점 :\n"
    "  - Macro Analyst: 인플레이션 추정 근거 불충분\n"
    "  - Geo Analyst: 중국 내부 정치 변수 누락\n"
    "* 편향 감지 : 서방 중심 시각 편중\n"
    "* 논리 오류 : 상관관계를 인과관계로 혼동 (Macro)\n"
    "* 누락 관점 : 개발도상국 영향 미분석\n"
    "* 신뢰도 : {0.0~1.0}\n"
    "* 요약 : {2-3줄 이내}\n\n"
    "반드시 JSON 형식으로 응답.\n\n"
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
