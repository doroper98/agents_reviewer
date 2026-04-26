---
tier: 3
last_synced_with: v2.6.0
ssot_for:
  - "파일·디렉토리 설명 (저장소 지도)"
depends_on:
  - "src/* (실제 파일 구성)"
  - "docs/ARCHITECTURE.md"
last_review: 2026-04-26
---

# Event Analysis Team — Repository Map

> 파일·디렉토리 책무를 한눈에 보는 지도. 카탈로그성 사실(에이전트 역할 등)은 [docs/CATALOGS.md](CATALOGS.md), 시스템 흐름은 [docs/ARCHITECTURE.md](ARCHITECTURE.md).

## Source Structure
```
src/
├── __init__.py
├── main.py              # Entry point — Telegram bot startup
├── config.py            # Environment config (Pydantic Settings)
├── models.py            # Pydantic data models (SSOT for data definitions)
├── orchestrator.py      # 4-phase pipeline orchestrator (VERSION SSOT)
├── telegram_bot.py      # Telegram bot handlers
├── agents/              # 에이전트 정의 — 카탈로그는 docs/CATALOGS.md
│   ├── __init__.py
│   ├── base.py                   # BaseAgent (Claude CLI/API wrapper)
│   ├── context_analyst.py
│   ├── player_analyst.py
│   ├── dynamics_analyst.py
│   ├── chain_reaction_analyst.py
│   ├── scenario_architect.py
│   ├── visual_analyst.py
│   └── report_synthesizer.py
├── archetypes/          # V3 Step 2 — 보고서 archetype 풀 (registry 패턴)
│   ├── __init__.py
│   ├── base.py                   # ReportArchetype Protocol
│   ├── registry.py               # archetype_id → 객체 (SSOT for archetype catalog)
│   ├── six_act_theater.py        # default; template=report.html (legacy)
│   ├── financial_transmission.py # 금융·거시 사건
│   └── tech_decomposition.py     # 기술·AI·IT 사건
└── templates/
    ├── report.html      # six_act_theater 용 (legacy 보존)
    ├── report.css       # 공통 CSS (모든 archetype 공유)
    └── archetypes/      # 신규 archetype placeholder 템플릿 (Step 3 에서 본격화)
        ├── financial_transmission.html
        └── tech_decomposition.html
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

## Other directories
- `samples/` — 샘플 입력·출력
- `scripts/` — 보조 스크립트 (예: html_to_md.py)
- `reports/` — 생성된 HTML 보고서 (git ignored)
