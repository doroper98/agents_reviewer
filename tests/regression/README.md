---
tier: 2
status: phase_0b_ssot
last_synced_with: v4.5.7
ssot_for:
  - "V5 Phase 0B Golden Evaluation Harness 사용·확장 가이드"
  - "5종 회귀 테스트 진입 / 출력 / threshold 문서"
  - "v4.5.7 baseline recording 절차"
depends_on:
  - "REFACTOR_V5_PLAN.md §3 (Phase 0B)"
  - "tests/regression/fixtures/golden_prompts.yaml"
  - "tests/regression/helpers.py"
  - "scripts/run_regression.py"
  - "scripts/record_baseline.py"
last_review: 2026-05-05
---

# V5 Phase 0B — Golden Evaluation Harness

> [REFACTOR_V5_PLAN.md §3 (Phase 0B)](../../REFACTOR_V5_PLAN.md) 의 SSOT 운용 가이드.
>
> V5 의 모든 후속 변경이 *성공인지 실패인지* 결정적으로 판정할 수 있는 회귀 테스트 framework. 사용자 보고를 기다리지 않고 *배포 전* 에 V5 가 v4.5.x baseline 보다 좋아졌는지를 측정한다.

---

## 1. 디렉토리 구조

```
tests/regression/
├── __init__.py                       # 모듈 진입
├── conftest.py                       # pytest fixtures
├── helpers.py                        # 공용 검증 함수 (pytest 무관 — CLI runner 도 사용)
├── README.md                         # 본 SSOT
├── test_golden_prompts.py            # Test 1/5 — Golden Prompt regression
├── test_visual_regression.py         # Test 2/5 — Playwright + 정적 SVG sanity
├── test_semantic_regression.py       # Test 3/5 — headline/body, deck/conclusion 등 점수
├── test_cost_regression.py           # Test 4/5 — 토큰·시간·호출 수 임계
├── test_completeness_regression.py   # Test 5/5 — 절단 검출 + placeholder + closing
├── test_state_compaction.py          # Phase 0C — 6-tier State + guards + 30% 절감
├── test_research_director.py         # Phase 1A — ≥80% expected_method 일치
├── test_evidence_dataset.py          # Phase 2A — AP-V5-24/25/26 + prose 인용 가드
└── fixtures/
    ├── golden_prompts.yaml           # 20건 Golden Prompt + expected metadata
    ├── baseline_v4_5_7.json          # v4.5.7 측정 결과 (record_baseline.py 가 채움)
    ├── sample_composed_reports/      # ComposedReport JSON sample (record_baseline.py 가 채움)
    │   └── _synthetic_smoke.json     # framework 자체의 smoke test 용 synthetic
    └── visual_baseline/              # Playwright screenshot baseline (선택, V5 진입 후 의미)
```

CLI 진입점:
```
scripts/run_regression.py             # 5종 회귀 테스트 일괄 실행 (pytest 미설치 환경 호환)
scripts/record_baseline.py            # v4.5.7 baseline 1회 박기 (실제 LLM 호출)
```

---

## 2. 5종 회귀 테스트 (Plan §3.4)

### 2.1 Golden Prompt Regression — `test_golden_prompts.py`

