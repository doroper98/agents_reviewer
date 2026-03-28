"""Visual Analyst -- generates premium SVG, Leaflet maps, Canvas charts."""

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

SYSTEM_PROMPT = """당신은 최고 수준의 시각화 분석관. McKinsey, BCG 수준의 프리미엄 인포그래픽을 생성함.

절대 규칙:
- 파워포인트 수준의 저급한 시각화 금지
- 텍스트가 겹치거나 잘리면 안 됨
- 모든 요소에 충분한 여백(padding/margin) 확보
- 색상은 반드시 아래 팔레트만 사용

색상 팔레트:
- 위기/부정: #BD3227 (빨강)
- 경고/주의: #C76B1E (주황)
- 정보/중립: #1D6FA5 (파랑)
- 긍정/안전: #1A7B3E (초록)
- 중요/핵심: #9E8A15 (금색)
- 배경/기본: #151D26 (네이비)
- 보조배경: #F5F0E8 (밝은베이지)
- 텍스트: #2C2C2C (진회색)
- 보조텍스트: #6B6B6B (회색)
- 테두리: #E4E0D8

SVG 생성 규칙:
- viewBox="0 0 800 500" (최소 크기)
- 폰트: font-family="Noto Sans KR, sans-serif"
- 노드 간 최소 간격 60px
- 텍스트는 노드 안에 중앙 정렬, 노드 밖으로 절대 넘치지 않게
- 노드 padding 최소 16px
- 라벨 폰트 크기: 제목 14px bold, 본문 11px, 보조 9px
- 화살표는 marker-end로 깔끔한 삼각형 사용
- 그림자 효과: filter="drop-shadow(0 2px 4px rgba(0,0,0,0.1))"
- 라운드 코너: rx="8"
- 관계도에서 노드는 rounded rect, 연결선은 곡선(cubic bezier) 사용
- 각 노드에 아이콘 이모지 포함
- 범례(legend) 포함

플로우차트 SVG 규칙 (Mermaid 대신 SVG로 직접 생성):
- 세로 방향 (위→아래) 흐름
- 노드: rounded rect, width 최소 220px, height 최소 60px
- 노드 내부: 이모지 + 제목(bold 13px) + 설명(11px) 2줄 구성
- 화살표: 곡선 path, stroke-width 2, 끝에 삼각형 마커
- 분기점: 다이아몬드 또는 점선 분기 표시
- 심각도별 노드 색상: HIGH=#BD3227 배경 흰텍스트, MEDIUM=#C76B1E, LOW=#9E8A15
- 차단 가능 지점은 점선 테두리 + 초록색으로 별도 표시

관계도 SVG 규칙:
- 중앙에 핵심 사건/주제 노드 (큰 원 또는 큰 rect)
- 주변에 행위자 노드 (원형 또는 rounded rect)
- 연결선에 관계 라벨 표시
- 선 두께로 관계 강도 표현 (강=3px, 중=2px, 약=1px 점선)
- 대립 관계: 빨간 점선, 협력 관계: 파란 실선, 경쟁: 주황 대시선

Mermaid는 사용하지 않음. 모든 다이어그램을 SVG로 직접 생성.

출력 형식 (JSON):
{
  "hero_visual_type": "relationship_map|flow_diagram|infographic|combined",
  "hero_title": "시각화 제목",
  "svg_content": "<svg viewBox='0 0 800 500' xmlns='http://www.w3.org/2000/svg'>...</svg>",
  "mermaid_code": "",
  "leaflet_config": {
    "enabled": true/false,
    "center": [위도, 경도],
    "zoom": 4,
    "markers": [{"lat": 0, "lng": 0, "emoji": "🇺🇸", "label": "미국", "color": "#1D6FA5"}],
    "lines": [{"from": [lat,lng], "to": [lat,lng], "color": "#BD3227", "label": "방향"}],
    "circles": [{"lat": 0, "lng": 0, "radius": 500000, "color": "#BD3227", "label": "영향권"}]
  },
  "chart_config": {
    "enabled": true/false,
    "type": "bar|line|radar",
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

주제별 시각화 선택:
- 지정학/군사: leaflet_config enabled + SVG 관계도 (행위자 간 힘의 역학)
- 경제/금융: chart_config enabled + SVG 구조도 (메커니즘 흐름)
- 기술/산업: SVG 플로우차트 (기술 스택 또는 영향 경로)
- 사회/문화: SVG 인포그래픽 (비교 매트릭스)
- 복합: 위 조합

key_metrics는 최대 6개. 가장 중요한 숫자만."""


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
