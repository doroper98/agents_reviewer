# Agents Reviewer — V3 Refactoring Master Plan

> **Target:** `doroper98/agents_reviewer`
> **Current version:** v2.4.0
> **Target version:** v3.0.0 (after Step 5)
> **Scope:** 분석 시스템 전반의 사고 구조 개선. 형식 압력 해소, 사건별 최적 분석 달성.

---

## 0. How to Use This Document

이 문서는 코딩 에이전트가 단계적으로 실행할 마스터 플랜이다. 다음 규칙을 지킬 것.

- 각 Step은 독립적으로 커밋한다. 단계를 건너뛰지 않는다.
- 각 Step 종료 시 `DEVLOG.md`에 변경 내역을 추가한다.
- 각 Step의 **Acceptance Criteria**를 모두 통과하지 못하면 다음 Step으로 진행하지 않는다.
- 기존 텔레그램 봇 인터페이스, Cloudflare 배포 흐름, 한국어 음슴체 톤은 변경하지 않는다.
- 의문이 생기면 사용자에게 묻기 전에 본 문서의 **Appendix**와 **Anti-patterns** 섹션부터 다시 읽는다.

커밋 메시지 규칙: `v{VER}: {요약}` (예: `v2.5.0: AnalysisStrategy Pydantic 승격`)

---

## 1. Why This Refactor

### 1.1 사용자가 느낀 증상

> "보고서에서 사용하는 분석 기법과 보고서의 구조 및 흐름이 너무 형식에 얽매여 있는 듯한 느낌이 강하다."

모든 사건이 같은 옷을 입은 것처럼 보인다. 인물극에 적합한 6막 극장 메타포가 기술·시장·과학 사건에도 강제 적용된다.

### 1.2 진짜 원인 (코드 레벨)

| # | 진단 | 코드 위치 |
|---|------|----------|
| 1 | `_generate_analysis_strategy()`가 dict를 반환. 계약(contract)이 없음 | `src/orchestrator.py:52-145` |
| 2 | Pydantic 모델이 정적. `PlayerAnalysis`, `DynamicsAnalysis` 등이 분석 형태를 강제 | `src/models.py` |
| 3 | HTML 매크로가 모델과 1:1 강결합. `render_players`/`render_dynamics`/`render_chain_reaction`/`render_scenarios` | `src/templates/report.html:157-280` |
| 4 | 7개 페르소나가 모든 사건에 동일 적용 | `src/agents/*.py` |
| 5 | `confidence_score: float` 단일 스칼라. 분해 없음 | 모든 분석 모델 |
| 6 | claim과 evidence가 추적되지 않음. 출처는 `sources: list[str]`로 끝 | `ContextAnalysis.sources` |
| 7 | 단방향 파이프라인. 품질 게이트 부재 | `src/orchestrator.py` |
| 8 | Watchlist가 보고서 텍스트로만 존재. 시스템적 추적 없음 | `ScenarioArchitect.watch_signals` |

### 1.3 핵심 인사이트 (전제)

**사건 유형뿐 아니라 사용자의 *질문 유형*에 따라 분석 기법과 보고서 구조가 달라져야 한다.**

같은 환율 사건도:
- "왜 이러는 거임?" → Root Cause + Systems Dynamics
- "어디로 번지나?" → Transmission Channel + Cascade Map
- "어떻게 대응함?" → Decision Matrix + Pre-mortem

질문 유형 분기 없이는 형식 압력이 해소되지 않는다.

---

## 2. Goals & Non-Goals

### 2.1 Goals

1. `AnalysisStrategy`를 정식 Pydantic 모델로 승격하고, 분석의 *전체 설계도*가 되게 한다.
2. 보고서 아키타입을 다중화한다. 6막 극장은 옵션 중 하나로 강등.
3. 분석 렌즈를 풀(pool)에서 사건별로 골라 실행한다.
4. claim-evidence 추적성을 모델 레벨에서 강제한다.
5. Quality Gate 두 곳을 도입한다 (Plan Sanity, Coverage Check).
6. `ConfidenceProfile`을 도입해 신뢰도를 3축으로 분해한다.
7. Watchlist를 보고서 텍스트가 아닌 자동 모니터링 시스템으로 만든다.
8. **점진 마이그레이션.** 빅뱅 리팩토링을 절대 하지 않는다.

### 2.2 Non-Goals (이번 리팩토링이 *하지 않는 것*)

- 7개 에이전트 즉시 폐지 — 단계적 통합 또는 Lens로 재정의
- 6막 극장 즉시 제거 — `archetype="six_act_theater"`로 보존
- 텔레그램 봇 명령어 인터페이스 변경
- Cloudflare Pages 배포 흐름 변경
- 음슴체 톤·모바일 반응형 CSS 변경
- 영어 전환 (한국어 + 영어 혼용 유지)
- Oracle Cloud 1GB VM 외 인프라 가정

---

## 3. Target Architecture (V3)

### 3.1 전체 흐름

