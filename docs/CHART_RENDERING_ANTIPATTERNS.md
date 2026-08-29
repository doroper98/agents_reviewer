---
tier: 2
last_synced_with: v8.5.11
ssot_for:
  - "차트 렌더링 코드/데이터 anti-patterns (charts.js + composer prompt 회귀 방지)"
depends_on:
  - "docs/MONO_THEME_GUIDE.md (디자인 anti-patterns §6)"
  - "src/templates/static/charts.js"
  - "src/templates/static/maps.js"
  - "src/agents/narrative_composer.py:SYSTEM_PROMPT (차트 섹션)"
last_review: 2026-06-11
---

# Chart Rendering Anti-Patterns

> mono guide §6 (디자인 anti-pattern: cross-hatch / opposite diagonals / big dots
> 등) 과 별개로, **코드·데이터 회귀로 발생하는 차트 품질 문제** 모음.
>
> 신규 차트 type 추가 / `charts.js` 수정 / composer prompt 차트 섹션 변경 시
> 본 문서의 체크리스트 위반 여부 *반드시* 점검. 회귀 1건 발견 시 본 문서에 항목
> 추가 (append-only) — 같은 실수 반복 방지의 SSOT.
>
> **번호 정책**: 본 문서의 CHART-AP-N 번호는 *부여된 순서대로 영구 보존*. 24ba563 commit 의 메시지가 신규 항목 ("보고서와 무관한 지리 annotation") 을 'CHART-AP-13' 으로 표기했으나 v4.5.4 에서 이미 같은 번호 (Gantt 시간축) 가 부여되어 *번호 충돌* 이 발생했음. [REFACTOR_V5_PLAN.md §3.7](../REFACTOR_V5_PLAN.md) 의 정본 표기에 따라 Phase 0 (v4.5.7 baseline SSOT Repair) 에서 후자를 **CHART-AP-14** 로 정정함. 누적 16개 (v5.2.0 — AP-15/AP-16 추가).

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

## CHART-AP-10: 지도 마커 라벨 충돌

**증상**: 지도에 가까이 있는 마커들 (예: 호른 아프리카의 자부티·베르베라·바벨만데브 — 100km 안) 의 라벨이 같은 좌표에 중첩되어 *전혀 읽을 수 없음*.

**최초 사례**: 소말릴란드 보고서 (v4.4.3 사용자 보고). `maps.js` 가 모든 마커 라벨을 *항상 marker 우측* (x = r + 4) 에 fixed → 가까운 마커끼리 100% 겹침.

**검증 체크리스트**:
- [ ] 마커 라벨 placement 가 4 candidate 위치 (우/좌/상/하) 시도?
- [ ] OccupancyTracker 로 bbox 충돌 검사?
- [ ] 라벨이 마커에서 떨어져 있으면 *leader line* (얇은 muted 선) 으로 연결?
- [ ] highlight 마커 *우선* placement (먼저 자리잡고 일반 마커는 남는 자리)?

**적용 패턴 (maps.js v4.4.4)**:
```js
const candidates = [
  { x: px + r + 6,      y: py - h/2, anchor: 'start' },  // right (default)
  { x: px - r - 6 - w,  y: py - h/2, anchor: 'start' },  // left
  { x: px - w/2,        y: py - r - 14, anchor: 'start' }, // above
  { x: px - w/2,        y: py + r + 4,  anchor: 'start' }, // below
];
for (const c of candidates) {
  if (!occupancy.hits(c.x - 2, c.y - 2, w + 4, h + 4)) {
    place(c); break;
  }
}
// 라벨 떨어져 있으면 leader line 추가
```

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

## CHART-AP-14: 보고서와 무관한 지리 annotation 무조건 렌더

**증상**: 특정 사례 때문에 추가한 지도 annotation 이 *모든* 보고서에 영구로 박혀, 주제와 무관한 보고서까지 렌더링됨. 결과: legend 가 본문 사실과 어긋난 noise 로 채워짐, 신뢰도 훼손.

> **번호 이력**: 24ba563 commit 메시지는 본 항목을 'CHART-AP-13' 으로 표기했으나, v4.5.4 에서 이미 같은 번호 (Gantt 시간축) 가 부여되어 충돌이 발생했음. Phase 0 (v4.5.7 SSOT Repair) 에서 [REFACTOR_V5_PLAN.md §3.7](../REFACTOR_V5_PLAN.md) 정본에 맞춰 **CHART-AP-14** 로 정정함.

**최초 사례** (v4.5.7 사용자 보고): `maps.js` 에서 소말릴란드 해칭 폴리곤 + "소말릴란드 (de facto)" legend 가 무조건 그려짐. 호르무즈 / 위안화 통행료 등 호른 아프리카와 무관한 보고서에서도 legend 에 표시 → 주제 혼란.

**원인**: feature 추가 시점의 의도 ("110m TopoJSON 이 소말리아에 통합되어 있으니 보완") 가 자연스럽게 "*항상* 그린다" 로 굳어짐. 코드 주석에도 "본 보고서 외에도 항상 정합" 식으로 명시되어 있어 의도된 것처럼 보였지만, 실제로는 본문 ↔ 지도 의미 정합성이 깨짐.

**수정** (v4.5.x):
- 폴리곤 + legend 둘 다 *viewport 가시성* 으로 게이트.
- `path.bounds(SOMALILAND_GEOJSON)` 으로 projected bbox 계산 → `[0,0]-[W,H]` 와 교차할 때만 렌더.
- 도쿄·서울·테헤란만 잡힌 보고서에서는 자동으로 사라짐.

**검증 체크리스트**:
- [ ] 새 지리 annotation (특정 분쟁지역 / 사실상 독립국 / 영토 분쟁 라벨 등) 추가 시: 그 지역이 viewport 에 보이는 보고서로 *조건부 렌더*?
- [ ] "이 보고서는 X 와 무관한데 legend 에 X 가 있나?" — 다양한 주제 (금융 / 기술 / 동북아 한정) 보고서로 cross-check?
- [ ] 코드 주석에 "*항상* 표시" / "*모든* 보고서에" 같은 표현 → 빨간 깃발. 그게 의도라면 명시적 payload 플래그로 toggle 가능하게.
- [ ] composer / visual_analyst 가 직접 emit 하지 않는 모든 자동 annotation 은 데이터 의존이 아니라 *위치 의존* — 본문이 그 위치 다루지 않으면 자동 제거되어야 함.

**관련**: CHART-AP-9 (지도 zoom / center) — 둘 다 "지도가 보고서의 실제 주제 / 지리적 범위와 정합되어야 한다" 는 큰 원칙의 다른 면.

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

## CHART-AP-11: 차트 카드 배경이 하드코딩 fallback (테마 미반영)

**증상**: 보고서 테마는 cream 인데 *차트 카드 (chart-card-stage)* 만 짙은 wine
색으로 박힘. 카드 안 SVG 가 본문 배경과 충돌해 텍스트/축 가독성 0.

**최초 사례**: 20260503_112703 보고서 (v4.5.2 사용자 보고). editorial_cream
테마 적용됐는데 모든 차트 카드 내부가 dark wine 박스. "글씨가 하나도 제대로
안 보이고 정보전달에 실패" — 사용자 인용.

**원인**: `charts.css:30` 의 `.chart-card-stage{background: var(--card-deep, #321F1F)}`
에서 `--card-deep` 변수가 *어떤 테마 블록에도 정의 안 됨* → CSS variable
resolution 실패 → fallback `#321F1F` (dark wine) 항상 적용. burgundy_mono 에선
우연히 어울려서 v4.4.x 까지 발견 안 됐고, editorial_cream 디폴트 채택 (v4.5.0)
후 즉시 노출.

**검증 체크리스트**:
- [ ] 모든 CSS `var()` fallback 이 *주 사용 테마* 와 어울리는지 검토. 단일
  하드코딩 fallback 은 다중 테마 시스템에서 회귀 자석.
- [ ] 신규 테마 도입 시 *모든* CSS 변수 (특히 chart-card / map / hero) 가
  새 테마에서 어떻게 보이는지 시각 확인.
- [ ] freeform_essay.html 의 `rgba(0,0,0,...)` 같은 *어두운 overlay* 도
  cream 테마에서 dim gray 로 보임 → 테마 변수 사용 권장.

**Fix (v4.5.3)**:
- `report.css` 각 테마 블록에 `--card-deep` 정의 추가 (editorial: cream tone,
  burgundy: deepest wine, light: deeper cream).
- `freeform_essay.html` 의 `.freeform-chart-wrap .chart-card` 배경:
  `rgba(0,0,0,0.18)` → `var(--card, var(--bg-2))`.

---

## CHART-AP-12: 버블 차트 스케일 고정 — 데이터가 frame 밖으로

**증상**: 버블 차트 frame + 축 라벨 (확률→ / 영향) 만 보이고 *버블 자체가
하나도 안 보임*. 데이터는 emit 됐는데 모든 점이 frame 밖.

**최초 사례**: 20260503_112703 보고서 (v4.5.2 사용자 보고). "주요 시나리오 —
확률 × 영향" 버블 차트 빈 frame. composer 가 emit 한 x/y 가 0~5 또는
0~100 범위였을 가능성 (composer prompt 가 0~1 정규화를 명시 안 함).

**원인**: `charts.js:drawBubble` 의 x/y 스케일이 `domain([0, 1])` 고정.
composer 가 `{x: 0.6, y: 0.7}` (0~1) 가정 emit 시 OK 지만, `{x: 60, y: 70}`
(0~100) emit 시 모든 bubble 이 frame 우상단 *밖*으로 나가 안 보임.

**검증 체크리스트**:
- [ ] charts.js 의 모든 차트 type 이 *데이터 extent 자동 감지* — 고정 domain
  금지. d3.extent / d3.min / d3.max 활용.
- [ ] composer prompt 의 bubble (또는 좌표 차트) 가이드에 *값 범위* 명시
  ("x, y 모두 0~1 정규화" 같은 강제) — 또는 자동 감지로 무관해지게.
- [ ] 빈 frame / 빈 차트 자체를 차단 (CHART-AP-7) — has_data 검증.
- [ ] size 도 동일 robust 처리 (composer 가 0~1 가정 위반해도 정규화).

**Fix (v4.5.3)**:
- `drawBubble`: `domain([0, 1])` → `domain([min, max])` 자동 감지 (d3.min/max).
  0 포함 + 약간의 padding 으로 frame 안 항상 보임.
- size 도 sMax 기반 정규화 (composer 가 0~10 emit 해도 OK).

---

## CHART-AP-13: Gantt 차트 시간축 누락 + 행 라벨/note 충돌

**증상**: Gantt 차트에 *X축 (시간 눈금) 자체가 안 그려짐*. 막대들은 있지만 어느
시점인지 모름. 또한 막대가 매우 짧은 경우 (start ≈ end) 막대 *오른쪽 끝* note
가 다음 행 라벨 또는 좌측 zone 라벨과 *동일 X 위치* 에 그려져 글자가 한 줄에
짓눌린 것처럼 보임.

**최초 사례**: 20260503_142254 보고서 (v4.5.3 사용자 보고). "테슬라·중국·한국
자율주행 일정 비교" gantt — 행 라벨 "OTA 패치" + note "테슬라 FSD HW4 한국
운영" 이 한 줄에 합쳐져 보임. X축 없어서 어떤 연도인지 추정 불가. 사용자 인용:
"의미 불명의 차트가 나오고 있어".

**원인**: `charts.js:drawGantt`
- X축 (`d3.axisBottom`) 자체가 없음 — 막대 위치만 그림.
- 막대 폭 `Math.max(2, x1 - x0)` — 최소 2px 만 보장. start === end 면 점.
- note 항상 `x1 + 6` (막대 우측 외부) — 막대가 짧으면 행 라벨과 X 가 겹쳐
  글자 충돌.

**검증 체크리스트**:
- [ ] 시간 축 차트 (gantt / line) 는 *반드시* X축 (눈금 + 라벨) 그릴 것.
  사용자가 "어느 시점" 을 즉시 인지해야 함.
- [ ] start/end 입력 정규화: numeric / 'YYYY' / 'YYYY-MM' 모두 지원.
  start === end 면 합리적 default 폭 (예: 0.4 단위) 적용.
- [ ] note placement 가 행 라벨 / 다른 막대 note 와 X 충돌 없는지 검증.
  막대 폭 ≥ N px 이면 *내부* 라벨, 아니면 *외부 우측* 으로 분기.
