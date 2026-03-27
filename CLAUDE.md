# CLAUDE.md — Event Analysis Team Agent System

## Project Overview
텔레그램을 통해 이벤트/사건 분석 명령을 수신하고, 9개의 전문 AI 에이전트가
협업하여 거시경제, 지정학, 미시경제, 투자, 역사/윤리적 관점에서 종합 분석 후
비주얼 HTML 보고서를 생성하는 시스템.

## Tech Stack
- Language: Python 3.11+
- AI: Anthropic Claude API (claude-sonnet-4-6)
- Messaging: python-telegram-bot
- Data Validation: Pydantic v2
- Report: Jinja2 HTML + YK_ soft-brutalism CSS
- Visualization: Plotly (interactive charts)

## Canonical Documents
- `docs_canonical/ARCHITECTURE.md` — 시스템 아키텍처
- `docs_canonical/STYLEGUIDE.md` — 코드 컨벤션
- `docs_canonical/TESTING.md` — 테스트 전략
- `docs_canonical/REPO_MAP.md` — 파일/폴더 구조 설명

## Execution Rules
1. 모든 코드 변경 후 `python -m py_compile` 검증
2. Type hints 필수
3. Pydantic 모델 사용 (dict 금지)
4. Agent system prompt는 한국어 + 영어 혼용 가능
5. 커밋 메시지: `v{VER}: {변경 요약}`

## Key Directories
- `src/agents/` — 9개 전문 에이전트 정의
- `src/templates/` — HTML 보고서 템플릿
- `src/style_guide/` — YK_ CSS 테마
- `docs_canonical/` — 정규 문서 4종
