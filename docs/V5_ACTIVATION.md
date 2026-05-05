---
tier: 1
status: v5_activation_guide
last_synced_with: v5.0.0
ssot_for:
  - "V5 Phase 단계적 활성화 절차 (opt-in flag 운용)"
  - "v4.5.7 → v5.0.0 마이그레이션 가이드"
depends_on:
  - "REFACTOR_V5_PLAN.md §0 (byte-equal 보존 원칙)"
  - "src/config.py (Config.enable_* fields)"
  - "tests/regression/ (회귀 테스트 통과율 측정)"
last_review: 2026-05-05
---

# V5 활성화 가이드

> **본 문서는 v4.5.7 baseline 위에 V5 신규 phase 들을 *단계적으로* 켜기 위한 운용 SSOT.** Plan §0.3 "단계 도약 금지" 원칙에 따라 phase 별로 flag 를 켜고 회귀 테스트 통과 확인 후 다음 단계로 이행.

---

## 1. 핵심 원칙

- **default OFF** — `.env` 에 아무것도 안 적으면 v4.5.7 호출 경로 그대로 실행 (byte-equal).
- **단계적 활성화** — 한 번에 한 flag 만 켜고 회귀 테스트 → fail count 가 baseline (52) 보다 *늘지 않는지* 확인. 늘면 즉시 OFF 후 디버깅.
- **표시 버전 분리** — 모든 flag 가 켜져도 `src/orchestrator.py:VERSION` 은 변경 안 됨. 텔레그램 표시 버전 변경은 *모든 phase 가 baseline 보다 좋다고 측정* 된 후 별도 commit.

---

## 2. 5종 Flag (Phase 매핑)

| 환경 변수 | 활성화되는 phase | 효과 |
|----------|----------------|------|
| `V5_RESEARCH_DIRECTOR=1` | Phase 1A | 사용자 질의 + EvidencePack → AnalysisBrief (분석 설계도) emit. 9종 method 자동 라우팅. |
| `V5_VISUAL_PLANNER=1` | Phase 2 | composer 가 emit 한 chart dict 를 Vega-Lite spec 으로 변환. design token 강제 (AP-V5-2). |
| `V5_EDITOR_PASS=1` | Phase 1 | composer DraftReport 직후 Editor (Opus 4.7) 7-rubric 비평·재집필. 진부어 차단, 보존 검증. |
| `V5_LAYOUT_TYPESETTER=1` | Phase 3 | Editor 후 9-vocab 중 섹션별로 결정 (hero / standard / two-column / pull-quote 등). |
| `V5_DESK_EDITOR=1` | Phase 7 | Phase 7A (Deterministic Gate) 통과 후 DeskEditor (vision) publish/hold/KILL 판정. |

> 각 flag 는 `1` / `true` / `yes` / `on` (대소문자 무시) 로 켜고 비워두면 꺼짐.
> 짧은 이름 (`V5_*`) 외에 `ENABLE_*` 형식도 받음 — 둘 다 동등.

### 항상 켜져 있는 모듈 (flag 없음)

- **Phase 0/0B/0C** — State 모델·회귀 framework·SSOT 문서. flag 무관, 이미 v5.0.0 의 기본.
- **Phase 2A** — EvidenceDataset Guard. composer 가 chart emit 시 항상 검증 (AP-V5-24/25/26).
- **Phase 2B** — Capability Registry. 미등재 chart type emit 차단 (AP-V5-27).
- **Phase 4** — Exhibit 번호제. composer 가 `[[ex:N]]` 마커 emit 시 renderer 가 자동 부여 (AP-V5-6).
- **Phase 5** — Word Budget + 절단 검출. 매 호출에서 truncation signal 측정.
- **Phase 6** — Chart Gate (Schema/Critic/Sanity/Fallback). VisualPlanner 활성 시 자동 적용.
- **Phase 6A** — Exhibit Priority. DesignBrief 의 required_exhibits 정합성 검사.
- **Phase 7A** — Deterministic Gate (11 Hard + 5 Soft). DeskEditor 활성 시 사전 단계로 항상.
- **Phase 8/8A** — Strategic Mode. 사용자 prefix 또는 패턴 자동 감지로 트리거.

---

## 3. 권장 단계적 활성화 순서

각 단계 후 회귀 테스트 통과율이 *떨어지지 않았는지* 확인:

```bash
python -m pytest tests/regression/ --tb=no -q 2>&1 | tail -5
```

baseline (52 failed) 보다 늘어나면 직전 flag OFF 하고 원인 디버깅.

