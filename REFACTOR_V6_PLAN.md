---
tier: 1
status: proposal (v2 — Codex 외부 critic 중심 개정)
target_version: v6.0.0
based_on_baseline: v5.8.8
last_synced_with: v5.8.8
ssot_for:
  - "V6 마스터 플랜 (workflow → agent, 사실 grounding + bounded Codex critic 루프)"
  - "V6 요구사항 (REQ-V6-N) 정본"
  - "V6 Phase 진입/완료 기준 + 상세 테스트 플랜"
  - "V6 anti-pattern (AP-V6-N) 카탈로그 — append-only"
depends_on:
  - "src/agents/narrative_composer.py (본문 생성·보완 — 보존, Claude Opus 고정)"
  - "src/agents/context_analyst.py (증거 수집 — provenance 확장)"
  - "src/visual/capture.py (차트 PNG 렌더 — Codex 미학 검수 입력)"
  - "src/visual/usage_log.py (텔레메트리 패턴 — critique_log 적립의 참조 구현)"
  - "docs/REPORT_WRITING_ANTIPATTERNS.md / docs/CHART_RENDERING_ANTIPATTERNS.md (승격 타깃)"
  - "REFACTOR_V5_PLAN.md (V5 Phase 와 충돌 금지 — 병행 트랙)"
  - "외부: codex CLI (ChatGPT 구독 인증, headless 호출) — V6 critic 의 런타임 의존"
proposed_by: NVIDIA GTC 보고서 팩트체크 회귀 (2026-06-01) + agentic 정의 논의 + Codex critic 설계 합의 (2026-06-03)
last_review: 2026-06-03
---

# REFACTOR V6 — Workflow → Agent: 사실 grounding + Bounded Codex Critic Loop

> **목적.** v5.8.8 은 *강한 문체·시각 거버넌스를 갖췄으나 사실 거버넌스와 검증 루프가
> 없는 단일 패스 LLM 파이프라인* 이다. 2026-06-01 NVIDIA GTC 보고서가 외부
> 팩트체크(ChatGPT)에서 받은 5종 사실오류는 *우연이 아니라 구조적 결함* 이다 —
> 가장 강한 사실 규율 장치(`Claim.must_have_evidence`)가 정작 사용자가 읽는
> 자유 본문(`ComposedSection.prose`)에는 적용되지 않고, 작성된 주장을 출처와
> 대조하는 *검증 루프* 가 시스템 어디에도 없다. style 은 `editor`, 차트는
> `chart_critic`/`desk_editor` 가 critic 을 도는데 **fact 에는 critic 이 없다.**
>
> **V6 의 한 줄 결정 (2026-06-03):** 그 빠진 critic 을 *외부 모델*로 채운다 —
> 외부(ChatGPT)가 우연히 대신해 주던 fact-critic 역할을 **`codex` CLI(ChatGPT 구독)**
> 로 파이프라인 안에 내재화한다. 교차 모델(GPT)이 Claude(Opus)의 confabulation 을
> 검수하는 구조라야, 같은 실패모드를 공유하는 Claude-자기점검의 맹점을 피한다.
>
> **루프 (확정).** `Opus 작성(1) → Codex 검수(1) → Opus 보완(1) → Codex 확인패스(1)`.
> 재작성은 1회(bounded), 확인패스는 검증만(재작성 없음). 루프 *제어*는 0 LLM
> (Codex verdict 의 위반 카운트로 결정). Codex 는 사실/문구 + 차트 데이터 + 차트
> 미학(렌더 PNG) 까지 검수하고, **스스로 웹 verify** 한다. 보완·재작성은 항상
> **Opus** (Sonnet 아님 — 본문은 Opus 고정 AP-V6-1, 구독 정액이라 Sonnet 비용 이점
> 0, 톤 드리프트 리스크만 남음).
>
> **비목적.** ① 무한 자율 agent 금지 (bounded·guarded 루프만). ② 사용자 본문
> 생성·보완 모델을 교체 금지 (Claude Opus 고정 — `_sanitize_symbols`/WRITE-AP-12/13
> 가 Opus 실패모드에 튜닝됨, AP-V6-1). Codex 는 *검수만*, 본문 텍스트를 직접
> 쓰지 않는다 (AP-V6-11). ③ V5 결정성·재현성 유지 — 모든 신규 행동은 `V6_*` flag
> default OFF, 꺼지면 v5.8.8 byte-equal (AP-V6-3). ④ 평이화·일반 독자 우선(v5.5.5)
> 후퇴 금지 — 사실 grounding 을 *그 위에* 얹는다.

---

## 0. 컨텍스트 — v5.8.8 현황과 V6 수술 대상

### 0.1 v5.8.8 까지 *이미 갖춘* 것 (보존 대상)

| 영역 | 현 상태 | 평가 |
|------|---------|------|
| 단일 편집장 (NarrativeComposer Opus) | 2-call Tier 4 작동 | ✅ |
| 문체 거버넌스 | REPORT_STYLE_GUIDE + WRITE-AP 14종 + `_sanitize_symbols` | ✅ |
| 시각 거버넌스 | chart_critic / desk_editor / deterministic_gate (V5) | ✅ |
| 차트 렌더 캡처 | `src/visual/capture.py` (Playwright PNG) | ✅ (Codex 미학 입력 재사용) |
| 시점 앵커링 (발행일↔사건일) | WRITE-AP-11/14 + `timeutil.KST` SSOT | ✅ 부분 |
| 일반 독자 우선 | 평이화 + footnotes (v5.5.5) | ✅ |
| 결정성·재현성 | golden_prompts 회귀 + byte-equal 가드 + patch_report (LLM 0) | ✅ |
| 시장 데이터 | market_fetcher 24종목 (KRX/Yahoo/FRED/ECOS) | ✅ |
| 텔레메트리 패턴 | `src/visual/usage_log.py` (JSONL 적립) | ✅ (critique_log 참조 구현) |

