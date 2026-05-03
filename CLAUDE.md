---
tier: 1
last_synced_with: v4.2.0
ssot_for:
  - "AI 에이전트 행동 규칙 (Execution Rules)"
  - "Change Propagation 매트릭스 (코드 변경 → 갱신할 문서)"
  - "Tier 4 파이프라인 정책 (2-call: context + composer)"
depends_on:
  - "docs/STYLEGUIDE.md (코드 컨벤션 SSOT)"
  - "docs/MONO_THEME_GUIDE.md (테마/패턴 SSOT)"
  - "DOCS_GOVERNANCE_V3.md (문서 거버넌스 SSOT)"
last_review: 2026-05-02
---

# CLAUDE.md — Event Analysis Team Agent System

## Project Overview
텔레그램 메시지 → **2-call Tier 4 파이프라인** (ContextAnalyst Sonnet 4.6 + UnifiedComposer Opus 4.7) → mono 테마 HTML 보고서 → Cloudflare Pages 배포. 시스템 흐름 SSOT 는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech Stack (v4.2.0)
- Language: Python 3.11+
- AI 모델: **claude-opus-4-7** (composer + context, 일관) · claude-sonnet-4-6 (legacy 보존)
- AI 호출: Claude Code CLI (--dangerously-skip-permissions) 또는 Anthropic API
- Messaging: python-telegram-bot
- Data Validation: Pydantic v2
- Report: Jinja2 HTML, freeform_essay.html 단일 템플릿
- Visualization: d3 v7 SVG 차트 (composer-emitted inline data, 8종 type)
- Map: d3 + d3-geo + world-atlas TopoJSON 110m (maplibre-gl 폐기, mono guide §2)
- Theme: mono 2종 (burgundy_mono / light_mono) 만, 멀티컬러 폐기
- Hosting: Cloudflare Pages (wrangler CLI 배포)
- Infra: Oracle Cloud VM (무료 티어)

## Agents (v4.2.0 Tier 4)
실제 호출되는 에이전트는 **2개**:
1. **ContextAnalyst** (Opus 4.7, 웹 검색) — 사실 / 타임라인 / 핵심 수치 / 출처 수집
2. **UnifiedComposer / NarrativeComposer** (Opus 4.7, 단일 호출) — 행위자 / 구조 / 시나리오 / 모순 분석 + 보고서 작성 + 차트 / 지도 데이터 emit

> legacy 7-agent (PlayerAnalyst, DynamicsAnalyst, ChainReactionAnalyst, ScenarioArchitect, SynthesisJudge, QualityInspector, VisualAnalyst) + 11-lens pool + 11-archetype matrix 는 **v4.0.0 부터 호출 안 함**. 모듈은 보존 (cleanup commit 미정).

세부 카탈로그는 [docs/CATALOGS.md §1](docs/CATALOGS.md). 이 문서는 카탈로그를 사본으로 갖지 않는다 (SSOT 단일 출처).

## Canonical Documents
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 시스템 아키텍처
- [docs/STYLEGUIDE.md](docs/STYLEGUIDE.md) — 코드 컨벤션
- [docs/TESTING.md](docs/TESTING.md) — 테스트 전략
- [docs/REPO_MAP.md](docs/REPO_MAP.md) — 파일/폴더 구조 설명
- [docs/CATALOGS.md](docs/CATALOGS.md) — 에이전트·렌즈·블록 카탈로그
- [docs/DATA_MODELS.md](docs/DATA_MODELS.md) — Pydantic 모델 도식
- [DEVLOG.md](DEVLOG.md) — 전체 개발 로그 (인프라, 트러블슈팅 포함)
- [CHANGELOG.md](CHANGELOG.md) — 사용자 관점 릴리스 노트
- [DOCS_GOVERNANCE_V3.md](DOCS_GOVERNANCE_V3.md) — 문서 거버넌스 (3-tier, SSOT 매트릭스)

