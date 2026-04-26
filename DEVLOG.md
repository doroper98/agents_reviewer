---
tier: 3
last_synced_with: v2.5.0
ssot_for:
  - "개발 상세 로그 (append-only)"
  - "인프라 설치 가이드"
  - "트러블슈팅 기록"
depends_on:
  - "GOAL.md (REQ-* 변경 추적)"
  - "CHANGELOG.md (사용자 관점 변경은 그쪽 SSOT)"
last_review: 2026-04-26
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
