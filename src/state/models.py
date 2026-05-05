"""V5 Phase 0C — 6-tier State 모델 정의 SSOT.

Plan §4.3 의 모델 정의를 *byte-equal* 로 따른다. 본 모듈은 *데이터 계약*
만 책임지며 변환 / guard 는 별도 모듈 (compaction.py / guards.py).

각 tier 의 책임:
    1. RawContext       — 원문, 검색결과, 출처. ContextAnalyst 가 *입력으로*
                          받고 *출력은* EvidencePack 으로 압축.
    2. EvidencePack     — ContextAnalyst 의 *압축 출력*. claims + actors +
                          timeline + contradictions. 후속 단계가 받는 *유일한*
                          사실 자료 (RawContext 는 후속 단계에서 못 봄).
    3. AnalysisBrief    — ResearchDirector (Phase 1A) 출력. 보고서의 분석
                          설계도. Composer 의 *전체 결정 도메인을 좁힘*.
    4. DraftReport      — Composer (drafting) 출력. prose 만 책임.
                          Editor 가 받는다 (RawContext / EvidencePack 미입력).
    5. ExhibitPack      — VisualPlanner (Phase 2) 출력. EvidenceDataset 별
                          chart spec + layout 결정.
    6. PublishManifest  — Renderer 출력. rendered HTML path + screenshots +
                          chart_gate_results. DeskEditor 가 받는다.

src/models.py 의 *기존* 모델과 분리 — src/models.py 는 v4.5.7 의 ComposedReport
계열 SSOT. src/state/models.py 는 V5 의 6-tier State SSOT. 둘은 별개로 유지하되
변환 함수가 가교 (compaction.py).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ─── 공통 leaf 모델 ────────────────────────────────────────────────────


class RawSource(BaseModel):
    """ContextAnalyst 가 본 1차 / 2차 출처 1건."""

    url: str = ""
    title: str = ""
    publisher: str = ""
    published_at: str = ""           # ISO 8601 또는 자유 텍스트
    accessed_at: str = ""
    raw_text: str = ""               # 원문 (요약 X). EvidencePack 으로 압축 시 quote/data 만.
    reliability: Literal["primary", "secondary", "expert", "model_inference"] = "secondary"


class SearchHit(BaseModel):
    """WebSearch / WebFetch 가 반환한 검색 결과 1건."""

    query: str = ""
    title: str = ""
    url: str = ""
    snippet: str = ""


class Claim(BaseModel):
    """EvidencePack 안의 1개 주장. source_id ≥ 1 강제."""

    claim_id: str = ""
    statement: str
    source_ids: list[str] = Field(default_factory=list, min_length=1)
    quote_or_data: str = ""
    timestamp: str = ""
    reliability: Literal["primary", "secondary", "expert", "model_inference"] = "secondary"

    model_config = ConfigDict(extra="forbid")


class Actor(BaseModel):
    """행위자 1명/그룹의 압축 표현. EvidencePack 의 actors 배열 원소."""

    actor_id: str = ""
    name: str
    role_tag: str = ""               # "정부", "기업", "분석가" 등 짧은 라벨
    one_line_summary: str = ""       # 5~10개 행위자 한 줄 요약 (Plan §4.3 actors_summary 의 입력)


class TimelineEvent(BaseModel):
    """EvidencePack.timeline 의 1개 이벤트."""

    when: str = ""                   # 날짜 또는 자유 텍스트
    what: str = ""                   # 사건 한 줄
    impact: str = ""                 # 영향 1~2 문장
    source_ids: list[str] = Field(default_factory=list)


class Contradiction(BaseModel):
    """EvidencePack 안에서 발견된 출처 / 입장 모순. Anti-pattern #5 — 봉합 X."""

    side_a: str
    side_b: str
    evidence: str = ""
    resolution: str = ""             # 채택 측 명시 (단 패배자는 counter_hypothesis 로 보존)


# ─── Tier 1 — RawContext ───────────────────────────────────────────────


