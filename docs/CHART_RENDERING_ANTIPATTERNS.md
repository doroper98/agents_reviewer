---
tier: 2
last_synced_with: v4.4.3
ssot_for:
  - "차트 렌더링 코드/데이터 anti-patterns (charts.js + composer prompt 회귀 방지)"
depends_on:
  - "docs/MONO_THEME_GUIDE.md (디자인 anti-patterns §6)"
  - "src/templates/static/charts.js"
  - "src/agents/narrative_composer.py:SYSTEM_PROMPT (차트 섹션)"
last_review: 2026-05-02
---

# Chart Rendering Anti-Patterns

> mono guide §6 (디자인 anti-pattern: cross-hatch / opposite diagonals / big dots
> 등) 과 별개로, **코드·데이터 회귀로 발생하는 차트 품질 문제** 모음.
>
> 신규 차트 type 추가 / `charts.js` 수정 / composer prompt 차트 섹션 변경 시
> 본 문서의 체크리스트 위반 여부 *반드시* 점검. 회귀 1건 발견 시 본 문서에 항목
> 추가 (append-only) — 같은 실수 반복 방지의 SSOT.

---

## CHART-AP-1: category / group 시각 분리 미적용

**증상**: 같은 차트 안의 노드 / 막대 / 셀이 그룹별 *시각적 차이가 없음*. 데이터의 의미 정보 손실.

**최초 사례**: `drawNetwork()` 가 `node.group` 필드를 시각적으로 무시 — 모든 노드 동일 accent solid (v4.4.2 fix). 11 행위자 차트에서 진영 (승인 / 반대 / 검토 / 비공식) 분류가 화면에 안 나타남.

**검증 체크리스트**:
- [ ] 차트 type 의 data schema 에 `group` / `category` / `severity` 필드가 있나?
- [ ] 시각화에서 그 필드별 *명확히 다른* fill / stroke / pattern 적용되나?
- [ ] 사용된 group 만 모아 자동 legend 노출되나?

**적용 예 (drawNetwork v4.4.2+)**: 한국어 키워드 매칭 (승인 / 반대 / 검토 / 비공식 + 영어 동의어) → 5종 시각 변형 (accent solid / accent-hatch / open ring with --down / dots / muted card).

---

## CHART-AP-2: 반복 라벨 시각 일관성 깨짐

**증상**: 같은 의미의 라벨이 row / series 마다 *다른 색·패턴*. 한 차트 안에서 같은 카테고리가 시각적으로 일관되지 않음.

**최초 사례**: `drawStacked()` 가 row 안 `k` 인덱스 기반으로 fill 결정 — 같은 segment.label 이 row 간 다르게 칠해짐 (v4.4.2 fix).

**검증 체크리스트**:
- [ ] segment.label / series.name 등 반복 가능한 식별자가 있는 차트면 *unique 라벨 → 고정 fill* 매핑이 row / 시리즈 무관하게 유지되나?
- [ ] 라벨 mapping 은 *pre-pass* 로 모든 데이터 훑은 뒤 결정 (drawing 전)?

**적용 패턴**:
```js
// pre-pass: collect unique labels in encounter order
const labelOrder = [];
rows.forEach(r => (r.segments || []).forEach(s => {
  if (s.label && labelOrder.indexOf(s.label) === -1) labelOrder.push(s.label);
}));
const labelToIndex = Object.fromEntries(labelOrder.map((l, i) => [l, i]));
// drawing: same label → same fill across rows
```

---

## CHART-AP-3: 음수 / 0 / 극단값 robust 처리 누락

**증상**: 음수 입력 시 SVG width / height 음수 → 미렌더. 0 값 segment 가 *조용히 사라짐* (사용자가 *데이터 누락* 이라 오해).

**최초 사례**: `drawStacked()` 음수 segment width 폭주 (v4.2.2 fix). 시나리오 정성 점수 ±9 입력 시 S3/S4 막대 비어보임.

**검증 체크리스트**:
- [ ] width / height 계산에 `Math.abs()` 또는 `Math.max(0, ...)` 적용?
- [ ] 0 값 segment 는 skip — *또는* 명시적 dotted track 으로 가시화 (조용히 안 사라짐)?
- [ ] composer prompt 에 양수 magnitude only 명시 (음수가 의미 있으면 별도 type)?

---

## CHART-AP-4: 고정 aspect-ratio 와 동적 viewBox 충돌

**증상**: 차트 카드 안에 *위·아래 빈 공간* (letterbox) 또는 차트 잘림.

