---
tier: 2
status: v5_validation_log
last_synced_with: v5.0.0
ssot_for:
  - "V5 phase 별 회귀 테스트 통과율 측정 결과"
  - "v4.5.7 baseline 대비 V5 진보 수치"
  - "flag-by-flag 효과 측정 — append-only 운영 로그"
depends_on:
  - "tests/regression/ (회귀 테스트 17종)"
  - "src/config.py (Config.enable_* fields)"
  - "REFACTOR_V5_PLAN.md §22 (인수 기준)"
last_review: 2026-05-05
---

# V5 Test Results — 통과율 측정 로그

> **목적:** 검토자 권장 (Plan §22 #2 + AP-V5-32) 에 따라 V5 의 *진보를 수치로* 박는 SSOT. flag 별로 회귀 테스트를 실행하고 fail count / token / elapsed 변화를 누적 기록.
>
> **append-only 정책:** 측정값은 *수정 금지*. 새 측정은 항상 새 entry 로. 이전 결과를 고치면 V5 의 진보 측정 자체가 무의미해짐.

---

## 1. baseline — v4.5.7 (모든 flag OFF)

**measurement date:** 2026-05-05
**branch:** main (commit `b3783f3`)
**flags:** 전부 OFF (`.env` 에 V5_* 없음)
**환경:** Ubuntu 22.04 / Python 3.11 / pydantic 2.x / pytest 8.x

```
python -m pytest tests/regression/ --tb=no -q
```

| 메트릭 | 값 |
|-------|-----|
| Total tests | 177 |
| **Passed** | **124** |
| **Failed** | **52** |
| Skipped | 1 |
| Pass rate | 70.1% |
| 전체 elapsed | (record_baseline.py 측정 — 139 min, 20 prompt LLM 호출 포함) |

**52 fail 의 분류** (Plan §22 #2 — V5 가 해결할 영역의 명세):

| Fail 카테고리 | 건수 | V5 어느 Phase 가 해결 |
|--------------|------|----------------------|
| `watch_signal_actionability=0` (semantic) | ~13 | Phase 1 Editor + Phase 5 Composer prompt 보강 |
| `total_chars_below_prompt_minimum` (completeness) | ~16 | Phase 5 Word Budget + adaptive max_tokens |
| `deck_conclusion_low` (semantic) | ~3 | Phase 1 Editor 7-rubric |
| `forbidden_chart_types_emitted` (golden) | ~16 | Phase 6 Chart Critic + Phase 2B Registry |
| 기타 (min_total_chars / 기타 임계) | ~4 | 누적 |

**AP-V5-32 정책:** V5 의 어떤 phase 도 fail count 를 52 보다 *늘려선* 안 됨. 늘리면 회귀.

---

## 2. flag-by-flag 측정 절차 (Plan §0.3 단계 도약 금지)

**원칙:**
1. baseline 대비 한 flag 씩 ON.
2. 매 단계마다 동일 명령으로 측정.
3. 결과를 본 문서 §3 에 *append* (수정 X).
4. fail count 가 *늘면* 그 flag 즉시 OFF + 디버깅. AP-V5-32 위반으로 다음 단계 진행 불가.

**측정 명령 (기준 — 모든 단계 동일):**

```bash
# 0. 환경 준비 — 처음 한 번
cd ~/agents_reviewer
source venv/bin/activate
pip install -r requirements-v5.txt -r requirements-test.txt
python -m playwright install chromium

# 1. flag 설정 (.env)
# 예: Step 1 — Editor 만 ON
echo "V5_EDITOR_PASS=1" >> .env

# 2. 봇 재시작 (CLAUDE.md VM 배포 SOP)
pkill -f "src.main"; sleep 2
nohup python -m src.main > bot.log 2>&1 & disown

# 3. 회귀 측정
python -m pytest tests/regression/ --tb=no -q 2>&1 | tail -5
```

**기록 항목:**
- `flags`: 켜진 V5_* 목록
- `passed / failed / skipped`
- `fail delta`: baseline (52) 대비 변화
- `pytest elapsed` (초)
- `actual report sample`: 텔레그램으로 보고서 1건 만들고 URL
- `chart drop / fallback count`: 로그 grep `chart_gate.*fallback`
- `desk decision`: 로그 grep `desk_editor.*decision`
- `notes`: 사용자 체감 / 이슈

---

## 3. 측정 결과 (append-only)

> **포맷:** YAML block + 한 줄 요약. 새 entry 는 *맨 아래에* 추가.

### Entry 1 — baseline (2026-05-05)

```yaml
date: 2026-05-05
branch: main
commit: b3783f3
flags: []  # 모든 V5 flag OFF
total: 177
passed: 124
failed: 52
skipped: 1
pass_rate: 70.1%
fail_delta: 0  # baseline
pytest_elapsed_s: ~30
actual_report_sample: (84 reports, v4.5.7 시절 누적 — retrofit_v5.py 분석 결과 publish 3 / kill 87)
notes: |
  v4.5.7 호출 경로 byte-equal. 회귀 framework 가 측정한 52 fail 이 V5 후속 phase 의 개선 영역 명세.
  retrofit_v5.py 의 87 kill 은 휴리스틱 오탐 (실제 V5 KILL 율과 다름).
```

### Entry 2 — Step 1: Editor only (TBD)

```yaml
date: TBD
branch: main
commit: TBD
flags: [V5_EDITOR_PASS]
# 측정 후 사용자가 채움
```

### Entry 3 — Step 2: Editor + ResearchDirector (TBD)

```yaml
date: TBD
flags: [V5_EDITOR_PASS, V5_RESEARCH_DIRECTOR]
```

### Entry 4 — Step 3: + VisualPlanner (TBD)

```yaml
date: TBD
flags: [V5_EDITOR_PASS, V5_RESEARCH_DIRECTOR, V5_VISUAL_PLANNER]
```

### Entry 5 — Step 4: + LayoutTypesetter (TBD)

```yaml
date: TBD
flags: [V5_EDITOR_PASS, V5_RESEARCH_DIRECTOR, V5_VISUAL_PLANNER, V5_LAYOUT_TYPESETTER]
```

### Entry 6 — Step 5: All ON (TBD)

```yaml
date: TBD
flags: [V5_EDITOR_PASS, V5_RESEARCH_DIRECTOR, V5_VISUAL_PLANNER, V5_LAYOUT_TYPESETTER, V5_DESK_EDITOR]
expected_pass_rate_threshold: ">= 88.7%"  # fail <= 20 / 177
expected_fail_delta: "<= -32"  # 52 → 20 미만이면 V5 진보 측정 성공
```

---

## 4. 진보 판정 정책 (Plan §22 #2)

**진보로 판정하는 조건 (모든 flag ON 시):**
- `fail_delta` ≤ -20 (= fail count 32 이하).
- 새로 *추가된* fail 0 건 (없던 fail 항목이 V5 켰을 때 생기면 회귀).
- `pytest_elapsed_s` baseline 의 3.0× 이내 (Phase 0B Cost Regression 정책).
- 텔레그램 실보고서 1건 이상의 사용자 체감 개선.

**부분 진보 (V5_EDITOR_PASS 만 — Step 1):**
- `deck_conclusion_low` ~3건 → 0 으로 줄어드는 게 1차 진보 시그널.

**회귀 — 그 단계의 flag OFF 후 재측정:**
- `fail_delta` > 0 이거나 새 fail 발생.
- pytest elapsed 가 3× 초과.

---

## 5. method 준수 테스트 — Phase 1A 의 *진짜 가치* 측정 (검토자 6번 지적)

ResearchDirector 가 method 를 *고르는* 것만으로는 부족. *고른 method 를 downstream agent 가 따르는지* 가 가치.

`tests/regression/test_method_compliance.py` (Phase 1A 의 method 준수 가드):

| 시나리오 | 검증 |
|---------|------|
| `method=decision_matrix` | StrategicReport 모델에 `decision_matrix` 필드 존재 + options ≥ 2 + criteria ≥ 3 + recommendation + action_plan_30_60_90 + failure_modes ≥ 3 |
| `method=transmission_channel` | required_exhibit priority=required 1개 이상 + heuristic 이 transmission 형 chart (bar/line/sankey 의 fallback) 추천 |
| `method=scenario_tree` | scenario branches ≥ 2 + watch_signals 이 driver 로 매핑 가능 |
| `method=stakeholder_matrix` | required_exhibit 에 matrix/grid 형 chart |
| `method=ACH` | hypothesis ≥ 2 + evidence_matrix 형식 |
| `method=fault_tree` | causal layer ≥ 2 |
| `method=pre_mortem` | failure_modes ≥ 3 |
| `method=transmission_timeline` | timeline events ≥ 3 |
| `method=comparative` | comparison entries ≥ 2 |

상세 23건 케이스 — `tests/regression/test_method_compliance.py` 참조.

---

## 6. 검토자 (제3기관) 이행 매핑

본 문서는 검토자의 5번 권장 ("V5 활성화 전 pytest 결과 저장") 의 SSOT. 이행 항목:

- ✅ **검토자 4순위 — requirements 분리** — `requirements-v5.txt` 신설. `docs/V5_ACTIVATION.md` §1.5 에 graceful degrade 매트릭스.
- ✅ **검토자 2순위 — pytest 결과 저장** — 본 문서 §3 (append-only) + 측정 명령 §2.
- ✅ **검토자 3순위 — flag 별 효과 측정표** — 본 문서 §3 의 6개 entry slot.
- ✅ **검토자 5순위 — method 준수 테스트** — `tests/regression/test_method_compliance.py` + 본 문서 §5.
- ⏳ **검토자 1순위 — 브랜치 정리** — main 머지 완료 (PR #8/10/11/12), default branch 는 GitHub UI 정책. 사용자 직접 처리 항목.

---

## 7. 사용 가이드

**측정 시:**
1. `.env` 에 flag 추가
2. 봇 재시작 (CLAUDE.md VM 배포 SOP)
3. `python -m pytest tests/regression/ --tb=no -q | tail -5`
4. 결과를 §3 의 빈 entry 채워 commit
5. 추가 flag 켜고 반복

**해석:**
- fail_delta 음수 = 진보. 클수록 좋음.
- 새 fail 발생 = 회귀. 즉시 그 flag OFF + 디버깅.
- 모든 entry 채우고 fail_delta ≤ -20 = V5 acceptance 충족.
