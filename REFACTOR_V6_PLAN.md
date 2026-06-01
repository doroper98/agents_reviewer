---
tier: 1
status: proposal
target_version: v6.0.0
based_on_baseline: v5.8.7
last_synced_with: v5.8.7
ssot_for:
  - "V6 마스터 플랜 (workflow → agent, 사실 grounding + bounded loop)"
  - "V6 요구사항 (REQ-V6-N) 정본"
  - "V6 Phase 진입/완료 기준 + 테스트 플랜"
  - "V6 anti-pattern (AP-V6-N) 카탈로그 — append-only"
depends_on:
  - "src/agents/narrative_composer.py (본문 생성 — 보존, Claude 고정)"
  - "src/agents/context_analyst.py (증거 수집 — provenance 확장)"
  - "src/config.py:_select_mode (역할별 모델 라우팅 확장 지점)"
  - "docs/REPORT_WRITING_ANTIPATTERNS.md (WRITE-AP-15/16 신설)"
  - "REFACTOR_V5_PLAN.md (V5 Phase 와 충돌 금지 — 병행 트랙)"
proposed_by: NVIDIA GTC 보고서 팩트체크 회귀 (2026-06-01) + agentic 정의 논의
last_review: 2026-06-01
---

# REFACTOR V6 — Workflow → Agent: 사실 grounding + Bounded Verification Loop

> **목적.** v5.8.7 은 *강한 문체·시각 거버넌스를 갖췄으나 사실 거버넌스와 루프가
> 없는 단일 패스 LLM 파이프라인* 이다. 2026-06-01 NVIDIA GTC 보고서가 외부
> 팩트체크(ChatGPT)에서 받은 5종 사실오류는 *우연이 아니라 구조적 결함* 이다 —
> 가장 강한 사실 규율 장치(`Claim.must_have_evidence`)가 정작 사용자가 읽는
> 자유 본문(`ComposedSection.prose`)에는 적용되지 않고, 작성된 주장을 출처와
> 대조하는 *검증 루프* 가 시스템 어디에도 없다. style 은 `editor`, 차트는
> `chart_critic`/`desk_editor` 가 critic 을 도는데 **fact 에는 critic 이 없다.**
>
> 젠슨 황의 정의 `AGENT = LLM + HARNESS` (GTC Taipei 2026) 로 보면 — 우리는
> harness 부품(PROMPT/CONTEXT/TOOLS/MEMORY/ORCHESTRATION/GOVERNANCE)을 *거의 다*
> 갖췄으나 한가운데 **OBSERVE→REASON→ACT 루프** 가 빠진 *직선 파이프* 다. V6 는
> 부품을 새로 사오는 게 아니라 **이미 있는 부품을 루프로 배선** 한다. 첫 루프는
> *사실 검증* — 외부(ChatGPT)가 대신 해주던 fact-critic 역할을 파이프라인 안으로
> 들인다.
>
> **비목적.** ① 무한 자율 agent 를 만들지 않는다 (bounded·guarded 루프만). ②
> 사용자 본문 생성 모델을 교체하지 않는다 (anti-pattern 가드가 Claude 실패모드에
> 튜닝됨 — AP-V6-1). ③ V5 의 결정성·재현성을 버리지 않는다 (모든 신규 행동은
> `V6_*` flag default OFF, 꺼지면 v5.8.7 byte-equal — AP-V6-3). ④ 평이화·일반
> 독자 우선(v5.5.5)을 후퇴시키지 않는다 — 사실 grounding 을 *그 위에* 얹는다.

---

## 0. 컨텍스트 — v5.8.7 현황과 V6 수술 대상

### 0.1 v5.8.7 까지 *이미 갖춘* 것 (보존 대상)

