---
tier: 1
last_synced_with: v4.5.7
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
- Visualization: d3 v7 SVG 차트 (composer-emitted inline data, 8종 type)
- Map: d3 + d3-geo + world-atlas TopoJSON 110m (maplibre-gl 폐기, mono guide §2)
- Theme: 3종 (editorial_cream / burgundy_mono / light_mono). v4.5.0 부터 디폴트는 editorial_cream, burgundy_mono 는 위기·분쟁 한정.
- Font: Newsreader (display serif, 영문/숫자) + IBM Plex Sans KR (본문) + IBM Plex Mono. Noto Serif KR 한국어 폴백.
- Hosting: Cloudflare Pages (wrangler CLI 배포)
- Infra: Oracle Cloud VM (무료 티어)

## Agents (v4.5.7 Tier 4)
실제 호출되는 에이전트는 **2개**:
1. **ContextAnalyst** (Opus 4.7, 웹 검색) — 사실 / 타임라인 / 핵심 수치 / 출처 수집. mode 별 max_tokens (fast 4K / standard 4K / deep 10K, v4.5.7).
2. **NarrativeComposer** (Opus 4.7, 단일 호출) — 행위자 / 구조 / 시나리오 / 모순 분석 + 보고서 작성 + 차트 / 지도 데이터 emit. mode 별 max_tokens (fast 12K / standard 20K / deep 32K, v4.5.4 의 `MAX_TOKENS_BY_MODE`).

V5 Phase 1A 부터 추가 가능한 에이전트:

3. **ResearchDirector** (Opus 4.7, MAX_TOKENS=6000) — `Config.enable_research_director` 가 켜진 환경 (env: `V5_RESEARCH_DIRECTOR=1`) 에서만 호출. 사용자 질의 + EvidencePack 을 받아 AnalysisBrief (분석 설계도 — thesis / selected_methods / report_shape / visual_constraints / strategic_hint) 를 emit. 디폴트 OFF — v4.5.7 호출 경로 byte-equal 보존. 꺼진 환경에선 `design_via_heuristics` 결정적 fallback 이 LLM 호출 없이 동일 형태로 emit. 9종 method SSOT: [docs/RESEARCH_DIRECTOR_METHODS.md](docs/RESEARCH_DIRECTOR_METHODS.md).

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
| `docs/CHART_RENDERING_ANTIPATTERNS.md` 새 항목 추가 | [CLAUDE.md `Anti-Patterns (차트 렌더링)`](CLAUDE.md), [CHANGELOG.md](CHANGELOG.md) 의 해당 버전 entry |
| `docs/REPORT_WRITING_ANTIPATTERNS.md` 새 항목 추가 | [CLAUDE.md `Anti-Patterns (보고서 본문 작성)`](CLAUDE.md), [CHANGELOG.md](CHANGELOG.md) |
| V5 Phase 진입/완료 ([REFACTOR_V5_PLAN.md](REFACTOR_V5_PLAN.md)) | [CHANGELOG.md](CHANGELOG.md), 신규 SSOT 문서 (Phase 0B 의 `tests/regression/README.md`, Phase 1A 의 `docs/RESEARCH_DIRECTOR_METHODS.md`, Phase 2B 의 `docs/VISUAL_CAPABILITY_REGISTRY.yaml`, Phase 7 의 `docs/DESK_VISUAL_RUBRIC.md`, Phase 8 의 `docs/STRATEGIC_MODE_PROMPT.md`), 영향받은 모든 문서 헤더의 `last_synced_with` |
| `tests/regression/fixtures/golden_prompts.yaml` 변경 | [tests/regression/README.md](tests/regression/README.md) §2 갱신, `helpers.py` 의 검증 함수가 새 expected 키 처리하는지 점검 (Phase 0B SSOT) |
| `src/state/*.py` 6-tier State 모델 변경 (Phase 0C) | [docs/ARCHITECTURE.md §11](docs/ARCHITECTURE.md) (V5 6-tier 도식), [docs/DATA_MODELS.md](docs/DATA_MODELS.md) (V5 State 섹션), [tests/regression/test_state_compaction.py](tests/regression/test_state_compaction.py) (guards + 30% 절감 검증), [REFACTOR_V5_PLAN.md §4](REFACTOR_V5_PLAN.md) (Phase 0C SSOT) — 단계 라벨·method enum·필드 추가 시 모두 갱신 |
| `src/agents/research_director.py` 변경 (Phase 1A) | [docs/RESEARCH_DIRECTOR_METHODS.md](docs/RESEARCH_DIRECTOR_METHODS.md) (9종 method SSOT — 사람-친화 정의), [src/state/models.py:AnalysisMethod.method](src/state/models.py) (Literal 9종 enum — 코드 SSOT), [tests/regression/test_research_director.py](tests/regression/test_research_director.py) (≥80% 일치 검증), [tests/regression/fixtures/golden_prompts.yaml](tests/regression/fixtures/golden_prompts.yaml) (각 prompt 의 expected_method), [REFACTOR_V5_PLAN.md §6](REFACTOR_V5_PLAN.md) (Phase 1A SSOT) |
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

