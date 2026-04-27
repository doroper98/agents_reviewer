---
tier: 2
last_synced_with: v2.9.0
ssot_for:
  - "현재 에이전트 카탈로그 (mirror of src/agents/*)"
  - "보고서 archetype 카탈로그 (mirror of src/archetypes/registry.py — V3 Step 2 활성화)"
  - "보고서 블록 타입 카탈로그 (mirror of src/models.py:BlockType — V3 Step 3 활성화)"
  - "분석 렌즈 카탈로그 (V3 Step 5 후 src/lenses/registry.py 미러)"
depends_on:
  - "src/agents/* (현재 SSOT)"
  - "src/archetypes/registry.py (archetype SSOT, Step 2 활성화)"
  - "src/models.py:BlockType (BlockType SSOT, Step 3 활성화)"
  - "src/lenses/registry.py (V3 후 lens SSOT)"
last_review: 2026-04-26
---

# Catalogs — Agents · Lenses · Archetypes · Blocks

> 본 문서는 **카탈로그 미러**다. 정의는 코드에서만, 문서는 사람이 읽기 쉬운 형태로 동기화한 사본일 뿐이다.
> 카탈로그를 *정의*하지 않는다. 카탈로그는 코드 registry 가 SSOT.

---

## 1. Agents — 현재 (v2.4.x, V3 이전)

각 에이전트의 정의는 `src/agents/<name>.py` 에 있다. 본 표는 미러.

| # | 에이전트 | 파일 | 역할 (요약) |
|---|---------|------|-------------|
| 1 | 상황인식 분석관 | `src/agents/context_analyst.py` | ACT I: 팩트, 타임라인, 핵심 수치, 웹 검색 |
| 2 | 이해관계자 분석관 | `src/agents/player_analyst.py` | ACT II: 행위자 식별, 전략, 위험도 |
| 3 | 구조 및 상호작용 분석관 | `src/agents/dynamics_analyst.py` | ACT III: 게임이론, 비대칭, 전환점, 피드백 루프 |
| 4 | 연쇄반응 분석관 | `src/agents/chain_reaction_analyst.py` | ACT IV: 인과 사슬, 도미노, 와일드카드 |
| 5 | 향후 시나리오 분석관 | `src/agents/scenario_architect.py` | ACT V+VI: 시나리오, 감시 신호, 균형 분석 |
| 6 | 시각화 분석관 | `src/agents/visual_analyst.py` | SVG 관계도, Leaflet 지도, Canvas 차트 |
| 7 | 보고서 합성관 | `src/agents/report_synthesizer.py` | HTML/Markdown 생성, Cloudflare 업로드 |
| 8 | 품질 검사관 (V3 Step 4) | `src/agents/quality_inspector.py` | Gate 1 (Plan Sanity) + Gate 2 (Coverage Check) — heuristic + LLM-as-judge |
| 9 | 종합 판단관 (V3 Step 4) | `src/agents/synthesis_judge.py` | findings → JudgmentVerdict, 모순 노출 (봉합 X), 3축 신뢰도 |

기능 요구사항 매핑은 [GOAL.md](../GOAL.md) 의 REQ-AGT-001~007 참조.

---

## 2. Analysis Lenses — V3 Step 5-A (v2.9.0) 도입