**최초 사례**: `charts.css` 의 `.chart-stage-bar { aspect-ratio: 5/3 }` 가 v4.4.0 의 동적 H 와 충돌 (v4.2.2 fix). SVG viewBox 가 데이터 길이 따라 비율 결정하는데 CSS 가 다른 비율 강제 → preserveAspectRatio 가 letterbox.

**검증 체크리스트**:
- [ ] CSS 의 `aspect-ratio` 강제가 SVG viewBox 의 자연 비율과 충돌 없나?
- [ ] viewBox 동적 H 사용 시 stage 컨테이너는 `height: auto` 만 (aspect-ratio 강제 X)?

---

## CHART-AP-5: 라벨 zone 밖 잘림

**증상**: 막대 끝 라벨이 SVG viewBox 우측 / 카드 경계 밖으로 벗어남.

**최초 사례**: `drawBar()` 가 W=360 + padR=30 만 — max 막대 시 라벨 완전 벗어남 (v4.2.2 → v4.4.0 fix). 배터리 3사 영업손실 -2078 이 -207 로 잘림.

**검증 체크리스트**:
- [ ] 라벨 placement 가 zone 검사 + 3-tier fallback?
  1. 외부 (막대 우측, default)
  2. 내부 (막대 안, 우측 정렬, inverse 색)
  3. 우측 정렬 (zone 끝)
- [ ] 라벨 길이 추정 시 한국어 (×1.4 정도) / 영어 (×1.0) 너비 차이 고려?

---

## CHART-AP-6: annotation 충돌 / 겹침

**증상**: vline 라벨 + end 라벨 + band 라벨이 같은 좌표 영역에서 겹침. 텍스트 가독성 0.

**최초 사례**: tier1_chart_preview v1 의 PER 차트 + line 차트 (v4.4.0 zone-based layout 으로 fix).

**검증 체크리스트**:
- [ ] zone-based layout (top / right / bottom margin) 명확 분리?
- [ ] `OccupancyTracker` (bbox 충돌 검사) 적용?
- [ ] vline 다수일 때 callout y 좌표 staggering (가까우면 +28 offset)?
- [ ] end 라벨 후보 N개 시도 (우측 → 위쪽 → 좌측 → 안)?

**적용 패턴**:
```js
function placeLabel(svg, x, y, text, t, occupancy, zones) {
  const candidates = [
    { x: x + 6,           y: y - 8,  anchor: 'start' },  // right
    { x: x + 6,           y: y - 18, anchor: 'start' },  // upper-right
    { x: x - labelW - 6,  y: y - 8,  anchor: 'start' },  // left
  ];
  for (const c of candidates) {
    if (c.x + labelW <= zones.W && !occupancy.hits(c.x, c.y, labelW, 14)) {
      // place + occupancy.add
      return;
    }
  }
}
```

---

## CHART-AP-7: 빈 데이터 차트 emit

**증상**: composer 가 data 비어있는데 chart-card 가 박혀 *빈 frame* 만 노출.

**최초 사례**: 배터리 3사 보고서의 빈 bubble 차트 (v4.4.0 fix). 시나리오 확률 × 영향 매트릭스가 데이터 0개로 frame 만.

**검증 체크리스트**:
- [ ] composer prompt 에 *type 별* "data 비면 emit 금지" 명시?
  - bar/donut/line/gantt/heatmap: data 빈 배열이면 X
  - network: nodes < 2 면 X
  - stacked: scenarios 빈 배열이면 X
  - dual_line: left.series 또는 right.series 비면 X
  - forecast: actual < 2 면 X
- [ ] `freeform_essay.html` 에 type 별 `has_data` 검증으로 chart-card 자체 skip (composer 가 잘못 emit 했을 때 fallback)?

---

## CHART-AP-8: 차트 type 이 사건과 부적합

**증상**: 데이터 성격에 안 맞는 type 으로 emit — 라벨 너무 길어 겹침, 또는 *차트가 무엇인지 모름*.

**최초 사례**: 소말릴란드 5단계 승인 경로 차트 (v4.4.2 사용자 보고). 5 phase timeline 데이터를 gantt 로 emit 했는데 phase 라벨이 너무 길어 left zone 안에서 wrap 안 되고 옆 라벨과 겹침. 사용자 인용: "차트가 뭔지 전혀 모르겠음."

