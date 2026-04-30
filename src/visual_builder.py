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
    judgment: "JudgmentVerdict | None" = None,  # forward ref
) -> VisualAnalysis:
    """결정적 빌더 종합. LLM 없이 시각화 채움. 데이터 없는 부분은 빈 값.

    confidence_score 는 *생성 가능한 시각화의 비율* 을 0~1 로 정규화.
    chart_config 에 d3 차트들이 들어감 (charts.js 가 ID 별로 그림).
    """
    svg_actor = build_actor_relationship_svg(players)
    svg_flow = build_flow_chain_svg(chain_reaction)
    key_metrics = build_key_metrics(context)
    glossary: list[dict] = []

    # v3.2.0 — d3 차트 데이터 빌더 (모두 결정적).
    chart_payload = build_chart_payload(
        context=context,
        players=players,
        dynamics=dynamics,
        chain_reaction=chain_reaction,
        scenarios=scenarios,
        judgment=judgment,
    )

    tries = 3
    have = sum(bool(x) for x in (svg_actor, svg_flow, key_metrics))
    confidence = round(have / tries, 2) if tries else 0.0

    primary_svg = svg_actor or svg_flow
    chart_enabled = bool(chart_payload)
    return VisualAnalysis(
        hero_visual_type="relationship_map" if svg_actor else "flow_diagram",
        hero_title="행위자 관계도" if svg_actor else "인과 사슬",
        svg_content=primary_svg,
        mermaid_code="",
        leaflet_config={"enabled": False},
        chart_config={"enabled": chart_enabled, "payload": chart_payload},
        key_metrics=key_metrics,
        glossary=glossary,
        confidence_score=confidence,
    )


# ----------------------------------------------------------------------
# v3.2.0 — d3 chart payload builders (deterministic, no LLM)
# ----------------------------------------------------------------------


def _parse_prob(p) -> int:
    """Parse '35%' / '0.35' / 35 → integer 0~100."""
    if isinstance(p, (int, float)):
        return int(round(p * 100)) if p <= 1.0001 else int(round(p))
    if isinstance(p, str):
        import re
        m = re.search(r"(\d{1,3}(?:\.\d+)?)", p)
        if m:
            v = float(m.group(1))
            return int(round(v * 100)) if v <= 1.0001 else int(round(v))
    return 0


def build_scenario_chart_data(scenarios: "ScenarioAnalysis | None") -> list[dict]:
    """ScenarioAnalysis → 시나리오 막대 차트 데이터."""
    if not scenarios or not scenarios.scenarios:
        return []
    out: list[dict] = []
    for sc in scenarios.scenarios[:6]:
        out.append({
            "name": (sc.get("name") or "")[:24],
            "tag": sc.get("tag") or "",
            "prob": _parse_prob(sc.get("probability", 0)),
            "note": (sc.get("description") or "")[:80],
        })
    return out


def build_key_figures_chart_data(context: "ContextAnalysis | None") -> list[dict]:
    """ContextAnalysis.key_figures → 도넛 차트 데이터.

    수치 추출: value 문자열에서 첫 숫자 파싱. 추출 실패 시 1로 폴백.
    """
    if not context or not context.key_figures:
        return []
    import re
    out: list[dict] = []
    for fig in context.key_figures[:6]:
        raw = str(fig.get("value", ""))
        m = re.search(r"(\d+(?:[.,]\d+)?)", raw.replace(",", ""))
        v = float(m.group(1)) if m else 1.0
        out.append({
            "label": (fig.get("label") or "")[:14],
            "value": v,
            "context": (fig.get("context") or "")[:60],
        })
    return out


def build_severity_chart_data(chain: "ChainReactionAnalysis | None") -> list[dict]:
    """ChainReactionAnalysis.chain → severity 히트맵 데이터."""
    if not chain or not chain.chain:
        return []
    out: list[dict] = []
    for step in chain.chain[:8]:
        out.append({
            "title": (step.get("title") or "")[:24],
            "severity": (step.get("severity") or "low"),
        })
    return out


def build_confidence_chart_data(judgment) -> dict | None:
    """JudgmentVerdict.confidence (3축) → 차트 데이터."""
    if judgment is None or judgment.confidence is None:
        return None
    cp = judgment.confidence
    return {
        "source_diversity": float(cp.source_diversity),
        "data_freshness": float(cp.data_freshness),
        "expert_consensus": float(cp.expert_consensus),
    }


