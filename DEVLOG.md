---
tier: 3
last_synced_with: v2.7.0
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
