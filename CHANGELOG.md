---
tier: 3
last_synced_with: v5.3.1
ssot_for:
  - "사용자 관점 릴리스 노트 (versioned changes)"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "DEVLOG.md (개발 상세 로그)"
last_review: 2026-05-19
---

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom `vMAJOR.MINOR.PATCH` scheme tracked in `src/orchestrator.py:VERSION`.

상세한 개발 로그·트러블슈팅·인프라 메모는 [DEVLOG.md](DEVLOG.md) 참조.

---

## [v5.3.1] — 2026-05-19

### Fixed — entry 애니메이션 커버리지 (option C — bar grow + donut sweep + fill-path fade)

**배경**: v5.3.0 의 `_applyEntryAnimation` 은 *type-무관 post-process* 로
설계됐다. renderer 코드를 손대지 않고 SVG DOM 만 스캔해 path/rect/circle
3종에 generic 애니메이션을 거는 방식. 하지만 두 가지 사각이 있었음:

1. **fill 있는 path 는 전부 skip** (line/area 의 stroke-only 만 그리기).
   결과: donut arc / choropleth 국경 / sankey flow / stacked_area 레이어 /
   forecast cone / area gradient 가 모두 무애니메이션. 보고서에서 가장
   자주 등장하는 *donut* 이 거의 정적으로 보이던 원인.

2. **rect 는 opacity fade 만** (width/height 변형 X). 가로 bar 의 막대가
   "좌→우 성장" 이 아닌 "그 자리에서 어슴푸레 진해짐" 으로만 등장.

옵션 A (fill-fade 만 추가, 최소 패치) 와 B (전 renderer 모크업 이식) 중,
사용 빈도 상위 2 type 만 renderer-level 로 가져오고 나머지는 generic
확장으로 메우는 **옵션 C** 채택.

**변경**:

- `drawBar` (`src/templates/static/charts.js:318`) — 막대 rect 에 두 가지
  data 속성 부여:
  - `data-anim="bar-grow"` (대상 식별)
  - `data-final-w={barW}` (목표 폭)

- `drawDonut` (`src/templates/static/charts.js:374`) — arc path 에:
  - `data-anim="donut-arc"` + `data-start={startAngle}` + `data-end={endAngle}`
  - SVG 루트엔 `data-donut-cx/cy/ir/r` (arcGen 재구성용 geometry)

- `_animateBars(svg)` — `rect[data-anim="bar-grow"]` 의 width 를 0 으로
  되감았다가 stagger 40ms / duration 380ms 으로 final width 까지 트랜지션.

- `_animateDonut(svg)` — SVG 의 geometry 메타로 `d3.arc()` 재구성,
  `attrTween('d')` 로 각 arc 를 startAngle 위치의 zero-arc 에서 (startAngle,
  endAngle) 로 펼침. duration 680ms. 시작 프레임 깜빡임 방지를 위해
  transition 직전 d 를 zero-arc 로 동기 세팅.

- `_applyEntryAnimation` 의 path 분기 재설계 — *fill 있는* path 면 opacity
  fade-in (360ms), *stroke only* 면 기존 stroke-dashoffset 그리기. 위
  type-specific 핸들러가 처리한 tagged 요소는 skip.

- **silent 회귀 fix** — `data-orig-dasharray` 가 어디서도 set 되지 않아
  dual_line / forecast 의 점선이 애니메이션 종료 후 솔리드로 둔갑하던
  버그 해소. dashoffset 트릭 시작 전에 기존 `stroke-dasharray` 를
  `data-orig-dasharray` 에 저장해 두고 on('end') 에서 복원.

**보존**:
- CHART-AP-18 가드 (≤700ms 단일 duration, prefers-reduced-motion 즉시 정적
  폴백, IntersectionObserver 1회 재생 후 unobserve, fallback 즉시 렌더).
- 나머지 17 종 차트의 generic post-process — rect fade / circle pop /
  stroke draw 동작 무변경.

**파일**:
- `src/templates/static/charts.js` — drawBar + drawDonut 태깅, _applyEntryAnimation
  재설계 (≈+70 lines, -10 lines)
- `src/orchestrator.py:VERSION` — `v5.3.0` → `v5.3.1`
- `README.md` Status 갱신
- `CHANGELOG.md` 본 entry

---

## [v5.3.0] — 2026-05-18

### Added — FT/Economist 스타일 신규 7종 차트 + 5-Layer Usage Guarantee

**개요**: 캔들 회귀 (v5.2.0 에 추가했으나 production 13종 중 약 70% 가
bar/line/donut 으로 collapse) 의 교훈으로 두 가지를 동시 도입.

#### Part 1 — 신규 7종 차트 (FT/Economist 스타일)

기존 13종에 7종 추가. 모두 `guarded` tier 로 시작 (chart_critic 통과율 측정
후 `safe` 승격 검토).

- **scatter** — 라벨 산점도 (FT 좌측 스타일). bubble 과 구분 — size 인코딩 X.
- **stacked_area** — 시계열 누적 영역 (FT 우측 스타일). 점유율 연속 변화.
- **lollipop** — bar 의 우아한 대안. 8-15 항목.
- **slope** — 2 시점 비교, 순위 역전. 3-10 항목.
- **small_multiples** — 4-9 패널 그리드 비교.
- **waterfall** — 증감 누적 분해 (P&L brücke). 첫·끝 row `type='total'` 강제.
- **range_bar** — Dumbbell. 두 값 사이 갭 (남녀 임금격차 등).

#### Part 2 — 5-Layer Usage Guarantee (회귀 방지 안전망)

- **Layer 1** — `src/visual/usage_log.py` (신규). 보고서당 emit chart type 을
  JSONL 영구 기록. 누적 ≥10 보고서에서 0회 emit type 을 WARNING 으로 표면화.
  CLI: `python -m src.visual.usage_log analyze`.
- **Layer 2** — `narrative_composer.py:SYSTEM_PROMPT` 에 차트 type 결정 트리
  + 반-편향 가드 추가. "시계열 + OHLC → candle (LINE 금지)" 같은 negative
  constraint 로 LLM 의 line/bar default bias 차단.
- **Layer 3** — `research_director.py:_DEFAULT_REQUIRED_EXHIBITS` 의 빈 method
  채움: `fault_tree → waterfall`, `pre_mortem → scatter`. 신규 type 에 자동
  수요 부여.
- **Layer 4** — `deterministic_gate.py` 에 `chart_type_monotony` soft fail
  추가 (SOFT_FAIL_RULES 5 → 6). standard ≥3 차트 + distinct <2, deep ≥5 차트
  + distinct <3 면 DeskEditor 가 hold 받아 type 다양화 지시.
- **Layer 5** — `tests/regression/fixtures/chart_type_scenarios.yaml` (신규).
  21 시나리오 (20 차트 type + map) SSOT. `KNOWN_CHART_TYPES` 와 1:1 매칭.

#### Part 3 — Pydantic 가드 보강

`src/visual/schemas.py:_TYPE_TO_GUARD` 11 → 21 entries. 신규 7종 +
production 가드 없던 3종 (`dual_line/forecast/choropleth`) 추가.

#### Part 4 — Capability Registry 갱신

`docs/VISUAL_CAPABILITY_REGISTRY.yaml` 분포: safe 11 / guarded 10 (3→10) /
experimental 2 / 총 23 (was 16). 신규 7종 모두 `d3_custom` + `guarded`.

#### 모크업 (검토용)

`samples/chart_animation_mockup.html` — 21종 entry 애니메이션 모크업.
IntersectionObserver 트리거, motion off / ambient drift 토글. production
이식은 본 PR *제외* — 모크업으로 검토 후 별도 PR 권장.

---

## [v5.2.13] — 2026-05-18

### Fixed — 컴팩트 스트립만 나오고 풀 차트가 누락되던 회귀 (사용자 catch)

**증상**: 시계열 데이터가 충분히 fetch 된 보고서에서 *compact strip 차트만*
계속 보이고, 캔들·라인·area 같은 정식 풀 카드 차트는 누락. 사용자 노출 결함.

**근본 원인** (v5.2.5 회귀): `src/orchestrator.py:_composer_instruments` 가
strip row (role='compact') 를 *composer 가 박은 instrument 집합* 으로 인정하도록
변경됐는데 (instrument 중복 emit 회피 목적), 부작용으로:
1. composer 가 SYSTEM_PROMPT 의 "시계열 차트 1개 이상 emit 강제 규칙" 을 어기고
   풀 카드를 0 개 emit
2. `_ensure_market_strip` 이 3+ instrument 를 compact row 로 박음
3. `_composer_instruments` 가 *모든* instrument 를 covered 로 반환
4. `_ensure_time_series_chart` fallback 의 dedupe 가 모든 instrument 잘라 no-op
5. 결과: 사용자가 strip 만 봄 (풀 카드 0)

`_drop_invalid_charts` validator 가 composer 의 candle/line/area 를 silent drop 한
케이스도 동일 결과 (drop 후 풀 카드 0 → strip 만 남음 → fallback 막힘).

**Fix**:
- `_count_existing_ts_charts` (`orchestrator.py:100-117`) 가 strip row
  (role='compact') 를 제외하도록 수정. strip 의 type 도 ``line`` 이지만 sparkline
  용 다른 시각 역할 — 풀 카드 보장 판정의 분자에 포함하면 회귀가 영구화.
- `_ensure_time_series_chart` (`orchestrator.py:500-573`) 에 *풀 카드 ≥1 보장*
  안전망 추가. composer 의 유효 풀 카드가 0 이면 data 가 가장 풍부한 series 1개를
  strip dedupe 우회로 풀 카드 강제 추가. 1개만 강제 — 모든 instrument 풀 카드는
  strip 의 at-a-glance 역할과 중복돼 시각 혼잡 (v5.2.5 의 origin).

**회귀 가드** (`tests/regression/test_compact_strip.py`):
- `test_count_existing_ts_charts_excludes_compact_strip` — strip row 가 풀 카드
  카운트에서 빠지는지 lock
- `test_ensure_time_series_chart_guarantees_full_card_when_composer_emits_zero` —
  사용자 사례 재현 + 풀 카드 ≥1 보장 lock
- `test_ensure_time_series_chart_preserves_composer_full_card` — composer 가
  풀 카드 emit 했으면 fallback 이 추가 풀 카드 안 박는지 lock (시각 혼잡 방지)
- `test_ensure_time_series_chart_force_picks_data_richest` — 강제 emit 시 data 가
  가장 풍부한 instrument 선택 규칙 lock

기존 `test_composer_instruments_picks_up_compact_role` 은 그대로 유지 — strip 도
dedupe 집합에 포함하는 것 *자체는* 정합 (instrument 중복 emit 회피 의도). 이번
fix 는 그 결과로 fallback 이 막히는 *별개의* 안전망 누락만 메움.

비-시계열 차트 (donut/bar/gantt/network/bubble/heatmap/stacked/dual_line/forecast/
choropleth) 는 composer 가 직접 결정 — fallback 없음 (의도된 동작). 시계열만
fetch 된 데이터를 자동으로 다루는 v5.2.0 약속 영역.

---

## [v5.2.12] — 2026-05-17

### Changed — 모순·신호 섹션 재디자인 (`freeform_essay.html`)

보고서 말미의 두 섹션이 본문과 톤이 따로 놀던 문제 정리. 모델 (`ComposedReport.contradictions`,
`watch_signals`) 은 변경 없음 — 템플릿 레이어 단독 변경.

**모순 (`composed.contradictions`)**: 카드 + "관점 A:/B:" 라벨 + 좌측 점선 보더로
정형 박스화돼 있던 렌더 → 본문 prose 와 동일한 톤의 서술형 단락으로 변환. composer
의 4-필드 (`side_a / side_b / evidence / resolution`) 는 그대로 받되 "한쪽은 X.
반면 다른 쪽은 Y." 패턴으로 한 단락에 결합. 강조 위계 3단:
- base: `--fg-2`
- claim (충돌하는 단언): `--fg-1` + bold (`.ct-claim`)
- accent (핵심 수치): `--accent` + bold (`.ct-accent`) — 본문 `<em>` 톤과 일치
- resolution: 단락 끝에 가는 accent 좌측 보더 + Newsreader italic, "분석가의
  정리" uppercase 라벨이 자동 prefix (`.ct-resolve`)

**신호 (`composed.watch_signals`)**: 어두운 카드 (`rgba(0,0,0,0.18)` 배경 + 좌측
accent 보더) → `chart-card` 와 동일 토큰 (`--card` / `--border-light` / 10px
round / `--shadow`). 내부 구조도 차트 카드 톤:
- 제목: Noto Serif KR 14.5px (`.chart-card-title` 톤)
- `deadline`: 우측 mono accent 칩
- `indicates`: `chart-card-takeaway` 클론 — 옅은 accent 배경 + accent 좌측 보더 +
  "시사" uppercase 라벨

WRITE-AP / CHART-AP 신규 항목 없음 (회귀가 아닌 의도적 디자인 개선).

---

## [v5.2.11] — 2026-05-17

### Fixed — 가로 막대 + 간트 차트 가독성/직관성 회귀

**문제 1 — 간트 풀폭 회귀**: 같은 월(예: `2026-05-09`, `2026-05-15`, `2026-05-21`)
안의 모든 이벤트가 day-precision 무시로 동일 시점으로 collapse 되고, 그 결과
zero-duration 폴백 `+0.4` (≈5개월) 가 일제히 발동해 *모든 막대가 데이터 영역
풀폭*으로 렌더되던 회귀. composer 가 day-precision ISO 로 emit 해도 JS 가
month 단위로만 파싱하던 게 근본 원인. CHART-AP-15 가드는 모든-행 zero-duration
케이스만 잡았기에 (3 point + 1 range 같은) mixed 케이스는 통과해 회귀가 잔존.

**Fix**:
- `drawGantt.parseTime` 에 day-precision 분기 추가: `YYYY-MM-DD` 도 파싱.
  encoding `y + ((m-1)*31 + (day-1)) / 372` — month-only 입력과 호환.
- zero-duration 폴백 `+0.4` 제거. 막대 시각적 minimum 은 기존 `Math.max(6, …)`
  pixel floor 가 보장.
- axis tick 단위/포맷 자동: span ≥ 4 yr → 연도 / 0.4 ≤ span < 4 → `YYYY-MM` /
  span < 0.4 → `MM-DD`. 이전엔 `2026.4` 같은 분수 연도 라벨이라 5월/4월 직관 X.
- annotation `vline.x`/`band.x_*` 도 `parseTime` 통과시켜 day-precision 지원.

**문제 2 — 가로 막대 라벨 포맷 불일치 + 시인성**: 값 라벨이 `String(d.value)`
raw 라 `13567` 그대로 찍히는 반면 x축 tick 은 `d3.format(',')` → `13,567`.
같은 차트 안에서 *포맷 불일치*. 또 22자 이상 라벨은 무음 truncate (잘림 인지
불가) + 값 0/극소이면 막대가 0px 로 사라져 빈 행처럼 보임.

**Fix**:
- 값 포맷 통일 헬퍼 `fmt(v)` 도입 — 천 단위 separator + |v| 규모별 소수점 자동
  (≥100 정수 / ≥10 `.1f` / 그 외 `.2f`). 부호 보존. 막대 라벨 + 축 tick 양쪽에
  동일 적용.
- 라벨 22자 초과 시 ellipsis `…` 부착.
- 막대 최소 너비 `Math.max(2, x1 - x0)` floor — 0/극소값도 시각적 흔적 보장.

**Files**:
- `src/templates/static/charts.js` — `drawBar` / `drawGantt` (`parseTime` 포함)
- `src/orchestrator.py:VERSION` → v5.2.11

### Known limitations (다음 회차)
- 가로 막대 음수는 여전히 magnitude 기반 (label 에 부호만 표시). 진짜 diverging
  bar (0 기준 좌·우 양방향) 는 미지원 — `BarChartGuard` 에서 reject 하거나
  렌더 분기 추가는 별도 작업.
- 간트 `BarRow.group` 필드는 schema 에만 있고 렌더 미사용 (dead field) — 그룹별
  색 구분 미구현. 본 회차 범위 밖.

---

## [v5.2.10] — 2026-05-17

### Fixed — compact strip sparkline 가격 흐름 가독성 + sparkline 기간 라벨 노출

**문제 1 — 너무 부드러운 곡선**: compact strip 의 sparkline 이
`d3.curveMonotoneX` 베지에 보간을 써서 일간 종가 변동을 *평탄화*. 실제
가격 흐름의 jaggedness 가 시각적으로 사라져 "그냥 우상향/우하향 곡선" 으로
밖에 안 보임. 사용자 catch: "가격 흐름이 너무 부드러운 곡선으로만 보이는걸
실제 가격 흐름을 알 수 있는 라인 형태로 보완".

**문제 2 — 기간 부재**: sparkline 옆에 라벨/축이 없어 표시된 기간이
지난 24h 인지, 1W 인지, 3M 인지 알 수 없음. 사용자 catch: "조그맣게 기간을
표현해주고".

**Fix**:
- `src/templates/static/charts.js` `drawSparkline`:
  - `d3.curveMonotoneX` → `d3.curveLinear` — 일간 종가 사이를 직선 segment
    로 연결. 베지에 평탄화 제거 → 실제 가격 흐름 (변동성·반전점·급등락)
    그대로 표시. `stroke-linejoin: miter` 로 꺾임도 sharp.
  - **baseline (시작 종가) dashed line** — 옅은 0.6px dashed, opacity 0.35.
    가격이 시작 대비 어디까지 움직였는지 한눈에 보이는 zero-line. mono
    가이드 위반 없음 (line color 와 동일, 액센트 색 X).
  - **min/max 극값 dot** — 기간 내 최고/최저 close 에 1.1px dot (opacity
    0.55). 변동의 진폭을 즉시 인지.
- `src/orchestrator.py:_compact_period_label` (신규) — start/end_date 일수
  차이로 짧은 라벨 (`24H` / `1W` / `2W` / `1M` / `3M` / `6M` / `1Y` / `2Y`
  / `{n}Y`) 분류. start/end 파싱 실패 시 data 포인트 수로 fallback.
- `src/orchestrator.py:_build_compact_strip_row` — payload 에
  `period_label` 필드 추가.
- `src/templates/archetypes/freeform_essay.html` — compact-row 안에
  `<span class="compact-period">` 삽입 (change 와 spark 사이).
- `src/templates/static/charts.css` — `.compact-row .compact-period` 규칙
  (9.5px / muted / monospace / uppercase / letter-spacing 0.4). 모바일
  ≤600px 분기에서 9px 로 축소.
- `tests/regression/test_compact_strip.py` — 6 신규 회귀: 버킷 정확도 +
  fallback + payload field + template span + CSS 규칙 + curveLinear lock.

**영향**: 시계열 instrument 3개↑ 보고서 (자동 trigger) 의 strip sparkline
시각이 즉시 변경. 풀 차트 / 본문 문체 / VM 운영 절차 무영향.

---

## [v5.2.9] — 2026-05-17

### Refactored — 본문 문체 SSOT 통합 + persona 채널 폐기 + dead persona 7개 모듈 청소

**문제**: composer (`src/agents/narrative_composer.py:SYSTEM_PROMPT`) 와
context (`src/agents/context_analyst.py:SYSTEM_PROMPT`) 사이에 문체·어휘
규칙이 *3중 중복* 되어 있었음. 또한 v4.3.0 의 `recommended_persona` dict
채널은 context 가 "디폴트 그대로 권장" 으로 emit 하고 composer 가 "느슨하게
적용 / 영감용" 으로 받아 *사실상 dead channel*. 더해서 음슴체 (context) vs
평어체 (composer) 의 어조 충돌 위험. 마지막으로 v4.0.0 부터 호출되지 않던
dead persona 7개 agent 모듈이 5년 가까이 보존되어 있었음.

**변경**:
- **본문 문체 SSOT 신설** — [docs/REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md)
  를 v5.2.9 부터 *보고서 본문 문체 SSOT* 로 재포지셔닝 (이전엔 abhinavbwj
  기반 색·타이포·레이아웃 가이드, v4.5.0 부터 stale). 색·타이포는
  [MONO_THEME_GUIDE.md](docs/MONO_THEME_GUIDE.md) 로 위임.
- **persona dict 채널 폐기**:
  - `src/models.py:ContextAnalysis.recommended_persona` 필드 삭제
  - `src/state/models.py` 의 `EvidencePack.recommended_persona`,
    `AnalysisBrief.recommended_persona` 필드 삭제
  - `src/state/compaction.py`, `src/agents/research_director.py` 의 persona
    복사·기본값 라인 삭제
  - `src/agents/context_analyst.py:SYSTEM_PROMPT` 의 "페르소나 권장" 섹션
    + JSON 출력 스키마 안의 `recommended_persona` 필드 삭제. "출력의 위치"
    섹션 신설 — "당신 출력은 내부 분석 메모. composer 가 평어체 본문으로
    재작성한다" 명시 (음슴 vs 평어 충돌 해소).
  - `src/agents/narrative_composer.py:SYSTEM_PROMPT` 의 "페르소나 적용"
    섹션 + `_build_payload` 의 `payload["persona"]` 주입 삭제
- **본문 문체 톤 온건화** (사용자 요청 — "지금보다 평이/친절/덜 극적"):
  - 수사적 질문 *1 섹션당 1~2회* → *보고서당 0~1회*
  - lede 예시 교체: "35년의 봉인이 한 번에 풀렸다 / 무대 위에 올랐다" 같은
    극적 톤 → "9월 27일, 미국은 베르베라항 사용권 확보를 공식 발표했다.
    35년 만의 외교 신호다." 같은 평이한 톤
  - 신문 표제어 ban 리스트 신설 (봉인 / 무대 위에 / 변곡점 / 거대한 파장 /
    격동의 / 운명의 / 칼끝 / 풍전등화 / 백척간두 / 일촉즉발)
  - 보수 표현 의무화 — 추정·예측 영역에서 "~로 보인다 / ~할 가능성"
  - editorial 컴포넌트 빈도 (lede / analogy / fact_grid / dropcap /
    pull_quote / kicker) 전부 절제 방향으로 가이드 통합
