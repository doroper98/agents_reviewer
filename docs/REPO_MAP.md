---
tier: 3
last_synced_with: v8.6.4
ssot_for:
  - "파일·디렉토리 설명 (저장소 지도)"
depends_on:
  - "src/* (실제 파일 구성)"
  - "docs/ARCHITECTURE.md"
last_review: 2026-05-14
---

# Event Analysis Team — Repository Map (v5.2.9)

> 파일·디렉토리 책무를 한눈에 보는 지도. 카탈로그성 사실(에이전트 역할 등)은 [docs/CATALOGS.md](CATALOGS.md), 시스템 흐름은 [docs/ARCHITECTURE.md](ARCHITECTURE.md).
>
> **v5.2.9: dead persona 7개 모듈 (`player_analyst / dynamics_analyst / chain_reaction_analyst / scenario_architect / visual_analyst / quality_inspector / synthesis_judge`) 삭제**. v4.0.0 부터 호출 안 되던 dead code 정리. lens 11종과 archetype 11종은 `[deprecated]` 표시 유지 — registry 만 import, 호출 경로 없음.
>
> **v4.5.7 baseline 추가 항목**: root `REFACTOR_V5_PLAN.md` (V5 마스터 플랜), `docs/legacy/` (v3 시대 SSOT 이전 디렉토리, Phase 0 SSOT Repair 에서 신설), `docs/legacy/REFACTOR_V3_PLAN.md` (v3 마스터 플랜 본문), `docs/legacy/README.md` (legacy 인덱스). root 의 `REFACTOR_V3_PLAN.md` 는 redirect stub.
>
> **V5 Tier 1 진행분** — Phase 0B 의 `tests/regression/` (20건 Golden Prompt + 5종 회귀 테스트), `scripts/run_regression.py` + `scripts/record_baseline.py`, `requirements-test.txt`. Phase 0C 의 `src/state/` (6-tier State 모델 + compaction + guards) + `tests/regression/test_state_compaction.py`. v4.5.7 호출 경로는 byte-equal 보존 (orchestrator 의 EvidencePack adapter 는 telemetry 전용).

