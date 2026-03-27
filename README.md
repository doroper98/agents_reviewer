# Event Analysis Team — AI Agent System

텔레그램을 통해 이벤트/사건 분석 명령을 내리면, 9개의 전문 AI 에이전트가
협업하여 **거시경제, 지정학, 미시경제, 투자, 역사/윤리적** 관점에서 종합 분석 후
비주얼 HTML 보고서를 생성하는 시스템.

## Architecture

```
User (Telegram)
    │
    ▼
┌──────────────────┐
│  Telegram Bot     │ ← 명령 수신 / 보고서 전송
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Orchestrator     │ ← 5단계 파이프라인 지휘
└────────┬─────────┘
         │
    ┌────┼────┬────┬────┐
    ▼    ▼    ▼    ▼    ▼
 Macro  Geo  Micro Invest History
    │    │    │    │    │
    └────┴────┴────┴────┘
         │
         ▼
┌──────────────────┐
│ Devil's Advocate  │ ← 감사/검증
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Report Synthesizer│ ← HTML 보고서 생성
└──────────────────┘
```

## Team Composition (9 Agents)

| # | Agent | Role |
|---|-------|------|
| 1 | **Orchestrator** | 파이프라인 지휘, 태스크 분배 |
| 2 | **Event Identifier** | 사건 5W1H 프로필 생성 |
| 3 | **Macro Analyst** | 거시경제 파급력 분석 |
| 4 | **Geopolitical Analyst** | 지정학적 파급력 분석 |
| 5 | **Micro Analyst** | 미시경제 파급력 분석 |
| 6 | **Investment Analyst** | 투자 영향 분석 |
| 7 | **History & Ethics Analyst** | 역사적 유사사례 + 윤리적 판단 |
| 8 | **Devil's Advocate** | 비판적 검증, 편향 탐지, 감사 |
| 9 | **Report Synthesizer** | 비주얼 HTML 보고서 생성 |

## Dual Execution Mode

### Mode A: API Mode
```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
```
- 직접 Anthropic API 호출
- 5개 에이전트 병렬 실행 (빠름)
- API 크레딧 소진

### Mode B: Claude Code Mode (Claude Max 구독)
```bash
# .env — API 키 비워두기
ANTHROPIC_API_KEY=
```
- `claude` CLI를 subprocess로 호출
- Max 구독 토큰 활용 (추가 비용 없음)
- 순차 실행

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/doroper98/agents_reviewer.git
cd agents_reviewer
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your tokens

# 3. Run
python -m src.main
```

## Report Design

HTML 보고서는 다음 디자인 요소를 포함합니다:
- Noto Serif KR / Noto Sans KR / JetBrains Mono 타이포그래피
- 4-Quadrant 영향도 매트릭스 (거시/지정학/미시/투자)
- 역사적 타임라인 시각화
- 4대 윤리 프레임워크 (공리주의/의무론/덕윤리/사회정의)
- Devil's Advocate 감사 체크리스트
- 단기/중기/장기 전망 카드

## Project Structure (YK_BP Methodology)

```
agents_reviewer/
├── CLAUDE.md            # AI 에이전트 행동 규칙
├── DEVLOG.md            # 개발 로그
├── GOAL.md              # 요구사항 & 성공 기준
├── WORKFLOWS.md         # 실행 절차
├── docs_canonical/      # 정규 문서 4종
├── docs/                # 추가 문서
├── src/
│   ├── main.py          # Entry point
│   ├── config.py        # 환경 설정
│   ├── models.py        # Pydantic 데이터 모델
│   ├── orchestrator.py  # 5단계 파이프라인
│   ├── telegram_bot.py  # 텔레그램 연동
│   ├── agents/          # 9개 전문 에이전트
│   └── templates/       # HTML 보고서 템플릿
└── reports/             # 생성된 보고서 (git ignored)
```
