"""Visual Analyst -- generates SVG, Leaflet maps, Canvas charts, Mermaid diagrams."""

from __future__ import annotations

from src.config import Config
from src.models import (
    ContextAnalysis,
    ChainReactionAnalysis,
    DynamicsAnalysis,
    PlayerAnalysis,
    ScenarioAnalysis,
    VisualAnalysis,
)
from .base import BaseAgent

SYSTEM_PROMPT = """당신은 시각화 분석관. 분석 결과의 핵심을 시각적 요소로 표현함.

규칙:
- 주제에 따라 적합한 시각화 유형을 자동 선택
- 지정학/군사 → Leaflet 지도 데이터 + SVG 관계도
- 경제/금융 → Canvas 차트 데이터 + 인포그래픽 HTML
- 기술/산업 → Mermaid 플로우차트 + SVG 구조도
- 복합 주제 → 위 조합

출력 형식 (JSON):
{
  "hero_visual_type": "relationship_map|flow_diagram|infographic|combined",
  "hero_title": "시각화 제목",
  "svg_content": "SVG 코드 (관계도, 구조도 등). 반드시 viewBox 포함, 반응형. 색상은 valentino-boop 팔레트 사용: #BD3227(빨강), #C76B1E(주황), #1D6FA5(파랑), #1A7B3E(초록), #9E8A15(금색), #151D26(네이비). 폰트: Noto Sans KR. 최소 400x300 크기.",
  "mermaid_code": "Mermaid 다이어그램 코드 (flowchart, sequence 등). 없으면 빈 문자열.",
  "leaflet_config": {
    "enabled": true/false,
    "center": [위도, 경도],
    "zoom": 4,
    "markers": [{"lat": 0, "lng": 0, "emoji": "🇺🇸", "label": "미국", "color": "#1D6FA5"}],
    "lines": [{"from": [lat,lng], "to": [lat,lng], "color": "#BD3227", "label": "타격 방향"}],
    "circles": [{"lat": 0, "lng": 0, "radius": 500000, "color": "#BD3227", "label": "영향권"}]
  },
  "chart_config": {
    "enabled": true/false,
    "type": "bar|line|radar|gauge",
    "title": "차트 제목",
    "labels": ["항목1", "항목2"],
    "values": [10, 20],
    "colors": ["#BD3227", "#1D6FA5"]
  },
  "key_metrics": [
    {"label": "지표명", "value": "수치", "color": "#BD3227", "icon": "📊"}
  ],
  "glossary": [{"term": "용어", "definition": "정의"}],
  "confidence_score": 0.0
}

중요:
- SVG는 반드시 유효한 SVG 코드여야 함. viewBox="0 0 800 400" 형태.
- Mermaid는 flowchart TD 또는 graph LR 형태.
- Leaflet config는 지정학 주제에만 enabled:true.
- 모든 시각화는 한국어 라벨 사용.
- 색상은 반드시 valentino-boop 팔레트만 사용.
- key_metrics는 최대 6개, 보고서 상단에 핵심 수치를 보여줌."""


class VisualAnalyst(BaseAgent):
    """Generates visual elements (SVG, Leaflet, Canvas, Mermaid) from analysis results."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="visual_analyst",
            role="시각화 분석관",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(  # type: ignore[override]
        self,
        context: ContextAnalysis | None,
        players: PlayerAnalysis | None,
        dynamics: DynamicsAnalysis | None,
        chain_reaction: ChainReactionAnalysis | None,
        scenarios: ScenarioAnalysis | None,
    ) -> VisualAnalysis:
        """Analyze all results and produce visual specifications."""
        analysis_context: dict = {}
        if context:
            analysis_context["context"] = context.model_dump()
        if players:
            analysis_context["players"] = players.model_dump()
        if dynamics:
            analysis_context["dynamics"] = dynamics.model_dump()
        if chain_reaction:
            analysis_context["chain_reaction"] = chain_reaction.model_dump()
        if scenarios:
            analysis_context["scenarios"] = scenarios.model_dump()

        raw_text = await super().analyze(analysis_context)
        return self._parse_json_response(raw_text, VisualAnalysis)
