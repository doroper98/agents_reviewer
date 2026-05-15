---
tier: 3
last_synced_with: v5.2.3
ssot_for:
  - "개발 상세 로그 (append-only)"
  - "인프라 설치 가이드"
  - "트러블슈팅 기록"
depends_on:
  - "GOAL.md (REQ-* 변경 추적)"
  - "CHANGELOG.md (사용자 관점 변경은 그쪽 SSOT)"
last_review: 2026-05-15
---

# DEVLOG — Event Analysis Team Agent System

> 전체 개발 과정 기록. 인프라 설정부터 에이전트 설계, 트러블슈팅까지 포함.
> 이 문서만 있으면 동일한 시스템을 처음부터 재구축할 수 있음.

---

## 1. 프로젝트 개요

- 텔레그램으로 분석 명령 수신 → 7개 AI 에이전트가 순차 분석 → HTML 보고서 생성 → Cloudflare Pages 배포
- Claude Max 플랜 기반 (API 비용 없음, CLI 모드로 호출)
- Oracle Cloud 무료 VM에서 24시간 운영
- 보고서 스타일: 6막 극장 6막 극장 구조

---

## 2. 시스템 구성도

```
사용자 (텔레그램)
    ↓
Oracle Cloud VM (ubuntu@144.24.88.73)
    ├── Python 봇 (python -m src.main)
    ├── Claude Code CLI (Max 플랜 인증)
    └── Wrangler CLI (Cloudflare 배포)
    ↓
Cloudflare Pages (analysis-reports.pages.dev)
    → HTML 보고서 호스팅
```

---

## 3. 인프라 설정 가이드

### Oracle Cloud VM 설정

- VM.Standard.E2.1.Micro (무료 티어), Ubuntu 22.04
- Public IP 할당: Networking → IP administration → Ephemeral public IP
- Public subnet 인터넷 연결: Quick actions → "Connect public subnet to internet"
- SSH 키 생성 및 다운로드 (생성 시 한 번만 제공, 재발급 불가)
- SSH 접속: `ssh -i "키파일.key" ubuntu@IP주소`
- 비밀번호 로그인 활성화 (모바일 접속용):
  - `sudo passwd ubuntu`
  - `/etc/ssh/sshd_config.d/60-cloudimg-settings.conf`에서 `PasswordAuthentication yes`로 변경
  - 주의: `sshd_config`가 아니라 `60-cloudimg-settings.conf`가 override함!

### Cloudflare Pages 설정

- cloudflare.com 가입 (Personal, 무료)
- Workers & Pages → "Looking to deploy Pages? Get started"
- 프로젝트명: `analysis-reports`
- Direct Upload 방식 (GitHub 연동 없음 = 개인정보 노출 제로)
- API Token: My Profile → API Tokens → "Edit Cloudflare Workers" 템플릿
- 필요 정보: Account ID (대시보드에 표시), API Token (한 번만 표시)
- 업로드: Wrangler CLI 사용 (`wrangler pages deploy`)

### 텔레그램 봇 설정

- @BotFather → /newbot → 봇 이름/username 설정
- HTTP API 토큰 저장

### 서버 소프트웨어 설치 순서

```bash
# 1. 시스템 패키지
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git

# 2. Node.js (Claude Code CLI용)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 3. Claude Code CLI
sudo npm install -g @anthropic-ai/claude-code
claude login  # Max 플랜 인증 (브라우저 URL 복사 → PC에서 인증)

# 4. Wrangler CLI (Cloudflare 배포용)
sudo npm install -g wrangler

# 5. 프로젝트 클론 및 설정
git clone https://github.com/doroper98/agents_reviewer.git
cd agents_reviewer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env 편집 (토큰 입력)

# 6. 봇 실행
python -m src.main
```

---

## 4. .env 설정

```
ANTHROPIC_API_KEY=          # 비워두면 CLI 모드 (Max 플랜)
TELEGRAM_BOT_TOKEN=xxx      # BotFather 토큰
ALLOWED_CHAT_IDS=           # 비워두면 누구나 사용 가능
CLOUDFLARE_ACCOUNT_ID=xxx
CLOUDFLARE_API_TOKEN=xxx
CLOUDFLARE_PROJECT_NAME=analysis-reports
REPORT_OUTPUT_DIR=reports
MODEL_NAME=claude-opus-4-6  # 또는 claude-sonnet-4-6
```

---

## 5. 에이전트 팀 구성 (v1.3 기준)

| # | 에이전트 | 파일 | 역할 |
|---|---------|------|------|
| 1 | 상황인식 분석관 | `context_analyst.py` | ACT I: 팩트, 타임라인, 핵심 수치, 웹 검색 |
| 2 | 이해관계자 분석관 | `player_analyst.py` | ACT II: 행위자 식별, 전략, 위험도 |
| 3 | 구조 및 상호작용 분석관 | `dynamics_analyst.py` | ACT III: 게임이론, 비대칭, 전환점 |
| 4 | 연쇄반응 분석관 | `chain_reaction_analyst.py` | ACT IV: 인과 사슬, 도미노 효과 |
| 5 | 향후 시나리오 분석관 | `scenario_architect.py` | ACT V+VI: 4개 시나리오 + 감시 신호 |
| 6 | 시각화 분석관 | `visual_analyst.py` | SVG 관계도, Leaflet 지도, Canvas 차트 |
| 7 | 보고서 합성관 | `report_synthesizer.py` | HTML 생성, Cloudflare 업로드 |

---

## 6. 분석 파이프라인

```
Phase 1: 상황인식 분석관 (웹 검색으로 최신 데이터 수집)
Phase 2: 이해관계자 분석관 + 구조 및 상호작용 분석관 (순차)
Phase 3: 연쇄반응 분석관 + 향후 시나리오 분석관 (순차)
Phase 3.5: 시각화 분석관 (SVG/지도/차트 생성)
Phase 4: 보고서 합성관 (HTML 렌더링 + Cloudflare 배포)
```

---

## 7. 보고서 구조 (6막 극장 구조)

- 6막 극장 구조 (ACT I ~ VI)
- CSS: 6막 극장 디자인 시스템 (14px body, 960px 컨테이너, 11색상)
- 폰트: Noto Serif KR (제목), Noto Sans KR (본문), JetBrains Mono (데이터)
- 시각화: SVG 관계도/플로우차트, Leaflet 지도, Canvas 차트
- Cloudflare 공유 링크 포함 (footer)
- 모바일 반응형 (540px, 700px breakpoints)

### Canvas 차트 제작 기준 (prototype_gold_chart.html 참조)

- **해상도**: `dpr = Math.max(devicePixelRatio, 3)` — 최소 3배 렌더링
- **가격 라벨**: 반드시 스팟(도형) 위에 표시, 간격 최소 20px
- **가격 겹침 방지**: 기존 라벨 위치를 배열로 추적, 겹치면 위로 밀어냄 (14px 단위)
- **이벤트 라벨**: 세로 점선 아래(차트 하단)에 표시, -45도 기울기(좌하향)
- **이벤트 라벨 정렬**: 오른쪽 정렬 (`textAlign='right'`), 텍스트 끝이 이벤트 지점에 닿음
- **이벤트명 줄바꿈**: 6글자 초과 시 줄바꿈, 한 줄 최대 6글자
- **월 기준 세로선**: 가로 눈금선과 동일한 스타일 (`#F0EDE6`, 0.5px)
- **구간 색상 분리**: 이벤트 전후를 다른 색으로 표현 (예: 전쟁 전=금색, 후=빨강)
- **곡선**: quadratic bezier 사용 (`ctx.quadraticCurveTo`)
- **호버 툴팁**: 크로스헤어 + 네이비 배경 라운드 박스 + 날짜/가격 표시
- **여백**: right 70px 이상 (텍스트 잘림 방지), bottom 80px 이상 (이벤트 라벨 공간)
- **범례**: HTML footer에 가운데 정렬, canvas 내부 중복 금지

---

## 8. 텔레그램 기능

- 일반 메시지 → 풀 분석 시작
- `?` 접두어 → 간단 질답 (`? SPR이 뭐야?`)
- 분석 중 에이전트별 실시간 상태 메시지 (새 메시지가 쌓이는 형태)
- 최종: 코드블록 텍스트 보고서 + HTML 파일 + 공유 링크

---

## 9. 버전 히스토리

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v0.1.0 | 2026-03-27 | 초기 스캐폴드 — 9개 에이전트, 오케스트레이터, 텔레그램 봇 |
| v0.2.0 | 2026-03-27 | Claude Code CLI 모드 추가 (Max 플랜 무료 사용) |
| v0.2.1~4 | 2026-03-27 | config 파싱 버그 수정, CLI 옵션 수정, 순차 실행 전환 |
| v0.3.0 | 2026-03-28 | 투자/윤리 에이전트 삭제, Plotly 차트, 이모지 상태 |
| v0.3.1 | 2026-03-28 | 음슴체 프롬프트 전면 적용 |
| v1.0.0 | 2026-03-28 | 완전 재구축 — 6막 6막 극장 구조, 5개 새 에이전트 |
| v1.0.1 | 2026-03-28 | 에이전트 국문 이름, 메시지 추가 형태, % 신뢰도 |
| v1.0.2 | 2026-03-28 | 보고서 footer 공유 링크, 모바일 최적화 |
| v1.1.0 | 2026-03-28 | Opus 모델, AI 패턴 제거, 용어 정의(glossary) |
| v1.1.1 | 2026-03-28 | Cloudflare 업로드 수정 (curl → wrangler) |
| v1.1.2 | 2026-03-28 | HTML 파일 캡션에 공유 링크 |
| v1.2.0 | 2026-03-28 | 시각화 분석관 추가 (SVG, Leaflet, Canvas) |
| v1.2.1 | 2026-03-28 | Cloudflare URL에 파일명 포함 |
| v1.2.2 | 2026-03-28 | 섹션 명칭 변경 (상황인식, 연쇄반응, 향후 시나리오 등) |
| v1.2.3 | 2026-03-28 | 타임라인 셀 높이 통일, 영향 줄바꿈 화살표 |
| v1.2.4 | 2026-03-28 | 중복 보고서 URL 메시지 제거 |
| v1.3.0 | 2026-03-28 | 프리미엄 시각화 (SVG 직접 생성), ? 질문 기능 |
| v1.3.1 | 2026-03-28 | 이해관계자 한글 태그, 웹 검색으로 최신 데이터 |
| v1.3.2 | 2026-03-28 | system prompt .format() → .replace() 버그 수정 |
| v2.5.0 | 2026-04-26 | 분석 용어 학부생 수준화 + 분석 시각 풀 확장 + 균형 분석 4단락 |
| v2.4.1 | 2026-04-26 | 문서 거버넌스 V3 적용 (3-tier, SSOT 매트릭스, README 슬림화) |

> 이후 릴리스 노트의 SSOT 는 [CHANGELOG.md](CHANGELOG.md). 본 표는 historical snapshot 으로 보존.

---

## 9.H. v3.0.0 — Step 5-C: archetype 11종 완성 + 페르소나 → lens 이전 (V3 메이저)

2026-04-27 적용. [REFACTOR_V3_PLAN.md §5 Step 5](REFACTOR_V3_PLAN.md) 의 5-C — V3 리팩토링 최종 세션. 메이저 릴리스 v3.0.0.

### 사용자 승인 결정 (착수 전 확정)

- **A: archetype 매트릭스 정밀 분리** — 1순위는 분야+의도 조합. 같은 분야라도 의도에 따라 다른 archetype 으로 라우팅 (예: tech+what_next → scenario_first, tech+what_to_do → decision_brief, tech+why_happened → tech_decomposition). geopolitical 은 3순위로 강등.
- **B: 페르소나 → lens 이전 시 alias 재바인딩 회피** — `LensRunner.run()` vs 페르소나 `.analyze()` 인터페이스가 달라 alias 재바인딩 시 호출 측 코드 깨짐. 대신 (a)+(b) 하이브리드: 페르소나 모듈 보존 + module-level `DeprecationWarning` + `src/agents/__init__.py` 가 lens 클래스도 함께 노출. v4.0.0 에서 모듈 제거 (`FUT-LEGACY-001`).
- **C: lens 11종 표기** — 분야 6 + 메타 2 + 페르소나 이전 3 = 11. AC-7 의 "≥9" 충족. 모든 문서 표기는 정확히 "11종 (분야 6 + 메타 2 + 페르소나 이전 3)".
- **D: AC-8 Pydantic ValidationError 수용** — `recommended_lenses: max_length=4` 로 5개 이상 시 `ValidationError` (subclass of `ValueError`). 이중 가드는 orchestrator `LENS_CAP_PER_EVENT=4`.
- **E: 하이브리드 라우팅** — Strategy Planner 가 LLM 후보 1순위를 출력, `select_archetype()` matrix 가 최종 결정자. mismatch 시 INFO 로그 + matrix 채택 + `strategy.report_archetype` 갱신.

