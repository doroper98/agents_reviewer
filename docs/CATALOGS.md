---
tier: 2
last_synced_with: v8.5.1
ssot_for:
  - "에이전트 카탈로그 (mirror of src/agents/*)"
  - "Mode 별 정책 (mirror of src/token_budget.py)"
  - "Composer chart type 카탈로그 (mirror of narrative_composer.py SYSTEM_PROMPT + charts.js RENDERERS)"
depends_on:
  - "src/agents/{context_analyst, narrative_composer}.py (살아있는 2개)"
  - "src/token_budget.py (mode 정책 SSOT)"
  - "src/agents/narrative_composer.py:MAX_TOKENS_BY_MODE (v4.5.4)"
  - "src/lens_policy.py:select_theme (테마 결정)"
  - "src/templates/static/charts.js (d3 렌더 SSOT)"
last_review: 2026-05-18
---

# Catalogs — Agents · Charts · Maps (v4.5.7)

> 본 문서는 **카탈로그 미러**다. 정의는 코드에서만, 문서는 사람이 읽기 쉬운 형태로 동기화한 사본일 뿐이다.
>
> **v4.0.0 Tier 4 부터** legacy 멀티 에이전트 (player/dynamics/chain/scenario/visual/judge/inspector) + 11종 lens pool + 11종 archetype matrix + 17종 BlockType 은 **호출 안 됨**. 본 문서의 해당 섹션은 *역사적 참고용*. 운영 중인 카탈로그는 §1 (에이전트 2개) + §5 (차트 type 8종) + §6 (지도 시스템) 뿐.
> 카탈로그를 *정의*하지 않는다. 카탈로그는 코드 registry 가 SSOT.

---

## 1. Agents — 현재 (v4.5.7)

