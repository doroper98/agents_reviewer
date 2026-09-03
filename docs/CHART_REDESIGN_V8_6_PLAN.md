---
tier: 2
status: in progress (Phase 0 v8.6.0 · Phase 1 v8.6.1 · Phase 2a v8.6.2 · Phase 2b v8.6.3 · Phase 2c v8.6.4 · 사다리 색 전환 v8.6.5 완료 · Phase 3 부터 대기)
target_version: v8.6.0 ~ v8.7.0
based_on_baseline: v8.5.15
last_synced_with: v8.6.5
ssot_for:
  - "차트 표현 방식 전면 흡수 마스터 플랜 — 참고 자료 '차트 실전 키트'(lieflat-charts 64종) 분석 결과"
  - "신규 차트 type 1차 4종 (treemap / tree / histogram / calendar_heat) + 2차 3종 (gauge / spectrum / funnel) 데이터 계약·렌더 스펙"
  - "기존 렌더러 기본 표현 전환 (캡슐·둥근 캔들·잉크 사다리·칸 질감·읽는 법 캡션) 규칙"
  - "차트 type-fit 파이프라인 (데이터 모양 → 맞는 type 결정적 재배치, src/visual/type_fit.py) 설계"
  - "차트 렌더 DOM 스냅샷 회귀 도구 (scripts/chart_dom_snapshot.py) 설계"
depends_on:
  - "docs/reference/chart_practice_kit_aisyncclub_2026-09-02.pdf (참고 자료 원본 — 사용자 보관 지시)"
  - "src/templates/static/charts.js (RENDERERS 31종, v8.5.15 기준 4,111줄)"
  - "src/visual/schemas.py (_TYPE_TO_GUARD / validate_chart_data / _DICT_DATA_REQUIREMENTS)"
  - "docs/MONO_THEME_GUIDE.md §4 / §6 / §10 (잉크 어휘 SSOT — 본 플랜이 §10.1 을 추가)"
  - "docs/CHART_RENDERING_ANTIPATTERNS.md (CHART-AP-1~45 계승, 본 플랜이 46·47 을 신설)"
  - "REFACTOR_V7_PLAN.md §1 (Track A — 에디토리얼 레이어·자산 버저닝 AP-V7-1·v7.1.0 소급 전례)"
  - "docs/VISUAL_ENHANCEMENT_V9_PLAN.md (직교 — event_timeline·전황 지도는 그쪽 트랙)"
  - "docs/CONTRACTS/report_bundle_v1.md §5 / §9 (osint 소비자 계약 — additive)"
proposed_by: 사용자 요청 (2026-09-03 — "차트 실전 키트 · AI싱크클럽" PDF 64장의 유형·표현 방식을 전부 흡수, 발현 빈도·유형 폭 확대, 데이터에 안 맞는 차트를 새 유형으로 제대로 보이게 하는 파이프라인)
last_review: 2026-09-03
---

# CHART REDESIGN V8.6 — 표현 방식 전면 흡수 · 신규 유형 · type-fit 파이프라인

> **목표 (사용자 지시 원문 요지, 2026-09-03).** ① 참고 자료의 *차트 유형* 과 *개별 차트의
> 표현 방식(디자인)* 을 다 흡수해 우리 것에 통합한다 — 캔들의 둥근 몸통 같은 것까지.
> ② 르포든 일반 보고서든 차트의 **발현 빈도와 유형 폭** 을 훨씬 넓히되 시각적으로
> 안정적이고 완성도 높게. ③ 기존 유형에 *억지로 끼워 넣던 데이터* 가 있었다면, 이번에
> 추가되는 유형으로 **제대로 보이게 하는 파이프라인** 을 세운다. ④ 참고 PDF 는 저장소에
> 보관한다 (`docs/reference/`).
>
> **핵심 판단.** 참고 자료의 매력은 종류의 수가 아니라 세 가지 문법 — *칸 하나가 정해진
> 수량* (rung/tick/dot), *잉크 농도 사다리*, *캡슐·속빈/채움 형태 인코딩* — 이다. 우리
> 27종 렌더러는 기반 체력(zone 엔진·annotation·충돌 회피·content-fit)이 충분하므로
> ⑴ 공유 어휘 계층을 먼저 깔고 ⑵ 기존 렌더러의 **기본 표현을 전환** 하고 (소급 —
> v7.1.0 전례, 사용자 지시) ⑶ 니치가 분명한 유형을 신설하고 ⑷ 데이터 모양을 보고
> 맞는 유형으로 *결정적으로* 재배치하는 안전망을 둔다. 데이터 계약(payload) 은 불변.
>
> **실행 구조.** 본 문서는 Fable 의 설계도, 구현은 Opus 5 가 §10 체크리스트 순서대로.
> Phase = 1 커밋 = 버전 1개. §8 사용자 결정은 전부 확정 (2026-09-03) — 즉시 Phase 0 착수 가능.

---

## §0. 요약

| 항목 | 내용 |
|------|------|
| 참고 자료 | `lieflat-charts` (Claude Code 스킬) 카탈로그 64장 — G(판단용 22) / L(정독용 20) / F(기본형 17) / M(지도 2) / B(대형 3). 코드 라이선스 **PolyForm Noncommercial 1.0.0**. 원본 PDF: [docs/reference/chart_practice_kit_aisyncclub_2026-09-02.pdf](reference/chart_practice_kit_aisyncclub_2026-09-02.pdf) |
| 라이선스 대응 | 참고 저장소의 코드·템플릿·토큰 파일 **복제 금지**. 시각 문법만 charts.js 로 *재구현*. PDF 는 사용자 지시로 내부 참고용 보관 |
| Phase 0 v8.6.0 | 공유 어휘 헬퍼 8개 + DOM 스냅샷 도구 + §10.1 문서 |
| Phase 1 v8.6.1 | **기본 표현 전환 (소급)** — bar 캡슐/칸 질감·candle 둥근 몸통·donut 눈금 링·diverging/pyramid/gantt 캡슐·lollipop 점 사다리·scatter 추선·range_bar 구슬·area 실선·line 일별 점·heatmap 둥근 칸 + 옵션 필드 (prior / before_after / orientation) |
| Phase 2a v8.6.2 | 신규 `treemap` (승격) · `tree` |
| Phase 2b v8.6.3 | 신규 `histogram` · `calendar_heat` + **calendar_heat 시장 시계열 자동 주입** (`_ensure_calendar_heat`, 사용자 결정) |
| Phase 2c v8.6.4 | **type-fit 파이프라인** `src/visual/type_fit.py` — 결정적 재배치 규칙 R1~R7 + 계측 + `patch_report --refit` |
| Phase 3·4 v8.6.5 | 갤러리 33종 시각 검수 · CHART-AP-46/47 · osint 통지(n) · 문서 정합 |
| Phase 5 v8.7.0 | 2차 흡수 — `gauge` · `spectrum` · `funnel` + 옵션 (bump strip / stacked rung / pictogram) |
| 기각 (근거 §1.3) | beeswarm·jitter·violin·ridgeline·box (건별 원자료 필요 → 날조 위험 WRITE-AP-5), circular/force (CHART-AP-36/37), bar race·dynamic stream·scatter morph (애니 전용), petal rose·big slice (판독 오류) |
| osint 영향 | 신규 type 은 osint 렌더 게이트(`render_io.SUPPORTED_CHART_TYPES` 22종)에서 *무경고 소실* → 통지(n) + producer `prerendered_svg` B안 폴백 |

---

## §1. 참고 자료 분석

### §1.1 시각 문법 5가지 (전 64장 공통) — 전부 흡수 대상

1. **셀 수 있는 단위 질감.** 막대를 면이 아니라 *칸* 으로. rung(가로 실선 층, F1) /
   tick(세로 눈금, F5) / dot(점, L2·G4·L14). 칸 하나 = 정해진 수량, 다섯 번째마다 굵게.
   반드시 "ONE RUNG = $1K" 식 **읽는 법 한 줄** 이 차트 안에 있다. 참고 카탈로그 자체
   규칙: "정직한 단위만, 개인을 날조하지 말 것" → 우리 WRITE-AP-5 와 같은 원리.
2. **잉크 농도 사다리 7단.** hue 없이 `#1C1C1A → #D8D7D1` 7단 (또는 5단). 1위가 가장
   진하다. 우리 §10 4단 사다리와 원리 동일, 단수만 확장.
3. **캡슐 + 직접 값 라벨.** 막대 끝 완전 원형 (radius 99), 값은 막대 끝·위에 굵은 숫자.
   캔들도 몸통이 둥근 캡슐 (F17). 축·그리드 최소.
4. **대문자 자간 벌린 캡션.** 하단 9.5px, letter-spacing .08em, muted. 우리는 *읽는 법*
   캡션으로 흡수 (장식 푸터 "RUNG BARS · MONO-BASIC" 은 템플릿 출처 줄이 이미 담당).
5. **형태 인코딩.** 속빈 원 = 이전/주말/미확정, 채움 = 이후/평일/확정 (F2·F12·L11).
   점선 = 뺄셈, 실선 = 덧셈 (F9). 색이 아니라 *모양* 이 의미를 진다.

### §1.2 참고 토큰 → 우리 토큰