### Step 1 — Editor Pass (보고서 품질 즉각 향상)

```bash
echo "V5_EDITOR_PASS=1" >> .env
python -m pytest tests/regression/test_editor.py -v
```

체감: deck/conclusion 정합 + 진부어 제거. baseline 의 `deck_conclusion_low` ~3건 해소 기대.

### Step 2 — Research Director (분석 깊이 향상)

```bash
echo "V5_RESEARCH_DIRECTOR=1" >> .env
python -m pytest tests/regression/test_research_director.py -v
```

체감: 사건 유형별로 적절한 분석 method 자동 선택 (호르무즈→geo_forecast, LLM→tech_diffusion 등 9종).

### Step 3 — Visual Planner + Chart Gate (차트 품질 향상)

```bash
echo "V5_VISUAL_PLANNER=1" >> .env
python -m pytest tests/regression/test_phase2_vega.py tests/regression/test_chart_correctness.py -v
```

체감: 차트가 Vega-Lite 어댑터 거쳐 design token 강제 적용 + 4중 게이트 (Schema/Critic/Sanity/Fallback). baseline 의 `forbidden_chart_types_emitted` ~16건 감소 기대.

### Step 4 — Layout Typesetter (레이아웃 다양화)

```bash
echo "V5_LAYOUT_TYPESETTER=1" >> .env
python -m pytest tests/regression/test_layout_typesetter.py -v
```

체감: 섹션별로 hero/two-column/pull-quote 등 9-vocab 중 자동 배치.

### Step 5 — Desk Editor (최종 KILL 게이트)

```bash
echo "V5_DESK_EDITOR=1" >> .env
python -m pytest tests/regression/test_desk_editor.py -v
```

체감: 결함 보고서가 publish 안 되고 hold/KILL 됨. **Playwright 가 설치되어 있어야 vision 캡처 가능** — 미설치 시 graceful skip.

```bash
# Playwright 설치 (필요 시)
pip install playwright && playwright install chromium
```

---

## 4. 회귀 테스트 통과율 모니터링

```bash
# 전체 17종 회귀 테스트 일괄
python -m pytest tests/regression/ --tb=no -q 2>&1 | tail -5

# 특정 phase 만
python scripts/run_regression.py --tests editor,director,phase2vega,chartgate,desk
```

기대 변화:

| Flag 활성화 | baseline 52 fail 중 줄어드는 항목 |
|------------|----------------------------------|
| `V5_EDITOR_PASS` | `deck_conclusion_low` ~3건 |
| `V5_RESEARCH_DIRECTOR` | `min_total_chars_below_threshold` 일부 |
| `V5_VISUAL_PLANNER` | `forbidden_chart_types_emitted` ~16건 |
| `V5_DESK_EDITOR` | `watch_signal_actionability=0` ~13건 (Editor 와 결합) |

전부 켰을 때 fail count 가 52 → 20 미만이면 V5 의 진보가 측정된 것. orchestrator VERSION bump 시점.

---

## 5. 봇 재시작

`.env` 변경 후 텔레그램 봇 서비스 재시작 필요:

```bash
# systemd 사용 시
sudo systemctl restart agents-reviewer

# 직접 실행 시
pkill -f "src.bot" && python -m src.bot &
```

config 가 startup 시점 1회 로드되므로 재시작 없이는 flag 변경 미반영.

---

## 6. 롤백

문제 발생 시 즉시 OFF:

```bash
# 특정 flag 만
sed -i 's/^V5_DESK_EDITOR=1$/V5_DESK_EDITOR=/' .env

# 모두 OFF (= v4.5.7 byte-equal)
sed -i 's/^V5_/# V5_/' .env

sudo systemctl restart agents-reviewer
```

---

## 7. 표시 버전 (`VERSION = "5.0.0"`) 변경 시점

다음 *모두* 충족 시:

1. 5종 flag 전부 ON 상태로 회귀 테스트 fail count 가 baseline 52 보다 *명백히 작음*.
2. 사용자가 텔레그램으로 5건 이상 실제 보고서 생성 후 품질 만족.
3. Plan §25.2 의 인수 기준 통과 — `git tag v5.0.0` 부착 완료.

이 후 별도 commit 으로:

```python
# src/orchestrator.py
VERSION = "5.0.0"
```

+ Change Propagation Matrix (CLAUDE.md) 따라 README / CHANGELOG / 문서 헤더의 `last_synced_with` 동기화. 봇 재시작.
