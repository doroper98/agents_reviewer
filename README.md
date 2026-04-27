---
tier: 1
last_synced_with: v3.0.0
ssot_for:
  - "저장소 진입점 (50초 안에 무엇이고 어디로 가야 할지 알 수 있게 함)"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "CHANGELOG.md"
  - "docs/ARCHITECTURE.md"
last_review: 2026-04-26
---

# Event Analysis Team — AI Agent System

텔레그램 메시지로 사건 분석을 지시하면, 7개 AI 에이전트가 순차 분석한 뒤 HTML 보고서를 만들어 Cloudflare Pages 에 배포하는 시스템.

## Status
- Version: v3.0.0 (SSOT: `src/orchestrator.py:VERSION`) — V3 리팩토링 완료
- Tier 1 docs: [GOAL](GOAL.md) · [CLAUDE](CLAUDE.md) · [STYLEGUIDE](docs/STYLEGUIDE.md) · [DOCS_GOVERNANCE_V3](DOCS_GOVERNANCE_V3.md)
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

## What This Does
- 텔레그램 봇이 분석 명령을 받음 (일반 메시지 → 풀 분석, `?` 접두어 → 간단 질답).
- 오케스트레이터가 Strategy Planner → 상황인식 → Quality Gate 1 → lens pool (사건당 ≤4) + 페르소나 → 시나리오 → 시각화 → Synthesis Judge → Quality Gate 2 → 합성관 순으로 진행.
- 보고서 archetype 11종 중 LLM 후보 + matrix 결정 (`select_archetype`) → Jinja2 렌더 → Cloudflare Pages 배포.

자세한 시스템 흐름은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 에이전트·렌즈·archetype 카탈로그는 [docs/CATALOGS.md](docs/CATALOGS.md).

## Recent Changes
최신 5건 — 전체 [CHANGELOG.md](CHANGELOG.md):
- **v3.0.0** V3 Step 5-C — archetype 11종 완성 + 페르소나 → lens 이전 (StakeholderLens/StructuralLens/CascadeLens) + 하이브리드 라우팅. V3 리팩토링 완료.
- **v2.9.5** V3 Step 5-B — Watchlist Registry (SQLite, asyncio monitor, /watchlist /fire 명령, Anti-pattern #11)
- **v2.9.0** V3 Step 5-A — Lens Pool (8종) + archetype 3종 추가 (총 6) + 4-cap 가드 (Anti-pattern #6)
- **v2.8.0** V3 Step 4 — Quality Gate 1/2 + Claim-Evidence 추적성 + Synthesis Judge (모순 노출, 봉합 X)
- **v2.7.0** V3 Step 3 — 보고서 블록 렌더링 시스템 (17종 BlockType + report_block.html 디스패처)

## License
TBD
