"""Deterministic visualization builder (v3.1.0).

VisualAnalyst 가 LLM 으로 SVG/지도/차트 사양을 짜는 대신, 코드로 만들 수 있는 시각화를
먼저 채운다. fast/standard 모드에서는 본 빌더만 사용; deep 또는 사용자가 명시한 경우에만
LLM VisualAnalyst 가 호출된다.

빌더 기능:
- ``build_actor_relationship_svg(players)`` — 행위자 카드 + 연결선 SVG
- ``build_flow_chain_svg(chain)`` — 인과 사슬 세로 플로우
- ``build_scenario_table(scenarios)`` — 시나리오 카드 데이터 (HTML 표는 템플릿이 처리)
- ``build_visuals(result)`` — 위 결과를 ``VisualAnalysis`` 로 묶어 반환

본 모듈은 LLM 호출 없이 100% 결정적. 데이터가 비면 빈 SVG/dict 반환.
"""

from __future__ import annotations

from html import escape

from src.models import (
    ChainReactionAnalysis,
    ContextAnalysis,
    DynamicsAnalysis,
    PlayerAnalysis,
    ScenarioAnalysis,
    VisualAnalysis,
)


# 색 팔레트 — visual_analyst 의 기존 시스템 프롬프트와 일치 (보고서 디자인 통일).
_COLOR_CRISIS = "#BD3227"
_COLOR_WARNING = "#C76B1E"
_COLOR_NEUTRAL = "#1D6FA5"
_COLOR_POSITIVE = "#1A7B3E"
_COLOR_KEY = "#9E8A15"
_COLOR_BG = "#151D26"
_COLOR_TEXT = "#D4C4AA"


def _risk_color(risk_level: str) -> str:
    rl = (risk_level or "").lower()
    if "극심" in rl or "critical" in rl:
        return _COLOR_CRISIS
    if "높" in rl or "high" in rl:
        return _COLOR_WARNING
    if "낮" in rl or "low" in rl:
        return _COLOR_POSITIVE
    return _COLOR_NEUTRAL


def build_actor_relationship_svg(players: PlayerAnalysis | None) -> str:
    """행위자를 원형으로 배치한 관계도 SVG. 6명 이하면 한 줄, 그 이상은 두 줄로.

    데이터 없으면 빈 문자열 반환.
    """
    if not players or not players.players:
        return ""
    actors = players.players[:8]
    n = len(actors)
    if n == 0:
        return ""

    width, height = 800, 560
    cx, cy = width // 2, height // 2 + 20
    radius = 200 if n <= 6 else 220

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="행위자 관계도">',
        f'<rect width="{width}" height="{height}" fill="{_COLOR_BG}"/>',
    ]

    # Center title node
    parts.append(
        f'<g transform="translate({cx},{cy})">'
        f'<rect x="-90" y="-30" width="180" height="60" rx="8" '
        f'fill="{_COLOR_NEUTRAL}" stroke="{_COLOR_TEXT}" stroke-width="1"/>'
        f'<text x="0" y="6" text-anchor="middle" fill="{_COLOR_TEXT}" '
        f'font-family="Noto Sans KR" font-size="16" font-weight="700">사건</text>'
        f'</g>'
    )

    import math

    # Lines first (so cards overlay)
    for i, actor in enumerate(actors):
        angle = -math.pi / 2 + (2 * math.pi * i / n)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        parts.append(
            f'<path d="M{cx},{cy} Q{(cx + x) / 2},{(cy + y) / 2 - 30} {x:.1f},{y:.1f}" '
            f'fill="none" stroke="{_COLOR_TEXT}" stroke-width="1.2" '
            f'stroke-opacity="0.5"/>'
        )

    # Actor cards
    for i, actor in enumerate(actors):
        angle = -math.pi / 2 + (2 * math.pi * i / n)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        name = escape((actor.get("name") or "")[:14])
        role = escape((actor.get("role_tag") or "")[:18])
        color = _risk_color(actor.get("risk_level", ""))
        parts.append(
            f'<g transform="translate({x:.1f},{y:.1f})">'
            f'<rect x="-72" y="-26" width="144" height="52" rx="6" '
            f'fill="{color}" stroke="{_COLOR_TEXT}" stroke-width="1"/>'
            f'<text x="0" y="-4" text-anchor="middle" fill="white" '
            f'font-family="Noto Sans KR" font-size="13" font-weight="700">{name}</text>'
            f'<text x="0" y="14" text-anchor="middle" fill="white" '
            f'font-family="Noto Sans KR" font-size="10" opacity="0.9">{role}</text>'
            f'</g>'
        )

    parts.append("</svg>")
    return "".join(parts)