- [ ] 가벼운 격자선 (시간 축 tick 별) 으로 시점 인지 보조.

**Fix (v4.5.4)**:
- 시간축 자동 추가 (`d3.axisBottom` 풍 — tick + label + grid).
- 입력 정규화 `parseTime()` — 'YYYY-MM' 도 numeric 으로 변환.
- start === end 면 0.4 단위 폭 부여 (점이 아니라 짧은 bar).
- 막대 최소 폭 2 → 6px.
- note placement: 막대 폭 ≥ 60px 이면 *내부* 흰글자, 아니면 *외부 우측*.

---

## CHART-AP-15: gantt zero-duration emit (point-in-time 이벤트 모음을 gantt 로)

**증상**: gantt 차트로 emit 됐지만 모든 row 의 `start == end` (단일 시점 이벤트들의
나열). 막대 폭 ≈ 0 → row 라벨만 일렬로 떠 있는 *빈 차트*. v4.5.4 의 fallback
(0.4 단위 / 최소 6px) 으로 시각적으로는 막대가 보이지만, 본질적으로 *기간*
차트인 gantt 의 의미를 잃음. 사용자가 "왜 다 똑같은 점만 찍혀 있나" 라고
인지함. CHART-AP-13 의 시간축 fix 와 별개의 *type 선택* 회귀.

**최초 사례**: 20260515_125106 보고서 ("코스피 8000 돌파") — section 4 의
"2026년 5월 코스피 8000 돌파 타임라인" gantt. 7개 row 중 6개가 zero-duration
(예: `{label:"코스피 +4.32%", start:"2026-05-11", end:"2026-05-11"}`). 이건 본질이
*event sequence* (시점 마커들의 나열) 이지 *duration timeline* 이 아님. 사용자
인용: "타임라인이라고 했는데 막대가 다 뭉쳐있다."

**원인**:
- composer prompt 의 gantt spec 이 `[{label, start, end, note?}] 사건 구간` 으로만
  적혀 있어, *기간* 의도가 약함. composer 가 "타임라인" 키워드 만 보고 gantt 를
  선택.
- `GanttGuard` 가 start ≤ end 만 검증 — zero-duration ratio 는 검증 X. point-in-time
  데이터가 그대로 통과.

**검증 체크리스트**:
- [ ] gantt 의 `start != end` row 가 *전체의 30% 이상* 인가? (아니면 type 부적합)
- [ ] composer prompt 에 "point-in-time 이벤트 모음은 gantt 금지, line + event
      marker 또는 본문 list 로" 명시되어 있는가?
- [ ] `GanttGuard.validate_durations` 가 zero-duration ratio > 0.7 거절하는가?
- [ ] 사용자 keyword "타임라인" 이 항상 gantt 로 매핑되지 않는가? (event sequence
      는 line / list)

**Fix (v5.1.2)**:
- `GanttGuard.validate_durations` 신규 — zero-duration ratio > 0.7 면 reject 메시지
  "CHART-AP-15 가드: gantt zero-duration ratio X% > 70%".
- `narrative_composer` 의 gantt spec 행에 *point-in-time 모음 emit 금지* 명시 +
  대안 (line + event marker / 본문 list) 안내.
- `tests/regression/test_chart_correctness.py::test_gantt_guard_rejects_all_zero_duration`
  로 회귀 가드.
- 본 보고서는 `patch_report.py 20260515_125106 --remove-chart 4:0` 로 일회성 제거.

---

## CHART-AP-16: donut 2-segment 안티패턴 (정보 손실 + subtitle 잉여)

**증상**: donut 차트로 emit 됐지만 segment 가 단 2개 — 보통 한쪽이 "기타" /
"비-X" 같은 *잡탕 segment*. 정보 손실 (잡탕 segment 내부 구성이 사라짐) + subtitle
이 이미 같은 비율 (예: "X 가 83%") 을 텍스트로 전달 → 차트 자체가 잉여. 더
나쁜 건, 렌더러 (`drawDonut`) 가 `data.length < 3` 이면 silently return 해서
*제목·부제·출처는 그대로 보이는데 도넛 그래픽만 사라진 빈 카드*가 됨. 사용자가
"차트가 안 보인다" 로 인지.

**최초 사례**: 20260515_125106 보고서 ("코스피 8000 돌파") — section 2 의
"외국인 5월 누적 순매도 구성" donut. data 가 `[{반도체:16.8}, {비반도체:3.4}]`
2 segment. "비반도체" 안에 금융 / 화학 / 자동차 등이 다 뭉쳐 정보 손실.
subtitle 이 이미 "20.2조원 중 16.8조원(83%)이 반도체" 라고 같은 비율을
전달하고 있었음. 게다가 렌더러가 silent return → 사용자에겐 빈 카드.

**원인**:
- `DonutGuard.data: list[DonutSlice] = Field(min_length=2)` 와 `drawDonut` 의
  `if (data.length < 3) return` 사이 *불일치*. 가드는 통과시키고 렌더러는
  drop → 빈 카드 회귀.
- composer prompt 의 donut spec 이 "(3개 이상, 균등 X)" 라고 *주석* 만 있고
  강제 체크는 없음 — composer 가 "구성" 단어 보면 자동으로 도넛 선택.

**검증 체크리스트**:
- [ ] donut segment 가 *반드시* 3 개 이상인가? (`DonutGuard.validate_segment_count`)
- [ ] composer prompt 에 "2 segment 도넛 emit 금지, 비율 카드 또는 본문 한 문장
      으로 대체" 명시?
- [ ] `DonutGuard` 의 `min_length` 와 `drawDonut` 의 `length < N` 가드가 *동일
      값* 인가? (mismatch 가 빈 카드 회귀의 원인)
- [ ] subtitle 이 이미 같은 비율 (%) 을 표현하면 chart_critic 의 Q2 (takeaway
      중복) 로 drop 되는가?

**Fix (v5.1.2)**:
- `DonutGuard.data` `min_length=2 → 3` + `validate_segment_count` 신규.
  메시지: "CHART-AP-16 가드: donut segment N 개 — 3 미만은 정보 손실".
- `narrative_composer` donut spec 에 "2 segment 도넛 emit 금지" 명시.
- `tests/regression/test_chart_correctness.py::test_donut_guard_rejects_two_slices`
  로 회귀 가드.
- 본 보고서는 `patch_report.py 20260515_125106 --remove-chart 2:0` 로 제거.
  subtitle 이 이미 충분한 정보 전달.

---

## CHART-AP-17: 차트 type starvation (신설 type 이 production 에서 거의 emit X)

**증상**: 새 chart type 을 production 에 wiring 했는데도 (composer 프롬프트,
가드, charts.js 모두 정합) 보고서에 거의 등장 안 함. 캔들 차트가 v5.2.0 에
추가됐으나 v5.3.0 직전까지 production 13종 중 약 70% 가 bar/line/donut 으로
collapse 한 회귀.

**근본 원인** (v5.2.0 사례):
- 새 type 의 자연 수요 부족 — 대부분의 보고서가 지수/환율/금리 (line) 또는
  국가별 비교 (bar) 였고, 개별주 사건 (candle 의 자연 영토) 은 드물었음.
- composer SYSTEM_PROMPT 가 새 type 을 *한 줄 설명* 만 박아두고 "언제
  쓰는지" 의 negative constraint (다른 type 금지 조건) 부재.
- 사용량 텔레메트리 부재 → 회귀를 *측정* 할 수 없어 한참 후에 발견.
- `_DEFAULT_REQUIRED_EXHIBITS` 에 새 type 가 매핑 안 됨 → research_director
  가 자동으로 요구하지 않음.

**검증 체크리스트** (v5.3.0 5-Layer Usage Guarantee):
- [ ] **Layer 1** — `src/visual/usage_log.py:KNOWN_CHART_TYPES` 에 새 type 등재
- [ ] **Layer 2** — composer SYSTEM_PROMPT 결정 트리에 *negative constraint*
      포함 (예 "OHLC 있음 → candle, LINE 금지")
- [ ] **Layer 3** — `_DEFAULT_REQUIRED_EXHIBITS` 의 method 중 하나가 새 type
      를 `visual_type_hint` 로 명시
- [ ] **Layer 4** — `deterministic_gate._check_chart_type_monotony` 가
      standard ≥3 차트에 distinct <2 면 soft fail
- [ ] **Layer 5** — `tests/regression/fixtures/chart_type_scenarios.yaml`
      에 sample_prompt + negative_examples 포함된 시나리오 항목

**Fix (v5.3.0)**:
- 5-Layer Usage Guarantee 동시 도입 (위 5 항목 모두).
- `tests/regression/test_chart_type_diversity.py` 가 active set ↔
  `KNOWN_CHART_TYPES` 1:1 매칭 강제 — 신규 type 도입 시 fixture 갱신 PR
  체크리스트 강제 (drift 즉시 fail).

---

## CHART-AP-18: 차트 entry 애니메이션의 motion 회귀 (v5.3.0 신설)

**증상**: entry 애니메이션이 (a) 스크롤 속도를 방해 / jank 유발, (b) editorial
mono 톤 (신문/잡지) 과 충돌 (지나친 bounce / glow / hue shift), (c)
`prefers-reduced-motion: reduce` 사용자의 접근성 요구 무시, (d) 한 번 본 차트
가 다시 viewport 진입 시 반복 재생되어 산만, (e) 모바일에서 ambient drift
(bubble/network 부유) RAF 가 스크롤 perf 잠식.

**근본 원인** (v5.3.0 도입 시 가능한 회귀):
- duration 이 700ms 초과 — 스크롤 빠르게 내리면 다음 차트 도착 전 transition
  미완성 (사용자가 정적 SVG 만 볼 가능성)
- bounce 강도가 너무 큼 (overshoot > 1.5) — 신문 톤에서 "재밌는" 느낌이
  과해 editorial 합 깨짐
- 반복 재생 — IntersectionObserver `unobserve` 안 하고 두번째 진입에 재생
- `prefers-reduced-motion` 미체크 — `_motionEnabled()` 가 거짓이어도 그냥 진행
- ambient (bubble/network 의 부유) 가 viewport 밖에서도 RAF 돌아 모바일
  배터리 + scroll FPS 잠식

**검증 체크리스트**:
- [ ] duration ≤ 700ms (각 transition 시간 + delay 합산 기준)
- [ ] easing 은 `easeCubicOut` 또는 `easeBackOut(<=1.4)` — `easeElasticOut`
      금지 (mono 톤 충돌)
- [ ] `_motionEnabled()` 가 `prefers-reduced-motion` 점검 후 false 면 즉시
      return (정적 렌더로 fallback)
- [ ] `IntersectionObserver` 가 `unobserve(stage)` 호출 (1회 재생 후 멈춤)
- [ ] backward-compat: IntersectionObserver 미지원 브라우저 → 즉시 렌더
      (애니메이션 X)
- [ ] ambient drift (만약 도입 시) 는 viewport 밖일 때 RAF pause

**Fix (v5.3.0)**:
- `charts.js:_applyEntryAnimation` 의 path/rect/circle 별 transition 700ms
  / 380ms / 440ms 상한 강제.
- `_motionEnabled()` = `window.matchMedia('(prefers-reduced-motion: reduce)')`
  체크.
- `IntersectionObserver` `rootMargin: '0px 0px -8% 0px', threshold: 0.12` +
  `unobserve` 직후 호출.
- ambient drift 는 본 PR 미도입 (검토 후 별도 PR 시 RAF pause 가드 필수).

---

## CHART-AP-19: 재무·수익성 보고서에서 sankey/waterfall 분해 차트 누락 (v5.4.3 신설)

**증상**: 사건 카테고리가 명백한 *재무 분해* (기업 실적 / 재무제표 / 수익성
분석 / 세그먼트 매출) 인데 composer 가 시계열 + bar + slope 만 박고 sankey
또는 waterfall (분해형 차트) 을 0개 emit. 추이는 보여주는데 *구조* 를 안
보여주는 보고서.

**대표 회귀 사례** (v5.4.2 — 삼성전자 2026 1Q 보고서
`analysis_20260520_134233`):
- event_category: '기업 재무 / 반도체 산업'
- 본문 narrative: 매출 333.6조 → DS / 모바일 / 디스플레이 / 가전 → 비용 →
  영업이익 57.2조. DS 영업이익률 37.3% → 66%. HBM4 ASP 분해. 명백한
  multi-stage 흐름 + P&L 1차원 분해.
