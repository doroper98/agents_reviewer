---
tier: 2
status: phase_8_ssot
last_synced_with: v4.5.7
ssot_for:
  - "Phase 8 Strategic Mode 의 composer system prompt 확장 정본"
  - "전략 보고서의 7개 디폴트 섹션 구조 + 필수 출력"
  - "전략 질의 감지 패턴 (명시 prefix + 정규식 + LLM fallback)"
depends_on:
  - "REFACTOR_V5_PLAN.md §17 (Phase 8 SSOT)"
  - "REFACTOR_V5_PLAN.md §18 (Phase 8A — 8개 필수 출력 강화)"
  - "src/agents/strategic_router.py (감지 코드 SSOT)"
  - "src/state/models.py:StrategicReport (모델 SSOT)"
last_review: 2026-05-05
---

# V5 Phase 8 — Strategic Mode (의사결정 보조)

> 본 문서는 Phase 8 의 *Composer system prompt 확장* + *전략 질의 감지 패턴* + *필수 출력 구조* 의 사람-친화 SSOT 다. 코드 SSOT 는 [src/agents/strategic_router.py](../src/agents/strategic_router.py) (감지) 와 [src/state/models.py:StrategicReport](../src/state/models.py) (모델). 본 문서가 변경되면 두 코드 SSOT 와 회귀 테스트도 함께 갱신.

---

## 1. 분석 모드 vs 전략 모드 (Plan §17.1)

두 모드는 보고서의 *지향점* 이 정반대다.

| 차원 | 분석 모드 (Analytical) | 전략 모드 (Strategic) |
|------|------------------------|------------------------|
| 시제 | 후행적 (과거 → 현재 분석) + 예측 | 선행적 (미래 행동 결정) |
| 자세 | 서술적 ("X 가 일어났다") | 처방적 ("X 를 해야 한다") |
| 핵심 산출 | 시나리오 + 감시 신호 | **옵션 + 권고 + 감시 신호** |
| user_intent | what_happened, why_happened, what_next 등 | **what_to_do (전용)** |
| 시각화 강조 | timeline / network / choropleth | **decision matrix / bubble (impact × feasibility)** |
| 결정 매트릭스 | 부수적 | **필수** |
| 권고 | 흐릿하게 본문에 흩어짐 | **명시적 별도 섹션** |
| Pre-mortem | 선택적 | **deep 모드 필수** |

v4.5.7 는 사용자가 전략 질의를 보내도 분석 모드로 처리한다. Plan §17 의 핵심 — 사용자가 *처방* 을 원할 때 *서술* 보고서로 응답하지 않게.

---

## 2. 전략 질의 감지 — 3-경로 (Plan §17.2)

우선순위 순:

### (가) 명시 Prefix (Plan §18.2)

가장 명확하고 비용이 들지 않는다. 7종 prefix:

```
?전략 <질의>     → strategic mode
?분석 <질의>     → analytical (default)
?예측 <질의>     → forecast (analytical 의 하위)
?비교 <질의>     → comparative (analytical 의 하위)
?지도 <질의>     → geo-priority (visual_constraints 에 map_required)
?짧게 <질의>     → fast mode 강제
?심층 <질의>     → deep mode 강제
```

prefix 가 있으면 *나머지 감지 경로 무시* 하고 즉시 분기.

### (나) 패턴 매칭 (Plan §17.2)

prefix 없을 때 결정적 정규식 8종 (`STRATEGIC_PATTERNS`):

```
어떤 전략
어떻게 해야
어떤 (선택|결정|판단|길)
취해야 (하|할)
(고려|반영)했을 때.{0,30}(전략|결정|선택)
옵션.{0,10}(평가|비교|선택)
(어느 쪽|어디로|어느 방향)으로
vs[.\s]
```

하나라도 매칭되면 strategic mode 후보. 단 (다) 의 LLM 분류와 *둘 다 strategic* 일 때만 활성.

### (다) LLM intent classifier (fallback)

ContextAnalyst 가 사실 수집과 함께 user_intent 분류 (추가 LLM 호출 없이). 결과 user_intent = `what_to_do` 면 strategic mode.

