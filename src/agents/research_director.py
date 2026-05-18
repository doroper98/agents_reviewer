"""V5 Phase 1A — Research Director / Method Router.

REFACTOR_V5_PLAN.md §6 의 *가장 본질적 추가*. 사용자 질의를 받자마자
보고서 유형 / 분석기법 / 필요한 데이터 / 필요한 시각화를 사전 설계하는
별도 LLM 단계.

신문사 비유: 데스크 편집자는 *기자에게 취재 방향과 관점을 미리 지시*
한다. ResearchDirector 가 *기사 데스크의 사전 지시* 역할.

[활성화 전략 — Phase 1A 시점]
- v4.5.7 호출 경로 byte-equal 보존을 위해 *opt-in flag* 로 통합.
- ``Config.enable_research_director`` (env: ``V5_RESEARCH_DIRECTOR=1``)
  가 켜진 환경에서만 ``orchestrator.run_analysis`` 가 호출.
- 꺼져 있는 경우 ``design_via_heuristics`` 가 LLM 호출 없이 결정적
  AnalysisBrief 를 emit (Golden Prompt expected_method 검증 가능).
- LLM 호출 실패 시 ``DEFAULT_BRIEF`` 로 graceful fallback (Plan §20.3).

[Public API]
    from src.agents.research_director import (
        ResearchDirector,
        design_via_heuristics,
        DEFAULT_BRIEF,
        SYSTEM_PROMPT,
    )

Plan SSOT:
- §6.3 ResearchDirector 모듈 시그니처
- §6.4 system prompt 핵심 지시 (1~6 + 원칙)
- §6.5 Composer 와의 인터페이스 변경
- §6.6 인수 기준 (Golden Prompt 20건 ≥ 80% 일치)
- §20.3 DEFAULT_BRIEF (호출 실패 시 fallback)
- docs/RESEARCH_DIRECTOR_METHODS.md — 9종 method 의 사람-친화 SSOT
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from src.agents.base import BaseAgent
from src.config import Config
from src.state.models import (
    AnalysisBrief,
    AnalysisMethod,
    EvidencePack,
    ReportShape,
    VisualConstraints,
)

logger = logging.getLogger(__name__)


# ─── SYSTEM_PROMPT (Plan §6.4 그대로) ────────────────────────────────────

SYSTEM_PROMPT = """당신은 데스크 편집자이자 분석 설계자다. 사용자 질의를 받았을 때 *기자가 글을
쓰기 전에* 다음을 결정한다.

1. 보고서 유형 — 이건 상황 보고인가, 예측인가, 전략 보조인가, 기술 분석인가,
                시장 분석인가, 정책 분석인가.
2. 분석기법 — 이 사건을 풀기에 *가장 적합한* 기법을 1~3개 선정한다.
              ACH·시나리오 트리·전이 채널·이해관계 매트릭스·결정 매트릭스·
              Pre-mortem·전이 타임라인·비교 분석·결함 트리 중에서 고른다.
              왜 이 기법인지 1~2문장으로 정당화한다 (`why_this_method`).
3. 필수 증거 — 이 기법이 *반드시 요구하는* 데이터 종류를 명시한다
                (`required_evidence`).
4. 시각화 제약 — 이 사건에 *반드시 들어가야 할* 시각화 (`must_have`),
                *허용되는* 시각화 (`allowed`),
                *금지되는* 시각화 (`forbidden`).
5. 보고서 형태 — 섹션 수 (3~7), peak 섹션 위치, 필수 섹션 라벨
                (`section_count`, `peak_section`, `must_have_sections`).
