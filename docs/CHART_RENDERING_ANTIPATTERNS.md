---
tier: 2
last_synced_with: v5.2.0
ssot_for:
  - "차트 렌더링 코드/데이터 anti-patterns (charts.js + composer prompt 회귀 방지)"
depends_on:
  - "docs/MONO_THEME_GUIDE.md (디자인 anti-patterns §6)"
  - "src/templates/static/charts.js"
  - "src/templates/static/maps.js"
  - "src/agents/narrative_composer.py:SYSTEM_PROMPT (차트 섹션)"
last_review: 2026-05-05
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
