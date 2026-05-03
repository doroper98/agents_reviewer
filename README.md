---
tier: 1
last_synced_with: v4.5.0
ssot_for:
  - "저장소 진입점 (50초 안에 무엇이고 어디로 가야 할지 알 수 있게 함)"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "CHANGELOG.md"
  - "docs/ARCHITECTURE.md"
last_review: 2026-05-03
---

# Event Analysis Team — AI Agent System

텔레그램 메시지로 사건 분석을 지시하면, **2-call Tier 4 파이프라인** (ContextAnalyst Opus 4.7 → UnifiedComposer Opus 4.7) 이 보고서를 자유 형식으로 작성한 뒤 editorial 톤 HTML (LG 벤치마크 차용) 로 Cloudflare Pages 에 배포하는 시스템.

## Status
- Version: **v4.5.0** (SSOT: `src/orchestrator.py:VERSION`) — **editorial 인터랙션 패턴** (평어체, 비유박스, fact-grid, dropcap, TOC) + Newsreader/IBM Plex 폰트. 신규 디폴트 테마 `editorial_cream` (cream + terracotta), `burgundy_mono` 는 위기·분쟁 한정 (어둡게 보정). v4.4.x 의 d3 차트/지도 + zoom + 소말릴란드 해칭 + 모든 raw text `strip_md` 일관 적용.
- Tier 1 docs: [GOAL](GOAL.md) · [CLAUDE](CLAUDE.md) · [STYLEGUIDE](docs/STYLEGUIDE.md) · [DOCS_GOVERNANCE_V3](DOCS_GOVERNANCE_V3.md) · [MONO_THEME_GUIDE](docs/MONO_THEME_GUIDE.md)
- Tier 2 docs: [ARCHITECTURE](docs/ARCHITECTURE.md) · [DATA_MODELS](docs/DATA_MODELS.md) · [CATALOGS](docs/CATALOGS.md) · [TESTING](docs/TESTING.md)
- Tier 3 docs: [WORKFLOWS](WORKFLOWS.md) · [DEVLOG](DEVLOG.md) · [CHANGELOG](CHANGELOG.md)

## Quick Start
```bash
git clone https://github.com/doroper98/agents_reviewer.git
cd agents_reviewer && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 환경변수 입력
python -m src.main
```

## What This Does (v4.2.0 Tier 4)
- 텔레그램 봇이 사건 한 줄 메시지를 받음. `짧게/간략/요약` → fast, `심층/자세히/면밀` → deep, 그 외 → standard 모드 자동 결정.
- **2-call 파이프라인**: ContextAnalyst (Sonnet 4.6, 웹 검색) 가 사실/타임라인/출처 수집 → UnifiedComposer (Opus 4.7) 가 *단일 호출* 로 행위자/구조/시나리오/모순 분석 + 보고서 본문 작성 + 감시 신호 추출 + 차트 데이터 + 지도 데이터까지 모두 emit.
- mode 는 composer 프롬프트의 분석 깊이 지시 (fast 3~4 섹션 / standard 4~6 / deep 5~7 + 모순 명시 필수) 에만 영향. LLM 호출 수는 모든 모드 2회 동일.
- 보고서: `freeform_essay.html` 단일 템플릿. composer 의 `ComposedReport` (headline / sections / charts / map / watch_signals / contradictions / confidence) 를 mono 테마 (burgundy_mono / light_mono) 로 렌더 → Cloudflare Pages 배포.
- 차트 8종 (bar/donut/line/gantt/network/stacked/bubble/heatmap) 은 composer 가 데이터까지 직접 emit, charts.js 가 mono guide §4 패턴으로 SVG 렌더. 지도는 d3 + d3-geo + TopoJSON (maplibre 폐기).
- 감시 신호는 SQLite Watchlist Registry 에 등록 → `/watchlist`, `/fire` 명령으로 후속 추적.

> v3.x 의 7-agent + 11-lens + 11-archetype + 5-게이트 멀티 파이프라인은 **v4.0.0 부터 호출되지 않음**. 코드는 보존 (향후 cleanup commit 에서 제거 예정).

자세한 시스템 흐름은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 에이전트·렌즈·archetype 카탈로그는 [docs/CATALOGS.md](docs/CATALOGS.md).