| 참고 (mono-tokens) | 우리 | 비고 |
|---|---|---|
| INK #1C1C1A / PAPER #F0EFEB | `t.text` / stage 배경(`--card-deep`) | 다크 테마는 반전 — 불투명도 사다리라 자동 대응. charts.js 는 `--card-deep` 를 읽지 않으므로 반전 글자색은 `t.card` 사용 |
| MUTED / FAINT / GRID | `t.muted` / `t.text`×.12 / `t.border`×.06 | §10 보조선 ≤ .06 유지 |
| L 7단 | `inkLadder(7)` = `t.text` × [1, .78, .60, .44, .30, .20, .12] | §10.1 신설. 4단은 구성(donut/stacked) 존속 |
| Title 16.5/700 · Subtitle 11.5 | 템플릿 `.chart-card-title/-subtitle` 그대로 | charts.js 는 헤더를 그리지 않음 (Jinja 형제 노드) |
| Source 9.5/.08em caps | `keyFooter()` SVG 내부 하단 | 템플릿 무변경 → 두 archetype 공통 |
| Bar radius 99 | `capsuleRect()` rx=h/2 | |
| Enter 900ms quarticOut | **미채택** — CHART-AP-18 (≤700ms·1회·reduced-motion) | 기존 `_applyEntryAnimation` 이 새 rect/circle/path 자동 처리 |
| Inter | Noto Sans KR / Noto Serif KR | 참고 §03 경고(Inter 한글 없음) — 우리 체인이 이미 우월 |

### §1.3 64종 대응·판정표

✅ 있음 · 🎨 기존 type 의 *기본 표현* 으로 흡수 (Phase 1) · 🔧 옵션 필드 · ➕ 신규 (1차) ·
⏩ 신규·옵션 (2차, Phase 5) · ✖ 기각

| 참고 | 이름 | 우리 | 판정 |
|---|---|---|---|
| G3 | Chunky Bars | bar | 🎨 캡슐 + 사다리 = **bar 새 기본** |
| F1 / F5 / L2 / L15 | Rung / Tick / Dot Cascade / Ballot Tally | bar | 🎨 정수·셀 수 있는 값이면 칸 질감이 기본 (규칙 §4.1) |
| G10 | Diverging Bar | diverging_bar | 🎨 캡슐 끝 |
| F6 | Paired Rungs | bar | 🔧 `prior` |
| F12 | Dumbbell Queue | range_bar | 🎨 구슬 연결선·속빈/채움 기본 + 🔧 `mode:"before_after"` |
| G21 | Rank Strip | bump | ⏩ `bump.layout:"strip"` |
| G16 / G17 / G18 / G9 | Bar Race / Dynamic Stream / Draw-in / Scatter Morph | — | ✖ 애니 전용 (G18 은 indicator 와 중복) |
| G12 | Stagger Wave | — | ✖ 30개 초과 항목 니치 없음 |
| G4 / L14 | Dot Waffle / Hundred Field | dot_matrix | ✅ (사다리 정합만) |
| F4 | Tick Donut | donut | 🎨 **100 눈금 링 = donut 새 기본** |
| F7 | Stacked Rungs | stacked | ⏩ `texture:"rung"` |
| G2 / G13 | Petal Rose / Big Slice | — | ✖ 장식·이중 인코딩 |
| G5 | Pictorial Bar | bar | ⏩ `texture:"pictogram"` |
| F13 | Nested Treemap | (registry experimental) | ➕ `treemap` 승격 |
| F2 | Hairline Line | line | 🎨 ≤40 포인트면 일별 점(주말 속빈) 기본 |
| F3 / L3 | Hairline Area / Barcode Lollipop | area | 🎨 ≤120 포인트면 세로 실선 기본 |
| G1 | Range Capsules | candle | ✅ (candle 상위 호환) |
| F17 | Candlestick | candle | 🎨 **둥근 몸통 캡슐 + 1px 심지 + 마지막 종가 라벨** |
| L17 | Calendar Heat | — | ➕ `calendar_heat` |
| G8 / F16 | Rainfall Dual / Stream Ribbon | combo / stacked_area | ✖ combo 가 담당 · 유선형은 CHART-AP-30 충돌 |
| L11 / L1 / L9 / L10 | Lineage / Launch Fan / Almanac / Radial Patchwork | — | ✖ V9 event_timeline 트랙 중복 · 장식 |
| L13 | Hourglass Stream | — | ⏩ `funnel` |
| F9 | Rung Waterfall | waterfall | 🔧 `texture:"rung"` 옵션만 (V7 "waterfall 변경 금지" — CHART-AP-20~27 표면) |
| G22 | Aggregate Sankey | sankey | ✅ |
| L5 / L12 | Radial Convergence / Type Colonnade | — | ✖ 개별→묶음 원자료 없음 |
| F14 | Rung Histogram | — | ➕ `histogram` |
| L18 / G15 / G19 / L19 / F15 | Beeswarm / Jitter / Violin / Ridgeline / Tick Box | — | ✖ 건별·분포 원자료 필요 (WRITE-AP-5). 유일 예외 — 출처가 최저/중앙/최고를 줄 때는 `range_bar` 가 이미 담당 |
| F11 | Tick Gauge | bullet | ⏩ `gauge` (지지율·달성률·가동률) |
| F8 | Plumb Scatter | scatter | 🎨 ≤20 점이면 추선(plumb) 기본 |
| L20 | Parallel Coordinates | — | ⏩ 검토 (한글 축 라벨 배치 검증 후) |
| L7 | Brand Spectrum | — | ⏩ `spectrum` (정책 성향·국가 입장) |
| G20 | Matrix Heat (Glance) | heatmap | 🎨 ≤60칸이면 둥근 칸 + 숫자 직독 기본 |
| L16 / L4 / L8 / G14 / F10 | 격자 변형 5종 | heatmap | ✖ heatmap 이 담당 |
| G7 | Tree LR | — | ➕ `tree` (위계 — stakeholder_map 은 관계) |
| G6 / G11 / L6 / B1 / B2 / B3 | Circular / Force / Cluster / Big | — | ✖ CHART-AP-36/37 |
| M1 / M2 | Choropleth | choropleth / embedded_map | ✅ |
| (F-계열 공통) | 캡슐 막대 | gantt / pyramid / bullet | 🎨 캡슐 끝 |

**결론.** 1차 4종 + 2차 3종 신설, 기존 12종 기본 표현 전환, 옵션 4종. 참고 64장 중
보고서에 유의미한 표현의 ~90% 를 흡수한다. 기각은 *데이터 정직성* 또는 *기존 안티패턴*
둘 중 하나에만 근거한다.

---

## §2. 불변 조건 (전 Phase 공통)

1. **소급 정책 (v7.1.0 전례 + 사용자 지시 2026-09-03).** 기본 표현 전환은 charts.js 를
   직접 바꾸므로 발행본 전부에 소급된다 (REFACTOR_V7_PLAN §1.6). 이번엔 이를 *의도* 한다.
   대신 ⑴ 데이터 계약(payload 필드·가드 밴드) 은 불변 ⑵ 스냅샷 도구(§3.2) 로 "어떤 type
   의 DOM 이 바뀌었는가" 를 매 Phase 커밋 메시지에 *증빙* ⑶ 갤러리 5테마 전·후 스크린샷을
   사용자가 리뷰한 뒤 머지 ⑷ 발행본 재배포는 다음 발행 때 디렉토리 통째 업로드로 자연
   반영 (별도 backfill 불필요, `patch_report --rerender-only` 로 개별 강제 가능).
2. **mono guide §4/§6/§10 계승.** 45° 한 방향 해치는 *명목 범주* 전용. 위계는 잉크 농도.
   accent 는 차트당 1 요소. 큰 숫자에 accent 금지. 보조선 ≤ .06. §10.1 을 *추가*.
3. **CHART-AP-1~45 계승.** 특히 15/16 (gantt·donut 가드), 17 (5-Layer — 신규 type 은
   결정 트리·fixture 까지 한 번에), 18 (모션), 20~27 (sankey/waterfall 손대지 않음), 30
   (curveLinear), 31 (밀도), 33 (라벨 충돌), 36/37, 38 (dict 형 elif), 44 (parity), 45
   (has_data SSOT). WRITE-AP-5 는 `unit` 에도 — 렌더러가 *자동 산출* 하므로 LLM 이 지어낼
   수 없다.
4. **데이터 계약 동결.** `{type, title, data, note?}` dict 계약과 `src/models.py` 무변경.
   ReportBundle `schema_version` 1 유지 (계약 §7 additive). osint 에는 통지(n).
5. **라이선스.** 참고 저장소 코드·SVG·템플릿·토큰 파일 복사 금지. 본 문서 수치는 관찰을
   우리 어휘로 다시 쓴 것. PDF 는 `docs/reference/` 에 원본 보관 (사용자 지시; 저장소가
   public 이면 제3자 문서 재배포에 해당하므로 README 에 출처·용도 명기).
6. **2-call 파이프라인·LLM 호출 수 불변.** type-fit 도 0-LLM.
7. **한글 라벨 규칙 (참고 §03 흡수).** 세로 칸 막대(`rung`) 는 모든 라벨 ≤6 글자·항목 ≤8
   일 때만. 아니면 렌더러가 *결정적으로* 가로(`tick`) 로 강등. 최종 방어는 렌더러.