- **dead persona 7개 모듈 + 그 테스트 삭제**:
  - `src/agents/{player,dynamics,chain_reaction,scenario,visual,
    quality_inspector,synthesis_judge}_analyst.py` 또는 `_judge.py` 7개 파일
  - `src/tests/test_quality_gates.py` (QualityInspector/SynthesisJudge 테스트)
  - `src/orchestrator.py` 의 7개 import + 인스턴스화 + `_wire_telemetry`
    의 list iteration 정리
  - `src/agents/__init__.py` 의 deprecated 7종 + lens 별칭 3종 export 정리
- **dead flag 6종 삭제** — `src/token_budget.py` 의
  `use_llm_quality_gate / use_llm_narrative_plan / use_llm_executive_summary /
  use_llm_visuals / use_llm_synthesis / use_legacy_personas`. v4.0.0 부터 모든
  mode 에서 False 였고 호출하던 agent 가 삭제됨. `allow_meta_lenses` 는
  `lens_policy` 가 검사하므로 보존. `src/tests/test_token_optimization.py`
  의 dead flag assertion / `TestDeprecatedPersonasGated` /
  `TestSynthesisJudgeGating` 블록 삭제.
- **사용자 노출 문구 일반화** — `src/telegram_bot.py:286` 의 "ScenarioArchitect 의
  watch_signals" → "보고서의 watch_signals" (dead agent 이름 사용자 노출 제거).

**영향**:
- 보고서 본문 톤이 신문 칼럼 흉내에서 *친절한 편집자의 차분한 설명* 으로
  shift. 극적 형용사·수사적 질문·editorial 컴포넌트 빈도 모두 절제됨.