- composer emit: `line ×4 + slope + bar + range_bar + forecast` — distinct
  5종이라 monotony 가드 통과, **sankey/waterfall 0**.

**근본 원인 — 결정 트리 collapse**:
- SYSTEM_PROMPT 의 [차트 type 결정 트리] (v5.2.14) 가 step 1 = "시간축
  있음?" 으로 시작. 시계열 데이터 (관련 기업 주가 + 분기 이익 추이) 가
  풍부하면 composer 가 step 1 분기로 먼저 collapse → step 3 (카테고리 비교)
  의 sankey / waterfall branch 까지 못 도달.
- 5-Layer Guarantee 의 Layer 4 (다양성 쿼터, `chart_type_monotony`) 도
  distinct ≥2 만 검사 — distinct 5종이라 silent 통과. sankey 누락에 *알람
  자체가 울리지 않음*.
- Layer 3 (method × exhibit 매트릭스) 의 `_DEFAULT_REQUIRED_EXHIBITS` 는
  research_director opt-in (디폴트 OFF) 이라 작동 안 함.

**검증 체크리스트**:
- [ ] composer SYSTEM_PROMPT 의 결정 트리에 *step 0 "사건 카테고리가 재무·
      수익성·기업 분석인가?"* 가 step 1 보다 먼저 평가됨을 명시
- [ ] step 0 매치 시 sankey 또는 waterfall *최소 1개* emit 강제 (시계열·
      추이는 *함께* OK, 단 분해 차트 ≥1 가 함께 있어야)
- [ ] anti-bias 가드 섹션에 "재무·수익성 보고서인데 시계열 + bar 만 박지 말
      것" 명시적 라벨링
- [ ] sankey type 별 가이드에 구체 사례 (총매출 → 사업부 → 영업이익, 적자
      flow 는 `negative=true`) 포함

**Fix (v5.4.3)**:
- `src/agents/narrative_composer.py:SYSTEM_PROMPT` 의 [차트 type 결정 트리]
  에 **step 0** 신설 (재무 카테고리 → sankey/waterfall ≥1 강제).
- 같은 SYSTEM_PROMPT 의 anti-bias 가드 + sankey type 가이드 동시 보강 (3곳).

**한계 — 향후 강화 옵션**:
- (A) Layer 4 다양성 쿼터 보강: *재무 카테고리 한정* sankey/waterfall 미포함
  시 soft fail 추가. 현재 distinct 만 검사 — 특정 type 누락은 검사 X.
- (B) Layer 3 활성화: `enable_research_director` opt-in 을 디폴트 ON 으로
  전환하면 `_DEFAULT_REQUIRED_EXHIBITS` 가 method × type 매핑 강제. 단 LLM
  호출 1개 추가.
- (C) 본 fix 만으로 v5.4.3 이후 재무 보고서의 sankey 빈도 추적 — telemetry
  로 효과 측정 후 (A) / (B) 도입 여부 결정.

---

## CHART-AP-20: sankey viewBox 과대 프로비저닝으로 "위로 쏠림" (v5.4.6 신설)

**증상**: 노드 수가 적은 (≤9) sankey 의 viewBox 가 320px (`H = max(320, ...)`)
로 강제 클램프되는데, 실제 컨텐츠는 그 안에서 ~180px (55%) 만 차지하고 나머지
~140px (45%) 가 빈 공간. 추가로 가중치가 큰 노드 (예: 메모리 65)가 자연스럽게
첫 컬럼 위쪽에 배치되면서 시각적 무게 중심이 위쪽으로 쏠림. 결과적으로 다크
스테이지 아래쪽 30~40% 가 휑하고 차트가 "위로 기울어진" 인상.

**예시 (v5.4.5 보고서, 8-노드 sankey)**:
- viewBox: `760×320`, zones.data.h = 268
- 컨텐츠 vertical extent: y=70.7 ~ 252.05 (181px)
- 위 여백: 42.75px (16%) / 아래 여백: 43.95px (16%) — 수학적으론 중앙
- 그러나 메모리 (65) → HBM/DRAM (22+43=65) 의 두꺼운 흐름이 위쪽 50% 에
  몰리고, 파운드리 (30) / LSI (5) 의 가는 흐름이 아래쪽 → 시각 무게 중심
  은 y=120 부근 (전체의 45%) 으로 위로 시프트.
- 다크 스테이지 height = 361px (SVG 341 + 20px padding) — 컨텐츠 영역
  대비 약 60px 의 dead space 가 아래쪽 끝에 누적되어 보임.

**왜 회귀했나**:
- `H = Math.max(320, Math.min(560, 60 + nodes.length * 28))` — 8 노드면 자연
  사이즈 284 < 320 으로 클램프 → 36px 강제 추가.
- `MAX_NODE_H_RATIO = 0.50` — 가장 두꺼운 컬럼 한 줄도 zones.data 의 50% 만
  사용 가능. 8-노드 케이스에선 컬럼 stack 이 60~65% 만 차지 → 나머지 35~40%
  가 위·아래 여백.
- v5.3.0 의 sankey 4원칙 (anchor 압축 / source-weighted ordering / 분기 V 분산
  / column y-centering) 은 컬럼간 *상대* 정렬을 정확히 잡지만, *컬럼 안*
  위·아래 휑함은 다루지 않음.

**검증 체크리스트**:
- [ ] `drawSankey` 가 노드 positioning 끝난 뒤 실제 content vertical extent
      를 측정한다 (`d3.min(nodes, n => n.y0) - LABEL_PAD_ABOVE` 등).
- [ ] tightH = extent + 위·아래 breathing room (각 14px) 으로 SVG viewBox 를
      *재설정*. 단 tightH < 원래 H 일 때만 (큰 sankey 는 그대로).
- [ ] 컨텐츠 전체를 `dy = SVG_TOP_BREATH - contentTop` 만큼 시프트해 위 여백
      을 고정 14px 로 정렬.
- [ ] 시프트는 link slice 계산 *전에* 수행 (slice 는 `n.y0` 사용).
- [ ] 회귀 테스트: 8-노드 (이 케이스) 와 12-노드 (regression) 양쪽 모두에서
      content_top_gap, content_bottom_gap 의 차이가 4px 이하인지 확인.

**Fix (v5.4.6)**:
- `src/templates/static/charts.js:drawSankey` 의 colKeys forEach 직후, link
  slice 할당 전에 content-fit viewBox 패스 신설:
  ```js
  const LABEL_PAD_ABOVE = 18;  // 중간 col 라벨 (y0-6, font 11)
  const LABEL_PAD_BELOW = 22;  // 중간 col value 라벨 (y1+14, font 10)
  const SVG_TOP_BREATH = 14;
  const SVG_BOT_BREATH = 14;
  let contentTop = Infinity, contentBot = -Infinity;
  nodes.forEach(n => {
    const above = (n.col > 0 && n.col < maxCol) ? LABEL_PAD_ABOVE : 0;
    const below = (n.col > 0 && n.col < maxCol) ? LABEL_PAD_BELOW : 0;
    if (n.y0 - above < contentTop) contentTop = n.y0 - above;
    if (n.y1 + below > contentBot) contentBot = n.y1 + below;
  });
  const tightH = (contentBot - contentTop) + SVG_TOP_BREATH + SVG_BOT_BREATH;
  if (tightH > 0 && tightH < H) {
    const dy = SVG_TOP_BREATH - contentTop;
    nodes.forEach(n => { n.y0 += dy; n.y1 += dy; });
    svg.attr('viewBox', `0 0 ${W} ${Math.round(tightH)}`);
  }
  ```
- 8-노드 DS 케이스: viewBox 320 → 238 (26% 축소), 위 7.86px / 아래 9.88px
  로 균형. 다크 스테이지 361px → 263px.
- 12-노드 회귀 케이스: viewBox 396 → 256 (35% 축소), 마찬가지 균형.
- 알고리즘 (v5.3.0 sankey 4원칙) 은 *보존*. 결과만 압축.

**한계 — 향후 강화 옵션**:
- (A) 모든 차트 type 의 viewBox 에 본 content-fit pass 일반화 (bar / network
  / heatmap 도 비슷한 dead space 가능). 단 차트별 라벨 위치가 달라 type 별
  PAD 상수 분기 필요 — 본 fix 는 sankey 한정.
- (B) Composer 가 emit 시 적정 H 를 함께 지정하게 하는 방안 — 단 LLM 부담
  추가. 본 deterministic fix 가 충분.

---

## CHART-AP-21: sankey 좌·우 zones margin 부족으로 라벨 잘림 (v5.4.7 신설)

**증상**: 첫 컬럼의 라벨 (예: "DS 매출") 과 값 (예: "100.0") 이 viewBox 왼쪽
경계 밖으로 뻗어 잘림. 동시에 마지막 컬럼의 라벨 끝에서 viewBox 오른쪽
경계까지 ~170px 의 과도한 공백. 차트가 "왼쪽으로 치우친" 시각 인상.

**예시 (v5.4.6 DS 매출 sankey)**:
- `computeZones(W, H, { left: 8, right: 8, ... })` — 좌·우 margin 각 8px
- 첫 컬럼 (`col=0`) 노드: `x0 = zones.data.x + 0*colWidth + 8 = 16`
- 라벨 위치: `x = x0 - 6 = 10`, text-anchor: `end`
- "DS 매출" 텍스트 폭 ~65px → 좌측 시작 좌표 ~-55 (음수) → **viewBox 밖**
- 마지막 컬럼: x1=521, 라벨 시작 x=527, "범용 DRAM·NAND" 끝 ~625
- 오른쪽 공백: 760 - 625 = 135px (18% wasted)
- 결과: 시각적으로 차트가 좌측에 몰리고 좌측 라벨은 truncated

**왜 회귀했나**:
- 초기 `drawSankey` 구현 (v5.3.0) 에선 라벨 짧고 (예: "출"), 좌측 margin 8px
  로도 텍스트 잘림이 미미했음.
- v5.4.6 의 content-fit viewBox 픽스로 SVG 가 자연 비율 (760×238) 로 렌더되면
  스테이지 폭 ~810 에 1.066× scale — 라벨이 viewBox 단위로 더 명확히 잘림.
- 한국어 첫 컬럼 라벨 ("DS 매출" / "총매출" / "매출 흐름") 은 평균 4~8 글자,
  font 11 에서 50~80px 폭 — `text-anchor: end at x0-6` 으로 음수 좌표까지 뻗음.

**검증 체크리스트**:
- [ ] 첫 컬럼 라벨이 한국어 8 자 이내일 때 viewBox 안 fully visible 한지 확인.
- [ ] 마지막 컬럼 라벨 (예: "범용 DRAM·NAND" / "캡티브 (사내 SoC·SSD)" 14자)
      이 viewBox 오른쪽 안에 들어가는지 확인.
- [ ] zones margin 변경 시 col 위치 식 `x0 = zones.data.x + col*colWidth + 8`
      이 그대로 작동 (zones.data 가 margin 을 자동 적용).

**Fix (v5.4.7)**:
- `src/templates/static/charts.js:drawSankey` 의 zones margin:
  - `{ left: 8, right: 8, ... }` → `{ left: 80, right: 120, ... }`
- left=80: 첫 컬럼 라벨 ("DS 매출" 등 ≤8자 한국어) 텍스트가 x≈22 부터 시작해
  viewBox 안 fits
- right=120: 마지막 컬럼 라벨 ("캡티브 (사내 SoC·SSD)" 등 ≤15자) 텍스트가
  x≈490 부터 시작해 ~615 에서 끝나며 viewBox 안 fits (~145px 여유)
- 좌·우 비대칭 (left<right) — 한국어 sankey 의 last col 라벨이 first col 라벨
  보다 평균 1.5~2× 길다는 휴리스틱 반영

**재발 (v6.0.1) — 고정 margin 의 구조적 한계**:
- 증상 재현 (analysis_20260606_114653, Colossus sankey): 첫 컬럼 라벨이
  "(Col 1, … MW, GPU 22만+)" / "(Col 2, … GPU 55.5만 발주)" 처럼 18~25자로
  길어지자 left=80 으로도 부족 — 라벨 앞부분 "(Col 1, …" 가 음수 좌표로 빠져
  잘리고 화면엔 "MW, GPU 22만+)" 만 남음.