### 모호 시 정책 (AP-V5-23)

prefix 없음 + 패턴 매칭 모호 + LLM 분류 ambiguous → **분석 모드 기본값**. 사용자가 `?전략` prefix 로 명시 재시도하는 게 안전.

---

## 3. Composer 의 전략 모드 SYSTEM_PROMPT 확장 (Plan §17.3)

기존 NarrativeComposer 의 SYSTEM_PROMPT 를 베이스로, `strategic_mode=True` 일 때 다음 지시를 *추가*:

```
=== 전략 모드 추가 지시 (strategic_mode=True 일 때만) ===

본 보고서는 사용자의 *의사결정* 을 보조한다. 분석 보고서가 아니다.

다음 7개 섹션 구조를 *강한 디폴트* 로 사용한다 (사건 성격에 따라
자율 변형 가능하나 옵션 ≥ 3개 + 권고 명시는 강제):

1. 결정 컨텍스트 — 무엇을 결정하는가, 누가 결정하는가, 언제까지,
   되돌릴 수 있는가
2. 옵션 도출 — 3개 이상 5개 이하. *2개 미만 금지* (이분법적 사고
   차단). *6개 이상 금지* (분석 마비 차단). 각 옵션은 한 줄 요약 +
   핵심 행동.
3. 평가 기준 — 사용자가 명시한 기준 (A, B, C 등) 을 그대로 보존
   하면서, 누락된 중요 기준을 추론해 추가 (예: 비용, 시간, 가역성,
   정치적 비용, 평판 영향).
4. 옵션 × 기준 매트릭스 — 시각화 *필수*. Vega-Lite heatmap 또는
   점수표 또는 bubble chart (영향 × 실현가능성).
5. Pre-mortem — 옵션별 실패 시나리오. "이 옵션이 실패한다면 *어떤
   이유로* 실패할까?" 옵션당 2~3개 실패 모드 + 각 실패의 leading
   indicator. **deep 모드에서 필수.**
6. 권고 — 한 옵션을 명시적으로 선택. "옵션 N 을 권고한다." 형식.
   근거 3개 이상. **권고 부재는 KILL 사유.**
7. 감시 신호 — 권고가 *틀렸다고 판단되는 조건*. "X 가 발생하면
   옵션 N 을 포기하고 옵션 M 으로 전환한다" 형식 (kill switch).

핵심 어법 규칙:
- 모호함 금지. "고려해야 할 수도 있다" 같은 보수 어법보다 "옵션 N 이
  옵션 M 보다 X 점 앞선다" 같은 명료한 표현을 우선한다.
- 권고를 흐리지 않는다. "각 옵션에 장단점이 있다" 식의 봉합은
  KILL 사유다.
- 사용자가 명시한 기준 A·B·C 를 *반드시* 평가 매트릭스의 행 또는
  열로 사용. 추가 추론 기준은 명시적 표시 (예: "기준 D — 추론").
```

---

## 4. 필수 시각화 — 전략 모드 전용 (Plan §17.5)

전략 모드 보고서는 다음 시각화를 *최소 1개 이상* 포함 — Phase 6 ChartCritic 이 강제.

### (가) 결정 매트릭스 (필수)

Vega-Lite heatmap 또는 점수표. 옵션 (행) × 기준 (열) 의 셀이 점수 (예: 1~5) 또는 정성 등급 (강/중/약). 본문 권고가 이 매트릭스의 어느 셀들에서 도출되는지 *직접 인용* 해야 (Phase 6 Critic 의 질문 4번).

`docs/VISUAL_CAPABILITY_REGISTRY.yaml` 에 `decision_matrix: status=safe` 로 등재됨 (Phase 2B).

### (나) 옵션 비교 bubble chart (권고)

x = 영향 (impact), y = 실현가능성 (feasibility), size = 비용 또는 위험. 4분면이 즉시 시각화.

### (다) Pre-mortem fishbone (deep 모드 권고)

권고 옵션의 실패 원인을 fishbone 으로 분해. 현재 Capability Registry 미등재 — Phase 8 정식 활성 후 등재 검토.

---

