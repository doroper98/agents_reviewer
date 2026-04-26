---
tier: 1
last_synced_with: v2.6.0
ssot_for:
  - "AI 에이전트 행동 규칙 (Execution Rules)"
  - "Change Propagation 매트릭스 (코드 변경 → 갱신할 문서)"
  - "Canvas 차트 제작 기준"
depends_on:
  - "docs/STYLEGUIDE.md (코드 컨벤션 SSOT)"
  - "DOCS_GOVERNANCE_V3.md (문서 거버넌스 SSOT)"
last_review: 2026-04-26
---

# CLAUDE.md — Event Analysis Team Agent System

## Project Overview
텔레그램 메시지 → 다중 AI 에이전트 분석 → HTML 보고서 → Cloudflare Pages 배포. 시스템 흐름 SSOT 는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech Stack
- Language: Python 3.11+
- AI: Claude Code CLI (claude-opus-4-6, Max 플랜 무료 모드) + 웹 검색
- Messaging: python-telegram-bot
- Data Validation: Pydantic v2
- Report: Jinja2 HTML + 별도 CSS
- Visualization: SVG 직접 생성, Leaflet 지도, Canvas 2D 차트
- Hosting: Cloudflare Pages (wrangler CLI 배포)
- Infra: Oracle Cloud VM (무료 티어)

## Agents
현재 구성 카탈로그(역할·파일 위치)는 [docs/CATALOGS.md §1](docs/CATALOGS.md). 이 문서는 카탈로그를 사본으로 갖지 않는다 (SSOT 단일 출처 원칙).

## Canonical Documents
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 시스템 아키텍처
- [docs/STYLEGUIDE.md](docs/STYLEGUIDE.md) — 코드 컨벤션
- [docs/TESTING.md](docs/TESTING.md) — 테스트 전략
- [docs/REPO_MAP.md](docs/REPO_MAP.md) — 파일/폴더 구조 설명
- [docs/CATALOGS.md](docs/CATALOGS.md) — 에이전트·렌즈·블록 카탈로그
- [docs/DATA_MODELS.md](docs/DATA_MODELS.md) — Pydantic 모델 도식
- [DEVLOG.md](DEVLOG.md) — 전체 개발 로그 (인프라, 트러블슈팅 포함)
- [CHANGELOG.md](CHANGELOG.md) — 사용자 관점 릴리스 노트
- [DOCS_GOVERNANCE_V3.md](DOCS_GOVERNANCE_V3.md) — 문서 거버넌스 (3-tier, SSOT 매트릭스)

## Canvas 차트 제작 기준
- 참조 구현: [docs/references/prototype_gold_chart.html](docs/references/prototype_gold_chart.html)
- 해상도: 최소 3x DPR
- 폰트: Noto Serif KR (가격/숫자), Noto Sans KR (라벨/설명/제목)
- 가격 라벨: 스팟 위 20px, 겹침 시 자동 상향 조정
- 이벤트 라벨: 차트 하단, -45도 좌하향, 6글자 줄바꿈
- 곡선: quadratic bezier, 구간별 색상 분리

## Execution Rules
1. 모든 코드 변경 후 `python -m py_compile` 검증
2. Type hints 필수
3. Pydantic 모델 사용 (dict 금지)
4. Agent system prompt 는 한국어 + 영어 혼용 가능
5. 커밋 메시지: `v{VER}: {변경 요약}`
6. CLI 모드: `--dangerously-skip-permissions --allowedTools "WebFetch,WebSearch"`
7. 시스템 프롬프트에 `.format()` 사용 금지 → `.replace()` 사용 (JSON `{}` 충돌 방지)
8. AnalysisStrategy 는 dict 가 아닌 Pydantic 모델로만 다룬다. dict 회귀 금지 ([REFACTOR_V3_PLAN.md §8](REFACTOR_V3_PLAN.md) Anti-pattern #3). per-agent directive 는 transitional `legacy_directives` 필드를 통해서만 접근.
9. 신규 문서는 [DOCS_GOVERNANCE_V3.md](DOCS_GOVERNANCE_V3.md) 의 YAML 헤더 규약 + SSOT 매트릭스를 따름. 사실은 한 곳에만 적고 다른 곳은 링크.

## Change Propagation Matrix
**코드를 변경했다면 같은 커밋에서 아래의 문서도 함께 갱신한다.** SSOT 매트릭스는 [DOCS_GOVERNANCE_V3.md §3](DOCS_GOVERNANCE_V3.md).

| 코드 변경 | 동시 갱신해야 할 문서 |
|-----------|----------------------|
| `src/orchestrator.py:VERSION` 증가 | [README.md](README.md) `Status`, [CHANGELOG.md](CHANGELOG.md) (신규 항목 추가), 영향받은 모든 문서 헤더의 `last_synced_with` |
| `src/models.py` 모델 추가/변경 | [docs/DATA_MODELS.md](docs/DATA_MODELS.md) (도식 + 의미 가이드) |
| `src/agents/*` 신규 추가/삭제 | [docs/CATALOGS.md §1](docs/CATALOGS.md), [docs/REPO_MAP.md](docs/REPO_MAP.md) |
| `src/lenses/*` 신규 추가 (V3 Step 5 후) | [docs/CATALOGS.md §2](docs/CATALOGS.md) |
| `src/archetypes/*` 신규 추가 (V3 Step 2 활성) | [docs/CATALOGS.md §3](docs/CATALOGS.md), [docs/ARCHITECTURE.md §5.1](docs/ARCHITECTURE.md) |
| `src/templates/blocks/*` 신규 추가 (V3 Step 3 후) | [docs/CATALOGS.md §4](docs/CATALOGS.md) |
| `src/templates/archetypes/*` 신규 추가 | [docs/REPO_MAP.md](docs/REPO_MAP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| [GOAL.md](GOAL.md) `REQ-*` 추가/완료 | [DEVLOG.md](DEVLOG.md) 에 변경 기록 |
| 의존성 추가 (`requirements.txt`) | [DEVLOG.md](DEVLOG.md), [README.md](README.md) Quick Start |
| 워크플로우 변경 | [WORKFLOWS.md](WORKFLOWS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 인프라 변경 (Cloudflare/VM) | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [DEVLOG.md](DEVLOG.md) |

## Anti-Patterns (문서)
[DOCS_GOVERNANCE_V3.md §9](DOCS_GOVERNANCE_V3.md) Anti-patterns 1~10 절대 위반 금지. 핵심:
- 사실을 두 곳에 적기 금지 → 한쪽은 링크
- `last_synced_with` 갱신 안 한 채 본문만 수정 금지
- DEVLOG 과거 항목 수정 금지 (append-only). 정정은 새 항목으로
- GOAL 의 REQ-* 삭제 금지. deprecated 마킹만

## Key Directories
- `src/agents/` — 분석 에이전트 정의 (현재 7개)
- `src/templates/` — HTML 보고서 템플릿
- `src/templates/report.css` — 보고서 CSS
- `docs/` — 모든 정규 문서 (이전 `docs_canonical/` 에서 이름 단순화)
- `docs/references/` — 참조 자료 (prototype HTML)
- `reports/` — 생성된 HTML 보고서 (git ignored)