- 근본 원인: **고정 margin 은 라벨 길이가 가변인 한 항상 어떤 입력에서 깨진다.**
  v5.4.7 의 left=80/right=120 은 ≤8자/≤15자 휴리스틱에 맞춘 값 — 그 가정을
  벗어나는 긴 라벨엔 무력. margin 을 더 키우면 짧은 라벨에선 과도한 공백.
- **Fix (v6.0.1) — 수평 content-fit viewBox** (`drawSankey` 끝, 라벨 렌더 후):
  모든 라벨이 그려진 뒤 `svg.node().getBBox()` 로 실제 content extent 측정 →
  viewBox 를 가로로 넓혀(`minX = min(vx, bb.x-12)`, `maxX = max(vx+vw,
  bb.x+bb.width+12)`) 라벨 overflow 를 포함. `preserveAspectRatio=xMidYMid` 가
  자동 중앙 정렬 → 차트가 살짝 축소되며 중앙으로 모이고, 좌·우 어느 쪽 라벨도
  잘리지 않는다. 수직 content-fit (CHART-AP-20) 은 보존 (vy/vh 그대로 사용).
  getBBox 실패 시 (레이아웃 전) try/catch 로 기존 viewBox 유지 — graceful.
- 교훈: **라벨 길이가 가변인 SVG 차트는 고정 margin 이 아니라 렌더 후 bbox 기반
  content-fit 으로 프레이밍한다** (network 재설계 CHART-AP-25 와 동일 원칙).

**재발 2 (v6.0.2) — expand-only content-fit 의 좌측 쏠림**:
- 증상: v6.0.1 적용 후 라벨 잘림은 사라졌으나(전부 보임) 차트가 *왼쪽으로 쏠리고*
  오른쪽에 ~150px 빈 여백이 남음 (사용자 재보고, IMG_2629).
- 근본 원인: v6.0.1 의 content-fit 이 **확장만(expand-only)** — `maxX = max(vx+vw,
  bb.x+bb.width+pad)` 로 원본 우측 경계(W=760)를 *유지*했다. 컨텐츠 우측 끝은 ~608
  인데 viewBox 우측은 760 → 그 사이 ~150px 가 빈 채로 viewBox 에 포함되어,
  `xMidYMid` 가 (빈 공간 포함) 전체를 중앙에 놓다 보니 컨텐츠는 좌측으로 쏠림.
- **Fix (v6.0.2)**: viewBox x/width 를 원본 프레임과 무관하게 **content bbox +
  동일 pad 로 양쪽 모두 타이트하게** 설정 (`x = bb.x - pad`, `w = bb.width +
  2*pad`). 빈 여백이 사라져 `xMidYMid` 가 컨텐츠를 폭에 맞춰 정확히 중앙 배치.
- 교훈 (보강): content-fit 은 **양방향 tight-fit** 이어야 한다. expand-only 는
  잘림은 막아도 비대칭 여백으로 정렬을 깬다 — 원본 프레임을 lower bound 로 쓰지 말 것.

**재발 3 (v6.0.3) — 라벨 포함 bbox 중앙정렬 ≠ 흐름 코어 중앙정렬**:
- 증상: v6.0.2 tight-fit 적용 후에도 "중앙이 아니다" (사용자 재보고, IMG_2641).
- 근본 원인: v6.0.2 는 **라벨 포함 bbox** 를 중앙에 뒀다. 좌·우 라벨 폭이 비대칭
  이면(여기선 좌측 "Colossus 2 (블랙웰 GPU 55.5만 발주)" ≫ 우측 "월 임대 매출
  21.7억 달러") bbox 중심은 맞아도 *흐름 코어(노드/리본)는 넓은 라벨 반대쪽으로
  쏠린다*. 사람 눈은 라벨이 아니라 **흐름 다이어그램** 의 중앙을 본다.
- **Fix (v6.0.3)**: 정렬 기준을 라벨 포함 bbox → **노드 코어**(첫 컬럼 `x0` ~ 마지막
  컬럼 `x1`)로 변경. 좌·우 여백 `m = max(overhangL, overhangR) + pad` 로 *동일* 하게
  잡아 ① 코어 중심 = viewBox 중심(코어 중앙정렬) ② `m ≥ 각 overhang` 으로 무클립.
  짧은 라벨 쪽에 여분 여백이 생기나 흐름은 정중앙.
- 교훈 (재보강): "차트 중앙정렬" 의 기준은 **시각적 주체(흐름/플롯 영역)** 이지
  텍스트 라벨 포함 bbox 가 아니다. 라벨은 비대칭 장식 — 코어를 기준으로 대칭 margin.

**재발 4 (v6.0.4) — 코어 중앙정렬도 비대칭 라벨이면 빈 여백으로 "치우침"**:
- 증상: v6.0.3 코어 중앙정렬 후에도 우측에 큰 빈 여백 → 여전히 좌측 치우침으로
  보임 (사용자 재보고, IMG_2642).
- 근본 원인: 끝-컬럼 라벨이 길면("Colossus 2 (블랙웰 GPU 55.5만 발주)" ~28자) 그쪽
  overhang 이 커진다. 코어를 중앙에 둬도 좌·우 margin 을 `max(overhang)` 로 동일하게
  잡으니 *짧은 라벨 측에 (overhangL − overhangR) 만큼 빈 여백* 이 남는다. 코어는
  수학적으로 중앙이지만, 한쪽의 큰 빈 공간이 시각적 "치우침" 인상을 만든다.
- **Fix (v6.0.4)**: 첫·마지막 컬럼의 긴 라벨을 **2줄로 줄바꿈**(`wrapEndLabel` — " ("
  또는 공백에서 접기, max ~14자/줄) + 노드에 세로 중앙정렬(`drawEndLabel`). overhang 이
  ~40% 줄고 좌·우가 대칭에 가까워져, 코어 중앙정렬과 결합 시 빈 여백이 최소화(≈pad)
  된다. 흐름이 빈 공간 없이 중앙에 온다.
- 교훈 (최종): 라벨 비대칭이 정렬을 깨면 **정렬 로직만으로는 한계** — 라벨 자체의
  가로 폭을 줄바꿈으로 bound 해야 한다. 정렬(코어 기준) + 라벨 wrap 의 *결합* 이 답.

**★ 최종 해법 (SSOT — 4회 재발 후 v6.0.4 확정). 끝-라벨 차트 중앙정렬은 이 3종 결합.**
> "sankey(또는 끝-라벨이 가로로 뻗는 차트)가 중앙이 아니다" 회귀가 또 오면, margin
> 숫자를 만지지 말고 **아래 3종이 모두 켜져 있는지** 확인한다. 하나라도 빠지면 재발.
>
> 1. **라벨 렌더 후 content-fit** (고정 margin 금지): 라벨까지 그린 *뒤* `getBBox()`
>    로 실제 extent 측정. 고정 `{left,right}` margin 은 라벨 길이가 가변인 한 반드시
>    어떤 입력에서 깨진다 (재발 1 — 잘림).
> 2. **코어 기준 중앙정렬** (라벨 포함 bbox 기준 금지): viewBox 를 *노드 코어*(첫
>    컬럼 `x0` ~ 마지막 컬럼 `x1`) 중심에 맞추고 좌·우 margin 을 `max(overhangL,
>    overhangR)+pad` 로 동일하게. 라벨 포함 bbox 를 중앙에 두면 좌·우 라벨 폭이
>    비대칭일 때 흐름이 쏠린다 (재발 2·3). 사람 눈은 라벨이 아닌 *흐름* 의 중앙을 본다.
> 3. **긴 끝-라벨 2줄 wrap** (`wrapEndLabel`/`drawEndLabel`): 1·2 만으론 긴 라벨의
>    overhang 이 커 짧은 쪽에 빈 여백이 남아 여전히 치우쳐 보인다 (재발 4). 끝-컬럼
>    라벨을 " (" 또는 공백에서 접어 overhang 을 ~40% 줄여 좌·우 대칭화.
>
> 코드 위치: 전부 `src/templates/static/charts.js:drawSankey` 의 노드 라벨 렌더 +
> 함수 끝 viewBox 블록. 마커: `wrapEndLabel` / `흐름 코어`. 수직 정렬(CHART-AP-20)은
> 직교 — 건드리지 말 것. 발행본 반영: `patch_report.py <id> --rerender-only` (charts.js
> 인라인 갱신, 데이터 무변경 → revision 유지가 정상).

**한계 — 향후 강화 옵션** (※ 1·2·3 채택 후 잔여 옵션):
- (A) 동적 margin 계산 — 실제 라벨 텍스트 너비 (canvas.measureText) 측정 후
  zones margin 산정. v6.0.4 의 `getBBox()` content-fit 이 사실상 이를 대체 (렌더 후
  실측). 별도 사전 측정은 폰트 로드 타이밍 의존이라 불채택.
- (B) 라벨 wrap (`<tspan>`/다단) — **v6.0.4 에서 채택** (`wrapEndLabel`). 당초 "마지막
  수단" 으로 적었으나, 끝-라벨 비대칭이 큰 한국어 sankey 에선 정렬만으론 부족해 필수가
  됐다. 1줄 가독성 표준은 ≤14자 라벨에 한해 유지(짧으면 wrap 안 함).

---

## CHART-AP-22: sankey 중간 컬럼 라벨 stacking 충돌 (v5.4.7 신설)

**증상**: 중간 컬럼 (`0 < col < maxCol`) 의 노드 위쪽 라벨 (예: "파운드리")
과 인접 상위 노드의 value 라벨 (예: "65.0") 이 vertical 거리 2~7px 으로
겹쳐 시인성 파괴. 사용자 표현 — "시인성이 박살나있네."

**예시 (v5.4.6 DS 매출 sankey, 메모리/파운드리 인접)**:
- 메모리 노드: y0=77, y1=164.1
- "65.0" value 라벨: y=164.1+14=178.1 (font 10 baseline)
- 파운드리 노드: y0=182.1 (MIN_NODE_PAD=18 만큼 떨어짐), y1=222.3
- "파운드리" 라벨: y=182.1-6=176.1 (font 11 baseline)
- 두 라벨의 baseline 차이: 176.1 - 178.1 = -2px (역전!)
- font 11 텍스트 높이 ~10px (cap 8 + desc 2) → "파운드리" 텍스트 영역:
  y=168.1 to 178.1
- font 10 텍스트 영역: y=171.1 to 180.1
- **overlap 7px** (y=171.1 to 178.1)

**왜 회귀했나**:
- `MIN_NODE_PAD = 18` 은 v5.3.0 초기 구현에서 *노드끼리* 의 vertical 간격을
  의미했지, *라벨 stacking* 을 고려하지 않음.
- 라벨 위치:
  - 위쪽 라벨: `y0 - 6` (font 11 baseline)
  - 값 라벨: `y1 + 14` (font 10 baseline)
- 두 노드 사이 사용 가능 영역: `(y0_lower - 6) - (y1_upper + 14) = pad - 20`
- pad=18 일 때 사용 가능 = -2 → 반드시 overlap
- 가중치 큰 노드 (메모리 65) 가 같은 컬럼의 작은 노드 (파운드리 30, LSI 5)
  와 인접할 때 항상 발생 — 모든 컬럼 mixed-weight sankey 에서 회귀.

**검증 체크리스트**:
- [ ] 중간 컬럼 ≥2 노드의 sankey 에서 인접 노드의 value 라벨 (`y1+14`) 과
      하위 노드 라벨 (`y0-6`) 의 baseline 차이 ≥ 16px 인지 확인.
- [ ] font 11 (label) + font 10 (value) 텍스트 영역이 픽셀-수준에서 겹치지
      않는지 (위 baseline + 2 < 아래 baseline - 8).
- [ ] 회귀 fixture: 메모리/파운드리/LSI 같은 3 노드 컬럼 sankey 의 라벨
      vertical 간격 측정.

**Fix (v5.4.7)**:
- `src/templates/static/charts.js:drawSankey` 의 `MIN_NODE_PAD`:
  - `18` → `36`
- 산식: pad = 위 라벨 height (8) + 값 라벨 height (7) + 텍스트 여백 (5) ×2
  = 30px 최소, 36 으로 4px 여유 buffer
- 결과 (메모리/파운드리 케이스): "65.0" baseline y=178.1, "파운드리"
  baseline y=200.1 → 차이 22px → 텍스트 영역 5~6px 여유 gap.

**부수 효과 — 차트가 vertical 로 약간 길어짐**:
- 컬럼 stack 이 (n-1)×18 → (n-1)×36 만큼 늘어남 (3-노드 col 1: +36px,
  4-노드 col 2: +54px).
- 8-노드 DS 케이스: v5.4.6 의 tightH 238 → v5.4.7 의 tightH ~308.
- 여전히 원래 H=320 보다 작음 (content-fit pass 가 작동) — 다크 스테이지
  높이 263px → ~340px. 위로 쏠림은 해소된 상태에서 라벨도 깨끗.

**한계 — 향후 강화 옵션**:
- (A) Adaptive pad — 인접 노드의 라벨 length 가 짧으면 pad 작게, 길면 크게.
  단 복잡도 ↑ 반대급부 작음.
- (B) 중간 컬럼 라벨 위치를 노드 측면 (col 0 / col maxCol 처럼) 으로 이동 —
  stacking 자체 회피. 단 flow 위에 라벨이 올라가 시각 잡음 증가.

---

## CHART-AP-23: forecast 차트 y축 도메인이 actual 점을 제외 (v5.4.8 신설)

**증상**: `drawForecast` 의 y축이 forecast 데이터 (low/mid/high) 범위만 반영하고
actual 데이터를 무시 → actual 의 값이 forecast 범위 아래/위에 있을 때 데이터
점이 **차트 영역 밖**에 박힘. 사용자 시각: "선이 중간에 끊긴 것처럼 보임."

**예시 (v5.4.7 HBM 보고서)**:
- actual: 2023=4, 2024=14, 2025=25
- forecast: 2026(low=30, mid=35, high=42), 2027(40,50,60), 2028(50,65,78)
- y 도메인 계산: `yMin = d3.min(forecast, d => +d.low) ?? d3.min(actual, ...)`
- `??` 는 nullish 일 때만 fallback — forecast 가 비어있지 않으면 actual 무시.
- 결과: yMin = 30 (forecast.low 의 min), yMax = 78 (forecast.high 의 max)
- 패딩 적용 후 y축 범위 ≈ 22~85 → **actual 2023=4 와 2024=14 가 22 아래로
  떨어져 차트 영역 밖**. 2025=25 도 30 아래라 y축 grid 영역 밖.
- 시각적으로 actual 선이 차트 하단 경계 밖에서 시작해 "25" 점이 grid 안에
  들어오긴 하지만 forecast 영역과 단절되어 보임.

**왜 회귀했나**:
- `??` 연산자는 *오직 left=null/undefined* 일 때만 right 로 fallback.
  `d3.min(forecast, ...)` 는 forecast 가 비어있어도 `undefined` 반환, 비어있지
  않으면 항상 숫자 반환 → 사실상 actual 은 forecast 가 있는 한 무시.
- `d3.min` 의 0 처리: 모든 값이 0 이면 `min` = 0 (falsy 지만 not nullish), 
  `??` 는 그대로 0 사용 — `||` 였다면 falsy 처리되어 actual 로 fallback 됐을 것.
  현재 코드의 `??` 자체가 의도와 다른 결과.
- 의도는 "forecast 가 있으면 forecast 만 봐도 충분 (forecast.low/high 가
  actual 을 covered 한다고 가정)" — 그러나 actual 이 forecast 범위 밖이면 깨짐.