## 차트·지도 제작 기준 (v4.2.0)
SSOT 는 [docs/MONO_THEME_GUIDE.md](docs/MONO_THEME_GUIDE.md). 핵심:
- **차트**: composer 가 `ComposedSection.charts` 에 직접 emit. type 8종 (bar/donut/line/gantt/network/stacked/bubble/heatmap). 카테고리 구분은 hue 가 아닌 45° 패턴 (hatch-tight/hatch-wide/dots/accent-hatch + accent solid).
- **지도**: composer 가 `ComposedReport.embedded_map` 에 emit. d3 + d3-geo + world-atlas/110m TopoJSON. maplibre-gl / 외부 타일 서비스 사용 금지 (mono guide Anti-pattern §6.6).
- **폰트**: Noto Serif KR (숫자/타이틀), Noto Sans KR (라벨/본문/지도 라벨)
- **색**: 큰 숫자에 액센트 색 금지 → `--text` 만 (mono guide §3.3)
- **사선**: 45° 한 방향만. cross-hatch / 반대 방향 / 회전 패턴 안에 dash 모두 금지 (mono guide §6.1~6.3).
- **참조 구현**: [samples/chart_map_mono_compare.html](samples/chart_map_mono_compare.html) (라이브: doroper98.github.io/agents_reviewer/samples/chart_map_mono_compare.html)