## Source Structure
```
src/
├── __init__.py
├── main.py              # Entry point — Telegram bot startup
├── config.py            # Environment config (Pydantic Settings)
├── models.py            # Pydantic data models (SSOT). v4.0.0~v4.2.0 ComposedReport 확장
├── orchestrator.py      # 2-call 파이프라인 진입점 (VERSION SSOT). v4.0.0 부터 ~120줄
├── telegram_bot.py      # Telegram bot handlers (/status, /watchlist, /stop 등)
├── token_budget.py      # mode 별 정책. v4.2.0: 모든 모드 max_llm_calls=2
├── lens_policy.py       # select_theme(category) → mono 2종. select_lenses() [deprecated]
├── telemetry.py         # LLM 호출 / 단계별 elapsed 기록
├── visual_builder.py    # [deprecated v4.2.0] build_chart_payload / build_map_payload — composer 가 직접 emit
├── brief_builder.py     # [deprecated] FullAnalysisResult 압축. 호출 안 됨
├── agents/              # v5.2.9: dead persona 7개 모듈 삭제. 살아있는 에이전트만 남음.
│   ├── __init__.py
│   ├── base.py                   # BaseAgent (Claude CLI/API wrapper)
│   ├── context_analyst.py        # ✅ Opus 4.7 (v4.1.0) — 사실/타임라인/출처 수집
│   ├── narrative_composer.py     # ✅ Opus 4.7 — NarrativeComposer (단일 호출)
│   ├── report_synthesizer.py     # ✅ HTML 렌더 + Cloudflare 배포 (LLM 거의 0)
│   ├── research_director.py      # ✅ V5 Phase 1A (opt-in, Config.enable_research_director)
│   └── codex_critic.py           # ✅ V6 Phase V6-1 (opt-in, V6_CODEX_CRITIC) — codex CLI 외부 fact critic
├── factcheck/           # V6 — 사실 거버넌스 (opt-in)
│   ├── __init__.py
│   ├── deterministic_guards.py   # ✅ V6-2 0-LLM 사전필터 (unsourced/scope/novelty/market/nan). log-only
│   ├── critic_loop.py            # ✅ V6-3 bounded 루프 (Opus작성→Codex검수→Opus보완≤1→확인≤1). V6_CODEX_CRITIC
│   └── critique_log.py           # ✅ V6-6 자율 보강 (적립→소프트가드 자동등재→승격 후보). V6_AUTOLEARN
├── archetypes/          # v4.0.0: freeform_essay 만 사용. 11종은 deprecated.
│   ├── __init__.py
│   ├── base.py                       # ReportArchetype Protocol
│   ├── registry.py                   # archetype_id → 객체. v4.0.0: select_archetype() 호출 안 됨
│   ├── freeform_essay.py             # ✅ v4.0.0~ 유일하게 사용되는 archetype
│   ├── six_act_theater.py            # [deprecated v4.0.0]
│   ├── financial_transmission.py     # [deprecated]
│   ├── tech_decomposition.py         # [deprecated]
│   ├── geopolitical_strategic.py     # [deprecated]
│   ├── accident_forensic.py          # [deprecated]
│   ├── policy_implementation.py      # [deprecated]
│   ├── decision_brief.py             # [deprecated]
│   ├── timeline_first.py             # [deprecated]
│   ├── scenario_first.py             # [deprecated]
│   ├── mechanism_decomp.py           # [deprecated]
│   └── industry_value_chain.py       # [deprecated]
├── lenses/              # [deprecated v4.0.0] 11종 모두 호출 안 됨
│   ├── __init__.py
│   ├── base.py                       # LensRunner ABC + 공통 LLM 호출 헬퍼
│   ├── registry.py                   # lens_id → LensRunner 인스턴스 팩토리
│   ├── geopolitical_lens.py          # DIME / PMESII / Escalation Ladder
│   ├── financial_transmission_lens.py # Balance Sheet / Flow of Funds / Transmission
│   ├── tech_architecture_lens.py     # Architecture Decomposition / Bottleneck
│   ├── policy_implementation_lens.py # Stakeholder Incentive / Implementation Gap
│   ├── accident_causality_lens.py    # Fault Tree / Bow-Tie / Swiss Cheese / STAMP
│   ├── market_structure_lens.py      # Network Analysis / Game Theory / Regime Shift
│   ├── red_team_lens.py              # ACH / Pre-mortem / Devil's Advocate (메타)
│   └── pre_mortem_lens.py            # 실패 가정 후 역설계 (메타)
├── watchlist/           # V3 Step 5-B — 감시 신호 영구 저장 + 자동 발화 (Anti-pattern #11)
│   ├── __init__.py
│   ├── registry.py                   # WatchlistRegistry (SQLite CRUD)
│   ├── db_schema.sql                 # watchsignals 테이블 + 인덱스
│   ├── converter.py                  # ScenarioAnalysis.watch_signals → WatchSignal
│   └── monitor.py                    # asyncio task (1h 주기) + 알림 포맷터
├── scheduler/           # v5.1.0 — 일일 자동 브리핑 (구독 기반, in-process asyncio)
│   ├── __init__.py
│   ├── subscriptions.py              # BriefingSubscriberRegistry (SQLite CRUD + 실행 이력)
│   ├── db_schema.sql                 # briefing_subscribers + briefing_runs 테이블
│   └── daily_briefing.py             # run_daily_briefing_loop asyncio task (기본 06:00 KST)
└── templates/
    ├── report.css          # ✅ Mono 2테마 (burgundy_mono + light_mono) SSOT. v3.5.0 부터 멀티컬러 폐기.
    ├── report.html         # [deprecated] six_act_theater 용
    ├── report_block.html   # [deprecated] 옛 archetype 디스패처. v3.5.0 에서 DATA DASHBOARD 섹션 삭제.
    ├── blocks/             # 17종 블록 템플릿. composer 가 embedded_blocks 로 명시 시만 사용 (실질 미사용).
    │   ├── narrative.html, claim_card.html, evidence_table.html, timeline.html, matrix.html
    │   ├── actor_cards.html, flow_chain.html, scenario_table.html, decomposition.html
    │   ├── argument_pair.html, data_series.html, watchlist.html, qna.html, callout.html
    │   ├── counter_hypothesis.html, decision_matrix.html, risk_matrix.html
    │   └── map.html         # [deprecated v4.2.0] composer.embedded_map 으로 대체
    ├── static/             # 보고서 정적 자산 (보고서 dir 로 동기화)
    │   ├── d3.v7.min.js
    │   ├── charts.js       # ✅ v4.2.0 재작성 — inline payload + mono guide §4 패턴
    │   ├── charts.css
    │   ├── maps.js         # ✅ v4.2.0 재작성 — d3 + d3-geo + TopoJSON (maplibre 폐기)
    │   └── maps.css        # ✅ v4.2.0 재작성 — mono 토큰만 사용
    └── archetypes/
        ├── freeform_essay.html       # ✅ v4.0.0~ 유일하게 사용. v4.2.0 에서 inline charts/map 렌더 추가.
        ├── financial_transmission.html # [deprecated]
        └── tech_decomposition.html   # [deprecated]
```

## Configuration Files
- `.env` — API keys (git ignored). 환경변수 목록 SSOT는 `.env.example`.
- `.env.example` — Template for `.env`
- `requirements.txt` — Python dependencies

