---
tier: 3
last_synced_with: v4.5.7
ssot_for:
  - "사용자 관점 릴리스 노트 (versioned changes)"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "DEVLOG.md (개발 상세 로그)"
last_review: 2026-05-05
---

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom `vMAJOR.MINOR.PATCH` scheme tracked in `src/orchestrator.py:VERSION`.

상세한 개발 로그·트러블슈팅·인프라 메모는 [DEVLOG.md](DEVLOG.md) 참조.

---

## [Unreleased]

V5 리팩토링 (REFACTOR_V5_PLAN.md) 진행 중. Tier 1 (토대) 진행:

- **Phase 0 (Baseline + SSOT Repair) — 완료.** v4.5.7 baseline 으로 문서·메타데이터 정합성 회복. 코드 변경 0 (orchestrator VERSION 은 이미 v4.5.7).
- **Phase 0B (Golden Evaluation Harness) — framework 완료, baseline 녹화 대기.** 20건 Golden Prompt fixture (8개 카테고리 정합) + 5종 회귀 테스트 (Golden / Visual / Semantic / Cost / Completeness) framework + CLI runner + record_baseline.py. py_compile 통과. 사용자가 `.env` 환경에서 `python scripts/record_baseline.py` 1회 실행 시 baseline 녹화 완료. SSOT: `tests/regression/README.md`.
- **Phase 0C (Pipeline State Compaction) — framework 완료, 후속 Phase 결합 대기.** `src/state/` 모듈 신설 — 6-tier State 모델 (RawContext / EvidencePack / AnalysisBrief / DraftReport / ExhibitPack / PublishManifest), RawContext → EvidencePack 변환 (`compact_to_evidence_pack`, `evidence_pack_from_context_analysis`), 8단계 입력 제한 강제 (`assert_input_is`, `forbid_raw_context_in`, AP-V5-30). orchestrator 에 EvidencePack adapter *telemetry 전용* 삽입 — v4.5.7 호출 경로 byte-equal 보존. 회귀 테스트 `tests/regression/test_state_compaction.py` 신설 (16건 케이스, Plan §4.5 인수 기준 #1~#3 검증). py_compile + AST + Plan §4.4 / §6.3 정적 일치 검증 통과.
- **Phase 1A (Research Director / Method Router) — framework 완료, opt-in 활성 대기.** `src/agents/research_director.py` 신설 — Plan §6.4 의 SYSTEM_PROMPT 그대로 + 9종 method enum (ACH / scenario_tree / transmission_channel / stakeholder_matrix / fault_tree / decision_matrix / pre_mortem / transmission_timeline / comparative) + 결정적 fallback `design_via_heuristics` (LLM 0) + DEFAULT_BRIEF (Plan §20.3 fallback). orchestrator 에 *opt-in flag* (`Config.enable_research_director`, env `V5_RESEARCH_DIRECTOR=1`) 로 통합 — 디폴트 OFF, v4.5.7 호출 경로 byte-equal 보존. 꺼진 환경에서도 `design_via_heuristics` 가 모든 prompt 에 AnalysisBrief 를 emit (Plan §6.6 인수 기준 #1 충족). SSOT: `docs/RESEARCH_DIRECTOR_METHODS.md` (9종 method 의 적용 사건·입력·출력·권장 시각화). 회귀 테스트 `tests/regression/test_research_director.py` 신설 — Golden Prompt 20건 expected_method 일치률 90% (Plan §6.6 인수 기준 #4 임계 80% 통과). `run_regression.py` 가 lazy import 로 sandbox graceful degrade.

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