8. **Execution Rule #12.** 커밋 prefix = `src/orchestrator.py:VERSION`. `git config
   core.hooksPath .githooks` 선행. 매 버전 README `Status` + CHANGELOG.
9. **위계 사다리의 색 = 테마 액센트 (사용자 결정 2026-09-03, v8.6.5 소급).** §1.1-2 의
   "잉크 농도 사다리" 는 *농도* 문법만 흡수하고 *색* 은 우리 것을 쓴다. 참고 자료의 검정
   잉크를 그대로 따라간 v8.6.1~v8.6.4 의 렌더는 13종 테마 위에서 회색으로만 보여 보고서와
   겉돌았다. 데이터 마크는 `--accent` 를 깔고 사다리를 불투명도로만 쓰며, 축·눈금·라벨·
   읽는 법 캡션은 `--text`/`--muted` 그대로다. up/down 의미색 · sankey 다색 팔레트 ·
   pyramid 좌측 중립 집단은 불변. 최저 단은 `.16` (라이트 테마 가시성). 어휘 SSOT 는
   [MONO_THEME_GUIDE §10.1](MONO_THEME_GUIDE.md) 의 v8.6.5 블록, 상수는 charts.js
   `LADDER_MIN` 한 곳.

---

## §3. Phase 0 — 공유 어휘 계층 + 회귀 도구 (v8.6.0)

> 기존 렌더러는 한 줄도 건드리지 않는다 (byte-equal 자명). 헬퍼는 charts.js IIFE 안
> `placeEndLabel` (`charts.js:274~306`) 바로 아래 `// ===== v8.6.0 unit vocabulary
> helpers =====` 블록.

### §3.1 헬퍼 명세 (8개)

```js
// 1. 숫자 포맷 단일 SSOT (기존 idiom 그대로 — 기존 렌더러 교체는 Phase 1 에서 함께)
function fmtNum(v) { const av = Math.abs(+v);
  if (av >= 100) return d3.format(',.0f')(+v);
  if (av >= 10)  return d3.format(',.1f')(+v);
  return d3.format(',.2f')(+v); }

// 2. 한국어 단위 — 1e12 조 / 1e8 억 / 1e4 만 / 1e3 천 (예: 2.5e8 → "2.5억"), unit_label 뒤에 붙임
function fmtUnitKo(unit, unitLabel) { ... }

// 3. 잉크 농도 사다리 — n≤4: 기존 4단 / 5~7: 7단 / 8+: 1→.12 선형
const LADDER4 = [1, .42, .24, .13], LADDER7 = [1, .78, .60, .44, .30, .20, .12];
function inkLadder(n) { if (n <= 4) return LADDER4.slice(0, n);
  if (n <= 7) return LADDER7.slice(0, n);
  return d3.range(n).map(i => 1 - (i / (n - 1)) * .88); }

// 4. 칸 단위 자동 — 칸수 ≤ maxMarks 가 되는 {1,2,2.5,5}×10^k 중 최소
function niceUnit(maxValue, maxMarks) { ... }

// 5. 셀 수 있는 값 판정 — 모든 값이 정수(|v-round(v)|<1e-9) 이고 max ≤ 500 이면 true.
//    비율(%)·지수·소수 값은 false → 캡슐. (bar 기본 질감 결정의 SSOT)
function isCountable(values, unitLabel) { ... }   // unitLabel 이 '%' 포함이면 무조건 false

// 6. 칸 질감 — count=round(value/unit) 개 마크. kind: 'tick'|'rung'|'dot'. every5 강조.
//    반환 {count, end}
function unitMarks(g, { kind, x, y, value, unit, gap, len, color, opacity }) { ... }

// 7. 캡슐 — rx=h/2, 폭 < h 이면 최소폭 h 클램프 (참고 G3)
function capsuleRect(g, x, y, w, h, fill, opacity) { ... }

// 8. 읽는 법 캡션 — SVG 하단 중앙, Noto Sans KR 9.5, letter-spacing .08em, t.muted,
//    라틴은 toUpperCase. 호출 렌더러는 H 산정에 FOOTER_H(18) 를 더한다.
function keyFooter(svg, W, H, text, t) { ... }
```
- 부가: `contentFit(svg, pad)` (sankey/stakeholder_map 의 ad-hoc getBBox 일반화, try/catch,
  기존 3곳은 교체하지 않음) — 신규 type(tree) 용.
- 구문 검사: `node -e "new Function(require('fs').readFileSync('src/templates/static/charts.js','utf8'))"`.

### §3.2 회귀 도구 — `scripts/chart_dom_snapshot.py`

- 갤러리 fixture(`samples/chart_gallery_v7.html` `PAYLOADS`) 를 헤드리스 chromium 으로
  렌더 → 각 `.chart-card-stage svg` `outerHTML` 정규화(태그·속성 정렬, 공백 제거) →
  sha256 을 `{type: {theme: hash}}` 로 기록. **픽셀이 아니라 DOM** — 폰트·OS 무관.
- `--out <json>` 기록 / `--check <json>` 비교 (차이 type 목록 출력, exit 1) /
  `--diff-report` (변경 type 만 요약 — Phase 1 커밋 메시지 증빙용).
- **스냅샷 키 (v8.6.1 구현 보정)**: 키는 갤러리 카드의 `data-snapshot-key`, 없으면
  `data-chart-type`. Phase 1 처럼 *같은 type 의 새 기본 표현이 여러 갈래* 일 때
  (bar 칸/캡슐/세로, heatmap 격자/강도, range_bar 두 모드, line 일별/실선) type 하나당
  fixture 하나로는 전환을 고정할 수 없어 도입했다 — `bar:capsule` 처럼 `:` 앞이 실제
  chart type 이고, `charts.js` 의 렌더 계약(`data-chart-type`)은 건드리지 않는다.
- 브라우저: Playwright-python → `$CHROME_BIN` → `/opt/pw-browsers/chromium-*/chrome-linux/chrome`.
  없으면 "skip" + exit 0. getBBox 의존 3종 (sankey·dot_matrix·stakeholder_map) 은 요소
  수·태그 분포만 비교 (loose).
- **갤러리 정비를 먼저**: `network` fixture 제거 + 누락 4종 (combo_candle / iv_skew /
  indicator / stakeholder_map) 추가 + `reportage_steel` 테마 버튼. 그 다음 baseline 기록.
- loose 비교 대상은 `contentFit`/ad-hoc getBBox 로 viewBox 를 사후 보정하는 렌더러다 —
  v8.6.2 기준 sankey · dot_matrix · stakeholder_map · **tree** (신규 type 이 `contentFit`
  을 쓰면 `LOOSE_TYPES` 에 함께 등록할 것).
- pytest 래퍼 `tests/regression/test_chart_dom_snapshot.py` (chromium 없으면 skip).
  VM-AP-2: `python scripts/...` 로만 실행, +x 불필요.

### §3.3 문서 (같은 커밋)

- `docs/MONO_THEME_GUIDE.md` §10.1 **셀 수 있는 단위 어휘 (v8.6.0)**: ① 정수·건수·인원·
  금액은 칸 질감, 비율·지수는 캡슐 ② 칸의 뜻은 렌더러 자동 산출·표기 ③ 7단 사다리는
  *순위* 전용, 구성은 4단 ④ 속빈/채움 = 이전/이후·주말/평일 ⑤ 읽는 법 캡션 필수 ⑥ 캡슐
  = 막대류 공통 기본 ⑦ 캔들 몸통 캡슐. §10 의 죽은 network 문장에 "(v7.9.17 폐기,
  CHART-AP-36)" 주석.
- `docs/REPO_MAP.md` 스크립트·baseline 등재. `docs/reference/README.md` (PDF 출처·라이선스·
  용도). VERSION v8.6.0 / README / CHANGELOG.

---

## §4. Phase 1 — 기본 표현 전환 (소급) + 옵션 필드 (v8.6.1)

> **구현 보정 (v8.6.1 랜딩 결과 — 아래 §4.x 의 "가드" 문장을 이렇게 읽는다).**
> 표현 옵션(`texture` / `unit` / `orientation` / `marks` / `fill` / `mode` / `cells`)은
> `data` 가 아니라 **payload 최상위** 필드다. `validate_chart_data(chart_type, data)` 는
> `data` 만 받으므로 이 값들에 닿지 못한다 — 그래서 옵션 검사는 기존 data 가드에 필드를
> 얹는 대신 **별도 진입점 `schemas.validate_chart_options(chart_type, payload)`**
> (+ `_TYPE_TO_OPTION_GUARD` Literal 가드 7종) 로 두고 `ComposedSection._drop_invalid_charts`
> 가 data 가드 통과 직후 호출한다. 정책은 동일(계약 밖 값 → drop). 행 단위 필드
> (`prior`, before_after 행)만 기존 data 가드에 들어간다. 옵션이 하나도 없는 payload 는
> 항상 통과 = v8.6.0 이전 발행본 additive 안전.
>
> 원칙: **표현은 바꾸고 데이터 계약은 안 바꾼다.** 각 렌더러 안에서 *조건이 결정적*
> (값 정수 여부·포인트 수·셀 수) 이면 새 표현이 기본. 옵션 필드는 기본 판정을 *덮어쓰기*
> 하는 용도. 매 렌더러 수정 후 `--diff-report` 로 바뀐 type 을 확인해 커밋 메시지에
> 나열한다. 기존 인라인 포맷 idiom 은 `fmtNum` 으로 교체 (출력 동일).

### §4.1 `bar` (`drawBar` `:308`)

- **기본 질감 결정 (렌더러, 0-LLM):** `payload.texture` 있으면 그것. 없으면
  `isCountable(values, unit_label)` → true 면 `tick` (가로), false 면 `capsule`.
  `payload.orientation==="vertical"` + 게이트(라벨 ≤6자·≤8항목) 통과 + countable → `rung`.
- `capsule`: 행 30, 막대 높이 18, `capsuleRect` rx 9, fill `t.text` × `inkLadder(n)[rank]`
  (rank = 값 내림차순, 데이터 순서 아님). 트랙 rect 제거. 값 라벨 끝 +10 Serif 700 13.
  accent 는 key(1위) 값 라벨에만.
- `tick`: `unit = payload.unit || niceUnit(max, 48)`, `unitMarks('tick', gap min(6, w/48),
  len 11, every5 15)`. key 행 opacity 1, 나머지 .62. footer `"한 칸 = {fmtUnitKo} ·
  다섯 칸마다 긴 눈금"`.