class RawContext(BaseModel):
    """1단계 — 원문 + 검색결과 + 사용자 요청.

    ContextAnalyst 만 입력으로 받고 *후속 단계는 보지 못한다*. raw_sources 는
    Plan §4.2 의 ~50KB 짜리 raw 텍스트가 핵심. token compounding 차단의 1차 가드.
    """

    user_request: str
    raw_sources: list[RawSource] = Field(default_factory=list)
    search_results: list[SearchHit] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ─── Tier 2 — EvidencePack ─────────────────────────────────────────────


class EvidencePack(BaseModel):
    """2단계 — ContextAnalyst 의 압축 출력.

    Plan §4.3 의 정의. 후속 모든 단계 (Composer / Editor / VisualPlanner /
    DeskEditor) 가 받는 *유일한 사실 자료*. RawContext 는 폐기 (후속 단계 진입 시
    객체 자체가 전달되지 않음 — guard 가 검증).
    """

    claims: list[Claim] = Field(default_factory=list)
    actors: list[Actor] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    # source_id → URL 룩업 (claims.source_ids 가 가리키는 곳).
    source_index: dict[str, str] = Field(default_factory=dict)
    # 사건 카테고리 — select_theme() 의 입력.
    category: str = ""
    # ContextAnalyst 가 추천한 페르소나 (v4.3.0 보존).
    recommended_persona: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


# ─── Tier 3 — AnalysisBrief (Phase 1A 산출, Phase 0C 에선 *형식만* 정의) ─


class AnalysisMethod(BaseModel):
    """ResearchDirector 가 선택한 분석기법 1종 (Plan §6.3 의 9종 enum)."""

    method: Literal[
        "ACH",
        "scenario_tree",
        "transmission_channel",
        "stakeholder_matrix",
        "fault_tree",
        "decision_matrix",
        "pre_mortem",
        "transmission_timeline",
        "comparative",
    ]
    why_this_method: str = ""        # 1~2문장 정당화
    required_evidence: list[str] = Field(default_factory=list)
    forbidden_visuals: list[str] = Field(default_factory=list)
    required_exhibits: list[str] = Field(default_factory=list)


class ReportShape(BaseModel):
    """보고서 형태 결정 — 섹션 수 / peak / 필수 섹션."""

    section_count: int = 4           # 3~7
    peak_section: int = 0            # 0-indexed
    must_have_sections: list[str] = Field(default_factory=list)
    optional_sections: list[str] = Field(default_factory=list)


class VisualConstraints(BaseModel):
    """시각화 제약 — must_have / allowed / forbidden."""

    must_have: list[str] = Field(default_factory=list)
    allowed: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class KeyNumber(BaseModel):
    """Composer prose 가 인용할 수 있는 핵심 숫자."""

    label: str
    value: str
    unit: str = ""
    source_id: str = ""              # EvidencePack.source_index 의 키


class AnalysisBrief(BaseModel):
    """3단계 — ResearchDirector (Phase 1A) 의 출력. Composer 가 받는다.

    Phase 0C 시점엔 *형식만* 정의. 실제 채워지는 시점은 Phase 1A 진입 후.
    """

    thesis: str = ""
    primary_question: str = ""
    secondary_questions: list[str] = Field(default_factory=list)
    selected_methods: list[AnalysisMethod] = Field(default_factory=list)
    report_shape: ReportShape = Field(default_factory=ReportShape)
    visual_constraints: VisualConstraints = Field(default_factory=VisualConstraints)
    key_numbers: list[KeyNumber] = Field(default_factory=list)
    actors_summary: list[str] = Field(default_factory=list)
    # Phase 8 라우팅 신호.
    strategic_hint: bool = False
    # Phase 1A 가 ContextAnalyst 의 recommended_persona 를 직접 사용 시
    # AnalysisBrief 로 함께 전달.
    recommended_persona: dict = Field(default_factory=dict)
    # 보고서 모드 (analytical / strategic 의 V5 분기).
    report_mode: Literal[
        "situation", "forecast", "strategy", "technical", "market", "policy",
    ] = "situation"


# ─── Tier 4 — DraftReport ─────────────────────────────────────────────


