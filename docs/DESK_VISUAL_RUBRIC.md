---
tier: 2
status: phase_7_ssot
last_synced_with: v4.5.7
ssot_for:
  - "Phase 7 DeskEditor 의 Visual 8-rubric (사진 프루프 검수) 정본"
  - "Self-improving rubric — YK 가 잡은 시각 결함의 append-only 누적 (Plan §16.12)"
depends_on:
  - "REFACTOR_V5_PLAN.md §16 (Phase 7 SSOT)"
  - "src/agents/desk_editor.py (코드 SSOT)"
  - "docs/MONO_THEME_GUIDE.md (디자인 톤 SSOT)"
last_review: 2026-05-05
---

# V5 Phase 7 — Desk Editor Visual Rubric (Self-improving)

> 본 문서는 **append-only** 입니다. Plan §16.12 의 self-improving rubric 정책에 따라, YK 가 발행된 보고서 검수 후 발견한 *시각 결함* 은 *반드시* 본 문서에 새 항목 (`(시각-N)`) 으로 추가됩니다 (AP-V5-16). 같은 결함이 두 번째 보고서에서 다시 발생하지 않도록 시스템이 *누적 학습* 하는 메커니즘.
>
> 본 문서의 항목은 [src/agents/desk_editor.py](../src/agents/desk_editor.py) 의 SYSTEM_PROMPT 가 *자동으로 포함* 합니다. 새 항목 append 시 desk_editor 의 다음 호출부터 활성.

---

## 0. 운영 정책 (Plan §16.12)

- **1차 검수 (자동)**: DeskEditor (Opus 4.7 Vision) 가 본 문서의 모든 시각 항목을 자동 catch — 목표 80%.
- **2차 검수 (YK)**: 진짜 미묘한 이슈만 fix. 목표 ≤ 5%.
- **3차 (피드백 루프)**: YK catch 한 결함 → 본 문서에 새 항목 (`(시각-N)`) append → 다음 DeskEditor 호출부터 자동 catch.

운영 1~3개월 후 평가 — YK catch 빈도가 시간에 따라 *감소* 하는지 확인.

## 1. Visual 8-rubric — Plan §16.4 정본 (DeskEditor 호출 시 항상 적용)

각 항목 1~5 점수. score ≤ 2 면 issue 발생. *입력은 렌더된 HTML 의 스크린샷 (3~5장)*. Vision LLM (Opus 4.7) 이 *눈으로 보고* 판정.

### (시각-1) 차트 라벨 / 축 잘림

- **무엇**: 차트 라벨이 박스 밖으로 나가거나, 축 텍스트가 카드 경계로 잘리는가
- **catch**: AP-5 (라벨 zone 밖 잘림)
- **score 2 이하 시 action**: `rerender_chart` 또는 `drop_chart`

### (시각-2) 지도 범위·중심 적절성

- **무엇**: 보고서 본문이 다루는 지역이 지도 frame 안에 *명확히 보이는가*. 너무 작거나 (호른 아프리카 보고서인데 유라시아 전체) frame 가장자리 위치인가
- **catch**: AP-9 (zoom/center 디폴트 의존)
- **score 2 이하 시 action**: `adjust_map_zoom_center`

### (시각-3) 데이터 마크 viewport 안

- **무엇**: 차트의 모든 데이터 점·막대·노드가 visible frame 안에 보이는가
- **catch**: AP-12 의 *시각 검증* (frame 밖으로 나간 데이터)
- **score 2 이하 시 action**: `adjust_chart_scale` 또는 `drop_chart`

### (시각-4) 텍스트 오버플로우

- **무엇**: 본문이 인접 요소로 흘러넘치거나, 헤드라인이 wrap 안 되고 잘리는가. pull_quote / kicker / lede 가 *부자연스러운* 위치에 잘려있는가
- **score 2 이하 시 action**: `adjust_layout` 또는 `shorten_text`

### (시각-5) 색상 톤 일관성

- **무엇**: 차트·카드·헤더 색이 V5 design token (Editorial Cream 또는 Burgundy Mono) 과 *시각적으로* 일치하는가. 한 차트만 다른 톤이거나, 다크 카드에 다크 텍스트 같은 가독성 결함
- **catch**: AP-11 의 *시각 확인* (CSS variable resolution 실패)
- **score 2 이하 시 action**: `reapply_theme`

### (시각-6) 본문-차트 시각 정합

- **무엇**: 차트가 인접 본문 단락 옆에 *명확히 짝지어져* 보이는가. 차트 위·아래 공백이 부자연스러워 떠다니는 느낌인가, 다음 섹션과 합쳐 보이는가
- **score 2 이하 시 action**: `adjust_layout`

### (시각-7) 모바일 반응형 깨짐

- **무엇**: 375px 폭 mobile_full 스크린샷에서 레이아웃이 깨지거나 차트가 잘리는가. fact_grid 가 모바일에서 어색하게 stacking 되는가
- **catch**: KILL 신호 (Plan §16.6 — `mobile_layout_broken` 가 score=1 이면 자동 KILL)
- **score 2 이하 시 action**: `adjust_responsive_breakpoints`

### (시각-8) 전체 미적 균형

- **무엇**: 페이지 전체를 멀리서 봤을 때 *시각적 노이즈·공허·과밀 구간* 이 있는가. 정량화 어려운 종합 미적 인상
- **운영 비유**: Foreign Affairs 데스크가 page proof 마지막에 보는 항목
- **score 2 이하 시 action**: `major_layout_revision`