## Execution Rules
1. 모든 코드 변경 후 `python -m py_compile` 검증
2. Type hints 필수
3. Pydantic 모델 사용 (dict 금지)
4. Agent system prompt 는 한국어 + 영어 혼용 가능
5. 커밋 메시지: `v{VER}: {변경 요약}`
6. CLI 모드: `--dangerously-skip-permissions --allowedTools "WebFetch,WebSearch"`
7. 시스템 프롬프트에 `.format()` 사용 금지 → `.replace()` 사용 (JSON `{}` 충돌 방지)
8. AnalysisStrategy 는 dict 가 아닌 Pydantic 모델로만 다룬다. dict 회귀 금지 ([REFACTOR_V3_PLAN.md §8](REFACTOR_V3_PLAN.md) Anti-pattern #3). per-agent directive 는 transitional `legacy_directives` 필드를 통해서만 접근.
9. claim 에 evidence 1 개 이상 강제 (`Claim.must_have_evidence` Pydantic validator). 빌더가 빈 evidence 로 Claim 생성 시도 금지 — Anti-pattern #4. 데이터가 없으면 finding 자체를 생성하지 말 것.
10. Synthesis Judge 는 모순을 봉합하지 않고 드러낸다. 모순은 `JudgmentVerdict.contradictions` 필드에 명시 — Anti-pattern #5. 어느 쪽 채택했는지 `resolution` 에 적되, 패배한 입장은 `counter_hypothesis` 로 보존.
11. 신규 문서는 [DOCS_GOVERNANCE_V3.md](DOCS_GOVERNANCE_V3.md) 의 YAML 헤더 규약 + SSOT 매트릭스를 따름. 사실은 한 곳에만 적고 다른 곳은 링크.

## Change Propagation Matrix
**코드를 변경했다면 같은 커밋에서 아래의 문서도 함께 갱신한다.** SSOT 매트릭스는 [DOCS_GOVERNANCE_V3.md §3](DOCS_GOVERNANCE_V3.md).

| 코드 변경 | 동시 갱신해야 할 문서 |
|-----------|----------------------|
| `src/orchestrator.py:VERSION` 증가 | [README.md](README.md) `Status`, [CHANGELOG.md](CHANGELOG.md) (신규 항목 추가), 영향받은 모든 문서 헤더의 `last_synced_with` |
| `src/models.py` 모델 추가/변경 | [docs/DATA_MODELS.md](docs/DATA_MODELS.md) (도식 + 의미 가이드) |
| `src/agents/*` 신규 추가/삭제 | [docs/CATALOGS.md §1](docs/CATALOGS.md), [docs/REPO_MAP.md](docs/REPO_MAP.md) |
| `src/lenses/*` 신규 추가 (V3 Step 5 후) | [docs/CATALOGS.md §2](docs/CATALOGS.md) |
| `src/archetypes/*` 신규 추가 (V3 Step 2 활성) | [docs/CATALOGS.md §3](docs/CATALOGS.md), [docs/ARCHITECTURE.md §5.1](docs/ARCHITECTURE.md) |
| `src/templates/blocks/*` 신규 추가 (V3 Step 3 활성) | [docs/CATALOGS.md §4](docs/CATALOGS.md), `src/models.py:BlockType` Literal 확장, `_BLOCK_BUILDERS` 등록 |
| `src/models.py:BlockType` 변경 | [docs/CATALOGS.md §4](docs/CATALOGS.md), [docs/DATA_MODELS.md §3.7](docs/DATA_MODELS.md), 신규 타입은 `src/templates/blocks/<type>.html` + 빌더 추가 |
| `src/templates/archetypes/*` 신규 추가 | [docs/REPO_MAP.md](docs/REPO_MAP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| `src/token_budget.py` 정책 변경 | [docs/ARCHITECTURE.md §3.1](docs/ARCHITECTURE.md), [docs/CATALOGS.md §2.1](docs/CATALOGS.md) |
| `src/lens_policy.py` 매핑 변경 | [docs/CATALOGS.md §2.1](docs/CATALOGS.md) |
| `src/templates/static/charts.js` 차트 추가/변경 (v3.2.0) | [CLAUDE.md `Chart System`](CLAUDE.md), `samples/chart_gallery.html`, `src/visual_builder.py:build_chart_payload`, `src/tests/test_chart_builders.py` |
| `src/agents/narrative_composer.py` 변경 (v3.3.0) | [docs/CATALOGS.md §1](docs/CATALOGS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [src/visual_builder.py:build_chart_catalog](src/visual_builder.py), [src/tests/test_narrative_composer.py](src/tests/test_narrative_composer.py) |
| `src/templates/archetypes/freeform_essay.html` 변경 (v3.3.0) | [docs/REPO_MAP.md](docs/REPO_MAP.md), [docs/CATALOGS.md §3](docs/CATALOGS.md) |
| `src/templates/static/charts.css` 차트 디자인 토큰 변경 | [CLAUDE.md `Chart System`](CLAUDE.md) |
| `src/visual_builder.py:build_chart_payload` 차트 매핑 변경 | [CHANGELOG.md `차트 매트릭스`](CHANGELOG.md) |
| [GOAL.md](GOAL.md) `REQ-*` 추가/완료 | [DEVLOG.md](DEVLOG.md) 에 변경 기록 |
| 의존성 추가 (`requirements.txt`) | [DEVLOG.md](DEVLOG.md), [README.md](README.md) Quick Start |
| 워크플로우 변경 | [WORKFLOWS.md](WORKFLOWS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 인프라 변경 (Cloudflare/VM) | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [DEVLOG.md](DEVLOG.md) |

## Anti-Patterns (문서)
[DOCS_GOVERNANCE_V3.md §9](DOCS_GOVERNANCE_V3.md) Anti-patterns 1~10 절대 위반 금지. 핵심:
- 사실을 두 곳에 적기 금지 → 한쪽은 링크
- `last_synced_with` 갱신 안 한 채 본문만 수정 금지
- DEVLOG 과거 항목 수정 금지 (append-only). 정정은 새 항목으로
- GOAL 의 REQ-* 삭제 금지. deprecated 마킹만

## Anti-Patterns (차트 렌더링 — v4.4.3 신설, v4.4.4 확장)
**charts.js / maps.js / composer 의 차트 prompt 변경 시 반드시 점검.** SSOT:
[docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md). 10개 패턴 누적:
- CHART-AP-1: category/group 시각 분리 미적용 (drawNetwork 회귀)
- CHART-AP-2: 반복 라벨 시각 일관성 깨짐 (drawStacked 회귀)
- CHART-AP-3: 음수/0/극단값 robust 처리 누락
- CHART-AP-4: 고정 aspect-ratio ↔ 동적 viewBox 충돌 (letterbox)
- CHART-AP-5: 라벨 zone 밖 잘림 (drawBar 회귀)
- CHART-AP-6: annotation 충돌 (vline + end label 등)
- CHART-AP-7: 빈 데이터 차트 emit
- CHART-AP-8: 차트 type 이 사건과 부적합
- CHART-AP-9: 지도 zoom/center 디폴트 의존
- CHART-AP-10: 지도 마커 라벨 충돌 (v4.4.4 신설 — 가까운 마커 라벨 100% 겹침)

회귀 발견 시 본 문서에 새 항목 (CHART-AP-N) append. 같은 실수 반복 차단의 SSOT.

## Anti-Patterns (보고서 본문 작성 — v4.4.4 신설, v4.4.7 확장)
**composer SYSTEM_PROMPT / persona 가이드 / 본문 출력 변경 시 반드시 점검.**
SSOT: [docs/REPORT_WRITING_ANTIPATTERNS.md](docs/REPORT_WRITING_ANTIPATTERNS.md). 7개 패턴 누적:
- WRITE-AP-1: 마크다운 강조 기호 raw 노출 ('AI 작성 흔적')
- WRITE-AP-2: 전문 용어 첫 등장 시 풀이 누락
- WRITE-AP-3: 지리적 사건의 지도 후행 배치
- WRITE-AP-4: AI 작성 느낌의 표현 (clichés)
- WRITE-AP-5: 출처 없는 추정을 단정으로 진술
- WRITE-AP-6: 모순을 자연스럽게 봉합
- WRITE-AP-7: 서수 / 기수의 모호한 혼용 ('N번' 의 두 얼굴 — v4.4.7 신설)

회귀 발견 시 본 문서에 새 항목 (WRITE-AP-N) append. 차트 anti-pattern 과 분리 유지.

## Key Directories (v4.2.0 — 호출되는 것만)
- `src/agents/` — 살아있는 에이전트 2개 (`context_analyst.py`, `narrative_composer.py`). 나머지 7개 파일은 보존하되 호출 안 됨.
- `src/templates/archetypes/freeform_essay.html` — 유일하게 사용되는 보고서 템플릿
- `src/templates/report.css` — mono 2테마 (burgundy_mono + light_mono) 정의 SSOT
- `src/templates/static/` — d3.v7.min.js / charts.js / maps.js / charts.css / maps.css (보고서 dir 로 동기화)
- `src/orchestrator.py` — 4단계 (context → composer → render → watchlist) 진입점, `VERSION` SSOT
- `src/models.py` — Pydantic 데이터 모델 SSOT (`ComposedReport.charts` / `embedded_map` 포함)
- `src/token_budget.py` — mode 별 정책. v4.2.0 에선 모든 모드 동일하게 2 LLM 호출. mode 는 composer prompt 깊이 지시만 결정
- `src/lens_policy.py` — `select_theme(category)` 로 mono 2종 중 결정. `select_lenses()` 는 호출 안 됨
- `src/telemetry.py` — LLM 호출 / 단계별 elapsed 기록
- `src/watchlist/` — SQLite Watchlist Registry (composed_report.watch_signals 에서 등록)
- `docs/` — 모든 정규 문서. `MONO_THEME_GUIDE.md` 가 차트/지도/테마 SSOT.
- `samples/` — 라이브 샘플 (GitHub Pages 자동 배포 — `chart_map_mono_compare.html`, `v4_2_0_architecture.html` 등)
- `reports/` — 생성된 HTML 보고서 (git ignored)

### Deprecated 모듈 (호출 안 됨, 파일 보존)
- `src/agents/{player,dynamics,chain_reaction,scenario,visual,quality_inspector,synthesis_judge}_*.py`
- `src/lenses/` (전체 11종)
- `src/archetypes/` (freeform_essay 외 11종)
- `src/visual_builder.py` (build_chart_payload / build_map_payload — composer 가 직접 emit 으로 대체)
- `src/templates/{report.html,report_block.html}` (legacy archetype 용)
- `src/templates/blocks/` 17종 — composer 가 `embedded_blocks` 로 명시 시만 사용 (현재 실질 미사용)

## Chart System (v4.2.0)
- 차트 데이터는 **composer 가 단일 LLM 호출 안에서 직접 emit** (외부 빌더 없음). 빈 데이터면 차트 없음.
- 8종 type: bar / donut / line / gantt / network / stacked / bubble / heatmap (mono guide §5).
- 각 차트는 `ComposedSection.charts: list[dict]` 의 dict 1개 — `{type, title, data, note?}`.
- 렌더링: `freeform_essay.html` 이 chart-card SVG + inline JSON payload emit → `charts.js` 가 스캔/렌더 (mono guide §4 패턴 자동 적용).
- 신규 type 추가 절차: ① `charts.js` 의 `RENDERERS` dict 에 함수 추가 ② composer SYSTEM_PROMPT 의 type 별 data 스키마 섹션에 추가 ③ samples 갱신 ④ 테스트.

## Map System (v4.2.0)
- composer 가 `ComposedReport.embedded_map` 에 보고서당 1개 emit (지리적 사건일 때만).
- 베이스맵: d3 + d3-geo + world-atlas/110m TopoJSON. maplibre-gl 의존 폐기.
- 렌더링: `maps.js` 가 `#freeform-map` 컨테이너 + `#map-payload` 스크립트 읽어 SVG 그림.
- mono guide §2.2: 외부 타일 서비스 / 글리프 PBF 호출 금지. world-atlas 한 번 fetch (~100KB) 후 캐시.

## Mode Routing (v4.2.0)
- 사용자 메시지 키워드로 자동 매핑: `짧게/간략히/요약` → fast, `심층/자세히/면밀` → deep, 그 외 → standard.
- Mode 별 정책 SSOT 는 [src/token_budget.py](src/token_budget.py).
- v4.0.0 부터 모든 모드 LLM 호출 **2회** 동일 (context + composer). mode 는 composer prompt 의 분석 깊이 지시 (섹션 수, 모순 명시 강도, 시나리오 개수) 만 결정.
