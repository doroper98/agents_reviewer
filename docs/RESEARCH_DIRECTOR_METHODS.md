---
tier: 2
status: phase_1a_ssot
last_synced_with: v4.5.7
ssot_for:
  - "Phase 1A ResearchDirector 의 9종 분석기법 정의"
  - "각 method 별 적용 사건 / 입력 증거 / 출력 / 권장·금지 시각화"
  - "method ↔ 보고서 형태 (report_shape) 의 매핑"
depends_on:
  - "REFACTOR_V5_PLAN.md §6 (Phase 1A)"
  - "src/state/models.py:AnalysisMethod (9종 enum SSOT)"
  - "src/agents/research_director.py:SYSTEM_PROMPT (Plan §6.4 그대로)"
  - "tests/regression/fixtures/golden_prompts.yaml (expected_method)"
last_review: 2026-05-05
---

# V5 Phase 1A — ResearchDirector 9종 분석기법 SSOT

> 본 문서는 Phase 1A 의 ResearchDirector 가 *기자에게 사전 지시* 할 때 사용하는 9종 분석기법의 정의·적용 사건·입력·출력·권장 시각화를 사람-친화적으로 정리한 SSOT 다. enum 정의는 [src/state/models.py:AnalysisMethod](../src/state/models.py), 시스템 프롬프트의 영문 / 한국어 라벨은 [src/agents/research_director.py:SYSTEM_PROMPT](../src/agents/research_director.py).
>
> **새 method 추가 시** — 본 문서 §1~9 중 적합한 자리에 항목 추가 + `AnalysisMethod.method` Literal 확장 + `research_director.py:SYSTEM_PROMPT` 의 enum 안내 갱신 + `tests/regression/test_research_director.py` 의 분포 가드 갱신. 1곳이라도 누락되면 SSOT 정합성 깨짐.
>
> **9종 enum 외 method 사용 금지** — Phase 1A 는 9종으로 동결. 신규 method 는 V5 정식 출시 후 별도 RFC.

---

## 0. method 선택 원칙 (Plan §6.4)

- 1개 사건에 **1~3개** method 선정. 4개 이상은 *분석 마비* 신호.
- 사건마다 적합 method 다름. *모든 사건에 같은 기법* 적용 금지.
- `why_this_method` 필드에 1~2문장 정당화 *반드시* 기록.
- ResearchDirector 의 선택은 [src/state/models.py:AnalysisBrief.selected_methods](../src/state/models.py) 에 emit, Composer / VisualPlanner / DeskEditor 가 후속 단계에서 본 근거를 본다.

대표 매핑 (Plan §6.4 정본):

| 사건 | 1순위 method | 2순위 method |
|------|-------------|--------------|
| 호르무즈 봉쇄 시 한국 LNG 영향 | `transmission_channel` | `scenario_tree` |
| Mac Studio 도입 시 전략 결정 | `decision_matrix` | `pre_mortem` |
| 미중 반도체 갈등 5년 흐름 | `comparative` | `transmission_timeline` |
| 이스라엘 이란 충돌 가능성 | `scenario_tree` | `stakeholder_matrix` |
| OpenAI o3 vs Sonnet 4.6 | `comparative` | `stakeholder_matrix` |
| LLM 의사결정 보조 윤리적 한계 | `comparative` | `ACH` |

---

## 1. ACH — Analysis of Competing Hypotheses (가설 경쟁 분석)

**무엇:** 같은 사실에 대해 *여러 가설* 이 경쟁할 때, 각 가설을 행으로 / 증거를 열로 두는 매트릭스를 만들어 *어느 가설이 가장 많은 증거를 설명* 하는지 평가. 정보분석 학계의 표준 기법 (Heuer 1999).

**적용 사건:**
- "정말 X 가 일어났나?" 같은 *사실 경쟁* 사건 (사건 진위, 동기 추정).
- 출처마다 다른 시각이 동시에 존재하는 상황.
- 윤리·철학 논의 (서로 다른 입장의 강도 비교).

**입력 (`required_evidence`):** `primary`, `secondary`, `expert` — 가설별로 *독립적인* 출처가 필수.

