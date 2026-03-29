# Event Analysis Team — AI Agent System

텔레그램을 통해 이벤트/사건 분석 명령을 수신하고, 7개의 전문 AI 에이전트가
협업하여 **상황인식, 이해관계자, 구조분석, 연쇄반응, 시나리오, 시각화** 관점에서
종합 분석 후 6막 극장 구조 HTML 보고서를 생성하는 시스템.

## Architecture

```
사용자 (텔레그램)
    │
    ▼
┌──────────────────┐
│  Telegram Bot     │ ← 명령 수신 / 보고서 전송
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Orchestrator     │ ← 4단계 파이프라인 지휘
└────────┬─────────┘
         │
   Phase 1: 상황인식 분석관 (웹 검색)
         │
   Phase 2: 이해관계자 → 구조/상호작용
         │
   Phase 3: 연쇄반응 → 시나리오
         │
   Phase 3.5: 시각화 분석관 (SVG/지도/차트)
         │
   Phase 4: 보고서 합성관 (HTML + Cloudflare 배포)
         │
         ▼
Cloudflare Pages (analysis-reports.pages.dev)
    → HTML 보고서 호스팅
```

## Team Composition (7 Agents)

| # | 에이전트 | 파일 | 역할 |
|---|---------|------|------|
| 1 | 상황인식 분석관 | `context_analyst.py` | ACT I: 팩트, 타임라인, 핵심 수치, 웹 검색 |
| 2 | 이해관계자 분석관 | `player_analyst.py` | ACT II: 행위자 식별, 전략, 위험도 |
| 3 | 구조 및 상호작용 분석관 | `dynamics_analyst.py` | ACT III: 게임이론, 비대칭, 전환점 |
| 4 | 연쇄반응 분석관 | `chain_reaction_analyst.py` | ACT IV: 인과 사슬, 도미노 효과 |
| 5 | 향후 시나리오 분석관 | `scenario_architect.py` | ACT V+VI: 4개 시나리오 + 감시 신호 |
| 6 | 시각화 분석관 | `visual_analyst.py` | SVG 관계도, Leaflet 지도, Canvas 차트 |
| 7 | 보고서 합성관 | `report_synthesizer.py` | HTML 생성, Cloudflare 업로드 |

## Execution Mode — Claude Code CLI (Max 플랜)

```bash
# .env — API 키 비워두기 (Max 플랜 CLI 모드)
ANTHROPIC_API_KEY=
```

- `claude` CLI를 subprocess로 호출
- Max 구독 토큰 활용 (추가 비용 없음)
- 순차 실행 (1GB VM 메모리 제한)
- `--dangerously-skip-permissions --allowedTools "WebFetch,WebSearch"`

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/doroper98/agents_reviewer.git
cd agents_reviewer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your tokens

# 3. Run
python -m src.main
```

## Telegram Usage

- **일반 메시지** → 풀 분석 시작 (7개 에이전트 순차 실행)
- **`?` 접두어** → 간단 질답 (`? SPR이 뭐야?`)
- 분석 중 에이전트별 실시간 상태 메시지
- 최종: 코드블록 텍스트 보고서 + HTML 파일 + Cloudflare 공유 링크

## Report Design (6막 극장 구조)

- 6막 극장 구조 (ACT I ~ VI)
- CSS: 6막 극장 디자인 시스템 (14px body, 960px 컨테이너)
- 폰트: Noto Serif KR (제목/가격), Noto Sans KR (본문/라벨)
- 시각화: SVG 관계도/플로우차트, Leaflet 지도, Canvas 2D 차트
- 모바일 반응형 (540px, 700px breakpoints)
- Cloudflare Pages 배포 + 공유 링크

## Project Structure

```
agents_reviewer/
├── CLAUDE.md              # AI 에이전트 행동 규칙
├── DEVLOG.md              # 전체 개발 로그
├── GOAL.md                # 요구사항 & 성공 기준
├── WORKFLOWS.md           # 실행 절차
├── docs_canonical/        # 정규 문서 4종
│   ├── ARCHITECTURE.md
│   ├── REPO_MAP.md
│   ├── STYLEGUIDE.md
│   └── TESTING.md
├── src/
│   ├── main.py            # Entry point
│   ├── config.py          # 환경 설정 (Pydantic Settings)
│   ├── models.py          # Pydantic 데이터 모델
│   ├── orchestrator.py    # 4단계 파이프라인
│   ├── telegram_bot.py    # 텔레그램 연동
│   ├── agents/            # 7개 전문 에이전트
│   │   ├── base.py
│   │   ├── context_analyst.py
│   │   ├── player_analyst.py
│   │   ├── dynamics_analyst.py
│   │   ├── chain_reaction_analyst.py
│   │   ├── scenario_architect.py
│   │   ├── visual_analyst.py
│   │   └── report_synthesizer.py
│   └── templates/         # HTML 보고서 템플릿
│       ├── report.html
│       └── report.css
├── reports/               # 생성된 보고서 (git ignored)
└── prototype_gold_chart.html  # Canvas 차트 참조 구현
```

## Token Usage (분석 1건당 추정)

| 시나리오 | 입력 토큰 | 출력 토큰 | 합계 |
|---------|----------|----------|------|
| 짧은 이벤트 | ~16K | ~5K | ~21K |
| 보통 이벤트 | ~28K | ~9K | ~37K |
| 복잡한 이벤트 | ~44K | ~13K | ~57K |

Max 플랜 CLI 모드이므로 API 비용은 없음.