## Root Documents (Tier 1·3)
- [README.md](../README.md) — 진입점 (Tier 1, slim)
- [GOAL.md](../GOAL.md) — 요구사항·성공 기준 (Tier 1, REQ/NFR/FUT SSOT)
- [CLAUDE.md](../CLAUDE.md) — AI 에이전트 행동 규칙 (Tier 1)
- [DOCS_GOVERNANCE_V3.md](../DOCS_GOVERNANCE_V3.md) — 문서 거버넌스 (Tier 1)
- [REFACTOR_V3_PLAN.md](../REFACTOR_V3_PLAN.md) — V3 리팩토링 명세 (Tier 2, 한시적)
- [WORKFLOWS.md](../WORKFLOWS.md) — 실행 절차 (Tier 3)
- [DEVLOG.md](../DEVLOG.md) — 개발 상세 로그 (Tier 3)
- [CHANGELOG.md](../CHANGELOG.md) — 사용자 관점 릴리스 노트 (Tier 3)

## docs/ (Tier 1·2·3)
- `ARCHITECTURE.md` — 시스템 구조 (Tier 2)
- `DATA_MODELS.md` — Pydantic 모델 도식 (Tier 2)
- `CATALOGS.md` — 에이전트·렌즈·블록 카탈로그 (Tier 2)
- `STYLEGUIDE.md` — 코드 컨벤션 (Tier 1)
- `TESTING.md` — 테스트 전략 (Tier 2)
- `REPO_MAP.md` — 본 문서 (Tier 3)
- `references/` — 참조 자료 (prototype HTML 등)
- `reference/` — 외부 참고 자료 원본 보관 (v8.6.0). 출처·라이선스·용도는 `reference/README.md`. 코드 복제 금지 대상 — 시각 문법만 우리 어휘로 재구현한다 (CHART_REDESIGN_V8_6_PLAN §2.5)
- `CHART_REDESIGN_V8_6_PLAN.md` — 차트 표현 전면 흡수·신규 유형·type-fit 마스터 플랜 (Tier 2, v8.6.0~v8.7.0)

## Other directories
- `samples/` — 샘플 입력·출력. `chart_gallery_v7.html` 은 production `RENDERERS` 와 1:1 인 전 type fixture 갤러리이자 DOM 스냅샷 회귀의 입력 (v8.6.1 부터 37 스냅샷 키 × 6테마 — 같은 type 의 표현 변형은 `data-snapshot-key` 로 구분). `chart_redesign_v8_6_compare.html` 은 v8.5.15 ↔ 현행 렌더러 전·후 비교 (좌측은 `samples/_legacy/charts.v8515.js` 사본이 그린다)
- `samples/_legacy/` — 비교 목업 전용으로 *고정한* 옛 렌더러 사본. `charts.v8515.js` 는 v8.6.1 표현 전환의 before 기준 (무시 대상 아님 — 비교 SSOT, 플랜 §4.8)
- `scripts/` — 보조 스크립트. `patch_report.py` (발행본 핫픽스, LLM 0), `backfill_report_meta.py` (옛 보고서 `report_meta` 백필 — v5.5.7 미만 보고서의 후속 버튼 복구, dry-run 기본), `html_to_md.py` 등, `chart_dom_snapshot.py` (v8.6.0 — 갤러리 fixture 를 헤드리스 chromium 으로 렌더해 차트 SVG 의 DOM 해시를 기록·대조. `--out` 기록 / `--check` 대조 / `--diff-report` 변경 type 요약. 브라우저 없으면 skip. baseline 은 `tests/regression/fixtures/chart_dom_baseline.json`, pytest 래퍼는 `tests/regression/test_chart_dom_snapshot.py`)
- `reports/` — 생성된 HTML 보고서 (git ignored). v5.5.0 부터 `--bundle` 시 `analysis_{ts}.bundle.json` 동반
- `src/timeline_flow.py` — v5.5.2 시간 흐름도 조립 (결정론 backbone + composer 윤색). render + bundle emit 공유
- `src/visual/type_fit.py` — v8.6.4 차트 type-fit 파이프라인. 데이터 모양에 안 맞는 차트 type 을 결정적 규칙 R1~R7 로 재배치한다 (0-LLM · 값·라벨 생성 금지 · 변환 후 가드 실패면 원본 유지). orchestrator 가 `_densify_ts_charts` 직후 호출하고 flag 는 `V8_TYPE_REFIT`. 발행본 소급은 `scripts/patch_report.py --refit`, 코퍼스 실측은 `python -m src.visual.type_fit --scan reports/ --dry-run` (읽기 전용, `--rules` 로 규칙표만도 가능). 계약·규칙 SSOT 는 `docs/CHART_REDESIGN_V8_6_PLAN.md` §6, 회귀는 `tests/regression/test_type_fit.py`
- `src/handoff/` — v5.5.0 ReportBundle 핸드오프 (osint_generator 연동). `bundle_builder.py` = `FullAnalysisResult → ReportBundle`. 계약 SSOT: `docs/CONTRACTS/report_bundle_v1.md`
- `src/tests/` — pytest 단위 테스트 (V3 Step 4 부터; 현재 `test_quality_gates.py` 18 케이스)