```
User Request (Telegram)
    │
    ▼
┌─────────────────────────────┐
│  Intent Classifier          │ ← user_intent 결정 (7종)
│  (모호하면 Multi-Intent)     │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Strategy Planner           │
│  - core_questions           │
│  - recommended_lenses       │
│  - evidence_plan            │
│  - report_archetype         │
│  - section_plan             │
│  - uncertainty_policy       │
└──────────────┬──────────────┘
               ▼
       ┌────[Quality Gate 1]────┐
       │  Plan Sanity Check     │
       └──────────────┬─────────┘
                      ▼
┌─────────────────────────────┐
│  Evidence Collector         │ ← fact_table, source_reliability
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Lens Runner Pool (top 3~4) │ ← Geopolitical / Financial /
│                             │   Technology / Policy /
│                             │   Accident / Market / ...
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Synthesis Judge            │
│  - contradiction matrix     │
│  - counter-hypothesis       │
│  - confidence (3-axis)      │
│  - main judgment            │
└──────────────┬──────────────┘
               ▼
       ┌────[Quality Gate 2]────┐
       │  Coverage·Trace·Coher. │
       └──────────────┬─────────┘
                      ▼
┌─────────────────────────────┐
│  Report Architect           │ ← block selection, section order
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Renderer                   │ ← HTML / Telegram / Markdown
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Watchlist Registry         │ ← signal DB + cron monitor
│         │                   │
│         └──signal fired──→  │ → Notify user w/ original link
└─────────────────────────────┘
```

### 3.2 핵심 책무 분리

| 컴포넌트 | 입력 | 출력 | 책무 한 줄 |
|----------|------|------|-----------|
| Intent Classifier | raw text | `user_intent` | 사용자가 무엇을 알고 싶은지 판별 |
| Strategy Planner | intent + raw text | `AnalysisStrategy` | 분석 전체 설계도 작성 |
| Quality Gate 1 | strategy | pass/fail | 계획이 실행 가능한가 |
| Evidence Collector | strategy | `Evidence[]` | 사실 수집 + 출처 신뢰도 평가 |
| Lens Runners | evidence + lens spec | `AnalyticalFinding[]` | 각 분석 렌즈로 결론 도출 |
| Synthesis Judge | findings | judgment + counter | 모순 *노출*, 종합 판단 |
| Quality Gate 2 | judgment | pass/fail | 커버리지·추적성·정합성 검증 |
| Report Architect | strategy + judgment | `AnalysisBlock[]` | 보고서 구조 조립 |
| Renderer | blocks | HTML/text | 출력 |
| Watchlist Registry | watch_signals | DB record + cron | 신호 모니터링 |

---

## 4. Data Model Specification

### 4.1 신규 모델 (전부 `src/models.py`에 추가)

```python
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


# ====== Strategy ======

UserIntent = Literal[
    "what_happened",       # 사실 파악
    "why_happened",        # 원인 분석
    "who_benefits",        # 이해관계 분석
    "where_spreads",       # 파급효과
    "what_next",           # 시나리오/전망
    "where_vulnerable",    # 취약점 분석
    "what_to_do",          # 의사결정
]


class EvidenceNeed(BaseModel):
    """수집해야 할 증거 명세."""
    need_id: str
    description: str
    expected_source_types: list[str]
    priority: Literal["P0", "P1", "P2"]


class ReportSectionPlan(BaseModel):
    """보고서 섹션 계획."""
    section_id: str
    title: str
    purpose: str  # 이 섹션이 답하려는 질문
    block_types: list[str]  # 사용할 블록 타입 ID 목록


class VisualizationSpec(BaseModel):
    visual_id: str
    visual_type: Literal["svg_relationship", "leaflet_map",
                         "canvas_chart", "mermaid_flow", "d3_custom"]
    purpose: str
    data_source: str  # 어느 finding/evidence에서 데이터를 가져올지


class AnalysisStrategy(BaseModel):
    """분석 전체 설계도. 기존 dict 방식 폐기."""
    event_type: str
    user_intent: UserIntent
    intent_confidence: float = Field(ge=0.0, le=1.0)
    multi_intent_secondary: list[UserIntent] = []  # 모호한 경우 보조 의도

    core_questions: list[str] = Field(min_length=1, max_length=7)
    recommended_lenses: list[str] = Field(min_length=1, max_length=4)
    evidence_plan: list[EvidenceNeed]
    report_archetype: str  # archetype_id
    section_plan: list[ReportSectionPlan]
    visualization_plan: list[VisualizationSpec]

    skip_agents: list[str] = []
    uncertainty_policy: Literal["aggressive", "moderate", "conservative"] = "moderate"
    theme: str = "burgundy"

    @model_validator(mode="after")
    def validate_lens_question_alignment(self):
        if len(self.core_questions) > 0 and len(self.recommended_lenses) == 0:
            raise ValueError("Core questions exist but no lenses recommended")
        return self


# ====== Claim & Evidence ======

ClaimType = Literal["fact", "inference", "prediction", "judgment"]
Reliability = Literal["primary", "secondary", "expert", "model_inference"]


class Evidence(BaseModel):
    """추적 가능한 증거 단위."""
    evidence_id: str  # "E-001"
    source_url: str
    quote_or_data: str  # 인용 또는 수치
    reliability: Reliability
    timestamp: str  # ISO 8601
    supports_claims: list[str]  # claim_id 역참조


class Claim(BaseModel):
    """주장 단위. 반드시 evidence를 1개 이상 가짐."""
    claim_id: str  # "C-001"
    statement: str
    claim_type: ClaimType
    evidence_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def must_have_evidence(self):
        if len(self.evidence_ids) == 0:
            raise ValueError(
                f"Claim {self.claim_id} requires at least one evidence_id. "
                f"This is a hard constraint."
            )
        return self


# ====== Confidence ======

class ConfidenceProfile(BaseModel):
    """단일 confidence_score 대체. 3축 분해."""
    source_diversity: float = Field(ge=0.0, le=1.0)  # 독립 출처 N개
    data_freshness: float = Field(ge=0.0, le=1.0)    # 가장 최근 데이터 시점
    expert_consensus: float = Field(ge=0.0, le=1.0)  # 의견 분기 정도

    @property
    def aggregate(self) -> float:
        """단일 점수가 필요할 때만 사용. 가중평균."""
        return (
            0.4 * self.source_diversity
            + 0.3 * self.data_freshness
            + 0.3 * self.expert_consensus
        )


# ====== Findings ======

class AnalyticalFinding(BaseModel):
    """렌즈가 산출하는 단위 결과."""
    finding_id: str
    lens_id: str
    answers_question: str  # core_question 중 어느 것에 답하는가
    main_claim: Claim
    supporting_findings: list[str] = []
    evidence: list[Evidence]
    confidence: ConfidenceProfile

    counter_hypothesis: str
    counter_required_evidence: list[str] = []  # 반대 가설이 옳다면 필요한 증거


class JudgmentVerdict(BaseModel):
    """Synthesis Judge의 종합 판단."""
    main_judgment: str
    base_scenario: str
    biggest_uncertainty: str
    contradictions: list[dict]  # [{lens_a, lens_b, conflict, resolution}]
    counter_hypothesis: str
    counter_evidence_needed: list[str]
    confidence: ConfidenceProfile


# ====== Watchlist ======

WatchDirection = Literal["confirms_base", "rejects_base", "ambiguous"]


class WatchSignal(BaseModel):
    signal_id: str
    description: str
    measurement: str  # "Brent crude > 95 USD"
    direction: WatchDirection
    deadline: date
    follow_up_action: str
    parent_report_url: str
    parent_report_id: str
    fired: bool = False
    fired_at: Optional[str] = None


# ====== Block Rendering ======

BlockType = Literal[
    "narrative",          # 산문 단락
    "claim_card",         # 주장 + 근거 카드
    "evidence_table",     # 증거 표
    "timeline",           # 시계열
    "matrix",             # 비교 매트릭스
    "actor_cards",        # 행위자 카드 (legacy player_card 대체)
    "flow_chain",         # 인과 사슬 (legacy chain_reaction 대체)
    "scenario_table",     # 시나리오 표
    "decomposition",      # 메커니즘 분해 (기술용)
    "argument_pair",      # ACH 가설 대결
    "data_series",        # 수치 시계열
    "watchlist",          # 감시 신호 그리드
    "qna",                # 흔한 질문 응답
    "callout",            # 강조 인용
    "counter_hypothesis", # 반대 가설 박스
    "decision_matrix",    # 의사결정 매트릭스
    "risk_matrix",        # 리스크 매트릭스
]


class AnalysisBlock(BaseModel):
    """보고서 렌더링의 기본 단위. 정적 매크로 대체."""
    block_id: str
    block_type: BlockType
    title: str
    purpose: str
    payload: dict  # 블록 타입별 자유 스키마
    related_findings: list[str] = []  # finding_id 참조
    section_id: str  # 어느 섹션에 속하는가
```

