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

SYSTEM_PROMPT = """당신은 시각화 분석관. 분석 결과를 SVG, 지도, 차트로 시각화함.

핵심 규칙:
- 텍스트 겹침/잘림 금지 (가장 중요)
- 모든 요소에 충분한 여백
- Mermaid 사용 금지. SVG 직접 생성만.

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
    "enabled": true/false, "type": "tradingview|bar|line|radar", "title": "",
    "tradingview_symbols": [{"symbol":"","label":"","interval":"D"}],
    "labels": [], "values": [], "colors": []
  },
  "key_metrics": [{"label":"","value":"","color":"","icon":""}],
  "glossary": [{"term":"","definition":""}],
  "confidence_score": 0.0
}

차트 규칙:
- 금융 데이터(주식/원자재/환율/지수)는 TradingView 사용
- 비금융/커스텀 데이터는 Canvas 사용
- TradingView 심볼: 원유=NYMEX:BZ1!/CL1!, 환율=FX:USDKRW/USDJPY, 지수=KRX:KOSPI/SP:SPX, 금=COMEX:GC1!, 금리=TVC:US10Y, VIX=CBOE:VIX, BTC=BINANCE:BTCUSDT
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

        raw_text = await super().analyze(analysis_context)
        return self._parse_json_response(raw_text, VisualAnalysis)