def build_stacked_chart_data(scenarios: "ScenarioAnalysis | None") -> dict | None:
    """ScenarioAnalysis.scenarios[*].impact_by_player → 시나리오 × 행위자 누적 막대."""
    if not scenarios or not scenarios.scenarios:
        return None
    palette_seed = ["#1A7B3E", "#C9A84C", "#1D6FA5", "#C76B1E", "#BD3227", "#8D4D14"]
    actors_seen: dict[str, str] = {}

    def _color_for(actor: str) -> str:
        if actor not in actors_seen:
            actors_seen[actor] = palette_seed[len(actors_seen) % len(palette_seed)]
        return actors_seen[actor]

    rows: list[dict] = []
    for sc in scenarios.scenarios[:5]:
        impacts = sc.get("impact_by_player") or []
        if not impacts:
            continue
        segments = []
        for imp in impacts[:5]:
            actor = (imp.get("player") or "")[:14]
            if not actor:
                continue
            # sentiment 가 비대칭이라 절대값으로 가중치 — 전부 동등 가중 1.
            segments.append({
                "label": actor,
                "value": 1,
                "color": _color_for(actor),
            })
        if segments:
            rows.append({
                "name": (sc.get("name") or "")[:18],
                "segments": segments,
            })
    if not rows:
        return None
    return {"scenarios": rows}


def build_bubble_chart_data(chain: "ChainReactionAnalysis | None") -> list[dict] | None:
    """ChainReactionAnalysis.wildcards → 리스크 매트릭스 버블."""
    if not chain or not chain.wildcards:
        return None
    out: list[dict] = []
    for w in chain.wildcards[:8]:
        prob = _parse_prob(w.get("probability", 0)) / 100.0
        impact_str = (w.get("impact") or w.get("severity") or "").lower()
        if "극심" in impact_str or "crit" in impact_str:
            impact = 0.95
        elif "높" in impact_str or "high" in impact_str:
            impact = 0.75
        elif "중" in impact_str or "med" in impact_str:
            impact = 0.5
        elif "낮" in impact_str or "low" in impact_str:
            impact = 0.25
        else:
            impact = 0.6
        out.append({
            "label": (w.get("event") or "")[:14],
            "x": prob,
            "y": impact,
            "size": max(20, int(prob * 100)),
            "note": (w.get("event") or "")[:80],
        })
    return out if out else None


def build_gantt_chart_data(context: "ContextAnalysis | None") -> list[dict] | None:
    """ContextAnalysis.timeline → Gantt. 날짜 비교가 가능하면 enable."""
    if not context or not context.timeline:
        return None
    items = []
    timeline = context.timeline[:8]
    n = len(timeline)
    for i, t in enumerate(timeline):
        date = (t.get("date") or "")[:10] or f"T{i+1}"
        event = (t.get("event") or "")[:24]
        if not event:
            continue
        items.append({
            "label": event,
            "start": i,
            "end": min(i + 1, n - 1) + 0.7,
            "color": "#C9A84C",
            "note": date,
        })
    return items if len(items) >= 2 else None


def build_network_chart_data(players: "PlayerAnalysis | None") -> dict | None:
    """PlayerAnalysis.players + alliances → force-directed network."""
    if not players or not players.players:
        return None
    nodes: list[dict] = []
    for p in players.players[:10]:
        name = (p.get("name") or "")[:12]
        if not name:
            continue
        risk = (p.get("risk_level") or "").lower()
        if "극심" in risk or "crit" in risk:
            group = "대립"
        elif "높" in risk:
            group = "주요"
        elif "낮" in risk:
            group = "중립"
        else:
            group = "주요"
        nodes.append({
            "id": name,
            "label": name,
            "group": group,
            "note": (p.get("role_tag") or "")[:30],
        })
    if len(nodes) < 2:
        return None

    links: list[dict] = []
    for a in (players.alliances or [])[:10]:
        group_names = a.get("group") or []
        if len(group_names) < 2:
            continue
        nature = (a.get("nature") or "중립").lower()
        link_type = "동맹"
        if "대립" in nature or "경쟁" in nature:
            link_type = "대립"
        elif "협력" in nature or "동맹" in nature:
            link_type = "동맹"
        else:
            link_type = "중립"
        for i in range(len(group_names) - 1):
            src = group_names[i][:12]
            tgt = group_names[i + 1][:12]
            if src and tgt:
                links.append({"source": src, "target": tgt, "type": link_type})

    return {"nodes": nodes, "links": links}