| 영역 | 현 상태 | 평가 |
|------|---------|------|
| 단일 편집장 (NarrativeComposer Opus) | 2-call Tier 4 작동 | ✅ |
| 문체 거버넌스 | REPORT_STYLE_GUIDE + WRITE-AP 14종 + `_sanitize_symbols` | ✅ |
| 시각 거버넌스 | chart_critic / desk_editor / deterministic_gate (V5) | ✅ |
| 시점 앵커링 (발행일↔사건일) | WRITE-AP-11/14 + `timeutil.KST` SSOT | ✅ 부분 |
| 일반 독자 우선 | 평이화 + footnotes (v5.5.5) | ✅ |
| 결정성·재현성 | golden_prompts 회귀 + byte-equal 가드 + patch_report (LLM 0) | ✅ |
| 시장 데이터 | market_fetcher 24종목 (KRX/Yahoo/FRED/ECOS) | ✅ |

### 0.2 *아직 남은* 11개 결함 (V6 수술 대상 — 2026-06-01 진단)

| ID | 결함 | NVIDIA 보고서 증거 | V6 Phase |
|----|------|--------------------|----------|
| **V6-GAP-1** | **자유 본문에 evidence-binding 이 안 걸린다.** Rule #9 `Claim.must_have_evidence` 는 Claim 모델에만 작동하고, 독자가 읽는 `ComposedSection.prose` 는 검증 없이 통과한다. 가장 강한 사실 규율이 정작 본문에 미적용. | 5종 오류 전부의 근본 뿌리 | Phase 1·3 |
| **V6-GAP-2** | **출처 없는 특정 수치를 방치한다.** composer 가 그럴듯한 정밀 숫자를 confabulate. | "27년 만의 PC 칩" (공식: 30년, 출처 불명) | Phase 1·3 |
| **V6-GAP-3** | **수치 scope 를 검증하지 않는다.** 진짜 숫자를 더 임팩트 있는 *잘못된 단위* 에 귀속. concreteness 압력의 부작용. | "보드 한 장 130만 부품" (실제: NVL72 *랙 전체*) | Phase 1·3 |
| **V6-GAP-4** | **출처 작성일과 사건 신규성을 구분하지 못한다.** 옛 보도자료를 "오늘 발표" 로 합성. WRITE-AP-11/14 의 미커버 사촌. | "GR00T 오늘 상용화" (실제: 3/16 산호세 기발표) | Phase 1·2·3 |
| **V6-GAP-5** | **시계열·시장 수치에 시점 라벨이 없다.** market_fetcher 의 직전 종가를 "직전 반응" 으로 과근접. | "키노트 직전 211.14, -1.45%" (실제: 직전 정규장 종가) | Phase 1·2 |
| **V6-GAP-6** | **fact-critic / 검증 루프가 부재한다 — 가장 본질적 결함.** composer 가 쓰면 그대로 발행. 주장↔출처 대조를 아무도 안 한다. 외부(ChatGPT)가 우리 fact-critic 을 대신 했다. | 위 5종이 발행본까지 도달 | **Phase 3 (FactCritic)** |
| **V6-GAP-7** | **per-fact provenance 메타가 없다.** 각 사실에 *언제 발표·어느 단위·어느 출처* 태그가 없어, 신규성·scope 를 데이터로 판정 불가. | GAP-3/4/5 를 프롬프트로만 막아야 함 | **Phase 2 (Provenance)** |
| **V6-GAP-8** | **모델 라우팅이 역할 무관이다.** 전부 Opus. 루프를 돌면 구독 토큰이 폭주한다. | (루프 도입 시 비용 위험) | **Phase 4 (Model Tiering)** |
| **V6-GAP-9** | **OBSERVE 가 1회성이다.** ContextAnalyst 웹검색이 한 번 돌고 끝. 근거 빈약을 감지해 재검색하지 못한다. | 부정확/누락 출처가 그대로 하류로 | Phase 5 |
| **V6-GAP-10** | **MEMORY read-back 이 없다.** 과거 보고서·watchlist 가 추론에 안 먹인다 (write-mostly). | 중복 각도·예측 추적 불가 | Phase 6 |
| **V6-GAP-11** | **orchestration 이 정적이다.** 복잡도 무관 고정 4단계. 루프 횟수를 사건 난이도로 판단하지 못한다. | (균질한 깊이) | Phase 7 |

