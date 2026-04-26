---
tier: 2
last_synced_with: v2.7.0
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

기능 요구사항 매핑은 [GOAL.md](../GOAL.md) 의 REQ-AGT-001~007 참조.

---

## 2. Analysis Lenses — V3 후 도입 예정

V3 Step 5 에서 `src/lenses/` 디렉토리에 LensRunner ABC 와 6개 기본 렌즈가 추가된다. 도입 후 등록될 렌즈 풀:

| Lens ID | 의미 | 출처 모듈 |
|---------|------|-----------|
| (V3 Step 5 후 작성) | — | `src/lenses/registry.py` |

V3 적용 전까지 본 섹션은 비어 있다. 빈 섹션을 *임의로 채우지 않는다* (Anti-pattern 9).

---

## 3. Report Archetypes — V3 Step 2 (v2.6.0) 도입

archetype registry 의 SSOT 는 `src/archetypes/registry.py`. 본 표는 미러.

| Archetype ID | 모듈 | 적용 상황 | suitable_intents | 섹션 흐름 |
|--------------|------|-----------|------------------|-----------|
| `six_act_theater` | `src/archetypes/six_act_theater.py` | 인물극형 사건 (전쟁, 외교, 정치 갈등, 리더십, 선거). 분류 애매 시 default. | 7종 모두 | 상황 → 행위자 → 구조 → 인과 → 시나리오 → 감시 신호 |
| `financial_transmission` | `src/archetypes/financial_transmission.py` | 시장/거시 사건 (환율, 금리, 자산 가격, 통화 정책, 신용). | `where_spreads`, `where_vulnerable`, `what_next` | 가격 반응 → 포지션·자금흐름 → 전이 경로 → 취약 고리 → 스트레스 시나리오 → 관찰 지표 |
| `tech_decomposition` | `src/archetypes/tech_decomposition.py` | 기술/AI/IT 사건 (모델 출시, 시스템 장애, 사이버 보안, 인프라). | `where_vulnerable`, `what_to_do`, `why_happened` | 문제 정의 → 시스템 구조 → 병목 → 성능·비용·리스크 → 대안 비교 → 실행 권고 |

### 3.1 선택 매트릭스 (Strategy Planner 가이드)

Strategy Planner 프롬프트에 박힌 분기 규칙. 자세한 본문은 `src/orchestrator.py:_generate_analysis_strategy()`.

- `user_intent='where_spreads'` AND `event_type ∈ {financial, market, macro, currency, interest_rate, asset_price}` → `financial_transmission`
- `event_type ∈ {tech, ai, it, software, model_release, system_outage, cyber_security}` → `tech_decomposition`
- 그 외 (인물극, 외교, 갈등, 정치, 일반) → `six_act_theater`

LLM 이 미등록 archetype_id 를 출력하면 `get_archetype()` 가 `six_act_theater` 로 폴백 (warning 로그).

### 3.2 V3 후 추가 archetype (예정)

REFACTOR_V3_PLAN.md Appendix B 의 11종 중 Step 2 에서는 3종만 도입. 나머지 8종 (geopolitical_strategic, industry_value_chain, accident_forensic, policy_implementation, decision_brief, timeline_first, scenario_first, mechanism_decomp) 은 V3 후속 트랙에서 추가. 추가 시 본 표 갱신 + `src/archetypes/<name>.py` 신설 + `registry.py` 등록 (Anti-pattern #14 회피).

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