### 0.2 *아직 남은* 11개 결함 (V6 수술 대상 — 2026-06-01 진단)

| ID | 결함 | NVIDIA 보고서 증거 | V6 Phase |
|----|------|--------------------|----------|
| **V6-GAP-1** | 자유 본문에 evidence-binding 미적용. Rule #9 는 Claim 모델에만 작동, 독자가 읽는 `prose` 는 무검증 통과. | 5종 오류 전부의 뿌리 | 2·3 |
| **V6-GAP-2** | 출처 없는 특정 수치를 방치 (confabulation). | "27년 만의 PC 칩" | 2·3·5 |
| **V6-GAP-3** | 수치 scope 미검증 (진짜 숫자를 잘못된 단위에 귀속). | "보드 한 장 130만 부품" (실제 NVL72 *랙*) | 2·3 |
| **V6-GAP-4** | 출처 작성일 ↔ 사건 신규성 미구분. | "GR00T 오늘 상용화" (실제 3/16 기발표) | 2·3·8 |
| **V6-GAP-5** | 시계열·시장 수치에 시점 라벨 부재. | "키노트 직전 211.14" (실제 직전 정규장 종가) | 2·8 |
| **V6-GAP-6** | **fact-critic / 검증 루프 부재 — 본질.** 외부 ChatGPT 가 우리 critic 을 대신함. | 5종이 발행본까지 도달 | **3 (Codex Critic)** |
| **V6-GAP-7** | per-fact provenance 메타 부재 (언제·어느 단위·어느 출처 태그 없음). | GAP-3/4/5 를 프롬프트로만 막음 | **8 (Provenance)** |
| **V6-GAP-8** | 차트 데이터·미학 검수가 Claude-자기점검뿐 (교차검증 부재). | (시각 회귀 누적) | **4 (Codex 미학)** |
| **V6-GAP-9** | OBSERVE 1회성 (근거 빈약 감지·재검색 불가). | 부정확/누락 출처 그대로 하류로 | 5·(백로그) |
| **V6-GAP-10** | MEMORY read-back 부재 (과거 보고서·watchlist 가 추론에 안 먹힘). | 중복 각도·예측 추적 불가 | 백로그 |
| **V6-GAP-11** | orchestration 정적 (복잡도 무관 고정 단계). | 균질한 깊이 | 백로그 |

> **공통 분모.** GAP-1~6 은 *"작성된 사실을 출처와 대조하는 단계 부재"* 로 수렴.
> GAP-6(루프 부재)이 본질, 나머지는 증상. V6 의 심장은 **bounded Codex critic 루프**
> (Phase 3)이며, Phase 2 는 그 루프가 호출 전 명백한 것을 거를 *0-LLM 사전필터* 를,
> Phase 8 은 critic 과 바이라인이 쓸 *provenance 재료* 를 깐다.

### 0.2-b 2차 표본 — 2026-06-03 일일 브리핑 회귀 (외부 Codex 데스크 검수)

NVIDIA(6/1)에 이어, 6/3 06:17 자동 브리핑(`analysis_20260603_061712_3e14fb009f`)이
외부 Codex 데스크 검수에서 받은 결함을 2차 표본으로 박았다. 1차(NVIDIA 5종)가
*사실 정밀도* 문제였다면, 2차는 **시장 데이터 정합성 + 오래된 뉴스 재탕**이 핵심 —
*상품의 존재 이유*(오늘의 시장 브리핑)를 직접 무너뜨리는 더 치명적 범주다.

| 신규 error_class / AP | 결함 | 증거 | 처리 |
|----------------------|------|------|------|
| `market_data_mismatch` ★최우선 | 코스피 8,650.93/-1.6% (실제 8,801.49/+0.15%, 부호 반대) · 원/달러 1,511.95 (실제 1,516.4) · 소스 혼합 | 연합뉴스 종가 | fixture + WRITE-AP-15 + `MarketDataSourceGuard` |
| `stale_sourcing` ★최우선 | Spider's Web(2025-06-01)을 "이틀 전"으로 — 1년 묵은 뉴스를 어젯밤으로 | 출처 작전일 | fixture + ContextAnalyst 최신성 제한 |
| `event_conflation` | 컴퓨텍스 ↔ GTC Taipei 혼동 | 공식 일정 | fixture + WRITE-AP-18 |
| `attribution_as_fact` | 러 국방부 '보복' 주장을 사실로 단정 | Reuters | fixture + WRITE-AP-16 |
| `causal_overreach` | 규제→한국 메모리 '직격탄'(중간단계 생략) | Reuters | fixture + WRITE-AP-17 |
| `metric_label_ambiguity` | '순이익률 71%' (매출총이익률 74.9% 혼동) | NVIDIA IR | fixture |
| CHART-AP-27 | 폭포수 부호 미인코딩 (100+22+12+8+9=151≠117) | 본 차트 | 결정적 `WaterfallCoherenceGuard` |
| CHART-AP-28 | 빈 차트 프레임 (small_multiples 데이터 0) | 본 차트 | 결정적 `EmptyChartGuard` |
| CHART-AP-29 | "코스피 nan%" 노출 | 본 카드 | 결정적 `NaNExposureGuard` |
| WRITE-AP-19~21 | 일방 서사 / 제목·본문 무게 불일치 / 신뢰도% 독자 노출 | 데스크 검수 | 서술 가드 |

