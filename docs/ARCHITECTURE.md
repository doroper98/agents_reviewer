---
tier: 2
last_synced_with: v3.1.0
ssot_for:
  - "시스템 아키텍처 다이어그램"
  - "분석 파이프라인 흐름"
  - "보고서 archetype 분기 구조 (V3 Step 2 활성화)"
  - "보고서 블록 렌더링 흐름 (V3 Step 3 활성화)"
  - "Quality Gate + Synthesis Judge 위치 (V3 Step 4 활성화)"
  - "토큰 사용량 추정"
  - "Token Budget + Mode Routing (v3.1.0 활성화)"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "src/agents/* (구성)"
  - "src/archetypes/registry.py (archetype 분기 SSOT)"
  - "src/token_budget.py (mode 정책)"
  - "src/lens_policy.py (lens 결정 규칙)"
  - "GOAL.md (REQ-AGT-*, REQ-V3-*)"
last_review: 2026-04-27
---

# Event Analysis Team — Architecture

> 시스템 아키텍처의 SSOT. 다이어그램·데이터 흐름·기술 스택을 한곳에 정리.
> 에이전트·렌즈·블록 카탈로그는 [docs/CATALOGS.md](CATALOGS.md), 데이터 모델 도식은 [docs/DATA_MODELS.md](DATA_MODELS.md).

---

## 1. 한 줄 요약

텔레그램 메시지 → mode 결정 (fast/standard/deep, 키워드 자동 매핑) → ContextAnalyst → Strategy Planner (축약) + Quality Gate 1 → lens pool (mode 별 cap 1/2/4) + (deep 만) v2 페르소나 → 시나리오 → 결정적 시각화 → Synthesis Judge (heuristic-first) + Quality Gate 2 → archetype 11종 중 matrix 결정 → HTML 보고서 → Cloudflare 배포 → 공유 링크 + Watchlist 영구 저장.

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
Phase 1   ① 상황인식 분석관 → ContextAnalysis
                ▼
Phase 1.5 [V3 Step 4] 🛡 Quality Gate 1 — Plan Sanity
                ▼  (failure → max 2 retries → "⚠️ 부분 분석 완료. gate_1 실패")
Phase 2   ② 이해관계자 분석관 → PlayerAnalysis
          ③ 구조/상호작용 분석관 → DynamicsAnalysis
Phase 3   ④ 연쇄반응 분석관 → ChainReactionAnalysis
          ⑤ 시나리오 분석관 → ScenarioAnalysis
Phase 3.5 ⑥ 시각화 분석관 → VisualAnalysis
                ▼
Phase 3.7 [V3 Step 4] orchestrator._wrap_findings()
                ▼  (각 v2 분석 → AnalyticalFinding(Claim+Evidence+ConfidenceProfile))
Phase 3.75 [V3 Step 5-A/5-C] 🔬 _run_lenses() — Lens Pool (cap 4)
                ▼  (strategy.recommended_lenses 의 lens_id 들 → registry.get_lens() →
                    각 lens 가 자체 LLM 호출 + AnalyticalFinding 산출, 11종 풀에서 4개 한도.
                    11종 = 분야 6 (geopolitical/financial_transmission/tech_architecture/
                    policy_implementation/accident_causality/market_structure) + 메타 2
                    (red_team/pre_mortem) + 페르소나 이전 3 (stakeholder/structural/cascade,
                    v3.0.0 Step 5-C — 구 PlayerAnalyst/DynamicsAnalyst/ChainReactionAnalyst))
