# Event Analysis Team — Repository Map

## Source Structure
```
src/
├── __init__.py
├── main.py              # Entry point — Telegram bot startup
├── config.py            # Environment config (Pydantic Settings)
├── models.py            # Pydantic data models for all analysis types
├── orchestrator.py      # 4-phase pipeline orchestrator
├── telegram_bot.py      # Telegram bot handlers
├── agents/
│   ├── __init__.py
│   ├── base.py                  # BaseAgent — Claude CLI/API wrapper
│   ├── context_analyst.py       # ACT I: 상황인식
│   ├── player_analyst.py        # ACT II: 이해관계자
│   ├── dynamics_analyst.py      # ACT III: 구조/상호작용
│   ├── chain_reaction_analyst.py # ACT IV: 연쇄반응
│   ├── scenario_architect.py    # ACT V+VI: 시나리오 + 감시 신호
│   ├── visual_analyst.py        # 시각화 (SVG/지도/차트)
│   └── report_synthesizer.py    # HTML 생성 + Cloudflare 배포
├── templates/
│   ├── report.html      # Jinja2 HTML report template (6막 구조)
│   └── report.css       # Burgundy report theme
└── style_guide/
    └── REPORT_STYLE_GUIDE.md  # 버건디 테마 스타일 가이드
```

## Configuration Files
- `.env` — API keys (git ignored)
- `.env.example` — Template for .env
- `requirements.txt` — Python dependencies

## Root Documents
- `CLAUDE.md` — AI 에이전트 행동 규칙
- `DEVLOG.md` — 전체 개발 로그
- `GOAL.md` — 요구사항 & 성공 기준
- `WORKFLOWS.md` — 실행 절차
- `overall_structure.md` — 시스템 전체 구조 설명