- `dot`: r 3, gap 2.6, `niceUnit(max, 40)`, every5 r 4. `rung`(세로): 열 폭 28, 실선 1px
  gap 4, `niceUnit(max, 40)`, 값 열 위, 라벨 열 아래. 게이트 실패 → tick 강등 +
  `console.info('[charts] bar rung→tick')`.
- **옵션:** `prior?:number`(행) — 행 36, 주 막대 아래 2px 에 같은 질감 opacity .22 + Sans
  10 muted 값. footer `"{value_label||'이번'} 진하게 · {prior_label||'이전'} 흐리게"`.
- 가드 `BarChartGuard` (`:1334`): `texture` Literal(tick/dot/capsule/rung) · `unit>0` ·
  `prior` finite · `orientation` Literal — 전부 optional. 위반 → drop (기존 정책).
- annotations 계약 유지 (`renderAnnotations(..., xScale, null)`; rung 세로면 `null, yScale`).

### §4.2 `candle` (`drawCandle` `:1325`) — 둥근 몸통

- 몸통 `rect` (`:1382`) → `rx = min(bw/2, 3)` 캡슐 (몸통 높이 < bw 이면 rx = h/2). 심지
  stroke 1px (현행 유지 폭이 더 굵으면 1 로). 색 규칙은 우리 `--up/--down` 유지 (참고의
  속빈=상승은 채택하지 않음 — 다크 테마 12종에서 속빈 몸통 가독 저하). 마지막 종가
  Serif 700 11 라벨 (`placeEndLabel`), 최고·최저 봉 Sans 9 muted 라벨. 이동평균 등
  추가 계산 없음 (V7 §1.2 의 MA20 은 별도).
- 시장 주입 경로(`_build_ts_chart`) 데이터 그대로 — 표현만.

### §4.3 `donut` (`drawDonut` `:369`) — 눈금 링

- 조각 ≤6 이면 **100 눈금 링**: 반지름 r 에 눈금 100개 (길이 10, 매 10번째 14, stroke 1.2),
  조각 = 눈금 연속 구간, 조각별 `inkLadder(n)` 농도, key 조각 accent. 조각 경계에 2px 틈.
  중앙 큰 숫자·우측 값 정렬 범례·arc sweep 애니 계약(`data-anim="donut-arc"`, `data-donut-*`)
  유지 — 눈금은 `<line>` 이라 애니 (D) rect/(E) circle 패스에 안 걸리므로 `<g data-anim=
  "static">` 로 감싼다. 조각 >6 이면 기존 arc 렌더 (판독성). CHART-AP-16 유지.
  footer `"눈금 하나 = 1% · 12시 방향이 0"`.

### §4.4 캡슐 끝 일괄 — `diverging_bar` / `pyramid` / `gantt` / `bullet` / `lollipop`

- `diverging_bar` (`:2761`, `:2770`): `rx 1.5` → 바깥쪽 끝만 캡슐 (`capsuleRect` 후 0 축
  쪽은 clipPath 로 직각 — 또는 두 rect 겹침). 0 기준선 dash 2 2. 값 라벨 유지.
- `pyramid` (`:2786`): 동일 원리 (바깥 끝 캡슐). `gantt` (`:518`): 막대 rx = h/2.
  `bullet` (`:2462`): 실적 막대 캡슐, 목표선 유지.
- `lollipop` (`:1784`): 줄기 0.8px opacity .35 (실선), 점 r 5 → `inkLadder(n)[rank]` 농도,
  key 점만 accent. countable 이면 줄기 대신 `dot` 질감 (참고 L2) + footer.

### §4.5 시계열 3종 — `line` / `area` / `scatter`

- `line` (`:434`): 포인트 ≤40 **and** `x` 가 ISO 날짜면 일별 점 기본 — r 3, 토/일 속빈
  (stroke 1.2, fill none). 첫·끝·최고 Serif 700 11. x 축 3 tick. footer `"점 하나 = 하루
  · 속빈 점 = 주말"` (주말 포인트 있을 때). >40 은 기존 렌더 (시장 주입 60~260 포인트는
  자동으로 기존 유지). `payload.marks="none"` 으로 끌 수 있음.
- `area` (`:1437`): 포인트 ≤120 이면 **세로 실선** 기본 — 그라데이션 제거, 각 포인트에서
  baseline 까지 0.8px `t.text` opacity .28 (간격 <2.5px 이면 실선만 stride 솎음, path 는
  전 포인트 — CHART-AP-31), 최고점 원 r 3.5 + 라벨. >120 은 기존. `payload.fill="gradient"`
  로 복귀 가능.
- `scatter` (`:1636`): 점 ≤20 이면 **추선(plumb)** 기본 — 각 점에서 x 축까지 0.6px
  opacity .25 세로선, 점 r 5 `inkLadder(n)` (y 내림차순), 상위 2 점만 라벨 (CHART-AP-33
  충돌 회피와 정합), x 축 양 끝 라벨만 (참고 F8 "CHEAP … PREMIUM" 은 `payload.x_low_label`
  / `x_high_label`, 없으면 축 tick 유지). >20 은 기존.

### §4.6 `range_bar` (`:2346`) — 구슬 연결 + before_after

- 기본: low 속빈 원(stroke 1.4) · high 채움, 연결선 → 구슬 (6개 균등 r 1.6). 범례 → footer
  `"속빈 원 = {low_label||'최저'} · 채운 원 = {high_label||'최고'}"`.
- 옵션 `mode:"before_after"` + 행 `{label, before, after}`: 양방향 허용 (`before != after`),
  감소면 구슬 `t.down`. after 라벨 Serif 700 12, before Sans 10 muted. 가드 `RangeBarGuard`
  (`:871`) `mode` Literal + 행 검증 분기.

### §4.7 `heatmap` 격자 (`drawHeatmapGrid` `:862`) — 둥근 칸

- 셀 ≤60 이면 rx 8, 간격 6, `inkLadder(5)[quantile]`, 셀 안 값 Serif 700 12 (opacity ≥.60
  이면 `t.card` 반전). >60 은 기존 (v7.1.0 농도 격자). `cells:"grid"` 로 복귀.

### §4.8 프롬프트·parity·목업

- `narrative_composer.py` `[type 별 data 스키마]` (`:273~`) bar/line/area/range_bar/heatmap/
  scatter 줄에 옵션 필드 + 원칙: "건수·인원·금액은 자동으로 칸 질감, 비율·지수는 캡슐 —
  `texture`·`unit` 은 *지정하지 말 것*(렌더러 자동). 전년·개편 전 비교면 `prior` 또는
  range_bar `mode:'before_after'`. 세로 칸(`orientation:'vertical'`) 은 이름 ≤6자·≤8항목."
- `PROMPT_SHAPES` 옵션 fixture 추가 (기존 유지), `test_chart_correctness.py` reject/pass.
- **갤러리 전·후 페이지** `samples/chart_redesign_v8_6_compare.html` — Phase 1 대상 12종
  각각 *v8.5.15 렌더(charts.js 를 `git show v8.5.15:...` 로 `samples/_legacy/charts.v8515.js`
  에 고정, gitignore 아님 — 비교 SSOT) vs 신 렌더* 를 나란히, 테마 3종 전환. 사용자
  리뷰 게이트. CHANGELOG 에 `--diff-report` 결과(변경 type 목록) 기재.

---

## §5. Phase 2 — 신규 type 1차 4종 (v8.6.2 / v8.6.3)

