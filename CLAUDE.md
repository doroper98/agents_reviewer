# CLAUDE.md — Event Analysis Team Agent System

## Project Overview
텔레그램을 통해 이벤트/사건 분석 명령을 수신하고, 7개의 전문 AI 에이전트가
협업하여 상황인식, 이해관계자, 구조분석, 연쇄반응, 시나리오, 시각화 관점에서
종합 분석 후 valentino-boop 스타일 HTML 보고서를 생성하는 시스템.

## Tech Stack
- Language: Python 3.11+
- AI: Claude Code CLI (claude-opus-4-6, Max 플랜 무료 모드) + 웹 검색
- Messaging: python-telegram-bot
- Data Validation: Pydantic v2
- Report: Jinja2 HTML + valentino-boop CSS (6막 극장 구조)
- Visualization: SVG 직접 생성, Leaflet 지도, Canvas 2D 차트
- Hosting: Cloudflare Pages (wrangler CLI 배포)
- Infra: Oracle Cloud VM (무료 티어)

## Agents (7개)
| 에이전트 | 파일 | 역할 |
|---------|------|------|
| 상황인식 분석관 | `context_analyst.py` | ACT I: 팩트, 타임라인, 웹 검색 |
| 이해관계자 분석관 | `player_analyst.py` | ACT II: 행위자, 전략, 위험도 |
| 구조 및 상호작용 분석관 | `dynamics_analyst.py` | ACT III: 게임이론, 전환점 |
| 연쇄반응 분석관 | `chain_reaction_analyst.py` | ACT IV: 인과 사슬, 도미노 |
| 향후 시나리오 분석관 | `scenario_architect.py` | ACT V+VI: 시나리오 + 감시 신호 |
| 시각화 분석관 | `visual_analyst.py` | SVG 관계도, 지도, 차트 |
| 보고서 합성관 | `report_synthesizer.py` | HTML 생성, Cloudflare 업로드 |

## Canonical Documents
- `docs_canonical/ARCHITECTURE.md` — 시스템 아키텍처
- `docs_canonical/STYLEGUIDE.md` — 코드 컨벤션
- `docs_canonical/TESTING.md` — 테스트 전략
- `docs_canonical/REPO_MAP.md` — 파일/폴더 구조 설명
- `DEVLOG.md` — 전체 개발 로그 (인프라, 트러블슈팅 포함)

## Canvas 차트 제작 기준
- 참조 구현: `prototype_gold_chart.html`
- 해상도: 최소 3x DPR
- 폰트 규칙 (JetBrains Mono 사용 금지):
  - 가격/숫자: Noto Serif KR bold (예: $4,460)
  - 라벨/설명: Noto Sans KR (예: 현재가, Jan, 이란 전쟁 개시)
  - 제목: Noto Serif KR 900
- 가격 라벨: 스팟 위 20px, 겹침 시 자동 상향 조정
- 이벤트 라벨: 차트 하단, -45도 좌하향, 오른쪽 정렬, 6글자 줄바꿈
- 곡선: quadratic bezier, 구간별 색상 분리
- 호버: 크로스헤어 + 네이비 툴팁
- 여백: right 70px+, bottom 80px+
- 범례: HTML footer 가운데 정렬, canvas 내부 중복 금지

## Execution Rules
1. 모든 코드 변경 후 `python -m py_compile` 검증
2. Type hints 필수
3. Pydantic 모델 사용 (dict 금지)
4. Agent system prompt는 한국어 + 영어 혼용 가능
5. 커밋 메시지: `v{VER}: {변경 요약}`
6. CLI 모드: `--dangerously-skip-permissions --allowedTools "WebFetch,WebSearch"`
7. 시스템 프롬프트에 `.format()` 사용 금지 → `.replace()` 사용 (JSON `{}` 충돌 방지)

## Key Directories
- `src/agents/` — 7개 전문 에이전트 정의
- `src/templates/` — HTML 보고서 템플릿 (valentino-boop 스타일)
- `src/style_guide/` — CSS 테마
- `docs_canonical/` — 정규 문서 4종
- `reports/` — 생성된 HTML 보고서 출력 디렉토리