**출력 — 보고서에 등장해야 할 것:**
- 가설 ≥ 3개의 명시적 라벨.
- 가설 × 증거 매트릭스 (heatmap 또는 결정 매트릭스 형태).
- 각 가설의 *반대 증거* 명시 (Anti-pattern #5: 봉합 금지).

**권장 시각화 (`required_exhibits`):** `heatmap` (가설 × 증거 매트릭스).

**금지 시각화 (`forbidden_visuals`):** `donut` — 비중 비교는 ACH 와 무관.

**대표 사건 — Golden Prompt 매칭:** *없음* (본 fixture 의 20건엔 명시 X). V5 운영 후 누적 시 본 표 갱신.

---

## 2. scenario_tree — 분기 시나리오 트리

**무엇:** 사건이 갈라질 미래 분기를 *명시적 트리* 로 정렬. 각 분기에 확률·영향·트리거를 매기고, 분기 사이의 leading indicator (transition signal) 를 추적.

**적용 사건:**
- "다음 6개월 안에 X 가 일어날까?" 형태의 *예측형*.
- 위기·분쟁의 escalation / de-escalation 분기.
- 정책 결과 예측 (시행되면 / 폐기되면).

**입력 (`required_evidence`):** `primary` (사실 자료) + `secondary` (분석가 의견).

**출력:**
- 시나리오 ≥ 3개 — 보통 base / bull (escalation) / bear (de-escalation).
- 각 시나리오의 확률 (정량) + 영향 (정성·정량).
- watch_signals — 시나리오 분기 판별 신호 (Plan §1 의 Watchlist 등록 트리거).

**권장 시각화:** `bubble` (시나리오 × 확률 × 영향).

**금지 시각화:** *없음* (사건 적합도 따라 다양).

**대표 사건 (Golden Prompt):**
- `geo_forecast_01` — 이스라엘 이란 직접 충돌 가능성 6개월 시각.
- `geo_forecast_02` — 대만 해협 위기 시나리오.

---

## 3. transmission_channel — 전이 채널 분석 (금융·정책·공급망)

**무엇:** 한 충격 (외부 사건) 이 어떤 *경로* 로 본 시스템에 전파되는지 단계별 추적. 한국 거시·산업 분석에서 가장 자주 쓰이는 기법.

**적용 사건:**
- "X 가 우리 시장 / 산업 / 가격에 미치는 영향" — 호르무즈 봉쇄, FOMC 인하, 환율 변동.
- 공급망 / 자금 흐름 / 정책 전이.

**입력 (`required_evidence`):** `primary` — 정확한 경로 추적이 핵심.

**출력:**
- 전이 단계 명시 (예: 호르무즈 봉쇄 → 보험료 → LNG 도입가 → 한국 가스공사 → 산업 비용).
- 각 단계의 *시간 지연* (하루 / 일주일 / 분기).
- 각 단계의 *증폭률* (탄성).

**권장 시각화 (`required_exhibits`):** `bar` (영향 비교) + `stacked` (단계별 누적).

**금지 시각화:** `network` — 노드-엣지 그래프는 *전이 단계 시간 순서* 를 흐리게 만듬.

**대표 사건 (Golden Prompt):**
- `fin_transmission_01` — 엔 캐리 unwind → KOSPI 옵션 변동성.
- `fin_transmission_02` — FOMC 인하 → 한국 채권 시장.
- `fin_transmission_03` — 비트코인 ETF 자금 유입 → 매크로 유동성 상관.
- `map_required_01` — 호르무즈 봉쇄 → 한국 LNG·원유 (지도 + 전이).

---

## 4. stakeholder_matrix — 이해관계자 매트릭스

**무엇:** 사건의 핵심 *행위자* (정부 / 기업 / 분석가 / 시장) 별 이해·인센티브·동맹·대립 구도를 매트릭스로 정렬.

**적용 사건:**
- 정책 / 규제 / 기술 도입 — 다양한 행위자가 다른 입장을 가질 때.
- 지정학적 사건 — 다국 행위자.
- 안보·외교 — 양측·삼각·다자 구도.

**입력:** `primary` + `secondary` — 각 행위자의 *공식 입장* 자료.

**출력:**
- 행위자 5~10명의 한 줄 요약 (`actors_summary`).
- 행위자 × 인센티브·우려·자원 매트릭스.
- 동맹·대립 관계 다이어그램.

**권장 시각화 (`required_exhibits`):** `network` (행위자 관계도) + `stacked` (이해관계 분포).

**금지 시각화:** *없음*.

**대표 사건 (Golden Prompt):**
- `geo_forecast_03` — 북한 핵실험 시 한국·일본 안보.
- `tech_struct_01` — Claude 4.7 출시 시 LG에너지솔루션 통합.
- `policy_dec_01` — EU AI Act high-risk 분류.
- `policy_dec_02` — 한국 가상자산 과세 유예.
- `map_required_02` — 남중국해 베트남·필리핀 EEZ 분쟁.

---

## 5. fault_tree — 결함 트리 분석

**무엇:** 시스템 실패 / 사고 / 오작동의 *원인 사슬* 을 결과부터 역추적. 항공·원자력 안전 분야 표준.

**적용 사건:**
- 사고·오작동 분석 (사후).
- 시스템 취약점 평가 (사전 — fault tree 의 역방향 사용).
- "왜 이게 일어났는가" 의 인과 추적.

**입력:** `primary` (1차 자료) + `expert` (도메인 전문가 의견).

**출력:**
- 최상위 실패 노드 + 하위 원인 노드의 트리 구조.
- AND / OR 게이트 (어떤 조합이 실패를 발생시키는지).
- 차단점 (break_point) — 사슬을 끊을 수 있는 단계.

**권장 시각화:** 사용자 정의 `fault_tree` SVG (V5 Phase 2B 의 experimental 카테고리).

**금지 시각화:** `donut` (비중 비교는 무관).

**대표 사건 (Golden Prompt):** *없음* — V5 운영 후 사고 사건이 들어오면 추가.

---

## 6. decision_matrix — 결정 매트릭스 (Phase 8 strategic mode 의 핵심)

**무엇:** 의사결정 보조 — 옵션 (행) × 평가 기준 (열) 의 점수표. 사용자가 명시한 기준 + 추론 기준을 함께 매트릭스로 정렬해 권고 도출.

**적용 사건:**
- "X 를 한다고 했을 때 어떤 전략을 취해야 할까" — Phase 8 strategic mode.
- 도입 결정 (Mac Studio, LLM 인프라).
- 투자·자원 배분 결정.

**입력:** `secondary` (시장 자료) + `expert` (도메인 의견).

**출력:**
- 옵션 ≥ 3개 (Plan §1 §9.3 — 2개 이하는 이분법, 6개 이상은 분석 마비).
- 평가 기준 — 사용자 명시 A·B·C + 추론 기준 (비용, 시간, 가역성 등) 명시.
- 권고 1개 옵션 명시 + 근거 ≥ 3개.
- watch_signals — 권고가 *틀렸다고 판단되는 조건* (kill_switch).

**권장 시각화 (`required_exhibits`):** `heatmap` 또는 `decision_matrix` (V5 Phase 2B 의 safe 카테고리 등록).

**금지 시각화:** `network` — 행위자 관계가 핵심이 아님.

**대표 사건 (Golden Prompt — strategic_query 카테고리):**
- `strategy_01` — Mac Studio 도입 비용·성능·확장성.
- `strategy_02` — 사내 LLM 인프라 자체 구축 vs 클라우드.
- `strategy_03` — 시리즈 A 다음 라운드 시기.

---

## 7. pre_mortem — 사전 부검

**무엇:** "이 옵션 / 결정이 *실패했다고* 가정하고, 실패 원인을 역추적." Klein (2007) 의 의사결정 보조 기법.

**적용 사건:**
- 의사결정 보조 (decision_matrix 와 짝).
- 권고 / 정책 / 투자 결정 직전.
- 위험 평가.

**입력:** `expert` + `model_inference` — 미래 실패 시나리오는 추론 영역.

**출력:**
- 옵션 / 권고당 실패 모드 ≥ 2개.
- 각 실패 모드의 *leading indicator* (조기 경보).
- 실패 시 대안 (옵션 N → 옵션 M 전환 트리거).

**권장 시각화:** fishbone (어골도) — V5 Phase 2B 의 experimental 카테고리.

**금지 시각화:** *없음*.

**대표 사건:** Phase 8 deep 모드 strategic_query 보고서 *전부* (Plan §9.5 — pre_mortem 은 deep 모드 권고).

---

## 8. transmission_timeline — 전이 타임라인

**무엇:** 사건 → 결과의 *시계열* 추적. 변천·이력·장기 흐름을 정렬.

**적용 사건:**
- "지난 5년 미중 반도체 갈등 흐름" 같은 *장기 추세* 분석.
- 정책 / 규제의 시행 → 효과 → 재시행 사이클.
- 기술 채택 곡선.

**입력:** `primary` + `secondary` — 시점 별 정확한 자료.

**출력:**
- 타임라인 — 결정적 사건 ≥ 5개.
- 각 사건의 *전후 변화* (지표 / 시장 / 정책).
- 추세선 (꺾임점 / 가속·감속 구간).

**권장 시각화 (`required_exhibits`):** `gantt` (단계별 구간) + `line` (지표 추세).

**금지 시각화:** *없음*.

**대표 사건 (Golden Prompt):**
- `tech_struct_02` — TSMC 2nm 양산 지연 → HBM4 영향.
- `long_deep_01` — 미중 반도체 갈등 5년 흐름 + 향후.

---

## 9. comparative — 비교 분석

**무엇:** vs 과거·동종·다른 국가·다른 정책 — *비교를 통해* 사건의 의미·우열·차이를 정렬.

**적용 사건:**
- vs 사례 (이전 위기, 다른 국가의 같은 정책).
- A vs B 모델·서비스·전략.
- 동시대 다국 정책 비교.
- 윤리·철학적 입장 비교.

**입력:** `primary` + `secondary` + `expert` — 비교 양측 모두 자료 충실 필수.

**출력:**
- 비교 양측 (또는 다측) 의 *명시적* 정의.
- 비교 차원 ≥ 3개 (예: 비용 / 성능 / 확장성).
- 차원 별 우열 + 종합 판정 (단 ACH 처럼 봉합 금지).

**권장 시각화 (`required_exhibits`):** `bar` (차원 별 비교) + `heatmap` (다차원 매트릭스).

**금지 시각화:** `network` — 비교는 *행위자 관계* 가 아님.

**대표 사건 (Golden Prompt):**
- `tech_struct_03` — OpenAI o3 vs Sonnet 4.6 포지셔닝.
- `no_charts_01` — LLM 의사결정 보조 한계 윤리적 논의.
- `no_charts_02` — 프라이버시 vs 효율성 trade-off.
- `long_deep_02` — 글로벌 AI 거버넌스 EU/US/중국/한국.

---

## 10. method ↔ report_shape 매핑 (Phase 1A 디폴트)

ResearchDirector 가 method 선정 후 자동으로 report_shape 의 must_have_sections 을 결정한다. 9종 method × 사건 카테고리 별 디폴트는 [src/agents/research_director.py:design_via_heuristics](../src/agents/research_director.py) 의 결정적 fallback 가 SSOT.

| method | 권장 must_have_sections (analytical mode) |
|--------|------------------------------------------|
| ACH | `situation` / `hypothesis_a` / `hypothesis_b` / `evidence_matrix` / `judgment` |
| scenario_tree | `situation` / `mechanism` / `scenarios` / `watch` |
| transmission_channel | `situation` / `mechanism` / `transmission_path` / `impact` / `watch` |
| stakeholder_matrix | `situation` / `actors` / `dynamics` / `outlook` / `watch` |
| fault_tree | `situation` / `failure_chain` / `break_points` / `prevention` |
| decision_matrix | `decision_context` / `options` / `criteria` / `matrix` / `recommendation` / `watch` |
| pre_mortem | (decision_matrix 의 보조 — 단독 사용 X) |
| transmission_timeline | `situation` / `historical_arc` / `current_position` / `forward` / `watch` |
| comparative | `situation` / `subjects` / `dimensions` / `judgment` / `watch` |

---

## 11. method 추가 절차 (V5 정식 출시 후)

본 문서 §1~9 의 9종으로 Phase 1A 동결. 신규 method 추가는 v5 정식 출시 후 다음 절차로:

1. **RFC 작성** — 새 method 의 적용 사건·입력·출력·권장 시각화 명시.
2. **3건 이상 retrospective** — 기존 V5 보고서 3건 이상에서 *기존 9종 으로 다루지 못한* 분석 결함을 보여 RFC 정당화.
3. **`AnalysisMethod.method` Literal 확장** — `src/state/models.py`.
4. **research_director.py SYSTEM_PROMPT 갱신** — Plan §6.4 의 enum 안내.
5. **본 문서 §1~9 사이에 새 §N 추가** + §0 의 대표 매핑 표 갱신.
6. **회귀 테스트 갱신** — `tests/regression/test_research_director.py` 의 분포 가드 + Golden Prompt fixture 의 expected_method 가드.
7. **CHANGELOG 의 V5 버전 entry 에 명시.**

step 1~7 모두 통과 후에만 method 추가. 누락 시 SSOT 정합성 깨짐.
