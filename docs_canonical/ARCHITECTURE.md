# Event Analysis Team — Architecture

## Tech Stack
| Area | Technology | Rationale |
|------|-----------|-----------|
| Language | Python 3.11+ | async/await, type hints, AI ecosystem |
| AI Engine | Anthropic Claude API | Structured output, tool use, reasoning |
| Messaging | python-telegram-bot | Async, webhook support |
| Data Models | Pydantic v2 | Validation, serialization |
| Report Template | Jinja2 | HTML templating |
| CSS Theme | YK_ soft-brutalism | Professional, readable |
| Charts | Plotly.js (CDN) | Interactive, no server needed |

## System Architecture

```
┌──────────────┐     ┌──────────────────────────────────────┐
│  Telegram     │────▶│  Telegram Bot (telegram_bot.py)      │
│  User         │◀────│  - Command parsing                   │
└──────────────┘     │  - Status updates                    │
                     │  - Report delivery                   │
                     └──────────┬───────────────────────────┘
                                │
                     ┌──────────▼───────────────────────────┐
                     │  Orchestrator (orchestrator.py)       │
                     │  - Task decomposition                │
                     │  - Agent coordination                │
                     │  - Pipeline management               │
                     └──────────┬───────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
     ┌────────────┐   ┌────────────────┐  ┌──────────────┐
     │ Phase 2:    │   │ Phase 3:       │  │ Phase 4:     │
     │ Event ID    │   │ Parallel       │  │ Audit        │
     │             │   │ Analysis (5x)  │  │ (Devil's     │
     │             │   │                │  │  Advocate)   │
     └─────────────┘   └────────────────┘  └──────────────┘
                                │
                     ┌──────────▼───────────────────────────┐
                     │  Report Synthesizer                   │
                     │  - Jinja2 template rendering         │
                     │  - Plotly chart generation            │
                     │  - HTML file output                  │
                     └──────────────────────────────────────┘
```

## Data Flow
1. User sends Telegram message → Bot parses AnalysisRequest
2. Orchestrator creates pipeline → Event Identifier runs first
3. EventProfile shared with 5 parallel analysts
4. All results sent to Devil's Advocate for audit
5. If REVISE → specific agents re-run with feedback
6. Report Synthesizer generates HTML → sent via Telegram

## Agent Communication
- All agents communicate via Pydantic models (no raw dicts)
- Orchestrator holds the FullAnalysisResult state
- Each agent receives relevant context and returns typed output
