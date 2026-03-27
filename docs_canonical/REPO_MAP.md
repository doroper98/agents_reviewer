# Event Analysis Team — Repository Map

## Source Structure
```
src/
├── __init__.py
├── main.py              # Entry point — Telegram bot startup
├── config.py            # Environment config (API keys, settings)
├── models.py            # Pydantic data models for all analysis types
├── orchestrator.py      # 5-phase pipeline orchestrator
├── telegram_bot.py      # Telegram bot handlers
├── agents/
│   ├── __init__.py
│   ├── base.py          # BaseAgent — Claude API wrapper
│   ├── event_identifier.py
│   ├── macro_analyst.py
│   ├── geopolitical_analyst.py
│   ├── micro_analyst.py
│   ├── investment_analyst.py
│   ├── history_ethics_analyst.py
│   ├── devils_advocate.py
│   └── report_synthesizer.py
└── templates/
    └── report.html      # Jinja2 HTML report template
```

## Style Guide
```
src/style_guide/
└── soft-brutalism.css   # YK_ soft-brutalism theme (inline in report)
```

## Configuration Files
- `.env` — API keys (git ignored)
- `.env.example` — Template for .env
- `requirements.txt` — Python dependencies