Phase 3.8 [V3 Step 4] 🧮 SynthesisJudge.judge(findings) → JudgmentVerdict
                ▼  (contradictions 노출, 봉합 X — Anti-pattern #5)
Phase 3.9 [V3 Step 4] 🛡 Quality Gate 2 — Coverage Check
                ▼  (failure → max 2 retries (judgment 재생성) → "⚠️ 부분 분석 완료. gate_2 실패")
Phase 4   ⑦ 보고서 합성관 → Jinja2 → HTML → Cloudflare Pages
                ▼
Phase 4.5 [V3 Step 5-B] 📒 Watchlist Registry
                ▼  (ScenarioAnalysis.watch_signals → WatchSignal → SQLite 영구 저장.
                    봇 프로세스 내 asyncio monitor (1h 주기) 가 deadline 도래 시
                    auto-fire (ambiguous) + 텔레그램 알림. Anti-pattern #11 회피)
```

각 에이전트는 이전 에이전트들의 결과를 누적해서 받음. Quality Gate 두 곳은 우회 금지 (Anti-pattern #7) — 실패해도 부분-분석 알림 후 *계속 진행*. 자세한 역할은 [docs/CATALOGS.md](CATALOGS.md) 의 Agents 섹션 참조.

### 3.0 Quality Gates + Synthesis Judge 다이어그램 (V3 Step 4 — v2.8.0)

```
   AnalysisStrategy ─────┐
        │                │
        ▼                │
  ┌──────────────────────┴────────────────────────┐
  │  🛡 Gate 1 — Plan Sanity                       │
  │  · core_questions 분석 가능성                    │
  │  · lens-intent 정합성                           │
  │  · evidence_plan 실행 가능성                     │
  │  · LLM-as-judge (선택, CLI 가용 시)              │
  │  · 실패 → 최대 2회 strategy 재생성                │
  │  · 그래도 실패 → "⚠️ 부분 분석 완료" 알림 + 계속    │
  └──────────────────┬───────────────────────────┘
                     ▼
            (모든 v2 에이전트 실행)
                     │
                     ▼
        FullAnalysisResult (v2 분석들)
                     │
                     ▼
  ┌──────────────────────────────────────────────┐
  │  orchestrator._wrap_findings()                │
  │  · context.sources → Evidence 풀              │
  │  · 각 분석 → Claim (evidence_ids ≥1 강제)      │
  │  · ConfidenceProfile 3축 분해                  │
  │  · counter_hypothesis 보존                    │
  │  → list[AnalyticalFinding]                    │
  └──────────────────┬───────────────────────────┘
                     ▼
  ┌──────────────────────────────────────────────┐
  │  🧮 SynthesisJudge.judge()                     │
  │  · 페어와이즈 어휘 충돌 스캔                       │
  │  · counter_hypothesis 명시적 모순 검출            │
  │  · contradictions[] 에 노출 (봉합 X)             │
  │  · resolution: 어느 쪽 채택 + 패배자 counter 보존  │
  │  · ConfidenceProfile = finding 평균 - 모순 페널티  │
  │  → JudgmentVerdict                            │
  └──────────────────┬───────────────────────────┘
                     ▼
  ┌──────────────────────────────────────────────┐
  │  🛡 Gate 2 — Coverage Check                    │
  │  · 모든 core_question 에 finding 매칭            │
  │  · Claim → Evidence 연결 (Pydantic 가드 + 추가)   │
  │  · main_judgment + counter_hypothesis 비어있지 않음│
  │  · 실패 → 최대 2회 judgment 재생성                │
  │  · 그래도 실패 → "⚠️ 부분 분석 완료" 알림 + 계속    │
  └──────────────────┬───────────────────────────┘
                     ▼
            (보고서 합성 — Phase 4)
```

게이트는 항상 실행되며 우회 불가 (Anti-pattern #7). 게이트 통과율·재시도율은 `[quality_inspector] gate_X stats: ...` 로 INFO 로그.

### 3.1 토큰 사용량 + Mode 정책 (v3.1.0)

분석 1건당 LLM 호출 수와 lens 개수, 보조 LLM 단계의 사용 여부는 mode 별로 차등. SSOT 는 [src/token_budget.py](../src/token_budget.py).

| Mode | LLM 호출 cap | Lens cap | LLM Quality Gate | LLM Narrative Plan | LLM Visuals | LLM Synthesis | Legacy Persona |
|------|------------|---------|----------------|------------------|-----------|--------------|---------------|
| fast | 4 | 1 | ❌ | ❌ | ❌ | ❌ | ❌ |
| standard (default) | 7 | 2 | ❌ | ❌ | ❌ | 조건부* | ❌ |
| deep | 12 | 4 | ✅ | ✅ | ✅ | ✅ | ✅ |

\* standard 의 SynthesisJudge LLM 은 contradictions 발견 / aggregate confidence 0.55 미만 / core_questions 미답변 위험 시에만 발화. 그 외에는 heuristic 만.

#### Mode 결정 규칙
- 사용자 메시지에 `짧게` / `간략히` / `간략하게` / `빠르게` / `요약` / `간단히` / `간단하게` / `fast` 키워드 → **fast**
- 사용자 메시지에 `심층` / `깊게` / `자세히` / `정밀` / `면밀` / `상세하게` / `deep` 키워드 → **deep**
- 둘 다 있으면 deep 우선
- 그 외 → **standard** (default)

#### 토큰 사용량 (분석 1건당 추정, 입력+출력 합계)

| Mode | v3.0.0 (이전) | v3.1.0 (이후) |
|------|------------|------------|
| fast (구 quick_mode) | ~28K | ~12K |
| standard | ~37K | ~18K |
| deep | ~57K | ~46K (품질 보존) |

추가로 Strategy Planner 프롬프트 5배 축소 + `json.dumps(indent=2)` 폐기로 input 토큰 ~30% 추가 절감. Max 플랜 CLI 모드라 추가 비용 없음 — 절감 효과는 *시간 단축* 과 *보고서 응답 지연 감소* 로 체감.

### 3.2 Lens 선택 정책 (`lens_policy`)

[src/lens_policy.py](../src/lens_policy.py) 가 `(event_type, user_intent, mode)` 3-튜플로 lens 를 결정. 카탈로그는 [docs/CATALOGS.md §2](CATALOGS.md).

```
event_type 분야별 lens 우선순위:
  tech       → tech_architecture, structural
  accident   → accident_causality, structural, cascade
  financial  → financial_transmission, market_structure, cascade
  industry   → market_structure, stakeholder, structural
  policy     → policy_implementation, stakeholder
  geopolitical → geopolitical, stakeholder, structural
  general    → stakeholder, structural

메타 lens (red_team / pre_mortem) 자동 추가 조건:
  user_intent ∈ {what_to_do, where_vulnerable} → red_team
  user_intent ∈ {what_next}                    → pre_mortem
  · fast 모드는 메타 lens 추가 안 함 (cap=1)
  · deep 모드는 cap 여유 있을 때 반대편 메타 lens 도 추가
```

LLM Strategy Planner 의 `recommended_lenses` 출력은 *우선순위 보정* 에만 활용 (분야 lens 만). 메타 lens 결정권은 정책 단독.

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

### 5.1 Archetype 분기 + 블록 렌더링 (V3 Step 2/3/5-A/5-C — v2.6.0/v2.7.0/v2.9.0/v3.0.0)

Orchestrator 는 **하이브리드 라우팅** 적용 (v3.0.0):
1. Strategy Planner 가 LLM 후보 1순위 `strategy.report_archetype` (string ID) 를 출력.
2. `src/archetypes/registry.select_archetype(strategy)` 가 4-tier 우선순위 매트릭스로 archetype 을 결정 (matrix 가 **최종 결정자**).
3. LLM 후보 ≠ matrix 결과 시 INFO 로그 (`[orchestrator] archetype mismatch — LLM=…, matrix=…`) 후 matrix 결과로 진행. `strategy.report_archetype` 도 matrix 결과로 갱신 → 보고서 헤더와 일치.
4. ReportSynthesizer 가 archetype 별로 분기 렌더 — `six_act_theater` 는 legacy 흐름(byte-equal 보장), 그 외는 블록 디스패처.

```
   AnalysisStrategy.{user_intent, event_type, report_archetype(LLM 후보)}
                        │
                        ▼
   src/archetypes/registry.select_archetype(strategy)   ← matrix 최종 결정자
   (LLM 후보 ≠ matrix 결과 시 INFO 로그 후 matrix 채택,
    strategy.report_archetype 도 갱신)
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
  Step 2/5-A 분야 6종            Step 5-C 의도 전용 5종
  ─────────────────────          ───────────────────────
  · six_act_theater              · decision_brief   (what_to_do)
    (인물극형 specialty,           · timeline_first  (what_happened)
     v3.0.0 default 아님)         · scenario_first  (what_next)
  · financial_transmission       · mechanism_decomp (why_happened)
  · tech_decomposition           · industry_value_chain
  · geopolitical_strategic         (산업·가치사슬)
  · accident_forensic
  · policy_implementation
            │                       │
            └───────────┬───────────┘
                        ▼
   ReportSynthesizer.synthesize(result, archetype)
            │
   ┌────────┴─────────────┐
   ▼                      ▼
 six_act_theater          그 외 archetype (블록 디스패처 경로 — Step 3, v2.7.0)
 → render('report.html')  ┌─────────────────────────────────────────────┐
 (legacy, byte-equal      │ _build_blocks(): for section in             │
  보장 — Anti-pattern #2) │   archetype.section_plan(strategy):         │
                          │   for block_type in section.block_types:    │
                          │     payload = _BLOCK_BUILDERS[type](result) │
                          │     if payload: AnalysisBlock(...)          │
                          │ result.strategy.section_plan = plan         │
                          │ result.blocks = [...]                       │
                          └────────────────────┬────────────────────────┘
                                               ▼
                          ┌─────────────────────────────────────────────┐
                          │ render('report_block.html', ...)            │
                          │  iterate section_plan, dispatch by          │
                          │  section_id → include blocks/<type>.html    │
                          │  (17종 BlockType, payload-only access)      │
                          └─────────────────────────────────────────────┘
```

빌더 매핑·블록 카탈로그의 SSOT 는 코드 (`src/agents/report_synthesizer.py:_BLOCK_BUILDERS`, `src/models.py:BlockType`). 사람-친화 미러는 [docs/CATALOGS.md §3-4](CATALOGS.md). 신규 archetype 추가 시 `src/archetypes/<name>.py` 신설 → `registry.py` 등록 → CATALOGS §3 갱신 (Anti-pattern #14). 신규 BlockType 추가 시 `src/models.py:BlockType` Literal 확장 → `src/templates/blocks/<type>.html` 신설 → `_BLOCK_BUILDERS` 등록 → CATALOGS §4 갱신 (Anti-pattern #15).

### 5.2 보고서 구조 — six_act_theater (인물극형 specialty)

> v3.0.0 부터 default 가 아님. `select_archetype()` 매트릭스의 3순위 (`geopolitical` + `who_benefits`/`what_happened`) 또는 4순위 fallback 에서만 라우팅.

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