**검증 체크리스트**:
- [ ] actual 의 최저값이 forecast.low 의 min 보다 작은 케이스에서 actual 의
      모든 점이 y축 grid 안에 들어가는지.
- [ ] actual 의 최고값이 forecast.high 의 max 보다 큰 케이스도 동일 확인.
- [ ] y축 도메인 산정 시 actual + forecast 양쪽 값 모두 포함.

**Fix (v5.4.8)**:
- `src/templates/static/charts.js:drawForecast` 의 y 도메인:
  ```js
  const yValues = actual.map(d =&gt; +d.y)
    .concat(forecast.flatMap(d =&gt; [+d.low, +d.mid, +d.high]));
  const yMin = d3.min(yValues);
  const yMax = d3.max(yValues);
  ```
- actual.y / forecast.low / forecast.mid / forecast.high 4종 모두 산입 →
  모든 데이터 점이 항상 y 범위 안. forecast 가 비어있어도 작동 (yValues 가
  actual 만 포함).

---

## CHART-AP-24: forecast 차트 actual ↔ forecast 선 단절 (v5.4.8 신설)

**증상**: actual 선 (solid) 이 마지막 actual 해 (예: 2025) 의 점에서 끝나고,
forecast 선 (dashed) 은 첫 forecast 해 (예: 2026) 에서 시작. 둘 사이 1년치
gap 으로 시각 단절 + cone (low~high shaded area) 도 2026 의 low/high 부터
시작해 actual 끝점과 disconnected.

**예시 (v5.4.7 HBM 보고서)**:
- actual 2025 점 (25) 의 위치와 forecast 2026 점 (mid=35) 사이 1년치 X 간격.
- solid 검정 선이 (2025, 25) 에서 끝남.
- dashed 빨강 선이 (2026, 35) 에서 시작.
- 두 선이 서로 만나지 않아 차트가 "중간에 끊긴" 인상.
- cone 도 마찬가지로 2026 부터 시작 — actual 끝점에서 fan 이 펼쳐지지 않음.

**왜 회귀했나**:
- `drawForecast` 가 actual 과 forecast 를 *완전히 별도* path 로 렌더.
- actual 의 lineA path 는 actual 만, forecast 의 lineF 는 forecast 만.
- 두 데이터셋의 boundary (fork_at 시점) 에서 연결 segment 없음.
- 표준 fan chart 컨벤션 (cone 이 fork 시점에서 한 점으로 narrow → 미래로
  확장, mid 선은 actual 끝점에서 dashed 연속) 미적용.

**검증 체크리스트**:
- [ ] forecast 의 첫 점이 actual 의 마지막 점과 *동일 위치* 에서 시작하는지
      (data prepending 또는 동일 boundary year 컨벤션).
- [ ] cone 이 fork 시점에서 low=mid=high=actual.y 인 한 점에서 시작해 미래로
      퍼지는 fan 형태인지.
- [ ] forecast 가 비어있을 때 actual 단독 line 만 그려지고 컴포넌트 누락
      에러 없는지.

**Fix (v5.4.8)**:
- `src/templates/static/charts.js:drawForecast`:
  ```js
  let forecastBridge = forecast;
  if (forecast.length &amp;&amp; actual.length) {
    const lastA = actual[actual.length - 1];
    forecastBridge = [
      { x: lastA.x, low: +lastA.y, mid: +lastA.y, high: +lastA.y },
      ...forecast,
    ];
  }
  ```
- `forecastBridge` 의 첫 점 = actual 의 마지막 점 (low=mid=high=actual.y 인
  한 점). cone area 와 mid 선 모두 이 bridge 를 사용 → 시각적으로:
  - cone: fork 시점에서 한 점, 미래로 갈수록 low~high 폭 확대 (fan 형태)
  - mid 선: actual 끝점에서 시작해 forecast 의 마지막 mid 까지 dashed 연속
- actual 의 lineA / actual 끝점의 dot / forecast 끝점의 dot / fork_at 의
  vertical 라인은 그대로 (`forecast` 원본 사용) — bridge 는 cone+mid 렌더용
  로컬 변수.

**한계 — 향후 강화 옵션**:
- (A) Boundary year 데이터 컨벤션 강제 — composer 가 forecast 의 첫 항목을
  actual 마지막 해 + 1 이 아닌 *actual 마지막 해와 동일* 로 emit 하도록 prompt
  조정. 현재 fix 는 데이터 그대로 두고 *렌더링* 에서만 bridge — 가장 비침습.
- (B) Forecast 의 첫 점이 actual 의 마지막 해와 같으면 (composer 가 그렇게
  emit), bridge 를 skip — 중복 점 방지. 현재 fix 는 다른 해여도 안전.

---

## CHART-AP-25: 행위자 관계도를 radial network (hairball) 로 렌더 (v5.5.5 신설)

**증상**: `drawNetwork` 가 노드를 원 위에 *입력 순서대로* 균등 배치하고 엣지를
직선으로 그림. 노드 위치가 아무 의미를 안 가져 엣지가 전부 중심을 관통하는
실타래(hairball)가 됨. "누가 주도/대립인지", "누가 영향력이 큰지"가 위치로 안
읽히고, 라벨 8글자 잘림 + 관계는 dash 로만 구분해 범례 대조 필요. 시인성 최악.

**원인**: 관계망을 node-edge 그래프로 그리는 형식 자체가 편집 보고서엔 부적합.
force/radial 레이아웃은 본질적으로 가독성이 낮다 (FT/Economist 가 이해관계자
관계를 hairball 로 안 그리는 이유).

**Fix (v5.5.5)**: radial → **인접행렬 (adjacency matrix)**. 데이터 계약
(`{nodes:[{id,label,group}], links:[{source,target,type}]}`) 불변 — composer /
`NetworkGuard` / capability registry / usage_log 전부 무변경, `drawNetwork`
*렌더러 본문만* 교체 (type 명 `network` 유지). 행위자를 행·열에 두고 셀이 관계
type 인코딩 (대립=`--down`+✕ / 동맹=`--accent` / 영향=`accent-hatch` /
연관=`dots`), 대각선 `--border` fill-opacity 0.35 차단, 진영(group) 정렬로 블록
구조 노출. 선 교차 0 → hairball 원천 제거. viewBox 는 `getBBox` content-fit 으로
산출 → 라벨/범례 자동 중앙 정렬 + 클리핑 0 (수동 margin 추정의 fragility 제거).
셀 rect 는 `data-anim="static"` 태깅 — 64셀 fade 캐스케이드 + opacity 덮어쓰기
방지. 모크업: `samples/actor_relationship_redesign_compare.html` (radial vs 대안 3종).

---

## CHART-AP-26: slope 차트 좌·우 라벨 충돌 (v5.5.8 신설)

**증상**: `drawSlope` 가 라벨을 `yScale(value)` 의 점 위치에 그대로 그림. 여러
시리즈가 *동일/근접 값* 을 가지면 라벨이 같은 y 에 포개져 글자가 뭉개짐. 실제
사례 — "effective per-token price" slope 에서 세 모델이 모두 2025-10 기준 100.0
→ 좌측 라벨 "Gemini 100.0 / GPT 100.0 / Claude 100.0" 가 한 점에 겹쳐
`GeGPGmi 100.0` 처럼 판독 불가. (기준선 정규화 차트는 좌측 값이 다 같아 특히 빈발.)

**원인**: 라벨 위치에 충돌 회피(dodge)가 없음. 점·선은 정상이나 텍스트만 겹침.

**Fix (v5.5.8)**: 좌·우 라벨 baseline 을 최소 간격(`minGap=13`)으로 dodge —
값 순으로 정렬 후 하향 push → 하단 초과 시 그룹 상향 시프트 → 상단 클램프. 점·선은
실제 값 위치 유지(시각 정확성 보존), 라벨이 dodge 로 떨어지면 점→라벨 가는
connector(0.6px). 단일/충분히 떨어진 라벨은 기존과 동일하게 렌더. charts.js 는
보고서 공유 자산이라 재배포/`--rerender-only` 시 기존 보고서도 자동 교정.

---

## CHART-AP-27: 폭포수(waterfall) 차트 부호(±) 미인코딩 (v5.8.8 신설)

**증상**: 폭포수 차트가 *증가/감소를 모두 위로 올라가는 막대* 로 그림. 실제 사례 —
"HBM 매출 변동 요인" 폭포수에서 `100 → +22 → +12 → 8 → 9 → 117`. 의미상 22·12는
더하기, 8·9는 **빼기**(미 규제·중국 위축, takeaway 도 "더하기 두 줄, 빼기 두 줄"
명시)인데, 8·9가 위로 쌓이는 막대로 렌더돼 누적이 ~150까지 올라갔다가 최종 막대만
117로 뚝 떨어지는 비논리적 그림. `100+22+12+8+9 = 151 ≠ 117` 인데도 차트가 통과.

**원인**: 폭포수 step 데이터에 방향(부호)이 없거나 렌더러가 무시. 모든 step 을
양(+)으로 쌓아 감소 요인이 시각적으로 증가로 둔갑. 연결선(connector)이 최종 막대와
어긋남.

**Fix 방향 (결정적 가드 — Codex/LLM 불필요)**: `WaterfallCoherenceGuard` —
① `base + Σ(signed steps) == final_total` 검증, 불일치 시 차트 drop/flag.
② step 별 부호를 데이터 계약에 강제(`delta` 부호 또는 `direction: up|down`),
감소 step 은 running total 에서 *아래로* 그림. 위반 시 `_drop_invalid_charts` 에서
silent drop. 회귀 fixture: `chart_type_scenarios.yaml` 에 waterfall 부호 케이스 추가.

