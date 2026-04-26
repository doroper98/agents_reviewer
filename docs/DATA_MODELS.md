---
tier: 2
last_synced_with: v2.7.0
ssot_for:
  - "Pydantic 모델 관계 도식 (필드 정의는 미러 아님)"
depends_on:
  - "src/models.py (필드 정의의 SSOT)"
last_review: 2026-04-26
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
                  (strategy + 6 analyses + blocks)
                         │
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

## 2. 모델 목록 (현재 v2.7.0)

| 모델 | 책무 | 정의 위치 |
|------|------|-----------|
| `AnalysisRequest` | 사용자 요청 (텔레그램 메시지 → 모델) | `src/models.py` |
| `AnalysisStrategy` | 분석 설계도 — user_intent, core_questions, recommended_lenses, skip_agents, theme, report_archetype, section_plan (V3 Step 1~3) | `src/models.py` |
| `EvidenceNeed` | Strategy 가 명세하는 증거 수집 항목 (V3 Step 1) | `src/models.py` |
| `ReportSectionPlan` | 보고서 섹션 계획 — archetype.section_plan() 산출, 디스패처가 iterate (V3 Step 3 활성화) | `src/models.py` |
| `VisualizationSpec` | 시각화 사양 — Visual Analyst 가 참조 | `src/models.py` |
| `BlockType` (Literal 17종) | 블록 타입 enum — narrative, claim_card, evidence_table, timeline, matrix, actor_cards, flow_chain, scenario_table, decomposition, argument_pair, data_series, watchlist, qna, callout, counter_hypothesis, decision_matrix, risk_matrix (V3 Step 3) | `src/models.py` |
| `AnalysisBlock` | 보고서 렌더링의 기본 단위 — block_id/block_type/payload (V3 Step 3) | `src/models.py` |
| `ContextAnalysis` | ACT I 결과 (팩트·타임라인·수치) | `src/models.py` |
| `PlayerAnalysis` | ACT II 결과 (행위자·동맹·power_dynamics) | `src/models.py` |
| `DynamicsAnalysis` | ACT III 결과 (비대칭·전환점·피드백 루프·반대 가설) | `src/models.py` |
| `ChainReactionAnalysis` | ACT IV 결과 (인과 사슬·차단점·와일드카드) | `src/models.py` |
| `ScenarioAnalysis` | ACT V+VI 결과 (시나리오·감시 신호·무효화 조건) | `src/models.py` |
| `VisualAnalysis` | 시각 요소 (SVG·Leaflet·Canvas) | `src/models.py` |
| `NarrativeSection` | 보고서의 단일 섹션 사양 (legacy six_act_theater 전용) | `src/models.py` |
| `NarrativePlan` | 섹션 순서·테마 (legacy six_act_theater 전용) | `src/models.py` |
| `FullAnalysisResult` | 모든 분석 결과 + 메타데이터 (`strategy`, `blocks` 포함) | `src/models.py` |

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
- `block_type`: 17종 `BlockType` Literal 중 하나.
- `title`: 블록 제목 (선택). 빈 문자열이면 템플릿이 생략.
- `purpose`: 이 블록이 답하려는 질문 또는 책무 — 보통 부모 `ReportSectionPlan.purpose` 와 동일.
- `payload`: 자유 dict. block_type 별 스키마는 [docs/CATALOGS.md §4](CATALOGS.md) 의 표 참조. **블록 템플릿이 접근 가능한 유일한 데이터** (Anti-pattern #8).
- `related_findings`: V3 Step 4+ Finding ID 역참조용 (현재는 빈 리스트).
- `section_id`: 디스패처가 `result.strategy.section_plan` 의 동일 ID 섹션과 매치.

블록 빌더 매핑 SSOT 는 `src/agents/report_synthesizer.py:_BLOCK_BUILDERS` 와 `_payload_*` 정적 메서드들. 빌더는 v2 분석 데이터 (`result.context`, `result.players` 등) 를 typed payload 로 변환하지만, 데이터 부재 시 `None` 반환 → 디스패처는 해당 블록을 생성하지 않음.

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