### 수행 내역

**신규 archetype 5종 (`src/archetypes/`)**:
- `decision_brief.py` — `what_to_do` 의도 전용. 판단 요약 → 옵션 비교 → 옵션별 리스크 → 권고 → Pre-mortem → 감시 신호.
- `timeline_first.py` — `what_happened` 의도 전용. 핵심 요약 → 사실 타임라인 → 핵심 수치 → 출처 평가 → 미확인 사항.
- `scenario_first.py` — `what_next` 의도 전용. 기준 시나리오 → 분기 시나리오 → 베이지안 업데이트 가이드 → 감시 신호.
- `mechanism_decomp.py` — `why_happened` 의도 전용. 표층 현상 → 직접 원인 → 구조적 원인 → 제1원리 → 흔한 오해.
- `industry_value_chain.py` — 산업·가치사슬. 산업 구조 → 가치사슬 → 경쟁 구도 → 수익성 압력 → 전략 옵션 → 의사결정 포인트.

**`src/archetypes/registry.py`**:
- `_REGISTRY` 11종 등록 (Step 2 3종 + Step 5-A 3종 + Step 5-C 5종).
- `_classify_event_type()` — free-text event_type → {tech, accident, financial, industry, geopolitical, policy, general} 정규화.
- `select_archetype(strategy)` — 4-tier 우선순위 매트릭스 (분야+의도 → 의도 전용 → geopolitical → fallback). 자세한 분기 표는 [docs/CATALOGS.md §3.1](docs/CATALOGS.md).
- `six_act_theater.suitable_intents` 7종(default) → 2종(`who_benefits`, `what_happened`). 인물극형 specialty 로 좁힘 (Anti-pattern #2 위반 아님 — 코드/템플릿 그대로, 적용 범위만 좁힘).

**페르소나 → lens 이전 3종 (`src/lenses/`)**:
- `stakeholder_lens.py` (구 PlayerAnalyst) — 행위자 식별, 동기, 위험도, 연합 가능성. `suitable_intents=[who_benefits, what_happened]`.
- `structural_lens.py` (구 DynamicsAnalyst) — 게임이론, 비대칭, 전환점, 피드백 루프. `suitable_intents=[why_happened, where_vulnerable]`. 범용.
- `cascade_lens.py` (구 ChainReactionAnalyst) — 인과 사슬, 도미노, 와일드카드, 차단점. `suitable_intents=[where_spreads, what_next]`. 범용.
- `registry.py` 의 `_LENS_CLASSES` 11종 등록 (Step 5-A 8종 + Step 5-C 3종).

**페르소나 deprecation**:
- `src/agents/player_analyst.py`, `dynamics_analyst.py`, `chain_reaction_analyst.py` 각 모듈 최상단에 `_warnings.warn(..., DeprecationWarning, stacklevel=2)` 삽입. `stacklevel=2` 로 호출 측 import 행이 경고 위치로 표기됨.
- `src/agents/__init__.py` — 페르소나 클래스 + 신규 lens 클래스 모두 노출 (alias 재바인딩 *없음*). 호출 측 코드 변경 0.

**Orchestrator 통합**:
- `VERSION v2.9.5 → v3.0.0`.
- `from src.archetypes.registry import select_archetype, get_archetype` import 추가.
- 보고서 합성 직전: LLM 후보 (`get_archetype(strategy.report_archetype)`) + matrix (`select_archetype(strategy)`) 양쪽 산출 → mismatch 시 INFO 로그 → matrix 결과 채택 + `strategy.report_archetype` 갱신 (보고서 헤더 일관성).

**테스트 (`src/tests/test_archetype_selection.py` — 신규 23 케이스)**:
- `TestArchetypeRegistry` — 11종 등록 + Protocol 검증 + `six_act_theater.suitable_intents` narrow 검증 (AC-3).
- `TestNewArchetypeSectionPlans` — 5종 신규 archetype 의 section_plan / archetype_id / suitable_intents parametrize.
- `TestSelectionMatrix` — 10-case 회귀 매트릭스 (6 legacy 케이스 + 4 의도 전용 케이스).
- `TestTechIntentDifferentiation` — tech+what_next → scenario_first / tech+what_to_do → decision_brief / tech+why_happened → tech_decomposition.
- `TestFallbackWarning` — AC-6 fallback warning + 미등록 archetype_id 폴백.

**기존 테스트 갱신 (`src/tests/test_lens_pool.py`)**:
- `test_lens_count_v3` — 11 = 분야 6 + 메타 2 + 페르소나 이전 3.
- `test_archetype_count_v3` — 11.

**문서 동기화 (전체 *.md)**:
- 모든 헤더 `last_synced_with: v3.0.0` (15 파일).
- `CHANGELOG.md` v3.0.0 entry 추가 (Added/Changed/Deprecated/Removed/Security/Migration).
- `README.md` Status 갱신 + Recent Changes 5건 + What This Does 흐름 갱신.
- `docs/CATALOGS.md` §1 페르소나 deprecated 마킹 / §2 lens 11종 표 / §3 archetype 11종 표 / §3.1 4-tier 매트릭스 / §3.2 (예정 5종) 삭제.
- `docs/ARCHITECTURE.md` §1 한 줄 요약 갱신 / §3 Phase 3.75 lens 풀 11종 / §5.1 archetype 분기 다이어그램 11종 + 하이브리드 라우팅 / §5.2 title `(default archetype)` → `(인물극형 specialty)`.
- `GOAL.md` REQ-V3-008 (archetype 11종) + REQ-V3-009 (페르소나 → lens 이전) + FUT-LEGACY-001 추가.

### Acceptance Criteria — Step 5-C (17 main + 5 추가, 모두 [x])

1. [x] AC-1: archetype 11종 등록 (`list_archetypes()` 길이 11)
2. [x] AC-2: 신규 5종 모두 `ReportArchetype` Protocol 충족 (runtime_checkable isinstance)
3. [x] AC-3: `six_act_theater.suitable_intents` = [`who_benefits`, `what_happened`] (specialty)
4. [x] AC-4: `select_archetype()` 매트릭스 4-tier 모두 분기 검증 — 10-case 회귀 PASS
5. [x] AC-5: tech 의도 차등화 — what_next/what_to_do/why_happened 별 다른 archetype
6. [x] AC-6: fallback 시 warning 로그 (caplog 검증)
7. [x] AC-7: lens ≥ 9 (실제 11 = 분야 6 + 메타 2 + 페르소나 이전 3)
8. [x] AC-8: `recommended_lenses` 5개 이상 시 Pydantic `ValidationError` (subclass of `ValueError`)
9. [x] AC-9: 페르소나 import 시 `DeprecationWarning` 발생 (3 모듈 모두)
10. [x] AC-10: `src/agents/__init__.py` — 페르소나 + 신규 lens 양쪽 export, alias 재바인딩 없음
11. [x] AC-11: orchestrator 하이브리드 라우팅 — LLM 후보 + matrix 결과 모두 산출, mismatch 시 INFO 로그 + matrix 채택
12. [x] AC-12: `strategy.report_archetype` 가 최종 archetype_id 로 갱신 (보고서 헤더 일관성)
13. [x] AC-13: six_act_theater 보고서 출력 byte-equal 보장 (legacy 분기 무수정)
14. [x] AC-14: `src/orchestrator.py:VERSION = "v3.0.0"` 단일 SSOT
15. [x] AC-15: 모든 *.md 헤더 `last_synced_with: v3.0.0` 일관
16. [x] AC-16: 71 pytest (archetype 23 + lens 11 + quality 18 + watchlist 19) 모두 PASS
17. [x] AC-17: `python -m py_compile` 모든 src 파일 통과
18. [x] 추가 #1: DOCS_GOVERNANCE §10 grep 통과 (사실 중복 0건)
19. [x] 추가 #2: SSOT 위반 검사 — archetype/lens 카탈로그는 코드만 SSOT
20. [x] 추가 #3: 토큰 추정 — lens 4-cap 으로 사건당 ≤57K 유지 (ARCHITECTURE §3.1)
21. [x] 추가 #4: 메모리 추정 — Watchlist DB 무관 (별도 테이블, 인덱스 3개)
22. [x] 추가 #5: 분기 검토 일정 등록 — 본 항목 §10 추가 (3개월 후 2026-07-27)

### 변경된 파일

- 신규: `src/archetypes/{decision_brief, timeline_first, scenario_first, mechanism_decomp, industry_value_chain}.py` (5 파일), `src/lenses/{stakeholder, structural, cascade}_lens.py` (3 파일), `src/tests/test_archetype_selection.py`
- 수정: `src/archetypes/registry.py` (11종 등록 + select_archetype + _classify_event_type), `src/archetypes/six_act_theater.py` (suitable_intents narrow), `src/lenses/registry.py` (3종 추가), `src/orchestrator.py` (VERSION + 하이브리드 라우팅), `src/agents/__init__.py` (lens export), `src/agents/{player,dynamics,chain_reaction}_analyst.py` (DeprecationWarning), `src/tests/test_lens_pool.py` (count 갱신)
- 수정 (문서): `CLAUDE.md`, `GOAL.md`, `README.md`, `CHANGELOG.md`, `WORKFLOWS.md`, `DOCS_GOVERNANCE_V3.md`, `REFACTOR_V3_PLAN.md`, `docs/{ARCHITECTURE, CATALOGS, DATA_MODELS, REPO_MAP, STYLEGUIDE, TESTING, REPORT_STYLE_GUIDE}.md`
- 본 문서 (§9.H 신규 + §10 분기 검토 일정 등록)

### v3.0.0 메이저 릴리스 마무리

- 단일 커밋: `v3.0.0: archetype 11종 + lens 9종 + Watchlist + Quality Gate. V3 리팩토링 완료`
- **NO main merge** (사용자 승인 후 수동) — develop 브랜치에 push 만.
- **NO `git tag v3.0.0`** (사용자 승인 후 수동) — 메이저 태깅은 main merge 후.
- 분기 검토 일정 — 2026-07-27 (3개월 후) §10 등록.

---

## 9.G. v2.9.5 — Step 5-B: Watchlist Registry

2026-04-26 적용. [REFACTOR_V3_PLAN.md §5 Step 5](REFACTOR_V3_PLAN.md) 의 5-B 부분만 본 마일스톤. 5-C (페르소나 deprecation) 는 별도 세션 사용자 지시 대기.

### 사용자 승인 결정 (재확인)

- **B 보강**: 봇 재시작 복구 — `WatchlistRegistry.load_active_signals()` 호출 *불필요*. SQLite 영구 저장이라 인스턴스화만으로 active 상태 자연 복구. monitor task 만 새로 띄우면 됨. (B 보강 결정의 *실질 구현* 은 SQLite 자체의 영속성)
- **외부 데이터 폴링 제외**: deadline 자동 + 사용자 `/fire` 두 트리거만. 외부 데이터 폴링 (예: DXY 자동 검증) 은 v3.1+ FUT 트랙.

### 수행 내역

**모델**:
- `WatchSignal` Pydantic — signal_id / description / measurement / direction / deadline / follow_up_action / parent_report_url / parent_report_id / parent_chat_id / fired / fired_at
- `WatchDirection` Literal 3종 — `confirms_base` / `rejects_base` / `ambiguous`

**`src/watchlist/`**:
- `__init__.py` — 공개 API (`WatchlistRegistry`, `convert_watch_signals`, `run_monitor_loop`)
- `db_schema.sql` — `watchsignals` 테이블 + 3 인덱스 + WAL 모드. 표준 라이브러리 (`sqlite3`) 만 사용 — 의존성 추가 0.
- `registry.py` — sync API on top of sqlite3. CRUD: `register` (idempotent INSERT OR IGNORE) / `get` / `list_active` / `list_active_for_chat` / `list_fired` / `mark_fired` (선택적 direction 갱신) / `count_active` / `count_total`. 컨텍스트 매니저로 connection 관리.
- `converter.py` — ScenarioAnalysis.watch_signals (dict[]) → WatchSignal[]. direction 휴리스틱 추정 (위험·악화 → rejects_base, 지속·확정 → confirms_base, 그 외 ambiguous), deterministic signal_id (`WS-YYYYMMDD-<hash>` — 같은 보고서 + 같은 신호 텍스트 동일 ID), default deadline = today + 30일.
- `monitor.py` — `run_monitor_loop` (asyncio background task), `tick_once` (mock 가능 단위 함수), `format_telegram_alert` (spec template 정확). LLM 호출 없음 — 가벼운 시간 기반 스캔.

**Orchestrator 통합**:
- `__init__(config, watchlist_registry=None)` — None 이면 등록 스킵 (단위 테스트 안전)
- 분석 종료 직후 (보고서 URL 발급 후) `result.scenarios.watch_signals` 자동 변환 + `registry.register()` (Anti-pattern #11 회피)
- `VERSION v2.9.0 → v2.9.5`

**TelegramBot 통합**:
- `__init__` 에서 `WatchlistRegistry(reports/watchlist.db)` 인스턴스화 후 orchestrator 에 주입
- Application.builder() 에 `post_init` (monitor task 기동) + `post_shutdown` (정리) 훅
- `_notify_signal_fired(signal)` — `app.bot.send_message(chat_id=signal.parent_chat_id, ...)`
- 신규 명령: `/watchlist` (chat-scoped active list), `/fire <signal_id> [direction]` (auth 검증 + 수동 발화 + 알림)

**테스트**:
- `src/tests/test_watchlist.py` — 19 pytest 케이스 (모델 / Registry CRUD / converter / monitor auto-fire mocked clock / notify failure isolation / 봇 재시작 sim / 알림 포맷)
- 기존 28 케이스 (lens_pool 11 + quality_gates 18) 모두 통과 — 빅뱅 회피 (Anti-pattern #12). 누적 48/48 PASS.

### Acceptance Criteria — Step 5-B 부분 적용 (watchlist 관련)

- [x] WatchSignal SQLite DB 등록 검증 (Anti-pattern #11): `registry.register()` 후 `count_active()` 증가 확인 (pytest)
- [x] 봇 재시작 시 active 신호 복구: 새 `WatchlistRegistry(same_path)` 인스턴스가 이전 active 신호 그대로 보여줌 (pytest `TestBotRestartPersistence`)
- [x] monitor task deadline 도래 시 auto-fire: mocked clock 으로 검증 (pytest)
- [x] 알림 메시지 형식 spec 정확 (pytest `TestAlertFormat`)
- [x] `/watchlist` chat-scoped 필터링 검증 (pytest)
- [x] 모든 v2 / Step 5-A 회귀 통과 (49/49 pytest)
- [x] AC #14: 모든 *.md 헤더 v2.9.5 일관 + SSOT/payload-only grep 통과

### 변경된 파일

- 신규: `src/watchlist/{__init__, registry, db_schema, monitor, converter}.py` (5 파일), `src/tests/test_watchlist.py`
- 수정: `src/models.py` (WatchSignal + WatchDirection), `src/orchestrator.py` (VERSION + watchlist_registry param + 분석 종료 후 등록), `src/telegram_bot.py` (registry 생성 + monitor lifecycle hooks + `/watchlist` `/fire` 명령 + notify callback)
- 수정: `CLAUDE.md`, `GOAL.md` (REQ-V3-007), `README.md`, `CHANGELOG.md`, `docs/CATALOGS.md` (§5 Watchlist), `docs/DATA_MODELS.md` (§3.13 WatchSignal), `docs/ARCHITECTURE.md` (Phase 4.5), `docs/REPO_MAP.md`, `docs/TESTING.md` (헤더 v2.9.5)
- 본 문서 (Step 5-B 기록 append)

### 5-C 진행 시 주의 사항 (다음 마일스톤 — 사용자 승인 후)

1. **3 페르소나 (Player/Dynamics/ChainReaction) → lens 이전**: `src/lenses/{stakeholder,structural,cascade}_lens.py` 신설. 기존 페르소나 파일은 *deprecated 마킹만* 유지 (Anti-pattern #1 — 즉시 삭제 금지).
2. **Legacy import alias**: `from src.agents.player_analyst import PlayerAnalyst` 호출 경로 보존. lens 가 페르소나 *대체* 가 아니라 *추가 / 보완* 으로 운용.
3. **회귀 검증 우선순위**: six_act_theater archetype 의 byte-equal 출력은 v3.0.0 까지 유지. legacy 데이터 흐름 (`result.players`, `result.dynamics`, `result.chain_reaction`) 도 그대로.
4. **메이저 릴리스 마무리**: 모든 *.md 헤더 v3.0.0, CHANGELOG.md v3.0.0 항목, README architecture 다이어그램 갱신, 분기 검토 일정 등록, `git tag v3.0.0`.
5. **`legacy_directives` 제거 시점**: Step 5-C 메이저 릴리스에 동시 제거 가능 (lens runner 가 directive 를 직접 처리). 단 *제거는 별도 sub-PR* 권장.

---

## 9.F. v2.9.0 — Step 5-A: Lens Pool

2026-04-26 적용. [REFACTOR_V3_PLAN.md §5 Step 5](REFACTOR_V3_PLAN.md) 의 5-A 부분 (Lens Pool 구축) 만 본 마일스톤. 5-B (Watchlist) / 5-C (페르소나 deprecation) 는 별도 세션 사용자 지시 대기.

### 사용자 승인 결정 (착수 전 확정)

- **A**: "4개" = 사건당 *동시 실행 한도* (Anti-pattern #6). 페르소나 lens 화는 5-C 에서 진행.
- **B**: Watchlist 는 5-B 에서. asyncio task 봇 재시작 시 `WatchlistRegistry.load_active_signals()` 패턴.
- **C**: archetype 3종 신설 — 본 마일스톤에 포함.
- **D**: Appendix C 8 lens 모두 신설. 본격 prompt 튜닝은 v3.x.
- **E**: AC 정확도 5/6 이상, SSOT/헤더 자동 검증 추가.

### 수행 내역

**Lens Pool (5-A 핵심)**:
- `src/lenses/__init__.py`, `base.py` (`LensRunner` ABC + 공통 LLM 호출 + 출력 JSON 스키마 + Pydantic 가드 + heuristic fallback), `registry.py` (lens_id → LensRunner 인스턴스, 미등록 시 red_team 폴백)
- 8종 lens 구현: `geopolitical_lens`, `financial_transmission_lens`, `tech_architecture_lens`, `policy_implementation_lens`, `accident_causality_lens`, `market_structure_lens`, `red_team_lens`, `pre_mortem_lens`. 각각 `lens_id`/`name`/`suitable_intents`/`suitable_event_types`/`method_steps`/`failure_modes`/`system_prompt` 6개 클래스 속성 + `_abstract_marker()` 노옵 정의.
- 각 lens 의 system prompt 는 최소 (분야별 method 1줄 요약 + 음슴체 톤 + JSON 출력 가이드). 본격 튜닝은 v3.x 패치.

**신규 archetype 3종 (5-A에 포함)**:
- `geopolitical_strategic.py`: 사건 요약 → 전장·행위자 → 의도/능력 → 확전 경로 → 억제 요인 → 감시 신호
- `accident_forensic.py`: 사실 타임라인 → 직접 원인 → 방어막 실패(Swiss Cheese) → 조직적 원인(STAMP) → 재발 방지 → 미해결 질문
- `policy_implementation.py`: 정책 의도 → 이해관계자 → 제약 → 집행 가능성 → 부작용 → 수정안
- `src/archetypes/registry.py` 에 3종 등록 (총 6 archetypes).

**Orchestrator 통합**:
- `src/orchestrator.py:VERSION` `v2.8.0 → v2.9.0`
- Strategy Planner 프롬프트에 archetype 6종 + lens 8종 매트릭스 + 선택 규칙 + 4-cap 명시
- `_run_lenses(result, evidence, status_callback)` 헬퍼 — `LENS_CAP_PER_EVENT=4` 런타임 가드, 미등록 lens_id 필터링
- `result.findings = wrapped_findings + lens_findings` (Step 4 Wrap + Step 5 Lens 동시)
- 텔레그램 진행 메시지에 "🔬 Lens 풀 실행: [...] (N/4 cap)" 추가

**Pydantic 가드 강화**:
- `AnalysisStrategy.recommended_lenses` 의 기존 `max_length=4` 가 1차 가드. orchestrator `LENS_CAP_PER_EVENT=4` 가 런타임 mutation 대비 2차 가드. 둘 다 Anti-pattern #6 회피.

**테스트**:
- `src/tests/test_lens_pool.py` — 11 케이스 (registry 8 + Protocol/ABC isinstance + fallback finding + archetype 6 + 4-cap 이중 가드)
- 기존 `test_quality_gates.py` 18 케이스 모두 통과 — 빅뱅 회피 (Anti-pattern #12)

### 회귀 테스트 결과 (사진 매트릭스 6 케이스, 정적 시뮬레이션)

| # | 케이스 | 기대 archetype | 기대 lenses | 결과 | template |
|---|--------|----------------|-------------|------|----------|
| 1 | "환율 어떻게 됨" | financial_transmission | market_structure, financial_transmission | ✓ 일치 | report_block.html |
| 2 | "미중 무역 분쟁 현 상황" | six_act_theater 또는 geopolitical_strategic | geopolitical, policy_implementation | ✓ 일치 (six_act_theater 채택) | report.html (legacy) |
| 3 | "호르무즈 해협 위기 분석" | geopolitical_strategic | geopolitical, financial_transmission, market_structure | ✓ 일치 | report_block.html |
| 4 | "GPT-5 출시" | tech_decomposition | tech_architecture, market_structure | ✓ 일치 | report_block.html |
| 5 | "OO 공장 화재" | accident_forensic | accident_causality | ✓ 일치 | report_block.html |
| 6 | "한국 부동산 규제 발표" | policy_implementation | policy_implementation, financial_transmission | ✓ 일치 | report_block.html |

**6/6 일치** — AC #1 의 5/6 기준 통과. 4-cap 도 모든 케이스에서 준수 (최대 3 lens — Case 3).

### Acceptance Criteria (5-A 부분 적용 — lens 관련만)

- [x] LensRunner ABC 8종 모두 구현 (`isinstance(LensRunner)=True` 검증, pytest 통과)
- [x] `src/lenses/registry.py:get_lens()` 함수 존재 + 미등록 ID 폴백
- [x] 사건당 lens 4개 이하 (Pydantic max_length=4 + LENS_CAP_PER_EVENT=4 이중 가드, pytest 검증)
- [x] 6 케이스 archetype 자동 선택 6/6 일치 (5/6 기준 초과 달성)
- [x] 8 lens 단독 실행 통과 (fallback path 검증, pytest 11/11 통과)
- [x] archetype 6종 등록 (3종 추가) — `report_block.html` 디스패처 사용
- [x] 모든 v2 회귀 테스트 (Step 4 까지) 여전히 통과 — quality_gates 18/18

(나머지 AC: WatchSignal DB 등록은 5-B, 페르소나 deprecation isinstance 검증은 5-C 에서)

### 변경된 파일

- 신규: `src/lenses/{__init__,base,registry,geopolitical_lens,financial_transmission_lens,tech_architecture_lens,policy_implementation_lens,accident_causality_lens,market_structure_lens,red_team_lens,pre_mortem_lens}.py` (11 파일)
- 신규: `src/archetypes/{geopolitical_strategic,accident_forensic,policy_implementation}.py` (3 파일)
- 신규: `src/tests/test_lens_pool.py` (11 케이스)
- 수정: `src/archetypes/registry.py` (3종 추가 등록), `src/orchestrator.py` (VERSION + 프롬프트 확장 + `_run_lenses` + LENS_CAP)
- 수정: `CLAUDE.md`, `GOAL.md`, `README.md`, `CHANGELOG.md`, `docs/CATALOGS.md`, `docs/ARCHITECTURE.md`, `docs/REPO_MAP.md`, `docs/DATA_MODELS.md`, `docs/TESTING.md` (헤더 v2.9.0 + 본문)
- 본 문서 (Step 5-A 기록 append)

### 5-B 진행 시 주의 사항 (사용자 승인 후)

1. **Watchlist registry 저장**: `reports/watchlist.db` (SQLite). Python 표준 라이브러리만 사용 (의존성 추가 0).
2. **봇 프로세스 내 asyncio task**: 1GB VM 제약 — 별도 cron 프로세스 회피. `WatchlistRegistry.load_active_signals()` 로 부팅 시 DB → task 재구성.
3. **외부 데이터 폴링은 본 step 밖**: 신호 발화 트리거는 *deadline 도래* 와 *사용자 직접 fire 명령* 둘만. 시장 데이터 자동 폴링은 v3.1+.
4. **알림 송신**: 기존 텔레그램 봇 객체 재사용. signal 의 `parent_report_url` 에 묶인 chat_id 로.
5. **ScenarioArchitect.watch_signals → WatchSignal 자동 변환**: dict 형식 → Pydantic WatchSignal Pydantic, deadline 파싱 (없으면 +30일 default).

---

## 9.E. v2.8.0 — Step 4: Quality Gate 1/2 + Claim-Evidence + Synthesis Judge

2026-04-26 적용. [REFACTOR_V3_PLAN.md §5 Step 4](REFACTOR_V3_PLAN.md) + Anti-patterns #4/#5/#7/#10 준수.

### 수행 내역

- `src/models.py`:
  - `Claim` (evidence_ids `min_length=1` + `must_have_evidence` model_validator — Anti-pattern #4 이중 가드)
  - `Evidence` (evidence_id / source_url / quote_or_data / reliability / timestamp / supports_claims)
  - `ConfidenceProfile` (3축 + `aggregate` property — `0.4·sd + 0.3·df + 0.3·ec`, Anti-pattern #10 회피)
  - `AnalyticalFinding` (main_claim + evidence + confidence + counter_hypothesis)
  - `JudgmentVerdict` (main_judgment + contradictions[] 노출 + counter_hypothesis — Anti-pattern #5)
  - `FullAnalysisResult.findings`, `FullAnalysisResult.judgment` Optional 필드
  - 기존 `confidence_score: float` 필드들은 deprecated 마킹 (즉시 삭제 금지 — Anti-pattern #10)
- `src/agents/quality_inspector.py` — Heuristic-first + LLM-as-judge 보강:
  - `gate_1_plan_sanity(strategy)` → core_questions 길이/내용, recommended_lenses 정합성, evidence_plan 실행 가능성
  - `gate_2_coverage_check(strategy, findings, judgment)` → 모든 core_question 매칭, claim-evidence 연결 추가 검증, judgment.main_judgment & counter_hypothesis 비어있지 않음
  - LLM judge 는 30초 timeout, CLI 부재/실패 시 휴리스틱 결과 채택 (게이트 자체가 죽지 않게)
- `src/agents/synthesis_judge.py` — Findings → JudgmentVerdict (Anti-pattern #5 회피):
  - 페어와이즈 어휘 충돌 스캔 (12쌍 lexicon: 상승↔하락, 증가↔감소, 강세↔약세, ...)
  - counter_hypothesis 명시적 모순 검출
  - resolution 에 *어느 쪽 채택했는지* 명시 — 패배자 입장은 봉합되지 않고 counter_hypothesis 로 보존
  - 3축 신뢰도 합성 = finding 평균 - (모순 1건당 expert_consensus 0.1 차감)
  - LLM 으로 main_judgment / base_scenario / counter_hypothesis 산출 (실패 시 휴리스틱 폴백)
- `src/orchestrator.py`:
  - `_wrap_findings(result)` 헬퍼 — context.sources → Evidence 풀, 각 v2 분석 → AnalyticalFinding (round-robin question 매칭, ConfidenceProfile 휴리스틱 변환)
  - `_run_gate_with_retries(gate_name, gate_fn, regen_fn, ...)` — 최대 2회 재시도 + 부분-분석 알림 + 통계 카운터
  - run_analysis 흐름 wiring: Gate 1 (strategy 직후), Gate 2 (보고서 합성 직전 — wrap → judge → gate 2)
  - `_gate_stats` 카운터 + 끝부분에 통과율/재시도율 INFO 로그
  - `VERSION` `v2.7.0 → v2.8.0`
- `src/tests/test_quality_gates.py` — pytest 18 케이스 (Claim validator, ConfidenceProfile, gate 1/2, synthesis judge contradiction)
- `src/tests/__init__.py`

### Acceptance Criteria

- [x] `Claim(claim_id='C-1', statement='x', claim_type='fact', evidence_ids=[])` → ValidationError (PASS)
- [x] gate_1 / gate_2 단위 테스트 통과 (PASS, 18/18)
- [x] 인위적 모순 케이스 (호르무즈 어휘 충돌) → contradictions 1건 기록 (PASS)
- [x] 게이트 실패 시 텔레그램 알림 형식 `"⚠️ 부분 분석 완료. {gate} 실패 ({reason})"` (PASS, simulation 으로 검증)
- [x] 게이트 통과율·재시도율 로그 출력 (`[quality_inspector] gate_X stats: ...`) — 코드 경로 확인
- [x] ConfidenceProfile.aggregate 가중평균 정확 (0.4·sd + 0.3·df + 0.3·ec — PASS)

### 회귀 테스트 3건 결과 (정적 시뮬레이션)

> **테스트 한계**: VM 텔레그램 봇·CLI 호출 없이 `_wrap_findings + judge + gate_2` 직접 호출로 검증.

| # | 입력 | findings | contradictions | gate_1 | gate_2 | 노출된 모순 |
|---|------|---------:|---------------:|--------|--------|-------------|
| 1 | "미중 무역 분쟁 현 상황" | 5 | 0 | PASS | PASS | (없음) |
| 2 | "호르무즈 해협 위기 분석" | 5 | **1** | PASS | PASS | dynamics_analyst("강한 상승") vs scenario_architect("분명한 하락") — resolution: dynamics 채택 (conf 0.52 vs 0.50), 패배자는 counter_hypothesis 로 보존 |
| 3 | (force-fail: findings=[], judgment=None) | 0 | — | — | **FAIL** | reason: "judgment is None (Synthesis Judge 미실행)". 부분-분석 알림: `"⚠️ 부분 분석 완료. gate_2 실패 (judgment is None ...)"` |

### 게이트 통과율·재시도율 (시뮬레이션 통계)

3건 시뮬레이션 기준:
- `gate_1`: attempts=2, passes=2, retries=0, partial=0 → **pass_rate 100%, retry_rate 0%**
- `gate_2`: attempts=3, passes=2, retries=0, partial=1 → **pass_rate 67%, retry_rate 0%, partial_rate 33%**

partial 1건은 의도적 강제 실패 케이스 (Case 3) 이므로, 정상 케이스 기준 게이트 통과율은 100%.
실제 봇 운영 환경에서는 `[quality_inspector] gate_X stats: attempts=N passes=M retries=R partial=P (pass_rate=X% retry_rate=Y%)` 로기로 관측 가능.

### ConfidenceProfile 3축 값 분포 샘플

Case 2 (호르무즈 해협 위기) 의 JudgmentVerdict.confidence:
- `source_diversity = 0.200` (sources 1개 / 5)
- `data_freshness  = 0.700` (web search 가정)
- `expert_consensus = 0.630` (finding 평균 0.73 - 모순 1건 페널티 0.10)
- `aggregate       = 0.479` (0.4·0.20 + 0.3·0.70 + 0.3·0.63)

Case 1 (미중 무역 분쟁, 모순 0건) 의 동일 입력 대비:
- `expert_consensus = 0.730` (페널티 없음 → 모순 페널티 차이만큼 +0.10)
- `aggregate       = 0.509` (Case 2 보다 +0.030)

→ 신뢰도가 *모순 발견 시 자동 하락* 함을 확인. Anti-pattern #5 가 강조하는 "모순 노출이 신뢰도 자체에도 반영되어야 한다" 원칙 준수.

### 변경된 파일
- 신규: `src/agents/quality_inspector.py`, `src/agents/synthesis_judge.py`, `src/tests/__init__.py`, `src/tests/test_quality_gates.py`
- 수정: `src/models.py` (5개 신규 모델 + FullAnalysisResult 필드 + deprecation 주석), `src/orchestrator.py` (VERSION + 게이트 wiring + findings wrapper + 통계)
- 수정: `CLAUDE.md` (Execution Rule #9, #10), `GOAL.md` (REQ-V3-004/005), `README.md`, `CHANGELOG.md`, `docs/CATALOGS.md`, `docs/DATA_MODELS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/REPO_MAP.md` (헤더 + 본문)
- 본 문서 (Step 4 기록 append)

### Step 5 진행 시 주의 사항 (Lens Pool 통합 지점)

1. **Lens runner 가 `AnalyticalFinding` 을 직접 산출**: 현재 `orchestrator._wrap_findings()` 가 v2 분석 결과 → AnalyticalFinding 변환 어댑터. Step 5 의 LensRunner ABC 가 도입되면 이 어댑터는 *비-lens* 출처 (legacy 에이전트) 에만 사용. lens runner 는 Pydantic Claim/Evidence 를 처음부터 직접 만들어 반환.

2. **`finding.lens_id` 와 lens registry 매핑**: 현재 lens_id 는 v2 에이전트 이름 (`context_analyst` 등). Step 5 에서 `src/lenses/registry.py` 가 SSOT 가 되며 lens_id 가 registry 키와 일치해야 함. 어댑터의 lens_id 매핑도 함께 정리.

3. **Synthesis Judge 의 LLM 호출 비용**: Step 5 가 lens 4개를 병렬 실행하면 finding 수가 5 → 10+ 로 증가, judge 의 페어와이즈 스캔도 증가. timeout 60초가 짧을 수 있음 — 모니터링 필요.

4. **Quality Gate 2 의 evidence 매칭 강화**: 현재 evidence_pool 은 context.sources 공유 (모든 finding 이 같은 풀). Step 5 lens 가 *자체* evidence 를 산출하면 finding.evidence 가 다양해짐 → gate 2 의 evidence_id 매칭 검사가 더 의미있어짐. 단 Step 5 에서 *너무 엄격해지지 않게* 주의 — 한 lens 의 evidence 가 다른 lens 의 claim 에 사용될 수 있음.

5. **`Watchlist` 모델 도입**: spec §4.1 의 `WatchSignal` (Step 5 신설 예정) 은 `parent_report_id`, `parent_report_url`, `fired`, `fired_at` 등 운영 메타데이터 보유. DB 등록 (Anti-pattern #11) — 텍스트 보존만 하지 말 것. `result.scenarios.watch_signals` (현재 dict[]) 와의 매핑 어댑터가 필요할 수 있음.

6. **`legacy_directives` 제거 시점**: Step 5 가 lens runner 를 도입하면 더 이상 dict-shaped per-agent directive 가 필요 없음. 그러나 *제거는 별도 PR* 로 (Anti-pattern #12 빅뱅 회피).

7. **`confidence_score: float` 정리 시점**: deprecated 마킹만 되어 있음. v3.0.0 릴리스에서 일괄 제거 예정. Step 5 까지는 그대로 보존 + 신규 코드는 `ConfidenceProfile` 만 사용.

8. **Quality Gate 의 `regenerate_fn` 의미**: gate_1 재시도는 strategy 재생성 (LLM 다시 호출), gate_2 재시도는 judgment 재생성 (synthesis judge 다시). Step 5 lens runner 도입 시 gate_2 재시도가 "lens 재실행" 까지 포함할지 결정 필요. 현재는 judgment 만 재생성하지만 lens 결과가 부족해 gate 2 가 실패할 수 있음.

---

## 9.D. v2.7.0 — Step 3: 보고서 블록 렌더링 시스템

2026-04-26 적용. [REFACTOR_V3_PLAN.md §5 Step 3](REFACTOR_V3_PLAN.md) + [Appendix D](REFACTOR_V3_PLAN.md) 완수.

### 수행 내역

- `src/models.py`:
  - `BlockType` Literal 17종 도입 (narrative, claim_card, evidence_table, timeline, matrix, actor_cards, flow_chain, scenario_table, decomposition, argument_pair, data_series, watchlist, qna, callout, counter_hypothesis, decision_matrix, risk_matrix).
  - `AnalysisBlock` Pydantic 모델 (block_id / block_type / title / purpose / payload / related_findings / section_id).
  - `FullAnalysisResult.blocks: list[AnalysisBlock]` Optional 필드 추가.
- `src/templates/blocks/` — 17 개 단일-책임 템플릿. 평균 ~21 줄, 최대 29 줄, 모두 ≤ 50 줄 제약 준수. `block.payload` 만 참조 (Anti-pattern #8).
- `src/templates/report_block.html` — 디스패처. `result.strategy.section_plan` 을 iterate 하고 각 섹션의 `block.section_id` 매치 블록을 `{% include "blocks/<type>.html" %}` 로 렌더.
- `src/templates/report.css` — block-* 클래스 append 만 추가 (기존 클래스 무수정). 542 → 765 줄. 기존 디자인 토큰 (`--text-primary`, `--gold`, `--red` 등) 재사용.
- `src/agents/report_synthesizer.py`:
  - 17개 `_payload_*` 정적 메서드 (v2 분석 데이터 → typed payload dict).
  - `_BLOCK_BUILDERS` 레지스트리 (BlockType → builder 함수).
  - `_build_blocks(result, archetype)` — archetype.section_plan() 순회하며 AnalysisBlock 생성. six_act_theater 면 빈 리스트 반환 (legacy 경로 보존).
  - `synthesize()` 분기: legacy six_act_theater 는 기존 코드 경로 100% 유지 (byte-equal), 그 외는 빌더 호출 + 디스패처 렌더.
- `src/archetypes/{financial_transmission,tech_decomposition}.py` — `template_path()` 가 `report_block.html` 반환. Step 2 placeholder HTML 은 디스크에 보존만 (Anti-pattern #2).
- `src/orchestrator.py:VERSION` `v2.6.0 → v2.7.0`.

### 17 종 블록 카탈로그 (요약)

| Block | 빌더 데이터 출처 (v2.7.0 기준) | 상태 |
|-------|------------------------------|------|
| `narrative` | `result.context.background` + `result.dynamics.summary` | 활성 |
| `claim_card` | placeholder | Step 4 활성 예정 |
| `evidence_table` | placeholder | Step 4 |
| `timeline` | `result.context.timeline` | 활성 |
| `matrix` | placeholder | Step 5 lens-driven |
| `actor_cards` | `result.players.players` | 활성 |
| `flow_chain` | `result.chain_reaction.chain` | 활성 |
| `scenario_table` | `result.scenarios.scenarios` | 활성 |
| `decomposition` | `result.dynamics.framework` + `asymmetries` | 활성 |
| `argument_pair` | `result.dynamics.key_insight` vs `counter_view` | 활성 |
| `data_series` | `result.visuals.chart_config.charts` | 활성 |
| `watchlist` | `result.scenarios.watch_signals` | 활성 |
| `qna` | placeholder | 후속 |
| `callout` | `result.dynamics.key_insight` 또는 `result.chain_reaction.worst_case` | 활성 |
| `counter_hypothesis` | `result.dynamics.counter_view` + `cognitive_biases` | 활성 |
| `decision_matrix` | placeholder | Step 4+ decision_brief archetype |
| `risk_matrix` | `result.chain_reaction.wildcards` | 활성 |

상세 payload 스키마는 [docs/CATALOGS.md §4](docs/CATALOGS.md).

### 회귀 테스트 3건 결과 (정적 시뮬레이션)

> **테스트 한계**: 본 세션에 텔레그램 봇·Cloudflare 인프라 없음. _build_blocks() 호출 + 디스패처 직접 렌더로 검증.

| # | 입력 | 기대 archetype | 결과 |
|---|------|----------------|------|
| 1 | "미중 무역 분쟁 현 상황" | `six_act_theater` | template=`report.html` (legacy), 0 blocks built. byte-equal 검증 sha256 `d22a78077300b6b4...` 일치. |
| 2 | "환율 어떻게 됨" | `financial_transmission` | template=`report_block.html`, 6 sections / 11 blocks built. 9 types used: callout, counter_hypothesis, data_series, decomposition, flow_chain, narrative, risk_matrix, scenario_table, watchlist. 디스패처 렌더 42,626 bytes / 307 block-* CSS 클래스. |
| 3 | "GPT-5 출시" | `tech_decomposition` | template=`report_block.html`, 6 sections / 10 blocks built. 9 types used (decomposition + risk_matrix 포함 ✓). 디스패처 렌더 41,695 bytes / 294 block-* CSS 클래스. |

### Acceptance Criteria

- [x] archetype="six_act_theater" 보고서 byte 단위 동일 — sha256 검증 통과
- [x] archetype="financial_transmission" 보고서가 report_block.html 로 렌더 — 분기 진입 + 11 blocks 생성 확인
- [x] archetype="tech_decomposition" 동일 — 10 blocks 생성, decomposition + risk_matrix 포함
- [x] 17 종 블록 단독 렌더링 통과 — ok=17/17
- [x] 모든 블록 템플릿 50 줄 이내 — 최대 29 줄 (scenario_table)
- [x] `grep "result\.(context|players|...)" src/templates/blocks/*.html` 결과 0 건 — payload-only access 준수

### 변경된 파일

- 신규: `src/templates/blocks/{17 types}.html`, `src/templates/report_block.html`
- 수정: `src/models.py` (BlockType, AnalysisBlock, FullAnalysisResult.blocks), `src/orchestrator.py` (VERSION), `src/agents/report_synthesizer.py` (블록 빌더 + 분기), `src/archetypes/{financial_transmission,tech_decomposition}.py` (template_path), `src/templates/report.css` (block-* append)
- 수정: `CLAUDE.md`, `GOAL.md`, `README.md`, `CHANGELOG.md`, `docs/CATALOGS.md`, `docs/DATA_MODELS.md`, `docs/ARCHITECTURE.md` (헤더 + 본문)
- 본 문서 (Step 3 기록 append)

### Step 4 진행 시 주의 사항

1. **Claim/Evidence 도입 영향**: 현재 `claim_card`, `evidence_table` 빌더는 placeholder (빈 payload 반환). Step 4 가 `Claim` / `Evidence` 모델을 추가하면 두 빌더를 *수정*하면 되며, 템플릿은 이미 payload 스키마 (`statement`, `evidence_ids`, `evidences[]` 등) 가 정의돼 있어 그대로 쓸 수 있음.

2. **Pydantic validator 우회 금지** (Anti-pattern #4): Step 4 가 `Claim.must_have_evidence` validator 를 도입하면, 빌더가 빈 evidence 로 Claim 을 생성할 수 없게 됨. 기존 `_payload_claim_card` placeholder 는 **반드시 함께 갱신**하여 ValidationError 방지. (현재 placeholder 는 dict 만 반환하므로 영향 없음 — 구조화된 Claim 객체로 전환 시 주의.)

3. **`legacy_directives` 잔존**: Step 5 까지 유지. Step 4 에서 *읽기*만 가능, *쓰기* 금지.

4. **section_plan 사이드 이펙트**: `_build_blocks()` 가 `result.strategy.section_plan = plan` 으로 strategy 를 변형함. Step 4 에서 strategy 를 다른 곳에서 재참조하는 경우 이 사이드 이펙트를 인지할 것.

5. **Step 2 placeholder HTML**: `src/templates/archetypes/{financial_transmission,tech_decomposition}.html` 은 *고아* 상태 (사용처 없음). Step 4+ 에서 정리 가능하지만 빅뱅 회피 (Anti-pattern #12) — 한 커밋에 여러 정리 작업 묶지 말 것.

6. **Confidence/3축 분해**: Step 4 에서 `ConfidenceProfile` 도입 시, 현재 `confidence_score: float` (스칼라) 사용 중인 모든 모델은 deprecated 마킹만 하고 즉시 삭제 금지 (Anti-pattern #10).

7. **Synthesis Judge**: Step 4 spec 에 `JudgmentVerdict` 가 있을 가능성 높음. 도입 시 `result.judgment` Optional 필드 추가 + 신규 archetype section 에서 활용. `argument_pair`, `counter_hypothesis` 블록의 빌더가 judgment 데이터를 참조하도록 확장 가능 (현재는 dynamics 에서만 가져옴).

---

## 9.C. v2.6.0 — Step 2: 보고서 아키타입 다중화

2026-04-26 적용. [REFACTOR_V3_PLAN.md §5 Step 2](REFACTOR_V3_PLAN.md) + [Appendix B](REFACTOR_V3_PLAN.md) 완수.

### 수행 내역
- `src/archetypes/` 디렉토리 신설:
  - `base.py`: `ReportArchetype` Protocol 정의 (`@runtime_checkable` 으로 `isinstance()` 검증 가능)
  - `six_act_theater.py`: 기존 `report.html` 보존 (Anti-pattern #2). `template_path()` → `"report.html"`
  - `financial_transmission.py`: Appendix B 매트릭스 그대로 (가격 반응 → 포지션·자금흐름 → 전이 경로 → 취약 고리 → 스트레스 시나리오 → 관찰 지표)
  - `tech_decomposition.py`: Appendix B 매트릭스 그대로 (문제 정의 → 시스템 구조 → 병목 → 성능·비용·리스크 → 대안 비교 → 실행 권고)
  - `registry.py`: `_REGISTRY` dict + `get_archetype(id)` (Anti-pattern #1: if/elif 하드코딩 금지 — registry 패턴 사용). 미등록 ID 는 `six_act_theater` 로 폴백 + warning 로그.
- `src/templates/archetypes/{financial_transmission,tech_decomposition}.html` placeholder (Step 3 에서 본격 블록 렌더링).
- `src/orchestrator.py`:
  - `_generate_analysis_strategy()` 프롬프트에 archetype 자동 선택 매트릭스 추가 (`user_intent` + `event_type` → `archetype_id`)
  - LLM 출력의 `report_archetype` 을 `list_archetypes()` 으로 검증, 미등록값은 폴백
  - `synthesize()` 호출 시 `get_archetype()` 으로 객체 해소 후 전달
  - `VERSION` `v2.5.0 → v2.6.0`
- `src/agents/report_synthesizer.py:synthesize()`:
  - `archetype: ReportArchetype | None = None` 인자 추가 (None 시 default = `six_act_theater` → 기존 흐름과 byte 동일)
  - `archetype.archetype_id == "six_act_theater"` 분기는 *기존 코드 경로 그대로* (render vars 변경 0건)
  - 신규 archetype 분기는 `archetype.template_path()` 와 `archetype.section_plan(strategy)` 만 사용한 placeholder render

### 회귀 테스트 3건 결과

> **테스트 한계**: 본 세션에 텔레그램 봇·Cloudflare 인프라가 없어 실제 봇 송신은 수행 불가. 대신 *Strategy Planner 의 archetype 선택 결정 트리*와 *분기 진입 경로*를 정적으로 검증.

| # | 케이스 입력 | 기대 archetype | 검증 방식 | 결과 |
|---|-------------|----------------|----------|------|
| 1 | `"미중 무역 분쟁 현 상황"` | `six_act_theater` | event_type=`diplomacy/political_conflict` 매트릭스 → default 폴백, byte-equal 보장 (Path: `report.html` 그대로) | ✅ |
| 2 | `"환율 어떻게 됨"` | `financial_transmission` | event_type=`currency` ∈ financial_transmission.suitable_event_types, intent=`where_spreads` ∈ suitable_intents → 신규 분기 진입 (Path: `archetypes/financial_transmission.html`, 18763 bytes, "Archetype Preview" 배너 + 6 sections 포함 확인) | ✅ |
| 3 | `"GPT-5 출시"` | `tech_decomposition` | event_type=`model_release` ∈ tech_decomposition.suitable_event_types → 신규 분기 진입 (Path: `archetypes/tech_decomposition.html`, 18715 bytes, 6 sections 포함 확인) | ✅ |

byte-equal 검증 명령:
```python
# six_act_theater path: legacy render vs registry-routed render
sha256 일치: ddf77c20fbba88e5b0a571a7fb290e4dc3dcb5c6730cd3cf4c6edc8af6adbc90
length: 18112 == 18112
```

### 변경된 파일
- 신규: `src/archetypes/__init__.py`, `base.py`, `registry.py`, `six_act_theater.py`, `financial_transmission.py`, `tech_decomposition.py`
- 신규: `src/templates/archetypes/financial_transmission.html`, `tech_decomposition.html`
- 수정: `src/orchestrator.py` (프롬프트, archetype 검증, synthesize 호출, VERSION)
- 수정: `src/agents/report_synthesizer.py` (`synthesize()` 시그니처 + 분기)
- 수정: `CLAUDE.md`, `GOAL.md`, `README.md`, `CHANGELOG.md`, `docs/CATALOGS.md`, `docs/ARCHITECTURE.md`, `docs/REPO_MAP.md` (헤더 + 본문)
- 본 문서 (Step 2 기록 append)

### Step 3 진행 시 주의 사항
- 신규 archetype 의 placeholder 템플릿은 의도된 *임시* 렌더. Step 3 가 도입되면 placeholder 를 *완전 교체* 하지 말고, archetype 별로 `report_block.html` 디스패처를 통한 블록 렌더링 흐름으로 전환.
- `archetype.section_plan(strategy)` 가 반환하는 `ReportSectionPlan.block_types` 는 현재 placeholder 문자열. Step 3 에서 `BlockType` Literal 이 정의되면 본 문자열들이 `BlockType` 값과 일치해야 함 (`narrative`, `actor_cards`, `flow_chain`, `scenario_table`, `decomposition`, `data_series`, `risk_matrix`, `decision_matrix`, `argument_pair`, `watchlist`, `counter_hypothesis`, `callout`, `matrix`, `timeline`).
- `archetype.template_path()` 는 Step 3 에서 단일 `report_block.html` 디스패처로 통일될 가능성 있음 (archetype 별 별도 HTML 파일 → archetype 별 *섹션 플랜* 만 차이). 본 결정은 Step 3 spec 에서 확정.
- `legacy_directives` (Step 1 transitional shim) 는 Step 5 까지 유지. Step 3 에서 *읽기*만 가능 (per-agent directive 는 여전히 v2 흐름으로 전달).

---

## 9.B. v2.5.0 — Step 1: AnalysisStrategy Pydantic 모델 승격

2026-04-26 적용. [REFACTOR_V3_PLAN.md §5 Step 1](REFACTOR_V3_PLAN.md) 완수.

수행 내역:
- `src/models.py`: `UserIntent` (Literal 7종), `EvidenceNeed`, `ReportSectionPlan`, `VisualizationSpec`, `AnalysisStrategy` 신규 추가 + 기존 모델 보존 (4.2 §4.2 무파괴 원칙).
- `AnalysisStrategy` 는 `model_validator` 로 lens-question 정합성 검증, `core_questions` `min_length=1` 보장.
- `AnalysisStrategy.skip_agents` 는 alias `"skip"` 으로 v2 dict 키 호환.
- Step 1 한정 transitional shim: `legacy_directives: dict[str, str]` 필드 — v2 의 per-agent directive 문자열 보존. Step 5 lens pool 도입 시 제거 예정.
- `src/orchestrator.py:_generate_analysis_strategy()` 가 dict 대신 `AnalysisStrategy` 반환. 실패 시 `_empty_strategy_fallback()` 사용 (Anti-pattern #3 dict 회귀 방지).
- 프롬프트 확장: `event_type`, `user_intent` (7종 분기 설명 포함), `intent_confidence`, `core_questions`, `recommended_lenses` 신설.
- 호출 측 (run_analysis) 은 객체 속성 (`strategy.skip_agents`, `strategy.theme`) 으로 전환. directive 추출은 `strategy.legacy_directives.get("agent_name", "")` 통해서만 수행.
- `FullAnalysisResult` 에 `strategy: AnalysisStrategy | None = None` Optional 필드 추가. orchestrator 가 매 분석 결과에 전략을 보존.
- `VERSION` 상수 `v2.4.0 → v2.5.0` 갱신.

### user_intent 분류 샘플 (v2.5.0 Step 1 검증용)

다음은 Strategy Planner 의 분류 결과 예시 — 동일 사건이라도 사용자 질문 의도에 따라 분기 가능함을 확인.

| 사건 입력 | 분류된 user_intent | intent_confidence | core_questions (요지) | recommended_lenses |
|-----------|-------------------|-------------------|------------------------|---------------------|
| "미중 무역 분쟁 현 상황" | `what_happened` | 0.85 | 현재 관세 수준은? 합의/결렬 상태는? | ["context", "transmission_channel"] |
| "미중 무역 분쟁의 원인" | `why_happened` | 0.90 | 갈등의 근본 원인은? 구조적 요인은? | ["systems_dynamics", "political_economy"] |
| "미중 무역 분쟁이 한국에 미칠 영향" | `where_spreads` | 0.92 | 1차 전이 경로는? 2차 효과는? | ["transmission_channel", "input_output"] |
| "미중 무역 분쟁에 한국이 어떻게 대응?" | `what_to_do` | 0.88 | 가능한 대응 옵션은? 트레이드오프는? | ["decision_matrix", "pre_mortem"] |

핵심 인사이트 (REFACTOR_V3_PLAN.md §1.3): **사건 유형뿐 아니라 사용자의 질문 유형에 따라 분석 기법과 보고서 구조가 달라져야 한다.** Step 1 은 그 분기를 가능케 하는 기반 자료구조를 도입한 것. Step 2 부터 archetype 다중화로 실제 분기를 적용한다.

### 변경된 파일
- `src/models.py` (신규 모델 5종 + `FullAnalysisResult.strategy` 필드)
- `src/orchestrator.py` (`_generate_analysis_strategy()` 시그니처·반환 타입·프롬프트, 호출 측 객체 속성 전환, VERSION 증가)
- `CLAUDE.md` (Execution Rule #8 추가, last_synced_with 갱신)
- `GOAL.md` (REQ-V3-001 추가, last_synced_with 갱신)
- `docs/DATA_MODELS.md` (AnalysisStrategy 도식 + §3.0 의미 가이드 추가, last_synced_with 갱신)
- `CHANGELOG.md` (v2.5.0 항목 작성)
- 본 문서 (Step 1 기록 append)

### Step 2 진행 시 주의 사항
- `report_archetype` 은 현재 단일값 (`six_act_theater`). Step 2 에서 archetype 다중화 시 `archetype="six_act_theater"` 가 default 이며 다른 archetype 추가 시 `docs/CATALOGS.md §3` 갱신 필수 (Anti-pattern #14).
- `recommended_lenses` 의 lens ID 는 현재 placeholder 문자열 (예: `"context"`, `"transmission_channel"`). Step 5 에서 `src/lenses/registry.py` 가 SSOT 가 되며 본 필드의 ID 는 registry 키와 일치해야 함.
- `legacy_directives` 는 Step 5 직전까지 유지. Step 2~4 에서는 *읽기*는 하되 *쓰기*는 하지 않는다 (lens-driven directive 가 점진 도입됨).

---

## 9.A. v2.4.1 — 문서 거버넌스 V3 적용 (Step 0)

2026-04-26 적용. [DOCS_GOVERNANCE_V3.md](DOCS_GOVERNANCE_V3.md) Step 0 완수.

수행 내역:
- 디렉토리 정리: `docs_canonical/` → `docs/`, `prototype_*.html` → `docs/references/`, `overall_structure.md` 흡수 후 삭제, `src/style_guide/REPORT_STYLE_GUIDE.md` → `docs/REPORT_STYLE_GUIDE.md` 이전
- 모든 마크다운에 거버넌스 YAML 헤더 추가 (tier, last_synced_with, ssot_for, depends_on, last_review)
- 신규 문서 3종: `CHANGELOG.md`, `docs/CATALOGS.md`, `docs/DATA_MODELS.md`
- README 60줄 이내로 슬림화 (현행 48줄). 7개 에이전트 표·토큰 추정·6막 디자인 설명 → 각 SSOT 로 이전
- CLAUDE.md 에 Change Propagation 매트릭스 추가, 7개 에이전트 표를 CATALOGS 링크로 대체
- WORKFLOWS.md 의 stale `docs_canonical/` 경로 갱신
- SSOT 위반 grep 검사 통과 (실질 위반 0건, 단순 언급은 SSOT 위반 아님)

V3 리팩토링 본 트랙 (Step 1~5) 은 별도 진행 — 본 작업은 Step 0 만 완료 후 멈춤.

---

## 9.I. 분기 검토 일정 (Quarterly Review Schedule)

V3 리팩토링 완료 (v3.0.0, 2026-04-27) 직후 등록. 메이저 릴리스 후 코드/문서/SSOT 일관성을 정기적으로 점검.

| 검토 일자 (예정) | 점검 항목 | 출력물 |
|------------------|-----------|--------|
| 2026-07-27 (3개월) | (1) `src/agents/{player,dynamics,chain_reaction}_analyst.py` 사용 빈도 — DeprecationWarning 로그 수집 후 v4.0.0 제거 가능성 평가. (2) archetype 매트릭스 라우팅 적중률 (LLM 후보 vs matrix 결과 mismatch 비율) 측정. (3) lens 4-cap 충분성 검증. (4) 모든 *.md `last_synced_with` ↔ 코드 VERSION 일치 grep. | DEVLOG §9.I 후속 항목 + (필요 시) FUT-LEGACY-001 priority 조정 |
| 2026-10-27 (6개월) | (1) Watchlist auto-fire 통계 (deadline / `/fire` 비율). (2) Quality Gate 통과율·재시도율. (3) Synthesis Judge 모순 검출 빈도. (4) 토큰 사용량 vs ARCHITECTURE §3.1 추정치 일치 여부. | DEVLOG §9.J + (필요 시) GOAL.md FUT-* 추가 |
| 2027-01-27 (9개월) | v4.0.0 사전 점검 — legacy alias 제거 영향 분석 (`grep -r "from src.agents.player_analyst"` 등 외부 호출 0건 확인). | v4.0.0 RFC 초안 |

검토 시 발견된 사실은 본 §9.I 가 아니라 신규 §9.J / §9.K… append-only 항목으로 기록 (Anti-pattern: DEVLOG 과거 항목 수정 금지).

---

## 10. 트러블슈팅 & Lessons Learned

### Oracle Cloud

- VM 생성 시 "Create new virtual cloud network" 선택해야 Public IP 할당 가능
- Public IP는 생성 후 IP administration에서 수동 할당 (Ephemeral)
- SSH 키 권한 오류: Windows에서 `icacls key.key /inheritance:r /grant:r "%USERNAME%:R"`
- 비밀번호 로그인이 안 될 때: `/etc/ssh/sshd_config.d/60-cloudimg-settings.conf`가 `sshd_config`를 override함

### Cloudflare

- Direct Upload API는 manifest 필요 → wrangler CLI 사용이 안정적
- wrangler 배포 URL은 `{hash}.{project}.pages.dev` 형태, 파일명을 직접 붙여야 함
- 프로젝트 생성 시 단일 파일 업로드 불가 → 폴더로 감싸서 업로드

### Claude Code CLI

- `-s` 옵션 없음 → 시스템 프롬프트를 사용자 메시지에 prepend
- `--dangerously-skip-permissions` 필요 (비대화형 실행)
- `--allowedTools "WebFetch,WebSearch"` 로 웹 검색 활성화
- 로그인: 서버에서 `claude login` → URL 복사 → PC 브라우저에서 인증

### Python / Pydantic

- pydantic-settings가 빈 문자열을 JSON으로 파싱 시도 → `list[int]` 필드는 `str`로 받아서 property로 변환
- `.format()`에 JSON 예시가 포함된 문자열 → `{}`가 충돌 → `.replace()` 사용

### 1GB 서버 한계

- 4개 에이전트 병렬 실행 시 메모리 부족으로 멈춤 → 순차 실행으로 변경
- 나중에 Mac Mini 등으로 이전 시 병렬 실행 복원 가능

### 텔레그램

- 메시지 수정(edit_text) 방식 → 새 메시지 추가(reply_text) 방식으로 변경 (사용자 선호)
- 4096자 제한 → 긴 보고서는 분할 전송
- HTML 파일 캡션에 공유 링크 포함

### 보고서

- Plotly.js → Canvas 2D + SVG 직접 생성으로 변경 (6막 극장 구조)
- Mermaid.js → SVG 직접 생성으로 변경 (품질 향상)
- `**` 마크다운 볼드 → 에이전트 출력에서 자동 strip
- 섹션 명칭은 사용자 피드백으로 여러 번 변경됨 (상황판 → 상황인식 등)
- 용어 정의(glossary)는 텔레그램 텍스트 보고서 말미 + HTML 각 섹션 말미

---

## 11. 아이폰/아이패드 접속 (Termius)

- Termius 앱 설치 (App Store)
- SSH 키 방식은 키 파일 전송 시 깨질 수 있음 → 비밀번호 방식 추천
- 호스트 설정: IP, username(ubuntu), password
- 기존 호스트가 접속 안 되면 삭제 후 새로 만들기

---

## 12. 향후 개선 사항

- Mac Mini 로컬 서버 이전 시 병렬 실행 복원
- 분석 중 사용자 추가 요청 반영 (중간 피드백)
- 분석 대기열 (여러 분석 동시 요청)
- Figma MCP를 활용한 더 고급 시각화
- 보고서 에필로그 (예측 검증 스코어카드)

---

## 13. v4.x — Tier 4 단순화 (2026-05-02)

### 13.1 배경 — v3.5.0 까지의 누적 문제
스크린샷 분석 결과 v3.4.7 까지 보고서에서 두 가지 증상이 살아있었다:

1. **차트 무지성 박힘** — `visual_builder.build_chart_payload()` (v3.2.0 추가) 가 분석 결과 데이터에서 9종 차트를 자동 추출하고, `report_block.html` 의 "DATA DASHBOARD" 섹션이 데이터만 있으면 무조건 9개 슬롯을 렌더. Insight Gate (v3.4.4) 는 donut/stacked 만 가벼운 검사. 사건과 무관한 차트가 양산됨.
2. **보고서 틀 고정** — `archetypes/registry.py:select_archetype()` 매트릭스가 LLM 의 `report_archetype` 결정을 *덮어씀* (v3.0.0 의 "정밀 우선순위"). 11개 archetype 의 `section_plan()` 은 Python 코드로 고정된 6 섹션. 사건마다 보고서가 같은 틀로 떨어짐.

진단 결과 두 문제는 다른 파일에 있지만 *공통 원인*: 다중 에이전트 체계가 자유도를 막고 있었다. v3.0.0~v3.4.7 의 7-agent + 11-lens + 11-archetype + 5-게이트 파이프라인은 분석 깊이는 보장하지만 보고서 형태/내용 선택의 자유는 코드가 빼앗고 있던 구조.

### 13.2 v4.0.0 — Tier 4 (2026-05-02)
멀티 에이전트 파이프라인을 폐기하고 **ContextAnalyst + UnifiedComposer 2-call** 로 압축.

**호출 안 되게 된 모듈** (코드 보존):
- `src/agents/{player,dynamics,chain_reaction,scenario,visual,quality_inspector,synthesis_judge}_*.py` (7개)
- `src/lenses/` 11종
- `src/archetypes/` 의 `freeform_essay` 외 11종
- `src/visual_builder.py:build_chart_payload / build_map_payload`
- `src/templates/{report.html, report_block.html}` (legacy archetype 용)

**남은 호출 경로**:
1. `ContextAnalyst.analyze()` — 사실/타임라인/출처 (Sonnet 4.6)
2. `NarrativeComposer.compose_unified()` — 행위자/구조/시나리오/모순 분석 + 본문 작성 + watch_signals + contradictions + confidence (Opus 4.7 단일 호출)
3. `ReportSynthesizer.synthesize()` — `freeform_essay.html` 로 mono 테마 HTML 렌더 (LLM 0)
4. Watchlist Registry — `composed_report.watch_signals` SQLite INSERT

**LLM 호출 수**: deep 13 → 2 (~85% 감소). 모든 모드 동일하게 2회.
**지연**: ~90~180초 → ~30~60초 추정 (~60% 감소).
**비용**: 운영 비용 ~70% 추정 절감 (단일 Opus 4.7 호출 vs 13개 호출).

**ComposedReport 확장**:
- `watch_signals: list[dict]` — Watchlist 통합 (이전 ScenarioArchitect 출력 대체)
- `contradictions: list[dict]` — Anti-pattern #5 (모순 봉합 금지) 보존
- `confidence_summary: str` + `confidence_score: float` — composer 자체 평가

**잃은 것** (사용자에게 사전 안내됨):
- 다중 관점 분리 분석 (각 lens 별 독립 finding)
- Evidence-Claim 추적성 강제 (Claim.evidence_ids min_length=1 validator)
- Quality Gate 1/2 + AMC required_inputs 검증
- SynthesisJudge 의 별도 모순 검사 (LLM cross-check)
- red_team / pre_mortem 메타 lens 자동 추가

### 13.3 v4.1.0 — ContextAnalyst → Opus 4.7
v4.0.0 의 2-call 파이프라인에서 context 가 composer 가 보는 *유일한* 사실 입력 → 사실 추출 품질이 보고서 전체 품질의 상한. ContextAnalyst 를 Sonnet 4.6 → Opus 4.7 로 통일 (composer 와 같은 모델). fast 모드 다운그레이드 로직도 제거.

비용 ~1.6~1.8× (vs v4.0.0). 지연 ~30초 추가. 절대값으로는 v3.5.0 deep 의 30~40% 수준.

### 13.4 v4.2.0 — Composer-emitted 차트/지도
v4.1.0 까지 차트/지도가 *전혀* 안 박혔던 문제 해결. composer 가 chart-id 를 referencing 해도 freeform_essay.html 의 chart_payload 가 비어있어 매칭이 항상 false.

해결: composer 가 차트/지도 데이터를 직접 emit.
- `ComposedSection.charts: list[dict]` — `{type, title, data, note?}`. 8종 type.
- `ComposedReport.embedded_map: dict | None` — 보고서 레벨 단일 지도.
- `charts.js` 전면 재작성 — 전역 chart-payload 객체 패턴 폐기, 섹션별 inline JSON payload + mono guide §4 패턴 자동 적용.
- `maps.js` 전면 재작성 — maplibre-gl 의존 폐기, d3 + d3-geo + world-atlas/110m TopoJSON.

### 13.5 v4.x 아키텍처 시각화
- `samples/v3_5_0_architecture.html` — v3.5.0 아카이브 (히스토리)
- `samples/v4_0_0_architecture.html` — v4.0.0 Tier 4 (burgundy_mono)
- `samples/v4_2_0_architecture.html` — v4.2.0 (light_mono, 본 절에서 추가)

라이브 URL: `https://doroper98.github.io/agents_reviewer/samples/<file>.html` (GitHub Pages 자동 배포)

### 13.6 트러블슈팅
- VM 봇 재기동 시 옛 인스턴스 죽이기 — `pkill -9 -f 'python -m src.main'` 한 줄로 통일 (literal `<PID>` 입력 실수 회피)
- `kill -9 <PID>` 는 bash 가 `<` 를 redirection 으로 해석해 syntax error → 사용자 가이드에서 제거
- VM 의 venv 활성 (`source venv/bin/activate`) 안 하고 `python -m src.main` 시 `python` 미발견 — venv activation 절차 필수
- v4.0.0 첫 기동 시 옛 v3.5.0 인스턴스와 동시 실행 → 텔레그램 `409 Conflict: terminated by other getUpdates request` — `pkill` 로 한 번에 종료
- `/status` 의 에이전트 리스트가 옛 8명 그대로 → `telegram_bot.py:_status` 핸들러 갱신 (v4.1.0)

### 13.7 회귀 우려 + 운용 메모
- composer 가 가끔 JSON 출력 깨질 수 있음 → `_parse_response` 가 None 반환 → orchestrator 가 minimal fallback (context.summary 1섹션) 생성. 사용자에겐 보고서가 *비어있어 보일 수 있음*.
- composer 비용 (Opus 4.7) 이 사용자 결정으로 OK 받음. 모니터링은 telemetry 의 `record_llm_call` (input/output chars + elapsed_ms) 으로 해결.
- 차트/지도 ANTHROPIC_API_KEY 경고는 CLI 모드면 무시 가능 (config.use_cli_mode=True 일 때).

### 13.8 v4.4.0~v4.4.3 — Tier 1+2 차트 강화 + 회귀 누적 + 체계화 (2026-05-02 후속)

[v4.4.0] Tier 1 (메타데이터 5필드: subtitle / annotations / source / takeaway / reference_line) +
Tier 2 (신규 type 3종: dual_line / forecast / choropleth) + zone-based layout 엔진
(top/right/bottom margin 분리 + OccupancyTracker bbox 충돌 검사 + 5종 fallback).

[v4.4.1] patch_report.py 신설 — LLM 호출 0 으로 보고서 부분 수정·재렌더·재배포.
ReportSynthesizer 가 HTML 옆에 ComposedReport JSON 자동 저장.

[v4.4.2 — 사용자 검증으로 발견한 시스템 회귀 2건]
소말릴란드 승인 보고서 검증 결과:
- network 차트가 node.group 시각 무시 — 진영 (승인/반대/검토/비공식) 모두 동일 fill (CHART-AP-1)
- stacked 차트 segment legend 없음 — 어느 막대가 어느 카테고리인지 모름 (CHART-AP-2)
- gantt timeline 라벨 너무 길어 zone 밖 겹침 → 차트 의미 0 (CHART-AP-8, 데이터 수정으로 해결)
- 지도 zoom/center 디폴트 (3.0) → 호른 아프리카 안 보임 (CHART-AP-9, 데이터 수정)

전자 2건 (CHART-AP-1, 2) 은 charts.js 코드 수정 → 모든 보고서 자동 fix.
후자 2건 (CHART-AP-8, 9) 은 patch_report.py 로 보고서 한정 fix.

[v4.4.3 — 체계화] 사용자 요청: "같은 방식의 실수가 반복되지 않는 체계에 적용"
- docs/CHART_RENDERING_ANTIPATTERNS.md 신설 (Tier 2 SSOT) — 9개 패턴 + 검증 체크리스트.
  매 charts.js / composer prompt 변경 시 점검. 새 회귀 발견 시 append-only.
- CLAUDE.md 의 Anti-Patterns 섹션에 차트 9 패턴 요약 + 새 문서 링크 추가.
- 본 §13.8 항목으로 회귀 발견·수정 흐름 기록 (DEVLOG append-only 규칙).

[적용 방법 — 운영자]
charts.js 변경은 정적 자산이라 봇 재기동 불필요. `cp src/templates/static/charts.* reports/`
+ `wrangler pages deploy reports` 만 실행하면 모든 보고서 (기존 포함) 즉시 fix.

---

## v5.1.0 — Daily Briefing Scheduler (2026-05-13)

### 사용자 요청
"간밤(00~07시) 산업/지정학/정치/전쟁 이슈에 대해 매일 자동으로 보고서를 deep 모드로
생성하고 아침 07:30 에 자동으로 배포 + 텔레그램 송신."

### 설계 결정

| 항목 | 선택 | 사유 |
|------|------|------|
| 스케줄링 | in-process asyncio task | 별도 cron / systemd timer 불요. watchlist monitor 패턴과 일관성. |
| 구독 모델 | `/briefing_on` 명령 | env var (`DAILY_BRIEFING_CHAT_ID`) 보다 사용자 친화적 — "지금 챗하고 있는 봇이 그 채팅 알 거 아냐" 라는 사용자 멘탈모델에 부합. SQLite 영속화. |
| Deep 모드 | 기존 v4.0.0 `mode='deep'` 재사용 | v4 부터 mode 가 이미 token_budget 에 정의됨 (`fast/standard/deep`). composer 프롬프트가 deep 시 5~7 섹션 + 모순 명시. 추가 구현 0. |
| 분석 범위 | 단일 통합 보고서 | 산업/지정학/정치/전쟁 4개 분야를 1개 deep 보고서로 통합. composer 가 자유 형식 (`freeform_essay`) 으로 3~5건 사건 다룸. |
| 시간대 | KST (Asia/Seoul) 기본 | `DAILY_BRIEFING_TZ` 로 IANA tz 변경 가능 (`zoneinfo`, Python 3.9+). |
| 같은 날 중복 트리거 방지 | `briefing_runs.run_date` PK | 봇 재시작 + 트리거 시각 통과 케이스에서 atomic guard (`INSERT OR IGNORE`). |
| Config 패턴 | `Field` + `AliasChoices` | 기존 V5 opt-in flags (`enable_*`) 와 일관 — 동일 변수에 `DAILY_BRIEFING_ENABLED` (대문자 env) + `daily_briefing_enabled` (소문자) 양쪽 alias. |

### 구현 핵심

- **신규 모듈** `src/scheduler/`:
  - `subscriptions.py` — `BriefingSubscriberRegistry` (SQLite, WAL 모드, sync sqlite3, contextmanager). Watchlist registry 와 동일 패턴.
  - `daily_briefing.py` — `run_daily_briefing_loop()` background task + 순수 함수 `_next_trigger()` / `_build_briefing_prompt()` (테스트 가능 분리).
  - `db_schema.sql` — `briefing_subscribers` (chat_id PK, mode AnalysisMode CHECK) + `briefing_runs` (run_date PK).

- **Orchestrator**: 변경 없음. 기존 `run_analysis(event_description, chat_id, status_callback, mode)` 시그니처를 그대로 사용. 일일 브리핑은 `mode='deep'` 전달.

- **TelegramBot 수정**: `_on_app_post_init` 에 `asyncio.create_task(run_daily_briefing_loop)` 추가 (watchlist monitor task 옆). `_on_app_post_shutdown` 에 두 task 모두 정리하는 루프. `_send_text_to_chat` / `_send_document_to_chat` 헬퍼 추가 — scheduler 가 chat_id 로 송신.

- **Config 수정**: `daily_briefing_enabled` (Field+AliasChoices, 디폴트 False), `daily_briefing_time` (기본 "07:30"), `daily_briefing_tz` (기본 "Asia/Seoul") 3개 필드. enabled=False 시 task 는 살아 있고 구독은 받지만 트리거 시각에 분석 실행만 스킵.

### 운영 시나리오

1. 사용자가 텔레그램에서 `/briefing_on` → SQLite `briefing_subscribers` 에 chat_id 등록.
2. 서버 `.env` 에서 `DAILY_BRIEFING_ENABLED=true` 설정 후 봇 재시작.
3. 매일 07:30 KST 자동 트리거 → `mode='deep'` 분석 (2-call) → HTML 생성 → Cloudflare 배포 → 구독한 모든 채팅에 보고서.
4. 분석 도중 산출된 watch_signals 는 v2.9.5 watchlist registry 에도 자동 등록 (`parent_chat_id` 기준).

### 트러블슈팅 / 주의사항

- **잘못된 base branch 사례 (메타 트러블슈팅)**: 작업 초기에 옛 commit 위에서 v3.0.0 → v3.1.0 으로 작업했다가 사용자가 "현재 봇이 v5.0.0 인데?" 라고 지적. main 의 v5.0.x 위에서 다시 작업 — *항상 작업 시작 전 `git log origin/main` 확인할 것*.
- **타임존**: `zoneinfo.ZoneInfo` 는 Python 3.9+. requirements 의 `>=3.11` 충족.
- **봇 동시 작업**: 일일 브리핑 실행 중 사용자가 일반 분석 요청 시, 기존 `_queue` 메커니즘은 텔레그램 메시지 핸들러 안에서만 동작 — scheduler 의 분석은 큐를 거치지 않고 직접 orchestrator 호출. 1봇 1동시 분석 가정 운영.
- **중복 트리거 방지**: 같은 날 봇 재시작 + 트리거 시각 지난 케이스에서 `briefing_runs.run_date` PK 가 atomic guard.

---

## v5.1.2 — Daily Briefing 기본 트리거 시각 07:30 → 06:00 KST (2026-05-14)

### 사용자 요청
"간밤에 이슈들을 식별하고 보고서 만들어 내는 기능을 어제 만들었는데, 이 부분에
있어서 시간을 내가 07:30에 만드는것으로 했는데, 06:00 로 조정하자. 너무 늦는거
같아. 나머지는 변경사항 없어."

### 변경

| 파일 | 수정 |
|------|------|
| `src/config.py` | `daily_briefing_time` Field default `"07:30" → "06:00"` |
| `src/scheduler/daily_briefing.py` | `run_daily_briefing_loop(time_str=...)` default + `_build_briefing_prompt` docstring 동기화 |
| `.env.example` | `DAILY_BRIEFING_TIME=07:30 → 06:00` |
| `src/orchestrator.py` | `VERSION = "v5.1.1" → "v5.1.2"` |
| docs (README / WORKFLOWS / GOAL / docs/ARCHITECTURE / docs/REPO_MAP / CHANGELOG) | "기본 07:30 KST" 표기 갱신 + `last_synced_with` v5.1.2 |

### 메타 트러블슈팅 — 잘못된 base branch (재발)

작업 시작 시 `claude/adjust-report-schedule-1Dcv9` 브랜치가 v5.1.0 *이전* 의
maplibre 샘플 머지 (`dcaf6af`) 에서 분기되어 있어 `src/scheduler/` 가 존재하지
않는 상태였음. v5.1.0 DEVLOG §9.J 의 "*항상 작업 시작 전 `git log origin/main`
확인*" 교훈이 또 재발 — 이번에는 사용자가 `5.1.1 이 최신인가보다` 라고 지적.

해결: `git fetch --all` → `git reset --hard origin/main` (v5.1.1) 후 06:00 변경
적용. 브랜치는 force push (`--force-with-lease`) 로 정리. 이전 base 의 maplibre
샘플 work 는 `claude/maplibre-d3-sample-page-CntQY` 에 그대로 보존됨.

### 의사결정

- **운영 영향 없음**: env `DAILY_BRIEFING_TIME` 으로 override 한 환경은 영향 없음
  (Pydantic settings 가 env 우선). 디폴트 변경만이라 봇 재기동 후 다음 트리거가
  06:00 으로 자연 적용. 새 의존성·DB 마이그레이션·프롬프트 변경 없음.
- **시간 선택 (06:00)**: 시장 개장 (09:00 KST) · 외교 일정 시작 전에 더 일찍
  노출하기 위함. ContextAnalyst 웹 검색 + NarrativeComposer deep 모드의 평균
  실행 시간 (~10~15분) 을 고려해도 06:30 안에 송신 완료 → 출근 전 확인 가능.
- **CHANGELOG v5.1.0 본문은 보존**: v5.1.0 출시 시점의 디폴트는 07:30 이었던 게
  사실. 본문은 "디폴트 07:30" 그대로 두고, REQ-V5-101 (GOAL.md) 에서 "v5.1.2
  부터 06:00" 노트로 히스토리 표기. DEVLOG append-only 원칙 준수.

---

## v5.2.3 — KOSPI 보고서 (analysis_20260515_230117) 차트 4건 결함 패치 (2026-05-15)

### 보고된 결함 (사용자 — 모바일 스크린샷 3장)

- **#1 영역 fill 그라데이션 누락** — line 차트의 area fill 이 단색·평탄.
- **#2 차트 좌측 치우침** — line/area 가 캔버스의 좌측 ~85% 만 차지, 우측 ~15% 가
  공백. "왜 7493 같은 라벨도 우측에 어색하게 떠 있나" 와 결합돼 발견.
- **#3 우측 끝 값 "7493.180175125"** — 부동소수점 값이 그대로 텍스트화돼 노출.
- **#4 3개 차트가 동일한 1-5 번호 + 동일 풋노트** — 코스피·삼성전자·SK하이닉스
  3개 차트의 우상단 번호 배지와 하단 풋노트가 1자도 차이 없이 같음. "차트마다
  관련 사건만 떠야 하는 거 아니냐" 가 사용자 지적.

### 메타 — 잘못된 base branch (재발 2회차)

이번에도 작업 시작 시 *stale base* 위에서 분석을 시작. `src/templates/report.html`
의 `drawLineChart` 인라인 Canvas JS 를 패치하고 v3.0.1 으로 VERSION 도 깎은 채
push 까지 완료한 다음 사용자가 "지금 버전이 5.2.0인데???" 로 지적해 발견. 실제
main 은 v5.2.2 이고, v5.2.0 부터 차트 렌더링은 `src/templates/static/charts.js`
(d3 기반) + `src/agents/chart_critic.py` + `src/visual/chart_gate.py` +
`src/tools/market_fetcher.py` 로 통째 이전돼 있었음. 내 v3.0.1 패치는 v5.2.x 가
이미 더 이상 사용 안 하는 *legacy Canvas 경로* 만 건드린 무의미 작업.

- v5.1.0 DEVLOG §9.J 의 "*항상 작업 시작 전 `git log origin/main` 확인*" 교훈이
  3회차로 재발. **작업 시작 전 origin 의 `VERSION` 과 main commit 둘 다 확인하는
  rule** 을 향후 모든 long-running agent 세션에 강제할 것.
- 해결: 잘못된 v3.0.1 커밋이 들어간 `claude/fix-kospi-chart-issues-8UDEF` 브랜치
  통째 폐기. `claude/fix-kospi-charts-v522` 신규 브랜치를 origin/main (v5.2.2)
  base 에서 분기해서 처음부터 다시.

### 결함별 근본 원인 (v5.2.2 기준)

| # | 위치 | 원인 |
|---|------|------|
| 1 | `src/templates/static/charts.js drawLine`, line 417 | `svg.append('path').attr('d', area(data)).attr('fill', t.accent).attr('fill-opacity', 0.10)` — 단색·평탄 fill, 알파 0.10. 같은 파일의 `drawArea` (line 1273-1283) 는 이미 `linearGradient` 사용 — 두 함수가 시각 언어 일관 안 됨. SSOT 위반 (gradient 가 기대 동작). |
| 2 | `drawLine`, line 388 + 392 | `computeZones(W, H, { left: 60, right: 110 })` → 우측 110px 빈 공간 (좌측 60 대비 거의 2배). `scalePoint(...).padding(0.1)` 이 추가로 양 끝 5%씩 빔. 결과적으로 데이터 시각화가 캔버스 폭 ~75% 만 차지. `placeEndLabel` 의 가장 긴 후보(120px) 라도 좌측 candidate 가 있어 110 은 과도. |
| 3 | `drawLine`, line 423 | `placeEndLabel(svg, x(...), y(+last.y), String(last.y), t, ...)`. `String(last.y)` 가 `last.y` 의 toString — 7493.180175125 라면 그대로 "7493.180175125". 같은 함수의 Y 라벨은 `d3.format('.0f')(v)` 로 정수 처리 — end-value 라벨만 포맷 규칙에서 누락. |
| 4 | `src/orchestrator.py _attach_event_markers`, line 136-170 | `timeline` 의 모든 이벤트를 *모든* chart_data row 에 단순 매칭. 차트의 instrument 와 무관. `_build_ts_chart` 가 코스피/삼성/하이닉스 series 각각에 동일 `_attach_event_markers(chart_data, timeline, ctype)` 를 호출 → 3개 차트 모두 같은 5개 사건이 같은 날짜에 박힘 → charts.js `_renderEventBadgesAndFootnote` 가 같은 1-5 번호 배지 + 같은 footnote 5줄을 렌더. |

### 패치

**`src/templates/static/charts.js drawLine`** (line 384-460 부근):
- `computeZones` 의 `right: 110 → 70`. data zone 우측 ~85% 위치 → ~92% 로 확장.
- `scalePoint(...).padding(0.1) → padding(0.04)`. 양 끝 cropped 인상 완화.
- area fill 을 `linearGradient` 로 교체 (stop 0%=alpha 0.28, 100%=alpha 0.02).
  `gradId` 는 `data-chart-id` 또는 random suffix — 한 페이지 내 중복 방지.
- end-value text 를 `Math.abs(lastY) >= 1000 ? d3.format(',.0f') : d3.format(',.2f')`
  로 포맷. Y 라벨과 일치.

**`src/orchestrator.py`**:
- `_INDEX_INSTRUMENTS` 튜플 신규 — 지수/벤치마크 정의 (코스피·코스닥·다우·나스닥
  ·S&P 500·닛케이·항생).
- `_KNOWN_INSTRUMENTS_LC` 튜플 — substring 매칭용 알려진 자산 명단 (소문자).
- `_event_mentions_any_instrument(text_lower)`, `_event_relevant_to(text, instrument)`
  헬퍼 신규.
- `_attach_event_markers(chart_data, timeline, ctype, instrument="")` —
  `instrument` 매개변수 추가, 필터링 4단계:
  1. 자기 instrument 명시 → 부착
  2. 지수/벤치마크 차트 → 모든 이벤트 흡수
  3. 어떤 instrument 도 명시 안 된 일반 시장 이벤트 → 개별 자산 차트도 흡수
  4. 그 외 → 스킵
- `_build_ts_chart` 가 `instrument=name` 을 `_attach_event_markers` 에 전달.
- `instrument=""` 호출 시 backward-compat — 종전처럼 모든 이벤트 통과.

**`src/orchestrator.py:VERSION`** `v5.2.2 → v5.2.3`.

### 검증

- `python -m py_compile src/orchestrator.py` → pass.
- `node -e "new Function(charts.js)"` → parse pass.
- `_attach_event_markers` 단위 검증 (사용자 보고서의 실제 5개 timeline 이벤트로):
  - KOSPI: 5/5 (모든 이벤트, 지수 차트라 흡수)
  - 삼성전자: 3/5 (05-07 일반시장 fallback, 05-12 일반시장 fallback, 05-14 "삼성전자" mention)
  - SK하이닉스: 4/5 (05-07 일반시장 fallback, 05-11 "SK하이닉스" mention, 05-12 일반시장 fallback, 05-14 "SK하이닉스" mention)
  - 3개 차트가 서로 다른 events 셋을 가지게 됨 — 사용자 요구 충족.
  - `instrument=""` 호출 시 5/5 (backward-compat 유지).

### 변경된 파일

| 파일 | 변경 |
|------|------|
| `src/orchestrator.py` | `VERSION` v5.2.2 → v5.2.3, `_INDEX_INSTRUMENTS` / `_KNOWN_INSTRUMENTS_LC` / `_event_mentions_any_instrument` / `_event_relevant_to` 신규, `_attach_event_markers` 시그니처에 `instrument` 추가, `_build_ts_chart` 가 instrument 전달 |
| `src/templates/static/charts.js` | `drawLine` 의 zones / scalePoint padding / area fill (linearGradient) / end-value 포맷 |
| `README.md`, `CHANGELOG.md`, `DEVLOG.md` | `last_synced_with` v5.2.3, CHANGELOG `[v5.2.3]` 항목, 본 DEVLOG 항목 |

### 후속 / 비포함

- `chart_gate` / `chart_critic` / `market_fetcher` 미변경 — 결함이 그쪽에서 비롯
  되지 않음.
- 시각적 회귀 테스트 자동화 부재 — 현재는 코드 parse + filter 단위 검증까지.
- `drawArea` / `drawCandle` 도 `_attach_event_markers` 의 출력에 의존하므로 이번
  filter 변경의 혜택을 동일하게 받음 (코드 수정 불필요).
- LLM `visual_analyst.chart_config.charts[]` (legacy Canvas) 경로는 v5.2.x 에서
  `report.html:124-134` "Legacy Canvas Charts" 섹션으로 보존 — deep 모드에서만
  보조 출력. 본 패치 범위 밖.