> **우선순위 상향(중요).** 이 표본이 드러낸 두 가지를 V6 최상단으로 끌어올린다 —
> ① **시장 데이터 단일 소스·시점 라벨 강제**(WRITE-AP-15, `MarketDataSourceGuard`):
> 시장 수치는 `market_fetcher` time_series 에서만, 결측이면 *생략*(자유서술 confabulation
> 금지). ② **일일 브리핑 검색 최신성 제한**: ContextAnalyst 웹검색을 최근 24~48h 로
> bound — `stale_sourcing` 의 근본 원인. 이 둘은 Codex critic(Phase 3) 이전에, Phase 2
> 결정적 가드 + ContextAnalyst 하드닝으로 *먼저* 잡아야 하는 0-LLM 영역이다.
> CHART-AP-27/28/29 도 동일 — Codex 없이 결정적 가드로 막힌다.

### 0.3 구현 우선순위 — 3-Tier (Codex 중심 재배치)

| Tier | 내용 | 포함 Phase | 정당화 |
|------|------|------------|--------|
| **Tier 0 — 외부 의존 검증** | codex CLI headless 호출·구조화 출력·인증·rate-limit·graceful degrade 를 *먼저* 증명 | Phase 0(완료), 1 | 전 Phase 가 codex 경로에 달림. 안 되면 설계 전면 재고. **최우선 spike.** |
| **Tier 1 — 사실 사전필터 (LLM 0)** | 결정적 가드(Codex 앞단 필터·한도 절약) + composer 프롬프트 하드닝 | Phase 2 | codex 호출 = ChatGPT 한도 소모. 명백한 것은 공짜로 거름. byte-equal 위험 낮음. |
| **Tier 2 — Codex critic 루프 (핵심)** | 검수→Opus 보완→확인패스 (사실+차트데이터), 그다음 미학(vision), 웹verify | Phase 3, 4, 5 | V6 의 심장. Tier 0 가 깔려야 동작. |
| **Tier 3 — 자율 보강 + 신뢰장치** | critique 적립→소프트가드→게이트 승격, provenance, 바이라인 | Phase 6, 7, 8 | 루프가 돌아 verdict 가 흘러야 의미. |
| **백로그 — 확장 agentic** | 반복 OBSERVE / memory read-back / 동적 orchestration | (후속) | Tier 0~3 이 단단해진 뒤. |

핵심: **외부 critic(Tier 2)이 강력해도 호출 경로(Tier 0)가 불확실하면 전부 공중에 뜬다.
Phase 1 codex spike 부터.**

---

## 1. V6 설계 원칙

1. **bounded·guarded 루프만.** 재작성 ≤1, 웹검색 ≤N(기본 3), 확인패스 ≤1. ① 횟수 cap
   ② 결정적 종료조건 ③ 실패 시 결정적 fallback. 무한 자율 금지 (AP-V6-2).
2. **본문 생성·보완은 Claude(Opus) 고정.** anti-pattern 가드가 Opus 실패모드에 튜닝됨.
   Codex 는 *검수·지시*만 하고 본문 텍스트를 직접 쓰지 않는다. 보완은 Codex 지시를
   받아 **Opus** 가 수행 (AP-V6-1, AP-V6-11).
3. **루프 제어는 0 LLM.** "재작성/재검 할까" 판정은 Codex verdict 의 *위반 카운트*
   (결정적). LLM 토큰/한도는 *작업*(검수·보완·웹verify)에서만 (AP-V6-5).
4. **flag OFF = byte-equal.** 모든 신규 행동은 `V6_*` env flag default OFF. 꺼지면
   v5.8.8 호출 경로·출력 byte-equal. golden_prompts 회귀로 강제 (AP-V6-3).
5. **사실 > 문체.** 평이화·생생함(v5.5.5)은 grounding *뒤에*. 출처 없는 생생함은
   과장이다. concreteness 와 fact 충돌 시 fact 가 이긴다.
6. **외부 critic 은 근거를 인용해야 한다.** Codex 의 모든 지적은 *어느 근거/URL 과
   충돌하는지* 명시해야 행동 대상이 된다. 근거 없는 지적은 false-positive 로 보고
   Opus 가 멀쩡한 본문을 망치지 않게 무시 (AP-V6-8).
7. **자율 보강은 적립과 적용을 분리.** Codex verdict 는 자동 적립(안전)하되, live
   SYSTEM_PROMPT/정규 가드로의 편입은 게이트 통과만 (AP-V6-9). 자동은 *log-only
   소프트가드* 까지만.
8. **신뢰장치는 사실에 묶인다.** 바이라인("Opus 작성 / Codex 검수")은 실제 검수가
   *돌았을 때만* 노출. 안 한 검수를 했다고 쓰지 않는다 (AP-V6-10).
9. **append-only 측정.** V6 효과는 `docs/V6_TEST_RESULTS.md` 에 추가만 (AP-V6-6).
10. **외부 의존은 항상 graceful degrade.** codex 부재/인증실패/한도초과/timeout 시
    critic 스킵 → v5.8.8 단일패스로 정상 발행 (market_fetcher 패턴, AP-V6-12).

---

## 2. 요구사항 명세 (REQ-V6-N)