> 공통 절차 (CLAUDE.md Chart System 9단 + 3): ① `charts.js` RENDERERS(`:3888`) ② `schemas.py`
> 가드 + `_TYPE_TO_GUARD`(`:1190`) + dict 형이면 `validate_chart_data` elif(`:1255~`) +
> `_DICT_DATA_REQUIREMENTS`(`:1352`) ③ `usage_log.KNOWN_CHART_TYPES`(`:42`) ④ registry yaml +
> `distribution`(`:273`) ⑤ `test_capability_registry.py` (`:45` 카운트, `:83`/`:100` 집합)
> ⑥ composer 스키마 줄 + 결정 트리 분기 ⑦ `PROMPT_SHAPES` ⑧ `chart_type_scenarios.yaml`
> ⑨ 갤러리 `PAYLOADS` ⑩ `svg_prerender.B_PLAN_CHART_TYPES` (`src/handoff/svg_prerender.py:35`)
> ⑪ `report_bundle_v1.md` §9 pin 줄 ⑫ `test_chart_correctness.py`.
> 등록 후 분포: **safe 11 / guarded 21 / experimental 1 (chord) / total 33**
> (treemap experimental→guarded, `default_policy` 제거, `added_in: v8_6_2`).
> — Phase 2a(v8.6.2) 시점의 실제값은 **safe 11 / guarded 19 / experimental 1 / total 31**
> (treemap 승격 + tree 신설). 위 33 은 Phase 2b 의 histogram·calendar_heat 까지 더한 값.

### §5.1 `treemap` — 2층 구성 (v8.6.2)

- 니치: 예산·수출 품목·매출·지출 *2층 구성*. stacked 는 1차원, donut 은 ≤8·1층.
- 데이터 (dict): `{children:[{label, value?, children?:[{label, value}]}], unit_label?}`.
  깊이 ≤2, 잎 `value>0` 필수, 부모 value 생략 시 자식 합 (있으면 ±2% 이내, 아니면 drop).
  1층 2~8, 잎 총 3~40.
- 가드: `TreemapNode`(재귀, extra allow) + `TreemapGuard(children min2 max8)` + validator
  (깊이·잎 수·합). elif + `_DICT_DATA_REQUIREMENTS["treemap"]=("children",)` +
  `_MIN_LEN_REQUIREMENTS["treemap"]=("children",2)`.
- 렌더 `drawTreemap`: W 720 H 400. `d3.hierarchy.sum.sort(desc)` → `d3.treemap().paddingInner(3)
  .paddingTop(20).paddingOuter(2).tile(d3.treemapSquarify)`. 그룹 헤더 caps Sans 9.5 .08em
  muted `"{label} · {share%}"`. 잎 fill `t.text × inkLadder(nGroups)[groupRank] × (.92~.60
  잎 내 보간)`. 잎 라벨: ≥56×30 이름+값 두 줄 / ≥30×16 이름만 / 미만 없음. 글자색 반전
  규칙 (opacity ≥.55 → `t.card`). 최대 잎 1개 stroke accent. footer `"면적 = {unit_label||
  '값'} · 진할수록 큰 묶음"`.
- 결정 트리 (`:469~472` "4. 구성" 끝): "구성이 *2층* (부문→세부) 이고 잎 ≥6 → treemap."
- PROMPT_SHAPES / 시나리오 (`sample_prompt: "2026 예산안 부처별·사업별 구성"`) / 갤러리
  (반도체 수출 구성 2층).

### §5.2 `tree` — 위계 (v8.6.2)

- 니치: 지배구조·계열사·조직도·파벌 계보·정책 체계. stakeholder_map = *관계*, tree = *소속*.
- 데이터 (dict): `{root:{label, note?, children:[{label, note?, children?}]}, accent_label?}`.
  깊이 ≤3, 노드 4~40, 자식 ≤8/노드, label ≤18자, note ≤24자.
- 가드: `TreeNode` + `TreeGuard(root)` + validator. elif + `_DICT_DATA_REQUIREMENTS["tree"]=("root",)`.
- 렌더 `drawTree`: 좌→우 `d3.cluster().size([innerH, innerW])` (잎 정렬). H = max(280,
  leaves×22+40). 링크 `d3.linkHorizontal`, 1층 1.4px .9 / 2층 1px × `inkLadder(nBranches)
  [branch]`. 노드 root r5 · 중간 r3.5 · 잎 r2.5. 라벨 root Serif 700 13 (왼쪽) · 중간 Sans
  600 11 (위-왼쪽) · 잎 Sans 10.5 (+8) + note Sans 9 muted. `contentFit(svg,14)`. `accent_label`
  일치 노드만 accent.
- 결정 트리 (`:473~477` 뒤 "5-b. 위계"): "소속 관계(A 아래 B 아래 C) 2~3층 → tree. 대립·
  동맹 *관계* 면 stakeholder_map(르포)/표."
- 갤러리: 대기업 지배구조 (지주→중간지주 2→계열사 6).

### §5.3 `histogram` — 1변수 구간 도수 (v8.6.3)

- 니치: 연령대별 인원·금액 구간별 건수·기간 분포 — *출처가 집계를 줄 때*. x 가 순서 있는
  구간, 세로가 자연.
- 데이터 (list): `[{bin, count≥0, note?}]` 4~24 + payload `unit?`, `unit_label?`. list 형
  → else 분기 자동.
- 가드: `HistogramRow(bin min1 max12, count ge0)` + `HistogramGuard(min4 max24)` + `sum>0`.
- 렌더 `drawHistogram`: 세로 rung 열 (F14). W 720, H 300+18. 열 폭 min(34, (w-8(n-1))/n).
  `unit = niceUnit(maxCount, 40)`, `unitMarks('rung')`. 최빈 열 opacity 1 + 값 Serif 700 12,
  나머지 .55, 0 열은 짧은 대시. x 라벨 Sans 10 (n>12 홀수 생략). annotations vline(bin)·
  hline 개방 (밴드 매핑). footer `"한 칸 = {fmtUnitKo}{unit_label} · 다섯 칸마다 진한 선"`.
- 결정 트리 (`:459~468` "3. 범주 비교"): "범주가 *순서 있는 구간* 이고 값이 건수·인원 →
  histogram. 출처에 구간별 집계가 있을 때만 (WRITE-AP-5)."
- 갤러리: 가계대출 금액 구간별 차주 수.

### §5.4 `calendar_heat` — 일별 강도 달력 (v8.6.3)

- 니치: 60일~1년 *일별* 강도 — 변동성·공습/시위 횟수·발언 빈도·확진·정전. "언제 몰렸나".
- 데이터 (dict): `{values:[{date:"YYYY-MM-DD", value≥0}], metric_label?, unit_label?}` 60~400
  (초과 시 마지막 371일 클램프), 중복 날짜 금지.
- 가드: `CalendarHeatRow`(ISO 검증) + `CalendarHeatGuard(values min60 max400)` + 중복 검사.
  elif + `_DICT_DATA_REQUIREMENTS["calendar_heat"]=("values",)`.
- 렌더 `drawCalendarHeat`: 주 열 × 요일 7행. 원 r 4.2 간격 13, 5분위 `inkLadder(5)` 역순,
  0 은 속빈. 월 라벨 caps 9.5, 요일 "월·수·금" 9 muted. 최대일 점선 링 r 6.5 + Serif 700 11
  `"{date} · {value}"`. W 720, H 7×13+24+18. footer `"점 하나 = 하루 · 진할수록
  {metric_label||'값'} 큼"`.
- **starvation 보호**: `usage_log.DATA_GATED_TYPES = frozenset({"calendar_heat"})` 신설,
  `composer_rebalance_hint` 제외 (`:238~239`). 일별 데이터 없는 보고서에 힌트가 들어가면
  날조 유도 (candle 과 같은 성격).
- 결정 트리 (`:444~455` "1. 시간축"): "일별 값 ≥60일이고 질문이 *언제 몰렸나* → calendar_heat.
  추세 자체면 line."
- PROMPT_SHAPES 는 결정적 빌더(70일). 갤러리: 코스피 |일간 등락률| 120일 (`dailySeries` 재사용).
- **시장 시계열 자동 주입 (사용자 결정 2026-09-03 — 이번 Phase 에 포함).**
  `src/orchestrator.py` 에 `_ensure_calendar_heat(composed, context) -> None` 신설, 호출은
  `_ensure_time_series_chart` (`:2103`) **직후** 같은 `report_format != "reportage"` 분기
  안 (르포는 시장차트 자동 주입 자체를 건너뛰므로 동일 규칙). 규칙 (0-LLM, 결정적):
  ① 주입 대상 = `_ensure_time_series_chart` 가 고른 *주제 우선 instrument* 1개
  (`_topic_priority_key` 동일 순서) 의 series, 행 ≥60 (3M 기본 기간이면 거래일 ~60)
  ② 값 = `|close_t / close_{t-1} - 1| × 100` (첫 행 제외, `close` 없으면 `value`/`y`
  순으로 대체, NaN 봉 제외 — CHART-AP-29) ③ chart dict = `{type:"calendar_heat",
  title:"{instrument} 일별 변동 강도", subtitle:"거래일만 표시 · 주말·휴장일은 속빈 점",
  unit_line:"단위: |일간 등락률| %", source: series 의 source, metric_label:"등락 폭",
  data:{values:[{date, value}]}}` ④ composer 가 이미 `calendar_heat` 를 emit 했으면
  no-op (중복 회피, `_composer_instruments` 와 같은 원리) ⑤ 삽입 위치 = 주제 instrument
  의 풀 카드(line/candle/area) *바로 뒤* 같은 섹션 ⑥ `ChartCountLimits` 초과 시 주입
  생략 (deep 5 / standard 4 — `_check_chart_count_exceeded` 와 같은 집계) ⑦ flag
  `ENABLE_CALENDAR_HEAT_INJECT` (Config, 기본 `1`; `0` → byte-equal). 테스트
  `tests/regression/test_calendar_heat_inject.py`: 60행 미만 no-op · 중복 no-op · 상한
  초과 no-op · 값 계산 정합 (3행 수기 검산) · 르포 no-op · flag OFF byte-equal.
  usage_log 는 `types` 에 `calendar_heat` 로 집계되나 `DATA_GATED_TYPES` 라 rebalance
  힌트엔 안 들어간다 — composer 자발 emit 은 여전히 데이터 있을 때만.