### 4.2 기존 모델 처리 (하위호환)

`src/models.py`의 기존 모델은 **삭제하지 않는다.** 다음 규칙을 따른다.

- `ContextAnalysis`, `PlayerAnalysis`, `DynamicsAnalysis`, `ChainReactionAnalysis`, `ScenariosAnalysis`, `VisualsAnalysis`: **유지**.
- `FullAnalysisResult`: 다음 Optional 필드 추가.
  ```python
  strategy: Optional[AnalysisStrategy] = None
  findings: list[AnalyticalFinding] = []
  blocks: list[AnalysisBlock] = []
  watch_signals: list[WatchSignal] = []
  judgment: Optional[JudgmentVerdict] = None
  ```
- `confidence_score: float`: **deprecated 마킹**, 즉시 삭제 금지. 신규 코드는 `ConfidenceProfile` 사용.

---

## 5. Migration Plan — 5 Steps

### Step 1: AnalysisStrategy 정식 모델 (1주, 무파괴)

**목표:** dict 기반 strategy를 Pydantic 모델로 전환. 하위호환 유지.

**파일 변경:**
| 작업 | 파일 |
|------|------|
| 신규 추가 | `src/models.py` (Section 4.1 모델 추가) |
| 수정 | `src/orchestrator.py:52-145` `_generate_analysis_strategy()` |

**구현 가이드:**
1. `AnalysisStrategy` 모델을 `src/models.py`에 추가.
2. `_generate_analysis_strategy()`의 프롬프트를 확장. 신규 필드 `core_questions`, `user_intent` 포함하게 한다.
3. `AnalysisStrategy.model_dump()` 결과가 기존 dict 키와 호환되도록 한다.
4. orchestrator는 내부적으로 `AnalysisStrategy` 객체를 들고 다닌다. 에이전트에 전달할 때만 `directive` 문자열을 추출.

**Acceptance Criteria:**
- [ ] `python -m py_compile src/models.py` 통과
- [ ] `python -m py_compile src/orchestrator.py` 통과
- [ ] 기존 텔레그램 봇 명령으로 보고서 1건 생성 → 회귀 없음
- [ ] 신규 strategy 객체는 `core_questions`가 1개 이상 포함됨 (실패 시 ValidationError)
- [ ] `user_intent` 분류 로그가 `DEVLOG.md`에 샘플로 1건 기록됨

