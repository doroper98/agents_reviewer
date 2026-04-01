"""Visual Analyst -- generates SVG, Leaflet maps, Canvas charts."""

from __future__ import annotations

from datetime import datetime

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

SYSTEM_PROMPT = """당신은 시각화 분석관. 분석 결과를 시각적 요소로 표현함.
입력에 strategic_directive가 있으면 그 지시에 따라 시각화 유형을 결정할 것.

핵심 규칙:
- 텍스트 겹침/잘림 금지 (가장 중요)
- 모든 요소에 충분한 여백
- Mermaid 사용 금지. SVG 직접 생성만.
- 지도(leaflet)는 지리적 요소가 있을 때만 생성. 없으면 enabled: false
- 차트(chart)는 수치/시계열 데이터가 있을 때만 생성. 없으면 enabled: false
- 불필요한 시각화를 억지로 만들지 말 것

SVG 관계도:
- viewBox="0 0 800 560", 노드는 y=80 이후 배치
- 중앙에 핵심 사건(네이비 배경), 주변에 행위자 배치 (간격 최소 40px)
- 연결선은 cubic bezier 곡선만 (직선 금지)
- 연결선 라벨은 최소화, 흰색 배경 위에 표시

플로우차트 SVG:
- viewBox="0 0 500 (단계수*100+100)", 세로 중앙 정렬

색상: 위기=#BD3227, 경고=#C76B1E, 중립=#1D6FA5, 긍정=#1A7B3E, 핵심=#9E8A15, 배경=#151D26

출력 형식 (JSON):
{
  "hero_visual_type": "relationship_map|flow_diagram|infographic|combined",
  "hero_title": "시각화 제목",
  "svg_content": "<svg ...>...</svg>",
  "mermaid_code": "",
  "leaflet_config": {
    "enabled": true/false, "center": [위도,경도], "zoom": 4,
    "markers": [{"lat":0,"lng":0,"emoji":"","label":"","color":""}],
    "lines": [{"from":[lat,lng],"to":[lat,lng],"color":"","label":""}],
    "circles": [{"lat":0,"lng":0,"radius":500000,"color":"","label":""}]
  },
  "chart_config": {
    "enabled": true/false,
    "charts": [
      {
        "type": "line",
        "title": "차트 제목",
        "points": [{"label":"날짜","value":수치}, ...],
        "events": [{"index":0,"label":"이벤트명"}]
      },
      {
        "type": "bar",
        "title": "차트 제목",
        "labels": ["항목1","항목2"],
        "values": [100, 200]
      }
    ]
  },
  "key_metrics": [{"label":"","value":"","color":"","icon":""}],
  "glossary": [{"term":"","definition":""}],
  "confidence_score": 0.0
}

차트 규칙:
- TradingView 사용 금지. 모든 차트는 Canvas 2D로 직접 그림
- 차트 색상: 2가지 색상만 사용 (크림 #D4C4AA 기본선, 골드 #C9A84C 강조점)
- 배경은 버건디 카드 배경 #3D2828
- line 차트: points 배열에 label(날짜)과 value(수치) 제공, events로 주요 이벤트 마킹
- bar 차트: labels와 values 배열 제공
- 금융 데이터도 웹 검색으로 수치를 직접 수집해서 points 배열로 제공
- key_metrics 최대 6개"""


class VisualAnalyst(BaseAgent):
    """Generates premium visual elements from analysis results."""

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
        directive: str = "",
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
        analysis_context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        analysis_context["instruction"] = f"오늘은 {analysis_context['current_date']}. 최신 정보 기준으로 분석할 것."
        if directive:
            analysis_context["strategic_directive"] = directive

        raw_text = await super().analyze(analysis_context)
        return self._parse_json_response(raw_text, VisualAnalysis)