### §5.5 두 Phase 공통 마감

- `KNOWN_CHART_TYPES` 4종, `chart_type_scenarios.yaml` 헤더 카운트 36(= production 35 + embedded_map,
  실측 기준), 갤러리 = RENDERERS 1:1,
  헤드리스 렌더 unknown/예외 0, 스냅샷 baseline 신규 type 추가 기록.
- `report_bundle_v1.md` §9 pin 주석 "v8.6.3: +treemap/tree/histogram/calendar_heat (additive,
  schema_version 1, §5 B안 폴백 4종 추가)". CLAUDE.md `Chart System` "27종"→"31종".

---

## §6. Phase 2c — type-fit 파이프라인 (v8.6.4)

> **사용자 지시 ③ 의 구현.** composer 가 데이터 모양에 안 맞는 type 을 골랐을 때 (예:
> 연령대 구간을 bar 로, 2층 구성을 donut 으로, 일별 60일을 heatmap 으로) 결정적 규칙으로
> *맞는 type* 으로 바꾼다. 프롬프트 결정 트리가 1선, 이 파이프라인이 안전망 — `_densify_ts_charts`
> / `_reconcile_visual_references` 와 같은 자리·같은 성격 (0-LLM, 디폴트 ON, 킬 스위치).

### §6.1 위치·계약

- 모듈 `src/visual/type_fit.py`: `refit_chart(chart: dict, *, report_format: str) ->
  tuple[dict, str | None]` (새 chart dict 또는 원본, 적용 규칙 id) + `refit_charts(composed)
  -> list[RefitEvent]`. 순수 함수 — `ComposedSection` 재검증은 `refit_charts` 가
  `ComposedSection.model_validate` 로 재구성해 `_drop_invalid_charts` 를 한 번 더 태운다
  (이전에 드롭된 `_dropped_charts` 기록은 이어 붙여 보존 — usage_log 의 emit/kept 2단
  집계가 그 기록에 기댄다).
  — **구현 보정 (v8.6.4 랜딩)**: ⑴ `refit_charts` 는 `report_format` 을 키워드로 받는다
  (기본 `"standard"`). ⑵ 바꿀 게 없으면 `refit_chart` 가 *원본 객체 그대로* 를 돌려주고
  (`out is chart`), 호출부는 identity 로 변경 여부를 판별한다 — 규칙 id 가 있는데 payload
  가 원본인 경우도 있다 (`R7-pending`, 세기만 하는 규칙). ⑶ 변환 시 원본 type 에만 있는
  표현 옵션 키(`schemas.option_fields` 차집합)와 annotation 레이어 없는 target
  (treemap / calendar_heat)의 `annotations` 만 떼고, `title`/`subtitle`/`unit_line`/
  `source`/`note`/`takeaway` 는 전부 계승한다.
- 호출: `src/orchestrator.py` `_densify_ts_charts` 호출 (`:2109`) **직후·`_reconcile_visual_
  references` (`:2118`) 직전**. flag `V8_TYPE_REFIT` (Config, 기본 `1`; `0` 이면 byte-equal).
- `scripts/patch_report.py` 에 `--refit` (rerender 경로에서 같은 함수 호출, `revision`
  소수부 +1 — 표현 변경 규칙과 동일). VM 용 dry-run: `python -m src.visual.type_fit --scan
  reports/ --dry-run` → 규칙별 적중 수·보고서 id 출력 (335건 코퍼스 실측 근거 확보).
- 계측: `usage_log.append_run` 에 optional `refit: [{from, to, rule}]` 필드 (JSONL additive).
  `analyze()` 에 `refit_distribution` 추가. 30건 후 어떤 오배치가 잦은지 → 프롬프트 결정
  트리 보강 (자기교정 루프와 같은 원리, CLAUDE.md `5-Layer ①`).

### §6.2 규칙 (전부 결정적 · 확신 있을 때만 · 각각 fixture 필수)

| id | from → to | 조건 (모두 만족) | 변환 |
|---|---|---|---|
| R1 | bar → histogram | n≥4 · 모든 label 이 구간 패턴 (`^\d+\s*[~\-–]\s*\d+`, `^\d+대$`, `^\d+세`, `이상/이하/미만/초과` 접미) · value≥0 · 정수 | `bin=label, count=value`, payload `unit_label` 계승 |
| R2 | donut / stacked(1 scenario) → treemap | label 이 `A · a1` / `A/a1` / `A > a1` 분리자를 ≥60% 갖고 분리 후 그룹 ≥2·그룹당 잎 ≥2 · 잎 총 ≥6 | 그룹→children 2층 |
| R3 | heatmap(list x,y,value) → calendar_heat | x 가 ISO 날짜 ≥60 distinct · y 가 단일 값 | `values=[{date:x, value}]` |
| R4 | slope → range_bar(before_after) | items ≥8 (SlopeGuard 최대 10) | `before=a, after=b`, `before_label/after_label = left/right_label` |
| R5 | bar → bar(vertical rung) | n≤8 · 모든 label ≤6자 · countable · payload.orientation 없음 | `orientation:"vertical"` 부여 (표현만) |
| R6 | line(≤40, ISO) → line | 변환 없음 — Phase 1 기본이 처리. 규칙표에 *명시적 no-op* 로 기록 (오해 방지) | — |
| R7 | gantt(all start==end) → (drop 유지) | CHART-AP-15 현행. V9 event_timeline 랜딩 시 그쪽으로 재배치 — 본 Phase 는 로그만 (`refit:[{rule:"R7-pending"}]`) | — |

- 금지: 값·라벨을 *생성* 하는 변환 (예: bar 를 histogram 으로 바꾸며 빈 구간 채우기).
  규칙은 필드 이름 바꾸기·재그룹만. 변환 후 `validate_chart_data`(+`validate_chart_options`)
  실패면 **원본 유지** (더 나빠지지 않기).
- **구현 보정 (v8.6.4 랜딩) — 위 표를 이렇게 읽는다.**
  · R1 은 `count` 를 0 이상 *정수* 로만 받고 bin 라벨 12자 상한(HistogramRow)까지 미리
    본다. R1 이 안 걸린 bar 에 R5(표현만)가 걸릴 수 있다 — 둘은 배타가 아니라 순차다.
  · R2 의 "≥60%" 는 값싼 사전 게이트일 뿐이고, 분리자 *없는* 라벨은 **자기 자신을 그룹으로
    하는 잎 1개** 로 취급한다. 그러면 "그룹당 잎 ≥2" 제약에 자동으로 걸려 변환이 취소된다
    — 데이터를 한 행도 버리지 않으면서(안전 규칙 ②) 애매한 경우를 배제하는 방식이다.
  · R3 은 행이 400을 넘으면 **변환하지 않는다**. 가드 상한을 맞추려면 행을 잘라야 하는데
    그건 데이터를 버리는 것이다. y 단일 값은 `metric_label` 로 재사용한다(생성 아님).
  · R5 는 `orientation` *또는* `texture` 가 이미 있으면 건너뛴다 (작성 모델의 표현 지정
    존중). 조건은 `charts.js:drawBar` 의 rung 게이트와 같은 값 — 게이트를 못 넘을 값을
    넣으면 렌더러가 가로로 강등할 뿐이라 미리 막는다.
  · R6 은 `RULES` 레지스트리에 `active=False` 로 등재만 하고 이벤트도 내지 않는다.
    R7 은 `active=False` 지만 `R7-pending` 이벤트를 내 계측에 남는다.
- 테스트 `tests/regression/test_type_fit.py`: 규칙별 positive 1+ · negative 2+ (평범한
  bar 가 R1 에 안 걸림, 날짜 아닌 heatmap 이 R3 에 안 걸림, 7 items slope 는 R4 미적용),
  flag OFF byte-equal, 변환 실패 시 원본 유지.
- Phase 5 착지 후 추가 규칙: R8 bar(n==1, target 있음) → gauge · R9 sankey(사슬형 2열) →
  funnel (§9).

### §6.3 프롬프트 측 (1선)