---

## 2. Append-only 누적 — YK catch 항목 (`(시각-9)+`)

> 본 섹션은 **append-only**. YK 가 발행된 보고서 검수 후 발견한 *명백한 시각 결함* 을 새 항목으로 추가합니다 (AP-V5-16 강제). 기존 항목 *수정·삭제 금지*.

> 항목 형식 — 각 항목은 다음 4 필드 명시:
>
> ```
> ## (시각-N) — 추가됨 vX.Y.Z (YYYY-MM-DD)
> - 증상: <YK 가 본 결함의 1~2 문장 설명>
> - 사례: <보고서 ID 또는 캡쳐 fingerprint>
> - 검수 기준: <DeskEditor 가 다음 호출에서 *catch* 할 정량/정성 기준>
> - 권장 action: <issue 발생 시 어떤 lower editor 가 fix 할지>
> ```

(현재까지 누적: 1건.)

## (시각-9) 지도·차트 annotation 의 주제 정합성 — 추가됨 v5.0.2 (2026-05-06)

- **증상**: 지도가 보고서 *주제* (deck / headline / 주된 prose) 와 의미적으로 *부수적* 또는 *기계적* 으로 추가됨. 카테고리 라벨 ("거시경제·지정학") 만 보고 자동 추가되지만, 실제 본문은 다른 축 (예: 통화·재정 정책결정자의 의사결정) 에 집중. 지도가 *주제 핵심* 이 아닌 *주변 사실* 만 보여주면 KILL 사유.
- **사례**: 2026-05-06 00:50:27 — "이란 전쟁 충격이 미·한 통화·재정 정책결정자에게" 보고서. 베센트·파월·신현송 의사결정 분석이 지배적인데 지도는 호르무즈→동아시아 원유 회랑만. *지도가 주제 보조도 아닌 노이즈*. 사용자 catch.
- **검수 기준**:
  1. 지도/차트의 모든 marker / arc / region annotation 이 *deck 또는 headline* 의 핵심 키워드와 의미적으로 직접 연결되는가? (단순 카테고리 일치 X — 주제 주체·행위·의사결정과의 연결).
  2. annotation 의 주제 적합도 점수 ≤ 1 면 KILL.
  3. 보고서 prose 가 다른 축 (예: 정책결정자 / 의사결정 / 시간축) 이 지배적이면 *지도 자체* 를 hide 하는 게 더 나은 시각.
- **권장 action**:
  - **Editor (Phase 1)**: deck/headline 재집필 시 지도-주제 연결 강제 (지도 마커 지명이 prose 에 명시 등장하지 않으면 지도 unhide).
  - **Composer**: visual_constraints 의 must_have 에 'map' 이 있어도 *주제 주체가 사람·정책결정자* 면 forbidden 으로 격하.
  - **결정적 가드**: prose 본문에서 지도 마커의 지명이 N≤2 회 등장하면 `has_inline_map=False` 로 자동 강등.



---

## 3. 자동 KILL 신호 (Plan §16.6 — Visual 부분)

다음 시각 항목 중 *둘 이상* 충족 시 **자동 KILL** (LLM 판단 X, 결정적 룰):

```python
KILL_RULES_VISUAL = {
    "majority_charts_visually_broken":  visual_fail_count(charts) >= len(charts) * 0.5,
    "mobile_layout_broken":             visual_rubric_score("시각-7") <= 1,
    "theme_token_mismatch":             visual_rubric_score("시각-5") <= 1,
}
```

논리 KILL_RULES (Plan §16.6 의 5종) + 본 시각 KILL_RULES (3종) 합산해 *둘 이상* 발화 시 자동 KILL.

---

## 4. 새 항목 append 절차

YK 가 발행된 보고서에서 시각 결함을 발견했을 때:

1. **캡쳐**: 결함이 보이는 스크린샷 저장.
2. **사례 기록**: 보고서 ID 또는 URL.
3. **본 문서의 §2 에 새 `## (시각-N)` 항목 append** — 위 형식 따라 4 필드.
4. **commit**: `docs(desk-rubric): add (시각-N) — <한 줄 요약>`.
5. **자동 활성**: 다음 DeskEditor 호출부터 SYSTEM_PROMPT 에 자동 포함 → 자동 catch.

본 절차는 [REFACTOR_V5_PLAN.md §16.12](../REFACTOR_V5_PLAN.md) + AP-V5-16 (Plan §23) 에 의해 강제됩니다.

---

## 5. SSOT 정합성

- **사람-친화**: 본 문서 §1 + §2 (rubric 자체).
- **코드 SSOT**: [src/agents/desk_editor.py](../src/agents/desk_editor.py) 의 `SYSTEM_PROMPT_VISUAL_RUBRIC` 상수 — 본 문서를 빌드 시점에 자동 포함 (또는 그대로 박힘).
- **회귀 테스트**: [tests/regression/test_desk_editor.py](../tests/regression/test_desk_editor.py) 가 본 문서의 §1 8-rubric 항목 수가 8개임을 검증.

본 문서의 항목 수가 변경되면 desk_editor.py 의 SYSTEM_PROMPT 캐시 + 회귀 테스트 분포 가드 함께 갱신 (CLAUDE.md Change Propagation Matrix).