| REQ | 요구사항 | 검증 (테스트 §) | Phase |
|-----|----------|------------------|-------|
| **REQ-V6-1** | 본문 prose 의 정량 주장(숫자·년수·개수·%)은 evidence/웹에 binding 되거나, 안 되면 헤지 또는 drop. | T-1, T-3 | 2, 3 |
| **REQ-V6-2** | 출처에 없는 특정 수치는 결정적 사전필터로 우선 검출, 잔여는 Codex 가 잡음. | T-1, T-3 | 2, 3, 5 |
| **REQ-V6-3** | 정량 주장의 scope(단위·전체/부분) 모호 시 검출. "130만" 단독 금지 → "랙 전체 130만". | T-1, T-3 | 2, 3 |
| **REQ-V6-4** | 출처 작성일 ≠ 사건일이면 "오늘 발표" 류 신규성 단정 차단. | T-2, T-3 | 2, 3, 8 |
| **REQ-V6-5** | 시계열·시장 수치는 시점 라벨 동반("직전 정규장 종가"). "직전 반응" 류 금지. | T-2 | 2, 8 |
| **REQ-V6-6** | **codex CLI headless 호출**: 구조화 verdict(JSON) 수신, 절단 복구, 인증/한도/timeout graceful degrade. | T-C1~C3 | 1 |
| **REQ-V6-7** | **bounded Codex critic 루프**: 검수→Opus 보완(≤1)→Codex 확인패스(≤1), 위반 카운트로 결정적 제어, fallback 발행. | T-3, T-4 | 3 |
| **REQ-V6-8** | Codex verdict 는 **per-claim 구조화 지시**(location/error_class/quote/evidence_conflict/fix_instruction/severity) + 근거·URL 인용. | T-V1 | 1, 3 |
| **REQ-V6-9** | Codex 가 **차트 데이터 정합 + 미학**을 검수(미학은 렌더 PNG 입력). V5 deterministic_gate 는 0-LLM 앞단 필터로 보존. | T-5 | 4 |
| **REQ-V6-10** | Codex **웹 verify**(≤N, budget bound) + 사용 URL 을 verdict 에 명시. | T-6 | 5 |
| **REQ-V6-11** | **자율 보강**: 모든 verdict 를 `critique_log.jsonl` 적립 → 재발 임계 시 log-only 소프트가드 자동화 → 추가 재발 시 게이트 통과로 정규 가드/프롬프트/fixture 편입. | T-7 | 6 |
| **REQ-V6-12** | **바이라인 신뢰장치**: 보고서 말미 "Claude Opus {ver} 작성 / OpenAI Codex 검수" — config SSOT 버전, 검수 실제 수행 시에만 조건부 렌더. | T-8 | 7 |
| **REQ-V6-13** | **per-fact provenance**: ContextAnalysis 각 증거에 source_date/scope_note/source_url (additive, Optional). | T-9 | 8 |
| **REQ-V6-14** | **역할 라우팅**: body=Opus 고정 / critic=Codex / control=0 LLM. 비용 지표 = $ 가 아니라 **ChatGPT/Claude 구독 호출수·한도·지연**. | T-10 | 1, 3 |

---

## 3. Phase 명세

> 모든 Phase: ① flag OFF byte-equal(T-0) 선통과 후 머지 ② 독립 PR ③ 효과는
> V6_TEST_RESULTS append. flag 네임스페이스 `V6_*` (V5 와 분리).

### Phase V6-0 — Baseline + Fact-error Golden Fixtures ✅ (완료, main)
- `tests/regression/fixtures/fact_discipline_scenarios.yaml` — NVIDIA 5종, error_class
  5종 동결: `unsourced_number` / `scope_misattribution` / `novelty_conflation` /
  `timepoint_overclaim` / `list_truncation`. + `test_fact_discipline.py` 스켈레톤.
- **불변 계약**: error_class 5종은 동결. 신규 class 는 Phase 6 게이트 승격으로만 추가.

### Phase V6-1 — Codex CLI 통합 Spike + Verdict 계약 (Tier 0, 최우선) ✅ (완료, 2026-06-03)
**상태**: **DoD 전부 충족.** `src/agents/codex_critic.py` + `src/models.py:FactVerdict`/
`CritiqueClaim` + `Config.codex_*`(`V6_CODEX_CRITIC` default OFF) + 회귀
`test_codex_contract.py`(T-V1) / `test_codex_critic.py`(T-C1/C2/C3, 39 tests pass).
orchestrator 미연결 = flag OFF byte-equal. **VM 실연동 검증 완료** — codex-cli 0.136.0
(gpt-5.5) e2e 검수가 scope_misattribution + unsourced_number 를 정확히 검출
(35.1s, 측정 로그 `docs/V6_TEST_RESULTS.md` §1). stdin 입력·`-o` 클린 캡처·`-i` 비전
지원 확정. 다음 = Phase 2(사전필터) / 3(루프).
**목적**: 전 Phase 가 의존하는 외부 경로를 *먼저* 증명. 여기서 막히면 설계 재고.
- **신규 SSOT**: `src/agents/codex_critic.py` — codex CLI 를 `_call_cli` 패턴으로
  headless 호출(`codex exec` 류, stdin=프롬프트+보고서 JSON+근거, stdout=verdict JSON).
  Claude 쪽 `_repair_truncated_json` 대응물로 codex 출력 절단 복구.
- **계약(Pydantic)**: `src/models.py:FactVerdict` — `claims: list[CritiqueClaim]`,
  각 `{location, error_class, quote, evidence_conflict, source_urls, fix_instruction,
  severity}`. `verdict_status`(clean/violations), `cited_urls`, `model_label`.
- **graceful degrade**: codex 미설치/인증실패/한도초과/timeout → `FactVerdict(skipped=True)`
  → 루프 스킵 → v5.8.8 단일패스 발행.
- **flag**: `V6_CODEX_CRITIC` (전 루프 마스터 스위치, default OFF).
- **VM 검증 항목**(구현 직전, 코드 아님): ① Oracle Ubuntu codex 설치 + ChatGPT
  headless 인증 유지 방식 ② Codex 호출 rate-limit 이 일일브리핑+온디맨드 빈도 감당
  ③ 비대화형 JSON 출력 안정성 ④ 비전(이미지) 입력 지원 여부(Phase 4 의존).
- **DoD**: 모킹된 codex 응답으로 FactVerdict 파싱·절단복구·degrade 3경로 테스트 통과.
  실제 codex 1회 수동 호출 로그 첨부(VM). flag OFF byte-equal.

