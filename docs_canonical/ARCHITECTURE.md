# Event Analysis Team — Architecture

## Tech Stack
| Area | Technology | Rationale |
|------|-----------|-----------|
| Language | Python 3.11+ | async/await, type hints, AI ecosystem |
| AI Engine | Claude Code CLI (Opus) | Max 플랜 subprocess 호출, 웹 검색 |
| Messaging | python-telegram-bot | Async 텔레그램 봇 |
| Data Models | Pydantic v2 | Validation, serialization |
| Report Template | Jinja2 | HTML 렌더링 |
| CSS | report.css | 별도 파일, 6막 극장 구조 |
| Visualization | SVG 직접 생성 | 관계도, 플로우차트 |
| Maps | Leaflet.js (CDN) | 지정학 분석 시 |
| Charts | Canvas 2D / TradingView | 금융=TradingView, 기타=Canvas |
| Hosting | Cloudflare Pages | wrangler CLI 배포 |
| Server | Oracle Cloud VM | 무료 티어, Ubuntu 22.04 |

## System Architecture

```
┌──────────────┐     ┌──────────────────────────────────────┐
│  Telegram     │────▶│  Telegram Bot (telegram_bot.py)      │
│  User         │◀────│  - Message handling                  │
└──────────────┘     │  - Status updates                    │
                     │  - Report delivery                   │
                     └──────────┬───────────────────────────┘
                                │
                     ┌──────────▼───────────────────────────┐
                     │  Orchestrator (orchestrator.py)       │
                     │  - 4-phase pipeline                  │
                     │  - Sequential agent execution        │
                     │  - FullAnalysisResult accumulation    │
                     └──────────┬───────────────────────────┘
                                │
         Phase 1: ① 상황인식 분석관 (웹 검색)
                  ▼
         Phase 2: ② 이해관계자 → ③ 구조/상호작용
                  ▼
         Phase 3: ④ 연쇄반응 → ⑤ 시나리오
                  ▼
         Phase 3.5: ⑥ 시각화 (SVG/지도/차트)
                  ▼
         Phase 4: ⑦ 보고서 합성 → Cloudflare 배포

```

## Data Flow
1. User sends Telegram message → Bot creates AnalysisRequest
2. Orchestrator runs 7 agents sequentially (context cascading)
3. Each agent: system prompt + accumulated context → Claude CLI → JSON → Pydantic model
4. Report Synthesizer: Jinja2 render → HTML save → wrangler deploy → Cloudflare URL
5. Bot sends: text summary + HTML file + share link

## Agent Communication
- All agents communicate via Pydantic models (no raw dicts)
- Orchestrator holds the FullAnalysisResult state
- Each agent receives all previous results and returns typed output
- Claude CLI called via subprocess with `--dangerously-skip-permissions`
