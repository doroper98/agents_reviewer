# Event Analysis Team — 전체 시스템 구조

> 이 문서 하나로 시스템의 전체 흐름을 파악할 수 있음.
> 마지막 업데이트: 2026-03-29 (v1.7.1)

---

## 1. 시스템 한줄 요약

텔레그램 메시지 → 7개 AI 에이전트 순차 분석 → 6막 HTML 보고서 생성 → Cloudflare 배포 → 텔레그램 공유 링크 전송

---

## 2. 인프라 구성

```
┌─────────────────────────────────────────────────────────────┐
│                    사용자 (텔레그램 앱)                        │
│                    메시지 전송 / 보고서 수신                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS (Telegram Bot API)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Oracle Cloud VM (무료 티어)                      │
│              ubuntu@<오라클_VM_IP>                             │
│                                                              │
│   ┌──────────────────────────────────────────────┐           │
│   │  Python 봇 (python -m src.main)               │           │
│   │  ├── 텔레그램 메시지 수신/응답                   │           │
│   │  ├── 오케스트레이터 (파이프라인 제어)              │           │
│   │  └── 7개 에이전트 순차 호출                      │           │
│   └──────────────────┬───────────────────────────┘           │
│                      │ subprocess 호출                        │
│   ┌──────────────────▼───────────────────────────┐           │
│   │  Claude Code CLI (Max 플랜 인증)               │           │
│   │  --dangerously-skip-permissions               │           │
│   │  --allowedTools "WebFetch,WebSearch"           │           │
│   │  → 각 에이전트의 시스템 프롬프트 + 분석 컨텍스트  │           │
│   └──────────────────────────────────────────────┘           │
│                      │                                       │
│   ┌──────────────────▼───────────────────────────┐           │
│   │  Wrangler CLI (Cloudflare 배포)               │           │
│   │  wrangler pages deploy reports/               │           │
│   └──────────────────┬───────────────────────────┘           │
└──────────────────────┼───────────────────────────────────────┘
                       │ HTTPS
                       ▼
┌─────────────────────────────────────────────────────────────┐
│          Cloudflare Pages (무료)                              │
│          <클라우드플레어_프로젝트명>.pages.dev                           │
│          → HTML 보고서 호스팅 + 공유 링크                      │
└─────────────────────────────────────────────────────────────┘
```

**비용**: 전부 무료 (Oracle Cloud 무료 티어 + Claude Max 플랜 + Cloudflare Pages 무료)

---

## 3. 분석 파이프라인 (에이전트 실행 순서)

사용자가 텔레그램에 메시지를 보내면 다음 순서로 실행됨:

```
Phase 1    ┌─────────────────────────────────────────┐
           │  ① 상황인식 분석관 (context_analyst)      │
           │     웹 검색으로 최신 팩트 수집              │
           │     타임라인, 핵심 수치, 배경 정리          │
           └──────────────────┬──────────────────────┘
                              ▼
Phase 2    ┌─────────────────────────────────────────┐
           │  ② 이해관계자 분석관 (player_analyst)     │
           │     핵심 행위자 식별, 전략, 위험도         │
           └──────────────────┬──────────────────────┘
                              ▼
           ┌─────────────────────────────────────────┐
           │  ③ 구조/상호작용 분석관 (dynamics_analyst) │
           │     게임이론, 비대칭 구조, 전환점           │
           └──────────────────┬──────────────────────┘
                              ▼
Phase 3    ┌─────────────────────────────────────────┐
           │  ④ 연쇄반응 분석관 (chain_reaction)       │
           │     인과 사슬, 도미노 효과, 차단점         │
           └──────────────────┬──────────────────────┘
                              ▼
           ┌─────────────────────────────────────────┐
           │  ⑤ 시나리오 분석관 (scenario_architect)   │
           │     4개 시나리오 + 확률 + 감시 신호        │
           └──────────────────┬──────────────────────┘
                              ▼
Phase 3.5  ┌─────────────────────────────────────────┐
           │  ⑥ 시각화 분석관 (visual_analyst)         │
           │     SVG 관계도, Leaflet 지도, 차트        │
           └──────────────────┬──────────────────────┘
                              ▼
Phase 4    ┌─────────────────────────────────────────┐
           │  ⑦ 보고서 합성관 (report_synthesizer)     │
           │     Executive Summary 생성 (Claude 호출)  │
           │     Jinja2 HTML 렌더링                    │
           │     Cloudflare Pages 배포                 │
           └──────────────────────────────────────────┘
```