---

## CHART-AP-28: 빈 차트 프레임 — 데이터 0인데 틀/라벨만 렌더 (v5.8.8 신설)

**증상**: "주간 사망자 추이" small_multiples 가 다섯 도시(키이우/드니프로/자포리자/
폴타바/하르키우) 패널 *틀과 라벨만 띄우고 내부 데이터는 전부 비어* 발행. 독자는
즉시 "검수 없이 자동 발행됐다"고 판단 — 출고 중단 사유.

**원인**: 차트 구조(패널·축·라벨)는 emit 됐으나 data series 가 빈 배열/0 포인트.
"빈 데이터면 차트 없음" 규칙(Chart System)이 small_multiples 등 일부 type 에
미적용 — `_drop_invalid_charts` / `_TYPE_TO_GUARD` 가드 구멍.

**Fix 방향 (결정적 가드 — LLM 불필요)**: `EmptyChartGuard` — 모든 type 에 대해
*렌더 가능한 데이터 포인트 총합 == 0* 이면 차트 통째 drop (프레임도 안 그림).
small_multiples 는 *모든 패널* 이 비면 drop, 일부만 비면 빈 패널 제외. 회귀
fixture 에 type 별 empty-data 케이스 추가.

---

## CHART-AP-29: NaN/null 값을 사용자에게 그대로 노출 (v5.8.8 신설)

**증상**: 본문/카드에 `코스피 nan% 1M` 이 그대로 노출. 시장 데이터가 부분 결측인데
계산식이 NaN 을 만들고 그 문자열이 렌더까지 흘러감. (06:00 일일 브리핑은 KRX 데이터
미확정 시각이라 빈 series → NaN 빈발 가설.)

**원인**: market_fetcher graceful degrade(빈 series)가 차트/카드 수치 계산으로
전파될 때 `NaN`/`null`/`Infinity` 를 거르지 않음. 변화율 `(a-b)/b` 에서 b 결측 시 NaN.

**Fix 방향 (결정적 가드 — LLM 불필요)**: `NaNExposureGuard` — 사용자 노출 수치
문자열에 `NaN`/`nan`/`null`/`undefined`/`Infinity` 가 있으면 해당 값을 숨기거나
카드/차트를 drop. 더 근본적으로 시장 수치 결측 시 *그 수치를 아예 emit 하지 않음*
(WRITE-AP-15 와 연동 — composer 가 결측 시점에 자유서술로 메우지 않게).

**v7.9.17 — 소스 차단 가드 (실제 재발, 사용자 catch).** 2026-06 코스피 회귀: Yahoo
`^KS11` 의 미완성 *마지막 봉*이 `close=NaN` 으로 흘러들어 ① 코스피 line/candle 차트가
빈 프레임(takeaway 는 9,064 인데 차트 마지막은 nan), ② 감시 스트립 `코스피 nan%`,
③ 종합지수 카드 `7815.59 → nan` 으로 노출. `NaNExposureGuard` 는 *문자열* 검출이라
계산 *이전* 의 데이터 결측은 못 막았다. 다층 차단:
1. **소스** — `market_fetcher._df_to_ohlc` / `_to_float` 가 `math.isfinite()` 로 비유한
   봉을 *생성 단계에서* skip (`nan <= 0` 이 False 라 기존 `c<=0` 가드를 빠져나가던 허점).
2. **합류 길목** — `orchestrator._sanitize_market_nan` 가 fetch 직후 `context.time_series`
   의 비유한 봉을 결정적 제거(모든 소스 공통 chokepoint). compact strip 빌더도 `_is_finite_num`
   로 방어.
3. **발행본 복구** — `scripts/patch_report.py --sanitize-ts-nan` 로 이미 나간 보고서의
   NaN 봉 제거 + subtitle/등락률/takeaway 재계산 (LLM 0, URL 보존).

---

## 회귀 발견 시 — 표준 프로토콜

1. 본 문서의 9 패턴 중 어디에 해당하는지 분류
2. 시스템적 회귀 (모든 보고서 영향) → 코드 수정 (`charts.js` 또는 composer prompt). 새 패턴이면 본 문서에 CHART-AP-N 항목 추가
3. 이 보고서만 영향 → `scripts/patch_report.py` 로 데이터 수정 (LLM 0)
4. fix 후 *DEVLOG.md* 에 commit 사유 + 본 문서 항목 reference
5. 다음 commit 부터 본 문서 체크리스트 점검 (PR 시 자동 점검 가능 → 향후 GitHub Action 으로 확장)

---

## CHART-AP-30: 시장 시계열 풀 차트의 곡선 보간 — 실제 가격 경로 왜곡 (v7.0.1 신설, 사용자 catch)

**증상**: 코스피·환율 같은 지수/가격 line 차트가 부드러운 곡선으로 그려져 실제 가격의
움직임(segment-by-segment jaggedness)이 시각적으로 사라짐. `curveMonotoneX` 가 점 사이를
베지에로 평탄화 — 데이터에 없는 중간 경로를 그려넣는 *왜곡*.

**경위**: v5.2.9 에서 *같은 이유로* compact strip sparkline 은 `curveLinear` 로 교정됐으나
(당시에도 사용자 catch), 풀 카드 렌더러들(line/area/dual_line/forecast/stacked_area/
small_multiples)과 connected_scatter(CatmullRom — 점 사이가 부풀어 좌표 경로 왜곡)에는
곡선 보간이 잔존. 2026-06-11 사용자 재지적으로 전면 교정.

**Fix**: 시장·값 시계열 렌더러 전부 `curveLinear` 통일 (v7.0.1). 유일한 예외 = `bump`
(순위 축 — 값이 아닌 서수 전환의 관례적 s-curve 연출이라 monotoneX 유지).

**가드**: 신규 시계열 렌더러 추가 시 곡선 보간 금지가 기본값. 곡선을 쓰려면 "값이 아닌
서수/연출 축" 임을 본 항목에 예외로 등재하고 사유를 적을 것.

---

## CHART-AP-31: composer 가 시계열 차트 데이터를 듬성하게 추려 emit (일별 밀도 손실) (v7.0.2 신설, 사용자 catch)

**증상**: 지수/가격 차트가 8~12 포인트로 납작하게 렌더 — "일별 종가가 기준이어야
하는데 정보가 너무 없다" (사용자). market_fetcher 는 일별 3M (~60거래일) 을 공급하지만,
차트 데이터를 *composer LLM 이 손으로 emit* 하는 구조라 토큰 절약으로 듬성하게 추려
쓴다. SYSTEM_PROMPT 의 "row 그대로 변환" 지시는 *지시 준수* 에 의존 — 100% 보장 안 됨
(`_ensure_time_series_chart` 의 교훈과 동일 패턴: 누락은 막았지만 *밀도* 는 안 봤다).

**Fix**: `src/orchestrator.py:_densify_ts_charts` (v7.0.2, 결정적 0-LLM, 디폴트 ON) —
composer 가 emit 한 line/candle/area 차트의 title 에서 instrument 매칭 → 차트 *자신의
날짜 창* 안에 실 데이터 행이 더 많으면 그 창의 전체 일별 행으로 데이터 교체. 의도적
확대 창 (사건 주간) 보존, 단축 날짜 표기는 전체 series 폴백, 이벤트 마커 (row.event) 는
날짜/suffix 매칭으로 보존. type·제목·해석은 composer 권한 그대로 — 데이터 행만 실측 치환.

**가드**: `tests/regression/test_ts_densify.py` 6케이스 (창 내 교체 / 확대 창 보존 /
단축 표기 폴백 / 이벤트 보존 / candle OHLC / 불변 케이스).

---

## CHART-AP-32: sankey 노드 라벨의 수치 + 자동 값 라벨 중복 표기 (v7.5.1 신설, 사용자 catch)

**증상**: 실보고서 sankey 노드에 같은 숫자가 두 번 — '하만 3.8' (라벨) 바로 아래
'3.8' (렌더러 자동 합계). 사용자가 "목업 sankey 는 마음에 드는데 실보고서 sankey 는
마음에 안 들었다" 로 보고 — 실데이터 목업 제작 중 재현.

**원인**: `drawSankey` 는 노드 통과량(in/out 합)을 *자동으로* 보조행에 표기하는데,
composer SYSTEM_PROMPT 의 sankey 구체 예가 'nodes=[총매출 133.9조 / ... / 영업이익
57.2조]' 식으로 **라벨에 수치를 박도록** 가르쳤다 (갤러리 fixture 도 동일). LLM 이
예시를 따르면 모든 노드가 이중 표기.

**Fix (v7.5.1, 이중)**:
1. 렌더러 결정적 가드 — 자동 값(`,.1f` 포맷 또는 정수형)이 라벨 문자열에 이미
   포함돼 있으면 자동 값 라벨 생략. `value_label` 명시는 항상 존중.
2. composer SYSTEM_PROMPT 구체 예를 '라벨은 이름만 + ★ 수치 박지 말 것' 으로 교정.
   `value_label` 은 자동 수치를 *대체* 하므로 '마진 42.7%' 같은 *다른* 정보만,
   수치도 함께 보이려면 '57.2 · 마진 42.7%' 처럼 직접 결합.

**가드**: 위 1 의 렌더러 dedup 이 프롬프트 미준수(구 패턴 emit)도 흡수. 갤러리·실데이터
목업 fixture 를 클린 문법으로 교정 (`samples/chart_gallery_v7.html`,
`samples/v7_5_realdata_mockup.html`).

---

## CHART-AP-33: scatter 라벨 충돌 (근접 점들의 라벨 중첩) (v7.9.8 신설, 사용자 catch)

**증상**: IV 스큐 scatter('행사가별 내재변동성')의 우측 군집 — '풋 1,525'·'콜 1,527.5'·
'콜 1,462.5' 라벨이 같은 자리에 겹쳐 읽을 수 없음. 모든 라벨이 점 오른쪽 고정 오프셋
`(cx+8, cy+4)` 으로만 찍혀 근접 점들의 라벨이 포개졌다.

**원인**: `drawScatter` 가 라벨 충돌 회피(dodge) 없이 고정 오프셋만 사용. slope 차트는
`dodgeYs` 로 세로 분산을 했지만 scatter 엔 미적용.

**Fix (v7.9.8)**: ① plot 우측 66% 안쪽 점은 라벨을 *왼쪽*(anchor end)에 둬 plot 밖
잘림 방지 ② 같은 쪽 라벨끼리 `dodgeYs(minGap 13, [top,bottom] 클램프)` 세로 분산 ③ 점에서
멀어진 라벨엔 가는 connector. 점·축 위치는 실제 값 그대로(불변). 발행본은 charts.js
변경이라 `patch_report <id> --rerender-only` 로 동일 URL 재렌더 시 적용.

## CHART-AP-34: dot_matrix(와플) 좌측 쏠림 — 가운데 정렬 누락 (v7.9.8 신설, 사용자 catch)

**증상**: '코스피 100종목 중 등락 분포' dot_matrix 가 차트 카드 왼쪽으로 쏠리고
오른쪽에 큰 빈 여백. 100칸 그리드(좌측 고정 padL=26) + 범례(우측 고정)가 W=720 의
왼쪽 ~440px 만 차지.

**원인**: `drawDotMatrix` 가 grid 를 좌측 고정·범례를 우측 고정 좌표로 그려, 콘텐츠
실폭이 viewBox 보다 좁을 때 우측 여백이 그대로 남음 (sankey CHART-AP-20/21 과 동류 —
content-fit 부재).

**Fix (v7.9.8)**: 그리드+범례를 한 `<g>` 에 담고 렌더 후 `getBBox()` 로 실제 content
extent 측정 → `translate((W-bb.width)/2 - bb.x, 0)` 로 가로 중앙정렬 (sankey 의 content-fit
패턴 동일). getBBox 미지원 환경은 좌측정렬 폴백. 발행본은 `--rerender-only` 로 적용.

## CHART-AP-35: composer diverging_bar 에서 지수 등락률(neg)을 0/누락으로 emit (v7.9.14 신설, 사용자 catch)

