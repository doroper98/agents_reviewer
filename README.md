---
tier: 1
last_synced_with: v2.7.0
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
- Version: v2.7.0 (SSOT: `src/orchestrator.py:VERSION`)
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
- 오케스트레이터가 7개 에이전트를 순차 호출 (상황인식 → 이해관계자 → 구조 → 연쇄반응 → 시나리오 → 시각화 → 합성).
- Jinja2 로 HTML 보고서를 렌더링하고 Cloudflare Pages 에 배포 후 공유 링크를 반환.

자세한 시스템 흐름은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 에이전트 카탈로그는 [docs/CATALOGS.md](docs/CATALOGS.md).

## Recent Changes
최신 5건 — 전체 [CHANGELOG.md](CHANGELOG.md):
- **v2.7.0** V3 Step 3 — 보고서 블록 렌더링 시스템 (17종 BlockType + report_block.html 디스패처; 매크로 1:1 결합 해소)
- **v2.6.0** V3 Step 2 — 보고서 archetype 다중화 (six_act_theater 강등 + financial_transmission, tech_decomposition 추가)
- **v2.5.0** V3 Step 1 — AnalysisStrategy Pydantic 모델 승격 (user_intent, core_questions, recommended_lenses)
- **v2.4.1** 문서 거버넌스 V3 적용 (3-tier, SSOT 매트릭스, README 슬림화)
- **v1.x~v2.4.0** 6막 극장 구조 정착, SVG/Canvas 시각화, Markdown export (DEVLOG §9)

## License
TBD
