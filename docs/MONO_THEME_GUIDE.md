---
tier: 2
last_synced_with: v8.6.5
ssot_for:
  - "Editorial Cream / Burgundy Mono / Light Mono 세 톤 팔레트"
  - "모노톤 차트·지도 패턴 시스템 (해칭·도트 정의 + 적용 규칙)"
  - "셀 수 있는 단위 어휘 — 칸 질감·캡슐·액센트 농도 사다리·읽는 법 캡션 (§10.1, v8.6.0 · 사다리 색 v8.6.5)"
  - "d3 + d3-geo + TopoJSON 시각화 스택 결정"
  - "Newsreader / IBM Plex Sans KR / IBM Plex Mono 폰트 시스템 (v4.5.0)"
  - "샘플 호스팅 — GitHub Pages + Actions 자동 배포"
depends_on:
  - "samples/chart_map_mono_compare.html"
  - "samples/report_design_sheet_v8_5_9.html"
  - ".github/workflows/pages.yml"
  - "docs/REPORT_STYLE_GUIDE.md"
  - "src/templates/report.css (테마 토큰 SSOT — v4.5.3 부터 --card-deep 정의 추가)"
  - "src/lens_policy.py:_THEME_BY_CATEGORY"
last_review: 2026-05-05
---

# Theme Guide — Editorial Cream · Burgundy Mono · Light Mono

> v4.5.0 부터 *세 톤* 보고서 테마. 디폴트는 `editorial_cream` (cream + terracotta, LG AI Seminar 톤). `burgundy_mono` 는 위기·분쟁 (`geopolitical`/`accident`) 한정. `light_mono` 는 legacy 보존. 색 대신 패턴/명암으로 카테고리를 구분하는 모노톤 시각화 시스템은 그대로.
> 살아있는 참조 구현: [samples/chart_map_mono_compare.html](../samples/chart_map_mono_compare.html).
> **라이브 미리보기**: <https://doroper98.github.io/agents_reviewer/samples/chart_map_mono_compare.html>

## 0. v4.5.0 변경 요약

| 항목 | v4.4.x 이전 | v4.5.0 |
|---|---|---|
| 디폴트 테마 | `burgundy_mono` (다소 밝은 와인) | `editorial_cream` (cream + terracotta) |
| `burgundy_mono` 톤 | bg `#3D1820`, water `#2A0E16` | bg `#2A0F18`, water `#1A0810` (어둡게 보정) |
| 폰트 | Noto Serif KR + Noto Sans KR + JetBrains Mono | **Newsreader** (display, 영문/숫자) + **IBM Plex Sans KR** (본문) + **IBM Plex Mono**. Noto Serif KR 한국어 폴백. |
| 카테고리 → 테마 | tech/financial/geopolitical/accident → burgundy, policy → light | tech/financial/policy/industry/general → editorial_cream, geopolitical/accident → burgundy_mono |
| Editorial 컴포넌트 | 없음 | `lede` / `analogy` / `fact_grid` / `dropcap` / 자동 TOC |
| composer 톤 | 음슴체 (~함) | 평어체 (~다) + 질문 던지기 |

세부 토큰은 `src/templates/report.css` (SSOT). 카테고리 라우팅은 `src/lens_policy.py:_THEME_BY_CATEGORY`.

---

## 1. 결정 배경

기존 보고서 멀티컬러(red·orange·gold·green·blue) 팔레트는 정보 밀도가 높을 때 시각 피로를 유발하고, 모노 인쇄·캡처·임베딩 환경에서 카테고리 구분이 사라지는 약점이 있었다. 멀티 컬러 팔레트는 **폐기**하고, 다음 두 모노톤을 보고서 메인 테마로 채택한다.

- **Light Mono** — 크림 배경 + 검정 텍스트 + 버건디 액센트. IBKR 풍 편집 톤.
- **Burgundy Mono** — 와인 배경 + 파치먼트 텍스트 + 앰버 액센트. @abhinavbwj 카드 풍.

색이 한 가지 지배 hue 로 수렴하므로, **카테고리 구분은 hue 차이가 아니라 패턴(45° 사선 밀도)·도트·액센트 단색·명암 단계**로 구현한다.

## 2. 시각화 스택