**증상**: 장마감 브리핑(analysis_20260618_184833) '지수 등락률 vs 종목 하락비율' diverging_bar
에서 KOSPI 의 `neg`(지수 등락률) 막대·값이 통째로 안 보임. 데이터를 보면 KOSPI `neg=0`,
KOSDAQ `neg=3.01` — composer 가 KOSPI 등락률을 0 으로 넣음(부제엔 '지수는 +2.25%' 라
써놓고 데이터엔 0, 자체 모순). 렌더러는 `neg>0` 일 때만 좌측 막대를 그려 누락처럼 보임.

**원인**: composer 가 *직접 선택해 만든* diverging_bar(내 결정적 차트 아님)의 데이터 오류.
LLM 이 한 행(KOSPI)의 등락률을 0 으로 떨어뜨림 — 산문/부제와 차트 데이터의 정합성 미보장.
(부수적으로 등락률 2~3% 와 하락비율 80% 를 한 발산 축에 두는 스케일 불일치도 약점.)

**Fix (v7.9.14 — 결정적 가드)**: orchestrator 가 장마감 브리핑(`fetch_kr_market_internals`)
한정으로, diverging_bar 행 라벨이 `KOSPI`/`KOSDAQ`(코스피/코스닥)인데 `neg` 가 0/누락이면
`context.time_series` 의 실측 지수 등락률(절댓값)로 채운다. 행사가 라벨 OI diverging_bar
(`neg=put_oi`)는 라벨이 KOSPI/KOSDAQ 가 아니라 비대상. 발행본은 데이터 직접 보정 후 재렌더.

---

## CHART-AP-36: 행위자 관계도(network/인접행렬) 포맷 폐기 (v7.9.17 신설, 사용자 요청)

**경위**: 이재명 G7 릴레이 보고서의 '만난 9개국' 행위자 관계 인접행렬(`network` 차트)을
두고 사용자가 "큰 의미도 없고 공간도 너무 차지한다 — 아예 저 포맷을 없애버리자"고 지적.
CHART-AP-25 에서 radial hairball → 인접행렬로 리디자인했으나, 정보 밀도 대비 세로 공간
점유가 과해 보고서 가독성을 떨어뜨린다는 판단.

**결정 (포맷 영구 제거)**: `network` 차트 type 을 시스템에서 폐기.
1. **emit 차단** — composer `SYSTEM_PROMPT` 의 type 목록·데이터 스키마·결정 트리·emit
   가드에서 network 제거. 결정 트리의 '관계망(노드-엣지)' 분기는 "본문 서술 또는 표로"로
   대체.
2. **drop 가드** — `schemas.py:validate_chart_data` 가 `network` 를 무조건 `(False,
   "network 포맷 폐기 (CHART-AP-36)")` 로 반환 → `ComposedSection._drop_invalid_charts`
   가 silent drop. composer 가 실수로 emit 해도 어떤 보고서에도 렌더 안 됨.
3. **레지스트리 정리** — `usage_log.KNOWN_CHART_TYPES`, `VISUAL_CAPABILITY_REGISTRY.yaml`
   (guarded 17→16, total 30→29), `chart_type_scenarios.yaml`(시나리오 삭제), `charts.js`
   (RENDERERS·`drawNetwork` 제거), `research_director` stakeholder_matrix exhibit
   (network→table) 에서 제거. 회귀 테스트 동시 갱신.
4. **발행본** — 이미 나간 보고서는 `scripts/patch_report.py <id> --show` 로 인덱스 확인 후
   `--remove-chart SEC:CHART` 로 제거.

`NetworkGuard`/`NetworkLink` Pydantic 클래스 정의는 보존(타 import 안전)하되 매핑에서 분리.

---

## CHART-AP-37: 행위자 관계도를 force/physics 레이아웃으로 렌더 (v8.0.0 선제 — network 교훈 상속)

**맥락**: v8.0.0 르포 트랙의 신규 `stakeholder_map`(인물·국기·로고가 들어가는 이해당사자
관계도)은 노드가 큰 카드라, force-directed 배치를 쓰면 노드가 겹치고 중심 관통 실타래가
생겨 CHART-AP-25(network hairball)를 그대로 재현한다. 이미지(국기/사진/로고)로 노드가
더 커지므로 위험이 오히려 크다.

**규칙 (선제 차단)**: `drawStakeholderMap` 은 **force/physics/simulation 절대 금지**.
노드 좌표는 데이터로 받지 않고 **결정적으로 계산**한다 — ① x = 진영(col: left/center/right)
칼럼 ② y = 칼럼 내 stack(세로 중앙 정렬 → 같은 행은 직선 연결) ③ 엣지는 결정된 노드
위에 직각+라운딩(엘보) 후행 레이어로 얹고, 노드를 이동시키지 않는다 ④ 한 노드의 다중
연결은 가장자리에서 서로 다른 지점에 분산(한 점 겹침 금지) ⑤ getBBox content-fit viewBox
로 자동 중앙정렬. 스키마(`StakeholderMapGuard`)는 좌표 필드를 입력으로 받지 않는다.
모크업 SSOT: `samples/stakeholder_map_gallery.html` / `samples/stakeholder_map_themes.html`.

---

## CHART-AP-38: 등록된 dict-데이터 차트 type 의 validate_chart_data 분기 누락 → 100% silent drop (v8.2.10 신설, 사용자 catch)

**증상**: 르포 2막 이해당사자 본문이 "(아래 관계도)"로 stakeholder_map 을 가리키는데
*어떤 르포에서도* 관계도가 안 보인다(섹션 charts=[]). composer 는 정상 emit 하는데도
v8.0.0 이래 한 번도 렌더된 적이 없다. 2026-06-27 사용자 catch.

**원인**: `stakeholder_map` 데이터는 dict `{nodes, edges}` 형식인데,
[schemas.py:validate_chart_data](../src/visual/schemas.py) 의 분기 사슬에 *stakeholder_map
전용 분기가 빠져* 있었다. dict 형식 type(stacked/dual_line/forecast/sankey/bump/combo
등)은 각자 `elif chart_type == "...": guard(**data)` 분기를 갖는데 stakeholder_map 만
누락 → 맨 끝 `else`(list[dict] 가정) 분기로 떨어져 `isinstance(data, list)` False →
`(False, "stakeholder_map 는 list[dict] 형식 필요")` 반환 → `ComposedSection._drop_invalid_charts`
가 **유효 데이터를 100% silent drop**. 가드(`StakeholderMapGuard`)·렌더러(`drawStakeholderMap`)·
레지스트리(`_TYPE_TO_GUARD`)는 다 있었으나 *디스패치 한 줄*이 빠져 도달 불가였다.

**Fix (v8.2.10)**: validate_chart_data 에 `elif chart_type == "stakeholder_map":`
분기 추가(sankey 와 동형 — dict 면 `guard(**data)`, 아니면 명확한 사유 반환). 일반화
회귀로 `_TYPE_TO_GUARD` 의 dict-데이터 type 들이 유효 최소 데이터로 validate_chart_data
를 통과하는지 강제([tests/regression/test_chart_correctness.py](../tests/regression/test_chart_correctness.py)
의 `test_every_dict_guard_type_has_dispatch_branch`). **신규 dict-형식 chart type 추가
시 반드시 validate_chart_data 분기 + 본 회귀의 samples 에 추가** (분기 누락 = 조용한 100% drop).

---

## CHART-AP-39: 대륙 간 스케일 지도를 평면 메르카토르로 렌더 → 빈 바다·구석 왜곡 (v8.2.13 신설, 사용자 catch)

**증상**: 환태평양 메모리 공급망(한국·미국·중국·대만) 보고서의 *첫 장면* 지도가
이상하게 나온다. 태평양 한가운데(center [-170, 28])를 중심으로 펼친 평면 지도가
대부분 빈 검은 바다 + 우측 구석에 북미만 걸리고, 한국·중국·대만 마커는 화면 밖으로
밀려난다. 2026-06-28 사용자 catch.

**원인**: composer 가 *대륙 간 스케일* 토픽(경도 span 154°)에 `projection: "globe"`
대신 평면 메르카토르(projection 무지정)를 emit. 평면 메르카토르는 경도 span 이 크면
거리·방향을 심하게 왜곡한다 — 환태평양처럼 자오선을 가로지르는 무대는 평면에서
가장자리로 흩어진다. 프롬프트는 '대양 횡단 공급망 → globe' 를 안내하나(LLM 지시
준수 의존) 누락됐다. globe 렌더 경로(`maps.js:renderGlobe`)는 이미 있었으나 payload
가 그것을 가리키지 않았다.

**Fix (v8.2.13)**: 결정적 안전망 2단.
① [orchestrator.py:`_promote_intercontinental_globe`](../src/orchestrator.py) — composer 가
projection 을 지정 안 한 평면 지도에서 마커 경도 span(자오선 wrap 보정)을 계산해
대륙 간 임계(>=100°)면 `projection="globe"` 로 자동 격상. 좁은 권역(지역 사건)·
composer 가 projection 명시한 경우는 no-op(평면 유지, byte-equal). 풀 파이프라인
post-process 블록(`_reconcile_visual_references` 다음)에 배선, 디폴트 ON.
② 발행본 한정 교정은 [patch_report.py](../scripts/patch_report.py) `--map-projection
globe` 로 수술적 전환(LLM 0, URL 동일). globe 는 드래그 회전·휠 확대되는 '움직이는'
지도이고 arcs 가 대권 최단경로로 그려져 대륙 간 흐름이 직관적이다.

---

## CHART-AP-40: stakeholder_map 엣지 라벨이 카드·다른 라벨 위에 찍혀 가림 (v8.2.16 신설, 사용자 catch)

**증상**: 르포 행위자 관계도(`stakeholder_map`)에서 관계 라벨 배지(`○ 설계` / `90만장`
/ `● 인프라` 등)가 가운데 칼럼 카드(`이재명 정부` / `김O씨`) 위에 겹쳐 찍혀, 그 카드의
역할 텍스트(`자금·입법 설계` / `금○○○ 현직`)를 가리고 라벨끼리도 같은 지점에 스택돼
글자가 뭉개진다. 2026-06-30 사용자 catch (르포 관계도).

**원인**: `drawStakeholderMap` 이 엣지 라벨을 **양 끝 부착점의 기하학적 중점**
(`cx=(A.x+B.x)/2`, `cy=(A.y+B.y)/2`)에 그대로 찍는다. `OpenAI`(왼쪽 col0) →
`삼성전자`(오른쪽 col2)처럼 col0↔col2 를 가로지르는 엣지는 중점이 정확히 **가운데
칼럼(col1)** 영역에 떨어지고, 라벨은 카드보다 위 레이어에 그려지면서 **카드 충돌 회피
로직이 전무**했다. 다중 cross 엣지의 라벨이 같은 중앙 지점에 몰리면 라벨끼리도 겹친다.
slope 차트는 이미 baseline dodge(CHART-AP-26)로 해결했으나 관계도엔 미적용.

**Fix (v8.2.16)**: [charts.js:`drawStakeholderMap`](../src/templates/static/charts.js)
라벨 배치에 결정적 de-confliction 패스 추가 — ① 노드 카드 + 이미 배치한 라벨을
장애물(AABB)로 보고 ② 중점에서 시작해 수직(±12~72) 우선·이어 수평(±22~66)으로 빈
자리를 탐색해 밀어내고 ③ 8px 이상 밀리면 중점→라벨로 가는 가는 연결선(border, opacity
0.6)을 남겨 어느 선의 라벨인지 보존한다(slope dodge 패턴 상속). + **선 스타일 범례**
(실제 등장한 유형만, 2종 이상일 때만 — `→ 영향·주도` / `● 협력·자금` / `✕ 대립` /
`○ 연관`)를 차트 하단에 자동 추가해 두 가지 시각 언어(자본 흐름 vs 영향·공급 관계)를
해독할 단서를 준다. 데이터 계약(nodes/edges)·가드·registry 불변, 순수 렌더 변경.
발행본은 `git pull` + 재배포 후 `patch_report.py <id> --rerender-only` 로 URL 동일 적용
(stakeholder_map 노드 텍스트 자체는 `--replace` 미도달 — `title/subtitle/note` 만 훑음,
교정 필요 시 `--add-stakeholder-map` 으로 차트 재주입).

---

## CHART-AP-41: stakeholder_map 교차 칼럼 엣지의 세로 구간이 한 통로에 포개짐 (v8.2.17 신설, 사용자 catch)

