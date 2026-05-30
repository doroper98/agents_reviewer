---
tier: 1
last_synced_with: v5.2.12
ssot_for:
  - "AI 에이전트 행동 규칙 (Execution Rules)"
  - "Change Propagation 매트릭스 (코드 변경 → 갱신할 문서)"
  - "Tier 4 파이프라인 정책 (2-call: context + composer)"
depends_on:
  - "docs/STYLEGUIDE.md (코드 컨벤션 SSOT)"
  - "docs/MONO_THEME_GUIDE.md (테마/패턴 SSOT)"
  - "DOCS_GOVERNANCE_V3.md (문서 거버넌스 SSOT)"
last_review: 2026-05-05
---

# CLAUDE.md — Event Analysis Team Agent System

> **🔴 운영 모드 SSOT — 절대 잊지 말 것.** 이 봇은 **Claude Code CLI 구독 플랜** 으로 돈다. `.env` 의 `ANTHROPIC_API_KEY` 는 *빈 값이 정상*. [src/config.py:131-135](src/config.py) 의 `_select_mode` 가 키가 비어있으면 자동으로 `use_cli_mode=True` 선택. `bot.log` 의 `WARNING: ANTHROPIC_API_KEY is not set` 은 [src/main.py:29](src/main.py) 가 무조건 찍는 노이즈 — 무시. 사용자에게 "API 키 채우라" 같은 조언 절대 금지. 사용자가 명시적으로 "API 로 바꿔달라" 라고 하지 않는 한 키 채우라고 하지 말 것.

## Project Overview
텔레그램 메시지 → **2-call Tier 4 파이프라인** (ContextAnalyst Opus 4.7 + NarrativeComposer Opus 4.7) → mono 테마 HTML 보고서 → Cloudflare Pages 배포. 시스템 흐름 SSOT 는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

> **V5 리팩토링 진행 중.** [REFACTOR_V5_PLAN.md](REFACTOR_V5_PLAN.md) 가 v5.0.0 의 4-Tier 17-Phase 마스터 플랜 SSOT. 현재는 Phase 0 (Baseline + SSOT Repair) 에 진입한 상태이고, v4.5.7 baseline 으로 코드·문서 정합성을 복원하는 작업이 진행된다. 코드는 v4.5.7 그대로 유지된다.

## Tech Stack (v4.5.7)
- Language: Python 3.11+
- AI 모델: **claude-opus-4-7** (composer + context, 일관) · claude-sonnet-4-6 (legacy 보존)
- AI 호출: Claude Code CLI (--dangerously-skip-permissions) 또는 Anthropic API
- Messaging: python-telegram-bot
- Data Validation: Pydantic v2
- Report: Jinja2 HTML, freeform_essay.html 단일 템플릿
- Visualization: d3 v7 SVG 차트 (composer-emitted inline data, **20종 type** — v5.3.0 부터 FT/Economist 스타일 신규 7종 포함)
- Map: d3 + d3-geo + world-atlas TopoJSON 110m (maplibre-gl 폐기, mono guide §2)
- Theme: 7종 풀 (editorial_cream / burgundy_mono / slate_steel / forest_sage / midnight_indigo / dusk_rose / paper_classic). v5.0.2 부터 보고서마다 `random.choice` 로 선택 (event_type 무관, 시각 다양성 목적). 모든 테마는 *동일 레이아웃* — bg/card/text/accent 만 다름. SSOT 는 [src/lens_policy.py:ALL_THEMES](src/lens_policy.py) + [src/templates/report.css](src/templates/report.css) 의 `[data-theme="..."]` 블록. legacy `light_mono` CSS 는 보존되었으나 풀에서 빠짐 — 직접 지정 시만 사용 가능.
- Font: Newsreader (display serif, 영문/숫자) + IBM Plex Sans KR (본문) + IBM Plex Mono. Noto Serif KR 한국어 폴백.
- Hosting: Cloudflare Pages (wrangler CLI 배포)
- Infra: Oracle Cloud VM (무료 티어)

## Agents (v4.5.7 Tier 4)
실제 호출되는 에이전트는 **2개**:
1. **ContextAnalyst** (Opus 4.7, 웹 검색) — 사실 / 타임라인 / 핵심 수치 / 출처 수집. mode 별 max_tokens (fast 4K / standard 4K / deep 10K, v4.5.7).
2. **NarrativeComposer** (Opus 4.7, 단일 호출) — 행위자 / 구조 / 시나리오 / 모순 분석 + 보고서 작성 + 차트 / 지도 데이터 emit. mode 별 max_tokens (fast 12K / standard 20K / deep 32K, v4.5.4 의 `MAX_TOKENS_BY_MODE`).

V5 Phase 1A 부터 추가 가능한 에이전트:

3. **ResearchDirector** (Opus 4.7, MAX_TOKENS=6000) — `Config.enable_research_director` 가 켜진 환경 (env: `V5_RESEARCH_DIRECTOR=1`) 에서만 호출. 사용자 질의 + EvidencePack 을 받아 AnalysisBrief (분석 설계도 — thesis / selected_methods / report_shape / visual_constraints / strategic_hint) 를 emit. 디폴트 OFF — v4.5.7 호출 경로 byte-equal 보존. 꺼진 환경에선 `design_via_heuristics` 결정적 fallback 이 LLM 호출 없이 동일 형태로 emit. 9종 method SSOT: [docs/RESEARCH_DIRECTOR_METHODS.md](docs/RESEARCH_DIRECTOR_METHODS.md).

> legacy 7-agent (PlayerAnalyst, DynamicsAnalyst, ChainReactionAnalyst, ScenarioArchitect, SynthesisJudge, QualityInspector, VisualAnalyst) 는 v4.0.0 부터 호출 안 됐고 **v5.2.9 에서 모듈 자체가 삭제됨**. 11-lens pool + 11-archetype matrix 는 모듈 보존 (lens registry 가 `src/orchestrator.py:get_lens` 에서 import 되지만 호출 경로 없음).

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

## VM 배포 SOP (✱ 기능 개발 완료 후 반드시 사용자에게 안내)

**규칙:** Claude 가 새 기능을 개발·main 머지한 직후, **반드시** Ubuntu VM 에서 봇을 재배포하는 정확한 명령어 묶음을 사용자에게 제공한다. 사용자에게 "재시작하세요" 처럼 모호하게 지시하지 말 것. 다음 4단계 *그대로* 복사해서 답변에 포함:

```bash
# 1. 코드 최신화
cd ~/agents_reviewer
git pull

# 2. 기존 봇 프로세스 모두 죽이기 (중복 인스턴스 방지)
pkill -f "src.main"
sleep 2 && ps aux | grep "src.main" | grep -v grep
# 두 번째 줄이 빈 출력이어야 함. 안 죽으면 kill -9 <PID>

# 3. venv 활성화 + 백그라운드로 1개만 띄우기
source venv/bin/activate
nohup python -m src.main > bot.log 2>&1 &
disown

# 4. 정상 가동 확인
sleep 3
ps aux | grep "src.main" | grep -v grep   # 한 줄만 떠야 함
tail -30 bot.log                          # "Application started" 확인
```

**필수 안내 사항:**
- 처음 clone 후 1회: `git config core.hooksPath .githooks` (commit-msg hook 활성화 — Execution Rule #12). 미설정 시 hook 작동 안 함.
- venv 가 없으면 `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt` 후 진행
- `.env` 변경 시 (env flag 추가 등) 재시작 *반드시* 필요. config 는 startup 시점 1회만 로드
- systemd 서비스로 등록되어 있다면 `sudo systemctl restart agents-reviewer` 한 줄로 대체 가능 — 없으면 위 4단계
- 사용자가 SSH foreground 로 봇을 띄운 상태에서 SSH 가 끊기면 봇 죽음 → `nohup ... & disown` 필수

**보안:**
- 봇 토큰·API 키가 노출된 로그를 사용자가 붙여넣으면 즉시 토큰 회전 안내 (`@BotFather /revoke` → `.env` 갱신 → 재시작)
- `.env` 는 절대 git 에 커밋 금지. `.env.example` 만 커밋

**진단 명령어 (사용자가 막혔을 때):**

```bash
# V5 flag 가 실제로 로드됐는지
python -c "from src.config import get_config; c = get_config(); print('research:', c.enable_research_director, 'visual:', c.enable_visual_planner, 'editor:', c.enable_editor_pass, 'layout:', c.enable_layout_typesetter, 'desk:', c.enable_desk_editor)"

# 봇 프로세스 추적
systemctl list-units --type=service --state=running | grep -iE "bot|analy|review"
ps aux | grep -iE "python.*bot|src.main" | grep -v grep

# 로그 실시간 모니터
tail -f bot.log
```

## 차트·지도 제작 기준 (v4.5.7)
SSOT 는 [docs/MONO_THEME_GUIDE.md](docs/MONO_THEME_GUIDE.md). 핵심:
- **차트**: composer 가 `ComposedSection.charts` 에 직접 emit. type **20종** (v5.3.0 부터). 기존 13종 (bar/donut/line/gantt/network/stacked/bubble/heatmap/dual_line/forecast/choropleth/candle/area) + FT/Economist 스타일 신규 7종 (scatter/stacked_area/lollipop/slope/small_multiples/waterfall/range_bar). 카테고리 구분은 hue 가 아닌 45° 패턴 (hatch-tight/hatch-wide/dots/accent-hatch + accent solid). 신규 7종은 `guarded` tier — chart_critic + Visual Sanity Gate C 통과 필수.
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
12. **커밋 메시지의 `vX.Y.Z:` prefix 는 `src/orchestrator.py:VERSION` 상수와 반드시 일치**. 메시지에만 새 버전 박고 상수 안 올리면 배포된 봇이 옛 버전을 계속 표기하는 회귀 (v5.2.5 까지 3회 반복) — `.githooks/commit-msg` 가 mismatch 시 커밋을 reject 한다. 활성화는 clone 직후 1회: `git config core.hooksPath .githooks`. `--no-verify` 우회 금지. 정말 우회해야 하면 `SKIP_VERSION_CHECK=1 git commit ...` (rebase / cherry-pick 같은 ops 한정).

## Change Propagation Matrix
**코드를 변경했다면 같은 커밋에서 아래의 문서도 함께 갱신한다.** SSOT 매트릭스는 [DOCS_GOVERNANCE_V3.md §3](DOCS_GOVERNANCE_V3.md).

| 코드 변경 | 동시 갱신해야 할 문서 |
|-----------|----------------------|
| `src/orchestrator.py:VERSION` 증가 | [README.md](README.md) `Status`, [CHANGELOG.md](CHANGELOG.md) (신규 항목 추가), 영향받은 모든 문서 헤더의 `last_synced_with` |
| `src/models.py` 모델 추가/변경 | [docs/DATA_MODELS.md](docs/DATA_MODELS.md) (도식 + 의미 가이드) |
| `src/handoff/bundle_builder.py` 또는 `src/models.py:ReportBundle` 모델군 (v5.5.0) 변경 | [docs/CONTRACTS/report_bundle_v1.md](docs/CONTRACTS/report_bundle_v1.md) (계약 SSOT — §7: additive=무증분 / breaking=schema_version 증분+양측 동시), `src/visual/schemas.py` (차트 data shape pin, 재정의 금지 §9), [docs/DATA_MODELS.md §5.5](docs/DATA_MODELS.md), `docs/CONTRACTS/report_bundle_v1.example.json` (예시 parity), `tests/test_report_bundle.py`. `ORIGIN_TO_VERIFICATION` / verification enum 변경 시 계약 §1/§2 + 회귀 테스트 동시 갱신 |
| `src/agents/*` 신규 추가/삭제 | [docs/CATALOGS.md §1](docs/CATALOGS.md), [docs/REPO_MAP.md](docs/REPO_MAP.md) |
| `src/lenses/*` 신규 추가 (V3 Step 5 후) | [docs/CATALOGS.md §2](docs/CATALOGS.md) |
| `src/archetypes/*` 신규 추가 (V3 Step 2 활성) | [docs/CATALOGS.md §3](docs/CATALOGS.md), [docs/ARCHITECTURE.md §5.1](docs/ARCHITECTURE.md) |
| `src/templates/blocks/*` 신규 추가 (V3 Step 3 활성) | [docs/CATALOGS.md §4](docs/CATALOGS.md), `src/models.py:BlockType` Literal 확장, `_BLOCK_BUILDERS` 등록 |
| `src/models.py:BlockType` 변경 | [docs/CATALOGS.md §4](docs/CATALOGS.md), [docs/DATA_MODELS.md §3.7](docs/DATA_MODELS.md), 신규 타입은 `src/templates/blocks/<type>.html` + 빌더 추가 |
| `src/templates/archetypes/*` 신규 추가 | [docs/REPO_MAP.md](docs/REPO_MAP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| `src/token_budget.py` 정책 변경 | [docs/ARCHITECTURE.md §3.1](docs/ARCHITECTURE.md), [docs/CATALOGS.md §2.1](docs/CATALOGS.md) |
| `src/lens_policy.py` 매핑 변경 | [docs/CATALOGS.md §2.1](docs/CATALOGS.md) |
| `src/templates/static/charts.js` 차트 추가/변경 (v3.2.0) | [CLAUDE.md `Chart System`](CLAUDE.md), `samples/chart_gallery.html`, `src/visual_builder.py:build_chart_payload`, `src/tests/test_chart_builders.py` |
| `src/tools/market_fetcher.py` 변경 (v5.2.0) | `src/config.py` (API key 필드), `src/models.py:ContextAnalysis` (`instruments_mentioned` / `time_series`), `src/agents/context_analyst.py:SYSTEM_PROMPT` (지원 종목 목록), `src/orchestrator.py` (fetch hook + `_select_market_period`), `tests/test_market_fetcher.py`, `.env.example`, [CLAUDE.md `Market Data Fetcher`](CLAUDE.md). 신규 instrument 추가 시 `INSTRUMENT_REGISTRY` + alias + 회귀 테스트 동시 갱신. |
| `src/models.py:ComposedSection._drop_invalid_charts` 변경 (v5.2.0) | `src/visual/schemas.py:_TYPE_TO_GUARD` (타입별 가드 SSOT), `tests/regression/test_composed_section_guard.py` (production wiring 회귀), `docs/CHART_RENDERING_ANTIPATTERNS.md` (AP-N 추가 시 함께). 본 validator 가 chart_gate 의 production 진입점 — 디폴트 ON. 위반 차트 silent drop. |
| `src/agents/narrative_composer.py` 변경 (v3.3.0) | [docs/CATALOGS.md §1](docs/CATALOGS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [src/visual_builder.py:build_chart_catalog](src/visual_builder.py), [src/tests/test_narrative_composer.py](src/tests/test_narrative_composer.py) |
| `src/agents/narrative_composer.py:SYSTEM_PROMPT` 또는 `src/agents/context_analyst.py:SYSTEM_PROMPT` 의 어조·어휘 가이드 변경 (v5.2.9 신설) | [docs/REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md) (본문 문체 SSOT — 한 곳에만 적기, anti-pattern #1), [docs/REPORT_WRITING_ANTIPATTERNS.md](docs/REPORT_WRITING_ANTIPATTERNS.md) (회귀 시 새 WRITE-AP-N append). 두 SYSTEM_PROMPT 와 STYLE_GUIDE 의 어휘 표·ban 리스트·빈도 가이드는 *항상 정합* 해야 — drift 발견 시 STYLE_GUIDE 가 정본 |
| `src/templates/archetypes/freeform_essay.html` 변경 (v3.3.0) | [docs/REPO_MAP.md](docs/REPO_MAP.md), [docs/CATALOGS.md §3](docs/CATALOGS.md) |
| `src/templates/static/charts.css` 차트 디자인 토큰 변경 | [CLAUDE.md `Chart System`](CLAUDE.md) |
| `src/visual_builder.py:build_chart_payload` 차트 매핑 변경 | [CHANGELOG.md `차트 매트릭스`](CHANGELOG.md) |
| [GOAL.md](GOAL.md) `REQ-*` 추가/완료 | [DEVLOG.md](DEVLOG.md) 에 변경 기록 |
| 의존성 추가 (`requirements.txt`) | [DEVLOG.md](DEVLOG.md), [README.md](README.md) Quick Start |
| 워크플로우 변경 | [WORKFLOWS.md](WORKFLOWS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 인프라 변경 (Cloudflare/VM) | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [DEVLOG.md](DEVLOG.md) |
| `docs/CHART_RENDERING_ANTIPATTERNS.md` 새 항목 추가 | [CLAUDE.md `Anti-Patterns (차트 렌더링)`](CLAUDE.md), [CHANGELOG.md](CHANGELOG.md) 의 해당 버전 entry |
| `docs/REPORT_WRITING_ANTIPATTERNS.md` 새 항목 추가 | [CLAUDE.md `Anti-Patterns (보고서 본문 작성)`](CLAUDE.md), [CHANGELOG.md](CHANGELOG.md) |
| V5 Phase 진입/완료 ([REFACTOR_V5_PLAN.md](REFACTOR_V5_PLAN.md)) | [CHANGELOG.md](CHANGELOG.md), 신규 SSOT 문서 (Phase 0B 의 `tests/regression/README.md`, Phase 1A 의 `docs/RESEARCH_DIRECTOR_METHODS.md`, Phase 2B 의 `docs/VISUAL_CAPABILITY_REGISTRY.yaml`, Phase 7 의 `docs/DESK_VISUAL_RUBRIC.md`, Phase 8 의 `docs/STRATEGIC_MODE_PROMPT.md`), 영향받은 모든 문서 헤더의 `last_synced_with` |
| `tests/regression/fixtures/golden_prompts.yaml` 변경 | [tests/regression/README.md](tests/regression/README.md) §2 갱신, `helpers.py` 의 검증 함수가 새 expected 키 처리하는지 점검 (Phase 0B SSOT) |
| `src/state/*.py` 6-tier State 모델 변경 (Phase 0C) | [docs/ARCHITECTURE.md §11](docs/ARCHITECTURE.md) (V5 6-tier 도식), [docs/DATA_MODELS.md](docs/DATA_MODELS.md) (V5 State 섹션), [tests/regression/test_state_compaction.py](tests/regression/test_state_compaction.py) (guards + 30% 절감 검증), [REFACTOR_V5_PLAN.md §4](REFACTOR_V5_PLAN.md) (Phase 0C SSOT) — 단계 라벨·method enum·필드 추가 시 모두 갱신 |
| `src/agents/research_director.py` 변경 (Phase 1A) | [docs/RESEARCH_DIRECTOR_METHODS.md](docs/RESEARCH_DIRECTOR_METHODS.md) (9종 method SSOT — 사람-친화 정의), [src/state/models.py:AnalysisMethod.method](src/state/models.py) (Literal 9종 enum — 코드 SSOT), [tests/regression/test_research_director.py](tests/regression/test_research_director.py) (≥80% 일치 검증), [tests/regression/test_method_compliance.py](tests/regression/test_method_compliance.py) (downstream contract — required_exhibits 매핑 + StrategicReport 8 필드 + heuristic 의 method 준수), [tests/regression/fixtures/golden_prompts.yaml](tests/regression/fixtures/golden_prompts.yaml) (각 prompt 의 expected_method), [REFACTOR_V5_PLAN.md §6](REFACTOR_V5_PLAN.md) (Phase 1A SSOT). `_DEFAULT_REQUIRED_EXHIBITS` 9종 매핑 변경 시 `test_method_compliance.py` 의 method-specific 검증 9종 함께 갱신 |
| 운영 의존성 (Plan §22 runtime) 추가 | [requirements-v5.txt](requirements-v5.txt) (Phase 2/2B/6/7 운영 패키지 SSOT), [docs/V5_ACTIVATION.md §1.5](docs/V5_ACTIVATION.md) (graceful degrade 매트릭스), [docs/V5_TEST_RESULTS.md](docs/V5_TEST_RESULTS.md) (effect 측정) — 새 phase 가 runtime 의존성 추가 시 3곳 모두 갱신 |
| V5 phase 활성화 / 회귀 측정 | [docs/V5_TEST_RESULTS.md §3](docs/V5_TEST_RESULTS.md) (append-only entry 추가), [docs/V5_ACTIVATION.md §3](docs/V5_ACTIVATION.md) (단계별 절차) — 새 측정 결과는 *추가만*, 기존 entry 수정 금지. AP-V5-32 강제 |
| `src/visual/evidence_dataset.py` 변경 (Phase 2A) | [src/state/models.py:EvidenceDataset / DatasetField / TransformStep](src/state/models.py) (모델 SSOT), [tests/regression/test_evidence_dataset.py](tests/regression/test_evidence_dataset.py) (AP-V5-24/25/26 검증), [REFACTOR_V5_PLAN.md §8](REFACTOR_V5_PLAN.md) (Phase 2A SSOT) — semantic_type 7종 enum / 3종 금지 행위 변경 시 모두 갱신 |
| `src/visual/v5_theme.py` 변경 (Phase 2) | [REFACTOR_V5_PLAN.md §19](REFACTOR_V5_PLAN.md) (design token 정본), `samples/chart_map_mono_compare.html` (사람-친화 SSOT), `src/templates/themes/{editorial,burgundy}.css` (브라우저 SSOT), [tests/regression/test_phase2_vega.py](tests/regression/test_phase2_vega.py) (drift 검증) — 4곳이 byte-equal 일치해야 |
| `src/visual/vega_adapter.py` 변경 (Phase 2) | [src/agents/visual_planner.py](src/agents/visual_planner.py) (Vega-Lite spec emit), [tests/regression/test_phase2_vega.py](tests/regression/test_phase2_vega.py) (어댑터 검증), [REFACTOR_V5_PLAN.md §7](REFACTOR_V5_PLAN.md) (Phase 2 SSOT) — render_vega_lite / validate_vega_spec / chart_dict_to_vega_spec 시그니처 변경 시 |
| `src/agents/visual_planner.py` 변경 (Phase 2) | [src/visual/vega_adapter.py](src/visual/vega_adapter.py) (출력 spec 검증), [src/state/models.py:EvidenceDataset](src/state/models.py) (입력 dataset), [tests/regression/test_phase2_vega.py](tests/regression/test_phase2_vega.py), [REFACTOR_V5_PLAN.md §7.3](REFACTOR_V5_PLAN.md) (Phase 2 agent SSOT) |
| `docs/VISUAL_CAPABILITY_REGISTRY.yaml` 변경 (Phase 2B) | [src/visual/capability_registry.py](src/visual/capability_registry.py) (캐시는 자동 갱신, 단 분포 가드 함수 검증 필요), [tests/regression/test_capability_registry.py](tests/regression/test_capability_registry.py) (분포 + safe/guarded/experimental 매칭), [REFACTOR_V5_PLAN.md §9](REFACTOR_V5_PLAN.md) (Phase 2B SSOT) — 새 chart type 추가는 *반드시* yaml + 회귀 테스트 분포 가드 함께 갱신 (PR 체크리스트, AP-V5-27 강제) |
| `src/visual/schemas.py` (Phase 6 Gate A) 변경 | [tests/regression/test_chart_correctness.py](tests/regression/test_chart_correctness.py) (해당 type guard 검증 추가), [docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md) (새 antipattern 매핑 시), [REFACTOR_V5_PLAN.md §13.2](REFACTOR_V5_PLAN.md) — 새 chart type 의 Pydantic guard 추가 시 _TYPE_TO_GUARD 매핑 + validate_chart_data 분기도 함께 |
| `src/visual/sanity_check.py` (Phase 6 Gate C) / `src/visual/chart_gate.py` (Gate D) 변경 | [src/agents/chart_critic.py](src/agents/chart_critic.py) (Gate B 정책 정합), [tests/regression/test_chart_correctness.py](tests/regression/test_chart_correctness.py), [REFACTOR_V5_PLAN.md §13](REFACTOR_V5_PLAN.md) (Phase 6 SSOT) — threshold (`SanityCheckThresholds`) 변경 시 Plan §13.4 의 임계와 정합 검증 |
| `src/agents/chart_critic.py` (Phase 6 Gate B) 변경 | [REFACTOR_V5_PLAN.md §13.3 / §13.8](REFACTOR_V5_PLAN.md) (7개 질문 + 운영 정책 SSOT), [tests/regression/test_chart_correctness.py](tests/regression/test_chart_correctness.py) (KEEP_SCORE_THRESHOLD 검증), CHANGELOG (운영 정책 변경 기록) |
| `src/state/models.py:Exhibit / RequiredExhibit / ExhibitPriority` (Phase 6A) 변경 | [src/visual/chart_gate.py](src/visual/chart_gate.py) (priority 분기 정합), [src/agents/research_director.py](src/agents/research_director.py) (`_DEFAULT_REQUIRED_EXHIBITS` 9종 매핑), [tests/regression/test_exhibit_priority.py](tests/regression/test_exhibit_priority.py) (AP-V5-28 검증), [REFACTOR_V5_PLAN.md §14](REFACTOR_V5_PLAN.md) (Phase 6A SSOT) — fallback_form enum 또는 priority enum 변경 시 |
| `src/visual/deterministic_gate.py` (Phase 7A) 변경 | [tests/regression/test_deterministic_gate.py](tests/regression/test_deterministic_gate.py) (HARD_FAIL_RULES + SOFT_FAIL_RULES + MODE_LOWER_BOUND + ChartCountLimits SSOT 검증), [REFACTOR_V5_PLAN.md §15](REFACTOR_V5_PLAN.md) (Phase 7A SSOT) — Hard fail 추가 시 plan 의 §15.4 + 회귀 테스트 *동시* 갱신. AP-V5-29 강제 (LLM Desk 우회 금지) |
| `src/agents/desk_editor.py` (Phase 7) 변경 | [docs/DESK_VISUAL_RUBRIC.md](docs/DESK_VISUAL_RUBRIC.md) (Visual 8-rubric SSOT — append-only), [src/visual/capture.py](src/visual/capture.py) (Playwright capture), [tests/regression/test_desk_editor.py](tests/regression/test_desk_editor.py) (KILL_RULES + HOLD_DISPATCH + SYSTEM_PROMPT 정합), [REFACTOR_V5_PLAN.md §16](REFACTOR_V5_PLAN.md) (Phase 7 SSOT) — KILL_RULES 추가는 plan §16.6 + 회귀 테스트 *동시* 갱신. AP-V5-11/12/13/14/15/16 강제 |
| `docs/DESK_VISUAL_RUBRIC.md` 새 (시각-N) 항목 append (AP-V5-16) | YK 가 발견한 결함만 추가 (append-only, 수정 X). 다음 DeskEditor 호출부터 SYSTEM_PROMPT 에 자동 포함. CHANGELOG 의 해당 버전 entry 에 명시 |
| `src/agents/strategic_router.py` (Phase 8) 변경 | [docs/STRATEGIC_MODE_PROMPT.md](docs/STRATEGIC_MODE_PROMPT.md) (3-경로 감지 SSOT), [src/state/models.py:StrategicReport](src/state/models.py) (8 필수 출력), [tests/regression/test_strategic_mode.py](tests/regression/test_strategic_mode.py) (정확도 ≥90% + KILL_RULES + AP-V5-18 갱신), [REFACTOR_V5_PLAN.md §17 + §18](REFACTOR_V5_PLAN.md) — STRATEGIC_PATTERNS 추가는 plan + 회귀 테스트 *동시* 갱신 |
| `src/agents/editor.py` (Phase 1) 변경 | [tests/regression/test_editor.py](tests/regression/test_editor.py) (7-rubric SSOT + 보존 검증), [REFACTOR_V5_PLAN.md §5](REFACTOR_V5_PLAN.md) (Phase 1 SSOT) — SYSTEM_PROMPT 의 7-rubric 변경 시 SECTION_SCORE_RUBRICS list + 회귀 테스트 *동시* 갱신. AP-V5-1 (Editor 우회 금지) 강제 |
| `src/agents/layout_typesetter.py` 또는 `LayoutPrimitive` Literal (Phase 3) 변경 | [src/state/models.py:LayoutPrimitive](src/state/models.py) (Literal SSOT), [tests/regression/test_layout_typesetter.py](tests/regression/test_layout_typesetter.py) (9-vocab AP-V5-3 가드), [REFACTOR_V5_PLAN.md §10](REFACTOR_V5_PLAN.md) (Phase 3 SSOT) — *9종 동결*. 추가/변경 금지 (AP-V5-3). 추가는 RFC + Plan 갱신 + 본 회귀 테스트 *동시* 갱신만 가능 |
| `src/visual/exhibit_numbering.py` (Phase 4) 변경 | [tests/regression/test_exhibit_and_budget.py](tests/regression/test_exhibit_and_budget.py) (정규식 SSOT + AP-V5-6), [REFACTOR_V5_PLAN.md §11](REFACTOR_V5_PLAN.md) — `[[ex:N]]` / `[[exr:N]]` / `[[exs:N-M]]` 정규식 변경 시 EXHIBIT_REF_PATTERN / EXHIBIT_REF_RANGE_PATTERN 동시 갱신. AP-V5-6 강제 (composer 임의 번호 부여 금지) |
| `src/visual/word_budget.py` (Phase 5) 변경 | [tests/regression/test_exhibit_and_budget.py](tests/regression/test_exhibit_and_budget.py) (5종 시그널 + gini + budget bands), [REFACTOR_V5_PLAN.md §12](REFACTOR_V5_PLAN.md) — MODE_TARGET_CHARS_LOWER 는 [tests/regression/helpers.py](tests/regression/helpers.py) 와 byte-equal 유지. COMPOSER_MAX_TOKENS_V5 변경 시 Plan §12.6 + 회귀 테스트 동시 갱신 |

## Anti-Patterns (문서)
[DOCS_GOVERNANCE_V3.md §9](DOCS_GOVERNANCE_V3.md) Anti-patterns 1~10 절대 위반 금지. 핵심:
- 사실을 두 곳에 적기 금지 → 한쪽은 링크
- `last_synced_with` 갱신 안 한 채 본문만 수정 금지
- DEVLOG 과거 항목 수정 금지 (append-only). 정정은 새 항목으로
- GOAL 의 REQ-* 삭제 금지. deprecated 마킹만

## Anti-Patterns (차트 렌더링 — v4.4.3 신설, v5.1.2 확장)
**charts.js / maps.js / composer 의 차트 prompt 변경 시 반드시 점검.** SSOT:
[docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md). **26개 패턴 누적**:
- CHART-AP-1~10: 기존 (drawNetwork / drawStacked / drawBar / 지도 / annotation 등)
- CHART-AP-11: 차트 카드 배경 하드코딩 fallback (v4.5.3 — `--card-deep` 미정의)
- CHART-AP-12: 버블 차트 스케일 고정 (v4.5.3 — `domain([0,1])` 고정)
- CHART-AP-13: Gantt 차트 시간축 누락 + 행 라벨/note 충돌 (v4.5.4 신설)
- CHART-AP-14: 보고서와 무관한 지리 annotation 무조건 렌더 (v4.5.7 신설 — Somaliland viewport gating)
- CHART-AP-15: gantt zero-duration emit (v5.1.2 신설 — point-in-time 이벤트 모음을 gantt 로, `GanttGuard.validate_durations` 추가)
- CHART-AP-16: donut 2-segment 안티패턴 (v5.1.2 신설 — 정보 손실 + subtitle 잉여 + 렌더러 silent return 빈 카드 회귀, `DonutGuard.validate_segment_count` 추가)
- CHART-AP-17: 차트 type starvation (v5.3.0 신설 — 캔들 회귀 교훈. 새 type 의 production wiring 만으로는 부족 — 5-Layer Usage Guarantee 필요)
- CHART-AP-18: entry 애니메이션 motion 회귀 (v5.3.0 신설 — duration / easing / prefers-reduced-motion / IntersectionObserver unobserve / ambient RAF pause 가드)
- CHART-AP-19: 재무·수익성 보고서에서 sankey/waterfall 분해 차트 누락 (v5.4.3 신설 — 결정 트리 collapse, 시계열 분기로 먼저 매치되어 분해 차트 branch 까지 못 도달. SYSTEM_PROMPT 에 step 0 추가)
- CHART-AP-20: sankey viewBox 과대 프로비저닝으로 "위로 쏠림" (v5.4.6 신설 — H = max(320,...) 클램프 + MAX_NODE_H_RATIO 0.50 의 결합으로 노드 적은 sankey 가 아래쪽 ~40% 휑함. content-fit viewBox 패스로 tight H 재계산 + dy 시프트)
- CHART-AP-21: sankey 좌·우 zones margin 부족으로 라벨 잘림 (v5.4.7 신설 — left=8/right=8 으로 첫 컬럼 "DS 매출" 라벨이 음수 좌표까지 뻗어 잘리고 마지막 컬럼 우측에 ~170px 휑함. left=80/right=120 으로 보정)
- CHART-AP-22: sankey 중간 컬럼 라벨 stacking 충돌 (v5.4.7 신설 — MIN_NODE_PAD=18 이 위 라벨 font11 + 값 라벨 font10 stacking 에 부족, 메모리/파운드리 사이 "65.0" ↔ "파운드리" 라벨 7px overlap. pad 36 으로 16px 여유 확보)
- CHART-AP-23: forecast 차트 y축 도메인이 actual 점을 제외 (v5.4.8 신설 — `?? fallback` 으로 forecast 가 있으면 actual 무시 → actual 의 값이 forecast 범위 밖이면 데이터 점이 차트 영역 밖에 박힘. actual + forecast 모든 값 산입으로 픽스)
- CHART-AP-24: forecast 차트 actual ↔ forecast 선 단절 (v5.4.8 신설 — actual 선과 forecast 선/cone 이 별도 path 로 그려져 boundary 에서 1년치 gap. actual 마지막 점을 forecast bridge 의 첫 점으로 prepend → cone 이 fork 시점에서 한 점, 미래로 fan 형태로 확장)
- CHART-AP-25: 행위자 관계도를 radial network (hairball) 로 렌더 (v5.5.5 신설 — 노드 위치 무의미 → 중심 관통 실타래, 시인성 최악. `drawNetwork` 렌더러를 **인접행렬** 로 교체. 데이터 계약 (nodes/links) · NetworkGuard · registry · usage_log 불변, type 명 `network` 유지. 셀이 관계 type 인코딩 (대립/동맹/영향/연관), getBBox content-fit viewBox 로 자동 중앙정렬. 모크업: `samples/actor_relationship_redesign_compare.html`)
- CHART-AP-26: slope 차트 좌·우 라벨 충돌 (v5.5.8 신설 — 동일/근접 값 다수 시 라벨이 같은 y 에 겹쳐 판독 불가. 기준선 정규화(모두 100.0) 차트에서 특히 빈발. `drawSlope` 에 라벨 baseline dodge (minGap 13 + 범위 클램프) + 점→라벨 connector 추가. 점·선은 실제 값 위치 유지)

회귀 발견 시 본 문서에 새 항목 (CHART-AP-N) append. 같은 실수 반복 차단의 SSOT.

## Anti-Patterns (보고서 본문 작성 — v4.4.4 신설, v4.5.4 확장)
**composer SYSTEM_PROMPT / docs/REPORT_STYLE_GUIDE.md / 본문 출력 변경 시 반드시 점검.**
SSOT: [docs/REPORT_WRITING_ANTIPATTERNS.md](docs/REPORT_WRITING_ANTIPATTERNS.md). 11개 패턴 누적:

> **★ 최우선 가치 — 일반 독자 우선 (v5.5.5).** 보고서는 *비전문가* 가 읽는다. ①
> 전문 용어·영어 표현·은어는 평이한 우리말로 바꾼다. ② 못 바꾸는 핵심 용어만 본문에
> 남기고 그 섹션 `ComposedSection.footnotes` 로 *문단 하단 주석* (`{term, explanation}`)
> 을 단다. 이 둘이 다른 모든 문체 규칙에 앞선다. SSOT: [docs/REPORT_STYLE_GUIDE.md §0.1](docs/REPORT_STYLE_GUIDE.md).
> 렌더는 `freeform_essay.html` 의 `.freeform-footnotes`, prompt 는 composer SYSTEM_PROMPT
> 의 "★ 최우선 원칙" 블록.

- WRITE-AP-1~7: 기존 (마크다운 raw / 용어 풀이 / 지도 후행 / 진부 연결어 / 추정 단정 / 모순 봉합 / 서수 모호)
- WRITE-AP-8: max_tokens 한도로 보고서 본문 중간 절단 (v4.5.4 신설 — 단일 8K 한도 회귀)
- WRITE-AP-9: 모순 섹션의 정적 메타-라벨 제목 (v5.5.1 신설 — "봉합하지 않은 충돌" 고정 제목이 결론 회피 인상 + 단조로움. composer 동적 `contradictions_heading` + resolution 단락 착지로 서술형 전환)
- WRITE-AP-10: 전문 용어·영어 표현을 평이화도 주석도 없이 본문에 방치 (v5.5.5 신설 — rate card / rate limit premium 회귀. `ComposedSection.footnotes` 문단 하단 주석 + 평이화 어휘표 신설)
- WRITE-AP-11: 발행일과 사건일이 다른데 본문에 시점 앵커 없음 (v5.6.4 신설 — 5/29 발행 보고서 본문이 "5월 26일 코스피..." 로 시작 + "같은 시각, 환율 7거래일 연속..." 로 지속 상태를 사건일에 고정 → 인지부조화 회귀. `_build_unified_payload` 에 `publication_date` 주입 + SYSTEM_PROMPT 의 `=== 시점 앵커링 ===` 섹션으로 첫 단락 시간 거리 명시 + '같은 시각' 금지 + 지속 상태는 발행일 현재 기준 프레이밍 강제)

회귀 발견 시 본 문서에 새 항목 (WRITE-AP-N) append. 차트 anti-pattern 과 분리 유지.

## Key Directories (v4.5.7 — 호출되는 것만)
- `src/agents/` — 살아있는 에이전트: `context_analyst.py` (사실 수집) + `narrative_composer.py` (본문 작성) + `report_synthesizer.py` (HTML 렌더) + `research_director.py` (V5 Phase 1A, opt-in). v5.2.9 에서 dead persona 7개 모듈 삭제.
- `src/templates/archetypes/freeform_essay.html` — 유일하게 사용되는 보고서 템플릿
- `src/templates/report.css` — 7테마 풀 (editorial_cream / burgundy_mono / slate_steel / forest_sage / midnight_indigo / dusk_rose / paper_classic) `[data-theme="..."]` 블록 정의 SSOT. legacy `light_mono` 블록도 보존 (v5.0.2 부터 풀 제외)
- `src/templates/static/` — d3.v7.min.js / charts.js / maps.js / charts.css / maps.css (보고서 dir 로 동기화)
- `src/orchestrator.py` — 4단계 (context → composer → render → watchlist) 진입점, `VERSION` SSOT
- `src/models.py` — Pydantic 데이터 모델 SSOT (`ComposedReport.charts` / `embedded_map` 포함)
- `src/token_budget.py` — mode 별 정책. v4.5.7 에선 모든 모드 동일하게 2 LLM 호출. mode 는 composer prompt 깊이 지시 + composer/context max_tokens 한도 (v4.5.4/v4.5.7) 결정
- `src/lens_policy.py` — `select_theme(event_type)` 가 `ALL_THEMES` 7종 풀에서 `random.choice` (v5.0.2). `select_lenses()` 는 호출 안 됨
- `src/telemetry.py` — LLM 호출 / 단계별 elapsed 기록
- `src/watchlist/` — SQLite Watchlist Registry (composed_report.watch_signals 에서 등록)
- `docs/` — 모든 정규 문서. `MONO_THEME_GUIDE.md` 가 차트/지도/테마 SSOT.
- `samples/` — 라이브 샘플 (GitHub Pages 자동 배포 — `chart_map_mono_compare.html`, `v4_2_0_architecture.html` 등)
- `reports/` — 생성된 HTML 보고서 (git ignored)

### Deprecated 모듈 (호출 안 됨, 파일 보존)
- `src/lenses/` (전체 11종) — registry 만 import, 호출 경로 없음
- `src/archetypes/` (freeform_essay 외 11종)
- `src/visual_builder.py` (build_chart_payload / build_map_payload — composer 가 직접 emit 으로 대체)
- `src/templates/{report.html,report_block.html}` (legacy archetype 용)
- `src/templates/blocks/` 17종 — composer 가 `embedded_blocks` 로 명시 시만 사용 (현재 실질 미사용)

### Removed 모듈 (v5.2.9 — 5년 가까이 dead code 정리)
- `src/agents/{player,dynamics,chain_reaction,scenario,visual,quality_inspector,synthesis_judge}_*.py` 7개 파일 삭제
- `src/tests/test_quality_gates.py` 삭제 (QualityInspector / SynthesisJudge 테스트)
- `src/models.py:ContextAnalysis.recommended_persona` 필드 삭제 — persona dict 채널 (v4.3.0) 폐기
- `src/state/models.py:EvidencePack.recommended_persona`, `AnalysisBrief.recommended_persona` 필드 삭제
- `src/token_budget.py` 의 dead flag 6종 (`use_llm_quality_gate / use_llm_narrative_plan / use_llm_executive_summary / use_llm_visuals / use_llm_synthesis / use_legacy_personas`) 삭제. 본문 문체 SSOT 는 [docs/REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md) 로 통합.

## Chart System (v5.3.0)
- 차트 데이터는 **composer 가 단일 LLM 호출 안에서 직접 emit** (외부 빌더 없음). 빈 데이터면 차트 없음.
- **20종 type**:
  - 기존 13종 (v5.2.13 까지): bar / donut / line / gantt / network / stacked / bubble / heatmap / dual_line / forecast / choropleth / candle / area
  - v5.3.0 신규 7종 (FT/Economist 스타일, **guarded** tier): scatter / stacked_area / lollipop / slope / small_multiples / waterfall / range_bar
- 각 차트는 `ComposedSection.charts: list[dict]` 의 dict 1개 — `{type, title, data, note?}`.
- 렌더링: `freeform_essay.html` 이 chart-card SVG + inline JSON payload emit → `charts.js` 가 스캔/렌더 (mono guide §4 패턴 자동 적용).
- **차트 type 결정 트리** — composer SYSTEM_PROMPT 의 결정 트리 (v5.3.0 신설). LLM 의 line/bar default bias 차단 (negative constraint 패턴).
- **5-Layer Usage Guarantee** (v5.3.0 — 캔들 회귀 차단):
  ① telemetry (`src/visual/usage_log.py`) — type emit JSONL 영구 기록, starvation alarm
  ② 결정 트리 (SYSTEM_PROMPT)
  ③ method × exhibit 매트릭스 (`research_director.py:_DEFAULT_REQUIRED_EXHIBITS` — fault_tree→waterfall, pre_mortem→scatter)
  ④ 다양성 쿼터 (`deterministic_gate.py:chart_type_monotony` soft fail — standard ≥3 차트에 distinct <2 면 hold)
  ⑤ 회귀 fixture (`tests/regression/fixtures/chart_type_scenarios.yaml` — 21 시나리오 SSOT, `KNOWN_CHART_TYPES` 와 1:1)
- 신규 type 추가 절차: ① `charts.js` 의 `RENDERERS` dict 에 함수 추가 ② composer SYSTEM_PROMPT 의 type 별 data 스키마 섹션에 추가 ③ `src/visual/schemas.py` 의 `_TYPE_TO_GUARD` 에 가드 추가 ④ `docs/VISUAL_CAPABILITY_REGISTRY.yaml` 등록 ⑤ `src/visual/usage_log.py:KNOWN_CHART_TYPES` 추가 ⑥ `tests/regression/fixtures/chart_type_scenarios.yaml` 시나리오 추가 ⑦ 회귀 테스트.

## Market Data Fetcher (v5.2.0)
- ContextAnalyst 가 LLM 출력에 `instruments_mentioned: list[str]` emit → orchestrator 가 `src/tools/market_fetcher.py` 의 `fetch_many` 호출 → `ContextAnalysis.time_series` 채움 → composer 가 candle / line / area 차트로 emit.
- 4 source: KRX (한국 개별주, 무인증) / YAHOO (지수 · DXY — `^KS11`/`^KQ11`/`DX-Y.NYB`, 무인증) / FRED (미국 매크로 — UST/WTI/금, free key) / ECOS (한국은행 macro, free key). SSOT `src/tools/market_fetcher.py:INSTRUMENT_REGISTRY` (현재 11 종목). v5.2.6 — DXY 는 FRED/DTWEXBGS (Fed Broad TWI, 117~125 레인지의 다른 지수) 에서 Yahoo/DX-Y.NYB (진짜 ICE DXY, 99~110 레인지) 로 교체.
- Graceful degradation — API key 누락·HTTP fail 시 빈 series + warning log. 보고서는 정상 진행, 해당 instrument 차트만 emit X.
- 기본 기간 3M (사건 보고서 event-anchored). 사건 일자 = `context.date` 기준. 향후 mode-aware period (daily=1M / historical=3Y) 확장 예정.
- 환경변수 `FRED_API_KEY` / `ECOS_API_KEY` / `KRX_API_KEY`. `.env.example` 참조.

## Report Images (v5.4.0)
- ContextAnalyst 가 수집한 `sources` URL 들에서 og:image / og:title / og:description / publisher 자동 추출 → `ContextAnalysis.available_images` → composer 가 본문 흐름에 맞는 사진만 골라 `ComposedReport.hero_image` (보고서당 0~1장) + `ComposedSection.images` (섹션당 0~1장, 보고서 전체 0~3장) emit.
- SSOT: [src/tools/image_fetcher.py](src/tools/image_fetcher.py) (og 메타 parser + publisher 매핑 16개 매체) + [src/agents/narrative_composer.py](src/agents/narrative_composer.py) `SYSTEM_PROMPT` 의 `=== 사진 (v5.4.0) ===` 섹션 (선택 원칙 / 캡션 작성 가이드 / Anti-pattern).
- 렌더: `freeform_essay.html` 의 `.freeform-figure.hero` (deck 직후) + `.freeform-figure.inline` (섹션 charts 다음, embedded_blocks 앞). 컬러 사진 그대로, mono 필터 X. caption 은 Newsreader italic + credit `© Publisher` 는 sans-serif tone-down. 7개 테마 토큰 (border-soft / fg-3) 자동 적용. 모크업 SSOT: [samples/report_images_theme_compare.html](samples/report_images_theme_compare.html).
- 외부 lib 의존성 0 — aiohttp + stdlib regex 만. HTML 첫 64KB cap (og 태그는 `<head>` 안). 평범한 데스크탑 Chrome UA + Accept 헤더로 위장 (메이저 매체 403 회피). per-URL 5s + total 12s timeout — 보고서 흐름 영향 최소화.
- Graceful degrade — sources 빈 list / 모든 URL 403·timeout / 네트워크 차단된 환경 / composer 가 자신 없어 사진 emit X 모두 보고서 정상 진행. `market_fetcher` 와 동일 패턴.
- **주의**: 사용자에게 노출되는 *유일한 외부 이미지 출처*. 광고·placeholder·매체 보일러플레이트 사진이 박힐 위험 — composer `SYSTEM_PROMPT` 의 *선택 원칙 #3* (title 에 'logo' / 'newsletter' / 'subscribe' 만 있으면 emit X) 으로 차단하지만 100% 아님. 봇 본인 사용 목적이므로 저작권은 출처표기 (© Publisher) 로 갈음.

## Map System (v4.5.7)
- composer 가 `ComposedReport.embedded_map` 에 보고서당 1개 emit (지리적 사건일 때만).
- 베이스맵: d3 + d3-geo + world-atlas/110m TopoJSON. maplibre-gl 의존 폐기.
- 렌더링: `maps.js` 가 `#freeform-map` 컨테이너 + `#map-payload` 스크립트 읽어 SVG 그림.
- mono guide §2.2: 외부 타일 서비스 / 글리프 PBF 호출 금지. world-atlas 한 번 fetch (~100KB) 후 캐시.
- v4.5.7 — Somaliland (de facto) 폴리곤·legend 는 `path.bounds()` viewport 교집합 통과 시에만 렌더 (CHART-AP-14). 무관한 지리 annotation 의 무조건 렌더 차단.

## Mode Routing (v4.5.7)
- 사용자 메시지 키워드로 자동 매핑: `짧게/간략히/요약` → fast, `심층/자세히/면밀` → deep, 그 외 → standard.
- Mode 별 정책 SSOT 는 [src/token_budget.py](src/token_budget.py).
- v4.0.0 부터 모든 모드 LLM 호출 **2회** 동일 (context + composer). mode 는 composer prompt 의 분석 깊이 지시 (섹션 수, 모순 명시 강도, 시나리오 개수) + max_tokens 한도 (v4.5.4: composer fast 12K / standard 20K / deep 32K, v4.5.7: context fast/standard 4K / deep 10K) 결정.
