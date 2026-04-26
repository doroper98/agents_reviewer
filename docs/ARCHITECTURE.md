---
tier: 2
last_synced_with: v2.6.0
ssot_for:
  - "시스템 아키텍처 다이어그램"
  - "분석 파이프라인 흐름"
  - "보고서 archetype 분기 구조 (V3 Step 2 활성화)"
  - "토큰 사용량 추정"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "src/agents/* (구성)"
  - "src/archetypes/registry.py (archetype 분기 SSOT)"
  - "GOAL.md (REQ-AGT-*, REQ-V3-*)"
last_review: 2026-04-26
---

# Event Analysis Team — Architecture

> 시스템 아키텍처의 SSOT. 다이어그램·데이터 흐름·기술 스택을 한곳에 정리.
> 에이전트·렌즈·블록 카탈로그는 [docs/CATALOGS.md](CATALOGS.md), 데이터 모델 도식은 [docs/DATA_MODELS.md](DATA_MODELS.md).

---

## 1. 한 줄 요약

텔레그램 메시지 → 7개 AI 에이전트 순차 분석 → 6막 HTML 보고서 생성 → Cloudflare 배포 → 텔레그램 공유 링크 전송.

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
│   │  └── 에이전트 순차 호출                           │           │
│   └──────────────────┬───────────────────────────┘           │
│                      │ subprocess 호출                        │
│   ┌──────────────────▼───────────────────────────┐           │
│   │  Claude Code CLI (Max 플랜 인증)               │           │
│   │  --dangerously-skip-permissions               │           │
│   │  --allowedTools "WebFetch,WebSearch"           │           │
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
│          <프로젝트명>.pages.dev                                │
└─────────────────────────────────────────────────────────────┘
```

비용은 Oracle Cloud 무료 티어 + Claude Max 플랜 + Cloudflare Pages 무료로 0원.

---

## 3. 분석 파이프라인 (에이전트 실행 순서)

```
Phase 1   ┌─────────────────────────────────────────┐
          │  ① 상황인식 분석관 (context_analyst)      │
          │     웹 검색 → 팩트, 타임라인, 핵심 수치     │
          └──────────────────┬──────────────────────┘
                             ▼
Phase 2   ┌─────────────────────────────────────────┐
          │  ② 이해관계자 분석관 (player_analyst)     │
          │     행위자, 전략, 위험도                   │
          └──────────────────┬──────────────────────┘
                             ▼
          ┌─────────────────────────────────────────┐
          │  ③ 구조/상호작용 분석관 (dynamics_analyst) │
          │     게임이론, 비대칭, 전환점               │
          └──────────────────┬──────────────────────┘
                             ▼
Phase 3   ┌─────────────────────────────────────────┐
          │  ④ 연쇄반응 분석관 (chain_reaction)       │
          │     인과 사슬, 도미노 효과                 │
          └──────────────────┬──────────────────────┘
                             ▼
          ┌─────────────────────────────────────────┐
          │  ⑤ 시나리오 분석관 (scenario_architect)   │
          │     시나리오 + 감시 신호                   │
          └──────────────────┬──────────────────────┘
                             ▼
Phase 3.5 ┌─────────────────────────────────────────┐
          │  ⑥ 시각화 분석관 (visual_analyst)         │
          │     SVG, Leaflet 지도, Canvas 차트       │
          └──────────────────┬──────────────────────┘
                             ▼
Phase 4   ┌─────────────────────────────────────────┐
          │  ⑦ 보고서 합성관 (report_synthesizer)     │
          │     Executive Summary → Jinja2 → HTML    │
          │     → Cloudflare Pages 배포              │
          └──────────────────────────────────────────┘
```

각 에이전트는 이전 에이전트들의 결과를 누적해서 받음. 자세한 역할은 [docs/CATALOGS.md](CATALOGS.md) 의 Agents 섹션 참조.

### 3.1 토큰 사용량 (분석 1건당 추정)

| 시나리오 | 입력 | 출력 | 합계 |
|---------|------|------|------|
| 짧은 이벤트 | ~16K | ~5K | ~21K |
| 보통 이벤트 | ~28K | ~9K | ~37K |
| 복잡한 이벤트 | ~44K | ~13K | ~57K |

Max 플랜 CLI 모드라 추가 비용 없음.

---

## 4. 데이터 흐름

```
사용자 메시지 (텍스트)
    ↓
telegram_bot.py: 메시지 수신, AnalysisRequest 생성
    ↓
orchestrator.py: 에이전트 순차 호출, FullAnalysisResult 누적
    ↓