**증상**: CHART-AP-40(라벨 겹침)을 고친 뒤에도, 관계도에서 **선 자체가 뭉쳐** 어느
선이 어디로 가는지 알 수 없다. 특히 가운데 칼럼(`이재명 정부`/`김용범`/`국민성장펀드`)
→ 오른쪽 칼럼(`삼성전자`/`SK하이닉스`)으로 가는 여러 엣지의 **세로 구간이 같은 x 에
포개져** 한 줄처럼 보인다. 2026-06-30 사용자 catch(라벨 픽스 후 후속).

**원인**: `smRoute` 가 모든 교차 엣지를 **양 끝 부착점의 수평 중점(`mx=(x0+x1)/2`)
한 곳에서 직각으로 꺾는다.** 가운데→오른쪽 엣지들은 부착 x 범위가 같으니 mx 도 거의
같은 값 → 세로 구간이 전부 같은 통로에 겹친다. 부착점 분산(slot)·라벨 de-confliction
(CHART-AP-40)은 있었으나 **선의 세로 통로(레인) 분리가 없었다.**

**Fix (v8.2.17)**: [charts.js:`drawStakeholderMap`](../src/templates/static/charts.js)
에 결정적 **레인 라우터** 추가 — ① 칼럼 사이 gap(col0↔col1=A, col1↔col2=B)을 통로로
보고 ② 각 교차 엣지를 *대상 칼럼 왼쪽 gap* 에 배정(col0→col2 는 가운데 칼럼을 가로질러
오른쪽 gap B 에서 하강 — 세로 구간이 카드 통로를 피함) ③ 같은 gap 의 엣지들을 source/
target y 평균으로 정렬해 gap 폭 안에서 **균등 분배한 레인 x(`bendX`)** 로 꺾는다.
세로 구간이 `(gr-gl)/(n+1)` 간격으로 서로 벌어져 분리된다. 같은 칼럼 수직 체인(왼쪽
올트먼→OpenAI→…)은 기존 직선 유지. 더불어 칼럼 간격 `GAP 128→152`·세로 간격
`VSP 120→140` 으로 레인·진입선에 숨 쉴 공간 확보. 교차 엣지 라벨은 레인(세로 구간)
위에 올려 실제 선과 붙였다. 데이터 계약·가드·registry 불변, 순수 렌더 변경.
발행본은 재배포 후 `patch_report.py <id> --rerender-only` 로 URL 동일 적용.

---

## CHART-AP-42: stakeholder_map 노드 자산 어휘 부족 — 미지원 국기 silent 강등 + 로고·인물 실사진 슬롯 부재 (v8.2.18 신설, 사용자 catch)

**증상**: 르포 관계도의 카드 완성도가 낮다. ① composer 가 `flag:"KR"` 을 emit 했는데
(2026-06-30 스타게이트 르포 — 이재명 정부/국민성장펀드/삼성전자/SK하이닉스 전부 KR)
**태극기 대신 이니셜 모노그램**이 찍힌다. ② 기관·기업(OpenAI/백악관/미 상무부 등)을
대표하는 **로고를 넣을 방법 자체가 없고**, ③ 인물 노드는 항상 **범용 실루엣**뿐 실제
인물 사진을 쓸 수 없다. 2026-07-02 사용자 catch.

**원인**: ① 인라인 국기 sprite 가 6개국(US/TW/CN/JP/UA/RU) 화이트리스트뿐이고,
`SM_FLAGS` 에 없는 코드는 **경고 없이 이니셜로 강등** — 한국 사건 중심 봇인데 KR 부터
없었다. ② 노드 데이터 계약에 로고·사진 필드가 없고 렌더러도 그릴 줄 몰랐다 (v8.0.0
주석의 "osint_generator 자산으로 교체 가능"은 슬롯만 뚫어두고 어휘를 안 채운 상태).

**Fix (v8.2.18)**: [charts.js:`drawStakeholderMap`](../src/templates/static/charts.js)
자산 시스템 신설 — **base(동기) + 원격 오버레이(비동기, 성공 시에만)** 2층 구조.
① `flag` 는 **ISO alpha-2 전 국가**: 인라인 sprite(KR 태극기 추가, 7종)가 있으면 그대로,
없으면 flagcdn CDN(`w80/<cc>.png`)을 `Image()` 프리로드해 성공 시 둥근 국기로 오버레이.
② 신규 `logo`(기관·기업 *공식 도메인*, 예 `"samsung.com"`) → favicon 서비스로 원형
로고 코인(흰 배킹+링). ③ 신규 `photo`(인물 사진 URL) → **흑백**(`sm-gray` feColorMatrix
saturate 0) 원형 사진. 우선순위 photo→logo→flag CDN, **모든 원격 자산은 로드 실패 시
기존 base(국기/실루엣/이니셜)가 그대로 남아 빈 슬롯이 생기지 않는다** (오프라인·404·
composer 오타 전부 graceful). 사진·로고가 메인 슬롯을 차지하면 `flag` 는 국적 배지로
자동 강등. composer SYSTEM_PROMPT + `_REPORTAGE_BLOCK` 에 "공식 도메인만·실존 확인
URL 만, 추측 금지(틀려도 fallback)" 지시 추가, 가드는 관용(`logo`/`photo` 필드 추가만 —
잘못된 값으로 차트 전체 drop 하지 않음).

---

## CHART-AP-43: stakeholder_map 엣지가 카드 뒤를 관통 + 라벨이 타 엣지 선·교차점 위에 안착 (v8.2.18 신설, 사용자 catch)

**증상**: ① 왼쪽↔오른쪽 칼럼을 가로지르는 엣지의 **수평 구간이 가운데 칼럼 카드
밴드를 그대로 통과** — 엣지는 카드 아래 레이어라 카드 뒤로 사라졌다 나타나 어느 선이
어디로 가는지 끊긴다. ② 같은 칼럼에서 행을 건너뛰는 엣지(예: 오라클→OpenAI 가 사이의
소프트뱅크를 관통)는 **사이 카드를 수직으로 뚫는다**. ③ 라벨 플레이트가 카드·타 라벨은
피하지만(CHART-AP-40) **다른 엣지의 선 위·선 교차점 위**에는 그대로 앉아 시인성을
깬다. 2026-07-02 사용자 catch (CHART-AP-40/41 픽스 후 잔존 결함).

**원인**: v8.2.17 레인 라우터는 *세로 구간* 의 포개짐만 풀었고 (a) 교차 엣지의 수평
구간은 여전히 부착점 y 그대로 가운데 칼럼을 관통, (b) 같은 칼럼 skip 엣지는 T/B 부착
직선이라 장애물 개념이 없었으며, (c) 라벨 장애물 목록에 엣지 세그먼트가 없었다.

**Fix (v8.2.18)**: [charts.js:`drawStakeholderMap`](../src/templates/static/charts.js)
라우팅을 **장애물 인지형 직교 라우터**로 재설계 — 4단 계획 패스.
① 세로 채널 4개(바깥-좌 / gap A / gap B / 바깥-우)에 엣지별 레인 x 균등 분배
(CHART-AP-41 상속). ② **교차(0↔2) 엣지는 가운데 칼럼 행 *사이* 빈 수평 밴드
('코리더')로 우회** — gapA 레인으로 내려가 코리더를 타고 gapB 레인으로 진입, 수평
구간이 카드를 절대 가로지르지 않는다. 코리더 y 는 밴드 내 14px 간격 분산 + 타 엣지
수평 스텁 y ±8px 회피 (평행 겹침 0 — 남는 교차는 직각 crossing 뿐). ③ **같은 칼럼
skip 엣지는 바깥 세로 레인으로 우회** (col0=바깥-왼쪽, col1/col2=오른쪽) — 사이 카드
관통 금지. ④ 라벨 장애물에 카드·기존 라벨 + **다른 엣지의 전 세그먼트**(±4px)를 포함,
앵커는 자기 선의 가장 긴 구간(교차 엣지는 코리더) 중점에서 시작해 *자기 선 방향
슬라이드 우선*(선 위 유지) → 수직 → 수평·대각 순으로 빈 곳 탐색. 연결선은 선에서
수직으로 8px 이상 벗어났을 때만. `smRoute`(단일 중점 꺾임) 폐기, `smRouteLane` 은
waypoint 폴리라인 + 모서리 라운딩으로 일반화. 데이터 계약·가드·registry 불변.
발행본은 재배포 후 `patch_report.py <id> --rerender-only` 로 URL 동일 적용.

---

## CHART-AP-44: composer 프롬프트 스키마 ↔ validator 가드 스키마 계약 불일치 — heatmap·stacked 100% silent drop (v8.5.11 신설)

**증상**: composer 가 SYSTEM_PROMPT 의 [type 별 data 스키마] 대로 heatmap
(`[{title, severity}]`) / stacked (`{scenarios:[...]}`) 를 emit 하면
`ComposedSection._drop_invalid_charts` (디폴트 ON) 가 **전량 조용히 드롭**.
발행본 실측: 두 type 모두 2026-05 중순 (가드 배선) 이후 발행 0건 — heatmap 12건·
stacked 3건의 기존 발행본도 전부 그 이전. 드롭된 type 은 usage_log 에 "0회 emit"
으로 기록돼 **기아(starvation)로 위장**되고, v8.3.0 자기교정 힌트가 깨진 type 을
더 자주 emit 시켜 전부 다시 버리는 악순환까지 형성. `tests/regression/
test_chart_diversity.py` 의 "8종 0회 emit" 관찰 중 heatmap/stacked 가 바로 이 케이스
(composer 편향으로 오진).

**원인**: CHART-AP-38 (stakeholder_map dispatch 분기 누락) 과 동일 클래스의 변종 —
이번엔 분기는 있으나 **가드가 요구하는 데이터 모양 자체가 프롬프트·렌더러·템플릿과
다른 계약**이었다. heatmap 가드는 `[{x,y,value}]` 를, stacked 가드는
`{categories, series}` 를 요구했지만 프롬프트·`drawHeatmap`/`drawStacked`·두 템플릿
has_data 게이트는 각각 `[{title,severity}]` / `{scenarios}` 계약. 가드는 자기 모양
으로만 테스트되고 *프롬프트가 문서화한 모양으로는 한 번도 검증된 적이 없어* 3개 층의
drift 가 누구에게도 안 보였다.

**Fix (v8.5.11)**: [schemas.py](../src/visual/schemas.py) —
① `HeatmapGuard` 양형 수용: 격자형 `[{x,y,value}]` (결정 트리 §6 정본) + 강도
트랙형 `[{title, severity:low|medium|high}]` (v7.1.0 렌더러 계약, 발행본 12건의
patch_report 재발행 하위호환). ② `StackedBarGuard` 를 렌더 계약 (`{scenarios:
[{name, segments:[{label,value≥0}]}]}`) 으로 재작성 — 구 `{categories,series}` 는
템플릿 has_data 가 거르는 렌더 불가 모양이라 reject 로 전환.
③ [charts.js:`drawHeatmap`](../src/templates/static/charts.js) 에 격자형 렌더 분기
신설 (`drawHeatmapGrid` — 잉크 농도 사다리 셀 매트릭스, mono guide §10) — 격자형이
가드를 통과하고도 severity 렌더러에서 깨지는 역방향 사고 차단. ④ 프롬프트 heatmap
스키마 라인에 격자형 명기. ⑤ **재발 차단 SSOT**:
[tests/regression/test_prompt_guard_parity.py](../tests/regression/test_prompt_guard_parity.py)
— `_TYPE_TO_GUARD` 전 type 에 대해 *프롬프트가 문서화한 모양 그대로* 가
`validate_chart_data` 를 통과하는지 + 새 type 등록 시 fixture 누락을 강제 검출.
CHART-AP-38/44 클래스(프롬프트↔가드 drift)를 테스트 층에서 통째로 차단.

**교훈**: 가드·렌더러·프롬프트·템플릿 4층이 각자 데이터 모양의 사본을 가진다 —
어느 층을 고치든 **프롬프트 문서 모양의 라운드트립 테스트** 없이는 정합을 보장할 수
없다. 신규 type 추가 절차에 parity fixture 등록이 필수 단계로 추가됨.

## 본 문서 갱신 규칙 (DOCS_GOVERNANCE 정합)

- **append-only**: 발견된 회귀는 새 항목으로 추가. 기존 항목 수정 금지. 정정은 새 항목으로.
- **회귀 ID 명시**: CHART-AP-N 으로 일관 부여. 코드 / 커밋 메시지에서 reference (예: "fix CHART-AP-5: bar label cutoff").
- **`last_synced_with` 갱신**: 항목 추가 시 헤더의 version 갱신.