### Phase V6-2 — Deterministic 사전필터 가드 + 프롬프트 하드닝 (Tier 1, LLM 0) ✅ (완료 2026-06-03)
**상태**: ① 결정적 가드 5종 (`UnsourcedNumberGuard`/`ScopeBarewordGuard`/`NoveltyDeltaGuard`/
`MarketDataSourceGuard`/`NaNExposureGuard`) + `run_fact_guards` + `GuardFlag` + 검수자
페르소나 훅 (`V6_CODEX_PERSONA_PATH`). T-1 결정적 타깃 5종 100%/0-FP. ② 프롬프트 하드닝 —
composer `_FACT_DISCIPLINE_BLOCK`(`V6_FACT_PROMPT`, `_compose_system_prompt()`) +
ContextAnalyst `_RECENCY_BLOCK`(`V6_RECENCY_BOUND`, `_build_system_prompt()`), `test_fact_prompt.py`
6종(OFF byte-equal/ON 주입). 모든 flag default OFF = byte-equal. 의미판단(threshold/FX
sub-tolerance/event/attribution/causal/metric/timepoint 앵커)은 Codex(Phase 3) 라우팅.
**목적**: codex 호출(=한도) 전에 명백한 위반을 0-LLM 으로 거른다.
- **신규 SSOT**: `src/factcheck/deterministic_guards.py` — ① `UnsourcedNumberGuard`
  (본문 "N년 만"·"N개"·"N%" 정규식 → evidence 문자열에 없으면 flag) ② `ScopeBarewordGuard`
  (대형 수치 단독) ③ `TimepointLabelGuard`(시장 수치 인접 시점 라벨 부재) ④
  `NoveltyDeltaGuard`(source_date−publication_date 차이 + "오늘/방금" 인접). `src/visual/`
  대칭 구조.