| 레이어 | 라이브러리 | 비고 |
|---|---|---|
| 베이스맵 | **d3 + d3-geo + TopoJSON (world-atlas/110m)** | 단일 ~100KB JSON 으로 전 세계 국경 벡터, 외부 타일 의존 없음 |
| 지리 오버레이 | **d3** (`geoMercator` + `geoPath`) | 위·경도→픽셀 투영, 호·반경원·마커 SVG 그리기 |
| 차트 | **d3 v7** (line/area/bar/force) | 모두 SVG. Canvas 사용 금지 |
| 폰트 | Noto Serif KR / Noto Sans KR | 본문/지도 라벨 모두 동일 폰트 사용 |

**MapLibre + 벡터 타일 / Leaflet + 비트맵 타일을 쓰지 않는 이유**:
- 외부 타일 서비스(OpenFreeMap, Maptiler 등)는 응답 지연 / 글리프 PBF 호출 / 스키마 변경에 취약함. 샘플 페이지가 빈 배경으로 떨어지는 회귀 발생.
- 이벤트 분석 보고서는 줌·팬이 거의 필요 없고 국가 수준 경계만 있으면 충분함. world-atlas 110m 으로 모든 케이스 커버.
- TopoJSON 은 한 번 받으면 두 컬럼이 캐시 공유. 인쇄·캡처 시에도 안정적.

## 3. 색 팔레트

### 3.1 Light Mono

```
용도            토큰         HEX          비고
배경           --bg          #efe8d9      따뜻한 크림
카드 면        --card        #f8f2e4
경계 (강)      --border      #b3a586
경계 (약)      --borderLight #d4c8a8
텍스트 본문    --text        #1a1a1a      거의 검정
텍스트 보조    --muted       #5a5a5a
지도 육지      land          #efe8d9
지도 수면      water         #dccea8
지도 국경      boundary      #1a1a1a
액센트 1 (편집 강조)  --accent  #9a1e3c   딥버건디
액센트 2 (긍정)       --up      #2d6a3e   포레스트 그린
액센트 3 (위험)       --down    #9a1e3c   동일 버건디 재사용
```

### 3.2 Burgundy Mono

```
용도            토큰         HEX          비고
배경           --bg          #3D1820      식별 가능한 딥와인
카드 면        --card        #4A222E
경계 (강)      --border      #6E3340
경계 (약)      --borderLight #4A222E
텍스트 본문    --text        #EFE5D1      파치먼트 크림
텍스트 보조    --muted       #A88E7A      더스티 모브
지도 육지      land          #3D1820
지도 수면      water         #2A0E16
지도 국경      boundary      #EFE5D1
액센트 1 (편집 강조)  --accent  #D4A858   앰버 골드
액센트 2 (긍정)       --up      #A8B582   세이지 올리브
액센트 3 (위험)       --down    #C9837A   더스티 로즈
```

### 3.3 액센트 의미 일관성

| 역할 | 적용 위치 |
|---|---|
| `--accent` | 편집 강조 (italic 단어), callout 좌측 보더, 키 카테고리 단색 |
| `--up` | 상승·기회·성공 지표 (작은 변동 라벨만) |
| `--down` | 하락·위험·경보 (작은 변동 라벨, 이벤트 vertical, 위험권 보더) |

큰 숫자(metric value)는 `--text` 로 강제 — 작은 변동 라벨에만 색을 쓴다.

## 4. 패턴 시스템

### 4.1 정의

총 4종 패턴 + 액센트 솔리드. 모든 사선은 **45°** 한 방향만, 도트는 미세 원형. **opposite-diagonal / cross-hatch / dashed-stroke 패턴 금지** — §6 참조.

| ID | 모양 | 타일 | stroke | 색 |
|---|---|---|---|---|
| `hatch-tight` | 45° 솔리드 사선 | 2.4 × 2.4 | 0.85 | `--text` |
| `hatch-wide` | 45° 솔리드 사선 | 3.8 × 3.8 | 0.7 | `--text` |
| `accent-hatch` | 45° 솔리드 사선 | 2.4 × 2.4 | 0.85 | `--accent` |
| `dots` | 미세 원 | 2.4 × 2.4 | r=0.22 | `--text` |
| (액센트 솔리드) | 단색 채움 | — | — | `--accent` |

SVG 정의 예시는 `samples/chart_map_mono_compare.html` 의 `definePatterns()` 참조.