def build_flow_chain_svg(chain_reaction: ChainReactionAnalysis | None) -> str:
    """인과 사슬을 위→아래 박스+화살표 SVG 로 렌더. 데이터 없으면 빈 문자열."""
    if not chain_reaction or not chain_reaction.chain:
        return ""
    steps = chain_reaction.chain[:6]
    n = len(steps)
    if n == 0:
        return ""

    box_w = 360
    box_h = 70
    gap = 30
    width = 500
    height = n * (box_h + gap) + 80

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="인과 사슬">',
        f'<rect width="{width}" height="{height}" fill="{_COLOR_BG}"/>',
    ]

    cx = width // 2
    for i, step in enumerate(steps):
        title = escape((step.get("title") or "")[:34])
        desc = escape((step.get("description") or "")[:54])
        severity = (step.get("severity") or "").lower()
        if "위기" in severity or "critical" in severity or "high" in severity:
            color = _COLOR_CRISIS
        elif "경고" in severity or "warn" in severity or "med" in severity:
            color = _COLOR_WARNING
        else:
            color = _COLOR_NEUTRAL

        y_top = 40 + i * (box_h + gap)
        parts.append(
            f'<g transform="translate({cx - box_w // 2},{y_top})">'
            f'<rect width="{box_w}" height="{box_h}" rx="8" '
            f'fill="{color}" stroke="{_COLOR_TEXT}" stroke-width="1"/>'
            f'<text x="{box_w // 2}" y="26" text-anchor="middle" fill="white" '
            f'font-family="Noto Sans KR" font-size="14" font-weight="700">{title}</text>'
            f'<text x="{box_w // 2}" y="48" text-anchor="middle" fill="white" '
            f'font-family="Noto Sans KR" font-size="11" opacity="0.92">{desc}</text>'
            f'</g>'
        )
        if i < n - 1:
            arrow_y_start = y_top + box_h
            arrow_y_end = y_top + box_h + gap - 4
            parts.append(
                f'<path d="M{cx},{arrow_y_start} L{cx},{arrow_y_end}" '
                f'stroke="{_COLOR_TEXT}" stroke-width="2" '
                f'marker-end="url(#chain-arrow)"/>'
            )

    parts.insert(
        2,
        '<defs><marker id="chain-arrow" viewBox="0 0 10 10" refX="5" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{_COLOR_TEXT}"/></marker></defs>',
    )
    parts.append("</svg>")
    return "".join(parts)


def build_scenario_table(scenarios: ScenarioAnalysis | None) -> list[dict]:
    """시나리오 카드 데이터를 dict 리스트로. 템플릿이 표로 렌더."""
    if not scenarios or not scenarios.scenarios:
        return []
    out: list[dict] = []
    for sc in scenarios.scenarios[:5]:
        out.append({
            "name": (sc.get("name") or "")[:60],
            "tag": (sc.get("tag") or "")[:20],
            "probability": (sc.get("probability") or "")[:20],
            "description": (sc.get("description") or "")[:200],
        })
    return out


def build_key_metrics(context: ContextAnalysis | None) -> list[dict]:
    """ContextAnalysis.key_figures 를 visual key_metrics 형식으로 정규화."""
    if not context or not context.key_figures:
        return []
    out: list[dict] = []
    for fig in context.key_figures[:6]:
        out.append({
            "label": (fig.get("label") or "")[:30],
            "value": (fig.get("value") or "")[:30],
            "color": _COLOR_KEY,
            "icon": "",
        })
    return out


def build_visuals(
    context: ContextAnalysis | None,
    players: PlayerAnalysis | None,
    dynamics: DynamicsAnalysis | None,
    chain_reaction: ChainReactionAnalysis | None,
    scenarios: ScenarioAnalysis | None,
) -> VisualAnalysis:
    """결정적 빌더 종합. LLM 없이 시각화 채움. 데이터 없는 부분은 빈 값.

    confidence_score 는 *생성 가능한 시각화의 비율* 을 0~1 로 정규화.
    """
    svg_actor = build_actor_relationship_svg(players)
    svg_flow = build_flow_chain_svg(chain_reaction)
    key_metrics = build_key_metrics(context)
    glossary: list[dict] = []

    # 가용 시각화 갯수 → confidence proxy.
    tries = 3
    have = sum(bool(x) for x in (svg_actor, svg_flow, key_metrics))
    confidence = round(have / tries, 2) if tries else 0.0

    # 본 빌더는 SVG 기반. Leaflet/Canvas chart 는 데이터에 명시적 좌표/시계열이 있을 때만
    # LLM VisualAnalyst 가 채움 — 결정적 빌더는 enabled=False 로 둠.
    primary_svg = svg_actor or svg_flow
    return VisualAnalysis(
        hero_visual_type="relationship_map" if svg_actor else "flow_diagram",
        hero_title="행위자 관계도" if svg_actor else "인과 사슬",
        svg_content=primary_svg,
        mermaid_code="",
        leaflet_config={"enabled": False},
        chart_config={"enabled": False},
        key_metrics=key_metrics,
        glossary=glossary,
        confidence_score=confidence,
    )


def needs_advanced_visuals(event_description: str) -> bool:
    """사용자 요청 텍스트가 고급 시각화/지도/차트를 *명시* 했는지.

    True 이면 deep 모드가 아니어도 LLM VisualAnalyst 호출을 허용 (orchestrator 가 결정).
    """
    text = (event_description or "").lower()
    keywords = (
        "지도", "map", "차트", "chart", "시계열", "timeseries", "시각화",
        "그래프", "graph", "infographic", "다이어그램",
    )
    return any(kw in text for kw in keywords)