**커밋:** `v2.5.0: AnalysisStrategy Pydantic 모델 승격, dict 호환 유지`

---

### Step 2: 보고서 아키타입 다중화 (1~2주)

**목표:** 6막 극장을 `archetype` 옵션으로 강등. 신규 archetype 2개 추가.

**파일 변경:**
| 작업 | 파일 |
|------|------|
| 신규 디렉토리 | `src/archetypes/` |
| 신규 | `src/archetypes/__init__.py` |
| 신규 | `src/archetypes/base.py` (Protocol 정의) |
| 신규 | `src/archetypes/six_act_theater.py` (현재 보고서 이전) |
| 신규 | `src/archetypes/financial_transmission.py` |
| 신규 | `src/archetypes/tech_decomposition.py` |
| 신규 | `src/archetypes/registry.py` |
| 수정 | `src/orchestrator.py` (strategy.report_archetype 분기) |

**구현 가이드:**
1. `ReportArchetype` Protocol 정의:
   ```python
   class ReportArchetype(Protocol):
       archetype_id: str
       name: str
       suitable_intents: list[UserIntent]
       suitable_event_types: list[str]

       def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]: ...
       def template_path(self) -> str: ...
   ```
2. `six_act_theater.py`는 현재 `report.html`을 그대로 가리킴.
3. `financial_transmission.py`, `tech_decomposition.py`는 자체 `section_plan()` 정의.
4. Strategy Planner의 프롬프트에 archetype 자동 선택 로직 추가 (Appendix B 매트릭스 참고).
5. archetype 선택 결과를 `AnalysisStrategy.report_archetype`에 저장.

**Acceptance Criteria:**
- [ ] `archetype="six_act_theater"`가 기본값일 때 기존 보고서와 동일 출력
- [ ] `archetype="financial_transmission"` 선택 시 신규 흐름 적용 (HTML은 Step 3에서 완성)
- [ ] Strategy Planner가 `user_intent`와 `event_type` 기반으로 archetype 자동 선택
- [ ] 모든 archetype은 `ReportArchetype` Protocol 구현
- [ ] `src/archetypes/registry.py`에 archetype_id로 객체 반환 함수 존재

**커밋:** `v2.6.0: 보고서 아키타입 다중화 + 6막 극장 archetype 강등`

---

### Step 3: 블록 렌더링 시스템 (2~3주)

**목표:** 매크로 4개를 블록 디스패처로 교체. 기존 템플릿과 공존.

**파일 변경:**
| 작업 | 파일 |
|------|------|
| 신규 | `src/templates/report_block.html` (블록 디스패처) |
| 신규 | `src/templates/blocks/*.html` (17개 블록 템플릿) |
| 수정 | `src/agents/report_synthesizer.py` (block list 생성) |
| 보존 | `src/templates/report.html` (six_act_theater 전용) |

**디스패처 패턴:**
```jinja2
{% for section in result.strategy.section_plan %}
<section id="{{ section.section_id }}">
  <div class="section-label">{{ section.purpose }}</div>
  <h2>{{ section.title }}</h2>
  {% for block in result.blocks if block.section_id == section.section_id %}
    {% include "blocks/" + block.block_type + ".html" %}
  {% endfor %}
</section>
{% endfor %}
```

**필수 17종 블록 (Appendix D 참조):**
- `narrative.html`, `claim_card.html`, `evidence_table.html`
- `timeline.html`, `matrix.html`, `actor_cards.html`
- `flow_chain.html`, `scenario_table.html`, `decomposition.html`
- `argument_pair.html`, `data_series.html`, `watchlist.html`
- `qna.html`, `callout.html`, `counter_hypothesis.html`
- `decision_matrix.html`, `risk_matrix.html`

**구현 가이드:**
1. 각 블록 템플릿은 50줄 이내. 단일 책임.
2. 블록 템플릿은 `block.payload`만 참조. 다른 모델 객체 직접 접근 금지.
3. CSS 클래스 명명: `block-{type}-{element}` (예: `block-claim-card-header`).
4. 기존 `report.css`의 디자인 토큰(`--text-primary`, `--blue` 등)은 그대로 재사용.

**Acceptance Criteria:**
- [ ] `archetype="six_act_theater"`인 경우 기존 보고서 변경 없음 (회귀 0건)
- [ ] `archetype="financial_transmission"`/`archetype="tech_decomposition"` 선택 시 블록 디스패처로 렌더링
- [ ] 새 블록 타입 추가가 새 파일 1개 추가로 가능 (`blocks/{new}.html`)
- [ ] 17종 블록 모두 샘플 데이터로 렌더링 테스트 통과

**커밋:** `v2.7.0: 블록 렌더링 시스템 도입, 매크로 1:1 결합 해소`

---

### Step 4: Quality Gate + Claim-Evidence 추적성 (3~4주)

**목표:** 단방향 파이프라인을 게이트 두 개로 검증. claim 단위 evidence 강제.

**파일 변경:**
| 작업 | 파일 |
|------|------|
| 신규 | `src/agents/quality_inspector.py` |
| 신규 | `src/agents/synthesis_judge.py` |
| 수정 | `src/orchestrator.py` (게이트 통합) |
| 수정 | `src/agents/*.py` (점진적으로 AnalyticalFinding 래핑) |