각 에이전트 (base.py):
    시스템 프롬프트 + 이전 분석 결과 → Claude CLI subprocess
    → JSON 응답 → Pydantic 모델 파싱
    ↓
report_synthesizer.py:
    FullAnalysisResult → Jinja2 렌더링 → HTML 저장 → wrangler 배포
    ↓
telegram_bot.py: HTML 파일 + 공유 링크 전송
```

모든 에이전트 간 통신은 Pydantic 모델 (raw dict 금지). 모델 정의 SSOT는 `src/models.py`, 도식은 [docs/DATA_MODELS.md](DATA_MODELS.md).

---

## 5. 보고서 생성 흐름

```
에이전트 1~6 분석 완료
    │
    ▼
report_synthesizer.py
    ├── 1) Claude 호출: Executive Summary (3줄)
    ├── 2) report.css 로드
    ├── 3) Jinja2 렌더링 (report.html + 데이터 + CSS → HTML)
    ├── 4) reports/analysis_YYYYMMDD_HHMMSS.html 저장
    ├── 5) reports/index.html (목록 페이지) 갱신
    └── 6) wrangler pages deploy reports/
            → https://<프로젝트명>.pages.dev/analysis_YYYYMMDD_HHMMSS.html
```

### 5.1 Archetype 분기 (V3 Step 2 — v2.6.0)

Strategy Planner 가 `user_intent` + `event_type` 으로 archetype 을 결정 → `src/archetypes/registry.py` 가 archetype 객체 반환 → ReportSynthesizer 가 `archetype.template_path()` 로 분기 렌더.

```
              AnalysisStrategy.report_archetype  (string ID)
                        │
                        ▼
            src/archetypes/registry.get_archetype()
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
six_act_theater   financial_transmission  tech_decomposition
   (default)      (시장·거시)            (기술·AI·인프라)
        │               │                │
        ▼               ▼                ▼
report.html      archetypes/             archetypes/
  (legacy,       financial_              tech_
   byte-equal)   transmission.html       decomposition.html
                 (Step 2 placeholder,    (Step 2 placeholder,
                  Step 3 본격 렌더)       Step 3 본격 렌더)
```

archetype 카탈로그의 SSOT 미러는 [docs/CATALOGS.md §3](CATALOGS.md). 신규 archetype 추가 시 `src/archetypes/<name>.py` 신설 → `registry.py` 등록 → CATALOGS 갱신 (Anti-pattern #14 회피).

### 5.2 보고서 구조 — six_act_theater (default archetype)

| 막 | 영문 | 한글 | 내용 |
|----|------|------|------|
| ACT I | THE BOARD | 상황인식 | 팩트, 타임라인, 핵심 수치, 배경 |
| ACT II | THE PLAYERS | 이해관계자 | 행위자, 전략, 위험도, 관계 구도 |
| ACT III | THE DYNAMICS | 구조/상호작용 | 프레임워크, 비대칭, 전환점 |
| ACT IV | THE CHAIN REACTION | 연쇄반응 | 인과 사슬, 차단점, 최악의 경우 |
| ACT V | THE SCENARIOS | 향후 시나리오 | 시나리오, 확률, 행위자별 영향 |
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
| 차트 | Canvas 2D | DPR 3x, Noto Serif KR/Noto Sans KR |
| 폰트 | Noto Serif KR + Noto Sans KR | Google Fonts CDN |
| 호스팅 | Cloudflare Pages | wrangler CLI 배포 |
| 서버 | Oracle Cloud VM | 무료 티어, Ubuntu 22.04 |

Canvas 차트 제작 기준은 [CLAUDE.md](../CLAUDE.md#canvas-차트-제작-기준) 와 참조 구현 [docs/references/prototype_gold_chart.html](references/prototype_gold_chart.html).

---

## 7. 에이전트 통신 규약

- 모든 통신은 Pydantic 모델 (raw dict 금지)
- 오케스트레이터가 `FullAnalysisResult` 객체를 들고 각 에이전트 결과를 누적
- 각 에이전트는 이전 결과를 모두 받아 typed output 반환
- Claude CLI 호출 시 `--dangerously-skip-permissions --allowedTools "WebFetch,WebSearch"`

---

## 8. Out of scope (이 문서가 다루지 않는 것)

- 에이전트별 상세 역할 → [docs/CATALOGS.md](CATALOGS.md)
- Pydantic 모델 정의 → `src/models.py` (도식만 [docs/DATA_MODELS.md](DATA_MODELS.md))
- 인프라 설치 절차 → [DEVLOG.md](../DEVLOG.md)
- 분석 명령 사용법 → [WORKFLOWS.md](../WORKFLOWS.md)
