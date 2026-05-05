---
tier: 2
last_synced_with: v4.5.7
status: partially_legacy
ssot_for:
  - "CLI Gate (py_compile) 정책"
  - "Quality Gate 단위 테스트 (deprecated 모듈 동작 보존 검증)"
  - "테스트 시나리오 카탈로그"
depends_on:
  - "src/agents/* (활성: context_analyst + narrative_composer 2개. 그 외 7개는 v4.0.0 부터 호출 안 됨)"
  - "src/tests/test_quality_gates.py (deprecated 모듈의 단위 테스트 — 호출되지 않는 5-gate 의 동작 보존 검증 목적)"
  - "docs/CATALOGS.md"
last_review: 2026-05-05
note: "본 문서의 §2 Quality Gates 단위 테스트는 v4.0.0 부터 호출 경로에서 비활성. 단위 테스트 자체는 여전히 실행 가능 (legacy 모듈의 동작 보존 검증). [REFACTOR_V5_PLAN.md Phase 0B](../REFACTOR_V5_PLAN.md) 가 신설할 Golden Prompt 회귀 하네스로 v5 출시 시점에 대체 예정."
---

# Event Analysis Team — Testing Strategy

> **현재 baseline (v4.5.7)**: §1 CLI Gate (`py_compile`) 가 핵심. §2 Quality Gates 단위 테스트는 deprecated 모듈의 *동작 보존 검증* 목적으로만 실행되며, v4.5.7 의 실제 호출 경로 (ContextAnalyst → NarrativeComposer) 에 대한 회귀 검증은 [REFACTOR_V5_PLAN.md Phase 0B](../REFACTOR_V5_PLAN.md) 의 Golden Prompt 20건 + 5종 회귀 테스트가 신설될 때 본격 도입된다. §3 Manual Verification 의 "7개 에이전트 모두 출력 생성 확인" 같은 항목은 v3 시대의 표현이며, v4.5.7 에서는 ContextAnalyst + NarrativeComposer 2개 출력만 검증한다.

## 1. CLI Gate (구문 검사)

```bash
find src -name "*.py" -print0 | xargs -0 python -m py_compile
```

전 파일 무오류 통과 필수. CI/배포 직전 필수.

## 2. Unit Tests — Quality Gates (V3 Step 4, v2.8.0)

```bash
python -m pytest src/tests/test_quality_gates.py -v
```

테스트 모듈 `src/tests/test_quality_gates.py` 가 다음을 검증:

### 2.1 Claim-Evidence 추적성 (Anti-pattern #4)
- `TestClaimEvidenceContract.test_empty_evidence_ids_raises` — `Claim(evidence_ids=[])` 시 `ValidationError`.
- `test_single_evidence_id_passes` — `evidence_ids=["E-1"]` 정상.
- `test_evidence_smoke` — Evidence 모델 기본.

### 2.2 ConfidenceProfile 3축 (Anti-pattern #10)
- `TestConfidenceProfile.test_aggregate_weighted_average` — `0.4·sd + 0.3·df + 0.3·ec` 정확.
- `test_aggregate_all_max` / `test_axis_bounds_enforced` — 0.0~1.0 강제.

### 2.3 Gate 1 — Plan Sanity 휴리스틱
- `TestGate1PlanSanity.test_pass_minimal_strategy` — 정상 strategy 통과.
- `test_fail_strategy_none` — None 입력 거절.
- `test_fail_short_question` — 너무 짧은 core_question 거절.

### 2.4 Gate 2 — Coverage Check 휴리스틱
- `TestGate2Coverage.test_pass_when_all_questions_answered` — 모든 question 매칭 시 통과.
- `test_fail_when_question_unanswered` — 미답변 question 시 실패 + 사유.
- `test_fail_when_judgment_missing` — judgment None 거절.
- `test_fail_when_main_judgment_blank` / `test_fail_when_counter_hypothesis_blank` — 종합 판단/반대 가설 빈 문자열 거절.

### 2.5 Synthesis Judge 모순 노출 (Anti-pattern #5)
- `TestSynthesisJudgeContradictions.test_lexical_conflict_surfaces` — "상승" vs "하락" 어휘 충돌 페어가 contradictions[] 에 노출. resolution 에 채택 명시 (봉합 X).
- `test_no_findings_returns_marked_empty_verdict` — 빈 findings 입력 시 명시적 "finding 없음" 판단 (gate 2 가 reject 가능).
- `test_consensus_no_contradictions` — 충돌 없을 때 contradictions 빈 배열 + main_judgment 채워짐.

### 2.6 모델 체인 스모크
- `test_chain_smoke` — Evidence → Claim → AnalyticalFinding 의 evidence_id 매칭.

총 18 케이스. 단위 테스트는 LLM 호출 없는 휴리스틱 경로만 검증 (테스트 stub config 가 `use_cli_mode=False`). LLM-as-judge 경로는 회귀 테스트 (수동) 에서만 검증.

## 3. Manual Verification

1. Send test message via Telegram
2. 7개 에이전트 모두 출력 생성 확인 (현재 구성, [docs/CATALOGS.md](CATALOGS.md))
3. HTML 보고서가 브라우저에서 정상 렌더링되는지 확인
4. 시나리오별 균형 분석 4단락 (핵심 판단/비대칭/민감도/한계) 가독성 확인
5. **V3 Step 4 추가**: 텔레그램 진행 메시지에 "🧮 종합 판단관" 표시 + 모순 발견 시 contradiction 건수 노출 확인. Gate 실패 시 "⚠️ 부분 분석 완료. {gate} 실패 ({reason})" 알림 도달 확인.

## 4. Test Scenarios

| Scenario | Input | Expected |
|----------|-------|----------|
| Basic event | "미국 관세 인상 분석" | 전체 7-에이전트 보고서 + Gate 1/2 통과 |
| Tech event | "OpenAI GPT-5 출시 분석" | 기술 중심 분석 + tech_decomposition archetype |
| Geopolitical | "러시아-우크라이나 전쟁 분석" | 지정학 중심 보고서 + 잠재적 모순 노출 |
| Conflict-prone | "호르무즈 해협 위기 분석" | Synthesis Judge contradictions 1건 이상 |
| Stress | (가짜 빈 evidence) | Gate 2 실패 → 부분 분석 알림 |