`src/lenses/registry.py` 의 8종 미러. lens 정의 SSOT 는 코드. 사건당 동시 실행 한도 = 4 (Anti-pattern #6).

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

### 2.1 Lens 선택 규칙 (Strategy Planner 가이드)

- 사건 핵심 분야 lens 1~2개 + 메타 lens (`red_team` 또는 `pre_mortem`) 0~1개 권장.
- **절대 5개 이상 금지** — Pydantic `recommended_lenses: max_length=4` + orchestrator `LENS_CAP_PER_EVENT=4` 이중 가드 (Anti-pattern #6).
- 미등록 lens_id 는 `red_team` 으로 폴백 + warning 로그 (registry 가드).

### 2.2 Lens 추가 절차

신규 lens 추가 시 (Anti-pattern #14 회피):
1. `src/lenses/<name>_lens.py` 신설 — `LensRunner` 상속, 클래스 속성 6종 + system_prompt 정의
2. `src/lenses/registry.py` `_LENS_CLASSES` 에 등록
3. 본 §2 표 갱신
4. `GOAL.md` 에 `REQ-LENS-*` 추가 (Appendix C 규칙)
5. `src/tests/test_lens_pool.py` 에 isinstance 검증 추가

---

## 3. Report Archetypes — V3 Step 2 + 5-A 도입 (총 6종)

archetype registry 의 SSOT 는 `src/archetypes/registry.py`. 본 표는 미러.

| Archetype ID | 모듈 | 적용 상황 | suitable_intents | 섹션 흐름 |
|--------------|------|-----------|------------------|-----------|
| `six_act_theater` | `src/archetypes/six_act_theater.py` | 인물극형 사건 (전쟁, 외교, 정치 갈등, 리더십, 선거). 분류 애매 시 default. | 7종 모두 | 상황 → 행위자 → 구조 → 인과 → 시나리오 → 감시 신호 |
| `financial_transmission` | `src/archetypes/financial_transmission.py` | 시장/거시 사건 (환율, 금리, 자산 가격, 통화 정책, 신용). | `where_spreads`, `where_vulnerable`, `what_next` | 가격 반응 → 포지션·자금흐름 → 전이 경로 → 취약 고리 → 스트레스 시나리오 → 관찰 지표 |
| `tech_decomposition` | `src/archetypes/tech_decomposition.py` | 기술/AI/IT 사건 (모델 출시, 시스템 장애, 사이버 보안, 인프라). | `where_vulnerable`, `what_to_do`, `why_happened` | 문제 정의 → 시스템 구조 → 병목 → 성능·비용·리스크 → 대안 비교 → 실행 권고 |
| `geopolitical_strategic` (5-A) | `src/archetypes/geopolitical_strategic.py` | 지정학·전쟁 (군사 행동, 안보 위기, 동맹 변동). | `who_benefits`, `what_next`, `where_vulnerable` | 사건 요약 → 전장·행위자 → 의도와 능력 → 확전 경로 → 억제 요인 → 감시 신호 |
| `accident_forensic` (5-A) | `src/archetypes/accident_forensic.py` | 사고·재난 (산업재해, 자연재해, 시설 사고). | `why_happened`, `where_vulnerable`, `what_to_do` | 사실 타임라인 → 직접 원인 → 방어막 실패 → 조직적 원인 → 재발 방지 → 미해결 질문 |
| `policy_implementation` (5-A) | `src/archetypes/policy_implementation.py` | 정책·사회 (법안, 규제, 사회 변화, 부동산 정책). | `who_benefits`, `what_to_do`, `where_vulnerable` | 정책 의도 → 이해관계자 → 제약 조건 → 집행 가능성 → 부작용 → 수정안 |

### 3.1 선택 매트릭스 (Strategy Planner 가이드, 충돌 시 위쪽 우선)

Strategy Planner 프롬프트에 박힌 분기 규칙. 자세한 본문은 `src/orchestrator.py:_generate_analysis_strategy()`.

- 사고·재난 (화재/폭발/붕괴/침수/산업재해/자연재해) → `accident_forensic`
- 정책·법안·규제 (부동산 규제/조세/노동 정책/규제 발표) → `policy_implementation`
- 군사·전쟁·안보 위기·동맹 변동 → `geopolitical_strategic`
- 시장·거시 (환율/금리/자산가격/유동성 위기) AND `user_intent ∈ {where_spreads, where_vulnerable, what_next}` → `financial_transmission`
- 기술·AI·IT (모델 출시/시스템 장애/사이버 사고/인프라) → `tech_decomposition`
- 그 외 인물극형 (외교 갈등/정치 분쟁/리더십 변화) 또는 분류 애매 → `six_act_theater`

LLM 이 미등록 archetype_id 를 출력하면 `get_archetype()` 가 `six_act_theater` 로 폴백 (warning 로그).

### 3.2 V3 후 추가 archetype (예정)

REFACTOR_V3_PLAN.md Appendix B 의 11종 중 Step 2 + 5-A 에서는 6종 도입. 나머지 5종 (industry_value_chain, decision_brief, timeline_first, scenario_first, mechanism_decomp) 은 v3.x 패치 트랙에서 추가. 추가 시 본 표 갱신 + `src/archetypes/<name>.py` 신설 + `registry.py` 등록 (Anti-pattern #14 회피).

---

## 4. Block Types — V3 Step 3 (v2.7.0) 도입

`src/models.py:BlockType` Literal 의 17종 미러. 정의 SSOT 는 코드. 각 블록은 `src/templates/blocks/<type>.html` 로 렌더되고, payload 는 빌더 (`src/agents/report_synthesizer.py:_payload_*`) 가 v2 분석 데이터에서 매핑한다.

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

## 5. 카탈로그 갱신 절차

신규 항목을 코드 registry 에 추가했다면 본 문서도 동시에 갱신한다 ([CLAUDE.md](../CLAUDE.md) Change Propagation 매트릭스 참조).

- 신규 에이전트 → `src/agents/` 추가 시 §1 표 갱신
- 신규 lens → `src/lenses/registry.py` 등록 시 §2 표 갱신
- 신규 archetype → `src/archetypes/registry.py` 등록 시 §3 표 갱신
- 신규 block → `src/models.py:BlockType` 추가 시 §4 표 갱신

자동화 권장은 [DOCS_GOVERNANCE_V3.md §4.1](../DOCS_GOVERNANCE_V3.md) 참조.