> **공통 분모.** GAP-1~6 은 전부 *"작성된 사실을 출처와 대조하는 단계 부재"* 한
> 가지로 수렴한다. GAP-6(루프 부재)이 본질이고 나머지는 그 증상이다. V6 의 심장은
> **bounded FactCritic 루프**(Phase 3)이며, Phase 1/2 는 그 루프가 판정할 *재료*
> (결정적 가드 + provenance)를 깐다.

### 0.3 구현 우선순위 — 3-Tier

| Tier | 내용 | 포함 Phase | 정당화 |
|------|------|------------|--------|
| **Tier 1 — 사실 토대 (LLM 0 또는 저비용)** | 결정적 가드 + 프롬프트 하드닝 + provenance | Phase 0, 1, 2 | 루프 없이도 5종 중 상당수를 즉시 차단. 가장 싸고 회귀 위험 낮음. |
| **Tier 2 — 루프 (agentic 핵심)** | FactCritic bounded loop + 역할별 모델 티어링 | Phase 3, 4 | V6 의 심장. Tier 1 가드가 깔려야 critic 이 *판정 재료* 를 가진다. |
| **Tier 3 — 확장 agentic** | 반복 OBSERVE + memory read-back + 동적 orchestration | Phase 5, 6, 7 | harness 의 나머지 화살표. Tier 1·2 가 단단해야 의미. |

핵심 메시지: **후행 루프(Tier 2)가 좋아도 상류 재료(Tier 1)가 없으면 critic 은
근거 없이 추측한다.** Tier 1 부터.

---

## 1. V6 설계 원칙

1. **bounded·guarded 루프만.** 모든 루프는 ① 최대 횟수 cap (재작업 ≤2, 재검색 ≤3)
   ② 결정적 종료조건 ③ 실패 시 결정적 fallback. 무한 자율 금지 (AP-V6-2).
2. **본문 생성은 Claude(Opus) 고정.** anti-pattern 가드(`_sanitize_symbols`,
   WRITE-AP-12/13 등)가 Claude 실패모드에 튜닝됨. *본문 비노출 역할*(critic·loop
   control·research plan)만 모델 교체 가능 (AP-V6-1).
3. **루프 제어는 0 LLM 우선.** "한 번 더 돌까" 판정은 `deterministic_gate` 사상의
   규칙으로. LLM 은 *작업*(재작성·재검색)에만. 토큰은 작업에서만 나간다 (AP-V6-5).
4. **flag OFF = byte-equal.** 모든 신규 행동은 `V6_*` env flag default OFF. 꺼지면
   v5.8.7 호출 경로·출력 byte-equal. golden_prompts 회귀로 강제 (AP-V6-3).
5. **사실 > 문체.** 평이화·생생함(v5.5.5)은 *grounding 뒤에* 온다. 출처 없는
   생생함은 과장이다. concreteness 와 fact 가 충돌하면 fact 가 이긴다.
6. **append-only 측정.** V6 효과는 `docs/V6_TEST_RESULTS.md` 에 추가만 (기존 수정
   금지, AP-V6-6 — V5 의 AP-V5-32 계승).

---

## 2. 요구사항 명세 (REQ-V6-N)