- **프롬프트**: `narrative_composer.py:SYSTEM_PROMPT` 에 `=== 사실 규율 (V6) ===` 블록
  (`.replace()`, Rule #7) — scope 명시 / 출처없는 특정수치 금지 / 신규성 구분 / 시장
  시점 라벨 / 목록 "대표 몇 + 등". V5 어조 지시와 직교.
- **anti-pattern 카탈로그**: 관측 회귀를 WRITE-AP-N 으로 append (이미 등재: WRITE-AP-15
  시장수치 자유서술 / 16 주장→사실 / 17 인과 과장 / 18 행사 혼동 / 19 일방서사 / 20
  제목·본문 무게 / 21 신뢰도% 노출, CHART-AP-27~29). 신규 발견 시 순차 추가.
- **시장 데이터 가드(최우선)**: `MarketDataSourceGuard` — 본문 시장 수치는 time_series
  단일 소스 ±tolerance 검증, 결측 시 생략. `NaNExposureGuard`(CHART-AP-29).
- **ContextAnalyst 최신성 제한**: 일일 브리핑 웹검색 최근 24~48h bound (`stale_sourcing` 차단).
- **flag**: `V6_FACT_GUARDS`. 초기 **log-only**(WARNING, drop 안 함) → FP 측정 후 enforce 승격.
- **DoD**: fixture 4종(unsourced/scope/timepoint/novelty) ≥90% 검출, FP < 임계.
  프롬프트 변경 후 golden_prompts 회귀 통과.

### Phase V6-3 — Codex Critic Loop: 사실+차트데이터 (Tier 2, **핵심**) ✅ (완료, e2e 수렴 2026-06-03)
**상태**: 루프 코드·orchestrator 연결·착지·회귀 랜딩. `src/factcheck/critic_loop.py`
(`CriticLoop` 제어 0-LLM, 재작성≤1·확인패스≤1, `apply_landing` unsourced drop,
`NarrativeComposerReviser`) + `NarrativeComposer.revise_for_facts`(Opus 보완, AP-V6-1/11,
텍스트-only merge 로 차트 보존) + orchestrator Phase 2.5 flag-gated. 사전필터(Phase 2)→
pre_flags 합류, 재작성 트리거는 Codex 위반에만. T-3/T-4 9종 + 전체 71 pass, flag OFF
byte-equal. **VM e2e 수렴 완료** — 실제 codex(gpt-5.5)+Opus 루프가 NVIDIA 표본 4위반을
보완 1회로 위반 0 수렴 (scope/unsourced/novelty 교정, 측정 `docs/V6_TEST_RESULTS.md §1`).
**남은 것(선택)** = 전체 4층 풀 파이프라인 e2e(웹검색+발행) + degrade 발행 확인 — 배포 단계.
차트 데이터 정합 검수는 codex 프롬프트에 포함(미학은 Phase 4).
**목적**: GAP-6. 확정 루프 `Opus 작성 → Codex 검수 → Opus 보완(≤1) → Codex 확인패스(≤1)`.
- 입력: ComposedReport(prose+차트 data) + ContextAnalysis. Codex 가 사실/문구 + 차트
  *데이터 정합*(차트 숫자 ↔ 본문/근거) 검수, FactVerdict emit.
- **사전필터 합류**: Phase 2 결정적 가드가 먼저 flag → 명백 위반은 codex 토큰 없이
  Opus 보완 지시에 합산.
- **보완 = Opus**: Codex `fix_instruction` 을 받아 Opus 가 해당 섹션 재작성(1회).
  Codex 는 본문을 직접 쓰지 않음 (AP-V6-11).
- **루프 제어 = 0 LLM**: verdict 위반 카운트 → 보완 트리거. 보완 후 확인패스 1회
  (재작성 없음, 검증만). 결정적 종료: 위반 0 또는 cap 소진.
- **착지(확정)**: 확인패스 후 잔존 위반 → **헤지 기본**, `unsourced_number` 만 **drop**
  (Claim validator 사상). 보고서 정상 발행.
- **flag**: `V6_CODEX_CRITIC` (Phase 1 마스터). OFF = 단일패스.
- **DoD**: NVIDIA fixture 5종 e2e → 위반 0/헤지/drop 수렴. 재작성 ≤1, 확인패스 ≤1
  강제 검증. degrade 시 정상 발행. flag OFF byte-equal.

### Phase V6-4 — Codex 미학 검수 (Vision, 렌더 PNG)
**목적**: GAP-8. 차트 데이터뿐 아니라 *미학*까지 Codex 가 본다.
- `src/visual/capture.py` 로 차트→PNG → Codex 비전 입력. verdict 에 차트별 시각 지적
  (가독성/잘림/패턴 충돌 등) + fix_instruction(데이터/타입/축 조정).
- **역할 분리**: V5 `deterministic_gate`(하드 규칙, 0-LLM)는 앞단 보존. V5
  `chart_critic`/`desk_editor`(Claude 미학)와 Codex 미학의 중복은 측정 후 정리 —
  교차검증으로 병행 유지 또는 Codex 로 흡수.
- **전제**: Phase 1 의 codex 비전 입력 지원 확인. 미지원 시 미학은 V5 유지, 본 Phase 보류.
- **flag**: `V6_CODEX_VISUAL`.
- **DoD**: 데이터-불일치 차트 + 미학 결함 차트 fixture 를 검출. flag OFF byte-equal.

### Phase V6-5 — Codex 웹 Verify (bounded)
**목적**: 우리 근거가 불완전해도 ground truth 대조. fact-critic 강화.
- Codex 가 verdict 산출 시 **자체 웹검색 ≤N(기본 3)** 허용 + 사용 URL 을 `cited_urls`
  에 명시. **재현성 포기 허용**(웹 변동) — flag OFF 경로는 byte-equal 유지, ON 만 비결정.
- bound: 검색 횟수 cap + 결정적 종료. URL 미인용 지적은 행동 안 함(AP-V6-8).
- **flag**: `V6_CODEX_WEBVERIFY`.
- **DoD**: 근거에 없는 사실을 웹으로 잡는 시나리오 통과, 검색 cap 준수, URL 인용 100%.

### Phase V6-6 — 자율 보강: critique 적립 → 소프트가드 → 게이트 승격 (Tier 3)
**목적**: "Codex 가 매번 잡는 패턴이 점점 시스템에 누적돼 스스로 강해진다." (사용자 핵심 안)
- **A. 적립(자동·안전)**: 모든 verdict 를 `src/factcheck/critique_log.jsonl` 에
  {error_class, 패턴 시그니처, location, report_id, 날짜}로 영구 적립(usage_log 패턴).
  코드/프롬프트 무변경 = 완전 안전.
- **B-1. 소프트가드 자동화(near-자율)**: 동일 시그니처 재발 ≥임계 → `factcheck/soft_guards.yaml`
  에 자동 등재 → 다음 보고서부터 **log-only/헤지 가드로만** 적용(본문 프롬프트 불변).
  오판이어도 drop 아닌 log/헤지라 피해 제한.
- **B-2. 정식 승격(게이트)**: 추가 재발 시 후보 표면화 → **사람 확인 1줄** 후 정규
  가드/`SYSTEM_PROMPT`/fixture/WRITE-AP·CHART-AP 로 편입(NVIDIA 5종이 fixture 가
  된 것처럼). live 프롬프트/정규 가드 자동 편입 금지 (AP-V6-9, byte-equal·오염 방지).
- **flag**: `V6_CRITIQUE_ACCUMULATION`(적립), `V6_SOFT_GUARDS`(소프트가드 적용).
- **DoD**: 적립 idempotent, 재발 임계 시 소프트가드 자동 등재, 소프트가드가 본문
  프롬프트를 변형하지 않음(byte-equal 본문 프롬프트 가드), 정식 승격은 게이트 필수.

### Phase V6-7 — 바이라인 신뢰장치
**목적**: REQ-V6-12. 독자가 보고서 신뢰도를 가늠하는 출처-검증 라벨.
- `freeform_essay.html` 말미에 "Claude Opus {ver} 작성 / OpenAI Codex 검수 ({n}회)".
  버전은 **config SSOT**(현 composer=Opus 4.7)에서 끌어옴 — 하드코딩 금지.
- **조건부 렌더**: critic 실제 수행 시에만. degrade/skip 시 검수 줄 생략(거짓 신뢰 금지,
  AP-V6-10). ReportBundle verification 척추와 정합.
- **flag**: `V6_BYLINE`.
- **DoD**: 검수 수행/스킵 2경로에서 바이라인 정/부 렌더, 버전 config 연동, 모델 ID
  내부 식별자 비노출.

### Phase V6-8 — Per-fact Provenance in ContextAnalysis
**목적**: GAP-7. 신규성·scope·시점을 *데이터*로 판정 + 바이라인/웹verify 정확도 보강.
- `src/models.py:ContextAnalysis` 증거 항목에 `source_date`/`scope_note`/`source_url`
  (additive, Optional — 구 데이터 호환). DATA_MODELS 갱신. `context_analyst.py:
  SYSTEM_PROMPT` 에 "각 사실에 발표일·단위 명시" 지시. image_fetcher 의 og:published
  재사용 검토(**기술 리스크**: 매체가 실제 제공하는지 사전 검증, 미제공 시 본문 날짜 파싱 대안).
- **flag**: `V6_PROVENANCE`.
- **DoD**: GR00T(3/16)·130만(랙) 케이스가 provenance 로 표현, NoveltyDelta/Scope 가드가
  프롬프트 없이 데이터로 판정. 회귀 테스트.

### 백로그 (Tier 외 — Tier 0~3 안정 후)
- **반복 OBSERVE**(GAP-9): ContextAnalyst 근거 gap 감지 재검색(≤3). `V6_ITER_OBSERVE`.
- **Memory read-back**(GAP-10): 과거 보고서·watchlist 추론 주입. `V6_MEMORY_READBACK`.
  **PII·admin URL·토큰 본문 유입 금지**(AP-V6-7).
- **동적 orchestration**(GAP-11): 복잡도로 루프 횟수 차등. `V6_DYNAMIC_ORCH`.

---

## 4. 상세 테스트 플랜

> **원칙.** ① 모든 Phase 는 *flag OFF byte-equal*(T-0) 선통과 후 머지 (AP-V6-3).
> ② 사실 검증은 `fact_discipline_scenarios.yaml` 단일 fixture SSOT 공유.
> ③ 외부(codex/웹) 의존 테스트는 **모킹 기본**(CI 결정적) + 실연동은 VM 수동 1회.
> ④ 효과 측정은 `docs/V6_TEST_RESULTS.md` append-only.

### 4.1 회귀·계약 (전 Phase 전제)
| ID | 테스트 | Phase | 파일 |
|----|--------|-------|------|
| **T-0** | flag OFF byte-equal — 모든 `V6_*` OFF 시 golden_prompts 출력 v5.8.8 동일 | 전 | `test_v6_byte_equal.py` |
| **T-V1** | FactVerdict 계약 — per-claim 필수필드(location/error_class/quote/evidence_conflict/fix_instruction/severity) + 근거·URL 인용 강제, 누락 시 거부 | 1,3 | `test_codex_contract.py` |

### 4.2 Codex 외부 경로 (모킹 + VM 실연동 1회)
| ID | 테스트 | Phase | 파일 |
|----|--------|-------|------|
| **T-C1** | headless 호출·JSON 파싱·절단복구 (모킹된 codex stdout) | 1 | `test_codex_critic.py` |
| **T-C2** | graceful degrade — codex 미설치/인증실패/한도/timeout 4경로 → skipped verdict → 단일패스 정상 발행 | 1 | `test_codex_critic.py` |
| **T-C3** | rate-limit/지연 측정 hook — 호출수·latency·한도소모 기록 (VM 실연동 수동 1회 + 모킹 단위) | 1 | `test_codex_critic.py` + VM 로그 |

### 4.3 사실 규율 (fixture 기반)
| ID | 테스트 | Phase | 파일 |
|----|--------|-------|------|
| **T-1** | 결정적 사전필터 검출률 — fixture unsourced/scope/timepoint ≥90% flag, FP < 임계 | 2 | `test_fact_discipline.py` |
| **T-2** | provenance 기반 신규성·시점 — GR00T(3/16)·시장 종가 데이터 판정 | 2,8 | `test_fact_discipline.py` |
| **T-3** | Codex critic e2e — NVIDIA 5종이 루프 후 위반 0/헤지/drop 수렴 (모킹 verdict) | 3 | `test_codex_loop.py` |
| **T-4** | 루프 bound — 재작성 ≤1, 확인패스 ≤1, 결정적 종료, fallback 정상 발행 | 3 | `test_codex_loop.py` |

### 4.4 시각·웹·자율보강·신뢰장치
| ID | 테스트 | Phase | 파일 |
|----|--------|-------|------|
| **T-5** | 미학/데이터 검수 — 데이터-불일치 차트 + 미학결함 차트 검출 (모킹 비전 verdict), PNG 렌더 경로 | 4 | `test_codex_visual.py` |
| **T-6** | 웹verify — 검색 cap(≤N) 준수, cited_urls 100%, URL 미인용 지적 무시(FP 가드) | 5 | `test_codex_webverify.py` |
| **T-7** | 자율보강 — critique_log append idempotent, 재발 임계→소프트가드 자동등재, **소프트가드가 본문 프롬프트 byte-equal 유지**, 정식승격 게이트 필수 | 6 | `test_critique_accumulation.py` |
| **T-8** | 바이라인 — 검수 수행→정 렌더 / 스킵→검수줄 생략(거짓신뢰 금지), 버전 config 연동, 내부 모델ID 비노출 | 7 | `test_byline.py` |
| **T-9** | provenance — source_date/scope/url additive, 구 데이터 호환, 미제공 매체 fallback | 8 | `test_provenance.py` |

### 4.5 비용·효과 측정 (append-only)
| ID | 지표 | 기록처 |
|----|------|--------|
| **T-10** | fact-error rate(fixture 기준 발행본 잔존위반/보고서), 루프 평균 횟수, **호출수·한도소모·지연**(토큰 아님 — 구독 정액), Codex FP율, 소프트가드 적중률 | `docs/V6_TEST_RESULTS.md` |

**측정 우선 원칙(중요).** Codex critic/소프트가드/enforce 가드는 모두 **log-only →
측정 → 승격** 순서. 첫 도입 시 아무것도 drop/enforce 하지 않고 텔레메트리만 쌓아
FP·효과를 본 뒤 단계적으로 enforce 로 올린다.

---

## 5. Anti-pattern (V6 누적 — AP-V6-N, append-only)

| AP | 금지 | 가드 |
|----|------|------|
| **AP-V6-1** | 사용자 본문(prose/headline/deck/broadcast) 생성·보완 모델을 Claude Opus 외로 교체 금지 | T-0/T-4 body=Opus 가드 |
| **AP-V6-2** | 무한·무경계 루프 금지 | 재작성≤1·웹검색≤N·확인패스≤1 cap + 결정적 종료 + fallback (T-4) |
| **AP-V6-3** | flag OFF 인데 출력이 v5.8.8 과 달라짐 금지 | T-0 byte-equal, 머지 전제조건 |
| **AP-V6-4** | 출처 없는 특정 수치 emit 금지 | UnsourcedNumberGuard(Phase 2) + Codex(Phase 3) |
| **AP-V6-5** | 루프 *제어*에 LLM 남용 금지 (제어는 결정적 위반 카운트) | control=0 LLM (Phase 3) |
| **AP-V6-6** | V6_TEST_RESULTS 기존 entry 수정 금지 (append-only) | 리뷰 체크 (AP-V5-32 계승) |
| **AP-V6-7** | memory read-back 으로 토큰·admin URL·PII 본문 유입 금지 | 백로그 Phase 검증 |
| **AP-V6-8** | Codex 의 근거/URL 미인용 지적을 행동 대상화 금지 (FP→본문 훼손) | verdict 의 evidence_conflict/source_urls 필수 (T-V1) |
| **AP-V6-9** | critique 적립을 live SYSTEM_PROMPT/정규 가드에 *자동* 편입 금지 (byte-equal 붕괴·프롬프트 오염·FP 영구화) | 자동은 log-only 소프트가드까지, 정식 편입은 게이트 (T-7) |
| **AP-V6-10** | 실제 안 돈 검수를 바이라인에 "검수" 로 표기 금지 | 조건부 렌더 (T-8) |
| **AP-V6-11** | Codex(외부 모델)가 본문 텍스트를 *직접 작성/편집* 금지 (검수·지시만) | 보완은 Opus 가 수행 (T-3) |
| **AP-V6-12** | 외부 의존(codex/웹) 실패가 보고서 발행을 막음 금지 | graceful degrade → 단일패스 (T-C2) |
| **AP-V6-13** | 보완 결과가 *정정 흔적/메타 코멘트* 를 본문에 남김 ('신규 공개 아님 / 사실과 다름 / 출처에 따르면 ~아니다' 류 해명조·부정 박제) — 독자 무가치. 검수는 독자에게 보이지 않아야 함 (2026-06-03 e2e 발견) | `REVISE_SYSTEM_PROMPT` 의 "★ 독자 우선" 블록 — 틀린 주장은 정확한 사실로 자연스럽게 재작성하거나 덜어냄, 부정문 박제 금지 |

회귀 발견 시 본 표에 AP-V6-N append.

---

## 6. 인수 기준 (V6 Definition of Done)

1. NVIDIA GTC fixture 5종 사실오류가 **발행본에서 0 으로 수렴**(위반→grounded/헤지/drop).
2. 모든 `V6_*` flag OFF 에서 golden_prompts 출력 **v5.8.8 byte-equal**(T-0).
3. Codex critic 루프가 **bounded**(재작성≤1·확인패스≤1) + 외부 실패 시 **결정적
   fallback**(단일패스) 정상 발행.
4. 본문 생성·보완은 **항상 Opus**(AP-V6-1/11), 검수는 **Codex**(교차 모델).
5. 자율 보강이 **적립↔적용 분리**(자동 소프트가드 + 게이트 승격, 본문 프롬프트 byte-equal 보존).
6. 바이라인이 **검수 실제 수행 시에만** 노출, 버전 config 연동.
7. WRITE-AP-15/16 + AP-V6-1~12 등록, `docs/V6_TEST_RESULTS.md` 효과(호출수·한도·FP율) 공개.
8. `src/orchestrator.py:VERSION` = `v6.0.0`, 전 문서 `last_synced_with` 갱신, CHANGELOG/
   README 동기화.

---

## 7. V5 와의 관계 (병행 트랙)

V6 는 V5 를 대체하지 않는다. V5 = *시각·분석설계·데이터계약* 트랙(Phase 0~8), V6 =
*사실 grounding + Codex critic 루프* 트랙. 충돌 지점은 두 곳:
- `narrative_composer.py:SYSTEM_PROMPT` — V6 `=== 사실 규율 ===` 블록은 V5 어조·시각
  지시와 *직교* 추가, 두 트랙 변경은 같은 SSOT(REPORT_STYLE_GUIDE +
  REPORT_WRITING_ANTIPATTERNS)에 정합.
- 차트 미학 검수 — V5 `chart_critic`/`desk_editor`/`deterministic_gate` 와 V6 Codex
  미학(Phase 4)이 중첩. deterministic_gate(0-LLM 하드규칙)는 *앞단 필터로 보존*,
  LLM 미학은 측정 후 병행/흡수 결정.

flag 네임스페이스 분리(`V5_*` vs `V6_*`).

---

## 8. 실행 로드맵 (새 세션 진입 순서)

> **이 플랜은 작성 완료(SSOT). 실행은 새 세션에서 Phase별 독립 PR 로.** 이 컨테이너는
> fresh clone(codex·인증·reports 없음)이라 codex 경로 실연동·byte-equal 측정 불가 —
> 실행은 VM 접근 가능한 세션에서.

1. **Phase 1 (codex spike)** 부터 — VM 검증 4항목(설치/인증/한도/비전) 먼저 확인 후
   `codex_critic.py` + FactVerdict 계약 + degrade. 여기서 막히면 전체 재고.
2. Phase 2(사전필터+프롬프트) 는 codex 와 독립이라 **병행 가능**.
3. Phase 3(루프) = 핵심. Phase 1·2 합류 후.
4. Phase 4(미학)·5(웹verify) 는 Phase 3 위에.
5. Phase 6(자율보강)·7(바이라인)·8(provenance) 는 verdict 가 흐른 뒤.
6. 각 Phase: flag default OFF → log-only → 측정(V6_TEST_RESULTS) → enforce 승격.

**미해결 → 새 세션 초입에 재확인:**
- (A) codex CLI 가 VM 에서 실제 headless·구조화출력·구독한도 OK 인지 — Phase 1 spike 가 답.
- (B) codex 비전 입력 지원 — Phase 4 가부 결정.
- (C) 소프트가드 재발 임계값(횟수) + enforce 승격 FP 임계(%) — 측정 후 수치 확정.
