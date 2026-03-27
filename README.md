# Event Analysis Team - AI Agent System

텔레그램을 통해 이벤트/사건 분석 명령을 내리면, 9개의 전문 AI 에이전트가
협업하여 거시경제, 지정학, 미시경제, 투자, 역사/윤리적 관점에서 종합 분석 후
비주얼 보고서를 생성하는 시스템.

## Architecture

```
User (Telegram) → Orchestrator → [Analysis Agents] → Report → User (Telegram)
```

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env  # API 키 설정
python -m src.main
```