**Quality Gate 1 — Plan Sanity Check:**
- core_questions가 분석 가능한 형태인가 (LLM-as-judge로 검증)
- recommended_lenses가 user_intent와 정합하는가 (Appendix A 매트릭스)
- evidence_plan이 실행 가능한가 (각 EvidenceNeed에 expected_source_types 존재)

**Quality Gate 2 — Coverage·Trace·Coherence:**
- **Coverage:** 모든 core_question에 최소 1개 finding이 응답 (`finding.answers_question`)
- **Traceability:** 모든 claim에 evidence가 1개 이상 연결 (Pydantic validator로 강제)
- **Coherence:** 모순되는 finding에 대한 Synthesis Judge의 판정 존재

**재시도 정책:**
- 게이트 실패 시 최대 2회 재시도
- 재시도 시 실패 사유를 LLM에 피드백
- 2회 재시도 후에도 실패하면 텔레그램으로 "부분 분석" 알림 + 어느 게이트 실패인지 명시

**Synthesis Judge의 책무 (중요):**
- 모순을 *봉합*하지 않는다. 모순을 **드러내고 어느 쪽이 더 가능성 높은지 판정**한다.
- `JudgmentVerdict.contradictions`에 모든 모순 기록.
- `counter_hypothesis`와 `counter_evidence_needed`를 반드시 작성.

**Acceptance Criteria:**
- [ ] `quality_inspector.py`에 `gate_1_plan_sanity()`, `gate_2_coverage_check()` 함수 존재
- [ ] 게이트 통과율, 재시도율이 logger.info로 기록됨
- [ ] 인위적 실패 케이스(claim에 evidence 0개) 작성 시 ValidationError 발생
- [ ] Synthesis Judge가 최소 1개 모순 사례에서 판정 출력
- [ ] 텔레그램 부분 분석 알림 메시지 형식: `⚠️ 부분 분석: {gate} 실패 ({reason})`

**커밋:** `v2.8.0: Quality Gate 1/2 + claim-evidence 추적성 + Synthesis Judge`

---

### Step 5: Lens Runner Pool + Watchlist Registry (5주 이후)

**목표:** 7개 페르소나를 4개 기본 렌즈 + 사건별 추가 렌즈로 재구성. Watchlist 자동 모니터링.

**파일 변경:**
| 작업 | 파일 |
|------|------|
| 신규 디렉토리 | `src/lenses/` |
| 신규 | `src/lenses/__init__.py` |
| 신규 | `src/lenses/base.py` (LensRunner ABC) |
| 신규 | `src/lenses/geopolitical.py` |
| 신규 | `src/lenses/financial_transmission.py` |
| 신규 | `src/lenses/tech_architecture.py` |
| 신규 | `src/lenses/policy_implementation.py` |
| 신규 | `src/lenses/accident_causality.py` |
| 신규 | `src/lenses/market_structure.py` |
| 신규 | `src/lenses/registry.py` |
| 신규 디렉토리 | `src/watchlist/` |
| 신규 | `src/watchlist/registry.py` (SQLite 기반 추천) |
| 신규 | `src/watchlist/monitor.py` (cron 신호 확인) |
| 수정/Deprecated | `src/agents/player_analyst.py` 등 (Lens로 통합 또는 deprecated) |

**LensRunner 추상 인터페이스:**
```python
class LensRunner(ABC):
    lens_id: str
    name: str
    suitable_intents: list[UserIntent]
    suitable_event_types: list[str]
    method_steps: list[str]
    failure_modes: list[str]

    @abstractmethod
    async def run(
        self,
        evidence: list[Evidence],
        directive: str,
    ) -> list[AnalyticalFinding]:
        ...
```

**렌즈 실행 정책:**
- 사건당 렌즈 **최대 4개**로 제한 (토큰 비용 통제)
- Strategy Planner가 우선순위 1~4위만 `recommended_lenses`에 넣음
- Oracle Cloud 1GB VM 제약으로 **순차 실행 유지**
- 향후 Mac Mini 이전 시 병렬 실행 활성화 (FUT-001 참조)

**Watchlist Registry:**
- SQLite (`reports/watchlist.db`) 또는 Cloudflare KV
- 스키마: `WatchSignal` 모델 그대로 직렬화
- cron job: `python -m src.watchlist.monitor --interval 6h`
- 신호 발생 시 텔레그램 알림 형식:
  ```
  🔔 감시 신호 발생
  사건: {parent_report_title}
  신호: {description}
  방향: {direction}
  원 보고서: {parent_report_url}
  권장 후속: {follow_up_action}
  ```

**기존 에이전트 처리:**
- `ContextAnalyst` → 유지 (Evidence Collector로 역할 명확화)
- `VisualAnalyst` → 유지
- `ReportSynthesizer` → 유지 (Report Architect + Renderer 역할)
- `PlayerAnalyst` → `lenses/stakeholder_lens.py`로 이전 (legacy 6막 극장에서만 호출)
- `DynamicsAnalyst` → `lenses/structural_lens.py`로 이전
- `ChainReactionAnalyst` → `lenses/cascade_lens.py`로 이전
- `ScenarioArchitect` → 유지 (모든 archetype에서 watch_signals 생성 담당)

**Acceptance Criteria:**
- [ ] 6개 렌즈 모두 `LensRunner` 추상 구현
- [ ] 사건당 렌즈 4개 초과 호출 시 ValueError
- [ ] Synthesis Judge가 렌즈 간 모순 매트릭스 작성 (최소 1건 테스트 케이스)
- [ ] Watchlist 신호 등록 → cron 트리거 → 텔레그램 알림 end-to-end 동작
- [ ] Oracle Cloud 1GB VM에서 메모리 초과 없이 동작
- [ ] 토큰 사용량이 v2.4.0 대비 30% 이내 증가 (Step 5 완료 기준)
- [ ] DEVLOG.md에 v3.0.0 릴리스 노트 작성