### 4.2 카테고리·심각도 적용 규칙

| 적용 대상 | 카테고리/단계 | 패턴 |
|---|---|---|
| 위험도 (3단계) | high | `hatch-tight` |
|  | medium | `hatch-wide` |
|  | low | `dots` |
| 막대 카테고리 (5종) | 핵심 항목 | 액센트 솔리드 |
|  | 기타 항목 1~4 | `hatch-tight` / `accent-hatch` / `hatch-wide` / `dots` (인덱스 순환) |
| 면적 차트 fill | 단일 시리즈 | `hatch-wide` 사선 해칭 |
| 지도 위험 반경 | 한 단계 | `hatch-wide` 채움 + 보더 점선 |

### 4.3 라인·연결선 스타일

색 대신 dash array 로 관계 종류 구분 (방향성 역시 같은 색계 안에서 처리).

| 종류 | dash | stroke-width |
|---|---|---|
| 동맹 / 협력 | 실선 | 1.4 |
| 충돌 / 봉쇄 | `5,3` | 2.0 |
| 영향 / 충격 | `2,3` | 1.4 |
| 전략 / 보조 | `1,3` | 1.4 |

## 5. 시각화별 처리 규칙

| Viz | 처리 |
|---|---|
| Geographic Map | 주 경로 = 실선, 보조 경로 = 점선. 위험권 = 사선 해칭 채움 + 점선 보더. 마커 라벨은 SVG 오버레이로 직접 그리고 베이스맵 텍스트 레이어는 사용하지 않는다 (성능). |
| Network (관계 인접행렬) | v5.5.5 부터 radial 폐기 → **인접행렬** (CHART-AP-25). 행위자를 행·열에 두고 셀이 관계 type 인코딩: 대립 = `--down` 솔리드 + ✕, 동맹 = `--accent` 솔리드, 영향 = `accent-hatch`, 연관 = `dots`. 대각선은 `--border` fill-opacity 0.35 로 차단. 진영(group) 으로 정렬해 같은 진영을 대각선 근처에 모은다. 데이터 계약 (nodes/links) 불변. viewBox 는 getBBox content-fit → 자동 중앙 정렬 + 라벨/범례 클리핑 0. 모크업: `samples/actor_relationship_redesign_compare.html`. |
| Line + Events | 면 채움은 `hatch-wide` 사선 해칭. 이벤트 vertical 은 `--down` 점선. 끝점 dot + 값 라벨은 `--accent`. |
| Bar Categorical | 핵심 항목 = 액센트 솔리드. 기타 항목 = §4.2 패턴 순환 (`hatch-tight`, `accent-hatch`, `hatch-wide`, `dots`). |

## 6. Anti-patterns (절대 금지)

검증 과정에서 시각적으로 깨졌던 조합. 새 패턴/시각화 추가 시에도 위반 금지.

1. **Cross-hatch (가로+세로 교차 패턴)** — 격자 문양이 차트의 그리드 라인과 충돌하고 데이터 카테고리 구분이 시각적으로 사라짐.
2. **Opposite-direction diagonals (45° + −45°)** — 인접 막대 사이에서 시선이 두 방향을 합쳐서 'X' 로 인지함. 모든 사선은 한 방향(45°)만.
3. **Dashed strokes inside rotated patterns** — 회전 후 인접 타일의 dash 가 격자처럼 정렬되어 '+' 모양으로 보임. dash 는 line element 에는 OK, pattern 내부에는 금지.
4. **너무 큰 도트** — r ≥ 0.4 는 점박이 텍스처가 되어 데이터 표면에 노이즈 유발. r=0.22 ~ 0.25 micro-dot 만 사용.
5. **인접 카테고리에 같은 hue 의 다른 명암** — 모노 한계로 카테고리간 차이가 거의 안 보임. 패턴 차이가 명암 차이보다 우선.
6. **베이스맵 비트맵 타일** — 모노 리스타일 불가, 패턴 오버레이와 색 충돌. 벡터 타일 + 인라인 style 만.
7. **큰 숫자(metric value)에 액센트 색 적용** — IBKR 레퍼런스 일관성. 큰 숫자는 항상 `--text`, 작은 변동 라벨에만 `--up`/`--down`.

## 7. 샘플 호스팅 (GitHub Pages)