- 어휘·어조 규칙이 한 곳 ([REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md))
  에 모임. 향후 문체 변경은 SSOT 한 곳만 손대면 됨 (anti-pattern #1 해소).
- 코드베이스 ~2000 줄 감소 (dead agent + dead test + dead flag).
- 호출 경로 변경 없음 — composer 와 context 의 입력/출력 형태는 그대로,
  단지 persona 필드 하나가 사라짐 (downstream 코드 미사용).

---

## [v5.2.8] — 2026-05-17

### Fixed — compact-strip 이 데스크탑/태블릿에서 본문 좌우를 넘어가던 회귀

사용자 보고: 콤팩트 스트립 차트가 데스크탑·태블릿 뷰포트에서 보고서 본문
(`.container` max 960px) 의 좌우 폭을 **넘어서서** 렌더링.

- **원인**: v5.2.5~v5.2.7 의 `.compact-strip` 이 의도적으로 break-out —
  `width: min(1100px, calc(100vw - 48px))` + `position: relative; left: 50%;
  transform: translateX(-50%)` 로 본문 폭을 escape 해 viewport 폭까지 확장.
  당시엔 모크업(1200px wrap)의 시각 정합 우선이었으나 사용자 시점에선
  본문과 분리된 폭이 부자연스러움.
- **수정**: break-out 제거 → `width: 100%; max-width: 100%;
  box-sizing: border-box` 로 본문 폭에 conform. grid `repeat(3, ...)` →
  `repeat(2, ...)` 으로 desktop/tablet 공통 2-col. 920px 미디어쿼리 분기
  삭제 (base 가 이미 2-col). 모바일(≤600px) 1-col stack 은 유지.
- **차트 수 가변 처리**: 2-col grid 의 자연 wrap — 3개 → 2x2 (마지막 1셀),
  5개 → 2x3 (마지막 1셀), 7개 → 2x4 (마지막 1셀) 등. odd N 의 마지막 왼쪽
  셀은 `:last-child` 로 separator 자동 제외.
- **세로 구분선**: nth-child(3n) → nth-child(2n) 기준으로 재배치.
- **회귀 가드**: `tests/regression/test_compact_strip.py` 의
  `test_compact_strip_css_breaks_out_of_narrow_container` 를
  `test_compact_strip_css_stays_within_container_width` 로 반전 + 신규
  `test_compact_strip_css_two_column_grid_on_desktop_tablet` 추가.
  16/16 통과.

---

## [v5.2.7] — 2026-05-16

### Fixed — 시계열 차트 takeaway 가 모든 차트에서 동일 + 소수점에서 절단되던 회귀

사용자 보고 (`analysis_20260516_230827`): DXY 차트의 takeaway 가
`"미국 10년물 국채 금리가 5월 15일 4"` 로 표시 — ① DXY 차트인데 미국채
얘기 (모든 시계열 차트가 같은 takeaway), ② 중간에서 끊김.

- **원인**: `src/orchestrator.py:_format_ts_takeaway` 가
  `context.summary.split(".")[0]` 을 1순위로 반환. 두 회귀 동시 유발:
  ① `context.summary` 는 보고서 전역 1개라 모든 차트가 같은 문장,
  ② `"4.52%"` 의 `.` 에서 split 되어 `"4"` 까지만 추출.
- **수정**: 전역 summary 경로 *제거*. 데이터 기반 결정적 takeaway 로 단일화 —
  `{instrument} 기간 중 {lo}~{hi} 사이 {상승/하락/횡보} — 마지막 {last}
  ({±N.NN}%), 변동폭 {N.N}%`. 차트마다 instrument + data 다르므로 자연히
  per-chart 차별화. 소수점 split 같은 절단 경로 없음.
- **기존 보고서 retro-fix**: `scripts/patch_report.py` 에
  `--regenerate-ts-takeaways` 플래그 추가. 시계열 차트 (line/area/candle) 의
  takeaway 만 새 로직으로 재계산 (LLM 호출 X). composer-emitted 비-시계열
  (network/donut/gantt) 은 건드리지 않음.
- **회귀 가드**: `tests/regression/test_ts_takeaway.py` 신규 — 소수점 절단 /
  차트별 차별화 / direction & range 키워드 / candle close 필드 / summary
  독립성 6종 검증.

### 사용법 (배포된 보고서 retro-fix)

```bash
# 예: analysis_20260516_230827 의 takeaway 재생성 + 재배포
python scripts/patch_report.py 20260516_230827 --regenerate-ts-takeaways
```

---

## [v5.2.6] — 2026-05-16

### Fixed — 달러인덱스(DXY) 가 ICE 가 아닌 Fed Broad TWI 를 가져오던 회귀

사용자 보고 (`analysis_20260516_230827`): 달러인덱스 차트가 `117.54 → 118.04`
로 표시 — 시장 통념의 DXY (최근 99~110) 와 ~15~20pt 어긋남.

- **원인**: `src/tools/market_fetcher.py:INSTRUMENT_REGISTRY["DXY"]` 가
  FRED 시리즈 `DTWEXBGS` (Nominal Broad U.S. Dollar Index, 2006-01=100,
  26개국 가중 — CNY·MXN 비중 큼, 최근 117~125 레인지) 를 가져와 "달러인덱스"
  로 라벨링. 시장에서 통용되는 DXY 는 **ICE U.S. Dollar Index**
  (1973-03=100, EUR 57.6 / JPY 13.6 / GBP 11.9 / CAD 9.1 / SEK 4.2 /
  CHF 3.6 6-통화 고정 바스켓, 최근 99~110 레인지) 로 완전히 다른 지수.
  FRED 무료 API 엔 ICE DXY 가 없음 (ICE 독점) — 가장 가까웠던 `DTWEXM`
  (Major TWI) 도 2019-12 단종.
- **수정**: DXY 라우팅을 Yahoo Finance 의 `DX-Y.NYB` 티커 (ICE U.S. Dollar
  Index 의 표준 Yahoo 심볼) 로 교체. `_TYPE_TO_GUARD` / chart_type 변경 없음
  (계속 line). Yahoo 인프라는 이미 v5.2.1 부터 코스피 (`^KS11`) / 코스닥
  (`^KQ11`) 용으로 가동 중이라 추가 의존성 없음.
- **회귀 가드**: `tests/test_market_fetcher.py:test_dxy_routed_to_yahoo_ice_ticker`
  추가 — `DTWEXBGS` 회귀 차단 + `DX-Y.NYB` 명시.
- **기존 보고서 영향**: `analysis_20260516_230827` 의 117.54 → 118.04 수치는
  DTWEXBGS 입장에선 올바른 값이지만 "달러인덱스" 라벨이 잘못됐던 것. 신규
  보고서부터 진짜 ICE DXY 값으로 표기. 기존 배포된 HTML 은 retroactive 패치
  불가 — 사용자가 동일 사건을 재분석하면 갱신됨.

---

## [v5.2.3] — 2026-05-15

### Fixed — KOSPI 보고서 (analysis_20260515_230117) 차트 렌더링 4건 결함

사용자 보고: 코스피 line 차트의 영역(area) fill 그라데이션 누락 / 차트가 좌측
치우침 / 우측 끝 값 라벨이 부동소수점 그대로 노출 ("7493.180175125") /
3개 차트(코스피·삼성전자·SK하이닉스) 가 동일한 1-5 번호 마커와 동일한 풋노트.

- **`src/templates/static/charts.js` `drawLine`** — area fill 을 단색
  (`fill: t.accent, fill-opacity: 0.10`) 에서 `linearGradient` (상단 alpha 0.28
  → 하단 0.02) 로 교체. `drawArea` 의 그라데이션 정의와 동일 패턴 — 두 함수
  시각 언어 일관성 회복. (결함 #1)
- **`src/templates/static/charts.js` `drawLine`** — `computeZones` 의
  `right: 110 → 70`, `scalePoint` 의 `padding: 0.1 → 0.04`. 우측 110px 가
  빈 채로 남아 차트가 왼쪽 치우치는 인상을 주던 현상 해소. `placeEndLabel`
  후보 위치들이 좌측으로도 떨어질 수 있어 110 은 과도. (결함 #2)
- **`src/templates/static/charts.js` `drawLine`** — `placeEndLabel(...
  String(last.y) ...)` 의 raw float 전달 → `Math.abs(lastY) >= 1000` 이면
  `d3.format(',.0f')` 로 정수 천단위, 그 외엔 `d3.format(',.2f')` 로 소수
  2자리. Y 라벨 포맷 규칙과 일치. (결함 #3)
- **`src/orchestrator.py` `_attach_event_markers`** — `instrument` 매개변수
  추가. `context.timeline` 전체를 모든 차트에 균등 부착하던 v5.2.2 회귀
  수정. 차트별 필터링 규칙:
  - 지수/벤치마크 차트 (코스피·코스닥 등) → 모든 이벤트 흡수
  - 자기 instrument 이름 명시된 이벤트 → 부착
  - 어떤 instrument 도 명시 안 된 일반 시장 이벤트 → 개별 자산 차트도 흡수
  - 그 외 (다른 instrument 가 명시된 이벤트) → 스킵
  - `instrument=""` 면 종전 동작 (모든 이벤트 통과) — backward-compat.
- **`src/orchestrator.py:VERSION`** `v5.2.2 → v5.2.3`.

### Added — 기존 보고서 소급 패치 스크립트 (`scripts/patch_existing_reports.py`)

v5.2.2 에서 이미 생성·배포된 보고서를 LLM 재호출 없이 v5.2.3 결함 해소 상태로
끌어올리는 일회용 도구. 두 단계 동시 처리:

1. `reports/charts.js` 를 v5.2.3 의 `src/templates/static/charts.js` 로 덮어쓰기
   → 결함 #1/#2/#3 (drawLine 로직) 즉시 해소.
2. `reports/analysis_*.html` 안의 `<script class="chart-payload-inline">`
   inline JSON 의 `data[].event` 필드를 instrument-aware filter 로 재계산
   → 결함 #4 (모든 차트 동일 1-5 사건) 해소.

원본은 `*.bak` 로 idempotent 백업. 운영자가 결과 확인 후 `wrangler pages deploy`
로 재배포. 사용법은 docstring 또는 DEVLOG v5.2.3 §"기존 보고서 소급 패치" 참조.

### Notes

- chart_gate / chart_critic / market_fetcher 미변경.
- 데이터 모델 변경 없음.
- charts.js 의 `drawArea` 는 이미 linearGradient 사용 중이라 변경 불필요 —
  이번 회귀는 `drawLine` 단독.
- 별도 스크립트 `scripts/patch_report.py` (ComposedReport JSON → ReportSynthesizer
  재렌더) 와 `scripts/patch_existing_reports.py` (HTML inline JSON 직접 패치)
  는 다른 용도로 공존. 후자가 더 가벼움 — composer JSON 보존 안 된 보고서에도
  적용 가능.

---

## [v5.2.2] — 2026-05-15

### Enhanced — `_ensure_time_series_chart` hook 을 mockup 수준 quality 로 보강

사용자 피드백: "차트는 적극적으로 박혀도 되지만, *mockup 수준의 정합성과 시인성*
은 필수." 이전 v5.2.1 hook 은 단순한 fallback 형태 (제목 "코스피 시계열", 이벤트
마커 없음, takeaway 없음) — 보고서 quality 가 mockup 보다 낮음. 이번 강화로 hook
이 생성하는 차트도 mockup 과 동일 시각화 정합성 확보.

**시그니처 변경**: `_ensure_time_series_chart(composed, time_series: list)`
→ `_ensure_time_series_chart(composed, context: ContextAnalysis)` —
timeline / summary 접근 위해 context 전체 받음. `patch_report.py
--ensure-time-series` 호출처도 갱신.

**적극 모드** (사용자 요청): composer 가 일부 instrument 만 emit 하고 나머지
빠뜨린 경우, hook 이 *모든 누락 instrument 를* 차트로 추가. composer 가 박은
instrument 는 제목 매칭으로 detect → skip (중복 회피).

### 차트 quality enhancement (5종)

1. **이벤트 마커 자동 부착** — `_attach_event_markers` 신규. context.timeline
   의 각 event 의 date 와 series.data row 의 date 매칭 → row 에 `event`
   필드 부착. charts.js 가 *자동으로* 번호 배지(❶❷❸) + 하단 footnote 렌더.
   mockup 의 핵심 시각 정합성.
2. **사용자 친화 title** — `_format_ts_title`:
   · Yahoo 지수 → "코스피 종합지수" / "코스닥 종합지수"
   · KRX 개별주 → "삼성전자 (005930)" / "SK하이닉스 (000660)"
   · 그 외 → instrument 이름 그대로
3. **변화율 명시 subtitle** — `_format_ts_subtitle`:
   "2026-04-15 ~ 2026-05-15 · -4.75% (284,000 → 270,500)" 형태. 사용자가
   차트 보지 않고도 *수치적 narrative* 파악.
4. **자동 takeaway** — `_format_ts_takeaway`:
   · 1순위: `context.summary` 첫 문장 (≤100자)
   · 2순위 (summary 없으면): 변동성 기반 — "기간 중 최고 X · 최저 Y — 변동폭 Z%"
5. **출처 표기** — `_format_ts_source`:
   "Yahoo Finance / 2026-04-15 ~ 2026-05-15 · 일간" — source / period / frequency
   3중 명시.

### 회귀 테스트 14건 추가 (기존 8건 갱신 + 6건 신규)

- mockup 품질 검증 — title / subtitle / source / takeaway / event markers
- 적극 모드 검증 — composer 가 일부 instrument 만 emit 했을 때 누락분 보충
- composer 가 같은 instrument 박았으면 중복 회피
- 후보 우선순위 (data 많은 순)
- 모든 no-op edge case (timeline 없음 / data 없음 / sections 없음)

전체 **119/119 통과** (test_market_fetcher 29 + test_chart_correctness 54 +
test_composed_section_guard 36).

### Notes

기존 보고서 `20260515_230117` 복구: `patch_report.py --ensure-time-series`
호출 시 새 quality 적용 (이벤트 마커 + 한국어 title + subtitle 변화율 등).

---

## [v5.2.1] — 2026-05-15

### Fixed — composer 가 available_time_series 무시하는 case C 회귀

20260515_230117 보고서 ("삼성전자·SK하이닉스 동반 급락 — 코스피 8000 사상 첫
돌파 직후 6% 폭락") 진단 결과:
- ContextAnalyst: `['코스피', '삼성전자', 'SK하이닉스']` 정상 emit
- orchestrator: 3 종목 모두 61 bars 실 OHLC fetch
- **composer LLM**: `available_time_series` payload 받았지만 *시계열 차트 0개* —
  대신 bar / donut / bubble (사건성 차트) 만 emit. 변동성 narrative 인데 핵심
  시각화 누락.

원인: v5.2.0 의 composer SYSTEM_PROMPT 가 "데이터 있다고 무조건 차트 만들지
말 것" 룰로 너무 보수적. LLM 이 차트 안 만들어도 되는 신호로 해석.

### Added — orchestrator 결정적 안전망 + composer prompt 강화

- **`src/orchestrator.py:_ensure_time_series_chart`** 신규 — composer 호출 직후
  실행. composer 가 시계열 차트 0개 emit 했고 `time_series` 데이터는 있을 때,
  가장 data 많은 series 를 그 series 의 `chart_type` 으로 변환해 sections[0].
  charts[0] 에 자동 삽입. composer 가 1개 이상 박았으면 no-op.
- **`src/agents/narrative_composer.py:SYSTEM_PROMPT`** 시계열 차트 섹션 강화:
  · "★ 강제 규칙 (v5.2.0+, 예외 없음)" 표기로 명시성↑
  · "available_time_series 가 비어있지 않으면 *반드시 최소 1개* 시계열 차트
    emit. 0개 emit 절대 금지" 룰 도입
  · 사건성 보고서 (변동·급등·급락·폭락 narrative) 는 관련 instrument *전부*
    차트로 (한 종목만 emit 하고 나머지 빠뜨리는 것 금지)
  · 차트 type 매핑 (지수=line / 개별주=candle / 원자재=area) 명시
  · "데이터 있다고 무조건 차트 만들지 말 것" 룰은 v5.2.0 이전 거로 명시 정정
- **`scripts/patch_report.py:--ensure-time-series`** 옵션 신규 — 기존 보고서를
  사후 복구. orchestrator 의 `_ensure_time_series_chart` 헬퍼 재사용. 회귀
  보고서 (20260515_230117 같은) 복구용.

### Added — 회귀 테스트 8건 (tests/regression/test_composed_section_guard.py)

- `test_ensure_ts_chart_adds_when_composer_skipped` — case C 회귀 가드
- `test_ensure_ts_chart_noop_when_composer_already_emitted` — 1개 이상이면 no-op
- `test_ensure_ts_chart_noop_when_no_time_series` — 데이터 없으면 no-op
- `test_ensure_ts_chart_noop_when_time_series_data_empty` — 빈 data 만이면 no-op
- `test_ensure_ts_chart_noop_when_no_sections` — sections 없으면 no-op
- `test_ensure_ts_chart_respects_chart_type_for_candle` — OHLC shape 보존
- `test_ensure_ts_chart_maps_xy_for_line` — line/area 는 {x,y} 형태로 변환
- `test_ensure_ts_chart_picks_most_data_rich_series` — 후보 다중일 때 우선순위

전체 109/109 통과.

---

## [v5.2.0] — 2026-05-15

Market Data Fetcher + 시계열 차트 (candle/area) + chart_gate production wiring +
mode-aware period + drawLine 이벤트 마커 통일. 본 릴리스로 CHART-AP-15/16 의
근본 원인 (시계열 데이터 부재 + 가드 비활성) 둘 다 해소. composer 가 같은 실수
해도 가드 자동 차단, 진짜 OHLC 로 차트 emit.

운영자 단계: VM 에 `pip install pykrx yfinance` + `.env` 에 `FRED_API_KEY` /
`ECOS_API_KEY` 추가 + 봇 재시작. 다음 보고서부터 코스피·삼성전자·DXY·국고 10Y·
미국채 1Y·WTI 등 실 OHLC 자동 차트 emit. `python scripts/verify_market_fetcher.py`
로 봇 재시작 전 안전망 검증.

### Fixed — chart_gate production wiring (CRITICAL)

이전엔 `run_chart_gate` / `validate_chart_data` 가 정의만 있고 production
경로에서 *호출 안 됨* (V5 Phase 6 flag 디폴트 OFF 때문). CHART-AP-15/16 가드
모두 dormant 상태였음 — composer 가 위반 차트 emit 해도 그대로 통과.

- **`src/models.py:ComposedSection._drop_invalid_charts`** — Pydantic
  `@model_validator(mode="after")` 신설. composer JSON 파싱 직후 *디폴트 ON* 으로
  각 차트 dict 에 `validate_chart_data` 호출. 위반 차트만 silent drop + warning
  log. 합법 차트는 절대 안 건드림. validator 자체 raise 도 차트 보존 (composer
  토큰 12~32K 비용 회피).
- **`tests/regression/test_composed_section_guard.py`** — 신규 17건 회귀 테스트.
  AP-15/16 의 실제 회귀 케이스 + 합법 차트 보존 + edge cases.

### Added — drawLine 의 이벤트 마커 통일 (Bloomberg/FT 스타일)

기존 `drawLine` 의 inline event 는 *점선만* 그리고 라벨 X — 어떤 이벤트인지 알
수 없었음. v5.2.0 에서 candle/area 에 도입한 번호 배지 + footnote 패턴을 line
에도 적용 (3 type 일관 스타일).

- **`src/templates/static/charts.js:drawLine`** — `data.filter(d=>d.event)`
  의 legacy dotted-line 만 그리던 블록을 `_renderEventBadgesAndFootnote`
  호출로 교체.

### Added — Mode-aware period 선택

market_fetcher 가 받는 fetch 기간을 사건/리포트 성격으로 분기:

- **`src/orchestrator.py:_select_market_period`** — 헬퍼 신설.
  daily briefing 키워드 (간밤/어제/오늘 등) → "1M",
  historical 키워드 (IMF/외환위기/10년 만에 등) → "3Y",
  기본 → "3M" (사건 보고서 event-anchored ±30일).

### Added — KRX ISIN 동적 lookup

기존 `_ISIN_MAP` 은 삼성전자/SK하이닉스 2개만 하드코딩. 사용자가 다른 종목
mention 하면 fetcher 가 빈 결과 반환했음. KRX search endpoint 로 동적 조회.

- **`src/tools/market_fetcher.py:_lookup_isin`** — KRX `finder_stkisu` POST 로
  6자리 코드 → ISIN 동적 조회. 결과는 `_ISIN_MAP` cache 에 자동 저장.
  하드코딩 seed 도 NAVER/카카오/현대차/LG화학/삼성SDI/삼성바이오 추가 (8 종목).

### Added — 운영 검증 스크립트

- **`scripts/verify_market_fetcher.py`** — `.env` 의 키로 6 종목 1M fetch 시도.
  ✅/❌ 표시 + 빈 응답 사유. 봇 재시작 *전* 키 검증용. pykrx/yfinance 설치 상태도 표시.

### Fixed — KRX 우회 (pykrx + Yahoo Finance 하이브리드)

운영 환경 verify 에서 두 차례 KRX 이슈 발견 → 단계적 해결.

- 1차: `src/tools/market_fetcher.py:KRXFetcher` 가 aiohttp 직접 POST → 모든
  KRX 종목이 `HTTP 400 LOGOUT` 으로 실패. warm-up GET 추가해도 미해결.
- 2차: **pykrx 로 전환** — 한국 거래소 scraping 표준 라이브러리. 개별주
  (삼성전자/SK하이닉스) 정상 fetch. requirements.txt 에 `pykrx>=1.0` 추가.
- 3차: pykrx 의 *지수* endpoint (`get_index_ohlcv`) 가 OTP 인증 우회 실패 →
  KOSPI/KOSDAQ 만 **Yahoo Finance** (`yfinance`) 로 우회 (`^KS11` / `^KQ11`
  ticker 무인증 안정). 개별주는 pykrx 그대로. requirements.txt 에 `yfinance>=0.2.40`
  추가. `INSTRUMENT_REGISTRY` 의 KOSPI/KOSDAQ source `'KRX'` → `'YAHOO'`.
- 데이터 정합 검증 — pykrx ↔ Yahoo cross-check 로 OHLC/거래량 byte-equal 확인
  (운영자 매뉴얼 검증).

---

### Added — 시계열 데이터 파이프라인 (B 안)

ContextAnalyst LLM 이 본문에서 다루는 금융 instrument 를 ``instruments_mentioned``
로 emit → orchestrator 가 KRX / FRED / ECOS 에서 실 OHLC fetch →
``ContextAnalysis.time_series`` 에 저장 → composer 가 line / candle / area
차트로 emit. 가짜 데이터 / 추정값 차트 회귀 (CHART-AP-15/16 의 근본 원인) 해소.

- **`src/tools/market_fetcher.py`** (신규) — FRED / ECOS / KRX 3 fetcher 통합.
  `INSTRUMENT_REGISTRY` 11 종목 (코스피·코스닥·삼성전자·SK하이닉스·DXY·UST 1Y/10Y·
  WTI·금·국고 10Y·원/달러). `resolve_instrument(query)` 한국어 alias 매칭.
  `fetch_market_series` / `fetch_many` async API. graceful degradation —
  API key 없으면 빈 series + warning log (보고서 진행).
- **`src/models.py`** — `ContextAnalysis.instruments_mentioned`, `time_series`
  필드 신설.
- **`src/agents/context_analyst.py`** — SYSTEM_PROMPT 에 `instruments_mentioned`
  emit 가이드 추가 (지원 종목 + 규칙 명시).
- **`src/orchestrator.py`** — Phase 1 직후 market_fetch hook. 사건 일자 anchor +
  3M 기본 기간 + 병렬 fetch. fetch 실패해도 보고서 흐름 영향 X.
- **`src/agents/narrative_composer.py`** — composer payload 에 `available_time_series`
  포함 + SYSTEM_PROMPT 에 "시계열 차트 데이터는 반드시 fetched series 만" 규칙.
- **`src/config.py`** — `FRED_API_KEY` / `ECOS_API_KEY` / `KRX_API_KEY` 환경변수.
- **`.env.example`** — 3 키 자리 + 발급 링크.

### Added — Candle / Area 차트 type

`charts.js` 의 11 type 에서 13 type 으로. 두 신규 type 은 시계열 OHLC 차트
전용이며 *반드시 market_fetcher 데이터로만 emit* (composer 가 추정 금지).

- **`src/templates/static/charts.js`** — `drawCandle` (OHLC body + wick, accent=bull
  outline / down=bear fill) + `drawArea` (line + gradient) 신규. 공통 헬퍼
  `_renderEventBadgesAndFootnote` — Bloomberg/FT 풍 번호 배지 (상단 same-Y +
  가로 cascade + leader line) + HTML footnote (`.chart-card-footnote` 안).
- **`src/templates/static/charts.css`** — `.chart-card-footnote` / `.chart-note-row`
  / `.chart-note-num` / `.chart-note-date` / `.chart-note-text` 토큰.
- **`src/visual/schemas.py`** — `CandleChartGuard` (data ≥2 + OHLC 순서 일관성
  low≤open≤high / low≤close≤high) + `AreaChartGuard` (line 과 동일 + finite).
  `_TYPE_TO_GUARD` 에 등록.
- **`tests/regression/test_chart_correctness.py`** — Candle / Area 가드 회귀 9건.
- **`tests/test_market_fetcher.py`** — 파서·라우팅·graceful degradation 25건 (모킹 only).

### Notes

- `enable_visual_planner` 등 V5 flag 와 *독립적* — 디폴트 ON. fetcher 는 API key
  유무로만 분기. 봇 운영자가 `.env` 에 키 추가 → 다음 보고서부터 자동 작동.
- 이번 commit 으로 CHART-AP-15 (gantt zero-duration) / CHART-AP-16 (donut 2-segment)
  의 *근본 원인* (= 시계열 데이터 부재로 composer 가 부적합 차트 선택) 해소.

---

### Fixed — donut 2-segment 빈 카드 + gantt zero-duration 빈 차트 회귀

20260515_125106 보고서 ("코스피 8000 돌파") 에서 2건의 차트 type 선택 회귀
사용자 보고. 둘 다 *데이터 결함이 아니라 type 선택 결함* — composer 가
부적합한 type 을 골랐고 가드 인프라가 못 잡음.

- **CHART-AP-15** (gantt zero-duration emit): "2026년 5월 코스피 8000 돌파
  타임라인" gantt — 7개 row 중 6개가 `start == end` (point-in-time 이벤트 모음).
  본질이 *event sequence* 이지 *duration timeline* 이 아니어서 gantt 부적합.
  `GanttGuard.validate_durations` 신규 — zero-duration ratio > 70% 면 reject.
- **CHART-AP-16** (donut 2-segment 안티패턴): "외국인 5월 누적 순매도 구성"
  donut — `[{반도체:16.8}, {비반도체:3.4}]` 2 segment. "비반도체" 잡탕 segment
  로 정보 손실 + subtitle 이 같은 비율(83%) 이미 전달 + 렌더러 (`drawDonut`)
  가 `< 3` 이면 silent return 해서 *제목·부제만 보이는 빈 카드*로 회귀.
  `DonutGuard.validate_segment_count` 신규 — segment < 3 이면 reject.

**수정**:
- `src/visual/schemas.py` — `DonutGuard` `min_length=2 → 1` + `validate_segment_count`,
  `GanttGuard` + `validate_durations`.
- `src/agents/narrative_composer.py:SYSTEM_PROMPT` donut / gantt spec 행에
  AP-15 / AP-16 명시.
- `docs/CHART_RENDERING_ANTIPATTERNS.md` AP-15, AP-16 append + `last_synced_with`
  → v5.1.2 + "누적 16개" 갱신.
- `CLAUDE.md` Anti-Patterns (차트 렌더링) 섹션 16개 패턴 / AP-15, AP-16 라인 추가.
- `tests/regression/test_chart_correctness.py` 회귀 테스트 4건 추가.
- 기존 보고서는 `scripts/patch_report.py 20260515_125106 --remove-chart 2:0
  --remove-chart 4:0` 로 일회성 정리 (LLM 호출 0).

---

## [v5.1.2] — 2026-05-14

### Changed — Daily Briefing 기본 트리거 시각 07:30 → 06:00 KST

`DAILY_BRIEFING_TIME` 디폴트를 `"07:30"` 에서 `"06:00"` 으로 조정. 시장 개장
(09:00 KST) · 외교 일정 시작 전에 더 일찍 노출하기 위함. 운영 중인 환경에서
`.env` 의 `DAILY_BRIEFING_TIME` 으로 override 한 경우 영향 없음 (env 우선).

**수정**:
- `src/config.py` `daily_briefing_time` Field default `"07:30" → "06:00"`.
- `src/scheduler/daily_briefing.py` `run_daily_briefing_loop(time_str=...)`
  default `"07:30" → "06:00"` + `_build_briefing_prompt` 안내 docstring 동기화.
- `.env.example` `DAILY_BRIEFING_TIME=07:30 → 06:00`.
- 문서 (`README`, `WORKFLOWS`, `GOAL`, `docs/ARCHITECTURE`, `docs/REPO_MAP`) 의
  "기본 07:30 KST" 표기 동시 갱신. v5.1.0~v5.1.1 의 출시 디폴트는 GOAL 의
  REQ-V5-101 노트에 명시 (히스토리 보존).
- `src/orchestrator.py:VERSION` `v5.1.1 → v5.1.2`.

### Notes

- 기능·구조 변경 없음 — 단일 디폴트 상수 조정. 스케줄러 task / DB 스키마 /
  텔레그램 명령 / 프롬프트 본문은 모두 그대로.
- 실행 중인 봇은 재기동 후 다음 트리거가 06:00 으로 잡힘. `/briefing_status`
  로 시각 확인 가능.

---

## [v5.1.0] — 2026-05-13

### Added — 자동 일일 브리핑 시스템

매일 지정 시각 (기본 07:30 KST) 에 "간밤 산업·지정학·정치·전쟁 이슈" 심층 보고서를
자동 생성·배포·텔레그램 송신. 별도 cron / systemd timer 없이 봇 프로세스 안 asyncio
task 로 동작 (watchlist monitor 와 동일 패턴).

**신규 모듈** `src/scheduler/`:
- `subscriptions.py` — `BriefingSubscriberRegistry` (SQLite CRUD; 구독 + 실행 이력)
- `daily_briefing.py` — `run_daily_briefing_loop()` background task + `_next_trigger()`
  / `_build_briefing_prompt()` 순수 함수
- `db_schema.sql` — `briefing_subscribers` + `briefing_runs` 두 테이블
  (`run_date` PRIMARY KEY 로 같은 날 중복 트리거 방지)

**신규 텔레그램 명령**:
- `/briefing_on` — 이 채팅을 일일 브리핑 수신처로 등록 (mode='deep' 고정)
- `/briefing_off` — 구독 해제
- `/briefing_status` — 구독 상태 + 스케줄러 활성 여부 + 시각/타임존 표시

**신규 환경변수** (`Config` 에 `AliasChoices` 패턴으로 추가):
- `DAILY_BRIEFING_ENABLED` — 디폴트 `false`. task 는 항상 살아 있고 구독은 받지만,
  트리거 시각에 실제 분석 실행 여부를 게이트. `false` 시 스킵 + 로그만.
- `DAILY_BRIEFING_TIME` — 디폴트 `07:30`. HH:MM (24h), `DAILY_BRIEFING_TZ` 기준.
- `DAILY_BRIEFING_TZ` — 디폴트 `Asia/Seoul`. IANA tz (예: `UTC`, `Asia/Tokyo`).

### Notes

- 일일 브리핑은 기존 v4.0.0 Tier 4 2-call 파이프라인 (`ContextAnalyst` + `NarrativeComposer`) 을 `mode='deep'` 으로 호출 — composer 프롬프트가 5~7 섹션 + 모순 명시.
- 브리핑 프롬프트는 ContextAnalyst 가 웹 검색으로 간밤 보도를 직접 확인하도록 명시 (학습 데이터 의존 금지). `mode='deep'` 강제 + 프롬프트에 "심층" 키워드 자연 포함.
- 봇 재시작 시 별도 복구 호출 불필요 — `BriefingSubscriberRegistry` SQLite 영속성으로 구독자 자연 복구.
- 같은 날 봇 재시작 + 트리거 시각 통과 케이스에서도 `briefing_runs.run_date` PK 가 중복 분석을 막음.
- `/status` 응답에 일일 브리핑 활성 여부 + 구독자 수 표시.

### Changed

- `src/orchestrator.py:VERSION` `v5.0.0 → v5.1.0`.

---

## [v5.0.0] — 2026-05-05

REFACTOR_V5_PLAN.md 17-Phase 마스터 플랜 완료. v4.5.7 호출 경로 byte-equal 보존 — V5 신규 모듈은 모두 opt-in (`V5_*` env flag, 디폴트 OFF).

**Tier 1 (Phase 0/0B/0C)** — Baseline + Golden Evaluation Harness (20 prompt + 회귀 17종) + 6-tier State 모델 (RawContext → EvidencePack → AnalysisBrief → DraftReport → ExhibitPack → PublishManifest).

**Tier 2 (Phase 1A/2/2A/2B)** — ResearchDirector (9-method 라우팅) + VisualPlanner (Vega-Lite spec) + EvidenceDataset Contract (AP-V5-24/25/26) + Capability Registry (16 chart type, AP-V5-27).

**Tier 3 (Phase 6/6A/7A/7/8/8A)** — Chart Gate (Schema/Critic/Sanity/Fallback) + Exhibit Priority + Deterministic Gate (11 Hard + 5 Soft) + DeskEditor (Logical 7 + Visual 8 rubric) + Strategic Mode (7 prefix + 8 패턴 + 8 필수 출력).

**Tier 4 (Phase 1/3/4/5)** — Editor Pass (7-rubric copy editing) + Layout Primitives (9-vocab AP-V5-3) + Exhibit 번호제 (`[[ex:N]]` / `[[exr:N]]` / `[[exs:N-M]]`, AP-V5-6) + Word Budget (5종 truncation signal + adaptive max_tokens, deep 64K, WRITE-AP-8 해소).

**활성화:** `docs/V5_ACTIVATION.md` 5-step 절차. `V5_RESEARCH_DIRECTOR=1` / `V5_VISUAL_PLANNER=1` / `V5_EDITOR_PASS=1` / `V5_LAYOUT_TYPESETTER=1` / `V5_DESK_EDITOR=1` 환경변수로 단계적 활성화.

**회귀 baseline:** v4.5.7 124 pass / 52 fail / 1 skip. V5 진보 측정은 후속 phase 별 baseline 재측정.

**Anti-pattern:** AP-V5-1 ~ AP-V5-32 누적, 회귀 테스트로 강제.

**진단 도구:** `scripts/retrofit_v5.py` — 기존 v4.5.7 보고서를 V5 게이트로 read-only dry-run 진단.

---

## [Unreleased]

V5 활성화 후속 작업 (각 phase 별 회귀 테스트 통과율 baseline 재측정).

---

## [v5.2.5] — 2026-05-16

### compact-strip (key_figures inline) 회생 + overflow root-fix + 모크업 양식 정렬

사용자 catch 3건 (overflow → 모크업 정합 → 시각 분리·모바일) 을 한 번에 정리.
이전 보고서 HTML (사용자 사전 push) 에는 있었으나 repo 에 미커밋 상태였던
`.compact-strip` 구현체를 회생시키며 v5.2.4 P0-Patch7 의 grid overflow 회귀를
근본 차원에서 fix.

**근본 원인 (회귀 1):** v5.2.4 의 `grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))`
+ flex children 의 고정 min-width 합 (name 64 + value 70 + change 50 + spark 60 +
gap 30 = 274px). flex 컨테이너의 default `min-width: auto` 가 grid track 의
220px 제약을 깨고 자식 합산 min-content 로 셀을 강제 확장 → 3 셀이 .freeform-section
.container (max 780px) 의 752px 를 넘쳐 옆 셀 콘텐츠를 침범. 라벨이 옆 sparkline
위에 겹쳐 보임.

**3-단 fix:**
1. `width: min(1100px, calc(100vw - 48px))` + `left: 50%` + `transform: translateX(-50%)`
   — strip 만 .container 의 780px 를 escape, 모크업 (`samples/market_charts_mockup.html`
   §2) 의 1200px wider context 재현. 모크업 CSS 값 (name 64fixed / value min 70 /
   change min 50 / spark flex 1 min 60) 글자 그대로 보존.
2. `.compact-row { min-width: 0 }` + `grid-template-columns: repeat(3, minmax(0, 1fr))`
   — break-out 동작 안 하는 edge case 의 safety net.
3. responsive (≤920 → 2 cols, ≤600 → 1 col stack) — 모크업 wrap 미만 viewport
   에서 overflow 보다 stack 이 항상 더 가독성 좋음.

**시각 분리 강화 (사용자 catch 3):**
- col gap 10 → 24px + 셀 사이 세로 separator (`::after` pseudo, 1px line)
- 행 내부 gap 10 → 8px (라벨+수치 그룹 더 묶음) + `.compact-spark margin-left: 6px`
  ([라벨+수치] 그룹 ↔ sparkline 시각 분리)

**모바일 명시 설계 (≤600px):**
- 1-col stack + 각 row 가 padding 10 + border-bottom 으로 독립 ticker 단위
- `:first-child` / `:last-child` padding·border reset
- name/value/change 폭 축소 (64/70/50 → 56/60/44) — 좁은 viewport fit

### 회생된 구현체 (repo 누락분)

- `charts.css` — `.compact-strip` / `.compact-row` 전체 CSS + 반응형
- `charts.js` — `drawSparkline` + `renderSparklines` (rAF×2 + ResizeObserver
  로 layout settle 후 그림) + `init()` 의 `renderSparklines()` 호출
- `freeform_essay.html` — `sec.charts` 를 `role='compact'` / 일반으로 namespace
  분기. compact 는 strip 으로 모아 prose 직후 1회만 emit
- `orchestrator.py` — `_format_compact_value` (rate/통화/일반 분기) +
  `_build_compact_strip_row` + `_ensure_market_strip` (instrument 3개↑ 면
  sections[0] 앞에 strip 자동 emit, idempotent) + `_composer_instruments` 가
  role='compact' 도 dedupe 집합에 포함

### 회귀 가드 (`tests/regression/test_compact_strip.py` — 15 tests)

- break-out width/left/translateX 동시 lock
- 모크업 §2 의 4 값 (name 64 / value 70 / change 50 / spark 60 + flex:1 +
  overflow:hidden) 글자 그대로 lock
- `.compact-row { min-width: 0 }` safety lock
- 920/600 breakpoint lock
- 세로 separator (`::after` selector + content/background) lock
- `.compact-spark margin-left` (그룹 분리) lock
- mobile 1-col stack 에서 `border-bottom` + `:last-child` reset 동시 lock
- `_ensure_market_strip` threshold-3 + idempotency + `_composer_instruments`
  role='compact' dedupe

---

## [v5.2.4] — 2026-05-15

### Standalone HTML 모드 — report_synthesizer 정적 자산 인라이닝

`<link href="charts.css">` / `<script src="charts.js">` 를 빌드 시점에 inline
`<style>` / `<script>` 로 치환. Cloudflare Pages 외 환경 (이메일 첨부, 로컬
열기) 에서도 차트가 정상 렌더.

---

## [v4.5.7 이전 — V5 리팩토링 진행 중 단계]

V5 리팩토링 (REFACTOR_V5_PLAN.md) Tier 1 (토대) 진행:

- **Phase 0 (Baseline + SSOT Repair) — 완료.** v4.5.7 baseline 으로 문서·메타데이터 정합성 회복. 코드 변경 0 (orchestrator VERSION 은 이미 v4.5.7).
- **Phase 0B (Golden Evaluation Harness) — framework 완료, baseline 녹화 대기.** 20건 Golden Prompt fixture (8개 카테고리 정합) + 5종 회귀 테스트 (Golden / Visual / Semantic / Cost / Completeness) framework + CLI runner + record_baseline.py. py_compile 통과. 사용자가 `.env` 환경에서 `python scripts/record_baseline.py` 1회 실행 시 baseline 녹화 완료. SSOT: `tests/regression/README.md`.
- **Phase 0C (Pipeline State Compaction) — framework 완료, 후속 Phase 결합 대기.** `src/state/` 모듈 신설 — 6-tier State 모델 (RawContext / EvidencePack / AnalysisBrief / DraftReport / ExhibitPack / PublishManifest), RawContext → EvidencePack 변환 (`compact_to_evidence_pack`, `evidence_pack_from_context_analysis`), 8단계 입력 제한 강제 (`assert_input_is`, `forbid_raw_context_in`, AP-V5-30). orchestrator 에 EvidencePack adapter *telemetry 전용* 삽입 — v4.5.7 호출 경로 byte-equal 보존. 회귀 테스트 `tests/regression/test_state_compaction.py` 신설 (16건 케이스, Plan §4.5 인수 기준 #1~#3 검증). py_compile + AST + Plan §4.4 / §6.3 정적 일치 검증 통과.
- **Phase 1A (Research Director / Method Router) — framework 완료, opt-in 활성 대기.** `src/agents/research_director.py` 신설 — Plan §6.4 의 SYSTEM_PROMPT 그대로 + 9종 method enum (ACH / scenario_tree / transmission_channel / stakeholder_matrix / fault_tree / decision_matrix / pre_mortem / transmission_timeline / comparative) + 결정적 fallback `design_via_heuristics` (LLM 0) + DEFAULT_BRIEF (Plan §20.3 fallback). orchestrator 에 *opt-in flag* (`Config.enable_research_director`, env `V5_RESEARCH_DIRECTOR=1`) 로 통합 — 디폴트 OFF, v4.5.7 호출 경로 byte-equal 보존. 꺼진 환경에서도 `design_via_heuristics` 가 모든 prompt 에 AnalysisBrief 를 emit (Plan §6.6 인수 기준 #1 충족). SSOT: `docs/RESEARCH_DIRECTOR_METHODS.md` (9종 method 의 적용 사건·입력·출력·권장 시각화). 회귀 테스트 `tests/regression/test_research_director.py` 신설 — Golden Prompt 20건 expected_method 일치률 90% (Plan §6.6 인수 기준 #4 임계 80% 통과). `run_regression.py` 가 lazy import 로 sandbox graceful degrade.
- **Phase 4 (Exhibit 번호제) + Phase 5 (Word Budget + 절단 회복) — framework 완료. Tier 4 종료.** Plan §11 + §12 — V5 의 마지막 Phase 들. *V5 의 보고서 본문 품질* 의 마지막 layer.
  - `src/visual/exhibit_numbering.py` 신설 (Phase 4) — Plan §11.3 의 `[[ex:N]]` / `[[exr:N]]` / `[[exs:N-M]]` 정규식 SSOT (`EXHIBIT_REF_PATTERN` + `EXHIBIT_REF_RANGE_PATTERN`). `assign_exhibit_ids` 자동 1부터 부여 + composer 가 박은 임의 ID 덮어씀 (AP-V5-6 강제). `resolve_exhibit_refs` (plain text) + `resolve_exhibit_refs_html` (anchor 점프) 양쪽. `validate_exhibit_refs` 가 Phase 7A 의 exhibit_ref_broken hard fail 의 사전 가드. `count_exhibit_refs` 통계 (Plan §11.5 인수 기준 — 보고서당 1~3회 권장).
  - `src/visual/word_budget.py` 신설 (Phase 5) — Plan §12 의 두 작업 통합. `MODE_TARGET_CHARS_LOWER` (Plan §6.4 byte-equal — fast 1500 / std 3500 / deep 6000) + `MODE_BUDGET_BANDS` (Plan §12.3 — peak_target / asymmetry 정도) + `COMPOSER_MAX_TOKENS_V5` (Plan §12.6 — fast 16K~24K / std 28K~40K / deep 48K~64K, **v4.5.7 의 deep 32K 한계 해소**). `detect_truncation` 5종 시그널 (production SSOT, helpers 와 byte-equal). `adaptive_max_tokens(mode, complexity)` + `complexity_score_from_context` (Plan §12.6 가중합). `compute_word_budgets` 가 mode 별 peak/support/watch 역할 분배. `gini_coefficient` + `section_length_distribution` (Plan §12.7 인수 기준 #1 측정). `stitch_continuation` 연속 호출 결합 (Plan §12.5 — 마지막 미완성 잘라내고 이어 작성).
  - 회귀 테스트 `tests/regression/test_exhibit_and_budget.py` 신설 — 32건 케이스. Phase 4 부분 (15건): assign_exhibit_ids AP-V5-6 강제 + 단일/괄호/범위/phantom resolve + HTML anchor + validate + count + 정규식 SSOT. Phase 5 부분 (17건): SSOT byte-equal + detect_truncation 4 시그널 + adaptive_max_tokens 보간 + complexity_score 가중합 + compute_word_budgets peak/role + gini 균등/집중 + stitch_continuation.
  - v4.5.7 호출 경로 byte-equal 보존 — Phase 4/5 모두 *데이터 + 함수* 형태. Renderer 결합 (Phase 4 의 anchor HTML 출력) 및 composer 호출 후 처리 (Phase 5 의 절단 검출 → 연속 호출) 는 별도 통합 작업.
  - **Tier 4 (미적 개선) 4/4 ✅ 종료. V5 17 Phase 모두 완료.**

- **Phase 3 (Layout Primitives) — framework 완료.** Plan §10 — 섹션마다 동일 구조 → *섹션별 layout 변주*. 9종 layout vocab 정본 동결 (AP-V5-3).
  - `src/state/models.py` — `LayoutPrimitive` Literal 9종 (standard / hero_map / hero_chart / split_2col / sidebar_callout / qna_panel / timeline_strip / signature_summary / exhibit_grid) + `LayoutAssignment` 모델 (section_idx + layout + why + assigned_by 3-tier).
  - `src/agents/layout_typesetter.py` 신설 — `LayoutTypesetter(BaseAgent)` (Sonnet 4.6, MAX_TOKENS=2048, 빠른 분류 작업). SYSTEM_PROMPT 가 Plan §10.3 의 결정 원칙 (60~70% standard / hero_* ≤ 1~2개 / 연속 배치 차단 / 지리 사건 hero_map 권장 등) 명시.
  - `plan_layouts_via_heuristics(sections, has_map, is_strategic, section_count)` — LLM 0 결정적 fallback. 9-vocab 모두 트리거 (지리/결론/차트≥3/Q&A 패턴/타임라인/비교/단일 결정적 차트/analogy 동반/그 외 standard) + 연속 배치 차단 + hero count ≤ 2 강제.
  - `fallback_all_standard(n)` — Plan §10.5 의 LayoutTypesetter 호출 실패 시 모든 섹션 standard fallback.
  - `Config.enable_layout_typesetter` opt-in flag (env `V5_LAYOUT_TYPESETTER=1`) — 디폴트 OFF.
  - 회귀 테스트 `tests/regression/test_layout_typesetter.py` 신설 — 23건 케이스. 9-vocab SSOT (AP-V5-3 강제 가드) + LayoutPrimitive Literal 정합 + heuristic 8종 트리거 검증 + 연속 배치 차단 + hero ≤ 2 cap + fallback_all_standard + agent 모델·예산 (Sonnet 4.6, 2048).
  - HTML 템플릿 (templates/layouts/) 은 *별도 작업* — 본 commit 은 결정 로직만. 템플릿이 박힐 때까지 LayoutAssignment 는 *meta 정보* 로 telemetry / 후속 분기.

- **Phase 1 (Editor Pass) — framework 완료. Tier 4 (미적 개선) 의 첫 Phase.** Plan §5 — V5 의 *보고서 글쓰기 품질* 개선 시작점. Drafting + Editing 2 호출 — 같은 Opus 4.7 이 *editor 페르소나* 로 자기 글을 비평·재집필.
  - `src/agents/editor.py` 신설 — `Editor(BaseAgent)` (Opus 4.7, MAX_TOKENS=16000). SYSTEM_PROMPT 가 Plan §5.4 의 7-rubric (군더더기 / 결론의 칼날 / 모순 봉합 / 차트-본문 결합 / 분량 비대칭 / 신선함 / 외래어 풀이) 그대로. JSON 응답 스키마 (critique / revisions / final) 강제.
  - `EditedReport` 모델 — ComposedReport 와 호환 구조 + `editor_critique` + `editor_pass_applied` flag.
  - `SectionScore` (7-rubric 0~10 점) + `SectionRevision` (rewrite/cut/keep) + `EditorCritique` 모델.
  - `assert_signal_count_preserved(draft, edited)` — Plan §5.6 인수 기준 #3 강제. Editor 가 watch_signals / contradictions 개수를 *축소* 하면 fail → graceful fallback (draft 그대로). Anti-pattern #5 (모순 봉합) 회귀 차단.
  - `detect_cliches(text)` — Plan §5.4 Q1 (padding) 의 결정적 보조. 7종 진부어 (`주목할 만한 점은`, `결론적으로`, `대체로` 등) 매칭.
  - `Config.enable_editor_pass` opt-in flag (env `V5_EDITOR_PASS=1`) — 디폴트 OFF.
  - 회귀 테스트 `tests/regression/test_editor.py` 신설 — 22건 케이스. SECTION_SCORE_RUBRICS 7종 SSOT + SYSTEM_PROMPT 7-rubric 정합 + 보존 검증 (4건) + 진부어 매칭 + EditedReport / EditorCritique 모델 + Editor 인스턴스 smoke.
  - v4.5.7 호출 경로 byte-equal 보존 — Composer DraftReport 가 Editor 통과 후 EditedReport 로 emit 되는 결합은 opt-in 시점에 활성.

- **Phase 8 + 8A (Strategic Mode + Contract) — framework 완료.** Plan §17 + §18 — 의사결정 보조 모드. *처방적* 보고서 (옵션 + 권고 + ActionPlan). 분석 모드와 *근본적으로 다른* 보고서 종류.
  - `docs/STRATEGIC_MODE_PROMPT.md` 신설 (Plan §25.1 사전 작업 #2 완료) — composer system prompt 확장 SSOT (전략 모드 7개 디폴트 섹션 + 핵심 어법 규칙) + 3-경로 감지 (prefix / 패턴 / LLM) + 한계 (LLM 의 utility function 모름) 명시.
  - `src/agents/strategic_router.py` 신설 — `EXPLICIT_PREFIXES` 7종 (`?전략` / `?분석` / `?예측` / `?비교` / `?지도` / `?짧게` / `?심층` + `/strategy` alias) + `STRATEGIC_PATTERNS` 8종 정규식 (Plan §17.2 byte-equal). `route_query(user_request, llm_user_intent)` 통합 router → `ModeRouting` (mode + detection_source + matched_prefix/patterns + cleaned_query). AP-V5-23 (모호 시 analytical 기본값) 강제.
  - `src/state/models.py` 강화 — Phase 8A 의 8개 필수 출력 모델: `StrategicReport` (decision_statement / options / criteria / constraints / decision_matrix / recommendation / kill_switch_conditions / action_plan_30_60_90) + leaf 모델 8종 (`StrategicOption` + `Criterion` + `Constraints` + `DecisionMatrix` + `Recommendation` + `ActionItem` + `ActionPlan` + `FailureMode`).
  - `KILL_RULES_STRATEGIC` (`run_strategic_kill_rules`) — Plan §17.6 + §18.4 의 9종: options_too_many (≥6) / no_decision_matrix / matrix_score_uniform / recommendation_absent (rationale<50자) / premortem_missing_deep / criteria_not_user_aligned / decision_statement_missing / action_plan_missing / kill_switch_missing. **AP-V5-18 갱신** (Plan §18.4) — 옵션 0개 → hold (KILL 아님), 1~2개 허용, 6+ KILL.
  - `evaluate_strategic_mode(report, mode)` 통합 평가 → `StrategicEvaluation` (decision: publish/hold/kill). 0 옵션 시 hold + 사용자 안내 ("?분석 prefix 로 재시도").
  - 회귀 테스트 `tests/regression/test_strategic_mode.py` 신설 — 39건 케이스. **Plan §17.7 인수 기준 #1 정확도 검증** — 30건 라벨된 query 의 routing 정확도 100% (≥90% 임계 통과). prefix 7종 + pattern 8종 + 모델 enum + 9종 KILL_RULES + AP-V5-18 갱신 정책 (0/1/2/6 옵션) + 통합 evaluate.
  - v4.5.7 호출 경로 byte-equal 보존 — 텔레그램 봇의 `_classify_input` 또는 orchestrator 의 mode 결정 시점에 결합 가능 (현재 코드만 박힘).

- **Phase 7 (Desk Editor — Logical + Visual Proof) — framework 완료. Tier 3 의 첫 Phase.** Plan §16 — V5 의 *가장 큰 사용자 체감 변화 시작점*. 신문사 데스크 등급의 시스템 QA + publish/hold/**KILL** 권한.
  - `docs/DESK_VISUAL_RUBRIC.md` 신설 (Plan §25.1 사전 작업 #4 완료) — Visual 8-rubric SSOT (시각-1~8) + append-only 누적 정책 (AP-V5-16) + 자동 KILL 신호 매트릭스. YK catch 결함이 다음 DeskEditor 호출에서 자동 catch 되도록 self-improving (Plan §16.12).
  - `src/visual/capture.py` 신설 — Plan §16.5 의 Playwright capture pipeline. `capture_proofs(html_path, exhibit_count, timeout_ms)` 가 desktop_full (1280×scrollHeight) + mobile_full (375×scrollHeight) + chart_closeup (≤3개) 캡쳐. Playwright 미설치 시 graceful 빈 list (Visual rubric skip). `save_captures_to_disk` 디버그용.
  - `src/agents/desk_editor.py` 신설 — Plan §16.2 의 DeskEditor (Opus 4.7 vision, MAX_TOKENS=8000). SYSTEM_PROMPT 가 Plan §16.3 의 Logical 7-rubric (headline_body / deck_conclusion / section_flow / chart_redundancy / watch_signal_predictivity / source_claim_ratio / smell_test) + DESK_VISUAL_RUBRIC.md §1 의 Visual 8-rubric 자동 포함 (self-improving).
  - `DeskVerdict` (decision: publish/hold/kill + logical_rubric_scores + visual_rubric_scores + issues + kill_reason + auto_kill_rules_triggered) + `DeskIssue` (severity / domain / rubric / suggested_action / target_module / visual_evidence_idx).
  - `run_logical_kill_rules` + `run_visual_kill_rules` + `evaluate_auto_kill` — Plan §16.6 의 결정적 KILL_RULES (Logical 5종 + Visual 3종, *둘 이상* 발화 시 자동 KILL). LLM 호출과 *별개* 로 작동 (AP-V5-14 강제).
  - `HOLD_DISPATCH` 매트릭스 17종 + `dispatch_hold_action` — Plan §16.8 의 lower editor 재호출 분기 (composer/editor/chart_critic/renderer/visual_planner/layout).
  - `Config.enable_desk_editor` opt-in flag (env `V5_DESK_EDITOR=1`) — 디폴트 OFF.
  - 회귀 테스트 `tests/regression/test_desk_editor.py` 신설 — 27건 케이스. DeskVerdict/DeskIssue enum 정합 + Logical 5-KILL + Visual 3-KILL + 자동 KILL 통합 (둘 이상 / 1종 / Logical+Visual 조합) + HOLD_DISPATCH 17종 매핑 + Playwright graceful skip + SYSTEM_PROMPT 의 7+8 rubric 정합 + DESK_VISUAL_RUBRIC.md SSOT 형식.
  - v4.5.7 호출 경로 byte-equal 보존 — Phase 7 전 단계 (Phase 7A Deterministic Gate) 통과 후에만 호출 가능.

- **Phase 7A (Deterministic Publish Gate) — framework 완료. Tier 2 의 마지막 Phase.** Plan §15 — DeskEditor (LLM Vision, Phase 7) 호출 *전* 결정적 (rule-based) 검사. 기계적으로 잡을 수 있는 결함은 LLM 비용 0 으로 차단. AP-V5-29 강제.
  - `src/visual/deterministic_gate.py` 신설:
    · **Hard fail 11종** (Plan §15.4): html_render_failed / html_unparseable / required_section_missing / exhibit_ref_broken / chart_without_source (AP-V5-26) / chart_container_empty / report_too_short (mode lower bound) / closing_missing / asset_404 (정적 자산 디스크 verify) / mobile_horizontal_overflow (inline width >400px 검출) / playwright_timeout. 1개라도 발생 시 decision='kill' → LLM 호출 0.
    · **Soft fail 5종** (Plan §15.5): asymmetry_gini (>0.6) / chart_count_exceeded (mode 별 fast 2 / std 4 / deep 5) / heading_pattern_repetitive (어두 동일 + 길이 ±2자) / watch_signal_all_ambiguous / stale_source_ratio (>70% 90일+). DeskEditor system prompt 에 hold 신호로 전달.
    · `MODE_LOWER_BOUND` (Plan §6.3 의 fast 1500 / std 3500 / deep 6000) + `ChartCountLimits` (Plan §13.8) SSOT.
    · `[[ex:N]]` / `[[exr:N]]` / `[[exs:N-M]]` exhibit ref 정규식 파싱 — Phase 4 신설 형식 사전 가드.
    · `_gini_coefficient` / `_heading_repetitive` / `_stale_source_ratio` 헬퍼.
    · `run_deterministic_gate(composed, rendered_html_path, mode, must_have_sections, playwright_timed_out)` 통합 진입점 → `DeterministicGateResult` (decision: publish/soft_fail/kill + hard_failures + soft_failures + metrics).
  - 회귀 테스트 `tests/regression/test_deterministic_gate.py` 신설 — Plan §15.6 인수 기준 #1 (11 hard fail 모두) + #2 (Hard fail → decision='kill' → LLM 호출 0) 결정적 검증. 22건 케이스 — clean publish + 11종 Hard fail 개별 + 4종 Soft fail + 다중 Hard 모두 보고 + Result 형식.
  - v4.5.7 호출 경로 byte-equal 보존 — Phase 7 (DeskEditor) 활성 시점에 결합. AP-V5-29 가 *Phase 7 가 박힐 때* 본격 활성.

- **Phase 6A (Exhibit Priority Policy) — framework 완료.** Plan §14 — Phase 6 의 보수적 drop 정책이 *핵심 논거 차트까지 조용히 사라지게* 만드는 부작용을 차단. AP-V5-28 (Required Exhibit 의 silent drop 금지) 강제.
  - `src/state/models.py` 강화 — `ExhibitPriority` Literal 3종 enum (required / supporting / decorative) + `Exhibit` 모델 신설 (priority + priority_assigned_by + fallback_form 필드) + `RequiredExhibit` 모델 신설 (Plan §14.4 — description / visual_type_hint / why_required / fallback_form) + `AnalysisMethod.required_exhibits` 가 `list[str]` → `list[RequiredExhibit]` 로 강화 (legacy `list[str]` 자동 변환 — model_validator before).
  - `src/visual/chart_gate.py` 강화 — `run_chart_gate(...)` 가 `priority` 와 `required_fallback_form` 인자 추가. priority 별 분기:
    · `required` → AP-V5-28 강제 격하 (fact_grid / table / text 순). 데이터 결손 시에도 *최소한 placeholder text emit* — drop 절대 금지. `ChartGateResult.required_fallback_used=True` 로 DeskEditor 가 hold 사유로 인지.
    · `supporting` (기본) → 기존 3단계 ladder (fact_grid → text → drop).
    · `decorative` → 1단계만 (fact_grid 안 되면 즉시 drop, 조용히).
  - `FallbackLadder.to_table()` 신설 — 행 다수 (>6) 데이터를 표 형식으로 격하. RequiredExhibit.fallback_form='table' 분기.
  - `ChartGateResult` 에 `priority` + `required_fallback_used` 추적 필드 추가.
  - `src/agents/research_director.py` SYSTEM_PROMPT 에 Plan §14 의 required_exhibits 정책 안내 추가 (각 method 마다 1~2개 핵심 차트 명시 + fallback_form 지정). `_DEFAULT_REQUIRED_EXHIBITS` heuristic 매핑 갱신 — 9종 method 모두 매핑 (fault_tree / pre_mortem 은 빈 list 허용). RequiredExhibit dict 형식으로 전환.
  - 회귀 테스트 `tests/regression/test_exhibit_priority.py` 신설 — Plan §14.5 인수 기준 #1~#3 모두 검증. 22건 케이스 — Exhibit default priority + 3-tier enum + RequiredExhibit 모델 + legacy list[str] 자동 변환 + AP-V5-28 강제 (required + Gate fail → drop 금지) + table fallback (row 다수) + text fallback (data 결손 placeholder) + decorative silent drop + supporting 3-step + ChartGateResult priority 추적 + ResearchDirector heuristic.
  - v4.5.7 호출 경로 byte-equal 보존 (legacy list[str] 자동 변환).

- **Phase 6 (Chart Correctness Gate — 4중 게이트) — framework 완료.** Tier 2 의 핵심. Plan §13 의 4중 게이트:
  - **Gate A (Schema Validation)** — `src/visual/schemas.py` 신설. 9개 type 별 Pydantic 가드 (`BubbleChartGuard`/`GanttGuard`/`NetworkGuard`/`BarChartGuard`/`LineChartGuard`/`HeatmapGuard`/`StackedBarGuard`/`DonutGuard`). NaN/inf 거절 (CHART-AP-3), 빈 data 거절 (CHART-AP-7), bubble size>0 (CHART-AP-12), gantt 시간 파싱 + 중복 라벨 (CHART-AP-13), network link 참조 + 노드 ≥ 2 (CHART-AP-1), donut 음수/0 합계, stacked categories ↔ values 정합. `parse_time` 이 ISO/날짜/연도 4종 형식 지원.
  - **Gate B (ChartCritic LLM)** — `src/agents/chart_critic.py` 신설 (Sonnet 4.6, 1024 tokens). Plan §13.3 의 7개 질문 SYSTEM_PROMPT — Q1 차트 빠지면 논거 약해지나 / Q2 takeaway repeat / Q3 type 적합 / Q4 prose 인용 (AP-V5-7) / Q5 중복 / Q6 지도 무관 (AP-14) / Q7 공허. `ChartVerdict` (score 1~5, keep/replace/drop). Plan §13.8 운영 정책 — score ≥ 4 만 keep (3 ambiguous → drop), 호출 실패 시 보수적 drop fallback. `critique_via_heuristics` 가 LLM 0 결정적 휴리스틱 (Q4 + Q7 평가).
  - **Gate C (Visual Sanity)** — `src/visual/sanity_check.py` 신설. lxml 기반 SVG 정적 검증 (미설치 시 정규식 fallback). `visual_sanity_check_svg(svg, viewbox)` 가 4개 항목 검증 — 마크 카운트 (AP-12), 라벨 bbox 충돌 ≤ 20% (AP-5/6/10), viewBox 점유율 ≥ 5% (빈 frame), 라벨 viewBox 밖 잘림 (AP-5).
  - **Gate D (Fallback Ladder)** — `src/visual/chart_gate.py` 신설. Plan §13.5 의 3단계 격하: ① fact_grid 변환 (≤ 6 행 시) → ② 자연어 1문장 요약 → ③ 차트 자체 drop. *깨진 차트 보고서 노출 0건* 정책.
  - **`run_chart_gate(chart, ...)`** 통합 진입점 — Gate A → B → (B-extra: EvidenceDataset) → C → D 순. 어느 게이트든 fail 시 즉시 Fallback Ladder. `ChartGateResult` 가 final_verdict (keep / fallback_fact_grid / fallback_text / fallback_drop) + gate_results + fallback_payload 반환.
  - 회귀 테스트 `tests/regression/test_chart_correctness.py` 신설 — Plan §13.7 인수 기준 #1 (14개 antipattern 시나리오). 38건 케이스 — Gate A 8개 type guard + Gate B 4건 (Q4/Q7/threshold 4) + Gate C 5건 (SVG 결함) + Gate D 4건 (fallback ladder) + 통합 5건 (run_chart_gate end-to-end).
  - v4.5.7 호출 경로 byte-equal 보존 — 본 게이트는 VisualPlanner / 미래 Phase 7 DeskEditor 의 emit 경로에 결합 (현재 코드만 박힘).

- **Phase 2B (Visualization Capability Registry) — framework 완료.** Plan §9 — 차트 type 의 *capability bound* 명시. `docs/VISUAL_CAPABILITY_REGISTRY.yaml` 신설 (16종 type — safe 11 / guarded 3 / experimental 2 정확 분포). `src/visual/capability_registry.py` 신설 — yaml 로더 (캐시) + `is_chart_type_allowed` (3-tier 정책: safe 자유 / guarded Phase 6 Gate C 필수 / experimental forbidden 디폴트, must_have 명시 시만) + `check_required_fields` (필드 정합) + `assert_chart_in_registry` (AP-V5-27 강제). VisualPlanner 의 `_parse_exhibits` + `plan_via_heuristics` 양쪽에 Registry 가드 통합 — emit 전 Registry 미등재/forbidden 즉시 drop. 회귀 테스트 `tests/regression/test_capability_registry.py` 신설 — Plan §9.3 의 11/3/2 분포 검증 + experimental forbidden 강제 + must_have 우회 + required_fields 정합 + renderer enum 4종 검증. 24건 케이스. v4.5.7 호출 경로 byte-equal 보존 (VisualPlanner opt-in flag 그대로).

- **Phase 2 (Visualization Decoupling + Open-Ended Charts) — framework 완료, opt-in 활성 대기.** Tier 2 의 첫 Phase. Plan §7 + §19 에 따라:
  - `src/visual/v5_theme.py` 신설 — Plan §19 의 design token SSOT (Editorial Cream + Burgundy Mono 2종 + 폰트 트리플렛). `get_theme_config(theme)` 가 Vega-Lite config 로 변환, `apply_theme_to_spec(spec, theme)` 가 LLM 이 박은 색을 *덮어씀* (AP-V5-2 강제).
  - `src/visual/vega_adapter.py` 신설 — `render_vega_lite(spec, theme, output)` 단일 어댑터 (Plan §7.4). `vl-convert-python` 미설치 환경에서 themed spec dict 로 graceful fallback (브라우저 vega-embed 호환). `validate_vega_spec` 이 Phase 6 Gate A 의 사전 가드 (CHART-AP-7 빈 data / 비-Vega-Lite schema 거절). `chart_dict_to_vega_spec` 이 v4.5.7 의 ComposedSection.charts 형식을 Vega-Lite 로 마이그레이션 보조.
  - `src/agents/visual_planner.py` 신설 — Plan §7.3 의 VisualPlanner (Opus 4.7, MAX_TOKENS 12000) + SYSTEM_PROMPT (Plan §7.3 그대로). `plan_via_heuristics` 가 LLM 호출 없이 v4.5.7 chart spec 을 EvidenceDataset Guard 통과 기준으로만 필터. `Config.enable_visual_planner` opt-in flag (env `V5_VISUAL_PLANNER=1`) 디폴트 OFF — v4.5.7 호출 경로 byte-equal 보존.
  - 회귀 테스트 `tests/regression/test_phase2_vega.py` 신설 — Plan §19 design token 정합성 + apply_theme 강제 + validate_vega_spec + Plan §7.7 antipattern 자동 해결 매핑 (AP-1 / AP-11 / AP-12) 검증. 25건 케이스.
  - Plan §7.8 인수 기준: #4 (모든 차트가 V5 design token 강제) ✅, #5 (자동 해결 8개 항목 검증) ✅. #1 (visual_builder 11개 함수 폐기) 은 Phase 2 본격 활성 시점에 — v4.5.7 charts.js 의존이라 *현재 보존*. #2 (새 chart type demo) / #3 (Editor → Visual 호출 순서) 는 Phase 1 (Editor Pass) 결합 후.

- **Tier 1 baseline 측정 (2026-05-05).** VM 에서 v4.5.7 환경 그대로 20건 Golden Prompt 실측 녹화 (139분, errors 0). 회귀 테스트 7종 통과율 **70.1% (124 pass / 52 fail / 1 skip / 177 total)** 박힘. 52 fail 은 *Plan §22 #2 의 의도대로* V5 후속 Phase 가 개선해야 할 항목들의 baseline (watch_signal direction 미발화 / 분량 부족 / 부적합 차트 / deck-결론 정합 등). AP-V5-32 활성 — V5 후속이 fail count 를 늘리면 회귀. helper 버그 1건 (`extract_chart_numbers` 의 1자리 숫자 거름 누락) 수정.

- **Phase 2A (EvidenceDataset Contract) — framework 완료, Phase 6 ChartCritic 결합 대기.** `src/state/models.py` 의 `EvidenceDataset` 강화 — `DatasetField` (semantic_type 7종 enum) + `TransformStep` (raw → 차트 데이터 변환 추적) BaseModel 화. `src/visual/evidence_dataset.py` 신설 — `EvidenceDatasetGuard` + 검증 함수 (`validate_evidence_dataset`, `ensure_chart_has_source_ids`, `ensure_chart_data_cited_in_prose`, `extract_chart_numbers`). Plan §8.5 의 3개 금지 행위 (AP-V5-24 prose 발 차트 데이터 / AP-V5-25 출처 없는 synthetic / AP-V5-26 source_id 없는 chart) 결정적 강제. Plan §8.6 의 ChartCritic 질문 8 (prose 인용 가드) 사전 구현 — 차트 data 의 *고유 숫자 ≥20% 가 prose 에 인용* 되어야 keep, 미만 시 drop 권고. 회귀 테스트 `tests/regression/test_evidence_dataset.py` 신설 — Plan §8.7 인수 기준 #1~#4 모두 결정적 검증 (24건 케이스). v4.5.7 호출 경로 byte-equal 보존 — Phase 6 ChartCritic 진입 시 본격 활성.

---

### v4.5.7 — ContextAnalyst max_tokens deep 모드 4K → 10K + Somaliland viewport gating

#### Changed
- `src/agents/base.py` — `BaseAgent._max_tokens_override` 지원. subclass 가 mode 별로 override 가능.
- `src/agents/context_analyst.py` — `request.mode` 별 max_tokens 분기. fast / standard 4096 유지, deep 4096 → 10000. deep 사건의 사실/타임라인/출처 다수 시 4K 부족 회귀 차단.

#### Fixed
- `src/templates/static/maps.js` — Somaliland (de facto) 해칭 폴리곤과 'de facto' legend 항목이 모든 보고서에 무조건 렌더되던 회귀. `path.bounds(SOMALILAND_GEOJSON)` 로 projection 적용 후 viewport 와 교집합 검사. 호르무즈·동북아 같은 무관 보고서에서 polygon + legend 모두 skip.
- 사용자 회귀 (호르무즈 / 위안화 통행세 보고서에 'Somaliland (de facto)' legend 노출) 차단.

#### Added
- **CHART-AP-14** — "보고서와 무관한 지리 annotation 무조건 렌더" anti-pattern 신설 (CHART_RENDERING_ANTIPATTERNS.md). `path.bounds()` 로 viewport 교집합 검사 후 render gating 의무화.

> 주의: 24ba563 commit 메시지는 이 항목을 'CHART-AP-13' 으로 표기했지만, v4.5.4 에서 이미 CHART-AP-13 (Gantt 시간축) 이 부여되어 번호 충돌. REFACTOR_V5_PLAN.md §3.7 의 정본에 맞춰 CHART-AP-14 로 정정한다.

---

### v4.5.6 — 'Analysis Team' 접두 + Rev 0 항상 표기

#### Changed
- `src/templates/archetypes/freeform_essay.html` hero eyebrow — `v4.5.5` → `Analysis Team v4.5.5 · Rev 0`. `Rev 0` 도 항상 표기 (이전엔 0 숨김). 사용자 요구 "애너리시스 팀 v4.5.5" 식 명시적 레이블.

---

### v4.5.5 — system_version + revision 추적성 (보고서 상단 노출)

#### Added
- `FullAnalysisResult.system_version: str` — 생성 시점 `src/orchestrator.py:VERSION` 기록. 재렌더 시엔 *재렌더 시점* 버전으로 갱신 (CSS/JS 가 그 버전 따름).
- `FullAnalysisResult.revision: int = 0` — 최초 생성 0, `patch_report.py` 수정 시 +1.
- `freeform_essay.html` hero eyebrow — `EVENT ANALYSIS · COMPOSED · v4.5.5 · Rev 2` 형식. revision 0 면 'Rev 0' 안 표시 (v4.5.6 에서 정책 변경 — 항상 표시).
- `.freeform-version` 토큰 — IBM Plex Mono, muted 색.

#### Changed
- `src/agents/report_synthesizer.py:synthesize()` — 매 렌더 (신규/재렌더 모두) 시 `result.system_version` 갱신. 재렌더만 한 경우엔 system_version 만 바뀌고 revision 그대로 (데이터 변경 X).
- `scripts/patch_report.py` — mutated 또는 `--edit` 인 경우 `result.revision += 1` 후 저장. `--rerender-only` 는 데이터 변경 없으니 revision 안 올림.

#### 배경
사용자 피드백 (20260503_164450) — 보고서가 477초 걸린 후 'composer 호출 실패. 사실 자료만 표시' 폴백으로 종료. 어떤 코드 버전에서 만들어졌는지, 이후 패치됐는지가 보고서 자체에 안 보여 진단·재발 추적 어려움.

---

### v4.5.4 — drawGantt 시간축 + note placement fix + composer max_tokens mode 별 분기

#### Added
- `narrative_composer.MAX_TOKENS_BY_MODE` — fast 12K / standard 20K / deep 32K. `_call_api(user_message, mode)` 에 mode 인자 추가.
- **CHART-AP-13** — "Gantt 차트 시간축 누락 + 행 라벨/note 충돌" anti-pattern 신설.
- **WRITE-AP-8** — "max_tokens 한도로 보고서 본문 중간 절단" anti-pattern 신설.

#### Changed
- `charts.js:drawGantt` 전면 보강 — `d3.axisBottom` 풍 시간축 자동 추가 (tick + label + grid). `parseTime()` 입력 정규화 (numeric / 'YYYY' / 'YYYY-MM' 모두 지원). `start === end` 면 0.4 단위 폭 부여. 막대 최소 폭 2 → 6px. note placement 분기 — 막대 폭 ≥ 60px 면 *내부* 흰글자, 아니면 *외부 우측*. 행 라벨 truncate 22 → 25자.
- `narrative_composer` 단일 `MAX_TOKENS = 8192` → `MAX_TOKENS_BY_MODE` (default fallback 32000).

#### Fixed
- WRITE-AP-8 회귀 — composer 의 단일 MAX_TOKENS=8192 가 deep 모드 (5~7 섹션 + 시나리오 + 모순 + 차트/지도 emit) 에서 부족해 응답 *중간 절단*. mode 별 분기로 차단.
- 자율주행 일정 비교 gantt 차트의 의미 불명 회귀 (사용자 피드백 20260503_142254).

---

### v4.5.3 — chart-card 테마 귀속 + bubble 스케일 자동 감지 (CHART-AP-11/12)

#### Added
- 각 테마 블록에 `--card-deep` CSS 변수 정의 — editorial_cream `#E5DBC4`, burgundy_mono `#1A0810`, light_mono `#dccea8`.
- **CHART-AP-11** — "차트 카드 배경이 하드코딩 fallback (테마 미반영)" anti-pattern 신설.
- **CHART-AP-12** — "버블 차트 스케일 고정 — 데이터가 frame 밖으로" anti-pattern 신설.

#### Changed
- `src/templates/archetypes/freeform_essay.html` `.freeform-chart-wrap .chart-card` 배경 — `rgba(0,0,0,0.18)` → `var(--card, var(--bg-2))`. 테마 따라감.
- `charts.js:drawBubble` — `d3.scaleLinear().domain([0,1])` 고정 → `d3.extent` 자동 감지. 0 포함 + 5% padding + size 정규화 (sMax 기반). composer 가 0~1 / 0~5 / 0~100 어느 범위로 emit 해도 정상 표시.

#### Fixed
- editorial_cream 디폴트 (v4.5.0) 채택 후 즉시 노출된 회귀 — 모든 차트 카드가 dark wine 박스로 표시되어 글자 가독성 0. `--card-deep` 변수 미정의로 CSS variable resolution fallback `#321F1F` 가 항상 적용된 결함.
- 시나리오 확률×영향 버블 차트의 빈 frame 회귀 — composer 가 0~5 또는 0~100 범위로 emit 시 모든 bubble 이 frame 밖으로 나가 안 보이던 문제.

---

### v4.5.2 — fact-grid 항상 한 줄 (data-cols 강제) + VERSION bump 동기화

#### Changed
- `src/templates/archetypes/freeform_essay.html` fact-grid CSS — 미디어 쿼리 폐기. `data-cols` 값 그대로 cols 적용. 2/3/4/5/6 모두 한 줄에 강제. wrap 가능성 자체 제거.
- 좁은 폭 (≤ 640px) 가독성 — tile padding 14px/16px → 10px/8px, label font 10.5px → 9px, value font 22px → 15px (`word-break: keep-all`), sublabel font 11px → 10px. 5/6 cols 추가 축소.
- `src/orchestrator.py:VERSION` — v4.5.0 → v4.5.2 (v4.5.1 / v4.5.2 commit 시 VERSION bump 누락분 동기화).

#### 사용자 피드백
v4.5.1 의 mobile 1-col stack 이 사용자 의도와 반대 ("한 줄에 보이는 게 더 좋아"). 정책 반전.

---

### v4.5.1 — fact-grid 모바일 1 col stack — 홀수 타일 어색 wrap 차단

#### Changed
- `src/templates/archetypes/freeform_essay.html` fact-grid — mobile (< 720px) 모든 count 1 col stack. desktop (≥ 720px) count 별 분기 유지 (2/3/4/5/6 한 줄). `data-cols="2"` 추가.

#### 비고
v4.5.2 에서 정책 반전됨 (사용자 피드백 따라 모바일도 한 줄 강제). v4.5.1 은 short-lived intermediate state.

---

### v4.5.0 — Editorial Interaction Patterns + Newsreader/IBM Plex Fonts (LG 벤치마크 차용)

LG AI Seminar 보고서를 인터랙션 패턴 벤치마크로 채택. 기술 스택 (d3 차트/지도, mono 테마 시스템, Tier 4 아키텍처) 은 그대로 유지하고 *말하는 방식 + 페이지 위 텍스트 구조* 만 차용. 음슴체 → 평어체, 신규 editorial 컴포넌트 4종, 폰트 시스템 교체.

#### Added
- 신규 테마 `editorial_cream` — cream (`#F2EBDB`) + terracotta accent (`#B05A38`). 디폴트로 채택. `burgundy_mono` 는 위기·분쟁 (`geopolitical`/`accident`) 한정.
- `ComposedSection.lede` — 긴 도입 1~3문장 (italic, prose 위 큰 글씨).
- `ComposedSection.analogy` — `{title, body}` 비유 박스. 어려운 개념을 일상 비유로.
- `ComposedSection.fact_grid` — `[{label, value, sublabel?}]` 핵심 수치 격자.
- `ComposedSection.dropcap` — bool, prose 첫 글자 dropcap 렌더 (보고서당 1~2 섹션 권장).
- 자동 TOC — 섹션 ≥ 2개일 때 hero 직후 자동 생성. 섹션 anchor (`#sec-N`) 자동 부여.
- 폰트: Newsreader (display serif, 영문/숫자) + IBM Plex Sans KR (본문) + IBM Plex Mono. 한국어는 Noto Serif KR 폴백.
- WRITE-AP-7 — 서수 / 기수 혼용 ("N번" 의 두 얼굴) anti-pattern 신설.

#### Changed
- composer SYSTEM_PROMPT v4.5.0 — 음슴체 (~함) 폐기 → 평어체 (~다). 질문 던지기 가이드. WRITE-AP-7 prevention 명시.
- `burgundy_mono` 톤 어둡게 보정 — bg `#3D1820` → `#2A0F18`, water `#2A0E16` → `#1A0810`. 사용자 피드백 "맑은 와인" → "dried-blood" 톤.
- `lens_policy._THEME_BY_CATEGORY` — 디폴트 `editorial_cream`, `geopolitical`/`accident` 만 `burgundy_mono`.
- `freeform_essay.html` — 모든 raw text 출력에 `| strip_md` 적용 (v4.4.7 정책 일관).

#### Fixed
- WRITE-AP-1 회귀 (v4.4.7) — markdown asterisk 가 `contradictions` / `watch_signals` / `deck` / `headline` 등 dict 필드에서 raw 노출. lightweight `_strip_markdown` 신규 + jinja2 `strip_md` filter + 모든 raw text 필드에 일괄 적용.

---

### v4.4.7 — Patch tool 텍스트 필드 옵션 + WRITE-AP-7 + WRITE-AP-1 확장

`patch_report.py` 에 `--deck` / `--headline` / `--closing` / `--confidence-summary` 추가. composed_report 텍스트 필드를 LLM 호출 없이 즉시 수정.

### v4.4.6 — 지도 상단 배치 + d3.zoom + 소말릴란드 해칭 폴리곤

WRITE-AP-3 (지도 후행 배치) 회귀 fix — 지도 섹션을 hero 직후로 이동. d3.zoom() pan/zoom + 컨트롤 버튼. 소말릴란드 (de facto) 45° 해칭 폴리곤 (Natural Earth 1:50m 단순화).

### v4.4.5 — patch_report.py 지도/마커 옵션 + 다중 차트 제거

`--show` / `--map-zoom` / `--map-center` / `--remove-marker` 추가. `--remove-chart` 다중 가능 (인덱스 shift 자동 처리).

---

### v4.2.0 — Composer-emitted Charts + Maps

Composer 가 차트/지도 데이터를 단일 LLM 호출에서 *직접 emit*. 옛 결정적 빌더 (`visual_builder.build_chart_payload`) + `auto-init by element id` 패턴 + `maplibre-gl` 의존 모두 폐기. mono guide §2 (d3 + d3-geo + TopoJSON) + §4 (45° 패턴 시스템) 정합.

#### Added
- `ComposedSection.charts: list[dict]` — 차트 데이터 inline. `{type, title, data, note?}`. 8종 type: `bar / donut / line / gantt / network / stacked / bubble / heatmap`.
- `ComposedReport.embedded_map: dict | None` — 보고서 레벨 단일 지도. `{center, zoom, markers, arcs, legend?}`.
- `charts.js` 전면 재작성 — 섹션마다 `<script class="chart-payload-inline">` 스캔, mono guide §4 패턴 (hatch-tight / hatch-wide / dots / accent-hatch) 자동 적용.
- `maps.js` 전면 재작성 — `d3.geoMercator` + `topojson.feature(world-atlas/110m)` 베이스맵, 외부 타일 서비스 의존 0.
- `freeform_essay.html` 의 closing 앞에 `#freeform-map` 영역 + `#map-payload` 스크립트 (composer 가 emit 했을 때만).

#### Changed
- composer SYSTEM_PROMPT — 차트 type 8종 별 data 스키마 명시. "수치 비교가 본문 이해에 결정적일 때만" 보수적 게이팅.
- `freeform_essay.html` — 옛 chart-id 기반 9개 if/elif 분기 (chart-scenarios / chart-figures / chart-severity / ...) 통째 폐기. 섹션마다 `sec.charts` 순회로 변경.
- `maps.css` — 옛 maplibre 용 `.block-map.theme-{light_mono,burgundy_mono}` 트리 통째 폐기. mono 토큰만으로 동적 적용하는 `.map-card / .map-stage` 만 남김.

#### Deprecated (호출 안 됨)
- `src/visual_builder.py:build_chart_payload()` — composer 가 직접 emit 으로 대체.
- `src/visual_builder.py:build_map_payload()` — 동일.
- `src/templates/blocks/map.html` (v3.4.0 추가분) — composer.embedded_map 으로 대체.

---

### v4.1.0 — ContextAnalyst → Opus 4.7

Tier 4 의 2-call 파이프라인에서 context 가 composer (Opus 4.7) 가 보는 *유일한* 사실 입력. 사실 추출 품질이 보고서 전체 품질의 상한선이라 모델을 한 세대 위로 통일.

#### Changed
- `src/agents/context_analyst.py` — `use_light_model=True → False` + `self.model_name = "claude-opus-4-7"` 직접 지정. config.model_name (Opus 4.6) 보다 한 세대 위.
- `src/orchestrator.py` — fast 모드의 context 다운그레이드 로직 + 모델 복원 코드 제거.
- `src/telegram_bot.py` — `/status` 의 ① 상황 분석관 모델 표시 갱신.

#### Effects
- 사실 추출 품질 상한 ↑ — 출처 1차/2차 구분 / 단위 보존 / 인과 순서 정확도.
- 비용: ~1.6~1.8× (vs v4.0.0). v3.5.0 deep (13-call) 대비 30~40% 수준.
- 지연: context 단계 ~10초 → ~25초 (총 ~30초 추가 추정).

---

### v4.0.0 — Tier 4 Unified Pipeline (MAJOR)

7개 분석 에이전트 + 11종 lens + 11종 archetype + 5단계 게이트 다중 파이프라인을 폐기하고 ContextAnalyst + UnifiedComposer 2회 LLM 호출로 압축. 보고서 자유도 최대화 + LLM 호출 ~85% 감소 + 지연 시간 ~60% 감소.

#### Pipeline change
- BEFORE (v3.5.0): context → strategy → gate1 → [players → dynamics → chain (deep만)] → scenarios → lens_pool 1~4종 → judgment → gate2 → visuals → composer → render. **LLM 호출 fast 5 / standard 8 / deep 13**.
- AFTER (v4.0.0): context → unified_composer → render. **LLM 호출 모든 모드 2회**.

#### Added
- `NarrativeComposer.compose_unified(context, mode)` — Opus 4.7 단일 호출에서 행위자 / 구조 / 시나리오 / 모순 분석 + 본문 작성.
- `ComposedReport.watch_signals: list[dict]` — Watchlist Registry 통합용. 기존 `ScenarioArchitect` 출력 대체.
- `ComposedReport.contradictions: list[dict]` — Anti-pattern #5 (모순 봉합 금지) 보존.
- `ComposedReport.confidence_summary: str` + `confidence_score: float` — composer 자체 신뢰도 평가.
- `freeform_essay.html` 에 contradictions / watch_signals / confidence 노출 섹션 추가.

#### Removed (호출 안 됨, 파일 보존)
- `_generate_analysis_strategy` LLM 호출 (event_type / intent / lenses / archetype 결정).
- Quality Gate 1 (계획 sanity) + Gate 2 (커버리지) LLM 검증.
- `PlayerAnalyst / DynamicsAnalyst / ChainReactionAnalyst / ScenarioArchitect` 호출.
- `SynthesisJudge.judge()` (모순/판단 LLM 검사).
- `_run_lenses()` (lens pool 1~4 LLM 호출).
- `VisualAnalyst.analyze()` (LLM 시각화 + 결정적 빌더 양쪽 모두).
- `select_archetype()` matrix 라우팅 — 항상 `freeform_essay`.

#### Changed
- `token_budget.py` — 모든 모드 `max_llm_calls=2`, `max_lenses=0`. mode 는 composer prompt 깊이 지시만 결정.
- orchestrator `run_analysis()` — ~370줄 → ~120줄.

---

### v3.5.0 — Composer to All Modes + Mono Theme Standard

`narrative_composer` (Opus 4.7) 를 fast/standard 에도 활성화 + 멀티컬러 6테마 폐기 + DATA DASHBOARD 9개 차트 무지성 박힘 차단.

#### Added
- `token_budget.for_mode("fast"|"standard")` 에 `use_llm_narrative_composer=True`. cap 상향 (fast 4→5, standard 7→8).
- `report.css` 의 `burgundy_mono` + `light_mono` 정의 (mono guide §3 팔레트).
- `freeform_essay.html` 에 contradictions / watch_signals / confidence 노출 섹션 (v4.0.0 으로 이어짐).

#### Removed
- `report.css` 의 6 멀티컬러 테마 (burgundy / geopolitical / financial / tech / nature / liquidglass) 통째 삭제.
- `report_block.html` 의 "DATA DASHBOARD / 한눈에 보기" 섹션 (9개 차트 슬롯) — composer-referenced 만 freeform_essay.html 이 렌더하는 정책으로 통일.

#### Changed
- `lens_policy.select_theme()` — multi-color 6테마 매핑 → mono 2종만. policy → light_mono, 그 외 → burgundy_mono.
- 모든 템플릿 (report_block / freeform_essay / financial_transmission / tech_decomposition) 디폴트 `data-theme` → `burgundy_mono`.
- `AnalysisStrategy.theme` 디폴트 + `_empty_strategy_fallback` + orchestrator fallback 모두 `burgundy_mono`.

---

### v3.4.7 — AMC 전체 archetype 적용 + required_inputs 검증 (PR4)

PR3 후속. PR3 에서 5개 archetype 만 contract() 선언 → PR4 에서 **나머지 7개까지 전체 12개 archetype 에 적용** + required_inputs 런타임 검증 추가.

#### Added — 7개 archetype 에 contract() + narrative_stage 태깅
- `geopolitical_strategic`: mandatory `[fact, mechanism, divergence, trigger]`, forbidden `[decision_matrix]`
- `industry_value_chain`: mandatory `[fact, mechanism, divergence, trigger]`
- `policy_implementation`: mandatory `[fact, mechanism, divergence, decision]`
- `tech_decomposition`: mandatory `[fact, mechanism, divergence, decision]`, forbidden `[scenario_table]`
- `timeline_first`: mandatory `[fact, divergence]`, forbidden `[decision_matrix, scenario_table]` (what_happened 전용 — 사실 정리가 본분)
- `freeform_essay`: 느슨한 contract (composer 가 stage 자율 결정 — mandatory_stages 비어있음)
- `six_act_theater`: mandatory `[fact, mechanism, divergence, trigger]` (legacy 라 enforcement 트리거 안 됨, 일관성/디버깅용)

→ **이제 12개 archetype 전체가 narrative_stage 태깅 + contract() 선언**. 모든 archetype 에서 stage 배지가 시각화되고 mandatory stage 미달 시 경고 가시화.

#### Added — required_inputs 런타임 검증
- `ReportSynthesizer._check_required_inputs()` 신설: contract.required_inputs 가 result 에 실제로 채워졌는지 검증.
  - `FullAnalysisResult.<field>` 가 None → missing
  - Pydantic 모델 인스턴스이지만 모든 list/dict/str 필드 비어있음 → missing
- `_build_blocks` 가 시작 시 검증, 누락 시 WARNING 로그.
- 첫 블록 `__amc__` 메타에 `required_inputs` + `missing_inputs` 기록.
- `report_block.html` 의 AMC 경고 배너가 누락된 입력도 표시 ("누락된 필수 입력: context, players").

#### Tests
- `test_amc_narrative_dsl.py` 확장:
  - **`TestArchetypeStageCoverage`**: 5개 individual test → `parametrize` 로 11개 strict archetype 전체 검증 (freeform_essay 는 별도)
  - **`TestArchetypeNoSelfViolation`**: 동일하게 11개 전체 자가 모순 검증
  - **`TestAllArchetypesHaveContract`** (신설): 12개 archetype 모두 callable contract() 노출 + AnalysisMethodContract 인스턴스 반환
  - **`TestRequiredInputsCheck`** (신설): _check_required_inputs 4개 테스트 (None / 빈 모델 / 데이터 있음 / 부분 누락)
- 결과: `pytest src/tests/` **202 passed, 4 skipped** (PR3 175 + PR4 27 신설). skip 4개는 mandatory_stages 또는 forbidden_blocks 가 비어있는 archetype 의 parametrize 항목.

#### Code quality
- Pydantic V2.11 deprecation 경고 해소: `obj.model_fields` → `type(obj).model_fields` (V3.0 에서 제거 예정).

---

### v3.4.6 — AMC + Narrative DSL (PR3) — 단조로움의 구조적 처방

PR1'/PR2 후속. 사용자 지적 *"기법 다양성을 주문했는데 형식이 늘 비슷함"* (REFACTOR_V3_PLAN §6) 의 **구조적** 처방.

문제의 본질은 LLM 능력 부족이 아니라 *아키텍처가 다양성을 보존·증폭하지 못하고 기본형으로 수렴*시키는 것. archetype 들은 표면상 다른 `block_types` 를 선언하지만 빌더가 archetype-blind 라 결국 같은 모양으로 평탄화됨. PR3 는 두 메커니즘으로 해결:

#### Added — Narrative DSL (5단계)
- **`NarrativeStage` Literal** (`src/models.py`): `fact / mechanism / divergence / decision / trigger` — 보고서 흐름의 5단 분석 단계.
- **`ReportSectionPlan.narrative_stage`** (optional): archetype 작성자가 각 섹션이 어느 단계인지 선언. backward-compat (None 허용).
- **시각 차별화** (`report.css`):
  - 섹션 헤더에 stage 배지 (색상이 단계별 — fact=blue / mechanism=gold / divergence=orange / decision=green / trigger=red)
  - 섹션 자체에 좌측 컬러 액센트 (스크롤하면서 단계 흐름이 한눈에 보임)
- 결과: 같은 archetype 의 섹션도 단계별로 시각적으로 분리되어 *단조로움 직접 해소*.

#### Added — AMC (Analysis Method Contract)
- **`AnalysisMethodContract` Pydantic model**: `method_id`, `required_inputs`, `mandatory_stages`, `forbidden_blocks`, `rationale` 필드.
- **archetype 별 `contract()` 메서드** (5개 구현):
  - `scenario_first`: mandatory `[fact, divergence, trigger]`, forbidden `[decision_matrix]`
  - `decision_brief`: mandatory `[fact, divergence, decision, trigger]`
  - `mechanism_decomp`: mandatory `[fact, mechanism, divergence]`, forbidden `[scenario_table, decision_matrix]`
  - `accident_forensic`: mandatory `[fact, mechanism, decision]`, forbidden `[scenario_table]`
  - `financial_transmission`: mandatory `[fact, mechanism, divergence, trigger]`, forbidden `[decision_matrix]`
- **default_contract()** helper: contract() 미선언 archetype 은 빈 contract → backward-compat.
- **synthesizer enforcement** (`_build_blocks`):
  - `forbidden_blocks` 등재된 block_type 은 빌더 실행 전 reject + INFO 로그
  - 빌드 후 mandatory stage 미달 시 WARNING 로그
  - 첫 블록 payload 에 `__amc__` 메타 부착 (covered/missing stages 기록)
- **템플릿 가시화** (`report_block.html`): AMC 미달 시 보고서 상단에 ⚠ 경고 배너 — 어떤 분석 단계가 빠졌는지 사용자에게 직접 노출.

#### Why this fixes monotony
이전: 5개 archetype 모두 `narrative` + `decomposition` + `matrix` + ...를 비슷한 순서로 호출 → *결과물이 비슷해 보임*. <br>
이후: 같은 `narrative` block 도 한 섹션은 `stage="fact"` (파란 배지), 다른 섹션은 `stage="divergence"` (주황 배지) → *시각·의미적으로 분리*. archetype 간 차별화는 mandatory_stages 차이 (decision_brief 만 `decision` 강제, accident_forensic 만 `decision`+`mechanism` 강제 등) 로 *구조적으로* 보장.

#### Tests
- `test_amc_narrative_dsl.py` 신설 — 19개 테스트:
  - `TestNarrativeStageField` (4): NarrativeStage Literal 동작 + ReportSectionPlan 확장
  - `TestAnalysisMethodContract` (3): AMC 모델 동작 + default_contract helper
  - `TestArchetypeContracts` (5): 5개 archetype 모두 contract() 선언 검증
  - `TestArchetypeStageCoverage` (5): 각 archetype 의 section_plan 이 자기 mandatory_stages 를 모두 커버 (자가 정합성)
  - `TestArchetypeNoSelfViolation` (2): forbidden_blocks 가 자기 section_plan 안에 없음 (자가 모순 방지)
- 결과: `pytest src/tests/` **175 passed** (PR2 156 + PR3 19).

#### Roadmap (남은 작업)
- 6개 archetype (geopolitical_strategic / industry_value_chain / policy_implementation / tech_decomposition / timeline_first / freeform_essay) 에 contract() + stage 태깅 → backward-compat 라 점진 가능.
- lens 단위 contract (현재는 archetype 단위만). lens 가 fact/mechanism 출력을 강제하는 형태로 확장 가능.
- AMC `required_inputs` 가 *충족 안 되면* archetype 자체 라우팅 거부 (현재는 경고만).

---

### v3.4.5 — Scenario data enrichment (PR2)

PR1' 후속. 사용자 진단 #2 (시나리오 시인성)의 *완성판* — 확률 bar 외에 **신뢰도** 와 **선행 신호** 를 시각화.

#### Added
- **`ScenarioAnalysis.scenarios[*].confidence`** (0.0~1.0 또는 0~100) — 이 시나리오 판단의 신뢰도. `scenario_architect` SYSTEM_PROMPT 가 LLM 에 요청. `visual_builder.build_scenario_table` 이 dict (`{raw, label}`) 로 정규화 (raw는 0~100 정수, label은 "높음/중간/낮음/매우 낮음").
- **`ScenarioAnalysis.scenarios[*].driver_signals`** (list[str] 또는 list[dict]) — 이 시나리오로의 분기를 *현재 관측 가능한* 형태로 식별하는 선행 지표 (최대 4개). visual_builder 가 dict/string 양쪽 입력 받아 정규화.
- **scenario_table.html 렌더 보강**:
  - 카드 헤더에 **신뢰도 배지** (`scenario-card-confidence`) — 색상이 신뢰도에 따라 변화 (높음=녹색, 중간=골드, 낮음=주황, 매우낮음=빨강).
  - **"선행 신호" 섹션** (`scenario-card-signals`) — 칩 형태 list, 각 칩 앞에 ► 마커.
- **scenario_architect prompt** 가 impact_by_player 의 impact 텍스트에 정량 강도 단어("극심한 타격", "높은 충격", "중간 영향", "낮은 파급") 포함을 권장. PR1'의 `_impact_magnitude` 가 추출하여 stacked chart 의 segment 가중치로 사용.

#### Backward compatibility
- 모든 신규 필드는 *optional*. `ScenarioAnalysis.scenarios` 는 여전히 `list[dict]` (loose). LLM 출력에 confidence/driver_signals 없으면 `confidence=None`, `driver_signals=[]` → 템플릿이 조건부 렌더 (`{% if sc.confidence %}` / `{% if sc.driver_signals %}`).
- 기존 시나리오 데이터(probability/description/impact_by_player만 있음)는 그대로 동작.

#### Tests
- `TestScenarioTable` 클래스 신설 — 6개 테스트:
  - `test_passes_confidence_as_float` (0~1 입력)
  - `test_passes_confidence_as_percent` (0~100 입력)
  - `test_omits_confidence_when_missing`
  - `test_extracts_driver_signals_from_string_list`
  - `test_extracts_driver_signals_from_dict_list`
  - `test_summarizes_impact_by_player`
- 결과: `pytest src/tests/` **156 passed** (PR1' 150 + PR2 6).

#### Roadmap
- **PR3** (별도 세션): AMC (Analysis Method Contract) + Narrative DSL — 단조로움의 *구조적* 처방.

---

### v3.4.4 — Quality fixes (PR1')

샘플 보고서(`analysis_20260501_165647`)에서 관찰된 6가지 품질 문제 중 v3.4.3 이후에도 *여전히 미해결인 4개*만 처리. 시나리오 모델 강화(PR2)와 AMC + Narrative DSL(PR3)은 후속.

#### Fixed
- **차트 테마 미동기 (#1)** — `src/templates/static/charts.js` 의 `TOKENS` 상수가 burgundy hex(`#321F1F`, `#C9A84C` 등) 하드코딩 → `getComputedStyle` 로 `:root` 의 `--card / --gold / --green / --orange / --red / --blue / --text-*` CSS 변수 읽기. 페이지 `data-theme` (geopolitical/financial/tech/nature/liquidglass) 와 차트 팔레트 자동 동기화. fallback 으로 burgundy 유지.
- **무지성 차트 (#3)** — `src/visual_builder.py`:
  - `build_key_figures_chart_data`: 숫자 추출 실패 시 `1.0` 폴백 제거 (균등 도넛 안티패턴 차단). 항목 < 3 이거나 모든 값 동일이면 빈 list → 도넛 미생성.
  - `build_stacked_chart_data`: 모든 segment `value=1` 하드코딩 제거. `_impact_magnitude()` 가 (a) 명시적 `impact_score/magnitude/weight` 필드, (b) impact 텍스트의 키워드("극심"/"높음"/"중간"/"낮음" 등) 우선순위로 정량값 추출. 추출 실패 segment skip, ≥4 segment + variance>0 일 때만 차트 생성.
- **빈 placeholder 블록 (#5 부분)** — `_payload_claim_card / _payload_evidence_table / _payload_qna` 가 빈 dict 대신 `None` 반환. 기존엔 빈 카드/표가 매 보고서에 렌더되어 단조로움의 직접 원인.
- **모바일 cram (#6 부분)** — `src/templates/report.css` 에 `@media (max-width:540px)` 추가:
  - `block-timeline-item` 세로 스택 (이전: `display:flex` + `min-width:110px` 날짜 → 좁은 폭에서 셀 안 텍스트가 한두 글자씩 흘러내림).
  - `evidence_table / risk_matrix` 테이블 → 카드 스택 변환 (`<thead>` 숨김, `<tr>`→카드, `<td>`→라벨된 행). `<td>` 에 `data-label` 속성 추가하여 카드 모드에서 라벨 표시.

#### Already-fixed-on-main (verified, no work needed)
- **#2 시나리오 시인성** — `scenario_table.html` 이 이미 `scenario-grid` + 확률 bar (v3.2.0). 단 `confidence`/`driver_signals` 필드는 **PR2 범위**.
- **#4 차트 빈 공간** — `charts.js` 가 이미 dynamic SVG sizing + `aspect-ratio` + 모바일 breakpoint (v3.2.0).
- **#5 단조로움 (부분)** — Narrative Composer (v3.3.0) 가 deep mode 에서 freeform 에디토리얼. AMC 등 구조적 처방은 **PR3 범위**.

#### Tests
- `test_chart_builders.py` 중 4개 테스트가 *이전의 잘못된 동작*(value=1 fallback, `1.0` default)을 검증하고 있어 **새 (올바른) 동작**에 맞게 갱신:
  - `test_extracts_numeric_value`: 3+ figures 로 변경 (Insight Gate 충족)
  - `test_falls_back_to_one_when_no_number` → `test_skips_when_no_number` (정정된 동작 검증)
  - `test_skips_when_uniform_values` 신설
  - `test_builds_segments_per_scenario` → `test_builds_segments_with_varied_magnitudes` (variance>0 검증)
  - `test_returns_none_when_uniform_magnitudes` 신설
  - `test_omits_empty_chart_types`: 1개 figure → key_figures omit (Insight Gate 동작 명시)
  - `test_full_payload_with_all_data`: 3+ figures + 변동성 있는 stacked
- 결과: `pytest src/tests/` **150 passed** (이전 144 + 신설 6).

#### Roadmap
- **PR2** (다음): `ScenarioAnalysis` 모델에 `confidence` + `driver_signals` 필드 추가. `visual_builder.build_scenario_table` 추출 + `scenario_table.html` 배지 렌더.
- **PR3** (별도 세션): AMC (Analysis Method Contract) — 기법별 `required_inputs / output_schema / mandatory_sections / forbidden_fallbacks` 선언. + Narrative DSL (fact→mechanism→divergence→decision→trigger). 사용자 지적 "기법 다양성을 주문했는데 형식이 늘 같음"의 *구조적* 처방.

---

## [3.4.3] — 2026-05-01

> **핫픽스 — v3.4.0 회귀 수정.** `_payload_map()` 이 `result.report_theme` 을 읽어 light/burgundy 분기를 시도하지만, `FullAnalysisResult` 모델에 해당 필드가 없어 `synthesize()` 초입의 `result.report_theme = theme` 할당이 Pydantic ValidationError 를 던졌다. 결과: 모든 보고서 생성이 `❌ 분석 실패: "FullAnalysisResult" object has no field "report_theme"` 로 실패. **한 줄 패치 — 모델에 필드 추가.**

### Changed
- **`src/models.py:FullAnalysisResult`** — `report_theme: str = ""` 필드 추가. SSOT (`NarrativePlan.report_theme`) 과 별개로 block builder 가 읽는 채널.
- **`src/orchestrator.py:VERSION`** `v3.4.2 → v3.4.3`

### Migration
- **VM 재기동 필요**.
- 분석 흐름은 그대로. Block builder 의 theme 분기가 이제 정상 작동.

---

## [3.4.2] — 2026-05-01

> **`/stop` `/stopall` — 진행 중 분석 텔레그램에서 직접 중단.** `_run_analysis` 시작 시점에 `asyncio.current_task()` 를 보관해 두고, `/stop` 핸들러가 `cancel()` 호출 → `CancelledError` 가 위로 전파되며 LLM 호출 / 서브프로세스 / await 체인 모두 정상 종료. `/stop` 은 현재 1건만, `/stopall` 은 큐까지 전부 비움. 인가 체크는 `/analyze` 와 동일 (`_is_authorized`).

### Added
- **`src/telegram_bot.py:_stop_command()`** — 진행 중 분석만 cancel. 큐는 보존. 메시지: `🛑 분석 중단 요청 보냄: <topic>\n정리 후 곧 종료됩니다.\n📋 대기열 N건 은 그대로 유지.`
- **`src/telegram_bot.py:_stopall_command()`** — 진행 중 분석 cancel + `self._queue.clear()`. 메시지: `🛑 전체 중단: 진행 중 분석 (<topic>) 취소 + 대기열 N건 비움.`
- **`src/telegram_bot.py:TelegramBot.__init__`** — `self._current_task: asyncio.Task | None = None` 인스턴스 변수.

### Changed
- **`src/orchestrator.py:VERSION`** `v3.4.1 → v3.4.2`
- **`src/telegram_bot.py:_run_analysis()`** — 시작 시점에 `self._current_task = asyncio.current_task()` 캡처. `except asyncio.CancelledError` 블록 추가 (사용자에게 "🛑 분석 중단됨" 알림 후 re-raise). `finally` 에서 `self._current_task = None`. `await self._process_queue()` 는 finally 에서 그대로 — `/stop` 후에도 큐 진행 (스킵하려면 `/stopall` 사용).
- **`src/telegram_bot.py:create_app()`** — `CommandHandler("stop", ...)` + `CommandHandler("stopall", ...)` 등록.
- **`src/telegram_bot.py:_start_command()`** — 도움말에 `/stop`, `/stopall` 두 줄 추가.

### Migration
- **VM 재기동 필요** — 코드 변경.
- 기존 동작 변경 없음. 새 명령만 추가.

### 동작 노트
- `CancelledError` 는 Python 3.8+ 부터 `BaseException` 상속이라 `except Exception:` 에 안 잡힘 — orchestrator/agent 의 일반 except 블록을 통과해 위로 전파.
- subprocess 기반 Claude CLI 호출 (`asyncio.create_subprocess_*`) 도 cancel 시 SIGTERM 전파됨.
- 부분적으로 생성된 `reports/` 임시 파일은 그대로 남을 수 있음 — 다음 분석에 영향 없음, 추후 cleanup 필요시 별도 작업.

---

## [3.4.1] — 2026-05-01

> **`/status` build info — 운영 디버깅 가속.** 봇 프로세스가 시작될 때 git 상태 (branch / short commit / commit date / dirty) 를 한 번 캡처해 `src/orchestrator.py:BUILD_INFO` 에 보관. 시작 로그 (`Starting Event Analysis Team bot — v3.4.1 · branch=main · commit=af9443d (...)`) 와 텔레그램 `/status` 응답 모두에 노출. *실행 중인 코드*의 커밋을 가리키므로 (pull 후 재기동을 안 한 케이스 포함) 운영자가 버전 미스매치를 즉시 알 수 있다.

### Added
- **`src/orchestrator.py:_capture_build_info()` + `BUILD_INFO`** — `git rev-parse --abbrev-ref HEAD` / `--short=7 HEAD` / `git log -1 --format=%cd --date=format:...` / `git status --porcelain` 4개 호출 (각 timeout 2s, stderr 무음). 실패 시 `"?"` 로 graceful degrade. import 시점에 1회만 실행 — 이후 disk 변경은 반영되지 않으며 이게 *목적*이다.

### Changed
- **`src/orchestrator.py:VERSION`** `v3.4.0 → v3.4.1`
- **`src/main.py:main()`** — `app.run_polling()` 직전 `logger.info("Starting Event Analysis Team bot — %s · branch=%s · commit=%s (%s)%s", ...)` 추가. 운영자가 tmux 첫 줄에서 즉시 확인.
- **`src/telegram_bot.py:_status_command()`** — `브랜치` / `커밋` 두 줄 추가 (`✅ 봇 실행 중` 직후, `가동시간` 위). dirty 일 때 `⚠️ uncommitted` 표기.

### Migration
- **VM 재기동 필요** — 코드 변경. 재기동 후 시작 로그와 `/status` 출력에 새 줄이 보여야 정상.
- 비-git 환경 / repo 외부에서 실행 시 `BUILD_INFO` 가 모두 `"?"` 로 표시됨 — 의도된 동작.

---

## [3.4.0] — 2026-05-01

> **`map` BlockType — MapLibre + d3-geo 지도 블록 통합.** 보고서 파이프라인에 maplibre-gl 4.7 + d3-geo v7 기반 지도 블록을 정식 추가. `BlockType` Literal 18번째로 `"map"` 등록. light_mono / burgundy_mono 두 테마와 골드(#C9A84C) 단일 하이라이트 원칙은 `samples/theme_mono_map_chart.html` 의 검증된 디자인을 그대로 옮긴다. 데이터 소스는 기존 `visual_analyst` 의 `leaflet_config` 를 재사용해 분석 흐름 변경 없이 시각화만 교체. 데이터 없으면 빌더가 None 반환 → 자동 스킵.

### Added
- **`src/templates/blocks/map.html`** — 새 블록 템플릿. `data-block-id` + `theme-light_mono`/`theme-burgundy_mono` 클래스 + `<script type="application/json">` 페이로드. 초기화는 `maps.js` 가 `DOMContentLoaded` 에 일괄 처리.
- **`src/templates/static/maps.js`** — `window.MapBlocks.initAll()` 진입점. maplibre-gl 인스턴스 생성, `d3.geoTransform` 으로 maplibre `map.project()` 를 d3-geo path projection 에 위임, `d3.geoInterpolate` 로 great-circle arc 64분할. `move`/`resize` 이벤트마다 SVG 오버레이 재투영. 244 lines, no deps beyond global `maplibregl` + `d3`.
- **`src/templates/static/maps.css`** — 블록 컨테이너·헤드·스테이지·범례·캡션 + 두 테마 CSS variables. 버건디는 `voyager_nolabels` 베이스 + `grayscale → sepia → hue-rotate(-22deg) → brightness(0.78)` 필터로 마룬 합성, 라이트는 `light_nolabels` + `grayscale → contrast(0.96) → brightness(1.04)`.
- **`src/visual_builder.py:build_map_payload()`** — leaflet_config (legacy `[lat,lng]`) → MAP block payload (`[lng,lat]`) 변환기. marker color/emoji 로 highlight 결정, line color 명시 시 highlight, 매칭 안 되는 line endpoint 는 placeholder 노드로 합성. legend 도 자동 생성.
- **`src/agents/report_synthesizer.py:_payload_map()`** — `result.visuals.leaflet_config` 가 enabled 일 때만 payload 빌드. theme 은 `result.report_theme` 을 따라 burgundy/light 분기. `_BLOCK_BUILDERS["map"]` 에 등록.
- **`src/tests/test_map_block.py`** — 13 케이스 (BlockType 검증, leaflet → maplibre 좌표 변환, highlight 룰, theme 분기, legend 자동 생성, placeholder 노드 합성, 빌더 등록).

### Changed
- **`src/orchestrator.py:VERSION`** `v3.3.1 → v3.4.0`
- **`src/models.py:BlockType`** Literal 에 `"map"` 추가 (17 → 18종).
- **`src/agents/report_synthesizer.py:STATIC_ASSETS`** `+ "maps.js", "maps.css"` (보고서 디렉토리 동기화 대상).
- **`src/agents/report_synthesizer.py:synthesize()`** `result.report_theme = theme` 를 초입에 기록 → block builder 가 light/burgundy 분기 가능.
- **`src/templates/report_block.html`** + **`src/templates/archetypes/freeform_essay.html`** — `has_map_block` 분기로 maplibre-gl CSS/JS + `maps.css`/`maps.js` + `d3.v7.min.js` 조건부 로드. 차트 블록과 d3 공유.
- **`src/archetypes/geopolitical_strategic.py`** — "전장·행위자" 섹션의 `block_types` 에 `"map"` 선두 추가. 데이터 없으면 자동 스킵.

### LLM 호출 수 변화
- 없음. 결정적 빌더만 추가.

### 보고서 디자인 변화
- `geopolitical_strategic` archetype 으로 라우팅된 보고서 + visual_analyst 가 `leaflet_config` 를 enabled 로 산출한 경우 → "전장·행위자" 섹션 상단에 maplibre+d3-geo 지도 블록이 등장. 기존 Leaflet 시각화 (`report.html` six_act_theater 경로) 는 그대로 유지.
- freeform_essay (deep 모드) 도 `_build_all_available_blocks` 에서 자동으로 map 블록 빌드 → composer 가 `embedded_blocks` 에 `"map"` 을 referencing 하면 본문에 박힘.

### Migration
- 기존 보고서 URL 계속 동작.
- visual_analyst 프롬프트 / 산출물 스키마 변경 없음 — `leaflet_config` 를 그대로 사용.
- **VM 재기동 필요** (코드 변경, 정적 자산 추가).
- 보고서 디렉토리에 `maps.js` / `maps.css` 가 처음 보고서 생성 시 자동 동기화됨.

---

## [3.3.1] — 2026-05-01

> **Sample 추가 (showcase only).** 보고서 파이프라인에는 변화 없음 — 디자인/톤앤매너 검증용 독립 HTML 페이지 1개 추가.

### Added
- **`samples/theme_mono_map_chart.html`** — maplibre-gl 4.7 + d3-geo v7 단일 페이지 샘플. 라이트 모노 (#FAFAF7 크림) / 버건디 모노 (#2B1A1A 마룬) 두 팔레트에 동일 데이터셋 (동북아·동남아 항만 네트워크 + 16주 컨테이너 처리량) 을 입혀 비교. 두 테마 공통 하이라이트 `#C9A84C` (골드) 로 부산↔싱가포르 회랑·관측 노드·14주차 피크 막대만 강조. 베이스 타일은 CartoDB `light_nolabels` / `dark_nolabels` + CSS 필터(`grayscale` / `sepia + hue-rotate`) 합성. d3.geoTransform 으로 maplibre `map.project()` 를 d3-geo path 에 위임, `d3.geoInterpolate` 로 great-circle arc 64분할.

### Changed
- **`src/orchestrator.py:VERSION`** `v3.3.0 → v3.3.1`
- **`README.md`** Status / Recent Changes / `last_synced_with` 갱신

### Not Changed (중요)
- **보고서 생성 파이프라인은 v3.3.0 과 동일.** 이 샘플은 `src/templates/`, `src/visual_builder.py`, `src/agents/visual_analyst.py`, `src/models.py:BlockType` 어디에도 연결되지 않은 **독립 쇼케이스**. 텔레그램 보고서가 maplibre 지도를 포함하려면 별도 통합 작업 (BlockType 추가, 블록 빌더, 템플릿 임베드, archetype 라우팅) 이 필요하며 이는 v3.4.0 이상에서 다룬다.
- VM 재기동 불필요 (런타임 동작 변화 없음).

---

## [3.3.0] — 2026-04-30

> **Narrative Composer (Opus 4.7) — Freeform Editorial Pass.** 보고서가 17 BlockType 슬롯에 데이터를 부어넣는 정형 구조에서 벗어나, deep 모드에서 Opus 4.7 단일 콜이 *편집장* 역할로 사건 성격에 맞춰 섹션 수/길이/순서/톤을 자유 결정. 차트는 composer 가 본문에 박는 자리만 결정하고 (auto-dashboard 폐지), 데이터 빌드는 그대로 결정적. fast/standard 모드는 영향 없음.

### Added
- **`src/agents/narrative_composer.py`** `NarrativeComposer` — Opus 4.7 (`claude-opus-4-7`) 단일 콜로 `ComposedReport` 산출. 전체 분석 결과 + claim 카탈로그 + 차트 catalog 를 입력으로 받음. CLI/API 모드 모두 지원, max_tokens=8192. 실패 시 `None` 반환하여 호출자가 폴백.
- **`src/models.py:ComposedReport`** + **`ComposedSection`** — composer 산출물 Pydantic 모델. `embedded_charts: list[chart_id]` + `embedded_blocks: list[block_type]` + `cited_claim_ids` 로 evidence 추적성 보존 (Anti-pattern #4 우회 금지).
- **`src/models.py:FullAnalysisResult.composed_report`** — composer 출력 보유 필드. None 이면 폴백 archetype 으로 라우팅.
- **`src/archetypes/freeform_essay.py`** + **`src/templates/archetypes/freeform_essay.html`** — composer 출력 전용 archetype + 템플릿. 산문 우위 디자인 (max-width 780px, Noto Serif KR 헤드라인, 최소한의 chrome). select_archetype matrix 가 아니라 orchestrator 가 deep + 성공 시 *명시* 라우팅.
- **`src/visual_builder.py:build_chart_catalog()`** + **`chart_id_to_payload_key()`** — 데이터 가용한 차트만 `[{id,title,hint}]` 로 노출. composer prompt 입력에 포함되어 invalid chart_id reference 방지.
- **`src/agents/report_synthesizer.py:_build_all_available_blocks()`** — freeform_essay 용 블록 빌더. section_plan 무관하게 가용한 BlockType 마다 1개씩 빌드 → composer 가 type 으로 referencing.
- **`src/tests/test_narrative_composer.py`** — 16 pytest 케이스 (chart catalog 필터링, ComposedReport/Section 모델, parser, reference validator, archetype 등록, token budget gating, payload builder).

### Changed
- **`src/orchestrator.py:VERSION`** `v3.2.0 → v3.3.0`
- **`src/orchestrator.py:run_analysis`** — judgment + visuals 직후 `narrative_composer.compose()` 호출 (deep 모드만). 성공 시 archetype 을 `freeform_essay` 로 *명시* 라우팅 (matrix 우선순위 무시). 실패 시 `select_archetype()` 폴백.
- **`src/orchestrator.py:Orchestrator.__init__`** + **`_wire_telemetry`** — `narrative_composer` 인스턴스 등록 + telemetry 와이어링.
- **`src/token_budget.py:TokenBudget`** — `use_llm_narrative_composer: bool` 필드 신규. deep=True, 그 외 False. deep 의 `max_llm_calls` `12 → 13` (composer +1).
- **`src/archetypes/registry.py`** — `freeform_essay` 추가 (총 12종).

### LLM 호출 수 변화
- fast/standard: 변화 없음 (composer 비활성).
- deep: `+1 Opus 4.7 콜` (max_tokens 8K, 입력 ~30~50K). 총 12 → 13. 기존 `_generate_executive_summary` / `_generate_narrative_plan` 보조 콜은 그대로 유지 (composer 출력이 메인 본문, deterministic summary 는 hero 영역).

### 보고서 디자인 변화
- deep 모드 보고서: 정형 17 슬롯 매핑이 아닌 **3~7개 자유 섹션** + 사건 성격에 맞춘 헤드라인/부제. Auto-dashboard 폐지 — 차트는 본문 흐름에 따라 composer 가 적재적소에 embed.
- Evidence 추적성: 본문에 등장하는 핵심 주장 옆에 `cited_claim_ids` (claim_id 목록) 인용 표기.
- fast/standard: v3.2.0 과 동일 (auto-dashboard + 정형 archetype).

### Migration
- 기존 보고서 URL 계속 동작.
- `FullAnalysisResult.composed_report` 필드는 optional — 기존 코드 영향 없음.
- 새 archetype `freeform_essay` 는 select_archetype() matrix 에 포함되지 않음 (orchestrator 만 라우팅).

---

## [3.2.0] — 2026-04-30

> **d3 Chart Dashboard + Mobile-first Scenario Cards.** 보고서 시각화 품질을 대폭 강화하는 minor 릴리스. d3 v7 라이브러리 인라인 임베드 (정적 자산) + 9종 차트 라이브러리 + 모바일 우선 시나리오 카드. 보고서가 데이터 가용성에 따라 자동으로 적절한 차트들을 모두 생성. v3.1.0 의 token budget 정책은 그대로.

### Added
- **`src/templates/static/d3.v7.min.js`** — d3 v7.9.0 minified (~274KB). Cloudflare Pages 에 정적 자산으로 배포되어 외부 CDN 의존 없음.
- **`src/templates/static/charts.js`** — 9종 d3 SVG 차트 라이브러리 (~700 lines). 모두 hover 인터랙션 + 진입 애니메이션 + 자체 디자인 토큰.
  1. `drawScenarioBar` — 시나리오 확률 가로 막대 (gradient + tag 색띠)
  2. `drawKeyFiguresDonut` — 핵심 수치 도넛
  3. `drawSeverityHeatmap` — 인과 사슬 위험도 히트맵 (CSS 기반, PDF 안전)
  4. `drawConfidenceTriple` — 신뢰도 3축 막대
  5. `drawTimeseriesLine` — 시계열 라인 (area gradient + animated path)
  6. `drawStackedBar` — 시나리오 × 행위자 누적 막대
  7. `drawBubble` — 리스크 매트릭스 (확률 × 영향, 4사분면)
  8. `drawGantt` — 타임라인 간트 차트
  9. `drawNetwork` — 행위자 force-directed 네트워크 그래프
- **`src/templates/static/charts.css`** — 차트 + 시나리오 카드 + hero dashboard 디자인 토큰 (~250 lines). burgundy 테마 변수 상속.
- **`src/visual_builder.py`** 차트 데이터 빌더 8종 — `build_scenario_chart_data`, `build_key_figures_chart_data`, `build_severity_chart_data`, `build_confidence_chart_data`, `build_stacked_chart_data`, `build_bubble_chart_data`, `build_gantt_chart_data`, `build_network_chart_data`, `build_chart_payload` (모두 결정적, LLM 호출 0).
- **`src/agents/report_synthesizer.py:_sync_static_assets`** — 보고서 디렉토리에 d3/charts.js/charts.css 자동 복사 (size+mtime 기반 idempotent).
- **`samples/chart_gallery.html`** — 9종 차트 모두 한 페이지에 보여주는 샘플 갤러리.
- **`src/tests/test_chart_builders.py`** — 24 pytest 케이스 (각 차트 데이터 빌더, 통합, 정적 자산 존재, 시나리오 카드 템플릿 검증).

### Changed
- **`src/orchestrator.py:VERSION`** `v3.1.0 → v3.2.0`
- **`src/templates/blocks/scenario_table.html`** — 4컬럼 `<table>` 폐기 → 모바일 우선 카드 그리드 (`scenario-grid` + `scenario-card`). 모바일에서 1열, 720px+ 에서 2열. tag 별 색띠 (`최선`/`기본`/`악화`/`최악`), 확률 큰 숫자 + gradient bar, 영향을 sentiment 색 칩으로 표시.
- **`src/templates/report.html:render_scenarios`** — 동일하게 카드 그리드로 통일. 표 마크업 완전 폐기.
- **`src/templates/report.html`** — 보고서 상단에 "한눈에 보기" (DATA DASHBOARD) 섹션 추가. 데이터 가용성에 따라 최대 8개 d3 차트 자동 렌더. 보고서 끝에 `<script type="application/json" id="chart-payload">` + d3.js + charts.js 로드.
- **`src/templates/report_block.html`** — 동일한 차트 대시보드 섹션 추가 (block dispatcher 경로 archetype 도 차트 동일하게 표시).
- **`src/agents/visual_analyst.py:VisualAnalyst.analyze(judgment=...)`** — 새 인자. deterministic 경로에서 신뢰도 차트 데이터 빌더 호출용.
- **`src/orchestrator.py:run_analysis`** — 시각화 단계를 SynthesisJudge 이후로 이동 (judgment.confidence 를 차트 데이터로 전달하기 위함).
- **`src/visual_builder.py:build_visuals(judgment=...)`** — 새 인자. `chart_config.payload` 에 8종 차트 데이터 dict 자동 채움.

### LLM 호출 수 변화
없음. 모든 차트는 결정적 빌더로 생성 (LLM 호출 0). v3.1.0 의 mode 정책 그대로 유지 — fast 4회, standard 7회, deep 12회.

### 보고서 크기 변화
- 보고서 HTML 자체: +2~5KB (chart payload + chart card markup)
- 정적 자산 (한 번만 다운로드 + 캐시): d3.v7.min.js 274KB + charts.js ~26KB + charts.css ~6KB = **306KB 추가** (Cloudflare 캐시 후 재방문 시 0KB)
- 첫 방문 시 Cloudflare CDN 에서 모든 자산 한 번에 다운로드 → 후속 보고서 방문은 캐시 사용

### 보고서 자동 차트 매트릭스
| 데이터 가용성 | 자동 생성되는 차트 |
|-----|-----|
| `scenarios` | 시나리오 막대 + (impact_by_player 있으면) 누적 막대 |
| `key_figures` | 도넛 |
| `chain.chain` | severity 히트맵 |
| `judgment.confidence` | 3축 신뢰도 막대 |
| `chain.wildcards` | 리스크 매트릭스 (버블) |
| `context.timeline ≥ 2건` | Gantt 타임라인 |
| `players.players + alliances` | force-directed 네트워크 그래프 |

데이터 없으면 해당 차트는 안 그림 (현재 정책 그대로).

### Migration
- 기존 보고서 URL 계속 동작 (마크업 변경만, 데이터 모델 변경 없음).
- `result.visuals.chart_config` dict 의 구조에 `payload` 키 추가됨 — 기존 `enabled`/`charts` 키는 그대로 유지 (LLM VisualAnalyst 산출물 호환).
- 봇 재시작 시 자동으로 d3/charts.js/charts.css 가 첫 보고서 생성 시 reports/ 로 복사되어 Cloudflare 에 배포됨.

---

## [3.1.0] — 2026-04-27

> **Token Budget + Mode Routing.** 보고서 품질을 유지하면서 입력 토큰·LLM 호출 수를 약 절반으로 줄이는 minor 릴리스. 한 사건에 모든 에이전트를 무조건 실행하던 기존 정책을 폐기하고, fast/standard/deep 3모드로 분기. v3.0.0 의 분석 모델·블록 시스템·archetype 11종은 그대로 유지.

### Added
- **`src/token_budget.py`** — `AnalysisMode` Literal (fast/standard/deep) + `TokenBudget` dataclass.
  - fast: 최대 LLM 호출 4회, lens 1개. quality gate / narrative plan / visual / synthesis LLM 모두 비활성. 페르소나 비활성. 메타 lens 비활성.
  - standard: 최대 LLM 호출 7회, lens 2개. 메타 lens 허용. synthesis LLM 은 contradictions / 저신뢰 / 미답변 risk 시에만 발화.
  - deep: 최대 LLM 호출 12회, lens 4개. 모든 LLM augmentation 활성 + 페르소나 호출.
  - `resolve_mode(event_description)` — 사용자 메시지의 키워드 (`짧게`/`간략히` → fast, `심층`/`자세히` → deep) 로 mode 결정. default `standard`.
- **`src/lens_policy.py`** — `select_lenses(event_type, user_intent, mode)` 코드 규칙 기반 lens 결정자.
  - 분야별 lens 우선순위 (tech_architecture / financial_transmission / accident_causality / policy_implementation / market_structure / geopolitical / stakeholder / structural / cascade).
  - 메타 lens (red_team / pre_mortem) 는 의사결정 / 취약점 / 전망 의도에서만 자동 추가.
  - `select_theme(event_type)` 코드 규칙 — Strategy Planner 프롬프트에서 분리.
- **`src/brief_builder.py`** + `src/models.py:AnalysisBrief`** — 후속 에이전트/렌즈에 전달할 *압축* 컨텍스트.
  - 모든 list 필드 길이 cap (BRIEF_MAX_FACTS=8, BRIEF_MAX_TIMELINE=6, BRIEF_MAX_ACTORS=5, BRIEF_MAX_CAUSAL=6, BRIEF_MAX_SCENARIOS=4, BRIEF_MAX_UNCERTAINTIES=4, BRIEF_MAX_SOURCES=8).
  - `compact()` — 빈 필드 자동 생략 dict 반환.
- **`src/visual_builder.py`** — 결정적 SVG 빌더 (`build_actor_relationship_svg`, `build_flow_chain_svg`, `build_scenario_table`, `build_visuals`). LLM 없이 SVG 생성. fast/standard 의 default. `needs_advanced_visuals()` 키워드 (지도/차트/시계열) 매칭.
- **`src/telemetry.py`** — `RunTelemetry` (사건당 인스턴스). 각 LLM 호출의 input/output char, elapsed ms, 단계별 timing, 선택된 lens / 스킵된 에이전트 / 스킵된 LLM 단계 기록. 보고서 완료 후 `log_summary()` 자동 호출.
- **`src/tests/test_token_optimization.py`** — 24 pytest 케이스 (TokenBudget 모드별 cap, resolve_mode 키워드, lens_policy 매핑, compact JSON serialization, AnalysisBrief 길이 제한, deterministic summary, persona gating, narrative plan gating, SynthesisJudge gating, visual builder).

### Changed
- **`src/orchestrator.py:VERSION`** `v3.0.0 → v3.1.0`
- **Strategy Planner 프롬프트 대폭 축소** — 약 4,200자 → 약 800자 (5배 축소).
  - 출력 항목: `event_type` / `user_intent` / `intent_confidence` / `core_questions` 만 LLM 이 산출.
  - archetype 선택은 `select_archetype()` matrix 단독 결정자 (LLM 후보 폐기).
  - theme 는 `lens_policy.select_theme()` 코드 규칙.
  - recommended_lenses 는 `lens_policy.select_lenses()` 가 mode 기반 결정.
  - per-agent directive (`legacy_directives`) 는 더 이상 LLM 으로 생성하지 않음 (transitional shim 은 보존, v4.0.0 제거 예정).
  - 모델: `model_name` (Opus) → `model_name_light` (Sonnet).
- **`src/agents/base.py:_serialize_context`** — `json.dumps(..., indent=2)` → `separators=(",", ":")` (한국어 JSON 토큰 ~30~50% 절감). `context.pop` 부작용 제거 — 호출자 dict 변형 금지.
- **`src/agents/base.py:BaseAgent.telemetry`** — 새 필드. orchestrator 가 사건당 `RunTelemetry` 인스턴스 주입 → 각 LLM 호출 자동 기록.
- **`src/orchestrator.py:run_analysis(mode=...)`** — mode 인자 추가 (None 이면 키워드 자동 매핑). 페르소나 (PlayerAnalyst/DynamicsAnalyst/ChainReactionAnalyst) 호출은 `budget.use_legacy_personas=True` 일 때만 (deep 모드 전용).
- **`src/agents/quality_inspector.py:QualityInspector.use_llm_judge`** — 새 플래그. default False. fast/standard 는 heuristic 만, deep 또는 환경변수 `QUALITY_LLM_JUDGE=true` 일 때만 LLM judge.
- **`src/agents/synthesis_judge.py:SynthesisJudge`** — heuristic-first 전환. `use_llm_synthesis` (deep), `allow_llm_on_low_confidence` (standard, contradictions/저신뢰 시에만), `core_questions_at_risk` 플래그 추가. fast 는 heuristic 만.
- **`src/agents/visual_analyst.py:VisualAnalyst.analyze(use_llm=...)`** — 새 인자. False 면 `visual_builder` 결정적 빌더만 사용. fast/standard default.
- **`src/agents/report_synthesizer.py:ReportSynthesizer`** — `use_llm_narrative_plan` / `use_llm_executive_summary` 플래그. fast/standard 는 default narrative plan + deterministic executive summary 사용. deep 만 LLM 호출.
- **`src/agents/report_synthesizer.py:_build_deterministic_summary()`** — 새 staticmethod. `judgment.main_judgment` + `biggest_uncertainty` + `counter_hypothesis` + top finding 으로 governance + key items 결정적 생성.
- **`src/models.py:AnalysisRequest.mode`** — Literal[fast/standard/deep] 필드 추가. default `standard`.
- **`src/agents/scenario_architect.py`** — persona None 입력 가드 — fast/standard 에서 player/dynamics/chain_reaction None 으로 들어오는 케이스 안전 처리.

### Deprecated (호환 유지)
- `PlayerAnalyst` / `DynamicsAnalyst` / `ChainReactionAnalyst` 페르소나 — fast/standard 에서는 호출 안 함. deep 모드에서만 호출 (6막 보고서 풍부 데이터 보존).
  - v3.0.0 부터 이미 `DeprecationWarning` 발화 중. v4.0.0 에서 6막 템플릿 재작업과 함께 정식 제거 예정 (FUT-LEGACY-001).

### LLM 호출 수 변화 (분석 1건당, 추정)
| Mode | v3.0.0 (이전) | v3.1.0 (이후) | 변화 |
|------|------------|------------|------|
| fast (구 quick_mode) | ~9 | **3~4** | -55% |
| standard (default) | 13~15 | **5~7** | -55% |
| deep | 13~15 | **9~12** | -20% (품질 보존) |

추가로 Strategy Planner 프롬프트 5배 축소 + `indent=2` 폐기로 input 토큰도 ~30% 추가 절감.

### Migration Notes
- 기존 `quick_mode` 키워드는 자동으로 `fast` mode 로 매핑됨 — 사용자 메시지 변경 불필요.
- `Orchestrator.run_analysis(event_description, chat_id)` API 변경 없음 (mode 인자는 optional).
- legacy 페르소나가 호출되지 않는 fast/standard 모드는 6막 (`six_act_theater`) 보고서를 받았을 때 일부 섹션 (이해관계자/구조/연쇄반응) 이 빈 상태가 될 수 있음. archetype matrix 가 적절한 block-based archetype 으로 라우팅하도록 강화됨.

---

## [3.0.0] — 2026-04-27

### Added
- **V3 Step 5-C — archetype 11종 완성 + 페르소나 → lens 이전. V3 리팩토링 최종.**
  - 신규 archetype 5종:
    - `decision_brief` — `what_to_do` 의도 전용 (옵션 비교 → 옵션별 리스크 → 권고 → Pre-mortem → 감시 신호)
    - `timeline_first` — `what_happened` 의도 전용 (핵심 요약 → 사실 타임라인 → 핵심 수치 → 출처 평가 → 미확인 사항)
    - `scenario_first` — `what_next` 의도 전용 (기준 시나리오 → 분기 시나리오 → 베이지안 업데이트 가이드 → 감시 신호)
    - `mechanism_decomp` — `why_happened` 의도 전용 (표층 현상 → 직접 원인 → 구조적 원인 → 제1원리 → 흔한 오해)
    - `industry_value_chain` — 산업·가치사슬 사건 (산업 구조 → 가치사슬 → 경쟁 구도 → 수익성 압력 → 전략 옵션 → 의사결정 포인트)
  - `src/archetypes/registry.select_archetype()` — 4-tier 우선순위 매트릭스 (분야+의도 → 의도 전용 → geopolitical → fallback)
  - `src/orchestrator.py` 하이브리드 라우팅 — LLM 1순위 후보 + matrix 최종 결정 (mismatch 시 INFO 로그로 추적)
  - 페르소나 → lens 이전 3종:
    - `src/lenses/stakeholder_lens.py` — `PlayerAnalyst` 대체 (행위자 식별, 전략, 위험도)
    - `src/lenses/structural_lens.py` — `DynamicsAnalyst` 대체 (게임이론, 비대칭, 전환점, 피드백 루프)
    - `src/lenses/cascade_lens.py` — `ChainReactionAnalyst` 대체 (인과 사슬, 도미노, 와일드카드)
  - `src/tests/test_archetype_selection.py` — 23 pytest 케이스 (Registry / 신규 5종 section_plan / 10-case 회귀 매트릭스 / tech 의도 차등화 / fallback warning)
  - `GOAL.md` REQ-V3-008 (archetype 11종 완성), REQ-V3-009 (페르소나 → lens 이전), `FUT-LEGACY-001` (v4.0.0에서 legacy alias 제거)

### Changed
- `src/orchestrator.py:VERSION` `v2.9.5 → v3.0.0`
- `six_act_theater.suitable_intents` 7종(default) → 2종(`who_benefits`, `what_happened`) — 인물극형 specialty 로 좁힘 (Anti-pattern #2 위반 아님: 코드/템플릿 그대로, 적용 범위만 좁힘)
- `src/lenses/registry.py` — 8종 → 11종 (분야 6 + 메타 2 + 페르소나 이전 3)
- `src/archetypes/registry.py` — 6종 → 11종, `select_archetype()` 매트릭스 4-tier 재설계
- Strategy Planner 가이드: archetype 후보 11종 + 4-tier 결정 규칙 (matrix 최종 결정)

### Deprecated
- `src.agents.PlayerAnalyst` → `src.lenses.stakeholder_lens.StakeholderLens` 사용 권장
- `src.agents.DynamicsAnalyst` → `src.lenses.structural_lens.StructuralLens` 사용 권장
- `src.agents.ChainReactionAnalyst` → `src.lenses.cascade_lens.CascadeLens` 사용 권장
- 위 3종 모듈 import 시 `DeprecationWarning` 발생 — v4.0.0 에서 모듈 제거 예정 (`FUT-LEGACY-001`)

### Removed
- 없음. V3 는 하위호환 유지. legacy alias 제거는 v4.0.0 (`FUT-LEGACY-001`) 별도 트랙.

### Security
- 변경 없음.

### Migration notes
- 페르소나 import 경로(`src.agents.player_analyst` 등) 는 v3.x 동안 동작 보장. 단, import 시점에 `DeprecationWarning` 출력 → `python -W error::DeprecationWarning` 으로 CI 게이트 가능.
- 신규 코드는 `src.lenses.*Lens` 사용. lens 는 `LensRunner.run()` 인터페이스 (페르소나 `.analyze()` 와 시그니처 다름) — alias 경로는 *동시 지원*, 호출 측 코드 변경 불필요.
- six_act_theater 가 더 이상 default 가 아님 — fallback 은 `select_archetype()` 매트릭스 끝의 명시적 fallback 분기 + warning 로그. 분류 매트릭스에서 매칭되지 않은 의도는 의도 전용 archetype 으로 라우팅.
- Watchlist DB 스키마 변경 없음 (v2.9.5 와 호환).

---

## [2.9.5] — 2026-04-26

### Added
- **V3 Step 5-B — Watchlist Registry**
  - `WatchSignal` Pydantic 모델 + `WatchDirection` Literal 3종 (confirms_base / rejects_base / ambiguous)
  - `src/watchlist/` 신설:
    - `registry.py` — `WatchlistRegistry` SQLite CRUD (`register`, `list_active`, `list_active_for_chat`, `mark_fired`, `get`, `count_active`, `count_total`)
    - `db_schema.sql` — `watchsignals` 테이블 + 3 인덱스 (active/chat/deadline). WAL 모드.
    - `converter.py` — `ScenarioAnalysis.watch_signals` (dict[]) → `list[WatchSignal]`. direction 휴리스틱 추정, deterministic signal_id, default deadline = today+30일
    - `monitor.py` — `run_monitor_loop` (봇 프로세스 내 asyncio task, 1시간 주기), `tick_once` (테스트 mock 가능), `format_telegram_alert` (spec 템플릿 정확)
  - 텔레그램 명령: `/watchlist` (이 채팅의 active 신호), `/fire <signal_id> [direction]` (수동 발화)
  - 봇 lifecycle hooks: `_on_app_post_init` (monitor task 기동) / `_on_app_post_shutdown` (정리)
  - Orchestrator: 분석 종료 후 `result.scenarios.watch_signals` 자동 변환 + DB 등록 (Anti-pattern #11 회피)
  - `src/tests/test_watchlist.py` — 19 pytest 케이스 (모델 / Registry CRUD / converter / monitor auto-fire (mocked clock) / 봇 재시작 시뮬레이션 / 알림 포맷)

### Changed
- `src/orchestrator.py:VERSION` `v2.9.0 → v2.9.5`
- `Orchestrator.__init__` 에 `watchlist_registry` optional 인자 추가 (None 시 등록 스킵 — 단위 테스트 안전)
- `TelegramBot.__init__` 가 `WatchlistRegistry(reports/watchlist.db)` 생성 후 orchestrator 에 주입 + Application.builder 에 post_init/post_shutdown 훅 등록
- 봇 시작 메시지 (`/start`) 에 `/watchlist`, `/fire` 도움말 추가

### Migration notes
- DB 파일 자동 생성 (`reports/watchlist.db`). 기존 보고서 파일들과 같은 디렉토리 — `.gitignore` 의 `reports/` 패턴에 자연스럽게 포함되어 git 추적 안 됨.
- 외부 시장 데이터 자동 폴링은 본 마일스톤 *밖* (FUT 트랙). 발화 트리거는 deadline 자동 + `/fire` 수동 둘만.
- 봇 재시작 시 별도 복구 호출 불필요 — SQLite 영구 저장이라 인스턴스화만으로 active 신호 복구.

---

## [2.9.0] — 2026-04-26

### Added
- **V3 Step 5-A — Lens Pool 도입**
  - `src/lenses/` 디렉토리 + `LensRunner` ABC + `registry.py` (8종 lens registry, 미등록 폴백)
  - 8종 lens 신설: `geopolitical`, `financial_transmission`, `tech_architecture`, `policy_implementation`, `accident_causality`, `market_structure`, `red_team`, `pre_mortem`
  - 사건당 동시 실행 한도 = 4 (Pydantic `max_length=4` + orchestrator `LENS_CAP_PER_EVENT=4` 이중 가드, Anti-pattern #6)
  - 신규 archetype 3종: `geopolitical_strategic`, `accident_forensic`, `policy_implementation` (총 6 archetypes)
  - `src/tests/test_lens_pool.py` — 11 pytest 케이스
  - `result.findings = wrapped + lens_findings` (Step 4 wrap + Step 5 lens 동시 운용)

### Changed
- `src/orchestrator.py:VERSION` `v2.8.0 → v2.9.0`
- Strategy Planner 프롬프트에 archetype 6종 + lens 8종 매트릭스 + 선택 규칙 + 4-cap 명시
- 텔레그램 진행 메시지에 "🔬 Lens 풀 실행: [...] (N/4 cap)" 추가

### Migration notes
- 기존 페르소나 (Player/Dynamics/ChainReaction) 는 *그대로 유지*. lens 는 *추가* 호출이라 v2 회귀 0건. 페르소나 → lens 이전은 v3.0.0 (Step 5-C) 에서.
- Watchlist 자동화 (5-B) 는 v2.9.5 마일스톤 — 별도 PR.
- six_act_theater 보고서 출력 byte-equal 보장 유지 (legacy 분기 무수정).

---

## [2.8.0] — 2026-04-26

### Added
- **V3 Step 4 — Quality Gate 1/2 + Claim-Evidence 추적성 + Synthesis Judge**
  - 모델: `Claim` (evidence_ids ≥1 Pydantic 강제, Anti-pattern #4), `Evidence`, `ConfidenceProfile` (3축, Anti-pattern #10), `AnalyticalFinding`, `JudgmentVerdict` (contradictions 노출, 봉합 X — Anti-pattern #5)
  - `FullAnalysisResult.findings`, `FullAnalysisResult.judgment` 신규 필드
  - `src/agents/quality_inspector.py` — `gate_1_plan_sanity` + `gate_2_coverage_check` (heuristic-first, LLM-as-judge 보강)
  - `src/agents/synthesis_judge.py` — findings → JudgmentVerdict, 어휘+counter_hypothesis 기반 모순 검출, 3축 신뢰도 합성
  - `orchestrator._wrap_findings()` — v2 분석 결과를 AnalyticalFinding 리스트로 래핑 (sources → Evidence 풀)
  - 게이트 wiring: gate 1 (strategy 직후, max 2 retry), gate 2 (보고서 합성 직전, max 2 retry), 실패 시 "⚠️ 부분 분석 완료. {gate} 실패 ({reason})" 텔레그램 알림 — 우회 금지 (Anti-pattern #7)
  - 게이트 통과율·재시도율 통계 INFO 로그
  - `src/tests/test_quality_gates.py` — 18 케이스 pytest 단위 테스트

### Changed
- `src/orchestrator.py:VERSION` `v2.7.0 → v2.8.0`
- 텔레그램 진행 메시지에 "🧮 종합 판단관" 단계 추가 (모순 건수 노출)

### Deprecated
- 기존 `confidence_score: float` 필드들 (`ContextAnalysis`, `PlayerAnalysis` 등) — 호환 목적 보존, 신규 코드는 `ConfidenceProfile` 사용 (Anti-pattern #10 회피)

### Migration notes
- six_act_theater 보고서 출력은 기능적으로 v2.7.0 과 동일. 진행 메시지에 게이트/판단관 단계만 추가.
- 게이트 실패가 분석 *중단* 을 뜻하지 않음 — 부분-분석 알림 후 보고서 생성 계속.

---

## [2.7.0] — 2026-04-26

### Added
- **V3 Step 3 — 보고서 블록 렌더링 시스템**
  - `BlockType` Literal 17종 + `AnalysisBlock` Pydantic 모델 (`src/models.py`)
  - `FullAnalysisResult.blocks: list[AnalysisBlock]` 필드
  - `src/templates/blocks/` — 17개 단일-책임 템플릿 (각 ≤50 줄, payload-only access)
  - `src/templates/report_block.html` — 디스패처 (section_plan iterate + section_id 매치)
  - `src/agents/report_synthesizer.py` — `_BLOCK_BUILDERS` 레지스트리 + 17개 `_payload_*` 빌더
  - `report.css` — block-* 클래스 append (기존 클래스 무수정, 디자인 토큰 재사용)

### Changed
- `src/orchestrator.py:VERSION` `v2.6.0 → v2.7.0`
- 신규 archetype (`financial_transmission`, `tech_decomposition`) 의 `template_path()` 가 `report_block.html` 반환 — Step 2 placeholder HTML 은 디스크에 보존되지만 사용 안 됨 (Anti-pattern #2)
- `ReportSynthesizer.synthesize()` 가 archetype 별 분기: legacy six_act_theater 는 기존 흐름 (byte-equal 보장), 그 외는 블록 빌더 + 디스패처

### Migration notes
- six_act_theater 보고서 출력은 v2.6.0 과 byte 단위 동일 (sha256 검증 통과).
- 신규 BlockType 추가 절차: ① `src/models.py:BlockType` Literal 확장 → ② `src/templates/blocks/<type>.html` 신설 (≤50 줄, payload-only) → ③ `_BLOCK_BUILDERS` 등록 → ④ `docs/CATALOGS.md §4` 갱신 (Anti-pattern #15).

---

## [2.6.0] — 2026-04-26

### Added
- **V3 Step 2 — 보고서 아키타입 다중화**
  - `src/archetypes/` 디렉토리 신설 (Protocol-based registry pattern)
    - `base.py` (`ReportArchetype` Protocol, `runtime_checkable`)
    - `six_act_theater.py` (default; 기존 `report.html` 그대로 가리킴)
    - `financial_transmission.py` (시장·거시 사건용 archetype)
    - `tech_decomposition.py` (기술·AI·IT 사건용 archetype)
    - `registry.py` (`get_archetype()`, `list_archetypes()`)
  - `src/templates/archetypes/{financial_transmission,tech_decomposition}.html` (Step 2 placeholder; Step 3 에서 본격 블록 렌더링)
  - Strategy Planner 프롬프트에 archetype 자동 선택 매트릭스 추가 (user_intent + event_type → archetype_id)
  - `ReportSynthesizer.synthesize()` 에 `archetype` 인자 추가, `archetype.template_path()` 로 분기

### Changed
- `src/orchestrator.py:VERSION` `v2.5.0 → v2.6.0`
- `AnalysisStrategy.report_archetype` 가 본격 활용됨 (Step 1 에서는 placeholder default 만 보유)
- 기존 6막 극장은 `archetype="six_act_theater"` 로 강등 — 분류 애매 시 default fallback (Anti-pattern #2: 즉시 제거 금지)

### Migration notes
- `archetype="six_act_theater"` 경로의 렌더 출력은 이전과 byte 단위 동일 (sha256 검증 통과).
- LLM 이 미등록 archetype_id 를 출력하면 `get_archetype()` 가 `six_act_theater` 로 폴백하며 warning 로그 기록.

---

## [2.4.1] — 2026-04-26

### Added
- 문서 거버넌스 V3 적용 (3-tier 계층, SSOT 매트릭스, YAML 헤더 규약)
- `docs/CATALOGS.md` (에이전트·블록 카탈로그)
- `docs/DATA_MODELS.md` (Pydantic 모델 도식)
- `CHANGELOG.md` (본 파일, Keep a Changelog 형식)
- `CLAUDE.md` 에 Change Propagation 매트릭스

### Changed
- `docs_canonical/` → `docs/` 이름 단순화
- `overall_structure.md` 내용을 `docs/ARCHITECTURE.md` 에 흡수
- `prototype_*.html` 두 개를 `docs/references/` 로 이동
- `src/style_guide/REPORT_STYLE_GUIDE.md` → `docs/REPORT_STYLE_GUIDE.md` 이전
- `README.md` 60줄 이내로 슬림화 (진입점·링크 위주)

### Removed
- `overall_structure.md` (루트)
- `prototype_d3_map.html`, `prototype_gold_chart.html` (루트)

---

## [2.5.0] — 2026-04-26

### Added
- **V3 Step 1 — AnalysisStrategy Pydantic 모델 정식 승격**
  - `AnalysisStrategy`, `EvidenceNeed`, `ReportSectionPlan`, `VisualizationSpec`, `UserIntent` (Literal 7종) 신규
  - `user_intent` / `core_questions` / `recommended_lenses` 필드 도입 → 사용자 질문 의도별 분석 분기 기반 마련
  - `FullAnalysisResult.strategy: AnalysisStrategy | None` Optional 필드 추가
  - `model_validator` 로 lens-question 정합성 강제, `core_questions min_length=1` 보장
- `dynamics_analyst` 신규 필드: `feedback_loops`, `counter_view`, `cognitive_biases`
- `chain_reaction_analyst` 신규 필드: `feedback_loops`, `wildcards`, `time_horizon`, `effect_type`, `reversible`
- `scenario_architect` 신규 필드: `preconditions`, `invalidation_conditions`
- 보고서 균형 분석 4단락 구조 강제 (핵심 판단 / 상하방 비대칭 / 변수 민감도 / 한계)
- `.balance-analysis` CSS 컴포넌트 (시인성 강화)

### Changed
- `src/orchestrator.py:_generate_analysis_strategy()` 가 dict 대신 `AnalysisStrategy` 반환. 호출 측은 객체 속성 (`strategy.skip_agents`, `strategy.theme`) 으로 접근 (Anti-pattern #3 dict 회귀 방지).
- `src/orchestrator.py:VERSION` `v2.4.0 → v2.5.0`.
- 모든 에이전트 시스템 프롬프트의 용어 난이도를 학부생 수준으로 낮춤.
- 분석 시각 풀 확장: 게임이론·시스템 사고·경로 의존성·신호 이론·네트워크·행동경제학 등 14가지.

### Deprecated
- `AnalysisStrategy.legacy_directives` — Step 1 한정 transitional shim. Step 5 lens pool 도입 시 제거 예정. 신규 코드는 `recommended_lenses` 사용.

---

## [2.4.0] — 2026-XX-XX

### Added
- AI 소비용 Markdown 보고서 export

---

## [2.4.1-pre] (사전 v2.4.1) — 2026-XX-XX

### Changed
- 모든 테마의 텍스트 대비 개선

---

## [1.x] — 2026-03-27 ~ 2026-03-29

자세한 1.x 릴리스 흐름은 [DEVLOG.md §9 버전 히스토리](DEVLOG.md) 참조.