def build_chart_payload(
    *,
    context: "ContextAnalysis | None",
    players: "PlayerAnalysis | None",
    dynamics: "DynamicsAnalysis | None",
    chain_reaction: "ChainReactionAnalysis | None",
    scenarios: "ScenarioAnalysis | None",
    judgment=None,
) -> dict:
    """가용 데이터를 보고 적절한 차트 데이터를 모두 채움.

    빈 dict 반환 가능 (데이터 없으면 차트 0개 → chart_config.enabled=False).
    """
    payload: dict = {}

    sc_bar = build_scenario_chart_data(scenarios)
    if sc_bar:
        payload["scenarios"] = sc_bar

    kf_donut = build_key_figures_chart_data(context)
    if kf_donut:
        payload["key_figures"] = kf_donut

    sev = build_severity_chart_data(chain_reaction)
    if sev:
        payload["severity_chain"] = sev

    conf = build_confidence_chart_data(judgment)
    if conf:
        payload["confidence"] = conf

    stacked = build_stacked_chart_data(scenarios)
    if stacked:
        payload["stacked"] = stacked

    bubble = build_bubble_chart_data(chain_reaction)
    if bubble:
        payload["bubble"] = bubble

    gantt = build_gantt_chart_data(context)
    if gantt:
        payload["gantt"] = gantt

    network = build_network_chart_data(players)
    if network:
        payload["network"] = network

    return payload


# ----------------------------------------------------------------------
# v3.3.0 — Chart catalog for narrative_composer
# ----------------------------------------------------------------------
#
# narrative_composer 는 ``embedded_charts: list[str]`` 에 chart_id 를 적어 본문에
# 박는다. 본 catalog 는 *지금 가용한* 차트만 (id, title, hint) 형태로 노출 →
# 데이터 없는 차트를 composer 가 referencing 하지 못하게 한다.
#
# chart_id ↔ payload key ↔ charts.js auto-init element id 매핑은 1:1:
#   payload["scenarios"]      → element id "chart-scenarios"
#   payload["key_figures"]    → element id "chart-figures"
#   payload["severity_chain"] → element id "chart-severity"
#   payload["confidence"]     → element id "chart-confidence"
#   payload["timeseries"]     → element id "chart-timeseries"
#   payload["stacked"]        → element id "chart-stacked"
#   payload["bubble"]         → element id "chart-bubble"
#   payload["gantt"]          → element id "chart-gantt"
#   payload["network"]        → element id "chart-network"

_CHART_CATALOG_DESCRIPTORS: dict[str, tuple[str, str, str]] = {
    # payload_key: (chart_id, title, hint for composer)
    "scenarios":      ("chart-scenarios",  "시나리오 확률 분포",     "막대 차트. 시나리오별 확률을 한눈에 비교할 때."),
    "key_figures":    ("chart-figures",    "핵심 수치 분배",         "도넛 차트. 사건의 핵심 수치 비중을 보여줄 때."),
    "severity_chain": ("chart-severity",   "인과 사슬 위험도",       "히트맵. 각 인과 단계의 심각도 흐름을 시각화."),
    "confidence":     ("chart-confidence", "신뢰도 분해",            "3축 차트. 출처 다양성·신선도·전문가 합의를 분리해 보여줌."),
    "timeseries":     ("chart-timeseries", "시계열 추이",            "선 차트. 시간에 따른 핵심 지표 변화를 강조할 때."),
    "stacked":        ("chart-stacked",    "시나리오 × 행위자 영향",  "누적 막대. 시나리오별로 누가 얼마나 영향받는지."),
    "bubble":         ("chart-bubble",     "리스크 매트릭스",        "버블. 확률 × 영향 좌표에 와일드카드를 배치."),
    "gantt":          ("chart-gantt",      "타임라인",               "Gantt. 사건의 시간축 구간을 보여줄 때."),
    "network":        ("chart-network",    "행위자 관계도",          "네트워크. 행위자 간 동맹·대립 구조를 시각화."),
}


def build_chart_catalog(chart_payload: dict) -> list[dict]:
    """``chart_payload`` 에서 *실제로 데이터가 있는* 차트만 추려 catalog 로 반환.

    composer prompt 입력용 — 데이터 없는 chart_id 를 referencing 못하게 한다.
    """
    if not chart_payload:
        return []
    out: list[dict] = []
    for key, (chart_id, title, hint) in _CHART_CATALOG_DESCRIPTORS.items():
        if chart_payload.get(key):
            out.append({"id": chart_id, "title": title, "hint": hint})
    return out


def chart_id_to_payload_key(chart_id: str) -> str | None:
    """역방향 lookup. composer 가 임의 chart_id 를 적었을 때 payload key 로 변환."""
    for key, (cid, _, _) in _CHART_CATALOG_DESCRIPTORS.items():
        if cid == chart_id:
            return key
    return None


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