**컨텍스트 누적 구조**: 각 에이전트는 이전 에이전트들의 분석 결과를 모두 받아서 작업함.
- ① → 혼자 작업 (웹 검색 기반)
- ②는 ①의 결과를 받음
- ③은 ①+②를 받음
- ④는 ①+②+③을 받음
- ...이런 식으로 누적됨

**토큰 사용량** (분석 1건당):
| 시나리오 | 입력 | 출력 | 합계 |
|---------|------|------|------|
| 짧은 이벤트 | ~16K | ~5K | ~21K |
| 보통 이벤트 | ~28K | ~9K | ~37K |
| 복잡한 이벤트 | ~44K | ~13K | ~57K |

---

## 4. 텔레그램 통신 흐름

### 풀 분석 (일반 메시지)
```
사용자: "이란-이스라엘 전쟁 분석해줘"
   ↓
봇: "🔍 분석을 시작합니다..."
봇: "📋 [1/7] 상황인식 분석 중..."
봇: "👥 [2/7] 이해관계자 분석 중..."
봇: "🔄 [3/7] 구조 분석 중..."
봇: "⛓️ [4/7] 연쇄반응 분석 중..."
봇: "🔮 [5/7] 시나리오 분석 중..."
봇: "📊 [6/7] 시각화 생성 중..."
봇: "📝 [7/7] 보고서 생성 중..."
   ↓
봇: [코드블록 텍스트 보고서]
봇: [HTML 파일 첨부 + Cloudflare 공유 링크]
```

### 간단 질답 (`?` 접두어)
```
사용자: "? SPR이 뭐야?"
   ↓
봇: [단일 Claude 호출로 간단 답변]
```

---

## 5. 보고서 생성 및 저장 흐름

```
에이전트 1~6 분석 완료
    │
    ▼
보고서 합성관 (report_synthesizer.py)
    │
    ├── 1) Claude 호출: 분석 결과 → 3줄 Executive Summary 생성
    │
    ├── 2) report.css 파일 로드 (별도 CSS 파일)
    │
    ├── 3) Jinja2 렌더링:
    │       report.html (템플릿) + 분석 데이터(JSON) + CSS → 완성된 HTML
    │
    ├── 4) 로컬 저장:
    │       reports/analysis_20260329_041500.html
    │
    ├── 5) index.html 생성:
    │       reports/index.html (보고서 목록 페이지)
    │
    └── 6) Cloudflare 배포:
            wrangler pages deploy reports/
            → https://{hash}.<클라우드플레어_프로젝트명>.pages.dev/analysis_20260329_041500.html
```

**보고서 구조 (6막 극장)**:
| 막 | 영문 | 한글 | 내용 |
|----|------|------|------|
| ACT I | THE BOARD | 상황인식 | 팩트, 타임라인, 핵심 수치, 배경 |
| ACT II | THE PLAYERS | 이해관계자 | 행위자, 전략, 위험도, 관계 구도 |
| ACT III | THE DYNAMICS | 구조/상호작용 | 프레임워크, 비대칭, 전환점 |
| ACT IV | THE CHAIN REACTION | 연쇄반응 | 인과 사슬, 차단점, 최악의 경우 |
| ACT V | THE SCENARIOS | 향후 시나리오 | 4개 시나리오, 확률, 행위자별 영향 |
| ACT VI | THE SIGNALS | 감시 시그널 | 시나리오 전환 판별 신호 |

