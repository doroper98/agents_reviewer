---
tier: 3
last_synced_with: v3.2.0
ssot_for:
  - "사용자 관점 릴리스 노트 (versioned changes)"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "DEVLOG.md (개발 상세 로그)"
last_review: 2026-04-30
---

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom `vMAJOR.MINOR.PATCH` scheme tracked in `src/orchestrator.py:VERSION`.

상세한 개발 로그·트러블슈팅·인프라 메모는 [DEVLOG.md](DEVLOG.md) 참조.

---

## [Unreleased]

(다음 릴리스 항목 대기 중.)

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