class DraftReport(BaseModel):
    """4단계 — Composer 출력. Editor 가 받는다.

    EvidencePack / RawContext 를 *다시 보지 않는다*. Plan §4.4 의 입력 제한.
    Phase 0C 시점엔 src.models.ComposedReport 가 사실상 동일 역할 — Phase 1
    (Editor Pass) 진입 시 ComposedReport 와 분리.
    """

    headline: str = ""
    deck: str = ""
    sections: list[dict] = Field(default_factory=list)  # ComposedSection 호환 dict
    closing: str = ""

    model_config = ConfigDict(extra="forbid")


# ─── Tier 5 — ExhibitPack (Phase 2 / Phase 4 의 입력) ──────────────────


class DatasetField(BaseModel):
    """EvidenceDataset.fields 의 1개 필드 정의 (Plan §8.3).

    semantic_type 은 차트 type 적합도 검증의 입력 — Phase 6 ChartCritic 의 sanity
    check 가 사용. 예: time / quantity 의 조합은 line 차트 적합, geo 면 choropleth.
    """

    name: str
    semantic_type: Literal[
        "time", "category", "geo", "quantity", "ratio", "score", "text",
    ]
    unit: str = ""                   # "USD", "%", "건" 등 — 비어 있어도 허용 (text/category 등)
    nullable: bool = False

    model_config = ConfigDict(extra="forbid")


class TransformStep(BaseModel):
    """raw → 차트 데이터의 변환 1단계. Plan §8.3 — 감사 추적용."""

    operation: str                   # "filter", "groupby", "normalize", "interpolate" 등
    description: str                 # 사람이 읽을 수 있는 설명 1~2문장
    input_fields: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class EvidenceDataset(BaseModel):
    """차트가 입력으로 받는 *유일한* 데이터 형태 (Plan §8.3 — Phase 2A SSOT).

    Phase 0C 에선 *형식 stub* 으로 정의. Phase 2A 부터 본격 활성:
    - source_ids ≥ 1 강제 (AP-V5-25)
    - DatasetField 로 fields 강화 (semantic_type 명시)
    - TransformStep 로 transforms 추적 가능 (Plan §8.7 인수 기준 #4)

    실제 검증 (Plan §8.5 의 3개 금지 행위) 은 src/visual/evidence_dataset.py
    의 EvidenceDatasetGuard 가 담당.
    """

    dataset_id: str                  # 보고서 안에서 unique
    title: str = ""
    source_ids: list[str] = Field(default_factory=list, min_length=1)
    rows: list[dict] = Field(default_factory=list)
    fields: list[DatasetField] = Field(default_factory=list)
    transforms: list[TransformStep] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    suitable_visuals: list[str] = Field(default_factory=list)
    forbidden_visuals: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ExhibitPack(BaseModel):
    """5단계 — VisualPlanner 출력. Renderer 가 받는다 (Plan §4.3)."""

    datasets: list[EvidenceDataset] = Field(default_factory=list)
    chart_specs: list[dict] = Field(default_factory=list)   # Vega-Lite spec (Phase 2)
    layouts: list[dict] = Field(default_factory=list)       # LayoutAssignment (Phase 3)


# ─── Tier 6 — PublishManifest ─────────────────────────────────────────


class ScreenshotCapture(BaseModel):
    """Playwright 캡쳐 1장 (Plan §8.2)."""

    role: Literal["desktop_full", "mobile_full", "chart_closeup", "map_closeup"] = "desktop_full"
    image_b64: str = ""
    label: str = ""
    width: int = 0
    height: int = 0


class PublishManifest(BaseModel):
    """6단계 — Renderer 출력. DeskEditor 가 받는다 (Plan §4.3).

    rendered HTML path + screenshots + chart_gate_results + 선검사 결과.
    DeskEditor 는 RawContext / EvidencePack 의 *원문* 을 보지 못함.
    """

    rendered_html_path: str = ""
    screenshots: list[ScreenshotCapture] = Field(default_factory=list)
    chart_gate_results: dict = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)         # Phase 7A deterministic gate 결과
    soft_fail_signals: list[str] = Field(default_factory=list)