## 5. decision_brief Layout Primitive (Plan §17.4)

분석 모드의 9종 layout 외에 전략 모드 *전용* 으로 1종을 추가:

| layout_id | 시각 효과 | 적용 위치 |
|-----------|-----------|-----------|
| `decision_brief` | 결정 컨텍스트가 hero 영역, 옵션이 numbered cards 그리드, 매트릭스가 full-width, 권고가 signature_summary 위치 | 전략 모드 보고서 전용 |

**AP-V5-3 (layout 추가 금지) 와 충돌하지 않음** — AP-V5-3 는 *분석 모드 9종 동결* 의미. 전략 모드 `decision_brief` 는 별도 vocab. 단 전략 모드도 layout 추가는 더 받지 않음 (1종으로 동결).

**AP-V5-20 (decision_brief 의 분석 모드 사용 금지)** — LayoutTypesetter 가 강제. 모드 분리를 layout 차원에서도 강제.

---

## 6. KILL_RULES_STRATEGIC (Plan §17.6 + §18.4)

전략 모드는 분석 모드의 KILL_RULES (논리 5 + 시각 3) *그대로* 적용 + 다음 추가. 전략 모드는 *단독 발화* (분석 모드의 "둘 이상" 정책과 다름).

```python
KILL_RULES_STRATEGIC = {
    # Plan §17.6 — 옵션 / 매트릭스 / 권고 / pre-mortem / 기준 정합
    "options_too_few":          len(options) < 3,
    "no_decision_matrix":       not has_decision_matrix,
    "recommendation_absent":    not recommendation or len(rationale) < 50,
    "premortem_missing_deep":   mode == "deep" and not premortems,
    "criteria_not_user_aligned": not all_user_criteria_present,

    # Plan §18.4 — 추가 강화
    "decision_statement_missing": not decision_statement,
    "action_plan_missing":        not action_plan_30_60_90,
    "kill_switch_missing":        len(kill_switch_conditions) == 0,
    "matrix_score_uniform":       _is_matrix_uniform(scores),
}
```

**AP-V5-18 갱신 (Plan §18.4 정책 완화)** — 옵션 정책이 *옵션 0개 → hold + 사용자 안내*, 옵션 1~5 → 허용 (1개는 "단일 옵션 권고임" 명시), 옵션 6 이상 → KILL. 검수자의 지적 (법적 강제 결정 등 진짜 단일 옵션 사례) 을 반영.

---

## 7. 한계 — 전략 모드가 *못 하는* 것 (Plan §17.8)

솔직히 짚어둔다. 전략 모드는 *제한적인 의사결정 보조* 다.

- LLM 의 평가 점수는 결국 *학습 데이터 기반 추론*. 사용자의 진짜 utility function 은 모름. 매트릭스 점수를 *최종 결정* 으로 받지 말고 *생각의 출발점* 으로 사용.
- 권고는 *현재 시점의 일반론적 우위* 를 가리킴. 사용자의 사적 정보 (평판 자산, 비공개 자원, 정치적 동맹) 를 반영 못 함.
- 실제 결정에는 LLM 이 잡지 못하는 *암묵 지식* 이 큰 부분.

이 한계를 보고서 footer 에 명시: "본 권고는 의사결정 보조용이다. 최종 판단은 사용자의 책임이다."

---

## 8. SSOT 정합성

| 영역 | 위치 |
|------|------|
| 사람-친화 본문 | 본 문서 |
| 감지 코드 (prefix + 패턴) | [src/agents/strategic_router.py](../src/agents/strategic_router.py) |
| 모델 (StrategicReport / Option / Matrix / ActionPlan) | [src/state/models.py](../src/state/models.py) |
| KILL_RULES 코드 | [src/agents/desk_editor.py](../src/agents/desk_editor.py) (분석 모드 KILL_RULES 재사용) + strategic 추가는 별도 함수 |
| 회귀 테스트 | [tests/regression/test_strategic_mode.py](../tests/regression/test_strategic_mode.py) |

본 문서 §3 (system prompt) / §6 (KILL_RULES) 변경 시 위 코드 SSOT + 회귀 테스트 *모두* 동시 갱신.