**검증 체크리스트**:
- [ ] composer prompt 에 type 별 *사건 적합도* 가이드 명시?
  - bar: 순위 비교 (3~10 항목, 라벨 짧음)
  - gantt: 명확한 시간 구간 (date range), 라벨 ≤14자
  - timeline 형 5~7 phase 흐름은 *bar 또는 본문 list* 로
- [ ] takeaway 한 줄 *강제* — takeaway 못 쓰면 차트 의미 없음 신호
- [ ] 회귀 발견 시 `patch_report.py --remove-chart` 로 즉시 제거 (전체 재분석 X)

---

## CHART-AP-9: 지도 zoom / center 디폴트 의존

**증상**: composer 가 정밀하게 emit 안 하면 지도가 잘못된 영역 / 너무 축소 → 핵심 마커 안 보임.

**최초 사례**: 소말릴란드 보고서 (v4.4.2 사용자 보고). zoom: 3.0 디폴트 + 텔아비브~모가디슈 마커 모두 한 frame 에 → 호른 아프리카 (소말릴란드 위치) 가 작아 안 보임.

**검증 체크리스트**:
- [ ] composer prompt 에 zoom 단계별 가이드?
  - 대륙 단위 (예: 유라시아 전체): 2~3
  - 국가 / 지역 (예: 호른 아프리카): 4~6
  - 도시 단위 (예: 서울 권역): 7+
- [ ] center: 마커들의 *중앙값* 권장 (단순 평균 X — 마커 분포 고려)?
- [ ] 마커가 한 지역에 몰리면 *zoom 강제 상향* (예: 호른 아프리카만 보면 5+)?
- [ ] 멀리 떨어진 마커 (예: 텔아비브 + 소말리아) 가 한 frame 에 들어오면 *연관성 약한 마커는 빼기* — 또는 zoom 낮추고 dual-frame?

---

## 체크리스트 — 새 차트 type / charts.js 변경 / composer prompt 변경 시

### 코드 변경 전 (스키마 설계)
- [ ] schema 에 `group` / `category` / `severity` 필드가 있으면 → CHART-AP-1
- [ ] segment / series 반복 가능하면 → CHART-AP-2
- [ ] 수치 입력은 항상 → CHART-AP-3 robust

### 코드 작성 시 (`charts.js`)
- [ ] `computeZones()` 사용 → CHART-AP-4, 5, 6
- [ ] `makeOccupancy()` + 라벨 후보 N개 → CHART-AP-5
- [ ] viewBox 동적 H — CSS 에 aspect-ratio 강제 X → CHART-AP-4
- [ ] 모든 데이터 access 빈 배열 / undefined 가드 → CHART-AP-7

### composer prompt 변경 시
- [ ] type 별 data 스키마 명시 → CHART-AP-7
- [ ] "data 비면 emit 금지" 가이드 → CHART-AP-7
- [ ] 사건 적합도 한 단계 가이드 → CHART-AP-8
- [ ] 지도면 zoom 단계 가이드 → CHART-AP-9

### 배포 전 시각 검증
- [ ] 다양한 데이터 분포 (1개 / 다수 / 음수 포함 / 극단값) 로 렌더 미리보기
- [ ] 라벨 길이 다양성 (한국어 짧 / 긺, 영어 짧 / 긺)
- [ ] 모바일 사이즈 (chart-card-stage 가 좁아질 때) 라벨 겹침 X

---

## 회귀 발견 시 — 표준 프로토콜

1. 본 문서의 9 패턴 중 어디에 해당하는지 분류
2. 시스템적 회귀 (모든 보고서 영향) → 코드 수정 (`charts.js` 또는 composer prompt). 새 패턴이면 본 문서에 CHART-AP-N 항목 추가
3. 이 보고서만 영향 → `scripts/patch_report.py` 로 데이터 수정 (LLM 0)
4. fix 후 *DEVLOG.md* 에 commit 사유 + 본 문서 항목 reference
5. 다음 commit 부터 본 문서 체크리스트 점검 (PR 시 자동 점검 가능 → 향후 GitHub Action 으로 확장)

---

## 본 문서 갱신 규칙 (DOCS_GOVERNANCE 정합)

- **append-only**: 발견된 회귀는 새 항목으로 추가. 기존 항목 수정 금지. 정정은 새 항목으로.
- **회귀 ID 명시**: CHART-AP-N 으로 일관 부여. 코드 / 커밋 메시지에서 reference (예: "fix CHART-AP-5: bar label cutoff").
- **`last_synced_with` 갱신**: 항목 추가 시 헤더의 version 갱신.