- 결정 트리에 각 규칙의 *원인 오배치* 를 negative 로 명시: "연령대·금액대 구간 → bar 금지
  (histogram)", "부문→세부 2층 → donut 금지 (treemap)", "일별 60일+ → heatmap 금지
  (calendar_heat)", "2시점 ≥8항목 → slope 금지 (range_bar before_after)". `chart_type_
  scenarios.yaml` 의 `negative_examples` 도 동일하게.

---

## §7. Phase 3·4 — 검수·안티패턴·osint·문서 (v8.6.5)

### §7.1 시각 검수

1. 스냅샷 `--diff-report` — Phase 1 이후 바뀐 type 목록이 §4 대상 12종과 *정확히 일치*
   (그 외 type 이 바뀌었으면 부작용).
2. 갤러리 5테마(+reportage_steel) × 33종 헤드리스 스크린샷 (`chrome --headless=new
   --screenshot --window-size=1000,16000`) → `samples/_render/` (gitignore). 확인: 라벨
   겹침(AP-33) · 캡션 잘림 · 다크 반전 글자색 · rung 강등 로그 · 540px 에서 footer 가독 ·
   눈금 링 donut 의 arc 애니 정상.
3. `samples/chart_redesign_v8_6_compare.html` 사용자 리뷰 → 머지 게이트.
4. codex 비전(`V6_CODEX_VISUAL`) 실보고서 평가는 VM 후속.

### §7.2 안티패턴 등재 (`docs/CHART_RENDERING_ANTIPATTERNS.md` `:1454` 뒤)

- `## CHART-AP-46: 단위 질감을 비정수·큰 값·비율에 적용 → 수백 칸 노이즈 또는 무의미 단위
  (v8.6.5 신설, 선제)` — 증상/원인(LLM 이 texture·unit 직접 지정)/Fix(`isCountable`
  자동 판정 + `niceUnit` 칸수 상한 + 프롬프트 "texture·unit 미지정" + 가드 `unit>0`).
- `## CHART-AP-47: 데이터 모양과 type 불일치를 프롬프트에만 맡김 → 구간·2층·일별 데이터가
  bar/donut/heatmap 으로 발행 (v8.6.5 신설, 사용자 지적)` — Fix = §6 type-fit.
- CLAUDE.md `Anti-Patterns (차트 렌더링)` 요약 줄 + CHANGELOG.

### §7.3 osint 통지(n) — `reviewer_osint_q_a`

- 규칙 CLAUDE.md OSINT 교신 ①~⑦. `add_repo(doroper98/reviewer_osint_q_a)` → clone →
  `threads/` 의 `agent_reviewer_bot_n_NN` 최대 +1 → `TZ=Asia/Seoul date +%Y_%m_%d_%H%M%S`
  → `templates/notice_template.md`.
- 내용: ① v8.6.3 부터 `charts[].type` 4종 추가 + 기존 type payload 옵션 필드 (bar
  texture·prior·orientation·unit / range_bar mode / area fill / line marks / heatmap cells /
  scatter x_low_label 등) + v8.6.4 type-fit 로 발행 분포 변화 예고 ② schema_version 1
  유지 ③ osint 현황 (탐색 결과): `render_io.SUPPORTED_CHART_TYPES` 22종 게이트 → 신규
  type 은 텍스트 폴백 무경고 소실, `BundleChart.prerendered_svg` 는 모델에만 있고 미소비,
  `hyperframes/bundle_to_video.py` 의 `EXTRA_CHART_SCENES` 는 별도 목록 ④ producer 는
  4종 `prerendered_svg` B안 폴백 제공 — 소비 여부는 osint 결정 (C0 원칙상 자체 렌더러가
  정답) ⑤ `ack_required: no`. osint_generator repo 자체는 본 플랜에서 무변경.

### §7.4 문서 헤더 정합

`last_synced_with: v8.6.5`: MONO_THEME_GUIDE / CHART_RENDERING_ANTIPATTERNS / REGISTRY 주석 /
REPO_MAP / report_bundle_v1 / 본 문서 (status → landed). README `Status`, CHANGELOG.
`REFACTOR_V7_PLAN.md` §1.2 미완 항목(`fmtNum` SSOT) 에 "v8.6.0~1 랜딩" 각주. `docs/
DATA_MODELS.md` 는 모델 무변경이라 제외 (usage_log JSONL 필드는 계약 아님).

---

## §8. 사용자 결정 사항 (전부 확정 — 재질문 금지)

| # | 결정 | 사용자 결정 (2026-09-03) | 반영 위치 |
|---|------|--------|-----------|
| ① | calendar_heat 시장 자동 주입 | **이번 Phase 에 주입** (Fable 권장 2차를 기각) | §5.4 `_ensure_calendar_heat` 스펙, Phase 2b 체크리스트 |
| ② | 7단 잉크 사다리 §10.1 등재 | **승인** | §3.3 (Phase 0) |
| ③ | 표현 방식 전면 흡수·소급 | 지시 | §2.1 / §4 |
| ④ | 신규 유형 폭넓게 (1차 4 + 2차 3) · type-fit 파이프라인 · PDF 보관 | 지시 | §5 / §6 / §9 / `docs/reference/` |

**network·force 계열 기각 근거 (사용자 질문 2026-09-03 에 대한 답, 기록용).**
- `network` 는 기능 부족이 아니라 **사용자 본인의 폐기 결정** 이다 (CHART-AP-36, v7.9.17).
  v5.5.5 에서 radial hairball 을 인접행렬로 바꿨는데도 "의미 대비 세로 공간 과다" 로
  포맷을 영구 제거했고, `validate_chart_data` 가 무조건 drop 한다.
- force/physics 레이아웃은 **좌표가 데이터가 아니라 물리 시뮬레이션 결과** 라 ① 렌더마다
  달라져 발행본·영상(osint)·스냅샷 회귀가 불가능하고 ② 노드가 카드(국기·로고·사진)인
  우리 관계도에선 겹침·중심 관통 실타래가 필연이며 (CHART-AP-25 재현) ③ 위치에 의미가
  없어 독자가 "왜 저기 있나" 를 읽을 수 없다. 그래서 v8.0.0 `stakeholder_map` 은 좌표를
  진영 칼럼으로 *결정적* 계산한다 (CHART-AP-37).
- 참고 자료의 G6 Circular / G11 Force / B1·B2 가 예뻐 보이는 이유는 노드 ≤12 이고
  라벨이 짧은 영문이기 때문이다. 같은 조건을 우리 데이터(한글 기관명·인물 + 국기·로고)가
  만족하지 않는다.
- **열어 둔 문 (선택, 본 플랜 밖):** G6 의 *원형(ring) 배치* 자체는 force 가 아니라
  결정적이다 (노드를 원주에 등간격, 엣지는 원 안 곡선). 사용자가 원하면
  `stakeholder_map.layout:"ring"` 옵션 (≤12 노드, 진영별 호 구간, 엣지 type 별 선 스타일
  유지) 으로 CHART-AP-37 을 위반하지 않고 그 *모양* 만 흡수할 수 있다. 채택 시 §9 표에
  추가 — 사용자 지시 있을 때만.

---

## §9. Phase 5 — 2차 흡수 (v8.7.0)

| 항목 | 참고 | 데이터 · 렌더 요지 | 절차 |
|---|---|---|---|
| `gauge` | F11 | `{value, target, label?, unit_label?}` 단일 KPI. 반원 100 눈금 링 (채움 = value/target), 중앙 큰 숫자 Serif 800 30 `t.text`(accent 금지 §10), 아래 `"{남은 눈금} TICKS TO GO"` → `"목표까지 {n}눈금"`. bullet 은 다항목, gauge 는 1항목 | 9단+3 |
| `spectrum` | L7 | `{rows:[{left_label, right_label, points:[{label, value:-1..1, emphasis?}]}]}` 2~6행, 점 ≤5/행. 양극 축 hairline, 점 r 4/emphasis r 7 ink, 축 끝 caps 라벨 | 9단+3 |
| `funnel` | L13 | `[{stage, count}]` 2~6 단계, 위→아래 폭 = count, 각 단계 tick 질감(참고 "한 눈금 = 사람 몇 명") + 단계 사이 `"{전환율}%"`. sankey 2열 사슬 오용을 R9 로 재배치 | 9단+3 |
| `bump.layout:"strip"` | G21 | 순위 격자 (셀 = 그 시기 순위, 1위 검정) + 우측 ▲▼ 변동 | 옵션 |
| `stacked.texture:"rung"` | F7 | 세그먼트별 농도 rung, 게이트 §2.7 | 옵션 |
| `bar.texture:"pictogram"` | G5 | 내장 글리프 4종 (사람·건물·차량·원) SVG path 인라인, 글리프 = `unit` | 옵션 |
| `parallel_coords` | L20 | 검토 — 한글 축 라벨 세로 배치 시험 후 채택 여부 | 검토 |

착수 조건: Phase 2c 계측 30건에서 R8/R9 후보(단일 KPI bar, 사슬형 sankey) 적중이 관찰되면
우선. 아니면 usage_log starvation 과 무관하게 v8.7.0 으로 진행 (사용자 "폭넓게" 지시).

---

## §10. Opus 실행 체크리스트 (순서 고정)

> 매 Phase 공통: `git pull origin claude/chart-type-design-improvement-3o6p4i` · `git config
> core.hooksPath .githooks` · 완료 시 `python -m py_compile` (변경 .py 전부) + `node -e`
> charts.js 구문 검사 + `pytest tests/regression -q` + 스냅샷 `--check`/`--diff-report` +
> VERSION/README/CHANGELOG → 커밋 `vX.Y.Z: ...` → push. 커밋·PR 에 모델명 금지. 시장 데이터
> ·발행본 접근이 필요한 검증(type_fit `--scan reports/`, codex 비전) 은 VM 명령을 사용자에게
> *복사용 한 줄* 로 제시 (CLAUDE.md "명령어 없는 지시 금지").

**Phase 0 (v8.6.0)** — 완료 (2026-09-03)
- [x] `samples/chart_gallery_v7.html`: network 제거 · 누락 4종 추가 · `reportage_steel` 버튼
      (RENDERERS 31종과 1:1, 헤드리스 렌더 unknown/예외 0)
- [x] `scripts/chart_dom_snapshot.py` + `tests/regression/test_chart_dom_snapshot.py` + baseline JSON
      (31 type × 6 테마, loose 3종. 하네스로 IntersectionObserver·모션·CDN 의존을 제거해 결정적 렌더)
- [x] charts.js 헬퍼 8개 + `contentFit` (정의만, 호출 0) · 구문 검사 · 스냅샷 `--check` 0 diff
- [x] MONO_THEME_GUIDE §10.1 · REPO_MAP · `docs/reference/README.md` · VERSION/README/CHANGELOG → 커밋

**Phase 1 (v8.6.1)** — 완료 (2026-09-03). 순서: bar → candle → donut → 캡슐 5종 → line/area/scatter → range_bar → heatmap
- [x] `samples/_legacy/charts.v8515.js` 고정 (릴리스 태그가 없어 커밋 메시지로 v8.5.15 커밋 특정)
- [x] 렌더러 13종 §4.1~4.7 · 인라인 포맷 → `fmtNum` (칸 질감 라벨은 정수 그대로)
- [x] `schemas.py` — 행 필드(`prior` / before_after 행) + **payload 옵션 가드 신설**
      (`validate_chart_options`, `_TYPE_TO_OPTION_GUARD` 7종). 옵션은 data 가 아니라
      payload 최상위라 `validate_chart_data` 로는 볼 수 없어 별도 진입점 +
      `ComposedSection._drop_invalid_charts` 배선. rung 게이트는 drop 이 아닌 렌더러 강등.
- [x] `narrative_composer.py` 스키마 줄 6곳(bar/line/area/heatmap/scatter/lollipop/range_bar) + §4.8 원칙 블록
- [x] `PROMPT_SHAPES` (+옵션 parity 3종) · `test_chart_correctness.py` (수용/거부 6종) ·
      `samples/chart_redesign_v8_6_compare.html` (좌 v8.5.15 실 렌더 vs 우 현행, 테마 3종)
- [x] 갤러리 표현 변형 fixture 6종 + 스냅샷 키(`data-snapshot-key`) 도입 → baseline 37키 × 6테마
- [x] `--diff-report` 변경 목록 = §4 대상 13종 (그 밖 24종 DOM 불변) → CHANGELOG 기재 → 커밋

**Phase 2a (v8.6.2) treemap·tree** — 완료 (2026-09-03)
- [x] 절차 ①~⑫ · registry 11/17/2/30 → **11/19/1/31** (treemap 승격 + tree 신설) ·
      `test_capability_registry.py` 3곳(카운트·guarded 집합·experimental 집합) + chart_gate
      의 experimental 예시를 treemap → chord 로 교체
- [x] dict 계약 2종이라 `validate_chart_data` elif + `_DICT_DATA_REQUIREMENTS` +
      `_MIN_LEN_REQUIREMENTS["treemap"]` 까지 (CHART-AP-38 — 빠지면 100% silent drop)
- [x] `usage_log.KNOWN_CHART_TYPES` · 결정 트리 2분기(4. 구성 끝 treemap / 5-b. 위계 tree)
      + 스키마 줄 + emit X 규칙 · `PROMPT_SHAPES` · `chart_type_scenarios.yaml`(34) ·
      `svg_prerender.B_PLAN_CHART_TYPES` · `report_bundle_v1.md` §9 pin
- [x] 갤러리 `PAYLOADS` 2종 + baseline 신규 키만 추가 (기존 37키 불변 — `--diff-report` 증명),
      `tree` 는 `contentFit` 의존이라 `LOOSE_TYPES` 등록
- [x] CLAUDE.md `Chart System` "27종"→"29종" + 신규 type 절차 ⑩~⑫ 명문화 → 커밋

**Phase 2b (v8.6.3) histogram·calendar_heat** — 완료 (2026-09-03)
- [x] 절차 ①~⑫ · registry 11/19/1/31 → **11/21/1/33** · `test_capability_registry.py` 3곳
- [x] `usage_log` KNOWN + `DATA_GATED_TYPES`(calendar_heat) · 결정 트리 2곳(1. 시간축 끝 calendar_heat /
      3. 범주 비교 첫 분기 histogram) · 갤러리 fixture 2종 · baseline **신규 2키만 추가**
      (`--diff-report` 로 기존 39키 중 38키 불변 증명 — 바뀐 1키는 아래 range_bar 덤)
- [x] `orchestrator._ensure_calendar_heat`(+ `_daily_move_values` / `_find_full_ts_card`) + Config
      `ENABLE_CALENDAR_HEAT_INJECT`(기본 ON) + `.env.example` + `tests/regression/test_calendar_heat_inject.py` 12종 (§5.4)
- [x] 덤 — Phase 1 의 `range_bar` `before_after` 값 라벨 정수화 (`isCountable` 재사용).
      최저~최고 range 모드는 소수가 정보라 v8.6.1 표기 유지 (스냅샷 `range_bar` 키 불변)
- [x] CLAUDE.md "31종" + `Market Data Fetcher` 절에 calendar_heat 주입 한 줄 → 커밋

> **구현 판단 3건 (계획서와 다르게 결정한 것).**
> ① `_ensure_calendar_heat(composed, context)` 에 `mode` 인자를 추가했다 (`mode="standard"` 기본).
>   §5.4 ⑥ 의 `ChartCountLimits` 는 mode 별 값이라 mode 없이는 상한을 알 수 없다.
> ② 대상 instrument 는 "`_topic_priority_key` 최상위" 가 아니라 "그 순서로 훑어 *풀 카드가 실제로
>   있는* 첫 종목" 이다. 달력은 추세 카드 뒤에 붙는 보조 시각물이라 붙일 카드가 없으면 뜻이 없고,
>   주인공이 compact strip 으로만 덮인 경우(§5.4 ⑤ 가 상정하지 않은 경우)에 삽입 위치가 사라진다.
> ③ `calendar_heat` 렌더러의 칸 간격은 고정 13 이 아니라 주 수에 따라 11~18 (1년치가 13 근방).
>   720 폭 캔버스에 18주짜리 달력을 13 간격으로 그리면 왼쪽 1/3 에만 몰려 카드가 비어 보인다.

**Phase 2c (v8.6.4) type-fit** — 완료 (2026-09-03)
- [x] `src/visual/type_fit.py` R1~R7 (`RULES` 레지스트리 + `RefitRule`/`RefitEvent`) +
      CLI `--scan/--dry-run/--rules` (읽기 전용) · Config `V8_TYPE_REFIT`(기본 ON) + `.env.example`
- [x] orchestrator 호출 — `_densify_ts_charts` 직후 · `_reconcile_visual_references` 직전,
      flag 게이트 뒤 · `patch_report --refit`(render_revision 소수부 +1) ·
      `usage_log.append_run(refit=...)` + `analyze()['refit_distribution']`
- [x] `schemas.option_fields()` 공개 헬퍼 신설 (type 변경 시 옛 표현 옵션 제거용)
- [x] `tests/regression/test_type_fit.py` 41종 (규칙별 positive ≥1 · negative ≥2 ·
      값 보존 · 가드 실패 시 원본 유지 · orchestrator 배선 · flag OFF · CLI scan) ·
      결정 트리 negative 4건(`[자주 나는 오배치 4가지]` 블록 + 분기 2곳 보강) ·
      `chart_type_scenarios.yaml` negative_examples 5곳 → 커밋
- [x] charts.js 무변경 → DOM 스냅샷 41키 0 diff 가 렌더 불변을 증명
- [x] 사용자에게 VM 실측 명령 제시: `cd ~/agents_reviewer && source venv/bin/activate && python -m src.visual.type_fit --scan reports/ --dry-run`

**Phase 3·4 (v8.6.5)**
- [ ] 갤러리 헤드리스 스크린샷 리뷰 · compare 페이지 사용자 게이트
- [ ] CHART-AP-46/47 · CLAUDE.md 요약 줄 · `reviewer_osint_q_a` 통지(n) · 문서 `last_synced_with` → 커밋

**Phase 5 (v8.7.0)** — §9 표 순서 (gauge → spectrum → funnel → 옵션 3종), 각각 절차 ①~⑫,
R8/R9 를 type_fit 에 추가.

**완료 기준 (전체)**: 회귀 전체 pass · 스냅샷 변경 type = 의도 목록과 일치 · 갤러리 36종
unknown/예외 0 · registry 36 · osint 스레드 posted · VM 반영 안내 (playbook §1 블록 +
`sudo systemctl restart agents-reviewer.service`) 복사용 제시.