**커밋:** `v3.0.0: Lens Runner Pool + Watchlist Registry + 페르소나 → 렌즈 재구성`

---

## 6. File Change Matrix (전체 요약)

| 파일/디렉토리 | 작업 | Step |
|---------------|------|------|
| `src/models.py` | 신규 모델 추가 (보존) | 1, 4, 5 |
| `src/orchestrator.py` | strategy 객체화, 게이트 통합 | 1, 2, 4, 5 |
| `src/archetypes/` | 신규 디렉토리 | 2 |
| `src/templates/blocks/` | 신규 디렉토리 (17개 템플릿) | 3 |
| `src/templates/report_block.html` | 신규 디스패처 | 3 |
| `src/templates/report.html` | 보존 (six_act_theater 전용) | 3 |
| `src/agents/quality_inspector.py` | 신규 | 4 |
| `src/agents/synthesis_judge.py` | 신규 | 4 |
| `src/lenses/` | 신규 디렉토리 | 5 |
| `src/watchlist/` | 신규 디렉토리 | 5 |
| `src/agents/player_analyst.py` | Lens로 이전 | 5 |
| `src/agents/dynamics_analyst.py` | Lens로 이전 | 5 |
| `src/agents/chain_reaction_analyst.py` | Lens로 이전 | 5 |
| `src/agents/scenario_architect.py` | 유지 (역할 재정의) | 5 |
| `src/agents/visual_analyst.py` | 유지 | — |
| `src/agents/context_analyst.py` | 유지 (Evidence Collector로 역할 명확화) | 5 |
| `src/templates/report.css` | 블록 클래스 추가 | 3 |
| `DEVLOG.md` | 단계별 갱신 | 매 Step |
| `GOAL.md` | 신규 요구사항 추가 (REQ-V3-*) | 1 |
| `CLAUDE.md` | 신규 규칙 반영 | 1 |
| `README.md` | 아키텍처 다이어그램 갱신 | 5 |

---

## 7. Validation Strategy

### 7.1 회귀 테스트 케이스 (각 Step 종료 시 실행)

| 케이스 | 입력 예시 | 기대 archetype | 기대 lens |
|--------|-----------|----------------|-----------|
| 짧은 사건 | "환율 어떻게 됨?" | `financial_transmission` | `market_structure` |
| 보통 사건 | "미중 무역 분쟁 현 상황" | `six_act_theater` 또는 `geopolitical_strategic` | `geopolitical`, `policy_implementation` |
| 복잡 사건 | "호르무즈 해협 위기 분석" | `geopolitical_strategic` | `geopolitical`, `financial_transmission`, `market_structure` |
| 기술 사건 | "GPT-5 출시" | `tech_decomposition` | `tech_architecture`, `market_structure` |
| 사고 사건 | "OO 공장 화재" | `accident_forensic` | `accident_causality` |
| 정책 사건 | "한국 부동산 규제 발표" | `policy_implementation` | `policy_implementation`, `financial_transmission` |

### 7.2 자동 검증

각 Step 종료 시 다음 명령으로 검증:
```bash
python -m py_compile src/**/*.py
python -m src.tests.regression  # 신규 테스트 모듈
```

### 7.3 수동 검증

- 텔레그램으로 회귀 테스트 케이스 6건 실행
- 생성된 HTML 보고서를 브라우저에서 확인
- DEVLOG.md에 각 케이스의 archetype/lens 선택 결과 기록

---

## 8. Critical Anti-Patterns (절대 하지 말 것)

다음 행동은 **절대** 하지 않는다. 발견 시 즉시 롤백.

1. ❌ **기존 7개 에이전트 일괄 삭제.** Step 5에서 점진적 이전.
2. ❌ **6막 극장 보고서 즉시 제거.** `archetype="six_act_theater"`로 영구 보존.
3. ❌ **AnalysisStrategy를 dict로 다시 떨어뜨리기.** 한 번 모델로 올린 후 dict로 회귀 금지.
4. ❌ **claim에 evidence 없이 통과시키기.** Pydantic validator를 우회하는 코드 금지.
5. ❌ **Synthesis Judge에서 모순을 봉합.** 모순은 *드러내야* 한다. 봉합은 보고서 품질 저하의 주범.
6. ❌ **렌즈 5개 이상 동시 실행.** 토큰 폭증 + 응집성 저하.
7. ❌ **Quality Gate 우회.** 게이트 통과 못 하면 부분 분석으로 알림. 우회 금지.
8. ❌ **블록 템플릿이 model 객체 직접 참조.** `block.payload`만 사용한다.
9. ❌ **`.format()` 사용.** 기존 규칙대로 `.replace()` 사용. JSON `{}` 충돌 방지.
10. ❌ **ConfidenceProfile 우회한 단일 스칼라 점수 신규 도입.** 신규 코드는 3축 분해 필수.
11. ❌ **Watchlist를 보고서 텍스트로만 남기기.** Step 5 이후 반드시 DB 등록.
12. ❌ **빅뱅 리팩토링.** 한 커밋에 여러 Step 섞지 않는다.

---

## Appendix A: User Intent → Lens 매트릭스