---

## 6. 기술 스택

| 영역 | 기술 | 비고 |
|------|------|------|
| 언어 | Python 3.11+ | async/await, type hints |
| AI | Claude Code CLI (Opus) | Max 플랜, subprocess 호출 |
| 메시징 | python-telegram-bot | 비동기 텔레그램 봇 |
| 데이터 검증 | Pydantic v2 | 모든 데이터 모델 |
| 보고서 템플릿 | Jinja2 | HTML 렌더링 |
| 시각화 | SVG 직접 생성 | 관계도, 플로우차트 |
| 지도 | Leaflet.js (CDN) | 지정학 분석 시 |
| 차트 | Canvas 2D / TradingView | 금융 데이터 시 TradingView |
| 폰트 | Noto Serif KR + Noto Sans KR | Google Fonts CDN |
| 호스팅 | Cloudflare Pages | wrangler CLI 배포 |
| 서버 | Oracle Cloud VM | 무료 티어, Ubuntu 22.04 |

---

## 7. 프로젝트 파일 구조

```
agents_reviewer/
├── CLAUDE.md                  # AI 에이전트 행동 규칙 (Claude Code가 읽음)
├── DEVLOG.md                  # 전체 개발 로그
├── GOAL.md                    # 요구사항 & 성공 기준
├── WORKFLOWS.md               # 실행 절차
├── overall_structure.md       # ← 이 문서
├── .env                       # 환경변수 (토큰, API 키)
├── requirements.txt           # Python 의존성
│
├── docs_canonical/            # 정규 문서
│   ├── ARCHITECTURE.md        # 시스템 아키텍처
│   ├── REPO_MAP.md            # 파일/폴더 구조
│   ├── STYLEGUIDE.md          # 코드 컨벤션
│   └── TESTING.md             # 테스트 전략
│
├── src/
│   ├── main.py                # 엔트리포인트 (봇 시작)
│   ├── config.py              # Pydantic Settings (.env 파싱)
│   ├── models.py              # 전체 데이터 모델 정의
│   ├── orchestrator.py        # 파이프라인 제어 (에이전트 순차 호출)
│   ├── telegram_bot.py        # 텔레그램 메시지 핸들링
│   │
│   ├── agents/                # 7개 에이전트
│   │   ├── base.py            # 기본 클래스 (Claude CLI/API 호출 공통 로직)
│   │   ├── context_analyst.py
│   │   ├── player_analyst.py
│   │   ├── dynamics_analyst.py
│   │   ├── chain_reaction_analyst.py
│   │   ├── scenario_architect.py
│   │   ├── visual_analyst.py
│   │   └── report_synthesizer.py
│   │
│   └── templates/             # 보고서 템플릿
│       ├── report.html        # Jinja2 HTML 템플릿 (6막 구조)
│       └── report.css         # 보고서 스타일시트
│
├── reports/                   # 생성된 HTML 보고서 (git ignored)
└── prototype_gold_chart.html  # Canvas 차트 참조 구현
```

---

## 8. 데이터 흐름 요약

```
사용자 메시지 (텍스트)
    ↓
telegram_bot.py: 메시지 수신, AnalysisRequest 생성
    ↓
orchestrator.py: 에이전트 순차 호출, FullAnalysisResult 구성
    ↓
각 에이전트 (base.py):
    시스템 프롬프트 + 이전 분석 결과 → Claude CLI subprocess → JSON 응답 → Pydantic 모델 파싱
    ↓
report_synthesizer.py:
    FullAnalysisResult → Jinja2 렌더링 → HTML 파일 저장 → wrangler 배포
    ↓
telegram_bot.py: HTML 파일 + 공유 링크 전송
```

모든 에이전트 간 통신은 **Pydantic 모델**을 통해 이루어짐 (raw dict 사용 금지).
오케스트레이터가 `FullAnalysisResult` 객체를 들고 있으면서 각 에이전트의 결과를 누적 저장.