> **v4.5.7 호출 경로의 *실제* 에이전트 2개:** ContextAnalyst (#1 아래 표) + NarrativeComposer (#10 아래 표). 그 외 (#2~#9) 는 v4.0.0 부터 호출되지 않음 — 모듈 보존만.
>
> **V5 Phase 1A (현재 opt-in)** — `ResearchDirector` (`src/agents/research_director.py`) 가 추가됨. `Config.enable_research_director=True` (env `V5_RESEARCH_DIRECTOR=1`) 일 때 ContextAnalyst 직후에 호출되어 `AnalysisBrief` (분석 설계도) 를 emit. 디폴트 OFF — v4.5.7 호출 경로 byte-equal 보존. 9종 method enum SSOT: [docs/RESEARCH_DIRECTOR_METHODS.md](RESEARCH_DIRECTOR_METHODS.md).
>
> **V6 Phase V6-1 (현재 opt-in, spike)** — `CodexCritic` (`src/agents/codex_critic.py`) 가 추가됨. `Config.enable_codex_critic=True` (env `V6_CODEX_CRITIC=1`) 일 때만 동작하는 *외부 fact critic* — codex CLI(ChatGPT 구독)를 headless 호출해 `ComposedReport` 를 사실 검수하고 `FactVerdict` 를 emit. **본문은 쓰지 않는다** (검수·지시만, 보완은 Opus, AP-V6-1/11). 외부 실패는 graceful degrade (`FactVerdict.skip`) → 단일패스 (AP-V6-12). 디폴트 OFF — v5.8.8 byte-equal. Phase V6-1 단계에선 orchestrator 가 *호출하지 않음* (계약·degrade spike). 루프 통합은 Phase V6-3. SSOT: [REFACTOR_V6_PLAN.md §3](../REFACTOR_V6_PLAN.md).
>
> **V6 Phase V6-3 (루프 연결)** — `src/factcheck/critic_loop.py:CriticLoop` 이 `Opus 작성 → Codex 검수 → Opus 보완(≤1) → Codex 확인패스(≤1)` 를 orchestrator Phase 2.5 (flag `V6_CODEX_CRITIC`) 로 돌린다. 보완은 `NarrativeComposer.revise_for_facts` (Opus 고정, 본문만 텍스트-only 재작성 후 코드가 차트/이미지/신호 merge 보존, AP-V6-1/11). 루프 제어는 0-LLM (Codex 위반 카운트). flag OFF = byte-equal.
>
> | # | 에이전트 | 파일 | 활성 |
> |---|---------|------|------|
> | 1 | ContextAnalyst | `src/agents/context_analyst.py` | ✅ 항상 |
> | — | **ResearchDirector (V5 Phase 1A)** | `src/agents/research_director.py` | opt-in (`V5_RESEARCH_DIRECTOR=1`) |
> | 10 | NarrativeComposer | `src/agents/narrative_composer.py` | ✅ 항상 |
>
> 아래 §1 의 v3.1.0 시대 표는 *역사적 참고용* — v4.0.0 부터 #2~#9 는 호출되지 않음.

### 1-legacy. Agents — v3.1.0 시대 표 (역사적 참고용)

각 에이전트의 정의는 `src/agents/<name>.py` 에 있다. 본 표는 미러. v3.1.0 부터 mode (fast/standard/deep) 별 호출 여부가 다르다.

| # | 에이전트 | 파일 | 역할 (요약) | fast | standard | deep |
|---|---------|------|-------------|:----:|:--------:|:----:|
| 1 | 상황인식 분석관 | `src/agents/context_analyst.py` | ACT I: 팩트, 타임라인, 핵심 수치, 웹 검색 | ✅ | ✅ | ✅ |
| 2 | 이해관계자 분석관 **[DEPRECATED v3.0.0]** | `src/agents/player_analyst.py` | ACT II 행위자 식별 / 위험도. v4.0.0 제거 예정 (`FUT-LEGACY-001`) — `src.lenses.StakeholderLens` 사용 권장 | ❌ | ❌ | ✅ |
| 3 | 구조 및 상호작용 분석관 **[DEPRECATED v3.0.0]** | `src/agents/dynamics_analyst.py` | ACT III 게임이론·전환점. v4.0.0 제거 예정 — `src.lenses.StructuralLens` 사용 권장 | ❌ | ❌ | ✅ |
| 4 | 연쇄반응 분석관 **[DEPRECATED v3.0.0]** | `src/agents/chain_reaction_analyst.py` | ACT IV 인과 사슬·와일드카드. v4.0.0 제거 예정 — `src.lenses.CascadeLens` 사용 권장 | ❌ | ❌ | ✅ |
| 5 | 향후 시나리오 분석관 | `src/agents/scenario_architect.py` | ACT V+VI: 시나리오, 감시 신호, 균형 분석 | ✅ | ✅ | ✅ |
| 6 | 시각화 분석관 | `src/agents/visual_analyst.py` | SVG 관계도, Leaflet 지도, Canvas 차트 (LLM) — fast/standard 는 `visual_builder` 결정적 빌더만 사용 | 결정적 | 결정적 | ✅ |
| 7 | 보고서 합성관 | `src/agents/report_synthesizer.py` | HTML/Markdown 생성, Cloudflare 업로드. fast/standard 는 deterministic summary + default narrative plan | 결정적 | 결정적 | ✅ LLM |
| 8 | 품질 검사관 (V3 Step 4) | `src/agents/quality_inspector.py` | Gate 1 + Gate 2. fast/standard 는 heuristic 만, deep 또는 `QUALITY_LLM_JUDGE=true` 일 때만 LLM judge | heuristic | heuristic | ✅ LLM |
| 9 | 종합 판단관 (V3 Step 4) | `src/agents/synthesis_judge.py` | findings → JudgmentVerdict, 모순 노출 (봉합 X), 3축 신뢰도. standard 는 contradictions/저신뢰 시에만 LLM | heuristic | 조건부 | ✅ LLM |
| 10 | 편집장 / Narrative Composer (v3.3.0) | `src/agents/narrative_composer.py` | Opus 5 단일 콜로 자유 형식 보고서 작성. 정형 17 슬롯이 아닌 사건별 3~7 섹션. 차트는 본문 흐름에 따라 embed. 성공 시 archetype 이 `freeform_essay` 로 라우팅. | ❌ | ❌ | ✅ Opus 5 |

DEPRECATED 페르소나 (#2/#3/#4) 는 import 시 `DeprecationWarning` 출력. v3.1.0 부터는 deep 모드에서만 호출 — fast/standard 에서는 lens pool 의 `stakeholder` / `structural` / `cascade` 가 대체 (§2 표 참조). v4.0.0 에서 6막 템플릿 재작업과 함께 정식 제거 (`GOAL.md FUT-LEGACY-001`).

기능 요구사항 매핑은 [GOAL.md](../GOAL.md) 의 REQ-AGT-001~007, REQ-V3-009 참조.

---

## 2. Analysis Lenses — V3 Step 5-A (v2.9.0) 도입, Step 5-C (v3.0.0) 페르소나 이전 3종 추가

`src/lenses/registry.py` 의 11종 미러 (분야 6 + 메타 2 + 페르소나 이전 3). lens 정의 SSOT 는 코드. 사건당 동시 실행 한도 = 4 (Anti-pattern #6).

| Lens ID | 모듈 | 분야 | suitable_intents (top) | method_steps 핵심 |
|---------|------|------|------------------------|-------------------|
| `geopolitical` | `src/lenses/geopolitical_lens.py` | 지정학 | who_benefits, what_next, where_vulnerable | DIME / PMESII / Escalation Ladder / Capability-Intent Matrix |
| `financial_transmission` | `src/lenses/financial_transmission_lens.py` | 금융·거시 | where_spreads, where_vulnerable, what_next | Balance Sheet Map / Flow of Funds / Transmission Channel / Liquidity Stress |
| `tech_architecture` | `src/lenses/tech_architecture_lens.py` | 기술·AI | where_vulnerable, what_to_do, why_happened | Architecture Decomposition / Dependency Graph / Bottleneck Analysis |
| `policy_implementation` | `src/lenses/policy_implementation_lens.py` | 정책 | who_benefits, what_to_do, where_vulnerable | Stakeholder Incentive Map / Distributional Impact / Implementation Gap |
| `accident_causality` | `src/lenses/accident_causality_lens.py` | 사고·재난 | why_happened, where_vulnerable, what_to_do | Fault Tree / Bow-Tie / Swiss Cheese / STAMP |
| `market_structure` | `src/lenses/market_structure_lens.py` | 시장 | who_benefits, where_spreads, what_next | Network Analysis / Game Theory / Regime Shift |
| `red_team` | `src/lenses/red_team_lens.py` | 메타 (반대 가설) | 7종 모두 (보조) | ACH / Pre-mortem / Devil's Advocate |
| `pre_mortem` | `src/lenses/pre_mortem_lens.py` | 메타 (실패 시나리오) | what_to_do, what_next, where_vulnerable | 실패 가정 후 역설계 |
| `stakeholder` (5-C) | `src/lenses/stakeholder_lens.py` | 페르소나 이전 (구 PlayerAnalyst) | who_benefits, what_happened | 행위자 식별 → 동기·자원·전략 → 위험도·연합·취약 고리 |
| `structural` (5-C) | `src/lenses/structural_lens.py` | 페르소나 이전 (구 DynamicsAnalyst) | why_happened, where_vulnerable | 게임이론 / 비대칭 / 전환점 / 피드백 루프 |
| `cascade` (5-C) | `src/lenses/cascade_lens.py` | 페르소나 이전 (구 ChainReactionAnalyst) | where_spreads, what_next | 인과 사슬 → 도미노 단계 → 와일드카드 → 차단점·시간지평 |

### 2.1 Lens 선택 규칙 (v3.1.0 — `lens_policy.select_lenses()`)

LLM 의 `recommended_lenses` 출력에 의존하지 않고 코드 규칙으로 결정. SSOT 는 [src/lens_policy.py](../src/lens_policy.py).

#### Mode 별 cap
| Mode | Lens cap | 메타 lens 자동 추가 |
|------|---------|-------------------|
| fast | 1 | ❌ |
| standard | 2 | ✅ (의사결정·전망 의도에서만) |
| deep | 4 | ✅ + 반대편 메타 lens 도 추가 |

#### 분야 lens 우선순위 (event_type 정규화 후)
```
tech         → tech_architecture, structural
accident     → accident_causality, structural, cascade
financial    → financial_transmission, market_structure, cascade
industry     → market_structure, stakeholder, structural
policy       → policy_implementation, stakeholder
geopolitical → geopolitical, stakeholder, structural
general      → stakeholder, structural
```

#### 메타 lens 자동 추가 매핑
- `user_intent ∈ {what_to_do, where_vulnerable}` → `red_team` 추가
- `user_intent ∈ {what_next}` → `pre_mortem` 추가
- 그 외 의도 (what_happened, why_happened, who_benefits, where_spreads) → 메타 lens 자동 추가 안 함 (모든 사건에 강제 추가 금지)

#### 가드
- **절대 5개 이상 금지** — Pydantic `recommended_lenses: max_length=4` + orchestrator `LENS_CAP_PER_EVENT=4` 이중 가드 (Anti-pattern #6).
- LLM 추천이 들어오면 *분야 lens 만* 우선순위 보정에 활용 (메타 lens 결정권은 정책 단독).
- 미등록 lens_id 는 `red_team` 으로 폴백 + warning 로그 (registry 가드).

### 2.2 Lens 추가 절차

신규 lens 추가 시 (Anti-pattern #14 회피):
1. `src/lenses/<name>_lens.py` 신설 — `LensRunner` 상속, 클래스 속성 6종 + system_prompt 정의
2. `src/lenses/registry.py` `_LENS_CLASSES` 에 등록
3. 본 §2 표 갱신
4. `GOAL.md` 에 `REQ-LENS-*` 추가 (Appendix C 규칙)
5. `src/tests/test_lens_pool.py` 에 isinstance 검증 추가

---

## 3. Report Archetypes — V3 Step 2/5-A/5-C/v3.3.0 누적 (총 12종)

archetype registry 의 SSOT 는 `src/archetypes/registry.py`. 본 표는 미러.

| Archetype ID | 모듈 | 적용 상황 | suitable_intents | 섹션 흐름 |
|--------------|------|-----------|------------------|-----------|
| `six_act_theater` | `src/archetypes/six_act_theater.py` | **인물극형 사건 specialty** (외교 갈등, 정치 분쟁, 리더십, 선거). v3.0.0 부터 default 가 아님. | `who_benefits`, `what_happened` | 상황 → 행위자 → 구조 → 인과 → 시나리오 → 감시 신호 |
| `financial_transmission` (5-A) | `src/archetypes/financial_transmission.py` | 시장/거시 사건 (환율, 금리, 자산 가격, 통화 정책, 신용). | `where_spreads`, `where_vulnerable`, `what_next` | 가격 반응 → 포지션·자금흐름 → 전이 경로 → 취약 고리 → 스트레스 시나리오 → 관찰 지표 |
| `tech_decomposition` (5-A) | `src/archetypes/tech_decomposition.py` | 기술/AI/IT 사건 (모델 출시, 시스템 장애, 사이버 보안, 인프라). | `where_vulnerable`, `what_to_do`, `why_happened` | 문제 정의 → 시스템 구조 → 병목 → 성능·비용·리스크 → 대안 비교 → 실행 권고 |
| `geopolitical_strategic` (5-A) | `src/archetypes/geopolitical_strategic.py` | 지정학·전쟁 (군사 행동, 안보 위기, 동맹 변동). | `who_benefits`, `what_next`, `where_vulnerable` | 사건 요약 → 전장·행위자 → 의도와 능력 → 확전 경로 → 억제 요인 → 감시 신호 |
| `accident_forensic` (5-A) | `src/archetypes/accident_forensic.py` | 사고·재난 (산업재해, 자연재해, 시설 사고). | `why_happened`, `where_vulnerable`, `what_to_do` | 사실 타임라인 → 직접 원인 → 방어막 실패 → 조직적 원인 → 재발 방지 → 미해결 질문 |
| `policy_implementation` (5-A) | `src/archetypes/policy_implementation.py` | 정책·사회 (법안, 규제, 사회 변화). | `who_benefits`, `what_to_do`, `where_vulnerable` | 정책 의도 → 이해관계자 → 제약 조건 → 집행 가능성 → 부작용 → 수정안 |
| `decision_brief` (5-C) | `src/archetypes/decision_brief.py` | 의사결정 보조 — `what_to_do` 의도 전용. event_type 무관. | `what_to_do` | 판단 요약 → 옵션 비교 → 옵션별 리스크 → 권고 → Pre-mortem → 감시 신호 |
| `timeline_first` (5-C) | `src/archetypes/timeline_first.py` | 사실 정리 — `what_happened` 의도 전용. | `what_happened` | 핵심 요약 → 사실 타임라인 → 핵심 수치 → 출처 평가 → 미확인 사항 |
| `scenario_first` (5-C) | `src/archetypes/scenario_first.py` | 향후 분기 — `what_next` 의도 전용. | `what_next` | 기준 시나리오 → 분기 시나리오 → 베이지안 업데이트 가이드 → 감시 신호 |
| `mechanism_decomp` (5-C) | `src/archetypes/mechanism_decomp.py` | 원인 해부 — `why_happened` 의도 전용. | `why_happened` | 표층 현상 → 직접 원인 → 구조적 원인 → 제1원리 → 흔한 오해 |
| `industry_value_chain` (5-C) | `src/archetypes/industry_value_chain.py` | 산업·가치사슬 (M&A, 경쟁, 공급망). | `who_benefits`, `where_vulnerable` | 산업 구조 → 가치사슬 → 경쟁 구도 → 수익성 압력 → 전략 옵션 → 의사결정 포인트 |
| `freeform_essay` (v3.3.0) | `src/archetypes/freeform_essay.py` | **Composer 전용** — Opus 5 narrative_composer 가 자유 형식으로 작성. select_archetype matrix 에서 매칭되지 않으며, deep 모드 + composer 성공 시 orchestrator 가 명시 라우팅. | (matrix 외) | composer 가 사건별로 자유 결정 (3~7 섹션) |

### 3.1 선택 매트릭스 — `select_archetype()` (v3.0.0)

코드 SSOT 는 `src/archetypes/registry.py:select_archetype()`. orchestrator 는 LLM 1순위 후보(strategy.report_archetype) 와 matrix 결과를 모두 산출하고 **matrix 가 최종 결정자**(mismatch 시 INFO 로그). 4-tier 우선순위:

**1순위 — 분야 + 의도 조합** (event_type 카테고리 정규화 후 매핑):
- `tech` + (`where_vulnerable`/`what_happened`/`why_happened`) → `tech_decomposition`
- `tech` + `what_next` → `scenario_first`  ·  `tech` + `what_to_do` → `decision_brief`
- `accident` + (`where_vulnerable`/`what_happened`/`why_happened`) → `accident_forensic`
- `accident` + `what_to_do` → `decision_brief`
- `financial` + (`where_spreads`/`where_vulnerable`) → `financial_transmission`
- `financial` + `what_next` → `scenario_first`
- `industry` + (`who_benefits`/`where_vulnerable`) → `industry_value_chain`
- `industry` + `what_to_do` → `decision_brief`
- `policy` + (`who_benefits`/`what_to_do`/`where_vulnerable`) → `policy_implementation`

**2순위 — 의도 전용** (event_type 미분류 / `general`):
- `what_to_do` → `decision_brief` · `what_next` → `scenario_first` · `why_happened` → `mechanism_decomp` · `what_happened` → `timeline_first`

**3순위 — geopolitical**:
- `geopolitical` + (`who_benefits`/`what_happened`) → `six_act_theater` (인물극형 specialty)
- `geopolitical` + 그 외 → `geopolitical_strategic`

**4순위 — fallback**: 분류된 event_type 이 1순위 미매칭 시 의도 전용으로 폴(2순위 보충), 그래도 미매칭이면 `six_act_theater` + warning 로그.

LLM 이 미등록 archetype_id 를 출력해도 `get_archetype()` 가 `six_act_theater` 로 폴백 (warning 로그). 이 fallback 은 archetype 누락 방지용 안전망일 뿐 — **분기 결정의 SSOT 는 `select_archetype()`**.

---

## 4. Block Types — V3 Step 3 (v2.7.0) 도입

`src/models.py:BlockType` Literal 의 18종 미러 (v3.4.0 에서 `map` 추가). 정의 SSOT 는 코드. 각 블록은 `src/templates/blocks/<type>.html` 로 렌더되고, payload 는 빌더 (`src/agents/report_synthesizer.py:_payload_*`) 가 v2 분석 데이터에서 매핑한다.

| Block ID | 템플릿 | payload 핵심 키 | 빌더 데이터 출처 (v2.7.0 기준) |
|----------|--------|-----------------|--------------------------------|
| `narrative` | `blocks/narrative.html` | `text`, `tone?` | `result.context.background` + `result.dynamics.summary` |
| `claim_card` | `blocks/claim_card.html` | `claim_id`, `statement`, `evidence_ids[]`, `confidence?`, `claim_type?` | placeholder (Step 4 에서 본격 도입) |
| `evidence_table` | `blocks/evidence_table.html` | `evidences[]: {evidence_id, source_url, quote_or_data, reliability, timestamp}` | placeholder (Step 4) |
| `timeline` | `blocks/timeline.html` | `events[]: {date, event, impact?}` | `result.context.timeline` |
| `matrix` | `blocks/matrix.html` | `rows[]`, `cols[]`, `cells: dict["row|col": str]` | placeholder (Step 5 lens-driven 비교) |
| `actor_cards` | `blocks/actor_cards.html` | `actors[]: {name, position, strategy, vulnerability, role_tag?, risk_level?, emoji?}` | `result.players.players` |
| `flow_chain` | `blocks/flow_chain.html` | `steps[]: {title, description?, severity?, affected?, time_horizon?}` | `result.chain_reaction.chain` |
| `scenario_table` | `blocks/scenario_table.html` | `scenarios[]: {name, tag?, probability?, description?, impact?}` | `result.scenarios.scenarios` (impact 는 impact_by_player 요약) |
| `decomposition` | `blocks/decomposition.html` | `root`, `branches[]: {label, detail?, branches?}` (재귀) | `result.dynamics.framework` + `asymmetries` |
| `argument_pair` | `blocks/argument_pair.html` | `hypothesis_a`, `hypothesis_b`, `evidence_alignment?: dict` | `result.dynamics.key_insight` vs `counter_view` |
| `data_series` | `blocks/data_series.html` | `series[]: {label, points[]: {x, y}}`, `unit?` | `result.visuals.chart_config.charts` |
| `watchlist` | `blocks/watchlist.html` | `signals[]: {signal, description?, indicates?, icon?, direction?, deadline?}` | `result.scenarios.watch_signals` |
| `qna` | `blocks/qna.html` | `pairs[]: {q, a}` | placeholder (후속) |
| `callout` | `blocks/callout.html` | `title?`, `body`, `style?: warning\|info\|insight` | `result.dynamics.key_insight` 또는 `result.chain_reaction.worst_case` |
| `counter_hypothesis` | `blocks/counter_hypothesis.html` | `base_judgment?`, `counter`, `required_evidence?[]`, `current_conflict?` | `result.dynamics.key_insight` + `counter_view` + `cognitive_biases` |
| `decision_matrix` | `blocks/decision_matrix.html` | `options[]`, `criteria[]`, `scores: dict["option|criterion": str]`, `recommendation?` | placeholder (Step 4+ decision_brief archetype) |
| `risk_matrix` | `blocks/risk_matrix.html` | `risks[]: {risk, probability?, impact?, mitigation?}` | `result.chain_reaction.wildcards` |
| `map` (v3.4.0) | `blocks/map.html` + `static/maps.{js,css}` | `theme: light_mono\|burgundy_mono`, `center: [lng,lat]`, `zoom`, `markers[]: {id,name,lng,lat,highlight}`, `arcs[]: {from_id,to_id,highlight}`, `legend[]?`, `caption?` | `result.visuals.leaflet_config` (visual_analyst) → `build_map_payload()` 변환 |

### 4.1 블록 템플릿 작성 규칙

- **Anti-pattern #8**: 템플릿은 `block.payload` 만 참조. `result.*` 모델 객체 직접 접근 금지. 검증 명령:
  ```bash
  grep -lE "result\.(context|players|dynamics|chain_reaction|scenarios|visuals|strategy)" src/templates/blocks/*.html
  # 빈 출력이어야 함
  ```
- **단일 책임**: 각 템플릿 파일 50줄 이내 (현재 평균 ~21 줄, 최대 29 줄).
- **CSS 명명**: `block-{type}-{element}` (예: `block-actor-cards-name`). 디자인 토큰 (`--text-primary`, `--gold`, `--red` 등) 재사용 — 신규 토큰 도입 금지.
- **빈 payload**: 데이터가 없을 때 우아하게 표시할 것 (`(데이터 없음)` 등 placeholder). 완전 빈 출력 금지.

### 4.2 디스패처 흐름

(생략 — Step 3 본문 그대로)

---

## 5. Watchlist Registry — V3 Step 5-B (v2.9.5) 도입

`src/watchlist/registry.py` 의 `WatchlistRegistry` (SQLite) 가 SSOT. 보고서 텍스트로만 남기지 않고 *영구 저장* (Anti-pattern #11 회피).

| 컴포넌트 | 모듈 | 책무 |
|---------|------|------|
| `WatchSignal` (Pydantic) | `src/models.py` | signal_id / description / measurement / direction / deadline / parent_chat_id / fired / fired_at |
| `WatchlistRegistry` | `src/watchlist/registry.py` | SQLite CRUD — register / get / list_active / list_active_for_chat / mark_fired |
| `convert_watch_signals` | `src/watchlist/converter.py` | `ScenarioAnalysis.watch_signals` (dict[]) → `list[WatchSignal]`. direction 휴리스틱 추정, 기본 deadline = today+30일 |
| `run_monitor_loop` | `src/watchlist/monitor.py` | 봇 프로세스 내 asyncio task — 1시간 주기 active signal 순회, deadline 도래 시 auto-fire (`ambiguous`) + 텔레그램 알림 |
| `format_telegram_alert` | `src/watchlist/monitor.py` | spec template 알림 텍스트 포맷터 |

### 5.1 발화 트리거 (V3 Step 5-B 한정)

- **deadline 자동 발화**: monitor task 가 `today >= sig.deadline` 인 active signal 을 자동으로 `ambiguous` 방향으로 발화.
- **사용자 수동 발화**: `/fire <signal_id> [direction]` 로 봇에 명시 발화 요청. direction 미지정 시 기존값 유지.
- *외부 시장 데이터 자동 폴링은 본 step 밖* (FUT 트랙).

### 5.2 봇 재시작 복구 (B 보강 결정 구현)

SQLite 영구 저장 덕분에 별도 재구성 로직 없이 `WatchlistRegistry(db_path)` 인스턴스화 + monitor task 기동만으로 복구. 봇 시작 시 `count_active()` 가 곧 부팅 시점의 활성 신호 스냅샷.

### 5.3 알림 텍스트 (spec 템플릿 정확)

```
🔔 감시 신호 발생
사건: {parent_report_title}
신호: {description} → {direction}
원 보고서: {parent_report_url}
권장 후속: {follow_up_action}
```

---

```
ReportSynthesizer.synthesize(result, theme, archetype)
  ├─ if archetype.archetype_id == "six_act_theater":
  │     → render('report.html', ...)            # legacy, byte-equal
  └─ else:
        ├─ blocks = self._build_blocks(result, archetype)
        │   ├─ archetype.section_plan(strategy) → list[ReportSectionPlan]
        │   ├─ for each section, for each block_type → _BLOCK_BUILDERS[type](result, section)
        │   └─ result.strategy.section_plan = plan; result.blocks = blocks
        └─ render('report_block.html', result, archetype_id, ...)
              → 디스패처가 result.strategy.section_plan 을 iterate,
                각 section.section_id 와 매치되는 result.blocks 를 include "blocks/<type>.html"
```

---

## 6. d3 Chart Library — v5.3.0

`src/templates/static/charts.js` 의 d3 차트 미러. SSOT 는 코드 (`RENDERERS` dict). 본 표는 사람-친화 가이드.

v3.2.0 의 9종 `drawScenarioBar/drawKeyFiguresDonut/...` 표는 폐기 — v4.0.0 부터 composer 가 데이터를 직접 emit 하는 mono-themed 렌더러로 전환. 이전 표의 ID 는 더 이상 호출 안 됨 (visual_builder.py 일부 함수도 deprecated).

### 6.1 차트 type 카탈로그 (v5.3.0 — 21종 + 1 embedded_map)

| # | type | charts.js fn | 데이터 shape | capability tier | 용도 |
|---|------|-------------|------------|----------------|------|
| 1 | `bar` | `drawBar` | `[{label, value, note?}]` | safe | 카테고리 순위/크기 (≤8) |
| 2 | `donut` | `drawDonut` | `[{label, value, note?}]` (≥3) | safe | 단일 시점 구성비 (CHART-AP-16 2-segment 금지) |
| 3 | `line` | `drawLine` | `[{x, y, event?}]` | safe | 시계열 단일 시리즈 |
| 4 | `gantt` | `drawGantt` | `[{label, start, end, note?}]` | safe | 사건 구간 (CHART-AP-15 zero-duration 금지) |
| 5 | `network` | `drawNetwork` | `{nodes, links}` | guarded | 관계도 (d3-force) |
| 6 | `stacked` | `drawStacked` | `{scenarios: [{name, segments}]}` | safe | 이산 시점 구성비 |
| 7 | `bubble` | `drawBubble` | `[{label, x, y, size?}]` | safe | 확률 × 영향 (3-variable) |
| 8 | `heatmap` | `drawHeatmap` | `[{title, severity}]` | safe | 위험도 격자 |
| 9 | `dual_line` | `drawDualLine` | `{left, right}` (좌·우 y축) | safe | 두 metric 동조/괴리 |
| 10 | `forecast` | `drawForecast` | `{actual, forecast, fork_at}` | safe | 실측 + 예측 + 신뢰구간 |
| 11 | `choropleth` | `drawChoropleth` | `[{country_code, value}]` | guarded | 지역별 강도 분포 (TopoJSON) |
| 12 | `candle` | `drawCandle` | `[{date, open, high, low, close}]` | safe | 개별주 일봉 (OHLC, v5.2.0+) |
| 13 | `area` | `drawArea` | `[{x, y, event?}]` | safe | 누적·부피성 시계열 |
| 14 | `scatter` | `drawScatter` | `[{label, x, y, accent?}]` | guarded | 라벨 산점도 (v5.3.0, FT 좌측 스타일) |
| 15 | `stacked_area` | `drawStackedArea` | `{series: [{name, values}]}` | guarded | 시계열 누적 영역 (v5.3.0, FT 우측 스타일) |
| 16 | `lollipop` | `drawLollipop` | `[{label, value}]` (8-15) | guarded | bar 의 우아한 대안 (v5.3.0) |
| 17 | `slope` | `drawSlope` | `{left_label, right_label, items}` | guarded | 2 시점 비교·순위 역전 (v5.3.0) |
| 18 | `small_multiples` | `drawSmallMultiples` | `{panels: [{label, series}]}` | guarded | 4-9 패널 그리드 비교 (v5.3.0) |
| 19 | `waterfall` | `drawWaterfall` | `[{label, value, type}]` (첫·끝 total) | guarded | P&L 1차원 분해 (v5.3.0) |
| 20 | `range_bar` | `drawRangeBar` | `[{label, low, high}]` (low<high) | guarded | Dumbbell (두 값 갭, v5.3.0) |
| 21 | `sankey` | `drawSankey` | `{nodes, links}` (DAG, 2-12 노드) | guarded | 다단계 재무 분해·자본 배분 (v5.3.0) |
| (map) | (maps.js) | `renderMap` | `{markers, routes?}` | guarded | `ComposedReport.embedded_map` 별도 채널 |

**capability tier**: SSOT 는 [docs/VISUAL_CAPABILITY_REGISTRY.yaml](VISUAL_CAPABILITY_REGISTRY.yaml). safe = VisualPlanner 자유 emit, guarded = chart_critic + Visual Sanity Gate C 통과 필수.

### 6.2 차트 type 결정 트리

composer 의 차트 선택은 SYSTEM_PROMPT 안의 결정 트리 (v5.3.0 신설) 가 SSOT. 코드: `src/agents/narrative_composer.py:SYSTEM_PROMPT`. 사람-친화 요약:

1. 시간축 있음? → line / area / candle / forecast / dual_line / stacked_area / small_multiples
2. 지리 데이터? → embedded_map / choropleth
3. 카테고리 비교? → bar / lollipop / slope / range_bar / waterfall / sankey (다단계 분해)
4. 구성비? → donut / stacked
5. 다차원 관계? → bubble / scatter / network
6. 2D 격자? → heatmap
7. 일정? → gantt

### 6.3 자동 차트 매트릭스
ResearchDirector 의 `_DEFAULT_REQUIRED_EXHIBITS` 가 9 method 별 자동 추천 type 보유 (SSOT: `src/agents/research_director.py`). 예:
- `scenario_tree` → bubble
- `transmission_channel` → sankey (v5.3.0 부터, 이전엔 bar)
- `stakeholder_matrix` → network
- `fault_tree` → waterfall (v5.3.0 신설)
- `pre_mortem` → scatter (v5.3.0 신설)

### 6.4 신규 차트 추가 절차 (v5.3.0 — 7단계, 5-Layer Usage Guarantee 정합)

1. `src/templates/static/charts.js` 의 `RENDERERS` dict 에 `drawXxx` 함수 추가
2. `src/visual/schemas.py` 의 `_TYPE_TO_GUARD` 에 `XxxGuard` Pydantic 가드 추가 + `validate_chart_data` 디스패처 분기
3. `src/agents/narrative_composer.py:SYSTEM_PROMPT` 의 type 별 data 스키마 + 결정 트리 + emit-X 가드 갱신
4. `docs/VISUAL_CAPABILITY_REGISTRY.yaml` 에 entry 추가 (safe / guarded / experimental)
5. `src/visual/usage_log.py:KNOWN_CHART_TYPES` 에 type 추가 (Layer 1 starvation 분모)
6. `tests/regression/fixtures/chart_type_scenarios.yaml` 에 시나리오 (data_shape / scenario / sample_prompt / negative_examples) 추가
7. 회귀 테스트 (test_chart_correctness / test_chart_type_diversity / test_capability_registry)

CLAUDE.md `Chart System` 섹션의 절차와 동일 — 두 곳이 정합 유지.

---

## 7. 카탈로그 갱신 절차

신규 항목을 코드 registry 에 추가했다면 본 문서도 동시에 갱신한다 ([CLAUDE.md](../CLAUDE.md) Change Propagation 매트릭스 참조).

- 신규 에이전트 → `src/agents/` 추가 시 §1 표 갱신
- 신규 lens → `src/lenses/registry.py` 등록 시 §2 표 갱신
- 신규 archetype → `src/archetypes/registry.py` 등록 시 §3 표 갱신
- 신규 block → `src/models.py:BlockType` 추가 시 §4 표 갱신

자동화 권장은 [DOCS_GOVERNANCE_V3.md §4.1](../DOCS_GOVERNANCE_V3.md) 참조.