Strategy Planner가 user_intent를 결정한 후 lens 후보를 좁히는 데 사용한다.

| user_intent | 의미 | 권장 lens (top 3) | 권장 archetype 후보 |
|-------------|------|--------------------|----------------------|
| `what_happened` | 사실 파악 | `situation_board`, `evidence_chain` | `timeline_first` |
| `why_happened` | 원인 분석 | `root_cause`, `systems_dynamics`, `incentive_analysis` | `mechanism_decomp` |
| `who_benefits` | 이해관계 분석 | `stakeholder_map`, `power_leverage`, `geopolitical` | `actor_centric` |
| `where_spreads` | 파급효과 | `transmission_channel`, `cascade_map`, `network_analysis` | `financial_transmission` |
| `what_next` | 시나리오/전망 | `scenario_planning`, `bayesian_update`, `pre_mortem` | `scenario_first` |
| `where_vulnerable` | 취약점 분석 | `stress_test`, `fault_tree`, `bottleneck_analysis` | `accident_forensic`, `tech_decomposition` |
| `what_to_do` | 의사결정 | `decision_matrix`, `option_analysis`, `pre_mortem` | `decision_brief` |

---

## Appendix B: Report Archetype Catalog

각 archetype의 섹션 흐름. Strategy Planner가 user_intent와 event_type을 보고 선택한다.

| archetype_id | 적용 상황 | 섹션 흐름 |
|--------------|-----------|-----------|
| `six_act_theater` | 인물극형 사건 (전쟁, 외교, 정치 갈등) | ACT I 상황 → ACT II 행위자 → ACT III 구조 → ACT IV 인과 → ACT V 시나리오 → ACT VI 감시 신호 |
| `financial_transmission` | 시장/거시 사건 (환율, 금리, 자산 가격) | 가격 반응 → 포지션·자금흐름 → 전이 경로 → 취약 고리 → 스트레스 시나리오 → 관찰 지표 |
| `tech_decomposition` | 기술/AI/IT 사건 (모델 출시, 시스템 장애) | 문제 정의 → 시스템 구조 → 병목 → 성능·비용·리스크 → 대안 비교 → 실행 권고 |
| `geopolitical_strategic` | 지정학·전쟁 (군사 행동, 안보 위기) | 사건 요약 → 전장·행위자 → 의도와 능력 → 확전 경로 → 억제 요인 → 감시 신호 |
| `industry_value_chain` | 기업·산업 (M&A, 공급망, 경쟁 구도) | 산업 구조 → 가치사슬 → 경쟁 구도 → 수익성 압력 → 전략 옵션 → 의사결정 포인트 |
| `accident_forensic` | 사고·재난 (산업재해, 자연재해) | 사실 타임라인 → 직접 원인 → 방어막 실패 → 조직적 원인 → 재발 방지 → 미해결 질문 |
| `policy_implementation` | 정책·사회 (법안, 규제, 사회 변화) | 정책 의도 → 이해관계자 → 제약 조건 → 집행 가능성 → 부작용 → 수정안 |
| `decision_brief` | `what_to_do` 의도 | 판단 요약 → 옵션 비교 → 옵션별 리스크 → 권고 → Pre-mortem → 감시 신호 |
| `timeline_first` | `what_happened` 의도 | 핵심 요약 → 사실 타임라인 → 핵심 수치 → 출처 평가 → 미확인 사항 |
| `scenario_first` | `what_next` 의도 | 기준 시나리오 → 분기 시나리오 → 베이지안 업데이트 가이드 → 감시 신호 |
| `mechanism_decomp` | `why_happened` 의도 | 표층 현상 → 직접 원인 → 구조적 원인 → 제1원리 → 흔한 오해 → 정리 |

**모든 archetype의 마지막 섹션은 다음 두 블록을 강제 포함:**
- `counter_hypothesis` 블록 (반대 가설)
- `watchlist` 블록 (감시 신호 그리드)

이는 인식론적 정직성을 위한 비대칭적 강제 사항이다.

---

## Appendix C: Analysis Lens Library

| lens_id | 분야 | 핵심 기법 | 주요 출력 블록 |
|---------|------|-----------|----------------|
| `geopolitical` | 지정학 | DIME, PMESII, Escalation Ladder, Capability-Intent Matrix | `actor_cards`, `scenario_table`, `flow_chain` |
| `financial_transmission` | 금융·거시 | Balance Sheet Map, Flow of Funds, Transmission Channel, Liquidity Stress | `data_series`, `flow_chain`, `risk_matrix` |
| `tech_architecture` | 기술·AI | Architecture Decomposition, Dependency Graph, Bottleneck Analysis | `decomposition`, `matrix`, `data_series` |
| `policy_implementation` | 정책 | Stakeholder Incentive Map, Distributional Impact, Implementation Gap | `actor_cards`, `matrix`, `qna` |
| `accident_causality` | 사고·재난 | Fault Tree, Bow-Tie, Swiss Cheese, STAMP | `flow_chain`, `timeline`, `decomposition` |
| `market_structure` | 시장 | Network Analysis, Game Theory, Regime Shift Analysis | `matrix`, `scenario_table`, `data_series` |
| `red_team` | 메타 (반대 가설) | ACH, Pre-mortem, Devil's Advocate | `argument_pair`, `counter_hypothesis` |
| `pre_mortem` | 메타 (실패 시나리오) | Pre-mortem | `counter_hypothesis`, `risk_matrix` |