20개 prompt 의 *기본 정합성* 검증. 각 prompt 마다:
- mode 결정 (resolve_mode 휴리스틱이 expected 와 일치)
- 섹션 수 범위 [min, max] 안인지
- min_total_chars 임계 통과
- forbidden_chart_types 미등장 (CHART-AP-8 회귀)
- 지도 동작 (must_have_map / forbidden_map / forbidden_geo_annotations — CHART-AP-14)
- contradictions / watch_signals 강제 (Anti-pattern #5)

**Phase 0B 시점**: sample 미녹화면 mode 결정만 검증, 나머지 SKIP.

### 2.2 Visual Regression — `test_visual_regression.py`

Plan §3.4 (나) — Playwright 로 desktop / mobile / exhibit closeup 캡쳐 + pixel diff.
- Playwright 미설치 시 SKIP (graceful)
- lxml 기반 정적 SVG sanity (V5 Phase 6 Gate C 의 사전 구현) — lxml 미설치 시 SKIP
- pixel diff 임계 5% 초과 시 fail

**Phase 0B 시점**: dependency 미설치 환경에선 SKIP, framework spec 만 보존.

### 2.3 Semantic Regression — `test_semantic_regression.py`

Plan §3.4 (다) — 결정적 휴리스틱 점수:
- `headline_body_match_score ≥ 0.30`
- `deck_conclusion_alignment ≥ 0.20`
- `watch_signal_actionability ≥ 0.34` (전부 ambiguous 회귀 거절)
- `contradiction_preservation_check` (side_a/side_b 형식 + 동치 거절)

V5 Phase 7 DeskEditor 의 LLM 검수 도입 전 단계의 *최저선 가드*. threshold 는 [`SEMANTIC_THRESHOLDS`](test_semantic_regression.py) 가 SSOT.

### 2.4 Cost Regression — `test_cost_regression.py`

Plan §3.4 (라) — 토큰·시간·호출 수 임계:
- `total_tokens / baseline ≤ 2.0×` (V5 비용 폭주 차단)
- `llm_call_count ≤ 12`
- `elapsed_seconds / baseline ≤ 3.0×`

baseline 미녹화 시 informational only — telemetry 입력이 있을 때만 활성. SSOT: [`COST_THRESHOLDS`](test_cost_regression.py).

### 2.5 Completeness Regression — `test_completeness_regression.py`

Plan §3.4 (마) + Plan §6.4 (절단 검출) — `helpers.detect_truncation` 의 5종 시그널:

### 2.6 (Phase 0C) State Compaction — `test_state_compaction.py`

Plan §4.5 인수 기준 #1~#3:
- 6-tier State (RawContext / EvidencePack / AnalysisBrief / DraftReport / ExhibitPack / PublishManifest) 정의 검증.
- 8단계 입력 제한 강제 (`assert_input_is`, AP-V5-30) — composer 가 RawContext 를 받으면 fail, editor 가 EvidencePack 을 받으면 fail 등.
- RawContext → EvidencePack 압축이 ≥30% 토큰 감소.
- 9종 method enum 정합성 (`typing.get_args` 정적 검증).

### 2.8 (Phase 2A) EvidenceDataset Contract — `test_evidence_dataset.py`

Plan §8.7 인수 기준 #1~#4:
- `EvidenceDataset` 의 `source_ids ≥ 1` Pydantic min_length 가드 + 공백 source_id 도 거절.
- `DatasetField` 의 7종 semantic_type enum (`time`, `category`, `geo`, `quantity`, `ratio`, `score`, `text`).
- `TransformStep` 의 input/output_fields 가 `dataset.fields` 안에 있는지 추적성 검증.
- `EvidenceDatasetGuard.evaluate_chart` 가 AP-V5-24 (prose 부산물) / AP-V5-25 (출처 없음) / AP-V5-26 (source_id 누락) 를 결정적 차단.
- `ensure_chart_data_cited_in_prose` 가 차트 수치 ≥20% prose 인용 강제 — Phase 6 ChartCritic 질문 8 의 사전 구현.
- 24건 케이스, 모두 LLM 0.

### 2.7 (Phase 1A) Research Director — `test_research_director.py`

Plan §6.6 인수 기준 #1, #4:
- 모든 사건 (20건) 에 대해 AnalysisBrief 가 emit (heuristic fallback 으로도).
- Golden Prompt expected_method 와 `design_via_heuristics` 의 selected_methods ≥ 80% 일치 (현재 90%).
- strategic_query 카테고리 → strategic_hint=true + report_mode='strategy'.
- map_required → visual_constraints.must_have 에 'map'.
- no_charts → visual_constraints.forbidden 에 8종 차트 모두.
- SYSTEM_PROMPT 의 Plan §6.4 (9종 method + 6종 report_mode + 호르무즈/LLM/미중 예시) 명시 검증.
1. JSON 파싱 실패
2. 마지막 섹션 prose 가 문장부호 없이 끝남
3. closing 비어있음
4. deep 모드에서 watch_signals/contradictions 비어있음
5. 총 분량 < mode lower bound × 0.7

추가:
- 빈 prose 섹션 거절
- unresolved placeholder (`TODO`, `[FILL_IN]`, `{{var}}`, `[[ex:N]]` 미치환) 검출

---

## 3. Threshold 정책

| 영역 | Threshold | 위치 | Plan 근거 |
|------|-----------|------|-----------|
| `SEMANTIC_THRESHOLDS.headline_body_match` | 0.30 | test_semantic_regression.py | §3.4 (다) — Phase 7 LLM 검수 전 최저선 |
| `SEMANTIC_THRESHOLDS.deck_conclusion` | 0.20 | test_semantic_regression.py | §3.4 (다) |
| `SEMANTIC_THRESHOLDS.watch_signal_actionability` | 0.34 | test_semantic_regression.py | §3.4 (다) — 1/3 이상 비-ambiguous |
| `COST_THRESHOLDS.max_total_token_ratio` | 2.0 | test_cost_regression.py | §21 — V5 +67~79% 허용, 폭주 차단 |
| `COST_THRESHOLDS.max_llm_call_count` | 12 | test_cost_regression.py | §1 — 신문사 모델 8 + DeskEditor + 재호출 |
| `COST_THRESHOLDS.max_elapsed_seconds_factor` | 3.0 | test_cost_regression.py | 사용자 체감 — 3배 이상은 회귀 |
| `MODE_TARGET_CHARS_LOWER` | 1500/3500/6000 | helpers.py | §6.3 — fast/standard/deep |

threshold 변경은 Plan 의 해당 섹션 변경과 함께 진행. 코드만 변경하면 SSOT 정합성 깨짐.

---

## 4. 사용법

### 4.1 5종 모두 실행 (개발 중)

```bash
# pytest 사용 (권장)
python -m pytest tests/regression/ -v

# CLI runner (pytest 미설치 환경)
python scripts/run_regression.py
python scripts/run_regression.py --json out.json
```

### 4.2 일부만 실행

```bash
python scripts/run_regression.py --tests golden,completeness
python -m pytest tests/regression/test_golden_prompts.py -v
```

### 4.3 v4.5.7 baseline 박기 (1회만)

`.env` 와 Anthropic API / Claude Code CLI 가 가용한 환경에서:

```bash
python scripts/record_baseline.py                        # 20건 모두
python scripts/record_baseline.py --only geo_forecast_01 # 1건만
python scripts/record_baseline.py --dry-run              # 형식 확인
```

결과:
- `tests/regression/fixtures/sample_composed_reports/<id>.json` — 각 prompt 의 ComposedReport
- `tests/regression/fixtures/baseline_v4_5_7.json` — `recorded: true` + 측정 메트릭

baseline 박은 후 5종 회귀 테스트가 *전부 활성* 화 — 그 이전엔 sample 미녹화 prompt 는 SKIP 로 처리.

### 4.4 V5 Phase 진입 전 회귀 검증 (CI 절차)

```bash
# 1. 회귀 테스트 통과율 측정 — baseline 비교.
python scripts/run_regression.py --json artifacts/v5_phase_X_pre.json

# 2. 통과율이 baseline 보다 *낮으면* 진입 거절 (AP-V5-32).
#    예: 5종 평균 95% → V5 변경 후 90% 이면 회귀.
```

CI 본가동 시 `pytest --require-baseline` 옵션으로 baseline 미녹화 시 자동 fail.

---

## 5. fixture 형식 가드

`golden_prompts.yaml` 의 형식이 변경되면 `test_distribution_matches_plan_3_3` 와 `test_each_prompt_has_required_keys` 가 자동 검출. 새 expected 키 추가 시 본 README 의 §2 와 helpers.py 의 검증 함수도 함께 갱신.

`distribution` 섹션의 카테고리·건수가 Plan §3.3 의 표와 *byte-equal* 일치해야 한다.

---

## 6. V5 Phase 진입 시 갱신

Phase 0B 의 산출물은 V5 의 *모든* 후속 Phase 진입의 전제 조건 (Plan §22 #2). 새 Phase 진입 시:

| Phase | 본 harness 갱신 사항 |
|-------|---------------------|
| Phase 0C (State Compaction) | ✅ 적용 — `tests/regression/test_state_compaction.py` 신설. 6-tier State 정의 + 8단계 guards (Plan §4.4) + RawContext → EvidencePack 압축 ≥30% 토큰 감소 (Plan §4.5 #3) 검증 |
| Phase 1A (ResearchDirector) | ✅ 적용 — `tests/regression/test_research_director.py` 신설. `golden_prompts.yaml.expected_method` 가 9종 enum 안에 있는지 가드 (`test_each_expected_method_is_in_phase_1a_enum`) + `design_via_heuristics` 의 결정적 fallback 이 ≥80% 일치 (Plan §6.6 #4 임계 충족, 현재 90%). LLM ResearchDirector 의 일치률은 `record_baseline.py` 에서 measured |
| Phase 2A (EvidenceDataset) | ✅ 적용 — `tests/regression/test_evidence_dataset.py` 신설. `EvidenceDataset` 강화 (DatasetField/TransformStep) + `src/visual/evidence_dataset.py` Guard + AP-V5-24/25/26 검증. Phase 6 ChartCritic 진입 시 VisualPlanner 와 결합 |
| Phase 2B (Capability Registry) | forbidden_chart_types 가 Registry 의 experimental status 와 일관되는지 |
| Phase 6 (Chart Gate) | 4중 게이트 (Schema / Critic / Sanity / Fallback) 의 통과율을 Cost Regression 에 누적 |
| Phase 7 (DeskEditor) | publish/hold/kill 분포 측정을 Cost Regression 에 누적 |
| Phase 8 (Strategic Mode) | `expected.strategic_intent` 가 실제 모드 라우팅과 ≥90% 일치하는지 |

---

## 7. Anti-pattern (Plan §23 의 V5 Phase 0B 관련)

본 harness 가 직접 enforce 하는 anti-pattern:

- **AP-V5-32 — Golden Prompt 회귀 무시 금지.** V5 의 어떤 Phase 도 baseline 통과율을 떨어뜨려선 안 된다. CI 가 본 harness 통과 여부를 *진입 전제 조건* 으로 강제.
- **AP-V5-21 — 절단 검출 우회 금지.** `detect_truncation` 이 매 호출에서 실행되는지 Completeness Regression 이 검증.
- **CHART-AP-14 — 무관 지리 annotation.** Golden Prompt Regression 의 `forbidden_geo_annotations` 항목 (`Somaliland` 등) 이 사전 차단.
- **WRITE-AP-8 — max_tokens 절단.** Completeness Regression 의 underweight 시그널이 사후 검출.

---

## 7.5 v4.5.7 baseline 통과율 — 측정 결과 (2026-05-05 녹화)

20건 Golden Prompt 를 v4.5.7 환경에서 실측 녹화한 후 7종 회귀 테스트를 적용한 결과:

| 항목 | 수치 |
|------|------|
| Total tests | 177 |
| Passed | **124** (helper bug fix 후) |
| Failed | **52** |
| Skipped | 1 |
| **Pass rate** | **70.1%** |

**52 fail 의 분류** — Plan §22 #2 의 의도에 따라 "v4.5.7 가 도달하지 못한 항목 = V5 가 개선해야 할 영역" 의 baseline:

| Fail 카테고리 | 건수 | V5 어느 Phase 가 해결 |
|--------------|------|----------------------|
| `watch_signal_actionability=0` (semantic) | ~13 | NarrativeComposer 의 `direction` 필드 emit — Phase 5 또는 LLM SYSTEM_PROMPT 보강 |
| `total_chars_below_prompt_minimum` (completeness) | ~16 | 분량 부족 — Phase 5 (Word Budget + 절단 검출) |
| `deck_conclusion_low` (semantic) | ~3 | deck ↔ 결론 정합 — Phase 1 (Editor Pass) |
| `forbidden_chart_types_emitted` (golden) | ~16 | 사건 부적합 차트 emit — Phase 6 (Chart Critic) |
| 기타 | ~4 | min_total_chars / 기타 임계 |

이 분류는 *V5 의 후속 Phase 가 정확히 어디를 손봐야 하는지* 의 명세입니다. 임계를 낮춰 100% pass 로 만들면 V5 의 *진보 측정 자체가 불가능* 해지므로, fixture threshold 는 *V5 목표값* 으로 박힌 채 유지됩니다.

### AP-V5-32 강제 정책 — V5 후속 Phase 에서

- **fail count 가 52 보다 늘어나면 회귀** — V5 변경이 baseline 보다 나빠졌다는 신호.
- **fail count 가 줄어들면 V5 의 개선이 측정됨** — Phase 5 가 watch_signal direction 을 emit 시키면 ~13 fail 이 0 으로 줄어드는 식.
- 새 fixture / 새 카테고리 추가는 baseline 재측정 후에만.

CI 또는 운영 점검 시 다음 한 줄로 통과율 측정:

```
python -m pytest tests/regression/ --tb=no -q 2>&1 | tail -5
```

마지막 줄이 다음 형태로 떨어집니다:
```
=========== 124 passed, 52 failed, 1 skipped, 3 warnings in YYs ===========
```

**52 failed 가 baseline 정확값.** 새 commit 이 53+ 로 늘리면 PR 거절 정책.

---

## 8. Phase 0B 인수 기준 (Plan §3.5)

본 SSOT 가 충족시키는 항목:

1. ✅ **20개 Golden Prompt 가 모두 fixture 로 저장** — `fixtures/golden_prompts.yaml` (20건, 8개 카테고리 분포 정합).
2. ✅ **5종 회귀 테스트가 모두 자동 실행 가능** — pytest 또는 `scripts/run_regression.py`.
3. ⏳ **v4.5.x baseline 의 회귀 테스트 통과율이 측정되어 박혀 있어야** — `scripts/record_baseline.py` 1회 실행 후 충족. Phase 0B 코드 단계에선 stub 만 존재.
4. ✅ **V5 Phase 진입 시 회귀 테스트 통과 여부가 진입 전제 조건** — `pytest --require-baseline` 옵션 + 본 README §6 의 매트릭스.

#3 의 ⏳ 는 *코드 단계 완료 후* 실 환경에서 사용자가 baseline 박는 단계로, Phase 0B 자체의 완료 정의에 포함되지만 본 PR 에선 framework + stub 만 제공.