## Recent Changes
최신 7건 — 전체 [CHANGELOG.md](CHANGELOG.md):
- **v4.5.0** Editorial 인터랙션 패턴 + Newsreader/IBM Plex 폰트 (LG 벤치마크 차용). 신규 디폴트 테마 `editorial_cream`, `burgundy_mono` 어둡게 + 위기/분쟁 한정. composer 평어체 (~다) + 신규 4 필드 (lede / analogy / fact_grid / dropcap) + 자동 TOC. WRITE-AP-7 (서수/식별번호 혼용) 추가.
- **v4.4.7** patch_report.py `--deck`/`--headline`/`--closing`/`--confidence-summary` 추가. WRITE-AP-1 회귀 fix (모든 raw text 필드에 `strip_md` filter 일괄 적용). WRITE-AP-7 신설.
- **v4.4.6** 지도 상단 배치 + d3.zoom() 인터랙션 + 소말릴란드 해칭 폴리곤. WRITE-AP-3 (지도 후행 배치) 회귀 fix.
- **v4.4.5** patch_report.py `--show` / `--map-zoom` / `--map-center` / `--remove-marker` + `--remove-chart` 다중 (인덱스 shift 자동 처리).
- **v4.2.0** Composer-emitted charts + maps. ComposedSection.charts (8 type) + ComposedReport.embedded_map 신설. charts.js 전면 재작성 (inline payload + mono guide §4 패턴). maps.js d3-geo + TopoJSON 으로 재작성, maplibre 폐기.
- **v4.1.0** ContextAnalyst → Opus 4.7. Tier 4 의 2-call 파이프라인에서 context 가 composer 가 보는 *유일한* 사실 입력이라 사실 추출 품질을 한 세대 위 모델로 상향. fast 모드 다운그레이드 제거.
- **v4.0.0** Tier 4 — UnifiedComposer 단일 호출 파이프라인 (MAJOR). 7개 분석 에이전트 + 11종 lens + 11종 archetype + 5단계 게이트 모두 호출 중단 (코드는 보존). LLM 호출 deep 13 → 2 (~85% ↓). archetype 매트릭스 라우팅 폐기, 항상 freeform_essay.
- **v3.5.0** Option C — narrative_composer 모든 모드에 활성. token_budget 통일. report_block.html 의 DATA DASHBOARD (9개 차트 슬롯 무지성 박힘) 통째 삭제. mono 테마 표준 적용 (lens_policy.select_theme 도 mono 만 emit).
- **v3.4.7** AMC 전체 archetype 적용 + required_inputs 검증 (PR4) — 12 archetype 에 contract() 적용. **pytest 202 passed**.
- **v3.4.6** AMC + Narrative DSL (PR3) — 단조로움의 *구조적* 처방. `NarrativeStage` Literal 5단계 (`fact / mechanism / divergence / decision / trigger`) + `ReportSectionPlan.narrative_stage`. `AnalysisMethodContract` Pydantic 모델 (mandatory_stages, forbidden_blocks, rationale). 5개 archetype 에 contract() 구현. 섹션 헤더 stage 배지 + 좌측 컬러 액센트로 시각 차별화.
- **v3.4.5** 시나리오 데이터 강화 (PR2) — `ScenarioAnalysis.scenarios[*]` 에 `confidence` (0~1 또는 0~100) + `driver_signals` (선행 지표 list) 필드 도입. `visual_builder.build_scenario_table` 정규화. `scenario_table.html` 카드 헤더에 신뢰도 배지 (색상이 신뢰도 따라 변화) + "선행 신호" 칩 list. backward-compat (loose dict).
- **v3.4.4** 보고서 품질 핫픽스 (PR1') — 4개 표면 문제 처리: ① `charts.js` TOKENS 하드코딩 → `getComputedStyle` (테마 동기), ② `visual_builder` Insight Gate (variance=0/value=1 차단, `_impact_magnitude()` 텍스트 키워드 추출), ③ `_payload_claim_card / evidence_table / qna` None 반환 (placeholder 회귀 차단), ④ `@media (max-width:540px)` 추가 (timeline 세로 스택, 테이블 카드 스택).
- **v3.4.3** 핫픽스 — `FullAnalysisResult.report_theme: str = ""` 필드 추가. v3.4.0 의 `_payload_map()` 이 `result.report_theme` 으로 light/burgundy 분기를 시도했지만 Pydantic 모델에 필드가 없어 `AttributeError` 로 보고서 생성 실패 → 분석 자체가 실패 판정. 한 줄 패치.
- **v3.4.2** `/stop` `/stopall` 명령 추가 — 진행 중 분석을 텔레그램에서 직접 중단. `/stop` 은 현재 1건만, `/stopall` 은 현재 + 대기열 전체 비움. asyncio.Task.cancel() 기반으로 LLM 호출/서브프로세스까지 시그널 전파. 인가 체크는 `/analyze` 와 동일.
- **v3.4.1** `/status` build info — 봇 프로세스 시작 시점에 git branch / short commit / commit date / dirty 여부를 한 번 캡처해 (`src/orchestrator.py:BUILD_INFO`) 시작 로그와 텔레그램 `/status` 응답에 노출. pull 만 하고 재기동을 안 한 경우에도 BUILD_INFO 는 *실행 중인 코드의* 커밋을 가리키므로 운영자가 버전 미스매치를 즉시 인지할 수 있다.
- **v3.4.0** `map` BlockType 추가 — maplibre-gl 4.7 + d3-geo v7 지도 블록을 보고서 파이프라인에 통합. `BlockType` Literal 에 `"map"` 추가 (총 18종), `_payload_map` 빌더 + `build_map_payload()` (visual_analyst 의 leaflet_config → MAP block payload 변환), `blocks/map.html` 템플릿, 정적 자산 `maps.js` / `maps.css`. light_mono / burgundy_mono 두 테마 + 골드 `#C9A84C` 단일 하이라이트. `geopolitical_strategic` archetype 의 "전장·행위자" 섹션에 자동 포함, 데이터 없으면 자동 스킵. **VM 재기동 필요.**
- **v3.3.1** Sample 추가 — `samples/theme_mono_map_chart.html` (maplibre-gl 4.7 + d3-geo v7). 라이트 모노 / 버건디 모노 두 팔레트에 동일 데이터셋 (동북아·동남아 항만 네트워크 + 16주 처리량) 을 입혀 `#C9A84C` 골드 단일 하이라이트 원칙을 보여주는 단일 페이지. 코드 영향 없음.
- **v3.3.0** Narrative Composer (Opus 4.7) — deep 모드 전용 freeform editorial pass. 정형 17 슬롯 대신 사건별 3~7 자유 섹션. 차트는 본문 흐름에 따라 composer 가 embed (auto-dashboard 폐지). claim 인용으로 evidence 추적성 보존. 새 archetype `freeform_essay` (총 12종). fast/standard 영향 0.
- **v3.2.0** d3 Chart Dashboard + Mobile-first Cards — d3 v7 인라인 임베드 (정적 자산), 9종 차트 라이브러리 (bar/donut/heatmap/triple/line/stacked/bubble/gantt/network), 시나리오 카드 그리드 (모바일 우선, 표 폐기), 보고서 자동 차트 생성 (데이터 가용성 기반), 차트 디자인 시스템 (charts.css), 차트 갤러리 샘플.
- **v3.1.0** Token Budget + Mode Routing — fast/standard/deep 모드 도입, Strategy Planner 프롬프트 축소 (~5x), AnalysisBrief compact context, deterministic visual/summary builder, 페르소나 deep-only, telemetry 도입. LLM 호출 ~50% 감소 (standard 기준).
- **v3.0.0** V3 Step 5-C — archetype 11종 완성 + 페르소나 → lens 이전 (StakeholderLens/StructuralLens/CascadeLens) + 하이브리드 라우팅. V3 리팩토링 완료.
- **v2.9.5** V3 Step 5-B — Watchlist Registry (SQLite, asyncio monitor, /watchlist /fire 명령, Anti-pattern #11)
- **v2.9.0** V3 Step 5-A — Lens Pool (8종) + archetype 3종 추가 (총 6) + 4-cap 가드 (Anti-pattern #6)
- **v2.8.0** V3 Step 4 — Quality Gate 1/2 + Claim-Evidence 추적성 + Synthesis Judge (모순 노출, 봉합 X)
- **v2.7.0** V3 Step 3 — 보고서 블록 렌더링 시스템 (17종 BlockType + report_block.html 디스패처)

## License
TBD