**렌즈 라이브러리 확장 규칙:**
- 신규 렌즈 추가 시 `LensRunner` ABC 구현 + `lenses/registry.py` 등록
- 각 렌즈는 `failure_modes` 명시 (이 렌즈를 쓰면 안 되는 경우)
- 새 렌즈 추가 시 GOAL.md에 `REQ-LENS-*` 추가

---

## Appendix D: Block Type Catalog

| block_type | 용도 | payload 스키마 (핵심 키) |
|------------|------|--------------------------|
| `narrative` | 산문 단락 | `text: str`, `tone: str` |
| `claim_card` | 주장 + 근거 카드 | `claim_id`, `statement`, `evidence_ids`, `confidence` |
| `evidence_table` | 증거 표 | `evidences: list[Evidence]` |
| `timeline` | 시계열 | `events: list[{date, event, impact}]` |
| `matrix` | 비교 매트릭스 | `rows: list[str]`, `cols: list[str]`, `cells: dict[(row,col), str]` |
| `actor_cards` | 행위자 카드 | `actors: list[{name, position, strategy, vulnerability, ...}]` |
| `flow_chain` | 인과 사슬 | `steps: list[{title, description, severity, affected}]` |
| `scenario_table` | 시나리오 표 | `scenarios: list[{name, description, probability, impact}]` |
| `decomposition` | 메커니즘 분해 | `root: str`, `branches: list[Node]` (재귀) |
| `argument_pair` | ACH 가설 대결 | `hypothesis_a`, `hypothesis_b`, `evidence_alignment: dict` |
| `data_series` | 수치 시계열 | `series: list[{label, points: list[(x,y)]}]`, `unit` |
| `watchlist` | 감시 신호 그리드 | `signals: list[WatchSignal]` |
| `qna` | 흔한 질문 응답 | `pairs: list[{q, a}]` |
| `callout` | 강조 인용 | `title`, `body`, `style: warning\|info\|insight` |
| `counter_hypothesis` | 반대 가설 박스 | `base_judgment`, `counter`, `required_evidence`, `current_conflict` |
| `decision_matrix` | 의사결정 매트릭스 | `options: list[str]`, `criteria: list[str]`, `scores: dict` |
| `risk_matrix` | 리스크 매트릭스 | `risks: list[{risk, probability, impact, mitigation}]` |

---

## Appendix E: Operating Rules (CLAUDE.md 보완)

기존 `CLAUDE.md`의 Execution Rules에 다음을 추가한다.

```
8. archetype/lens/block 추가 시 reg# istry에 반드시 등록
9. claim에 evidence 1개 이상 강제 (Pydantic validator)
10. Synthesis Judge는 모순을 봉합하지 않고 드러낸다
11. 렌즈는 사건당 최대 4개
12. Watchlist는 보고서 텍스트가 아닌 DB에 등록
13. ConfidenceProfile 3축 분해 사용. 단일 스칼라 신규 도입 금지
14. 모든 신규 모델 변경은 하위호환을 1릴리스 이상 유지
```

---

## Appendix F: Telegram UX 변경 사항

기존 인터페이스 보존. 단 다음 메시지 추가.

**의도 모호 시 (Multi-Intent Mode):**
```
🤔 질의가 다음 중 어느 것에 가까운지 모호함. 보조 의도까지 함께 분석함.
주의도: what_happened (현재 상황)
보조의도: what_next (향후 전망)
```

**부분 분석 알림 (게이트 실패 시):**
```
⚠️ 부분 분석 완료. {gate} 실패.
실패 사유: {reason}
완료된 분석: {completed_steps}
```

**Watchlist 알림:**
```
🔔 감시 신호 발생
사건: {parent_report_title}
신호: {description} → {direction}
원 보고서: {parent_report_url}
권장 후속: {follow_up_action}
```

---

## 9. Final Checklist Before v3.0.0 Release

- [ ] Step 1~5 모든 Acceptance Criteria 통과
- [ ] 회귀 테스트 6건 모두 통과
- [ ] DEVLOG.md에 v2.4.0 → v3.0.0 변경 사항 정리
- [ ] GOAL.md 업데이트 (REQ-V3-*, FUT-* 갱신)
- [ ] README.md 아키텍처 다이어그램 갱신
- [ ] CLAUDE.md Operating Rules 갱신
- [ ] WORKFLOWS.md 신규 흐름 반영
- [ ] 토큰 사용량 측정값 README에 갱신
- [ ] Cloudflare Pages 배포 정상
- [ ] Watchlist cron 동작 확인 (최소 1건 신호 발화)

---

## 10. Out of Scope (이번 리팩토링 이후 다룰 것)

다음은 v3.0.0 이후 별도 트랙에서 다룬다.

- 분석 결과의 사용자 평가 수집 (👍/👎 → 학습 루프)
- 보고서 품질 자동 평가 (LLM-as-judge)
- 다국어 지원
- Mac Mini 이전 시 병렬 렌즈 실행 (FUT-001)
- 분석 대기열 (FUT-003)
- Figma MCP 고급 시각화 (FUT-004)
- 보고서 에필로그 — 예측 검증 스코어카드 (FUT-005)

---

**End of V3 Refactoring Master Plan**

이 문서는 `agents_reviewer` 저장소 루트에 `REFACTOR_V3_PLAN.md`로 커밋되어야 한다.
실행 중 의문이 생기면 본 문서 Section 8 (Critical Anti-Patterns)부터 다시 읽는다.