| REQ | 요구사항 | 검증 (테스트 플랜 §) | Phase |
|-----|----------|----------------------|-------|
| **REQ-V6-1** | 본문 prose 의 *정량 주장*(숫자·년수·개수·%)은 evidence 에 binding 되거나, 안 되면 emit 금지. | T-1, T-3 | 1, 3 |
| **REQ-V6-2** | 출처에 없는 특정 수치("N년 만"·"N개"·"N%")는 결정적으로 검출·차단. | T-1 | 1 |
| **REQ-V6-3** | 정량 주장의 scope(단위·전체/부분)가 모호하면 검출. "130만" 단독 금지 → "랙 전체 130만". | T-1 | 1, 3 |
| **REQ-V6-4** | 출처 작성일이 사건일과 다르면 "오늘 발표" 류 신규성 단정 차단. "3월에 공개된 것을 재강조" 프레이밍. | T-2 | 1, 2, 3 |
| **REQ-V6-5** | 시계열·시장 수치는 시점 라벨 동반("직전 정규장 종가" 등). 장 마감 시 "직전 반응" 표현 금지. | T-2 | 1, 2 |
| **REQ-V6-6** | bounded FactCritic 루프 — 본문 주장을 evidence 와 대조, 위반 시 재작성 트리거(≤2회), 결정적 fallback. | T-3, T-4 | 3 |
| **REQ-V6-7** | ContextAnalysis 의 각 증거 항목에 provenance(source_date / scope / source_url) 태깅. | T-2 | 2 |
| **REQ-V6-8** | 역할별 모델 라우팅: 본문=Opus 고정 / critic·plan=저가 또는 2차 / loop control=0 LLM. | T-5 | 4 |
| **REQ-V6-9** | OBSERVE 반복 — 근거 gap 감지 시 재검색(≤3회, budget bound). | T-6 | 5 |
| **REQ-V6-10** | MEMORY read-back — 과거 보고서·watchlist 를 추론 context 로(중복 각도 회피, 예측 추적). | T-7 | 6 |
| **REQ-V6-11** | 동적 orchestration — 사건 복잡도로 루프 횟수·깊이 결정. | T-8 | 7 |

---

## 3. Phase 명세

### Phase V6-0 — Baseline + Fact-error Golden Fixtures
**목적**: V6 의 측정 기준. 2026-06-01 NVIDIA 케이스를 *영구 회귀 fixture* 로 박고,
5종 오류 클래스를 testable 하게 정의. (이 Phase 가 테스트 플랜의 운영 진입점.)
- **신규 SSOT**: `tests/regression/fixtures/fact_discipline_scenarios.yaml` — 각
  시나리오 = {evidence(provenance 포함), bad_prose(실제 회귀), error_class,
  expected_flag}. NVIDIA 5종 + 합성 케이스.
- **error_class 5종 동결**: `unsourced_number`(27년) / `scope_misattribution`(130만)
  / `novelty_conflation`(GR00T) / `timepoint_overclaim`(211.14) / `list_truncation`(OEM).
- **flag**: 없음 (fixture 는 항상 존재). 코드 무변경.
- **테스트**: `tests/regression/test_fact_discipline.py` 스켈레톤 — fixture 로드 +
  스키마 검증 (실제 가드는 Phase 1 에서 채움).
- **DoD**: fixture 5+ 시나리오, error_class enum 1:1, CI 로드 통과.

### Phase V6-1 — Deterministic Fact Guards + Composer Prompt 하드닝 (LLM 0)
**목적**: 루프 없이, 결정적 후처리 + 프롬프트로 5종 중 차단 가능한 것 즉시 차단.
가장 싸고 회귀 위험 낮음. (Tier 1 의 핵심.)
- **신규 SSOT**: `src/visual/` 와 대칭으로 `src/factcheck/deterministic_guards.py`
  — ① `UnsourcedNumberGuard`(본문의 "N년 만"·"N개"·"N%" 정규식 추출 → evidence
  문자열에 없으면 flag) ② `ScopeBarewordGuard`(대형 수치 단독 등장 검출) ③
  `TimepointLabelGuard`(시장 수치 인접에 시점 라벨 없으면 flag) ④
  `NoveltyDeltaGuard`(source_date − publication_date 차이 시 "오늘/방금" 인접 flag).
