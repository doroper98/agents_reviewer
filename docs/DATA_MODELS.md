---
tier: 2
last_synced_with: v4.2.0
ssot_for:
  - "Pydantic 모델 관계 도식 (필드 정의는 미러 아님)"
depends_on:
  - "src/models.py (필드 정의의 SSOT)"
last_review: 2026-05-02
---

# Data Models — Pydantic Schema Map

> **이 문서는 도식이다. 필드 정의는 `src/models.py` 가 SSOT.**
> 새 필드를 *정의*하지 않는다. 코드에 추가한 후 본 문서의 도식만 갱신한다 (Anti-pattern 9 회피).

---

## 1. 모델 관계도

```
                    AnalysisRequest
                         │
                         ▼
              ┌──────────────────────┐
              │  AnalysisStrategy    │ ← Strategy Planner 산출 (V3 Step 1, v2.5.0)
              │  - user_intent       │   user_intent / core_questions /
              │  - core_questions    │   recommended_lenses / report_archetype
              │  - recommended_lenses│   결정
              │  - report_archetype  │
              │  - section_plan      │ ← V3 Step 3 활성화 (archetype 이 채움)
              │  - skip_agents       │
              │  - legacy_directives │ ← Step 1 transitional shim (Step 5 제거 예정)
              └──────────┬───────────┘
                         ▼
                  Orchestrator pipeline
                         │
        ┌──────┬──────┬──┴───┬───────┬──────────┐
        ▼      ▼      ▼      ▼       ▼          ▼
   Context  Player Dynamics Chain  Scenario  Visual
   Analysis Analysis Analysis Reaction Analysis Analysis
        │      │      │      │       │          │
        └──────┴──────┴──┬───┴───────┴──────────┘
                         ▼
                  FullAnalysisResult
                  (strategy + 6 analyses + blocks + findings + judgment)
                         │
                         ├─ V3 Step 4 (v2.8.0) ──→ orchestrator._wrap_findings() ──→ list[AnalyticalFinding]
                         │                              │  (각 finding = main_claim(Claim, evidence_ids≥1)
                         │                              │   + evidence[Evidence] + ConfidenceProfile 3축
                         │                              │   + counter_hypothesis)
                         │                              ▼
                         │                  SynthesisJudge.judge(findings) ──→ JudgmentVerdict
                         │                              │  (contradictions 노출, 봉합 X — Anti-pattern #5)
                         │                              ▼
                         │                  QualityInspector.gate_2_coverage_check(strategy, findings, judgment)
                         │                              │  (실패 시 max 2 retry → "⚠️ 부분 분석 완료" 알림)
                         │                              ▼
                         ├─ archetype="six_act_theater" ──→ ReportSynthesizer (legacy report.html)
                         │
                         └─ 그 외 archetype ──→  _build_blocks(result, archetype)
                                                        │
                                                        ▼
                                            list[AnalysisBlock]
                                            (V3 Step 3 활성화)
                                            block_id / block_type / payload /
                                            section_id / related_findings
                                                        │
                                                        ▼
                                            ReportSynthesizer (report_block.html dispatcher)
                                                        │
                                                        ▼
                                            include "blocks/<block_type>.html"
                                            (17종 BlockType — 각 템플릿은
                                             block.payload 만 참조)
```

각 분석 모델은 `FullAnalysisResult` 의 optional 필드. `AnalysisStrategy` 도 optional 로 보존되어 보고서·로깅 단계에서 user_intent 를 추적할 수 있음. `NarrativePlan` 은 legacy six_act_theater 흐름 전용 — 신규 archetype 은 `result.strategy.section_plan` (`ReportSectionPlan` 배열) 이 디스패처의 iteration 대상.

---

## 2. 모델 목록 (현재 v2.9.5)