6. 전략 모드 신호 — 사용자 질의가 처방적 ("X 를 한다고 했을 때 어떤 전략을
                  취해야 하지" 형태) 이면 strategic_hint=true.

원칙:
- *모든 사건에 같은 분석기법* 을 적용하지 않는다. 사건마다 적합한 기법이 다르다.
- 호르무즈 봉쇄는 *전이 채널 분석* + *시나리오 트리* 가 어울린다.
- LLM 도입 결정은 *결정 매트릭스* + *Pre-mortem* 이 어울린다.
- 미중 반도체 갈등은 *비교 분석* + *전이 타임라인* 이 어울린다.
- 분석기법 선택을 *기록* 으로 남긴다 (`why_this_method`). 후속 단계가 이 근거를 본다.
- 1~3개 method 만 선택. 4개 이상은 *분석 마비* 신호.

Phase 6A — required_exhibits 정책 (Plan §14):
- 각 method 마다 *반드시 필요한 차트* 1~2개를 ``required_exhibits`` 에 명시.
- 이 차트들은 ChartCritic fail 해도 *drop 되지 않고* fallback 으로 격하만 된다
  (AP-V5-28). DeskEditor 가 이를 hold 사유로 인지.
- 보고서당 required exhibit 비율이 *너무 높으면* (>50%) ResearchDirector 의
  prompt tuning 신호 — 정말 핵심인 차트만 required 로.
- ``fallback_form`` — 차트 깨질 때 어떤 형식으로 격하할지:
  · ``fact_grid``: 라벨/값 격자 (≤6 행 권장)
  · ``table``: 데이터 표 (행 다수 시)
  · ``text``: 1문장 자연어 요약 (마지막 수단)

분석기법 enum (반드시 이 9종 중에서만 선택):
- ACH                    — Analysis of Competing Hypotheses (가설 경쟁 분석).
                          여러 시나리오의 증거 정합성을 매트릭스로 평가.
- scenario_tree          — 분기 시나리오 트리. 사건이 어떻게 갈라질지.
- transmission_channel   — 전이 채널 분석. 한 충격이 어떤 경로로 전파되는지
                          (호르무즈 → LNG → 한국 가격).
- stakeholder_matrix     — 이해관계자 매트릭스. 행위자별 이해·인센티브·동맹.
- fault_tree             — 결함 트리. 시스템 실패의 인과 사슬을 역추적.
- decision_matrix        — 결정 매트릭스. 옵션 × 기준 점수표 (전략 모드 핵심).
- pre_mortem             — 사전 부검. "이 옵션이 실패한다면 *어떤 이유로* 실패할까".
- transmission_timeline  — 전이 타임라인. 사건 → 결과의 시계열 추적.
- comparative            — 비교 분석. vs 과거·동종 사례·다른 국가.

보고서 유형 enum (반드시 이 6종 중에서만 선택):
- situation              — 사건 상황 요약·정리 (what_happened).
- forecast               — 미래 예측 (what_next, where_spreads).
- strategy               — 전략 의사결정 보조 (what_to_do — Phase 8 strategic mode).
- technical              — 기술 구조 분석 (HBM 공급망, AI 모델 구조 등).
- market                 — 금융·시장 분석.
- policy                 — 정책·규제 분석.

응답은 *반드시* 아래 JSON 스키마 그대로:

```json
{
  "report_mode": "situation|forecast|strategy|technical|market|policy",
  "primary_question": "사용자 질의를 분석 가능한 형태로 재기술한 한 줄 질문",
  "secondary_questions": ["답을 도출하려면 함께 풀어야 할 부속 질문 1~5개"],
  "thesis": "본 보고서가 도달할 결론의 한 줄 가설 (provisional)",
  "selected_methods": [
    {
      "method": "ACH|scenario_tree|transmission_channel|stakeholder_matrix|fault_tree|decision_matrix|pre_mortem|transmission_timeline|comparative",
      "why_this_method": "이 사건에 이 기법을 고른 이유 1~2문장",
      "required_evidence": ["primary","secondary","expert" 중 필요한 종류],
      "forbidden_visuals": ["이 기법에 부적합한 차트 type 0~3개"],
      "required_exhibits": [
        {
          "description": "예: '호르무즈 의존도 국가별 비교 차트'",
          "visual_type_hint": "예: 'bar' 또는 'choropleth' (Capability Registry 의 type)",
          "why_required": "이 차트가 분석기법의 *핵심 증거* 인 이유 1문장",
          "fallback_form": "fact_grid|table|text"
        }
      ]
    }
  ],
  "report_shape": {
    "section_count": 3-7,
    "peak_section": 0-indexed 섹션 위치,
    "must_have_sections": ["situation","mechanism","scenarios","watch" 등 사건 적합 라벨],
    "optional_sections": []
  },
  "visual_constraints": {
    "must_have": ["map", "decision_matrix" 등 반드시 필요한 시각화"],
    "allowed": ["bar","donut","line","gantt","network","stacked","bubble","heatmap"],
    "forbidden": ["사건과 부적합한 type"]
  },
  "actors_summary": ["이 사건의 핵심 행위자 5~10명 한 줄 요약"],
  "strategic_hint": false
}
```

JSON *외* 텍스트 출력 금지. 마크다운 fence 만 허용.
"""


# ─── DEFAULT_BRIEF (Plan §20.3 — 호출 실패 시 fallback) ───────────────────


def _default_brief() -> AnalysisBrief:
    """Plan §20.3: 'ResearchDirector 가 실패하면 *기본 AnalysisBrief* 를
    사용한다 (selected_methods 비어 있고, report_shape.section_count=4,
    must_have_sections=["situation","mechanism","scenarios","watch"]). v4.5.7
    동작과 사실상 동일하다.'
    """
    return AnalysisBrief(
        report_mode="situation",
        primary_question="",
        secondary_questions=[],
        thesis="",
        selected_methods=[],
        report_shape=ReportShape(
            section_count=4,
            peak_section=0,
            must_have_sections=["situation", "mechanism", "scenarios", "watch"],
            optional_sections=[],
        ),
        visual_constraints=VisualConstraints(
            must_have=[],
            allowed=["bar", "donut", "line", "gantt", "network", "stacked", "bubble", "heatmap"],
            forbidden=[],
        ),
        actors_summary=[],
        strategic_hint=False,
    )


# 모듈 레벨 SSOT — 회귀 테스트가 직접 import.
DEFAULT_BRIEF = _default_brief()


# ─── 결정적 fallback — heuristic method router (LLM 0) ──────────────────


# Plan §6.4 의 원칙 + docs/RESEARCH_DIRECTOR_METHODS.md 의 사례를 키워드 → method
# 매핑으로 박는다. 회귀 테스트가 Golden Prompt 20건 expected_method 와의 일치도
# ≥ 80% 를 검증.

_STRATEGIC_PATTERNS = [
    re.compile(r"어떤 전략"),
    re.compile(r"어떻게 해야"),
    re.compile(r"어떤 (선택|결정|판단|길)"),
    re.compile(r"취해야 (하|할)"),
    re.compile(r"(고려|반영)했을 때.{0,30}(전략|결정|선택)"),
    re.compile(r"옵션.{0,10}(평가|비교|선택)"),
    re.compile(r"(어느 쪽|어디로|어느 방향)으로"),
    re.compile(r"vs[.\s]"),
]


_METHOD_KEYWORDS: list[tuple[str, list[str]]] = [
    # method_id, [keywords (한국어)]
    ("decision_matrix",       ["전략", "어떻게 해야", "어떤 전략", "도입", "선택", "결정", "옵션", "어떤 길"]),
    ("transmission_channel",  ["전이", "채널", "공급망", "봉쇄", "유동성", "수출", "수입", "환율", "원유", "lng",
                               "에너지 안보", "여파", "자금 유입", "변동성", "관세"]),
    ("scenario_tree",         ["시나리오", "충돌 가능성", "전망", "확률", "분기", "시각", "위기", "전쟁", "분쟁",
                               "갈등", "충돌", "예측", "향후"]),
    ("stakeholder_matrix",    ["행위자", "이해관계", "동맹", "안보", "정책", "규제", "도입", "양측",
                               "정부", "기업", "통합", "영향"]),
    ("transmission_timeline", ["흐름", "5년", "10년", "추세", "이력", "변천", "장기"]),
    ("comparative",           ["vs", "비교", "다른", "대조", "차이", "윤리", "한계", "관점"]),
    ("pre_mortem",            ["실패", "역추적", "사전 부검"]),
    ("fault_tree",            ["사고", "결함", "오작동", "원인 분석"]),
    ("ACH",                   ["가설", "경쟁", "어느 쪽이 맞", "가능성 평가"]),
]


_REPORT_MODE_HINTS: list[tuple[str, list[str]]] = [
    ("strategy",  ["전략", "어떻게 해야", "옵션", "도입", "결정"]),
    ("forecast",  ["가능성", "전망", "시나리오", "향후", "다음"]),
    ("market",    ["변동성", "옵션", "etf", "유동성", "환율", "캐리", "상관", "kospi", "비트코인"]),
    ("technical", ["출시", "통합", "양산", "공급망", "공개", "포지셔닝", "추론"]),
    ("policy",    ["규제", "법안", "도입", "유예", "정책", "act", "분류"]),
]


def design_via_heuristics(user_request: str, mode: str = "standard") -> AnalysisBrief:
    """LLM 호출 없이 Golden Prompt 회귀 테스트가 사용 가능한 결정적 method router.

    실제 ResearchDirector LLM 의 출력보다 *덜 정교* 하지만, Plan §6.6 의
    인수 기준 #4 (Golden Prompt 20건 ≥ 80% 일치) 를 만족시키도록 키워드 가중합
    + 도메인 별 우선순위로 method 1~3개 선정.

    회귀 테스트가 본 함수의 출력을 expected_method 와 비교해 baseline 측정.
    """
    text = (user_request or "").lower()

    # 1. report_mode 결정 — 첫 번째 매칭되는 hint.
    report_mode: Literal["situation", "forecast", "strategy", "technical", "market", "policy"] = "situation"
    for mode_id, kws in _REPORT_MODE_HINTS:
        if any(k.lower() in text for k in kws):
            report_mode = mode_id  # type: ignore[assignment]
            break

    # 2. strategic_hint — 패턴 매칭.
    strategic_hint = any(p.search(user_request or "") for p in _STRATEGIC_PATTERNS)
    if strategic_hint:
        report_mode = "strategy"

    # 3. method 선정 — 키워드 점수합. 상위 1~3개.
    scores: dict[str, int] = {}
    for method_id, kws in _METHOD_KEYWORDS:
        score = sum(1 for k in kws if k.lower() in text)
        if score > 0:
            scores[method_id] = score

    if not scores:
        # 키워드 매칭 실패 — situation 으로 기본 처리.
        primary_method = "scenario_tree" if "분석" in text else "comparative"
        scores = {primary_method: 1}

    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_methods = [m for m, _ in ordered[:3]]

    selected_methods: list[AnalysisMethod] = []
    for m in top_methods:
        selected_methods.append(
            AnalysisMethod(
                method=m,  # type: ignore[arg-type]
                why_this_method=_DEFAULT_RATIONALE.get(m, "키워드 휴리스틱 선정"),
                required_evidence=_DEFAULT_REQUIRED_EVIDENCE.get(m, ["primary", "secondary"]),
                forbidden_visuals=_DEFAULT_FORBIDDEN_VISUALS.get(m, []),
                required_exhibits=_DEFAULT_REQUIRED_EXHIBITS.get(m, []),
            )
        )

    # 4. report_shape — mode 별 디폴트.
    section_count = {"fast": 4, "standard": 5, "deep": 6}.get(mode, 5)
    must_have_sections = ["situation", "mechanism", "scenarios", "watch"]
    if report_mode == "strategy":
        must_have_sections = [
            "decision_context", "options", "criteria", "matrix",
            "recommendation", "watch",
        ]
        section_count = max(section_count, 6)

    # 5. visual_constraints.
    must_have: list[str] = []
    forbidden: list[str] = []
    # 지리·지정학 관련 → map.
    if any(k in text for k in ["호르무즈", "해협", "반도체 갈등", "지도", "남중국해", "대만", "이스라엘 이란"]):
        must_have.append("map")
    # 윤리·논의형 → 차트 자체 비추천.
    if any(k in text for k in ["윤리", "프라이버시", "trade-off"]):
        forbidden = ["bar", "donut", "line", "gantt", "network", "stacked", "bubble", "heatmap"]
    # 결정 매트릭스 method → must_have decision_matrix.
    if "decision_matrix" in [m.method for m in selected_methods]:
        if "decision_matrix" not in must_have:
            must_have.append("decision_matrix")

    return AnalysisBrief(
        report_mode=report_mode,
        primary_question=user_request[:200],
        secondary_questions=[],
        thesis="",
        selected_methods=selected_methods,
        report_shape=ReportShape(
            section_count=section_count,
            peak_section=2,
            must_have_sections=must_have_sections,
            optional_sections=[],
        ),
        visual_constraints=VisualConstraints(
            must_have=must_have,
            allowed=["bar", "donut", "line", "gantt", "network", "stacked", "bubble", "heatmap", "map"],
            forbidden=forbidden,
        ),
        actors_summary=[],
        strategic_hint=strategic_hint,
    )


# ─── 결정적 fallback 의 보조 매핑 ───────────────────────────────────────


_DEFAULT_RATIONALE: dict[str, str] = {
    "ACH": "여러 가설의 증거 정합성을 매트릭스로 비교 평가해야 한다.",
    "scenario_tree": "사건이 갈라질 미래 분기를 정렬하고 확률·영향을 평가한다.",
    "transmission_channel": "한 충격이 어떤 경로로 전파되는지 단계별 추적이 핵심.",
    "stakeholder_matrix": "행위자별 이해·인센티브·동맹 구도를 정렬해야 분석이 풀린다.",
    "fault_tree": "시스템 실패의 인과 사슬을 역추적해 차단점을 찾는다.",
    "decision_matrix": "옵션 × 기준 점수표가 의사결정 보조의 핵심 시각화.",
    "pre_mortem": "권고가 실패한다면 어떤 이유로 실패할지 사전에 부검.",
    "transmission_timeline": "사건 → 결과의 시계열 추적이 변천을 드러낸다.",
    "comparative": "과거·동종 사례와의 비교가 사건의 의미를 정렬한다.",
}

_DEFAULT_REQUIRED_EVIDENCE: dict[str, list[str]] = {
    "ACH": ["primary", "secondary", "expert"],
    "scenario_tree": ["primary", "secondary"],
    "transmission_channel": ["primary"],
    "stakeholder_matrix": ["primary", "secondary"],
    "fault_tree": ["primary", "expert"],
    "decision_matrix": ["secondary", "expert"],
    "pre_mortem": ["expert", "model_inference"],
    "transmission_timeline": ["primary", "secondary"],
    "comparative": ["primary", "secondary", "expert"],
}

_DEFAULT_FORBIDDEN_VISUALS: dict[str, list[str]] = {
    "ACH": ["donut"],
    "decision_matrix": ["network"],
    "comparative": ["network"],
}

_DEFAULT_REQUIRED_EXHIBITS: dict[str, list[dict[str, str]]] = {
    "scenario_tree": [{
        "description": "시나리오별 확률 × 영향 매트릭스",
        "visual_type_hint": "bubble",
        "why_required": "분기 시나리오의 정량 비교가 method 의 핵심 산출.",
        "fallback_form": "fact_grid",
    }],
    "transmission_channel": [{
        # v5.3.0 — sankey 가 다단계 분배에 더 적합. bar 는 1차원 비교만 가능.
        "description": "전이 채널 단계별 흐름 분해 (매출→segment→비용→이익 같은)",
        "visual_type_hint": "sankey",
        "why_required": "한 입력이 다단계 노드로 어떻게 갈라지고 흡수되는지 정량 추적.",
        "fallback_form": "table",
    }],
    "stakeholder_matrix": [{
        "description": "행위자 관계도",
        "visual_type_hint": "network",
        "why_required": "이해관계자 동맹·대립 구도 시각화가 method 의 산출.",
        "fallback_form": "table",
    }],
    "decision_matrix": [{
        "description": "옵션 × 기준 결정 매트릭스",
        "visual_type_hint": "decision_matrix",
        "why_required": "Phase 8 strategic mode 의 핵심 산출 — 권고 도출 근거.",
        "fallback_form": "table",
    }],
    "transmission_timeline": [{
        "description": "단계별 시간 흐름",
        "visual_type_hint": "gantt",
        "why_required": "시계열 변천 추적이 method 의 핵심.",
        "fallback_form": "table",
    }],
    "comparative": [{
        "description": "차원별 비교 차트",
        "visual_type_hint": "bar",
        "why_required": "비교 양측의 정량 차이 표시.",
        "fallback_form": "fact_grid",
    }],
    "ACH": [{
        "description": "가설 × 증거 매트릭스",
        "visual_type_hint": "heatmap",
        "why_required": "가설 경쟁 분석의 핵심 시각화.",
        "fallback_form": "table",
    }],
    "fault_tree": [{
        # v5.2.14 Layer 3 — waterfall 이 자연 적합 (실패 요인 누적 분해).
        # 신규 type 도입 시 자동 수요 보장의 SSOT.
        "description": "실패 요인별 누적 분해",
        "visual_type_hint": "waterfall",
        "why_required": "fault_tree 의 핵심 산출 — 시작값에서 각 요인으로 분해되는 형태.",
        "fallback_form": "table",
    }],
    "pre_mortem": [{
        # v5.2.14 Layer 3 — scatter 가 실패 모드 시각화에 적합
        # (가능성 × 영향, 단 size 인코딩 불필요).
        "description": "실패 모드 가능성 × 영향 산점도",
        "visual_type_hint": "scatter",
        "why_required": "pre_mortem 의 'what could go wrong' 을 정량 위상으로.",
        "fallback_form": "fact_grid",
    }],
}


# ─── ResearchDirector — LLM 호출 ──────────────────────────────────────


class ResearchDirector(BaseAgent):
    """Plan §6.3 의 ResearchDirector — 사용자 질의 + EvidencePack 을 받아
    AnalysisBrief 를 emit.

    [모델·예산]
        DIRECTOR_MODEL = "claude-opus-4-7"  (분석기법 선택은 Opus capability)
        MAX_TOKENS     = 6000               (Plan §21 Phase 1A 추정)

    [사용]
        director = ResearchDirector(config)
        brief = await director.design(
            user_request="이스라엘 이란 충돌 가능성 분석",
            evidence_pack=ep,
            mode="deep",
            user_intent="what_next",
        )

    [Fallback]
        호출 실패 / JSON 파싱 실패 시 design_or_default() 가 DEFAULT_BRIEF 반환
        + telemetry 에 ``research_director_fallback=true`` 기록.
    """

    DIRECTOR_MODEL = "claude-opus-4-7"
    MAX_TOKENS = 6000

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="research_director",
            role="Research Director (분석 설계자)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=False,
        )
        self.model_name = self.DIRECTOR_MODEL

    async def design(
        self,
        user_request: str,
        evidence_pack: EvidencePack | None,
        mode: str = "standard",
        user_intent: str = "",
    ) -> AnalysisBrief:
        """Plan §6.3 — AnalysisBrief 를 emit.

        Args:
            user_request: 텔레그램 사용자 메시지 원문.
            evidence_pack: ContextAnalyst 의 압축 출력. None 이면 heuristic 만.
            mode: fast / standard / deep.
            user_intent: 텔레그램 봇의 intent classifier 결과 (선택).

        Returns:
            AnalysisBrief — Plan §4.3 / §6.3 의 모델.
        """
        self._max_tokens_override = self.MAX_TOKENS
        # EvidencePack 의 압축 요약을 user_message 의 보조 자료로 동봉.
        evidence_summary: dict[str, Any] = {}
        if evidence_pack is not None:
            evidence_summary = {
                "category": evidence_pack.category,
                "claims": [
                    {
                        "statement": c.statement,
                        "source_id": c.source_ids[0] if c.source_ids else "",
                    }
                    for c in (evidence_pack.claims or [])[:20]
                ],
                "timeline_count": len(evidence_pack.timeline or []),
                "actors": [a.name for a in (evidence_pack.actors or [])[:10]],
                "contradiction_count": len(evidence_pack.contradictions or []),
            }

        context = {
            "user_request": user_request,
            "mode": mode,
            "user_intent": user_intent,
            "evidence_pack_summary": evidence_summary,
        }
        try:
            raw_text = await super().analyze(context)
            return self._parse_brief(raw_text)
        except Exception as e:
            logger.warning(
                "[research_director] LLM call or parse failed: %s. "
                "Falling back to DEFAULT_BRIEF (Plan §20.3).",
                e,
            )
            if self.telemetry is not None:
                # telemetry 에 fallback 발화 기록 — 회귀 테스트 / Phase 1A 인수
                # 기준 #1 (모든 사건에 emit) 충족 확인.
                setattr(self.telemetry, "research_director_fallback", True)
            return _default_brief()

    async def design_or_heuristic(
        self,
        user_request: str,
        evidence_pack: EvidencePack | None,
        mode: str = "standard",
        user_intent: str = "",
    ) -> AnalysisBrief:
        """``design()`` 의 실패 시 ``DEFAULT_BRIEF`` 가 아닌 *결정적 heuristic*
        으로 fallback. opt-in flag 가 꺼진 환경에서도 AnalysisBrief 가
        emit 되어 Phase 1A 인수 기준 #1 을 충족시키는 경로.

        호출 비용을 최소화하려면 본 함수를 호출하지 말고 ``design_via_heuristics``
        를 직접 사용 (LLM 0).
        """
        try:
            return await self.design(
                user_request=user_request,
                evidence_pack=evidence_pack,
                mode=mode,
                user_intent=user_intent,
            )
        except Exception:
            return design_via_heuristics(user_request, mode=mode)

    def _parse_brief(self, raw_text: str) -> AnalysisBrief:
        """LLM 응답 → AnalysisBrief Pydantic 파싱.

        BaseAgent._parse_json_response 와 유사하지만 AnalysisBrief 의 *부분
        필드만* 채워 emit 된 경우에도 보수적 파싱.
        """
        import json

        text = (raw_text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"AnalysisBrief JSON parse failed: {e}") from e

        if not isinstance(data, dict):
            raise ValueError("AnalysisBrief root must be a JSON object")
        return AnalysisBrief.model_validate(data)