## Anti-Patterns (차트 렌더링 — v4.4.3 신설, v4.5.7 확장)
**charts.js / maps.js / composer 의 차트 prompt 변경 시 반드시 점검.** SSOT:
[docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md). **14개 패턴 누적**:
- CHART-AP-1~10: 기존 (drawNetwork / drawStacked / drawBar / 지도 / annotation 등)
- CHART-AP-11: 차트 카드 배경 하드코딩 fallback (v4.5.3 — `--card-deep` 미정의)
- CHART-AP-12: 버블 차트 스케일 고정 (v4.5.3 — `domain([0,1])` 고정)
- CHART-AP-13: Gantt 차트 시간축 누락 + 행 라벨/note 충돌 (v4.5.4 신설)
- CHART-AP-14: 보고서와 무관한 지리 annotation 무조건 렌더 (v4.5.7 신설 — Somaliland viewport gating)

회귀 발견 시 본 문서에 새 항목 (CHART-AP-N) append. 같은 실수 반복 차단의 SSOT.

## Anti-Patterns (보고서 본문 작성 — v4.4.4 신설, v4.5.4 확장)
**composer SYSTEM_PROMPT / persona 가이드 / 본문 출력 변경 시 반드시 점검.**
SSOT: [docs/REPORT_WRITING_ANTIPATTERNS.md](docs/REPORT_WRITING_ANTIPATTERNS.md). 8개 패턴 누적:
- WRITE-AP-1~7: 기존 (마크다운 raw / 용어 풀이 / 지도 후행 / 진부 연결어 / 추정 단정 / 모순 봉합 / 서수 모호)
- WRITE-AP-8: max_tokens 한도로 보고서 본문 중간 절단 (v4.5.4 신설 — 단일 8K 한도 회귀)

회귀 발견 시 본 문서에 새 항목 (WRITE-AP-N) append. 차트 anti-pattern 과 분리 유지.

## Key Directories (v4.5.7 — 호출되는 것만)
- `src/agents/` — 살아있는 에이전트 2개 (`context_analyst.py`, `narrative_composer.py`). 나머지 7개 파일은 보존하되 호출 안 됨.
- `src/templates/archetypes/freeform_essay.html` — 유일하게 사용되는 보고서 템플릿
- `src/templates/report.css` — mono 3테마 (editorial_cream + burgundy_mono + light_mono) 정의 SSOT (v4.5.0 부터 editorial_cream 디폴트, burgundy_mono 위기·분쟁 한정)
- `src/templates/static/` — d3.v7.min.js / charts.js / maps.js / charts.css / maps.css (보고서 dir 로 동기화)
- `src/orchestrator.py` — 4단계 (context → composer → render → watchlist) 진입점, `VERSION` SSOT
- `src/models.py` — Pydantic 데이터 모델 SSOT (`ComposedReport.charts` / `embedded_map` 포함)
- `src/token_budget.py` — mode 별 정책. v4.5.7 에선 모든 모드 동일하게 2 LLM 호출. mode 는 composer prompt 깊이 지시 + composer/context max_tokens 한도 (v4.5.4/v4.5.7) 결정
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

## Chart System (v4.5.7)
- 차트 데이터는 **composer 가 단일 LLM 호출 안에서 직접 emit** (외부 빌더 없음). 빈 데이터면 차트 없음.
- 8종 type: bar / donut / line / gantt / network / stacked / bubble / heatmap (mono guide §5).
- 각 차트는 `ComposedSection.charts: list[dict]` 의 dict 1개 — `{type, title, data, note?}`.
- 렌더링: `freeform_essay.html` 이 chart-card SVG + inline JSON payload emit → `charts.js` 가 스캔/렌더 (mono guide §4 패턴 자동 적용).
- 신규 type 추가 절차: ① `charts.js` 의 `RENDERERS` dict 에 함수 추가 ② composer SYSTEM_PROMPT 의 type 별 data 스키마 섹션에 추가 ③ samples 갱신 ④ 테스트.

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