샘플 HTML 은 GitHub Pages 로 자동 배포된다. raw.githack / jsDelivr / cdn.statically 같은 외부 프록시는 모바일 ISP 차단 / CDN 캐시 / Content-Type 문제로 신뢰할 수 없으므로, GitHub 자체 인프라(Pages + Actions)를 표준 미리보기 채널로 사용한다.

### 7.1 라이브 URL

```
https://doroper98.github.io/agents_reviewer/samples/<file>.html
```

현재 활성 샘플:
- [chart_map_mono_compare.html](https://doroper98.github.io/agents_reviewer/samples/chart_map_mono_compare.html) — 모노 테마 + 차트·지도 비교 레퍼런스
- [report_design_sheet_v8_5_9.html](https://doroper98.github.io/agents_reviewer/samples/report_design_sheet_v8_5_9.html) — **디자인 규약 시트** (v8.5.9). 보고서(`freeform_essay`) · 르포(`reportage`) 두 장르의 색 토큰 · 타이포그래피 · 레이아웃 · 컴포넌트 18종 · 차트/지도 어휘 · 모션 · 접근성 · 확장 절차를 한 장에. 팔레트/토큰 값은 `src/templates/report.css` 에서 파싱해 주입하고 컴포넌트 미리보기는 실제 템플릿 CSS 를 이식했다 (문서가 코드를 베끼지 않는다). 테마 21종 · 장르 2종 라이브 전환 + WCAG 대비 실시간 산출.

### 7.2 자동 배포 흐름

`.github/workflows/pages.yml` 워크플로우가 다음 조건에서 트리거되어 Pages 로 배포한다.
- `main` 브랜치에 `samples/**` 또는 `.github/workflows/pages.yml` 변경이 push 될 때
- Actions UI 에서 수동 dispatch (workflow_dispatch)

소요 시간 약 1~2분. 배포 결과는 위 URL 에서 즉시 확인 가능.

### 7.3 1회 설정

repo settings 에서 두 곳을 한 번만 켜두면 끝:
1. **Settings → Pages** → Source = `GitHub Actions`
2. **Settings → Environments → github-pages → Deployment branches and tags** = `No restriction` (또는 `main` 룰 추가)

이후로는 코드 push 만으로 자동 갱신.

## 8. 참조 자료

- 살아있는 비교 샘플 (라이브): <https://doroper98.github.io/agents_reviewer/samples/chart_map_mono_compare.html>
- 살아있는 비교 샘플 (소스): [samples/chart_map_mono_compare.html](../samples/chart_map_mono_compare.html)
- 보고서 전반 톤 가이드 (Burgundy 베이스): [docs/REPORT_STYLE_GUIDE.md](REPORT_STYLE_GUIDE.md)
- 배포 워크플로우: [.github/workflows/pages.yml](../.github/workflows/pages.yml)
- @abhinavbwj 의 "the distinction" / "computational design" 카드 톤 (Burgundy Mono 베이스 레퍼런스)
- IBKR Korean Stocks 리포트 (Light Mono 베이스 레퍼런스)

## 9. Change Propagation

- 팔레트 hex 변경 → `samples/chart_map_mono_compare.html` 의 `THEMES` 객체 + 본 문서 §3 동시 갱신
- 패턴 정의 변경 → `definePatterns()` + 본 문서 §4.1 동시 갱신
- Anti-pattern 추가 → 본 문서 §6 + 샘플 파일 검증 후 등재
- 지도 라이브러리 변경 → 본 문서 §2 + 샘플의 `buildMap()` + `buildColumn` 의 viz-desc 텍스트 동시 갱신
- 신규 샘플 추가 → `samples/` 에 파일 추가 + 본 문서 §7.1 활성 샘플 목록에 라이브 URL 등재
- Pages 워크플로우 변경 → `.github/workflows/pages.yml` + 본 문서 §7.2 트리거 조건 동시 갱신

---

## 10. v7.1.0 — 잉크 농도 위계 어휘 (초기 7종 리디자인, 사용자 승인)

bar / donut / stacked / bubble / heatmap / network / waterfall 의 리디자인
(samples/chart_redesign_v7_compare.html 목업 승인 후 charts.js 이식, 과거 발행본 소급)
에서 확정된 어휘 규칙 — 본 가이드 §4 패턴 시스템의 *적용 범위 정밀화*:

- **해치(45° 단방향)는 '명목 카테고리' 전용으로 환원.** 순위(bar)·서수 강도(heatmap)·
  구성 위계(stacked/donut)처럼 *한 변수의 위계* 인 곳에 해치를 쓰면 카테고리처럼
  오독되고 노이즈가 된다 — 그곳은 **단일 잉크(--text)의 농도 사다리** (예: 0.42/0.24/
  0.13, ≤4단) + 핵심 1개만 --accent.
- **값 라벨은 Newsreader 세리프 직접 라벨** (막대 끝·조각 중앙·기둥 위). 범례는 직접
  라벨이 불가능할 때만.
- **그리드 최소화** — 0-기준선만 crisp(--text, opacity ~0.55), 보조선은 opacity ≤0.06.
- **waterfall 3색 의미론**: 증가=--accent / 감소=--down / 합계=--text. 부호는 라벨에
  명시(+/−).
- **network 인접행렬** *(v7.9.17 폐기, CHART-AP-36 — 역사 기록)*: 갭 그리드(테두리 폐기) +
  관계 글리프 4종(대립 ✕ --down / 동맹 ● --accent / 영향 ▸ 방향 운반 / 연관 ○ 윤곽) +
  진영 색띠. `network` type 자체가 폐기되었으므로 본 줄은 당시 결정의 기록일 뿐 현행
  규칙이 아니다. 행위자 관계는 르포 전용 `stakeholder_map` (진영 칼럼 결정적 배치)이
  담당한다.
- 기존 §4 의 해치 패턴은 stacked_area·choropleth 등 *명목 카테고리 대면적* 에서 계속
  유효 — 폐기가 아니라 역할 정밀화다.


## 10.1 셀 수 있는 단위 어휘 (v8.6.0)

[CHART_REDESIGN_V8_6_PLAN.md](CHART_REDESIGN_V8_6_PLAN.md) §3.3 의 결정. §10 의 잉크
농도 위계를 *유지한 채*, 그 위에 "칸 하나가 정해진 수량" 이라는 어휘를 얹는다. 구현은
`src/templates/static/charts.js` 의 `// ===== v8.6.0 unit vocabulary helpers =====`
블록 (v8.6.0 정의 → **v8.6.1 에서 렌더러 13종에 배선**). 전·후 비교는
[samples/chart_redesign_v8_6_compare.html](../samples/chart_redesign_v8_6_compare.html).

**어느 조건에서 새 표현이 기본인가** (v8.6.1 — 전부 렌더러가 결정한다):
bar 는 값이 전부 정수이고 최대 500 이하면 칸, 아니면 캡슐 · line 은 40 포인트 이하이고
x 가 ISO 날짜면 일별 점 · area 는 120 포인트 이하면 세로 실선 · scatter 는 20 점 이하면
추선 · donut 은 6 조각 이하면 눈금 링 · heatmap 격자는 60 칸 이하면 둥근 칸. 조건을
벗어나면 옛 표현을 유지한다 — 판독성이 떨어지는 지점에서 렌더러가 물러선다.
덮어쓰기 옵션은 `texture`·`unit`·`orientation`·`prior`·`marks`·`fill`·`mode`·`cells`
(전부 선택. 계약 밖 값은 drop, 세로 칸 라벨 게이트만 가로 강등).

① **셀 수 있으면 칸, 아니면 캡슐.** 건수·인원·금액처럼 값이 전부 정수이고 최대값이
크지 않으면 막대를 *면* 이 아니라 *칸* 으로 그린다 (`isCountable`). 비율(%)·지수·평균
같이 나눈 값은 칸으로 세는 것이 거짓이므로 캡슐(매끈한 알약 막대)로 그린다.

② **칸의 뜻은 렌더러가 정하고 반드시 표기한다.** 한 칸이 몇인지는 `niceUnit` 이
{1, 2, 2.5, 5}×10ⁿ 중에서 칸 수가 적정해지는 최소 단위를 골라 자동 산출한다. 작성
모델은 단위를 지정하지 않는다 — 지어낸 단위가 차트에 박히는 것을 막기 위해서다
(WRITE-AP-5 의 시각물 판). 다섯 번째 칸마다 굵고 길게 그려 눈으로 세기 쉽게 한다.

③ **테마 액센트 농도 사다리 (7단) — 순위 전용, 구성은 4단.** 순위 비교(bar·lollipop·
scatter 등 항목이 5~7개인 곳)는 `[1, .78, .60, .44, .30, .22, .16]` 7단, 구성비
(donut·stacked)는 `[1, .46, .28, .16]` 4단을 쓴다. 8개 이상은 1 → .16 선형.
어느 쪽이든 **hue 는 쓰지 않는다** (§10 계승) — 위계는 오직 농도다.

> **v8.6.5 — 그 농도를 입히는 색이 바뀌었다 (사용자 지시 2026-09-03).** v8.6.1~v8.6.4
> 는 참고 자료의 *검정 잉크* 사다리를 그대로 따라 `--text` 위에 농도를 얹었는데, 우리
> 13종 테마 위에서는 회색으로만 보여 보고서 색감과 겉돌았다. 이제 **데이터 마크의 기본색은
> `--accent`** 다 — 막대 칸·캡슐·점·경로선·area 세로선·도넛 눈금 링·롤리팝 줄기·
> treemap/heatmap/calendar_heat 칸·tree 연결선·waterfall 합계·bullet 구간 띠·dot_matrix
> 채움. 사다리는 그 액센트의 `fill-opacity`/`stroke-opacity` 로만 쓴다.
>
> 바뀌지 않는 것: **축·눈금·라벨·읽는 법 캡션·그리드는 `--text`/`--muted`** · up/down
> 의미색(candle·diverging_bar 의 반대측·waterfall 감소·tension) · sankey 의 다색 팔레트
> (§10 이 인정한 예외) · pyramid 왼쪽 집단의 중립 톤 · 해치 패턴의 명목 카테고리 구분
> 규칙(선색만 액센트로 바뀐다).
>
> **§3.3 (큰 숫자에 액센트 금지) 과 충돌하지 않는다** — 바뀐 것은 *채움* 이고, 큰 숫자를
> 비롯한 모든 글자색은 여전히 `--text` 다. 액센트 글자는 §3.3 대로 차트당 1요소(보통
> 1위 값 라벨)로 유지된다.
>
> 최저 단이 `.12` → **`.16`** 으로 올라갔다. 액센트가 옅은 라이트 테마
> (editorial_cream)에서 `.12` 는 `--card` 위에서 사실상 사라졌다. 상수는 charts.js
> `inkLadder` 위의 `LADDER_MIN` 한 곳에서만 관리한다.

④ **속빈 = 이전·주말·미확정, 채움 = 이후·평일·확정.** 의미를 색이 아니라 *모양* 이
진다. 점선은 뺄셈·우회, 실선은 덧셈·본류. 다크 테마 12종에서도 형태는 그대로 읽힌다.

⑤ **읽는 법 캡션은 필수.** 칸 질감이나 형태 인코딩을 쓴 차트는 SVG 하단 중앙에 한 줄
("한 칸 = 1천억원 · 다섯 칸마다 긴 눈금", "속빈 원 = 최저 · 채운 원 = 최고")을 둔다
(`keyFooter`, 9.5px · 자간 .08em · `--muted`). 범례를 따로 두지 않기 위한 장치다.
높이 산정에 `FOOTER_H`(18)를 더한다. 장식 문구("RUNG BARS" 류)는 넣지 않는다.

⑥ **캡슐이 막대류의 공통 기본.** 막대 끝은 반원(`rx = h/2`, `capsuleRect`). 폭이
높이보다 좁으면 최소폭을 높이로 클램프해 알약 모양을 유지한다. 트랙(옅은 풀폭 배경
막대)은 두지 않는다.

⑦ **캔들 몸통도 캡슐.** 시가·종가 사이 몸통은 모서리를 둥글게, 심지는 1px. 색 규칙은
우리 `--up`/`--down` 을 유지한다 (속빈 몸통 = 상승 관례는 채택하지 않는다 — 다크 테마
12종에서 가독이 떨어진다).

**한글 라벨 게이트.** 세로 칸 막대는 라벨이 6글자 이하이고 항목이 8개 이하일 때만
쓴다. 넘으면 렌더러가 결정적으로 가로 눈금으로 강등한다 — 판단을 작성 모델에 맡기지
않는다.