- **프롬프트**: `narrative_composer.py:SYSTEM_PROMPT` 에 `=== 사실 규율 (V6) ===`
  블록 — 수치 scope 명시 / 출처 없는 특정수치 금지 / 신규성 구분 / 시장 시점 라벨 /
  목록은 "대표 몇 + 등". `.replace()` 사용 (Rule #7).
- **anti-pattern**: WRITE-AP-15(수치 scope 오귀속·출처없는수치), WRITE-AP-16(출처
  기발표↔오늘 신규 혼동) 신설 → `docs/REPORT_WRITING_ANTIPATTERNS.md` + CLAUDE.md.
- **flag**: `V6_FACT_GUARDS=1`. OFF 면 가드 미적용 (byte-equal). 단 프롬프트 블록은
  추가돼도 기존 출력에 영향 최소 — 측정 후 결정 (§테스트 T-1/T-2).
- **mode**: 결정적 가드는 *flag* 또는 *log-only* 우선(WARNING 만, drop 안 함) →
  오발 측정 후 enforce 승격. 초기엔 silent flag → telemetry.
- **DoD**: fixture 5종 중 unsourced_number/scope/timepoint/novelty 4종을 가드가
  ≥90% 검출, false-positive 측정 < 임계. 프롬프트 변경 후 golden_prompts 회귀 통과.

### Phase V6-2 — Per-fact Provenance in ContextAnalysis
**목적**: GAP-7. 각 증거에 *언제·어느 단위·어느 출처* 태그 → 신규성/scope/시점을
프롬프트가 아니라 *데이터* 로 판정.
- **모델**: `src/models.py:ContextAnalysis` 의 evidence 항목에 `source_date`,
  `scope_note`, `source_url` 추가 (additive, Optional — 구 데이터 호환). DATA_MODELS
  갱신.
- **에이전트**: `context_analyst.py:SYSTEM_PROMPT` 에 "각 사실에 발표일·단위 명시"
  지시. fetch 출처의 게시일 추출(image_fetcher 의 og:published 재사용 가능).
- **flag**: `V6_PROVENANCE=1`. OFF 면 필드 비고 기존 경로.
- **DoD**: NVIDIA fixture 의 GR00T(3/16)·130만(랙) 케이스가 provenance 로 표현되고,
  NoveltyDeltaGuard/ScopeGuard 가 프롬프트 없이 데이터로 판정. 회귀 테스트.

### Phase V6-3 — FactCritic Bounded Loop (agentic 핵심)
**목적**: GAP-6. 본문 주장을 evidence 와 대조하는 *루프*. 외부 ChatGPT 역할의 내재화.
- **신규 에이전트**: `src/agents/fact_critic.py` — 입력: ComposedReport prose +
  ContextAnalysis(provenance). 출력: `FactVerdict`(per-claim: grounded/unsourced/
  scope_mismatch/novelty_conflation + 수정 지시). bounded: 위반 발견 → composer
  재작성 1회 → 재검 1회 (최대 N=2). 결정적 종료: 위반 0 또는 N 소진.
- **루프 제어 = 0 LLM**: "재작성할까" 판정은 FactVerdict 의 위반 카운트(결정적).
  LLM 은 *판정*(critic)과 *재작성*(composer)에만. (AP-V6-5)
- **fallback**: N 소진 후에도 위반 잔존 시 → 해당 문장에 결정적 헤지 부착 또는 drop
  (Claim validator 사상). 보고서는 정상 발행.
- **flag**: `V6_FACT_CRITIC=1` default OFF. OFF 면 v5.8.7 단일 패스.
- **모델**: critic 은 Phase 4 의 역할 라우팅 적용 (저가 가능). 재작성 composer 는
  Opus 고정 (AP-V6-1).
- **DoD**: NVIDIA fixture 5종을 e2e 로 통과시켜 위반이 0 또는 헤지로 수렴. 루프 횟수
  ≤2 강제 검증. flag OFF byte-equal.

### Phase V6-4 — Role-based Model Tiering (비용 통제)
**목적**: GAP-8. 루프 비용 폭주 차단. `config._select_mode` 의 CLI/API 이분법에
*역할 축* 추가.
- **SSOT**: `src/config.py` 에 `role_model_map`(role → model/mode). 역할: `body`
  (Opus 고정) / `critic` / `plan` / `control`(=none, 0 LLM). 기본값은 전부 현행
  Opus 로 둬 byte-equal, flag 로 critic/plan 만 저가 전환.
- **flag**: `V6_MODEL_TIERING=1`. 세부 `V6_CRITIC_MODEL=haiku` 등.
- **2차 제공자(선택)**: critic/plan 에 한해 외부 모델 경로 hook (본문 절대 불가).
  종량/구독 trade-off 는 docs 에 명시. 디폴트는 Claude Haiku.
- **DoD**: 루프 1회당 토큰 소모를 tiering ON/OFF 로 측정(V6_TEST_RESULTS). body 가
  항상 Opus 인지 가드 테스트. AP-V6-1 회귀.

### Phase V6-5 — Iterative OBSERVE (Research Re-search Loop)
**목적**: GAP-9. ContextAnalyst 가 근거 gap 을 감지해 재검색(≤3, budget bound).
- bounded loop + 결정적 종료(필수 사실 충족 또는 budget 소진). flag `V6_ITER_OBSERVE=1`.
- **DoD**: gap 시나리오에서 재검색 발생·budget cap 준수. flag OFF byte-equal.

### Phase V6-6 — Memory Read-back
**목적**: GAP-10. 과거 보고서·watchlist 를 추론 context 로. (후속 보고 기능의 일반화.)
- watchlist registry + reports/*.json 에서 관련 과거 보고 요약 주입. 중복 각도 회피.
- flag `V6_MEMORY_READBACK=1`. **개인정보·토큰 노출 주의** (admin URL 등 본문 유입 금지).
- **DoD**: 후속/중복 시나리오에서 과거 맥락 반영. flag OFF byte-equal.

### Phase V6-7 — Dynamic Orchestration
**목적**: GAP-11. 사건 복잡도로 루프 횟수·깊이 결정. orchestrator 의 고정 4단계에
복잡도 분기 추가. flag `V6_DYNAMIC_ORCH=1`.
- **DoD**: 단순/복잡 시나리오에서 루프 횟수 차등. 상한 cap 준수. flag OFF byte-equal.

---

## 4. 테스트 플랜

> **원칙.** ① 모든 Phase 는 *flag OFF byte-equal* 회귀를 먼저 통과해야 머지 (AP-V6-3).
> ② fact 검증은 `fact_discipline_scenarios.yaml`(Phase 0) 를 단일 fixture SSOT 로
> 공유. ③ 효과 측정은 `docs/V6_TEST_RESULTS.md` append-only.

| ID | 테스트 | 대상 Phase | 파일 |
|----|--------|-----------|------|
| **T-0** | flag OFF byte-equal — 모든 `V6_*` OFF 시 golden_prompts 출력 v5.8.7 동일 | 전 Phase | `tests/regression/test_v6_byte_equal.py` |
| **T-1** | 결정적 가드 검출률 — fixture 의 unsourced_number/scope/timepoint 를 ≥90% flag, FP < 임계 | 1 | `test_fact_discipline.py` |
| **T-2** | provenance 기반 신규성·시점 — GR00T(3/16)·시장 종가 케이스 데이터 판정 | 1, 2 | `test_fact_discipline.py` |
| **T-3** | FactCritic e2e — NVIDIA 5종이 루프 후 위반 0 또는 헤지로 수렴 | 3 | `test_fact_critic.py` |
| **T-4** | 루프 bound — 재작성 ≤2, 결정적 종료, fallback 정상 발행 | 3 | `test_fact_critic.py` |
| **T-5** | 모델 라우팅 — body 항상 Opus, critic/plan 만 전환, 토큰 측정 | 4 | `test_model_tiering.py` |
| **T-6** | 반복 OBSERVE — gap 시 재검색, budget cap | 5 | `test_iter_observe.py` |
| **T-7** | memory read-back — 과거 맥락 주입, 토큰/PII 비유출 | 6 | `test_memory_readback.py` |
| **T-8** | 동적 orchestration — 복잡도별 루프 차등, 상한 cap | 7 | `test_dynamic_orch.py` |

**측정 지표** (V6_TEST_RESULTS.md): fact-error rate (fixture 기준 발행본 잔존 위반/
보고서), 루프 평균 횟수, 호출당 토큰(tiering ON/OFF), 지연(초). V6 의 DoD 는
*NVIDIA 5종이 발행본에서 0 으로 수렴* + *flag OFF byte-equal* + *비용 측정 공개*.

---

## 5. Anti-pattern (V6 누적 — AP-V6-N, append-only)

| AP | 금지 | 가드 |
|----|------|------|
| **AP-V6-1** | 사용자 본문(prose/headline/deck/broadcast) 생성 모델을 Claude 외로 교체 금지 | T-5 body=Opus 가드. critic/plan/control 만 교체 허용 |
| **AP-V6-2** | 무한·무경계 루프 금지 | 모든 루프 횟수 cap + 결정적 종료 + fallback (T-4) |
| **AP-V6-3** | flag OFF 인데 출력이 v5.8.7 과 달라짐 금지 | T-0 byte-equal, 머지 전제조건 |
| **AP-V6-4** | 출처 없는 특정 수치 emit 금지 | UnsourcedNumberGuard (Phase 1) |
| **AP-V6-5** | 루프 *제어*에 LLM 남용 금지 (제어는 결정적 우선) | control 역할 = 0 LLM (Phase 3/4) |
| **AP-V6-6** | V6_TEST_RESULTS 기존 entry 수정 금지 (append-only) | 리뷰 체크 (V5 AP-V5-32 계승) |
| **AP-V6-7** | memory read-back 으로 토큰·admin URL·PII 가 본문에 유입 금지 | T-7 비유출 검증 (Phase 6) |

회귀 발견 시 본 표에 AP-V6-N append.

---

## 6. 인수 기준 (V6 Definition of Done)

1. NVIDIA GTC fixture 5종 사실오류가 **발행본에서 0 으로 수렴** (위반→grounded/헤지/drop).
2. 모든 `V6_*` flag OFF 에서 golden_prompts 출력이 **v5.8.7 byte-equal** (T-0).
3. FactCritic 루프가 **bounded** (≤2회) 하며 실패 시 **결정적 fallback** 으로 정상 발행.
4. 본문 생성은 **항상 Opus** (AP-V6-1), critic/plan 만 모델 티어링으로 비용 절감 측정.
5. WRITE-AP-15/16 + AP-V6-1~7 등록, `docs/V6_TEST_RESULTS.md` 효과 공개.
6. `src/orchestrator.py:VERSION` = `v6.0.0`, 전 문서 `last_synced_with` 갱신, CHANGELOG/
   README 동기화.

---

## 7. V5 와의 관계 (병행 트랙)

V6 는 V5 를 대체하지 않는다. V5 는 *시각·분석설계·데이터계약* 트랙(Phase 0~8),
V6 는 *사실 grounding + agentic 루프* 트랙. 충돌 지점은 `narrative_composer.py:
SYSTEM_PROMPT`(양쪽 다 건드림) — V6 의 `=== 사실 규율 ===` 블록은 V5 의 어조·시각
지시와 *직교* 하게 추가하고, 두 트랙의 프롬프트 변경은 같은 SSOT(REPORT_STYLE_GUIDE
+ REPORT_WRITING_ANTIPATTERNS)에 정합. flag 네임스페이스 분리(`V5_*` vs `V6_*`).