| 모델 | 책무 | 정의 위치 |
|------|------|-----------|
| `AnalysisRequest` | 사용자 요청 (텔레그램 메시지 → 모델) | `src/models.py` |
| `AnalysisStrategy` | 분석 설계도 — user_intent, core_questions, recommended_lenses, skip_agents, theme, report_archetype, section_plan (V3 Step 1~3) | `src/models.py` |
| `EvidenceNeed` | Strategy 가 명세하는 증거 수집 항목 (V3 Step 1) | `src/models.py` |
| `ReportSectionPlan` | 보고서 섹션 계획 — archetype.section_plan() 산출, 디스패처가 iterate (V3 Step 3 활성화) | `src/models.py` |
| `VisualizationSpec` | 시각화 사양 — Visual Analyst 가 참조 | `src/models.py` |
| `BlockType` (Literal 18종) | 블록 타입 enum — narrative, claim_card, evidence_table, timeline, matrix, actor_cards, flow_chain, scenario_table, decomposition, argument_pair, data_series, watchlist, qna, callout, counter_hypothesis, decision_matrix, risk_matrix (V3 Step 3) + `map` (v3.4.0 maplibre-gl + d3-geo) | `src/models.py` |
| `AnalysisBlock` | 보고서 렌더링의 기본 단위 — block_id/block_type/payload (V3 Step 3) | `src/models.py` |
| `ClaimType` (Literal) | fact / inference / prediction / judgment (V3 Step 4) | `src/models.py` |
| `Reliability` (Literal) | primary / secondary / expert / model_inference (V3 Step 4) | `src/models.py` |
| `Evidence` | 추적 가능한 증거 단위 — evidence_id/source_url/quote_or_data/reliability/timestamp (V3 Step 4) | `src/models.py` |
| `Claim` | 주장 단위 — evidence_ids ≥ 1 강제 (Pydantic validator, Anti-pattern #4) | `src/models.py` |
| `ConfidenceProfile` | 3축 분해 신뢰도 — source_diversity/data_freshness/expert_consensus + aggregate property (V3 Step 4, Anti-pattern #10) | `src/models.py` |
| `AnalyticalFinding` | 렌즈 단위 결과 — main_claim + evidence + confidence + counter_hypothesis (V3 Step 4) | `src/models.py` |
| `JudgmentVerdict` | Synthesis Judge 산출 — main_judgment / contradictions (봉합 금지, Anti-pattern #5) / counter_hypothesis (V3 Step 4) | `src/models.py` |
| `WatchDirection` (Literal) | confirms_base / rejects_base / ambiguous (V3 Step 5-B) | `src/models.py` |
| `WatchSignal` | 감시 신호 — signal_id / description / measurement / direction / deadline / parent_chat_id / fired / fired_at. `WatchlistRegistry` (SQLite) 에 영구 저장 (Anti-pattern #11) | `src/models.py` |
| `ContextAnalysis` | ACT I 결과 (팩트·타임라인·수치) | `src/models.py` |
| `PlayerAnalysis` | ACT II 결과 (행위자·동맹·power_dynamics) | `src/models.py` |
| `DynamicsAnalysis` | ACT III 결과 (비대칭·전환점·피드백 루프·반대 가설) | `src/models.py` |
| `ChainReactionAnalysis` | ACT IV 결과 (인과 사슬·차단점·와일드카드) | `src/models.py` |
| `ScenarioAnalysis` | ACT V+VI 결과 (시나리오·감시 신호·무효화 조건) | `src/models.py` |
| `VisualAnalysis` | 시각 요소 (SVG·Leaflet·Canvas) | `src/models.py` |
| `NarrativeSection` | 보고서의 단일 섹션 사양 (legacy six_act_theater 전용) | `src/models.py` |
| `NarrativePlan` | 섹션 순서·테마 (legacy six_act_theater 전용) | `src/models.py` |
| `ComposedSection` (v3.3.0~v4.2.0) | composer 가 작성한 1개 자유 섹션. heading / kicker / prose / **`charts: list[dict]` (v4.2.0 신설, inline 차트 데이터 — type/title/data/note)** / embedded_blocks / pull_quote / cited_claim_ids. legacy `embedded_charts: list[str]` (chart-id 참조) 는 v4.2.0 부터 의미 잃음. | `src/models.py` |
| `ComposedReport` (v3.3.0~v4.2.0) | UnifiedComposer (Opus 4.7) 단일 호출 산출. headline / deck / sections / closing **+ (v4.0.0) watch_signals + contradictions + confidence_summary + confidence_score + (v4.2.0) embedded_map**. v4.0.0 부터 `freeform_essay` 만 사용하므로 사실상 보고서 SSOT | `src/models.py` |
| `FullAnalysisResult` | 모든 분석 결과 + 메타데이터 (`strategy`, `blocks`, `composed_report` 포함) | `src/models.py` |

각 모델의 **현재 필드 목록**은 `src/models.py` 를 직접 읽는다 — 본 문서에 필드 사본을 두면 SSOT 위반이 된다.

---

## 3. 핵심 필드 의미 (분석 산출물 위주)

필드 *정의* 가 아니라, 필드의 *목적*을 사람의 언어로 풀어둔 가이드.

### 3.0 AnalysisStrategy (V3 Step 1, v2.5.0)
- `event_type`: 사건 유형 한 단어 (예: "trade_dispute", "war", "tech_launch").
- `user_intent`: 7종 Literal — 사용자가 가장 알고 싶어 하는 질문 유형. (`what_happened`, `why_happened`, `who_benefits`, `where_spreads`, `what_next`, `where_vulnerable`, `what_to_do`)
- `intent_confidence`: 0.0~1.0. intent 분류 확신도.
- `multi_intent_secondary`: 모호한 경우의 보조 intent 목록.
- `core_questions`: 1~7개. 이 사건이 답해야 할 핵심 질문들. *반드시 1개 이상* (Pydantic `min_length=1`).
- `recommended_lenses`: 1~4개. 적용할 분석 렌즈 ID 목록. `core_questions` 가 비어 있지 않은데 비면 ValidationError (`validate_lens_question_alignment`).
- `evidence_plan`: `EvidenceNeed` 배열. 수집해야 할 증거 명세.
- `report_archetype`: 보고서 아키타입 ID. 현재는 `"six_act_theater"` 만 사용. Step 2 에서 다중화.
- `section_plan`: `ReportSectionPlan` 배열. Step 3 블록 시스템에서 본격 활용.
- `visualization_plan`: `VisualizationSpec` 배열.
- `skip_agents`: 스킵할 에이전트 이름 목록. v2 dict 호환을 위해 alias `"skip"` 보유.
- `uncertainty_policy`: `aggressive | moderate | conservative` (기본 `moderate`).
- `theme`: 보고서 테마. `burgundy | geopolitical | financial | tech | nature | liquidglass` (기본 `burgundy`).
- `legacy_directives`: **Step 1 한정 transitional shim**. v2 의 dict 기반 per-agent directive 문자열을 보존. Step 5 lens pool 도입 시 제거됨. 신규 코드는 `recommended_lenses` 를 사용할 것.

### 3.1 ContextAnalysis
- `timeline`: 날짜/사건/영향 트리오. 보고서 ACT I 의 타임라인 카드로 렌더.
- `key_figures`: label / value / context 트리오. 핵심 수치 카드.
- `background`: 배경 단락 (다단락 가능, `structured` 필터 처리).
- `glossary`: 용어 풀이. 보고서 말미.

### 3.2 PlayerAnalysis
- `players`: 각 항목은 name / role_tag / risk_level / position / strategy / vulnerability / timeline_pressure 키를 가진 dict.
- `alliances`: group(이름 배열) / nature(동맹/대립/협력 등).
- `power_dynamics`: 전체 권력 역학 요약 (서술형).

### 3.3 DynamicsAnalysis
- `framework`: 사용한 분석 시각의 조합 (예: "게임이론 + 경로 의존성 + 행동경제학").
- `asymmetries`: type / description / advantage_to.
- `feedback_loops`: type(강화|균형) / description.
- `tipping_points`: condition / timeline / consequence.
- `counter_view`: 반대 가설 또는 대안 해석.
- `cognitive_biases`: 분석 시 경계할 인지 편향 목록.

### 3.4 ChainReactionAnalysis
- `chain`: step / title / description / affected / time_horizon / effect_type / reversible / severity.
- `feedback_loops`: 사슬 안에서 자기강화·억제 구조.
- `break_points`: at_step / condition (사슬을 끊을 수 있는 지점).
- `wildcards`: 예측 어려운 흑조 사건.

### 3.5 ScenarioAnalysis
- `scenarios`: id / name / tag / probability / description / preconditions / trigger / impact_by_player.
- `watch_signals`: signal / description / indicates / icon.
- `invalidation_conditions`: 분석 자체를 다시 해야 하는 조건.
- `summary`: 균형 분석 본문 (4단락: 핵심 판단 / 상하방 비대칭 / 변수 민감도 / 한계와 유보).

### 3.6 NarrativePlan
- `report_theme`: 핵심 서사 한 문장.
- `sections`: NarrativeSection 배열. 각 섹션은 act_label / title / data_source / narrative_bridge / subsections 보유.
- **Scope**: legacy `six_act_theater` archetype 전용. 신규 archetype 은 `AnalysisStrategy.section_plan` 사용.

### 3.7 AnalysisBlock (V3 Step 3, v2.7.0)
- `block_id`: 보고서 내 고유 ID (예: `B-001`). 디스패처가 자동 생성.
- `block_type`: 18종 `BlockType` Literal 중 하나 (v3.4.0 부터 `map` 포함).
- `title`: 블록 제목 (선택). 빈 문자열이면 템플릿이 생략.
- `purpose`: 이 블록이 답하려는 질문 또는 책무 — 보통 부모 `ReportSectionPlan.purpose` 와 동일.
- `payload`: 자유 dict. block_type 별 스키마는 [docs/CATALOGS.md §4](CATALOGS.md) 의 표 참조. **블록 템플릿이 접근 가능한 유일한 데이터** (Anti-pattern #8).
- `related_findings`: V3 Step 4+ Finding ID 역참조용 (현재는 빈 리스트).
- `section_id`: 디스패처가 `result.strategy.section_plan` 의 동일 ID 섹션과 매치.

블록 빌더 매핑 SSOT 는 `src/agents/report_synthesizer.py:_BLOCK_BUILDERS` 와 `_payload_*` 정적 메서드들. 빌더는 v2 분석 데이터 (`result.context`, `result.players` 등) 를 typed payload 로 변환하지만, 데이터 부재 시 `None` 반환 → 디스패처는 해당 블록을 생성하지 않음.

### 3.8 Evidence (V3 Step 4, v2.8.0)
- `evidence_id`: 보고서 내 고유 ID (예: `E-001`, `E-INF-001` for model-inference fallback).
- `source_url`: 1차 출처 URL — 비어있으면 `quote_or_data` 가 자체 텍스트.
- `quote_or_data`: 인용 또는 수치. 출처가 없는 model_inference 의 경우 추론 근거 텍스트.
- `reliability`: `primary` / `secondary` / `expert` / `model_inference` 중 하나.
- `timestamp`: ISO 8601 형식 (또는 분석 시점 날짜).
- `supports_claims`: 이 evidence 가 뒷받침하는 claim_id 역참조 목록.

### 3.9 Claim (V3 Step 4, v2.8.0 — Anti-pattern #4 강제)
- `claim_id`: 고유 ID (예: `C-001`, `C-context_analyst-001`).
- `statement`: 주장 내용 (≤ 500자 권장).
- `claim_type`: `fact` / `inference` / `prediction` / `judgment`.
- `evidence_ids`: **min_length=1 강제**. 빈 리스트로 Claim 인스턴스 생성 시 ValidationError. `must_have_evidence` model_validator 가 이중 가드.

### 3.10 ConfidenceProfile (V3 Step 4, v2.8.0 — Anti-pattern #10 회피)
- 단일 스칼라 `confidence_score` 의 대체 모델. 기존 `confidence_score: float` 필드들은 호환 목적으로 보존되나 deprecated.
- 3축 (각 0.0~1.0):
  - `source_diversity`: 독립 출처 다양성 (출처 1개 → 0.2, 5개 이상 → 1.0 휴리스틱).
  - `data_freshness`: 데이터 시점의 최신성 (web search 기반 분석은 보통 0.7).
  - `expert_consensus`: 전문가 의견 수렴도 (모순 1건당 0.1 차감).
- `aggregate` (property): 가중 평균 `0.4·source_diversity + 0.3·data_freshness + 0.3·expert_consensus`. 단일 점수가 강제로 필요한 좁은 곳에서만 사용.

### 3.11 AnalyticalFinding (V3 Step 4, v2.8.0)
- `finding_id`: 고유 ID (예: `F-context_analyst-001`).
- `lens_id`: 산출 렌즈 ID (현재는 v2 에이전트 이름. Step 5 에서 lens registry 의 ID 로).
- `answers_question`: `strategy.core_questions` 중 어느 것에 답하는가.
- `main_claim`: 이 finding 의 핵심 주장 (Claim, evidence 1개 이상 강제).
- `supporting_findings`: 다른 finding ID 참조 (보조 근거).
- `evidence`: Evidence 리스트. main_claim 의 evidence_ids 가 여기 포함되어야 (gate_2 검증).
- `confidence`: ConfidenceProfile 3축.
- `counter_hypothesis`: 본 결론의 반대 가설 텍스트.
- `counter_required_evidence`: 반대 가설이 옳다면 추가로 필요한 증거 목록.

### 3.12 JudgmentVerdict (V3 Step 4, v2.8.0 — Anti-pattern #5 회피)
- Synthesis Judge 의 종합 판단. **모순을 봉합하지 않고 `contradictions` 필드에 노출**.
- `main_judgment`: 종합 판단 1~2 문장. 모순 발견 시 *어느 쪽 채택했는지* 명시.
- `base_scenario`: 기준 시나리오 1 문장.
- `biggest_uncertainty`: 가장 큰 불확실성 1 문장.
- `contradictions`: `[{lens_a, lens_b, conflict, resolution}]` 배열. 빈 배열은 "모순 없음을 명시" — 봉합과는 다름.
- `counter_hypothesis`: 종합 차원의 반대 가설.
- `counter_evidence_needed`: 반대 가설이 옳다면 필요한 증거 목록.
- `confidence`: ConfidenceProfile (finding 평균 - 모순 페널티).

### 3.13 WatchSignal (V3 Step 5-B, v2.9.5 — Anti-pattern #11 회피)
- `signal_id`: deterministic hash 기반 (`WS-YYYYMMDD-<8hex>`) — 같은 보고서 + 같은 신호 텍스트면 같은 ID 생성 (idempotent register).
- `description`: 감시 대상 신호 (예: "DXY 105 돌파").
- `measurement`: 측정 방식·기준 (예: "DXY 일봉 종가").
- `direction`: `confirms_base` / `rejects_base` / `ambiguous`. `convert_watch_signals()` 가 indicates 텍스트 어휘 (위험·악화·확정·지속 등) 로 휴리스틱 추정.
- `deadline`: ISO 8601 date "YYYY-MM-DD". `convert_watch_signals` 의 default = today + 30일.
- `follow_up_action`: 발화 시 권장 조치 텍스트.
- `parent_report_url`, `parent_report_id`: 원 보고서 식별. 알림 본문에 노출.
- `parent_chat_id`: 알림 송신 대상 텔레그램 chat_id (B 보강 결정 — 다중 사용자 지원의 첫 단계).
- `fired`, `fired_at`: 발화 상태 + 시각 (ISO 8601 datetime).
- 정의 SSOT 는 `src/models.py`. SQLite 영구 저장은 `src/watchlist/registry.py:WatchlistRegistry`.

---

## 4. 모델 변경 시 동시 갱신해야 할 곳

[CLAUDE.md](../CLAUDE.md) Change Propagation 매트릭스의 "src/models.py 변경" 행 참조. 핵심:

1. `src/models.py` 정의 갱신 (코드 SSOT)
2. 본 문서 §2 `모델 목록` 표 + §3 의미 가이드 갱신
3. 영향받는 에이전트의 system prompt JSON 스키마 갱신
4. 보고서 템플릿 (`src/templates/report.html`) 의 렌더링 부분 갱신
5. `DEVLOG.md` 에 변경 기록

V3 후에는 추가로:
- `docs/CATALOGS.md` 의 BlockType 표 갱신 (BlockType 변경 시)

---

## 5. Out of scope

- 필드의 정확한 타입·기본값 → `src/models.py` 직접 읽기
- 모델 인스턴스의 직렬화 형식 → Pydantic 의 `model_dump()` / `model_validate_json()` 동작 (코드)
- 에이전트가 어떤 시스템 프롬프트로 어떤 모델을 채우는지 → `src/agents/<name>.py` 의 SYSTEM_PROMPT
