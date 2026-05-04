---
tier: 1
status: proposal
target_version: v5.0.0
based_on_baseline: v4.5.7
depends_on:
  - "src/agents/narrative_composer.py (보존 + 분리)"
  - "src/visual_builder.py (확장)"
  - "src/templates/* (레이아웃 프리미티브 신설)"
  - "samples/chart_map_mono_compare.html (디자인 토큰 SSOT)"
  - "docs/CHART_RENDERING_ANTIPATTERNS.md (Phase 6 의 13 antipattern 매핑)"
proposed_by: external review (외부 리뷰)
last_review: 2026-05-04
---

# REFACTOR V5 — Foundation + Research Direction + Evidence Contract + Editor + Visualization + Desk + Strategic Mode

> **목적.** v4.5.7 (2-call Tier 4 + Editorial Cream/Burgundy Mono + 11-type chart enum + NarrativeComposer 단일 편집장 + 손-짠 D3 차트 렌더러) 의 14개 잔존 결함을 외과적으로 수술한다. 새 아키텍처가 아니라 *기존 자산 위에 부족한 layer 만 추가* 한다.
>
> 본 문서는 외부 검수 (제3 기관) 를 거쳐 *상류 설계 결함* (분석기법 라우팅 부재, 데이터 계약 부재, 평가 하네스 부재, State compounding 비용 누락) 이 *후행 정리 결함* (Editor / DeskEditor 부재) 보다 더 심각하다는 결론에 따라 9개 Phase 를 추가했다 (Phase 0, 0B, 0C, 1A, 2A, 2B, 6A, 7A, 8A). 우선순위가 *상류부터* 로 재배치되었다.
>
> 핵심 작업 8개를 짚어둔다. (1) `docs/CHART_RENDERING_ANTIPATTERNS.md` 의 13개 회귀가 *반응형으로* 누적된 구조를 끝낸다. (2) 신문사 데스크 등급의 *publish/hold/KILL 권한* 을 시스템에 도입한다. (3) **데스크가 원고 (JSON) 와 페이지 프루프 (rendered HTML 스크린샷) 를 모두 보고 판정** 한다 — YK 가 캡쳐로 잡고 있던 시각 결함을 자동화한다. (4) **분석 모드와 별도의 전략 모드 (의사결정 보조)** 를 도입해 사용자의 "X 를 한다고 했을 때 어떤 전략을 취해야 하지?" 형태의 질의를 처방적 보고서로 처리한다. (5) **ResearchDirector 를 Composer 앞에 둬** 분석기법·차트·지도·깊이를 사전 설계한다. (6) **EvidenceDataset 계약을 도입** 해 차트가 prose 부산물이 되지 않게 한다. (7) **SSOT 정합성을 회복** 하고 Golden Prompt 20건 회귀 하네스를 갖춘다. (8) **State compaction** 으로 토큰 compounding 폭주를 차단한다.
>
> **비목적.** archetype/BlockType 회귀를 허용하지 않는다 (v3 폐기 결정을 유지한다). 새 테마를 추가하지 않는다. lens 를 재도입하지 않는다.

---

## 0. 컨텍스트 — v4.5.7 현황과 남은 결함

### 0.1 v4.5.7 까지 *이미 해결된* 것 (보존 대상)

| 영역 | 현 상태 | 평가 |
|------|---------|------|
| 멀티-에이전트 → 단일 편집장으로 전환했다 | NarrativeComposer Opus 4.7 단일 호출이 작동한다 | ✅ |
| 정형 archetype 11종을 폐기했다 | freeform_essay 단일 라우팅으로 이전했다 | ✅ |
| Canvas 손코딩에서 D3 로 이전했다 | d3.v7 + TopoJSON 베이스맵을 사용한다 | ✅ |
| 차트 다양화를 시도했다 | 11 type (donut/bar/line/gantt/network/stacked/bubble/heatmap/dual_line/forecast/choropleth) 을 지원한다 | ⚠ 부분 (open-ended 가 아니다) |
| 시각 톤을 정립했다 | Editorial Cream + Burgundy Mono + Newsreader/IBM Plex 를 채택했다 | ✅ |
| 페르소나 / mode tier 를 도입했다 | recommended_persona + fast/standard/deep 를 운영한다 | ✅ |
| 토큰 효율을 개선했다 | Tier 4 (2-call) + telemetry 를 갖췄다 | ✅ |
| 한국어 톤 가이드를 정비했다 | 평어체 + 진부어 금지 + 외래어 풀이를 적용한다 | ✅ |
| 출처·모순·감시 신호를 정형화했다 | sources / contradictions / watch_signals 를 정형 emit 한다 | ✅ |

### 0.2 *아직 남은* 14개 결함 (V5 수술 대상)

| ID | 결함 | 결과 | V5 단계 |
|----|------|------|---------|
| GAP-1 | **Editor Pass 가 부재한다.** composer 가 분석·작성·편집을 단일 호출에서 모두 수행한다. 자기 글을 자기가 검토하지 못한다. | 같은 모델이 같은 호출에서 쓴 글은 *판에 박힌* 흐름으로 수렴한다. 군더더기 단락과 약한 결론이 잘려 나가지 않는다. | Phase 1 |
| GAP-2 | **차트가 닫힌 enum 으로 갇혀 있다.** 11 type 만 가능하다. 새 type 추가는 `visual_builder.py` 코드 변경이 필요하다. | 사건마다 *최적 시각화* 가 달라야 하는데 11개 안에서 *가장 비슷한* 것을 고를 수밖에 없다. | Phase 2 |
| GAP-3 | **섹션 레이아웃이 균질하다.** 모든 섹션이 동일한 구조를 따른다. 사건별·섹션별 레이아웃 변주가 없다. | 보고서 미적 완성도가 *템플릿* 느낌에 갇힌다. | Phase 3 |
| GAP-4 | **Exhibit 번호제가 부재한다.** "Exhibit 4 참조" 같은 IB 어법을 표현할 수 없다. | 본문 prose 와 차트의 결합도가 약하다. 차트가 *논거의 anchor* 가 되지 못한다. | Phase 4 |
| GAP-5 | **분량 budget 이 mode 단위로만 작동한다.** 섹션별 *어절·문자 수* 목표가 없다. | 분량 비대칭이 만들어지지 않는다. | Phase 5 |
| GAP-6 | **차트 렌더링 신뢰성이 결여되어 있다.** `charts.js` 가 type 마다 별도 손-짠 D3 함수를 갖는다. 13개 회귀가 반응형으로 누적되어 왔다. | 14번째·15번째 antipattern 이 줄을 서서 기다리는 구조이다. | Phase 2 + Phase 6 |
| GAP-7 | **차트-주제 적합도 게이트가 부재한다.** composer 가 "주제 카테고리 → 익숙한 차트" 식의 *선례 오염* 으로 emit 한다. | "주제에 따라 적절하지 않은 보고서에도 무지성으로 박힌다." | Phase 6 |
| GAP-8 | **데스크 등급 시스템 QA 가 부재한다 — 논리·시각 둘 다.** *완성된 보고서 전체* 를 보고 publish/hold/KILL 판정하는 권한이 없다. 어떤 단계도 *실제 렌더된 HTML 을 눈으로 검수* 하지 않는다. | 깨진 채로 발행된다. *YK 가 캡쳐 → 텔레그램 → AI 재작성 → 재배포* 사이클이 발생한다. | Phase 7 + Phase 7A |
| GAP-9 | **보고서가 중간에 끊긴다.** composer max_tokens 가 부족하거나 자체 조기 종료한다. 시스템이 절단을 검출하지 못한다. | 사용자가 직접 "끊겼다" 고 알아채야 한다. | Phase 5 (확장) |
| GAP-10 | **전략 질의 모드가 부재한다.** 사용자의 처방적 질의를 분석 모드로 처리한다. 옵션 enumeration·결정 매트릭스·명시적 권고가 부재하다. | 의사결정 보조용 보고서가 *처방* 이 아니라 *서술* 로 나온다. | Phase 8 + Phase 8A |
| **GAP-11** | **분석기법 라우팅이 부재한다 — 가장 본질적 결함.** Composer 가 ACH·시나리오 트리·전이 채널·이해관계 매트릭스 등의 분석기법을 *암묵적으로* 결정한다. 사용자 질의 → 보고서 형태·분석기법·필요한 시각화를 *사전 설계* 하는 단계가 없다. ContextAnalyst 는 사실 수집만 하고 그 다음이 곧장 작성 단계로 간다. | 사건마다 분석 깊이가 들쭉날쭉하다. *주제에 따라 동적으로 변하는 보고서* 가 못 만들어진다. 사용자가 "이번 사건은 시나리오 트리 + 전이 채널 분석이 어울리는데 그게 안 된다" 같은 회귀를 마주친다. | **Phase 1A (ResearchDirector)** |
| **GAP-12** | **차트 데이터 계약이 부재한다.** 차트가 *prose 의 부산물* 로 만들어진다. composer 가 prose 에 박은 숫자를 VisualPlanner 가 다시 차트로 emit 하는 흐름이다. source_id 가 강제되지 않고, "그럴듯한 숫자" 가 박힌다. | 차트의 데이터가 출처와 분리된다. 분석 신뢰도가 떨어진다. Phase 6 Critic 도 이 결함을 *사후 검증* 만 할 뿐이다. | **Phase 2A (EvidenceDataset)** |
| **GAP-13** | **SSOT 정합성이 깨져 있다.** README 는 v4.5.7 을 가리키고, `src/orchestrator.py:VERSION` 은 v3.0.0 으로 남아있다. `docs/ARCHITECTURE.md` 는 v3 의 7-agent / 11-lens / 11-archetype / 5-gate 구조를 SSOT 처럼 설명한다. 코드와 문서의 기준선이 어긋나 있다. | V5 의 "어디까지 했는가" 를 측정할 baseline 이 없다. 회귀 테스트를 만들 기준점이 없다. *V5 가 v4.5.7 보다 좋아졌는지* 를 증명할 수 없다. | **Phase 0 (Baseline + SSOT)** |
| **GAP-14** | **State compounding 비용이 통제되지 않는다.** 각 LLM 호출이 *raw context 전체* 를 다시 본다. ContextAnalyst 의 출처 원문을 Composer 가 보고, Composer 의 출력을 Editor 가 보면서 또 출처 원문을 보고, DeskEditor 가 다시 모든 것을 본다. 같은 raw context 가 4~5번 토큰으로 환산된다. | V5 의 layer 추가가 비용 폭주로 직결된다. 단순 합산 (제 plan 의 token budget 표) 가 *실제 비용을 과소평가* 한다. | **Phase 0C (State Compaction)** |

위 14개 모두 v4.5.7 의 *상류 설계 부재 + 데이터 계약 부재 + 후행 검증 부재 + 측정 기준 부재 + 비용 통제 부재* 의 5중 결함에서 비롯된다. 한 번 LLM 호출로 분석+편집+레이아웃+분량+시각화를 동시에 결정시키고, 그 결과를 검증 없이 렌더하면서, 완성된 보고서 전체에 reject/kill 권한을 주지 않고, 분석/전략 모드를 분기하지 않으며, *그 위에* 분석기법을 사전 설계하지 않고 차트를 출처와 분리해 만드는 한, 결과는 항상 평균값으로 수렴하며 깨진 차트가 통과하고 신뢰성이 낮은 패키지가 발행된다.

### 0.3 구현 우선순위 — 4-Tier 재배치 (외부 검수 반영)

본 plan 의 가장 큰 변경 사항이다. 기존 Phase 1 → 2 → 3 → ... → 8 의 *순차적* 진입 순서를 외부 검수 반영해 *상류 우선* 4-Tier 로 재배치했다. 핵심 메시지는 단순하다 — *후행 정리 (Editor / DeskEditor) 가 좋아도 상류 (분석 설계 / 데이터 계약 / 측정 기준) 가 약하면 V5 는 v4.5.7 의 누적 회귀를 그대로 반복한다.*

| Tier | 내용 | 포함 Phase | 정당화 |
|------|------|------------|--------|
| **Tier 1 — 토대** | SSOT, 측정 기준, 분석 설계, 데이터 계약, 비용 통제 | Phase 0, 0B, 0C, 1A, 2A | 이게 없으면 다른 layer 의 효과를 *증명할 수 없다*. |
| **Tier 2 — 시각 스택** | Vega-Lite, capability registry, chart gate, exhibit priority, deterministic publish gate | Phase 2, 2B, 6, 6A, 7A | 가장 자주 사용자가 마주치는 결함이다 (13개 antipattern). |
| **Tier 3 — 시스템 QA + 모드 분기** | Desk Editor (Logical + Visual Proof), Strategic Mode + Contract | Phase 7, 8, 8A | 발행 직전 단계. Tier 1·2 가 단단해야 의미 있다. |
| **Tier 4 — 미적 개선** | Editor Pass, Layout Primitives, Exhibit 번호제, Word Budget + 절단 | Phase 1, 3, 4, 5 | 여기까지 와야 v4.5.7 vs V5 의 *읽는 맛* 차이가 생긴다. 단 Tier 1~3 통과 후에만 의미가 있다. |

각 Tier 안에서는 Phase ID 알파벳/숫자 순으로 진행하고, Tier 간 경계에서는 *이전 Tier 가 완전히 운영 검증된 후* 다음 Tier 로 진입한다. 단계 도약을 금지한다 (예: Tier 1 미완성 채로 Tier 3 의 DeskEditor 부터 손대지 않는다).

---

## 1. V5 설계 원칙

### 1.1 핵심 — *역할 분리* (Separation of Concerns) — *신문사 데스크 모델*

v4.5.7 NarrativeComposer 가 짊어진 4가지 책임을 분리. 그 위에 *시스템 QA 권한* 까지:

```
v4.5.7 (현재)                v5.0.0 (목표) — 신문사 편집부 구조
━━━━━━━━━━━━━━━━━━━━━━━     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                              (1) ContextAnalyst        — 사실 수집  | 기자
ContextAnalyst                (2) Composer (Drafting)   — 산문 초고  | 기자
       ↓                      (3) Editor                — 글 비평·재집필 | 카피 에디터
NarrativeComposer             (4) VisualPlanner         — 시각화 spec | 사진 에디터 (지명)
   (분석+편집+               (5) ChartCritic            — 차트 적합도 | 사진 에디터 (검수)
    레이아웃+시각화           (6) LayoutTypesetter      — 섹션 레이아웃 | 레이아웃 디자이너
    동시 결정)                (7) Renderer              — HTML 출력  | 식자
       ↓                      (8) DeskEditor [신설]     — *publish/hold/KILL*  | **데스크 / 매니징 에디터**
   ReportSynthesizer
```

각 단계의 LLM 호출은 *자기 일에만 집중한다*. 다른 단계의 출력을 입력으로 받지만, 자기 책임 영역만 결정한다. **단 DeskEditor 만 예외이다 — 완성된 보고서 전체를 보고 publish/hold/KILL 권한을 행사한다**. 미디어 데스크와 동일한 위계를 따른다.

권한 위계:
- **Revise 권한 (lower editors)**: Editor, ChartCritic, LayoutTypesetter — 자기 영역 안에서 수정·drop. *발행 거부 권한 없음*.
- **KILL 권한 (DeskEditor 단독)**: 전체 보고서를 publish/hold/KILL 판정. KILL 시 발행 자체 거부한다.

### 1.2 비-원칙 (Non-Goals — 이번에 안 하는 것)

- 새 테마 추가 (Editorial Cream + Burgundy Mono 2종으로 **확정·동결**).
- 새 폰트 추가 (Newsreader + IBM Plex Sans KR + IBM Plex Mono 3종으로 확정·동결).
- archetype 을 부활시키지 않는다.
- BlockType 을 부활시키지 않는다.
- lens pool 재활성화 (Tier 4 폐기 결정 유지).
- Sonnet 4.6 이외 모델 를 추가하지 않는다.

### 1.3 보존 원칙 (Preserve Verbatim)

다음은 V5 에서도 **byte-equal 또는 functional-equal** 보존:

- `src/agents/context_analyst.py` — 사실 수집 단계, 그대로 보존한다.
- `src/templates/*.css` 의 design token (`:root` CSS 변수) — `samples/chart_map_mono_compare.html` 의 색·폰트와 정확히 일치해야 함 (§4 참조).
- `src/watchlist/*` — Watchlist Registry 변경하지 않는다.
- `src/telegram_bot.py` — 인터페이스 변경하지 않는다.
- 텔레그램 봇 명령어 (`/status`, `/watchlist`, `?` prefix) — 변경하지 않는다.
- Cloudflare Pages 배포 경로 — 변경하지 않는다.

---

## 2. Phase 0 — Baseline Freeze + SSOT Repair + Golden Evaluation Set

### 2.1 What

V5 의 어떤 코드 변경보다 *먼저* 수행한다. 현재 v4.5.x 의 실제 동작을 *고정* 하고, 문서·코드·테스트의 기준선을 일치시킨다. 본 Phase 가 부재하면 V5 의 "어디까지 해결됐는가" 를 측정할 수 없다.

### 2.2 Why

저장소 점검 결과 다음 SSOT 결함이 확인되었다.

- README 는 v4.5.7 을 현재 상태로 설명한다.
- `src/orchestrator.py:VERSION` 은 v3.0.0 으로 남아 있다.
- `docs/ARCHITECTURE.md` 는 v3.0.0 의 7-agent / 11-lens / 11-archetype / 5-gate 구조를 SSOT 처럼 설명한다.
- README 는 v4.0.0 부터 7-agent / 11-lens / 11-archetype / 5-gate 멀티 파이프라인이 호출 중단되었다고 설명한다.

문서와 코드의 버전 정합성이 깨져 있다. *V5 가 v4.5.7 보다 좋아졌는지* 를 증명할 baseline 자체가 없다.

### 2.3 필수 작업

(가) **버전 SSOT 일치 작업.** 다음 다섯 곳의 버전 표기를 일치시킨다.

- `src/orchestrator.py:VERSION` 을 README 의 현재 버전으로 갱신한다.
- README 의 "Current state" 섹션을 코드와 일치시킨다.
- `CHANGELOG.md` 의 최신 항목과 코드 버전을 일치시킨다.
- `docs/ARCHITECTURE.md` 를 *현재 실제 호출 경로* (v4.5.7 의 2-call Tier 4) 로 재작성한다. v3 의 멀티-에이전트 구조 설명은 *deprecated history* 섹션으로 이동한다.
- `docs/DATA_MODELS.md` 의 모델 정의를 현재 사용 중인 Pydantic 클래스와 일치시킨다.

(나) **실제 호출 경로의 Mermaid 다이어그램 작성.** 현재 v4.5.7 의 ContextAnalyst → NarrativeComposer → Renderer 경로를 단일 다이어그램으로 박는다. v3 잔존 모듈 (player_analyst, dynamics_analyst, scenario_architect 등) 이 *호출되지 않음* 을 명시한다.

(다) **v3 잔존 문서와 v4 실제 경로 분리.** `docs/legacy/` 디렉토리를 신설해 v3 시대의 모든 SSOT 문서를 이전한다. 현재 SSOT 와 historical SSOT 를 명확히 분리한다.

### 2.4 인수 기준 (Phase 0 Acceptance)

- 문서·코드 버전 불일치가 0건이어야 한다.
- 실제 실행 경로와 문서 설명 불일치가 0건이어야 한다.
- v3 잔존 SSOT 문서가 모두 `docs/legacy/` 로 이전되어야 한다.
- README, ARCHITECTURE, DATA_MODELS, CHANGELOG, CLAUDE.md 가 한 자리에서 v4.5.x 의 동일한 baseline 을 가리켜야 한다.

---

## 3. Phase 0B — Golden Evaluation Harness

### 3.1 What

V5 의 모든 후속 변경이 *성공인지 실패인지* 를 결정적으로 판정할 수 있는 회귀 테스트 프레임워크를 구축한다. 사용자 보고를 기다리지 않고 *배포 전* 에 V5 가 v4.5.x 보다 좋아졌는지를 측정한다.

### 3.2 Why

기존 `docs/TESTING.md` 는 py_compile 과 휴리스틱 단위 테스트 18개에 의존한다. 시각·레이아웃·보고서 완결성을 검증하지 못한다. V5 의 핵심 실패는 모두 이 영역에서 발생한다. *사용자가 발견하면 이미 늦다.*

### 3.3 Golden Prompt Set — 20건

다음 8개 카테고리에서 각 2~3건씩 총 20건의 prompt 를 수동으로 작성하고 fixture 로 박는다.

| 카테고리 | 건수 | 예시 |
|---------|------|------|
| 지정학 예측형 | 3 | "이스라엘-이란 직접 충돌 가능성을 다음 6개월 시각으로 분석" |
| 금융·시장 전이형 | 3 | "엔 캐리 unwind 가 KOSPI 200 옵션 변동성에 미치는 전이 채널 분석" |
| 기술·AI 구조분석형 | 3 | "Claude 4.7 출시가 LG에너지솔루션 c-DN 시뮬레이션 통합에 갖는 함의" |
| 정책·규제 의사결정형 | 2 | "EU AI Act 의 high-risk 분류가 우리 회사 LLM 도입에 미치는 영향" |
| 전략 질의형 (Phase 8 검증) | 3 | "Mac Studio M3 Ultra 256GB 도입 시 비용·성능·확장성을 고려한 전략" |
| 지도 필수형 | 2 | "호르무즈 해협 봉쇄 시 한국 LNG·원유 공급망 영향 (지도 포함)" |
| 차트 불필요형 | 2 | "윤리학적 관점에서 LLM 의 의사결정 보조의 한계" |
| 긴 deep 보고서 절단 재현형 | 2 | "지난 5년 미중 반도체 갈등 전체 흐름과 향후 시나리오 분석 (deep)" |

각 prompt 에 대해 v4.5.x 산출물 (HTML, screenshots, telemetry) 을 fixture 로 저장한다. V5 의 각 Phase 가 도입될 때마다 동일 prompt 로 재실행해 변화를 측정한다.

### 3.4 회귀 테스트 5종

(가) **Golden Prompt Regression.** 20개 prompt 의 expected report mode, expected section count range, required evidence types, forbidden chart types, required map behavior 를 fixture 로 박는다. V5 변경이 expected 와 어긋나면 실패다.

(나) **Visual Regression.** Playwright 로 desktop / mobile / exhibit closeup screenshot 을 캡쳐한 뒤 pixel diff 로 비교한다. chart bbox overflow, horizontal overflow 도 함께 검증한다. baseline 은 v4.5.x screenshot 이고, V5 가 의도적으로 더 좋아진 부분만 baseline 갱신한다.

(다) **Semantic Regression.** headline-body 정합, deck-conclusion 정합, evidence-claim coverage, source freshness, contradiction preservation, watch signal actionability 를 정량화해 점수로 측정한다.

(라) **Cost Regression.** total input/output tokens, LLM call count, elapsed time, retry count, hold/kill rate 를 매 실행마다 측정한다. v4.5.x 대비 토큰 폭주 (>2배) 시 fail.

(마) **Report Completeness Regression.** total chars by mode, section target vs actual, closing 존재 여부, unresolved placeholder count, JSON truncation 검출. GAP-9 (보고서 절단) 의 회귀 사례를 자동으로 잡는다.

### 3.5 인수 기준 (Phase 0B Acceptance)

- 20개 Golden Prompt 가 모두 fixture 로 저장되어야 한다.
- 5종 회귀 테스트가 모두 자동으로 실행 가능해야 한다 (CI 또는 로컬 스크립트).
- v4.5.x baseline 의 회귀 테스트 통과율이 측정되어 박혀 있어야 한다.
- V5 의 각 Phase 진입 시 본 회귀 테스트 통과 여부가 *진입 전제 조건* 이어야 한다.

---

## 4. Phase 0C — Pipeline State Compaction

### 4.1 What

각 LLM 호출이 *자기 책임에 필요한 압축 state 만* 받도록 한다. raw context 가 4~5단계에 중복 입력되어 token compounding 폭주가 일어나는 결함을 차단한다.

### 4.2 Why — 단순 합산은 거짓말이다

기존 token budget 표는 각 단계의 토큰 비용을 단순 합산했다. 실제로는 *같은 raw context 가 여러 단계에서 다시 입력* 된다.

```
v4.5.7 의 실제 token flow (압축 없음):
ContextAnalyst (raw sources ~50KB) → 출력 (10KB)
NarrativeComposer (raw sources 50KB + ContextAnalyst 출력 10KB) → 출력 (~30KB)
Editor (가상): raw 50KB + Composer 30KB → ...
DeskEditor (가상): raw 50KB + Composer 30KB + Editor 출력 ...

raw 50KB 가 4번 입력되어 200KB 가 토큰으로 환산된다 (실제 답변 분량과 무관).
```

V5 의 layer 추가가 *비용 폭주* 로 직결된다.

### 4.3 6-tier State 계층

각 단계 사이를 잇는 압축 state 를 정의한다.

```python
class RawContext(BaseModel):
    """1단계 — 원문, 검색결과, 출처. ContextAnalyst 가 입력으로 받고 폐기한다.
    이후 단계에서 *원문 그대로* 다시 보지 못한다."""
    raw_sources: list[RawSource]
    search_results: list[SearchHit]
    user_request: str

class EvidencePack(BaseModel):
    """2단계 — ContextAnalyst 의 압축 출력. 다음 단계가 받는다."""
    claims: list[Claim]              # claim + source_id + quote/data + timestamp + reliability
    actors: list[Actor]
    timeline: list[TimelineEvent]
    contradictions: list[Contradiction]

class AnalysisBrief(BaseModel):
    """3단계 — ResearchDirector 의 출력 (Phase 1A 참조).
    Composer 가 받는다. EvidencePack 의 모든 정보가 *추출되어* 들어가지 않는다."""
    thesis: str
    primary_question: str
    secondary_questions: list[str]
    selected_methods: list[AnalysisMethod]
    report_shape: ReportShape
    visual_constraints: VisualConstraints
    key_numbers: list[KeyNumber]      # composer prose 가 인용할 수 있는 핵심 숫자
    actors_summary: list[str]         # 5~10개 행위자 한 줄 요약

class DraftReport(BaseModel):
    """4단계 — Composer 출력. Editor 가 받는다.
    EvidencePack / RawContext 를 *다시 보지 않는다*."""
    headline: str
    deck: str
    sections: list[ComposedSection]
    closing: str

class ExhibitPack(BaseModel):
    """5단계 — VisualPlanner 출력. Renderer 가 받는다.
    EvidenceDataset 별로 chart spec 이 정렬되어 있다 (Phase 2A 참조)."""
    datasets: list[EvidenceDataset]   # source_id 강제
    chart_specs: list[VegaLiteSpec]   # Phase 2 참조
    layouts: list[LayoutAssignment]   # Phase 3 참조

class PublishManifest(BaseModel):
    """6단계 — Renderer 출력. DeskEditor 가 받는다.
    렌더된 HTML path + 스크린샷 + quality score."""
    rendered_html_path: str
    screenshots: list[ScreenshotCapture]
    chart_gate_results: dict
    issues: list[str]
```

### 4.4 각 LLM 호출의 입력 제한 — 강제 규칙

| LLM 호출 | 받는 state | 받지 못하는 state |
|----------|-----------|-------------------|
| ContextAnalyst | RawContext | — |
| ResearchDirector (Phase 1A) | EvidencePack + user_request | RawContext |
| Composer | AnalysisBrief + EvidencePack 의 *압축 요약* | RawContext, 출처 원문 전체 |
| VisualPlanner (Phase 2) | DraftReport + EvidenceDataset[] + visual_constraints | RawContext, raw web snippets |
| Editor (Phase 1) | DraftReport + AnalysisBrief 의 thesis/critique 만 | RawContext, EvidencePack 전체 |
| LayoutTypesetter (Phase 3) | DraftReport + ExhibitPack | RawContext, EvidencePack |
| ChartCritic (Phase 6 Gate B) | 단일 chart spec + 인접 prose + thesis | 다른 차트, RawContext |
| DeskEditor (Phase 7) | PublishManifest + DraftReport (final) + screenshots | RawContext, raw EvidencePack |

각 호출이 자기 책임에 필요한 *최소한의 state* 만 받는다. raw context 의 중복 입력을 차단한다.

### 4.5 인수 기준 (Phase 0C Acceptance)

- 6-tier State 모델이 `src/state/` 모듈에 정의되어야 한다.
- 각 LLM 호출의 입력이 명시된 state 외 다른 것을 받으면 회귀 테스트가 fail 해야 한다.
- v4.5.x 와 동일 prompt 에서 V5 의 총 입력 토큰이 *압축 적용 전 단순 합산 대비 30% 이상 감소* 해야 한다.
- 응답 정확도 (Golden Prompt 회귀) 가 압축으로 인해 떨어지지 않아야 한다.

---

## 5. Phase 1 — Editor Pass (단일 가장 큰 변경)

### 2.1 What

NarrativeComposer 단일 호출 → **Drafting + Editing 2 호출**.

```
ContextAnalysis
     ↓
Composer.draft()        ← 기존 NarrativeComposer 의 prose-only 책임. 차트/레이아웃 결정 X.
     ↓
DraftReport
     ↓
Editor.critique_and_revise()  [신설]   ← 같은 Opus 4.7. 다른 system prompt.
     ↓
EditedReport
     ↓
VisualPlanner / LayoutTypesetter  (Phase 2~3)
     ↓
ComposedReport (최종)
```

### 2.2 Why

- 같은 LLM 도 *editor 페르소나로 다시 들어가면* 자기 글의 약점을 본다 (다수 IB 워크플로우의 시니어 리뷰 패턴).
- 작성 중에는 *생산* 모드, 편집 중에는 *축약/날카롭게* 모드 — 인지 경제를 분리한다.
- 토큰: composer 1회 + editor 1회 = 약 30~40K (deep 기준). 현 단일 호출 32K 와 거의 동일. *증분 비용 거의 없음*.

### 2.3 How — 새 모듈 `src/agents/editor.py`

```python
class Editor:
    """Drafting → Editing 2단계의 두 번째. composer 의 산문을 비평하고 재집필한다.

    Editor 는 composer 와 *동일한* Opus 4.7 모델. 시스템 프롬프트만 다르다.
    """
    EDITOR_MODEL: str = "claude-opus-4-7"
    MAX_TOKENS: int = 16000  # 편집은 보통 분량 *유지 또는 축소*. 32K 불필요.

    async def critique_and_revise(
        self,
        draft: DraftReport,
        context: ContextAnalysis,
        mode: str = "standard",
    ) -> EditedReport:
        """3단계 응답 emit:
        1. critique: 섹션별 결함 진단 (군더더기 / 결론 약함 / 모순 봉합 / 분량 부적합)
        2. revisions: 섹션별 rewrite (full or partial). 잘라낼 섹션은 명시적 cut.
        3. final: critique 가 적용된 재집필본이다.
        """
```

### 2.4 Editor 시스템 프롬프트 — 핵심 7개 rubric

Editor 는 다음 7개 항목을 점수화 + 수정 (각 항목당 1줄 critique + 수정 지시):

```
1. 군더더기 (Padding)
   - 같은 결론을 다른 표현으로 두 번 말하는가
   - "주목할 만한 점은", "결론적으로" 같은 진부어가 살아있는가
   - 한 단락이 두 주장을 섞고 있는가
   → 잘라낼 문장과 단락을 명시한다.

2. 결론의 칼날 (Punch)
   - 각 섹션 마지막 문장이 *결론* 인가 *요약* 인가
   - 섹션이 끝났을 때 독자가 "그래서?" 라고 묻게 하는가
   → 결론 문장을 재집필한다.

3. 모순 봉합 여부 (Anti-pattern #5)
   - contradictions 가 본문에서 *대립* 으로 살아있는가, *둘 다 맞다* 식 봉합인가
   - 어느 쪽 손을 들었는지 명시되었는가
   → 봉합되었으면 분리해 날카롭게 다듬는다.

4. 차트-본문 결합도 (Chart-Prose Binding)
   - 차트 직전 단락이 thesis 한 줄을 미리 제시하는가
   - 차트 직후 단락이 패턴을 한 단계 *해석* 하는가 (반복 X)
   - 차트가 본문 흐름 *없이* 단독으로 박혀있는가
   → 결합이 약하면 본문 단락을 신설하거나 재작성한다.

5. 분량 비대칭 (Length Asymmetry)
   - 결정적 섹션이 보조 섹션보다 *충분히 긴가*
   - 균질 분포 (모든 섹션이 비슷한 길이) 면 *감점*
   → 짧게 할 섹션과 길게 할 섹션을 명시한다.

6. 신선함 (Originality)
   - 일반 뉴스 readout 으로도 도출 가능한 결론만 있는가
   - 특정 데이터·메커니즘에서만 나오는 *독자적* 통찰이 있는가
   - "공식 narrative 의 빈틈" 을 짚었는가
   → 평범한 결론이 박힌 섹션은 더 깊이 파거나 잘라낸다.

7. 외래어 / 전문용어 풀이 (Vocabulary Discipline)
   - 영어 약어·외래어 첫 등장 시 한 줄 풀이가 있는가
   - 학부생이 막힘없이 읽을 수 있는가
   → 막히는 지점에 풀이를 신설한다.
```

### 2.5 응답 형식

```json
{
  "critique": [
    {
      "section_idx": 0,
      "scores": { "padding": 7, "punch": 5, "contradiction": 9, "binding": 6, "asymmetry": "(전체 평가)", "originality": 6, "vocabulary": 8 },
      "issues": [
        "결론 문장이 사실 재진술. '~이 강화될 것' → '~을 6월 FOMC 까지 못 박을 가능성 70%' 로 구체화 필요",
        "단락 3 의 '주목할 만한 점은' 진부어 제거"
      ],
      "actions": ["rewrite_paragraph_3", "sharpen_conclusion"]
    },
    ...
  ],
  "revisions": [
    {
      "section_idx": 0,
      "action": "rewrite",
      "new_heading": "...",
      "new_kicker": "...",
      "new_prose": "...",
      "cuts": ["문단 5 통째로 삭제 (섹션 2 와 중복)"]
    },
    ...
  ],
  "final": {
    "headline": "...",
    "deck": "...",
    "sections": [...],   // critique 적용된 재집필 — DraftReport 와 동일 스키마
    ...
  }
}
```

### 2.6 인수 기준 (Phase 1 Acceptance)

- Editor 호출이 추가되어 *2-call → 3-call* 로 변경 (Context → Compose → Edit).
- Editor 호출 실패 시 graceful fallback — DraftReport 를 그대로 ComposedReport 로 사용 + telemetry 에 `editor_skipped` 를 기록한다.
- `samples/` 에 같은 사건의 (1) draft 단독 (2) draft + editor 비교 페이지 를 추가하지 않는다.
- Editor 의 7-rubric critique 가 telemetry 에 INFO 로그로 남긴다.
- 회귀 테스트: 기존 사건 5건 재실행, watch_signal 개수·contradictions 개수 를 동일하게 유지한다.

---

## 6. Phase 1A — Research Director / Method Router (가장 본질적 추가)

### 6.1 What

사용자 질의를 받자마자 *보고서 유형, 분석기법, 필요한 데이터, 필요한 시각화* 를 사전 설계하는 별도 LLM 단계를 신설한다. Composer 는 이 설계도를 받아 *초고만* 작성한다. 본 Phase 가 V5 의 가장 본질적 변화이다.

### 6.2 Why

본 plan 의 다른 모든 Phase 는 *Composer 이후* 의 정리 작업이다. Composer 가 분석기법을 *암묵적으로* 결정하는 한, 후행 정리는 한계가 명확하다. 사건마다 분석 깊이가 들쭉날쭉하고, 주제에 따라 동적으로 변하는 보고서를 만들지 못한다. v4.5.7 의 ContextAnalyst 는 사실 수집만 하고 그 다음이 곧장 작성으로 간다. 그 사이에 *분석 설계* 가 있어야 한다.

신문사 비유를 다시 쓰면, 데스크 편집자는 *기자에게 취재 방향과 관점을 미리 지시* 한다. 기자가 일단 쓴 다음 데스크가 고치는 게 아니다. ResearchDirector 가 *기사 데스크의 사전 지시* 역할이다.

### 6.3 모듈 — `src/agents/research_director.py`

```python
class ResearchDirector:
    """사용자 질의 + ContextAnalysis 를 받아 보고서의 분석 설계도를 작성한다.

    Composer 가 받는 AnalysisBrief 의 골격을 결정한다.
    """
    DIRECTOR_MODEL: str = "claude-opus-4-7"  # 분석기법 선택은 Opus 의 capability 영역
    MAX_TOKENS: int = 6000

    async def design(
        self,
        user_request: str,
        evidence_pack: EvidencePack,
        mode: str,
        user_intent: str,
    ) -> AnalysisBrief:
        ...

class AnalysisBrief(BaseModel):
    report_mode: Literal["situation", "forecast", "strategy", "technical", "market", "policy"]
    primary_question: str               # 사용자 질의를 분석 가능 형태로 재기술
    secondary_questions: list[str]      # 답을 도출하려면 함께 풀어야 할 부속 질문
    selected_methods: list[AnalysisMethod]
    report_shape: ReportShape
    visual_constraints: VisualConstraints
    strategic_hint: bool                # Phase 8 라우팅 신호

class AnalysisMethod(BaseModel):
    method: Literal[
        "ACH",                    # Analysis of Competing Hypotheses (가설 경쟁 분석)
        "scenario_tree",          # 분기 시나리오 트리
        "transmission_channel",   # 전이 채널 분석 (금융·정책 영향 추적)
        "stakeholder_matrix",     # 이해관계자 매트릭스
        "fault_tree",             # 결함 트리 (시스템 실패 분석)
        "decision_matrix",        # 결정 매트릭스 (Phase 8 전략 모드 핵심)
        "pre_mortem",             # 사전 부검 (실패 시나리오 역추적)
        "transmission_timeline",  # 전이 타임라인 (사건 → 결과 시계열 추적)
        "comparative",            # 비교 분석 (vs 과거·동종)
    ]
    why_this_method: str          # 1~2문장 정당화
    required_evidence: list[str]  # 이 기법이 요구하는 증거 종류
    forbidden_visuals: list[str]  # 이 기법에 부적합한 차트 type
    required_exhibits: list[str]  # 이 기법이 요구하는 시각화 종류

class ReportShape(BaseModel):
    section_count: int            # 3~7
    peak_section: int             # 0-indexed. 가장 분량이 큰 섹션 위치
    must_have_sections: list[str] # 예: ["situation", "mechanism", "scenarios", "watch"]
    optional_sections: list[str]

class VisualConstraints(BaseModel):
    must_have: list[str]          # 예: ["map_horn_of_africa", "transmission_diagram"]
    allowed: list[str]
    forbidden: list[str]
```

### 6.4 ResearchDirector 의 system prompt — 핵심 지시

```
당신은 데스크 편집자이자 분석 설계자다. 사용자 질의를 받았을 때 *기자가 글을
쓰기 전에* 다음을 결정한다.

1. 보고서 유형 — 이건 상황 보고인가, 예측인가, 전략 보조인가, 기술 분석인가,
                시장 분석인가, 정책 분석인가.
2. 분석기법 — 이 사건을 풀기에 *가장 적합한* 기법을 1~3개 선정한다.
              ACH·시나리오 트리·전이 채널·이해관계 매트릭스·결정 매트릭스·
              Pre-mortem·전이 타임라인·비교 분석 중에서 고른다.
              왜 이 기법인지 1~2문장으로 정당화한다.
3. 필수 증거 — 이 기법이 *반드시 요구하는* 데이터 종류를 명시한다.
4. 시각화 제약 — 이 사건에 *반드시 들어가야 할* 시각화, *허용되는* 시각화,
                *금지되는* 시각화를 명시한다.
5. 보고서 형태 — 섹션 수 (3~7), peak 섹션 위치, 필수 섹션 라벨.
6. 전략 모드 신호 — 사용자 질의가 처방적이면 strategic_hint=true.

원칙:
- *모든 사건에 같은 분석기법* 을 적용하지 않는다. 사건마다 적합한 기법이 다르다.
- 호르무즈 봉쇄는 *전이 채널 분석* + *시나리오 트리* 가 어울린다.
- LLM 도입 결정은 *결정 매트릭스* + *Pre-mortem* 이 어울린다.
- 미중 반도체 갈등은 *비교 분석* + *전이 타임라인* 이 어울린다.
- 분석기법 선택을 *기록* 으로 남긴다 (`why_this_method`). 후속 단계가 이 근거를 본다.
```

### 6.5 Composer 와의 인터페이스 변경

기존 `NarrativeComposer` 의 system prompt 가 자체적으로 결정하던 다음 항목을 ResearchDirector 가 미리 결정한 *AnalysisBrief* 로 받는다.

- 섹션 수와 순서 → `report_shape.section_count`, `must_have_sections`
- 분석 깊이 → `selected_methods` 의 기법 명시
- 차트 결정 → `visual_constraints.must_have` (Phase 2 의 VisualPlanner 가 이를 받는다)
- 페르소나 (현재 `recommended_persona` 와 통합) → ResearchDirector 가 method + persona 함께 결정

Composer 의 system prompt 는 *축소* 된다. *어떤 기법으로 무엇을 분석할지* 는 더 이상 Composer 가 결정하지 않는다.

### 6.6 인수 기준 (Phase 1A Acceptance)

- ResearchDirector 가 모든 사건에 대해 AnalysisBrief 를 emit 해야 한다.
- 동일 사건에 대해 ResearchDirector 가 *다른 분석기법* 을 선택한 사례가 사용자 retrospective 에 의해 검증되어야 한다 (예: 호르무즈 봉쇄에 *전이 채널* 을 선택, c-DN simulation 결정에 *결정 매트릭스* 를 선택).
- AnalysisBrief 의 `selected_methods` 가 보고서 prose 의 *실제 분석 형태* 와 일치해야 한다 (Phase 7 DeskEditor 가 이 일치성을 검증한다).
- Golden Prompt 20건의 expected method 와 ResearchDirector 의 실제 선택이 ≥ 80% 일치해야 한다.

---

## 7. Phase 2 — Visualization Decoupling + Open-Ended Charts

### 3.1 What

차트 결정을 composer 에서 떼어내 **VisualPlanner** 라는 별도 단계로 이전한다. 동시에 **Vega-Lite spec emit** 으로 닫힌 enum 을 폐기한다.

### 3.2 Why

- composer 가 prose 를 쓰면서 *동시에* 차트 type·데이터·annotation 결정하면, 차트 결정이 prose 의 thesis 에 종속됨. 반대로 prose 가 차트를 의식해서 좁게 쓰임. 양쪽 모두 약화된다.
- VisualPlanner 가 *완성된 prose 를 읽고* 시각화를 결정하면, 차트가 *논거를 강화하는 도구* 로 위치가 정립된다.
- Vega-Lite 는 LLM 이 이미 잘 아는 표준. 새 차트 type 추가에 코드 변경이 불필요하다.

### 3.3 How — 새 모듈 `src/agents/visual_planner.py`

```python
class VisualPlanner:
    """완성된 prose + ContextAnalysis → 차트 spec list.

    composer 의 산문을 읽고, 각 섹션에 대해:
    - 차트가 필요한가 (필요 없으면 emit X — 사건당 0~3개 적당)
    - 어떤 시각화 유형이 *논거를 가장 강화* 하는가
    - 어느 단락 직후에 박을 것인가 (anchor_paragraph_idx)
    - Vega-Lite spec 으로 emit
    """
    PLANNER_MODEL: str = "claude-opus-4-7"
    MAX_TOKENS: int = 12000
```

### 3.4 차트 enum 폐기 — Vega-Lite Adapter

`src/visual_builder.py` 의 `_render_donut`, `_render_bar`, `_render_gantt` 등 11개 함수 전부 폐기. 단일 어댑터로 통일:

```python
# src/visual_builder.py (V5)

def render_vega_lite(spec: dict, theme: str) -> str:
    """Vega-Lite JSON spec → SVG (server-side rendering).

    의존성: vega-cli (npm) 또는 vl-convert-python.
    theme 매개로 색·폰트·배경 일괄 주입 (composer 가 색 결정 X).
    """
```

VisualPlanner 가 emit 할 spec 예시:

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "title": { "text": "원유 vs 환율 30일 동조", "subtitle": "Bloomberg, 2026-04 / N=30" },
  "width": 560, "height": 280,
  "data": { "values": [{"day":1,"oil":66,"krw":1340}, ...] },
  "encoding": {
    "x": { "field": "day", "type": "quantitative", "title": "" },
    "y": { "field": "oil", "type": "quantitative", "title": "Brent ($/bbl)" }
  },
  "layer": [...],
  "config": {
    "$ref": "#/definitions/v5_theme_editorial"
  }
}
```

### 3.5 색·폰트 강제 — `_apply_v5_theme(spec, theme_name)`

LLM 이 차트 spec 에 색을 *결정하지 못하게* 차단. `render_vega_lite()` 진입 시점에 무조건 V5 design token 으로 덮어씀 (§4 참조). 이는 anti-pattern 이 아니라 *디자인 무결성 보호*.

### 3.6 차트 종류 — 무제한 (단 mono guide 준수)

V5 에서 emit 가능한 시각화 (Vega-Lite spec 으로 표현 가능한 것 모두):
- 기존 11종 + Sankey, Chord, Treemap, Streamgraph, Parallel Coordinates, Slope chart, Bump chart, Calendar heatmap, Radar/Spider, Bullet chart, Waterfall, Funnel, Density plot, Boxplot, Violin, Scatterplot matrix, Lollipop, Beeswarm 등을 사용한다.
- *단* mono 톤 + 45° 패턴 + 단일 액센트 규칙은 강제 (§4).
- 이모지·색깔 점 마커 를 금지한다.

### 3.7 Antipattern 자동 해결 매핑 (왜 Vega-Lite 인가)

`docs/CHART_RENDERING_ANTIPATTERNS.md` 의 13개 회귀 중 라이브러리 교체만으로 *자동 해결* 되는 항목과 추가 가드 (Phase 6) 가 필요한 항목 분리:

| AP-N | 증상 | Vega-Lite 자동 해결 | Phase 6 추가 가드 필요 |
|------|------|---------------------|------------------------|
| AP-1 | category/group 시각 분리 미적용 | ✅ `color: {field: "group"}` 인코딩 | — |
| AP-2 | 반복 라벨 시각 일관성 깨짐 | ✅ scale 안정성 보장 | — |
| AP-3 | 음수/0/극단값 robust 처리 누락 | ✅ 도메인 자동 감지 | ✅ schema 가드 (NaN/inf 차단) |
| AP-4 | aspect-ratio vs viewBox 충돌 | ✅ explicit width/height | — |
| AP-5 | 라벨 zone 밖 잘림 | ⚠ 자동 회전·축약 *부분* | ✅ visual sanity check (bbox) |
| AP-6 | annotation 충돌·겹침 | ⚠ 축 라벨 overlap detection 만 | ✅ visual sanity check |
| AP-7 | 빈 데이터 차트 emit | — | ✅ schema 가드 (data 길이 검증) |
| **AP-8** | **차트 type 사건과 부적합** | — | ✅ **Critic (LLM) 단독** |
| AP-9 | 지도 zoom/center 디폴트 | ✅ projection 자동 bounds | — |
| AP-10 | 지도 마커 라벨 충돌 | ⚠ 라벨 emit 만 자동, 충돌 X | ✅ visual sanity check |
| AP-11 | 차트 카드 배경 하드코딩 | ✅ theme config 강제 적용 | — |
| AP-12 | bubble 스케일 고정 | ✅ extent 자동 감지 | ✅ schema 가드 (finite 범위) |
| AP-13 | gantt 시간축 누락 | ✅ axis 자동 생성 | — |
| AP-14 | 보고서와 무관한 지리 annotation | — | ✅ **Critic (LLM) 단독** |

**Vega-Lite 단독으로 해결**: 8개 (AP-1, 2, 3, 4, 9, 11, 12, 13).
**Vega-Lite + Phase 6 visual check**: 3개 (AP-5, 6, 10).
**Phase 6 Critic 단독**으로 처리하는 항목은 2개 (AP-8, AP-14) 이다. *판단* 영역이라 라이브러리가 다루지 못한다.

즉 라이브러리 교체로 13개 중 11개가 자동 또는 시각 검증으로 해결된다. 남은 2개 (chart type 적합도 + 무관 annotation) 는 §7 Phase 6 의 LLM Critic 이 책임진다.

### 3.8 인수 기준 (Phase 2 Acceptance)

- `src/visual_builder.py` 의 11개 type-specific 함수 폐기, `render_vega_lite()` 단일 어댑터로 로 대체한다.
- VisualPlanner 가 prose 를 읽고 *최소 1종 새 차트 type* (예: Sankey 또는 Treemap) 을 사건에 맞게 emit 하는 사례 1건 demo.
- Editor → VisualPlanner 호출 순서 (편집된 prose 위에서 시각화 결정).
- 모든 차트가 V5 design token 으로 강제 적용됨을 회귀 테스트로 을 확인한다.
- AP-1 ~ AP-13 중 라이브러리로 자동 해결되는 8개 항목이 회귀 테스트에서 이 0회 발생해야 한다.

---

## 8. Phase 2A — Evidence Dataset Contract (차트 데이터 계약)

### 8.1 What

차트와 지도가 *prose 의 부산물* 이 아니라 *구조화된 EvidenceDataset 에서 직접* 생성되도록 데이터 계약을 도입한다. 모든 차트는 source_id 가 강제된 EvidenceDataset 을 입력으로 한다.

### 8.2 Why

본 plan 의 Phase 2 (Vega-Lite 전환) 와 Phase 6 (Chart Critic) 만으로는 *차트의 데이터가 출처와 분리되는 회귀* 를 막지 못한다. composer 가 prose 에 박은 숫자를 VisualPlanner 가 차트로 다시 emit 하면, "그럴듯한 숫자, 그럴듯한 축, 그럴듯한 범주" 가 만들어진다. 차트의 시각 품질은 좋아져도 분석 신뢰도는 오히려 낮아진다.

차트 품질의 절반은 *데이터 계약* 에서 결정된다. Vega-Lite 나 D3 의 문제 이전에 *어떤 데이터가 차트에 들어갈 수 있는지* 를 봉인해야 한다.

### 8.3 모델 — `src/visual/evidence_dataset.py`

```python
class EvidenceDataset(BaseModel):
    """차트가 입력으로 받는 *유일한* 데이터 형태.
    ContextAnalyst 또는 ResearchDirector 가 만들거나, raw source 에서 추출한다.
    composer 의 prose 에서는 *생성하지 않는다*.
    """
    dataset_id: str                   # 보고서 안에서 unique
    title: str
    source_ids: list[str]             # ≥ 1 강제. EvidencePack.claims 의 source_id 와 매칭.
    rows: list[dict]
    fields: list[DatasetField]
    transforms: list[TransformStep] = []   # raw → 차트 데이터의 변환 이력
    limitations: list[str] = []            # "표본 크기 작음" 같은 데이터 한계 명시
    suitable_visuals: list[str] = []       # 이 데이터에 적합한 차트 type
    forbidden_visuals: list[str] = []      # 이 데이터에 부적합한 차트 type

class DatasetField(BaseModel):
    name: str
    semantic_type: Literal["time", "category", "geo", "quantity", "ratio", "score", "text"]
    unit: str = ""                    # "USD", "%", "건" 등
    nullable: bool = False

class TransformStep(BaseModel):
    """raw → 차트 데이터의 변환 단계. 감사 추적용."""
    operation: str                    # "filter", "groupby", "normalize", "interpolate" 등
    description: str                  # 사람이 읽을 수 있는 설명
    input_fields: list[str]
    output_fields: list[str]
```

### 8.4 VisualPlanner 의 입력 변경

Phase 2 의 VisualPlanner 가 받는 입력이 다음과 같이 변경된다.

```python
class VisualPlanner:
    async def plan(
        self,
        edited_report: EditedReport,         # Phase 1 Editor 출력
        datasets: list[EvidenceDataset],     # Phase 2A 신규 — *차트 데이터의 유일한 출처*
        visual_constraints: VisualConstraints,  # Phase 1A ResearchDirector 출력
        thesis: str,                         # 보고서 전체 thesis
    ) -> list[VegaLiteSpec]:
        ...
```

### 8.5 강제 규칙 — *금지 행위*

VisualPlanner 와 그 이후 단계에서 다음을 *코드 레벨에서* 금지한다.

(가) prose 에 언급된 숫자를 임의로 차트 데이터로 재구성한다 — 금지. 차트 데이터는 *반드시* EvidenceDataset 에서 와야 한다.

(나) 출처 없는 synthetic value 를 사용한다 — 금지. EvidenceDataset 의 `source_ids` 가 비어 있으면 `EvidenceDatasetGuard` 가 fail.

(다) source_id 없는 chart 를 emit 한다 — 금지. Phase 6 Gate A schema validation 이 차단한다.

이 세 금지 행위는 AP-V5-24, AP-V5-25, AP-V5-26 으로 명문화된다 (§23 참조).

### 8.6 ChartCritic 의 검증 강화

Phase 6 Gate B 의 ChartCritic 이 다음 질문을 추가한다 (기존 7개 + 신규 1개).

> 질문 8 — *이 차트의 데이터가 EvidenceDataset 에서 직접 왔는가? prose 가 차트 데이터를 직접 인용하는가?* 인용이 0건이면 drop. EvidenceDataset 이 없으면 즉시 drop.

이 질문이 GAP-12 (차트 데이터 계약 부재) 의 사후 가드이다. *사전 가드는 EvidenceDataset 의 source_ids 강제 자체* 이다.

### 8.7 인수 기준 (Phase 2A Acceptance)

- 모든 차트가 EvidenceDataset 을 *반드시* 입력으로 받아야 한다 (회귀 테스트로 검증).
- 모든 EvidenceDataset 이 ≥ 1개의 source_id 를 가져야 한다.
- prose 에서 인용되지 않는 숫자가 차트에 들어 있으면 ChartCritic 이 drop 해야 한다.
- TransformStep 이 raw → 차트 데이터의 변환을 100% 추적 가능해야 한다.

---

## 9. Phase 2B — Visualization Capability Registry

### 9.1 What

차트 type 을 *무제한* 허용하는 대신, 각 차트 type 을 어떤 renderer 가 *안전하게* 처리할 수 있는지 명시한 Registry 를 도입한다. Phase 2 의 "open-ended charts" 표현을 *capability-bounded charts* 로 정정한다.

### 9.2 Why — Vega-Lite 가 만능이 아니다

Vega-Lite 는 layer / facet / concat / repeat / transform 으로 다중 뷰와 파생 데이터를 지원한다. mark + encoding 만 지정해도 축·범례·스케일을 자동 생성한다. 본 plan 의 §3.7 에서 13개 antipattern 중 8개가 Vega-Lite 만으로 자동 해결된다고 평가했다.

다만 Vega-Lite 가 *모든 시각화를 네이티브로 커버* 하지는 않는다. Sankey, Chord, 복잡한 force-directed network, 고급 지도 annotation 은 별도 renderer 가 필요할 수 있다. "Vega-Lite spec 으로 표현 가능한 것 모두" 라고 한 본 plan 의 §3.6 표현은 정정해야 한다.

### 9.3 Capability Registry — `docs/VISUAL_CAPABILITY_REGISTRY.yaml`

```yaml
visual_capabilities:
  bar:
    renderer: vega_lite
    status: safe
    required_fields: [category, value]
  line:
    renderer: vega_lite
    status: safe
    required_fields: [time, value]
  area:
    renderer: vega_lite
    status: safe
    required_fields: [time, value]
  stacked_bar:
    renderer: vega_lite
    status: safe
    required_fields: [category, segment, value]
  heatmap:
    renderer: vega_lite
    status: safe
    required_fields: [x_category, y_category, value]
  bubble:
    renderer: vega_lite
    status: safe
    required_fields: [x, y, size]
  donut:
    renderer: vega_lite
    status: safe
    required_fields: [category, value]
  forecast:
    renderer: vega_lite
    status: safe
    required_fields: [time, actual, forecast, ci_low, ci_high]
  dual_line:
    renderer: vega_lite
    status: safe
    required_fields: [time, left_value, right_value]
  gantt:
    renderer: vega_lite
    status: safe
    required_fields: [task, start, end]
  choropleth:
    renderer: vega_lite_or_d3_geo
    status: guarded
    required_fields: [geo_id, value]
    notes: "TopoJSON 베이스맵 의존. Phase 6 Visual Sanity 강제."
  network:
    renderer: d3_custom
    status: guarded
    required_fields: [nodes, links]
    notes: "d3-force 의존. force layout 안정성 회귀 테스트 필수."
  sankey:
    renderer: d3_custom
    status: guarded
    required_fields: [source, target, value]
    notes: "d3-sankey plugin. 노드 수 ≤ 12 권장."
  chord:
    renderer: d3_custom
    status: experimental
    default_policy: forbidden
    notes: "ResearchDirector 의 must_have 에 명시 등재 시에만 허용."
  treemap:
    renderer: vega_lite_or_d3_custom
    status: experimental
    default_policy: forbidden
  decision_matrix:
    renderer: vega_lite
    status: safe
    required_fields: [option, criterion, score]
    notes: "Phase 8 전략 모드 필수 시각화."
```

### 9.4 정책 — 3-tier

| status | 정책 |
|--------|------|
| `safe` | VisualPlanner 가 자유롭게 emit 한다. ChartCritic 통과는 여전히 필요하다. |
| `guarded` | ChartCritic 통과 + Visual Sanity (Gate C) 통과 필수. 실패율이 safe 대비 높을 것으로 예상. |
| `experimental` | 기본값 *forbidden*. 사용자가 명시 요청하거나 ResearchDirector 가 `must_have` 로 지정한 경우에만 허용. |

이 정책은 차트 type 이 늘어나도 *깨지는 차트 백화점* 이 되지 않게 차단한다.

### 9.5 인수 기준 (Phase 2B Acceptance)

- VISUAL_CAPABILITY_REGISTRY.yaml 이 모든 차트 type 을 명시적으로 분류해야 한다.
- VisualPlanner 가 emit 하는 모든 차트가 Registry 에 등재된 type 이어야 한다.
- experimental 차트가 등재 없이 emit 되면 즉시 fail 해야 한다.
- 새 차트 type 추가 시 Registry 갱신을 *필수 단계* 로 강제한다 (PR 체크리스트).

---

## 10. Phase 3 — Layout Primitives (섹션별 레이아웃 변주)

### 4.1 What

섹션마다 동일한 (kicker → heading → lede → prose → charts) 구조 → **섹션이 자기 layout primitive 를 선택**.

### 4.2 Layout Primitive 목록 (V5 정본 — 9종 고정, 그 이상 추가 X)

| ID | 시각 효과 | 적합 사건 |
|----|-----------|-----------|
| `standard` | 현 v4.5.7 기본 (kicker/heading/lede/prose/charts) | 보통 분석 섹션 |
| `hero_map` | 풀-bleed 지도 + 짧은 caption + 본문 별 섹션 | 지리 사건 도입 (호르무즈, 베르베라) |
| `hero_chart` | 풀-bleed 차트 1개 + 짧은 caption | 결정적 단일 차트 (Brent 30일) |
| `split_2col` | 좌측 prose / 우측 차트 또는 fact_grid | 비교·대조 (한국 vs 일본 의존도) |
| `sidebar_callout` | 본문 80% + 우측 사이드바 (analogy 또는 pull_quote) | 어려운 개념 풀이 동반 분석 |
| `qna_panel` | Q&A 형식 (질문 → 짧은 답변 ×3~5) | "흔한 오해" 섹션 / FAQ 톤 |
| `timeline_strip` | 가로 또는 세로 타임라인 + 사건별 미니 코멘트 | 사건 경과 압축 |
| `signature_summary` | 큰 글씨 헤드라인 + 부제 1문장 + 본문 X | 챕터 표지 / 보고서 결론 |
| `exhibit_grid` | 차트 2~4개 그리드 + 짧은 종합 caption | 멀티-앵글 데이터 비교 |

### 4.3 How — 새 모듈 `src/agents/layout_typesetter.py`

```python
class LayoutTypesetter:
    """편집된 보고서 + 시각화 spec → 섹션별 layout primitive 결정.

    LLM 호출 1회 (Sonnet 4.6, 빠른 결정으로 충분).
    각 섹션에 layout_id 부여. Renderer 가 layout 별 Jinja2 템플릿 분기.
    """
```

LayoutTypesetter 결정 가이드 (system prompt 핵심):

```
- 보고서당 standard 가 60~70% 비중. 그 외 layout 은 *액센트* 로만 사용한다.
- hero_map / hero_chart 는 보고서당 최대 1~2개. 도입부 또는 결정적 섹션에 배치한다.
- signature_summary 는 보고서 첫 또는 마지막 섹션 1개로 한정한다.
- 같은 layout 을 *연속 2섹션* 에 배치 금지 (리듬).
- 사건이 지리적이면 hero_map 을 1~2번째 섹션에 배치를 권장한다.
- exhibit_grid 는 차트가 3개 이상 모인 섹션 로 한정한다.
```

### 4.4 Renderer 변경

`src/templates/composed_report.html` 단일 → 9종 layout 별 partial template:
- `templates/layouts/standard.html`
- `templates/layouts/hero_map.html`
- `templates/layouts/hero_chart.html`
- `templates/layouts/split_2col.html`
- `templates/layouts/sidebar_callout.html`
- `templates/layouts/qna_panel.html`
- `templates/layouts/timeline_strip.html`
- `templates/layouts/signature_summary.html`
- `templates/layouts/exhibit_grid.html`

main 템플릿이 `{% include "layouts/" + section.layout + ".html" %}` 로 dispatch.

### 4.5 인수 기준 (Phase 3 Acceptance)

- 9종 layout 모두 데모 가능한 샘플 사건 1건 (`samples/v5_layout_showcase.html`).
- 같은 사건 v4.5.7 vs V5 레이아웃 비교 (`samples/v5_compare_layout.html`).
- LayoutTypesetter 호출 실패 시 모든 섹션이 `standard` 로 fallback.

---

## 11. Phase 4 — Exhibit 번호제 (Cross-Reference)

### 5.1 What

차트가 섹션 안에 갇혀있는 현재 구조 → **첫째 클래스 Exhibit** 으로 승격. 자동 번호 + 본문 cross-reference.

### 5.2 Why

IB 보고서 어법: "Exhibit 4 에서 보듯..." / "(Exhibit 7 참조)" / "Exhibits 2-3 비교". 차트가 *논거의 anchor* 이자 *공유 참조점* 으로 기능. 본문이 차트를 가리키고, 차트가 다시 본문을 강화하는 양방향 결합을 만든다.

### 5.3 How

`ComposedReport` 모델 확장:

```python
class Exhibit(BaseModel):
    exhibit_id: int  # 자동 부여 (Exhibit 1, 2, 3, ...)
    chart_spec: dict  # Vega-Lite spec (Phase 2)
    title: str
    subtitle: str = ""
    source: str = ""
    takeaway: str = ""
    anchor_section_idx: int  # 어느 섹션에 *주로* 박힐지 (LayoutTypesetter 결정)

class ComposedReport(BaseModel):
    ...
    exhibits: list[Exhibit] = []  # 보고서 전체에서 공유. 섹션이 cross-ref.
```

Composer / Editor 의 prose 안에서 cross-ref 표기:
```
[[ex:4]]   →  렌더 시 "Exhibit 4" 로 치환
[[exr:4]]  →  "(Exhibit 4 참조)"
[[exs:2-3]] → "Exhibits 2~3"
```

Renderer 가 정규식 치환을 적용하고 클릭 시 해당 exhibit 으로 anchor 점프시킨다.

### 5.4 시각 표기

각 Exhibit:
- 좌상단 회색 일련번호: "EXHIBIT 4"
- 차트 위 caption: 제목 / 부제
- 차트 아래 footer: source · takeaway

스타일 토큰 (V5 design token, §4):
```css
.exhibit-label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  letter-spacing: 1.6px;
  text-transform: uppercase;
  color: var(--muted);
}
```

### 5.5 인수 기준 (Phase 4 Acceptance)

- Composer/Editor 시스템 프롬프트에 `[[ex:N]]` 표기 규칙 를 추가하지 않는다.
- 본문에서 exhibit 을 cross-ref 한 사례가 보고서당 평균 1~3회 (telemetry 측정).
- exhibit 번호 충돌 / 미존재 ref 회귀 테스트 를 통과해야 한다.

---

## 12. Phase 5 — Word Budget per Section + 절단 회귀 해결

### 6.1 What

이 단계는 두 작업을 통합한다. 첫째, mode 단위(fast/standard/deep)의 *섹션 수* 가이드만 있던 것을 섹션 단위 *어절·문자 수* budget 으로 정밀화한다. 둘째, *보고서 출력이 중간에 잘리는 회귀* 를 자동 검출하고 연속 호출로 보정한다. 두 작업은 모두 *분량 통제* 라는 같은 축에 있어 한 Phase 로 묶는다.

### 6.2 Why

현재 v4.5.7 composer 는 두 회귀를 동시에 보인다.

(가) **분량 균질화 회귀.** composer 가 모든 섹션을 균질 분량으로 풀어쓴다. 결정적 섹션 (예: "왜 지금" 메커니즘 분석) 은 길게, 보조 섹션 (예: 배경 정리) 은 짧게 — 이런 *분량 비대칭* 이 IB 보고서의 리듬을 만든다. v4.5.7 는 이 리듬을 만들지 못한다.

(나) **출력 절단 회귀.** composer 의 max_tokens 가 부족할 때 JSON 이 마지막 섹션 중간에서 잘린다. 또는 max_tokens 에 닿지 않더라도 composer 자체가 "이 정도면 충분하다" 고 판단해 조기 종료한다. 두 경우 모두 *주제의 복잡도에 비해 보고서가 부족* 한 결과를 낳는다. 시스템은 이 부족을 감지하지 못하고 그대로 발행한다. YK 가 "보고서가 끊긴다" 고 알아채야 한다.

### 6.3 How — 섹션별 분량 budget

`ComposedSection` 에 `target_chars` 필드를 추가한다.

```python
class ComposedSection(BaseModel):
    ...
    target_chars: int = 1200  # 한국어 기준 권장 분량. Editor 가 이 budget 을 강제한다.
    actual_chars: int = 0     # 렌더 시점에 측정한다.
```

Mode 별 budget 분포는 다음과 같다 (composer 가 섹션 설계 시 결정한다).

| Mode | 총 분량 (KR 자) | 섹션 수 | 분포 가이드 |
|------|-----------------|---------|-------------|
| fast | 1,500~2,500 | 3~4 | 균등 (400~700자 씩) |
| standard | 3,500~5,500 | 4~6 | 비대칭 (peak 섹션 1,200~1,800자, 보조 섹션 500~800자) |
| deep | 6,000~9,000 | 5~7 | 강한 비대칭 (peak 섹션 2,000~2,500자, 보조 섹션 600~1,000자) |

Editor 는 `actual_chars > target_chars × 1.2` 인 섹션을 압축하고, `actual_chars < target_chars × 0.7` 인 섹션을 보강하거나 cut 한다.

### 6.4 How — 절단 자동 검출 (NEW)

composer 호출 직후 결정적 규칙으로 절단 여부를 판정한다. LLM 호출은 필요하지 않다.

```python
def detect_truncation(composed: ComposedReport | None, mode: str, raw_response: str) -> TruncationStatus:
    """composer 출력의 절단 여부를 판정한다."""
    issues: list[str] = []

    # 1. JSON 파싱 실패는 가장 명확한 절단 신호이다.
    if composed is None:
        return TruncationStatus(truncated=True, reason="json_parse_failed", raw_tail=raw_response[-500:])

    # 2. 마지막 섹션의 prose 가 문장 부호 없이 끝나면 잘렸다고 판정한다.
    if composed.sections:
        last_prose = composed.sections[-1].prose.rstrip()
        if last_prose and last_prose[-1] not in ".!?":
            issues.append("last_section_unfinished")

    # 3. closing 필드가 비어 있으면 epilogue 작성 전에 끊겼다.
    if not composed.closing:
        issues.append("closing_missing")

    # 4. deep 모드에서 watch_signals 또는 contradictions 가 비어 있으면 절단 가능성이 높다.
    if mode == "deep":
        if len(composed.watch_signals) == 0:
            issues.append("watch_signals_missing_in_deep")
        if len(composed.contradictions) == 0:
            issues.append("contradictions_missing_in_deep")

    # 5. 총 분량이 mode 별 하한의 70% 미만이면 부족하다고 판정한다.
    target_total = MODE_TARGET_CHARS_LOWER[mode]
    actual_total = sum(len(s.prose) for s in composed.sections)
    if actual_total < target_total * 0.7:
        issues.append(f"underweight_{actual_total}_vs_{target_total}")

    return TruncationStatus(truncated=bool(issues), reason="; ".join(issues))
```

이 검출은 모든 보고서에 적용된다. 절단으로 판정되면 다음 단계 (연속 호출) 로 진입한다.

### 6.5 How — 연속 호출 (Continuation Pass)

절단으로 판정되면 부분 출력을 다시 composer 에 입력하면서 *이어 작성* 을 지시한다. 같은 모델 (Opus 4.7) 을 사용한다.

```python
async def continuation_call(
    self,
    partial: ComposedReport,
    raw_partial: str,
    truncation_status: TruncationStatus,
    context: ContextAnalysis,
    mode: str,
) -> ComposedReport | None:
    """부분 출력 + 끊긴 위치를 입력해서 이어 작성한다.

    원본 시스템 프롬프트를 재사용한다.
    user message 에 다음을 포함한다:
    - 원래 입력 (사실 자료 등)
    - 절단된 raw 출력 (tail 1500자 정도)
    - 명시적 지시: "위 출력이 끊겼다. 동일한 JSON 구조를 유지하면서 끊긴 지점부터 정확히 이어 작성하라.
                   응답은 *남은 부분의 JSON* 만 생성하라 (예: 마지막 섹션이 잘렸으면 그 섹션의 나머지부터)."
    """
```

**연속 호출 한도** 는 1회를 넘지 않는다. 1회 후에도 절단이 검출되면 publish-with-warning 으로 진행한다 (사용자에게 "분량이 충분치 않을 가능성" 을 텔레그램 메시지에 표기한다). 무한 루프를 방지하는 cap 이다.

**Stitching 정책** 은 단순하다. 원본의 마지막 미완성 부분을 잘라내고, 연속 호출의 출력을 그 자리에 붙인다. 두 출력의 경계가 어색하면 Editor 가 다음 단계에서 다듬는다.

### 6.6 How — 적응형 max_tokens (NEW)

ContextAnalyst 가 사건 복잡도 점수를 산출한다 (출처 수 × 행위자 수 × 타임라인 사건 수 의 단순 가중합으로 시작한다). composer 의 max_tokens 가 이 점수에 따라 동적으로 조정된다.

```python
COMPOSER_MAX_TOKENS_V5 = {
    "fast":     {"base": 16000, "max": 24000},   # v4.5.7: 12000 단일
    "standard": {"base": 28000, "max": 40000},   # v4.5.7: 20000 단일
    "deep":     {"base": 48000, "max": 64000},   # v4.5.7: 32000 단일 — 가장 자주 잘림
}

def adaptive_max_tokens(mode: str, context: ContextAnalysis) -> int:
    """복잡도에 따라 base ~ max 사이에서 동적으로 결정한다."""
    config = COMPOSER_MAX_TOKENS_V5[mode]
    complexity = (
        len(context.sources) * 2 +
        len(context.timeline) * 1.5 +
        len(context.key_figures)
    )
    # 복잡도 정규화 (0~1) 후 base ~ max 사이에서 보간한다.
    norm = min(complexity / 50.0, 1.0)
    return int(config["base"] + (config["max"] - config["base"]) * norm)
```

Opus 4.7 의 출력 한도는 기본 32K 이지만 streaming + extended thinking 옵션으로 64K 까지 확보 가능하다 (Anthropic API 문서 확인 필요). v4.5.7 의 일률 32K 는 *복잡한 deep 사건에 부족* 하다. base 를 일괄 상향한다.

### 6.7 인수 기준 (Phase 5 Acceptance)

- 같은 사건을 deep 모드로 분석할 때 섹션 분량 분포의 *지니 계수* 가 v4.5.7 baseline 보다 0.10 이상 증가한다 (비대칭이 강해진다).
- Editor 호출 시점에 `actual_chars` 와 `target_chars` 를 텔레메트리에 기록한다.
- 절단 검출이 v4.5.7 의 회귀 사례 (보고서가 끊긴 사례) 를 회귀 테스트로 100% 잡아낸다.
- 연속 호출 후 최종 보고서의 절단 잔존율이 ≤ 5% 이다.
- 텔레그램 사용자가 "보고서가 끊겼다" 고 보고하는 빈도가 V5 출시 후 30일간 ≤ 2건이다.

---

## 13. Phase 6 — Chart Correctness Gate (차트 품질 4중 게이트)

> **목적.** `docs/CHART_RENDERING_ANTIPATTERNS.md` 의 13개 회귀가 *반응형으로* 누적된 구조를 끝낸다. 깨진 차트 / 부적합 차트 / 선례 오염 차트 가 보고서에 *노출되는 일이 0건이 되도록 한다.
>
> **원칙.** *작성 단계의 LLM 자율* 만으로 차트 품질을 보장하려고 한 것이 13개 antipattern 누적의 근본 원인. V5 는 차트가 보고서에 등장하기까지 *4중 게이트* 통과를 강제한다. 한 곳에서 떨어지면 fallback 사다리를 적용한다.

### 7.1 4중 게이트 — 흐름

```
VisualPlanner (Phase 2) emit 차트 spec
        ↓
[Gate A] Schema Validation         ← Vega-Lite JSON Schema + 타입별 Pydantic 가드 (결정적, LLM X)
        ↓ pass / fail → fallback
[Gate B] Chart-Topic Fit Critic    ← Sonnet 4.6 LLM 호출. 1차트당 ~1K 토큰.
        ↓ keep / replace / drop
[Gate C] Render-time Visual Sanity ← Vega-Lite SVG 렌더 후 정적 검증 (결정적, LLM X)
        ↓ pass / fail → fallback
[Gate D] Fallback Ladder           ← 어느 게이트든 fail 시 사다리 적용
        ↓
보고서에 노출
```

### 7.2 Gate A — Schema Validation (Pre-render)

**무엇을 검증하는가:**
1. Vega-Lite spec 자체의 JSON Schema 정합 (vl-convert / vega-cli 의 built-in validator).
2. 타입별 Pydantic 가드를 추가한다 — `src/visual/schemas.py` 를 신설한다.

**타입별 가드 예시:**
```python
class BubbleChartGuard(BaseModel):
    data: list[BubblePoint] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_finite_ranges(self) -> "BubbleChartGuard":
        xs = [p.x for p in self.data]
        ys = [p.y for p in self.data]
        if not all(math.isfinite(v) for v in xs + ys):
            raise ValueError("CHART-AP-12 가드: x/y 에 NaN/inf 포함")
        # 범위가 100배 차이면 의심 — 정규화 권장
        if max(xs) - min(xs) > 100 * (max(xs) + 1e-9):
            raise ValueError("CHART-AP-12 가드: x 범위가 비정상적으로 큼")
        return self

class GanttGuard(BaseModel):
    rows: list[GanttRow] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_ranges(self) -> "GanttGuard":
        for r in self.rows:
            if not _parse_time(r.start) or not _parse_time(r.end):
                raise ValueError(f"CHART-AP-13 가드: {r.label} start/end 파싱 실패")
            if _parse_time(r.start) > _parse_time(r.end):
                raise ValueError(f"CHART-AP-13 가드: {r.label} start > end")
        return self

class NetworkGuard(BaseModel):
    nodes: list[NetworkNode] = Field(min_length=2)
    links: list[NetworkLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_link_refs(self) -> "NetworkGuard":
        node_ids = {n.id for n in self.nodes}
        for link in self.links:
            if link.source not in node_ids or link.target not in node_ids:
                raise ValueError(f"CHART-AP-7/AP-1 가드: link source/target 미정의")
        return self
```

**커버리지:** AP-3 (NaN/inf), AP-7 (빈 data), AP-12 (bubble 범위), AP-13 (gantt 시간 정합).

**실패 시** Gate D (fallback) 로 진입한다.

### 7.3 Gate B — Chart-Topic Fit Critic (LLM 호출)

**왜 별도 LLM 호출인가:**
- AP-8 (5-phase gantt 라벨 충돌) 과 AP-14 (호르무즈 보고서에 소말릴란드 해칭 영구 박힘) 는 *판단* 문제. 라이브러리가 "이 차트 type 이 이 데이터에 맞는가" 를 물어주지 않는다.
- Editor 는 *글* 을 본다. Chart Critic 은 *논거-차트 결합* 을 본다. 책임을 분리한다.
- Sonnet 4.6 (model_name_light) 사용. Critic 1회당 ~1K 토큰. 보고서당 차트 0~5개면 5K 미만이다.

**모듈은 `src/agents/chart_critic.py` 에 신설한다.**

```python
class ChartCritic:
    """차트 spec + 인접 prose 를 받아 keep/replace/drop 판정."""
    CRITIC_MODEL: str = "claude-sonnet-4-6"
    MAX_TOKENS: int = 1024

    async def critique(
        self,
        chart_spec: dict,     # Vega-Lite spec
        section_prose: str,   # 차트가 박힐 섹션의 prose
        report_thesis: str,   # 보고서 전체 thesis (deck)
    ) -> ChartVerdict:
        ...

class ChartVerdict(BaseModel):
    score: int = Field(ge=1, le=5)  # 1=무관, 5=논거의 핵심
    verdict: Literal["keep", "replace", "drop"]
    reason: str  # 1문장
    suggested_type: str | None = None  # verdict=replace 일 때만
```

**Critic 시스템 프롬프트 — 핵심 7개 질문:**

```
당신은 데이터 시각화 비평가. 보고서에 박히려는 차트를 본다.
다음 7개 질문에 차례로 답하고 최종 판정 (keep/replace/drop).

1. 본 차트를 *빼면* 이 섹션의 논거가 실질적으로 약해지는가?
   → 약해지지 않으면 즉시 drop. (선례 오염 차단 — AP-V5-7)

2. 차트의 takeaway 한 줄이 인접 prose 의 thesis 와 *다른* 정보를
   주는가, *같은 말* 의 반복인가?
   → 같으면 drop.

3. 이 데이터 형태에 이 차트 type 이 *최적* 인가?
   - 5+ phase 시간 흐름 → gantt 가 아니라 timeline_strip 또는 본문 list
   - 0~1 정규화 안 된 좌표 데이터 → bubble 부적합
   - 라벨 ≥ 14자 + 항목 5개 이상 → bar 부적합
   → 최적이 아니면 replace + suggested_type.

4. 이 차트의 데이터가 *이 보고서의 prose* 에서 직접 인용되거나
   참조되는가? (예: prose 가 'Brent $112' 언급 → 차트에 brent 그래프)
   → 직접 참조 0건이면 drop. 차트가 "주제 비슷해서 박힌" 선례 오염의 신호이다.

5. 이 차트가 다른 차트와 *중복 정보* 를 보여주는가?
   → 중복이면 drop (보고서당 차트 ≤ 5개 강제).

6. 지도라면 — 이 보고서의 본문이 그 지역을 *명시적으로 다루는가*?
   → 안 다루면 drop. (AP-14: 무관 지리 annotation 차단)

7. takeaway 가 *공허* 한가? ('변동성이 크다' / '의존도가 높다' 같은
   당연한 관찰)
   → 공허하면 drop.

판정:
- keep: 5/7 이상 통과 + 결정적 질문 (1, 4, 6) 모두 통과
- replace: type 만 부적합 (3번만 fail), 다른 type 으로 살릴 수 있음
- drop: 그 외 모두

JSON 출력만:
{
  "score": 1~5,
  "verdict": "keep|replace|drop",
  "reason": "1문장. 어느 질문에서 fail 했는지 명시.",
  "suggested_type": "replace 일 때만"
}
```

**커버리지:** AP-8 (chart type 부적합), AP-14 (무관 annotation), AP-V5-7 (선례 오염).

**실패 시:** drop → Gate D (fallback). replace → suggested_type 으로 spec 재생성 1회 (그래도 fail 시 drop).

### 7.4 Gate C — Render-time Visual Sanity Check

**무엇을 검증하는가:**
Vega-Lite 가 SVG 렌더한 결과를 *파싱해서* 다음을 측정:

1. **viewport 안 마크 카운트.** SVG `<rect>`, `<circle>`, `<path>` 등 데이터 마크가 viewBox 안에 *몇 개* 보이는가. 0이면 fail (AP-12 의 빈 frame 같은 사례).
2. **라벨 bbox 충돌 비율.** SVG `<text>` 모두 추출 → 각 bbox 계산 → 충돌 페어 카운트. (충돌 페어 / 전체 라벨 페어) > 0.20 이면 fail (AP-5, AP-6, AP-10).
3. **빈 frame 감지.** viewBox 면적 대비 마크 + 라벨 영역 비율 < 5% 면 fail.
4. **라벨 잘림 감지.** `<text>` bbox 가 viewBox 밖으로 나가면 fail (AP-5).

**모듈:** `src/visual/sanity_check.py` 신설. 의존성: `lxml` (SVG 파싱).

```python
def visual_sanity_check(svg: str, viewbox: tuple[int, int, int, int]) -> SanityResult:
    tree = etree.fromstring(svg.encode())
    marks = _extract_data_marks(tree, viewbox)
    labels = _extract_text_bboxes(tree)

    issues: list[str] = []
    if len(marks) == 0:
        issues.append("AP-12: 데이터 마크 0개 (frame 밖 또는 빈 data)")
    overlap_ratio = _label_overlap_ratio(labels)
    if overlap_ratio > 0.20:
        issues.append(f"AP-5/6/10: 라벨 bbox 충돌 {overlap_ratio:.0%}")
    if _label_clip_count(labels, viewbox) > 0:
        issues.append("AP-5: 라벨 viewBox 밖 잘림")
    fill_ratio = _occupied_area_ratio(marks, labels, viewbox)
    if fill_ratio < 0.05:
        issues.append(f"AP-12: viewBox 의 {fill_ratio:.0%} 만 사용 (빈 frame)")

    return SanityResult(passed=not issues, issues=issues)
```

**커버리지:** AP-5 (라벨 잘림), AP-6 (annotation 충돌), AP-10 (마커 라벨 충돌), AP-12 (frame 밖).

**실패 시** Gate D (fallback) 로 진입한다. `result.telemetry` 에 어느 항목이 fail 했는지를 기록한다.

### 7.5 Gate D — Fallback Ladder

게이트 어느 단계든 실패 시 *깨진 차트를 노출하지 않고* 사다리 단계별로 격하:

```
1단계: 같은 데이터 → fact_grid 변환 (라벨 격자, 시각화 X).
       editorial 톤에 맞고 깨질 일 없음.
       데이터의 라벨 / 값 표시.

2단계: 1단계도 실패 (데이터 너무 많아 격자 부적합) → 본문에 1문장
       자연어 요약 추가 ("호르무즈 의존도는 한국 12%, 일본 11% 등").

3단계: 2단계도 실패 (Critic 이 drop) → 차트 자체 제거. 보고서에서
       흔적이 남지 않는다. telemetry 에 dropped_chart 를 기록한다.
```

**규칙:** *깨진 차트 / 부적합 차트가 보고서에 노출되는 일은 0건* 이어야 함. 사용자가 보고서를 열었을 때 "왜 이게 여기 있지?" 하는 차트는 V5 에서는 발생 X.

### 7.6 Antipattern → Gate 매핑 (전수)

| AP-N | 원인 | 1차 가드 | 2차 가드 |
|------|------|----------|----------|
| AP-1 | group/category 시각 분리 | Vega-Lite (Phase 2) | — |
| AP-2 | 라벨 색 일관성 | Vega-Lite (Phase 2) | — |
| AP-3 | 음수/0/극단값 | Vega-Lite + Gate A | — |
| AP-4 | aspect-ratio 충돌 | Vega-Lite (Phase 2) | — |
| AP-5 | 라벨 zone 밖 | Vega-Lite (부분) | Gate C |
| AP-6 | annotation 겹침 | Vega-Lite (부분) | Gate C |
| AP-7 | 빈 data emit | Gate A | Gate D fallback |
| AP-8 | type 사건 부적합 | **Gate B (Critic)** | Gate D fallback |
| AP-9 | zoom/center 디폴트 | Vega-Lite (Phase 2) | — |
| AP-10 | 지도 마커 충돌 | Vega-Lite (부분) | Gate C |
| AP-11 | 카드 배경 하드코딩 | Vega-Lite theme | — |
| AP-12 | bubble 스케일 | Vega-Lite + Gate A | Gate C |
| AP-13 | gantt 시간축 누락 | Vega-Lite (Phase 2) | — |
| AP-14 | 무관 지리 annotation | **Gate B (Critic)** | Gate D fallback |
| **AP-V5-7** | **선례 오염 (이번 V5 신규)** | **Gate B (Critic 질문 1, 4)** | Gate D fallback |

### 7.7 인수 기준 (Phase 6 Acceptance)

- 14개 antipattern 시나리오를 시뮬레이션한 회귀 테스트 (`tests/test_chart_correctness.py`) 신설. 각 antipattern 의 *깨진 입력* 을 만들어서 Gate A/B/C 가 잡는지 을 확인한다.
- 실 사용 보고서 10건 (다양한 카테고리) 에서 차트별 Gate 통과율 텔레메트리에 기록한다.
- *0번째 사용자 발견 antipattern* — V5 출시 후 30일간 새 antipattern (CHART-AP-15+) 0건 (목표).
- 사용자가 직접 "이 차트는 왜 여기 있지?" 라고 하는 사례 0건 (telegram 봇으로 보고된 회귀 카운트 = 0).

### 7.8 Critic 운영 정책 — *느슨하지 않게*

Critic 의 보수성 설정:
- score ≥ 4 만 keep (3 은 ambiguous → drop).
- 한 보고서에 차트 ≥ 5개면 score 가장 낮은 차트부터 drop (Critic 통과해도 *총량 가드*).
- Critic 자체 호출 실패 (timeout / parse error) 시 *drop* (보수적 fallback). composer 가 emit 한 차트를 무조건 통과시키지 않는다.

이는 v4.5.7 의 "composer 가 emit 한 건 일단 그린다" 와 정반대 정책. *기본은 drop, 통과는 명시적 승인이 있을 때만*.

---

## 14. Phase 6A — Exhibit Priority Policy (3-tier)

### 14.1 What

ChartCritic 의 "drop 우선" 정책을 보완해 *핵심 논거 차트가 조용히 사라지는* 부작용을 막는다. 모든 exhibit 을 3등급으로 나눠 등급별 fallback 정책을 적용한다.

### 14.2 Why

Phase 6 의 Critic 정책은 "score < 4 면 drop" 의 보수적 fallback 이다. 이는 깨진 차트 노출을 0으로 만들지만, 부작용으로 *중요한 Exhibit* 까지 너무 쉽게 사라질 수 있다. 그러면 보고서가 텍스트만 남고, "분량이 짧다 / 중간에 끊긴다 / 분석이 얕다" 는 회귀가 GAP-9 의 형태로 재발한다.

원칙은 다음과 같다. *깨진 차트는 노출하지 않는다. 단 핵심 논거 차트는 조용히 사라지게 하지 않는다.*

### 14.3 ExhibitPriority — 3-tier

```python
ExhibitPriority = Literal["required", "supporting", "decorative"]

class Exhibit(BaseModel):
    ...
    priority: ExhibitPriority = "supporting"  # 기본값
    priority_assigned_by: Literal["research_director", "visual_planner", "default"] = "default"
```

Priority 부여 주체와 정책은 다음과 같다.

| priority | 부여 주체 | Critic fail 시 정책 |
|----------|-----------|---------------------|
| `required` | ResearchDirector (Phase 1A) 가 분석기법의 핵심 증거로 지정 | **drop 금지.** fact_grid 또는 table 로 강제 대체. DeskEditor 에 hold 사유로 전달. |
| `supporting` | VisualPlanner 기본값 | fact_grid 또는 1문장 자연어 요약으로 대체. |
| `decorative` | VisualPlanner 가 *논거에 부수적* 으로 판단 | 조용히 제거. |

### 14.4 ResearchDirector 의 Required Exhibit 지정 — 의무

Phase 1A 의 AnalysisBrief 가 다음을 *반드시* 포함한다.

```python
class AnalysisMethod(BaseModel):
    ...
    required_exhibits: list[RequiredExhibit]  # priority="required" 가 강제

class RequiredExhibit(BaseModel):
    description: str             # "호르무즈 의존도 국가별 비교 차트"
    visual_type_hint: str        # "bar" 또는 "choropleth"
    why_required: str            # 1문장 정당화
    fallback_form: Literal["fact_grid", "table", "text"]  # drop 대체 형태
```

ResearchDirector 가 *한 사건의 핵심 분석에 어떤 차트가 필수인지* 를 사전에 결정한다. 이게 Phase 6A 의 작동 신호다.

### 14.5 인수 기준 (Phase 6A Acceptance)

- 모든 exhibit 이 priority 를 갖는다 (default supporting).
- Required exhibit 이 Critic fail 한 사례에서 drop 되지 않고 fallback 으로 대체되었음이 회귀 테스트로 확인되어야 한다.
- DeskEditor 가 required exhibit 의 fallback 발생을 hold 사유로 인지해야 한다 (사용자에게 "핵심 차트가 fallback 됨" 을 텔레메트리로 노출).
- 보고서당 required exhibit 비율이 *너무 높으면* (>50%) ResearchDirector 의 prompt tuning 신호.

---

## 15. Phase 7A — Deterministic Publish Gate (LLM 이전 결정적 검사)

### 15.1 What

DeskEditor (LLM Vision) 호출 *전* 단계에서 결정적 (rule-based) 검사를 먼저 수행한다. 기계적으로 잡을 수 있는 결함은 LLM 비용을 쓰지 않고 차단한다.

### 15.2 Why

Phase 7 의 DeskEditor 는 *모든 검수* 를 LLM 으로 한다. HTML 파싱 실패 / exhibit ref broken / mobile viewport overflow / asset 404 같이 *결정적으로 잡을 수 있는 결함* 까지 LLM 이 보고 있다. 토큰 낭비 + 불안정성 둘 다 키운다. *기계적으로 잡을 수 있는 문제는 LLM 에게 보내지 않는다.*

### 15.3 위치 — Renderer 와 Phase 7 사이

```
Renderer → reports/dev/<id>.html
        ↓
[Phase 7A] Deterministic Publish Gate    ← 신규
        ↓ pass / fail (hard / soft)
[Phase 7-pre] Playwright Capture
        ↓
[Phase 7] LLM DeskEditor (Logical + Visual Proof)
        ↓
[PUBLISH / HOLD / KILL]
```

### 15.4 검사 항목 — Hard Fail (즉시 KILL)

다음 중 하나라도 해당하면 Desk LLM 호출 없이 즉시 KILL.

```python
HARD_FAIL_RULES = {
    "html_render_failed":          not Path(rendered_html_path).exists(),
    "html_unparseable":            not _is_parseable_html(rendered_html_path),
    "required_section_missing":    _has_missing_required_sections(report, brief),
    "exhibit_ref_broken":          _has_broken_exhibit_refs(report.prose),
    "chart_without_source":        _has_chart_without_source_id(report.exhibits),
    "chart_container_empty":       _has_empty_chart_containers(rendered_html_path),
    "report_too_short":            total_chars < MODE_LOWER_BOUND[mode],
    "closing_missing":             not report.closing,
    "asset_404":                   _has_404_assets(rendered_html_path),
    "mobile_horizontal_overflow":  _has_mobile_overflow(rendered_html_path, threshold_px=24),
    "playwright_timeout":          _capture_failed_with_timeout(),
}
```

### 15.5 검사 항목 — Soft Fail (DeskEditor 에 hold 신호로 전달)

다음은 즉시 KILL 하지 않고 DeskEditor 에 *추가 검토 신호* 로 전달.

- 섹션 분량 비대칭 과다 (지니 계수 > 0.6)
- 차트 수가 mode 상한 초과
- heading pattern 반복 (모든 heading 이 비슷한 길이·구조)
- watch signal 의 약함 (모두 ambiguous)
- stale source 비율 높음 (3개월 이상 된 출처가 70%+)

### 15.6 인수 기준 (Phase 7A Acceptance)

- Hard fail 11종이 모두 회귀 테스트로 검증되어야 한다.
- Hard fail 발생 시 Desk LLM 호출이 *발생하지 않아야* 한다 (토큰 0).
- v4.5.x 의 "사용자가 발견한 결함" 사례 다수가 Phase 7A 의 결정적 룰로 잡혀야 한다.
- Soft fail 이 DeskEditor 의 system prompt 에 명시적으로 전달되어야 한다.

---

## 16. Phase 7 — Desk Editor (Logical + Visual Proof, publish / hold / KILL 권한)

> **목적.** 신문사 데스크 등급의 *시스템 QA*. Phase 1~6 의 부분 책임자들이 못 보는 *전체 패키지* 의 일관성·발행 적격성을 판정. **두 갈래 검수** — (가) 원고 검토 (manuscript review, JSON 기반) + (나) 페이지 프루프 검수 (galley proof, 렌더된 HTML 스크린샷 기반). **KILL 권한 도입** — 발행 가치 없는 보고서는 *조용히 발행하지 않는다*.
>
> **원칙.** 신문사·방송사 워크플로우의 *데스크 / managing editor* 를 시스템에 정확히 매핑. 실제 데스크는 (1) 원고를 *읽고* (2) 식자·조판 끝난 페이지 프루프를 *눈으로 보고* 둘 다 종합 판정. 같은 사람이 두 입력을 본다. v4.5.7 의 graceful fallback 정책 (어떻게든 내보냄) 과 정반대이다.
>
> **YK 의 현재 수동 워크플로우 자동화** — *YK 가 텔레그램으로 캡쳐 → AI 가 받아서 분석 → 패치 → 재배포* 사이클이 정확히 (나) 페이지 프루프 검수의 *수동 버전*. 이 책임을 시스템 안으로 이전.

### 8.1 Phase 7 위치 — 모든 단계 *이후*

```
ContextAnalyst → Composer → Editor → VisualPlanner → ChartCritic → ChartGate
                                                                       ↓
                                                                 LayoutTypesetter
                                                                       ↓
                                                              Renderer → reports/dev/<id>.html
                                                                       ↓
                                                          Playwright Capture (Phase 7-pre)
                                                                       ↓        ↘
                                                          ▶ DeskEditor ◀  ← Phase 7
                                                          (JSON + 3~5 screenshots)
                                                                       ↓
                                                              [PUBLISH / HOLD / KILL]
                                                                       ↓
                                                          PUBLISH → Cloudflare 배포 (reports/<id>.html)
                                                          HOLD    → lower editor 1회 재호출
                                                          KILL    → 발행 거부 + 사용자 알림
```

Phase 1~6 모두 통과 + 렌더링 완료 + 시각 캡쳐 완료 후 *최종 게이트*. 한 보고서당 1회 (HOLD 시 최대 1회 재호출).

중요: Renderer 가 *디스크에 HTML 쓰기* 와 *Cloudflare 업로드* 를 분리. Phase 7 KILL 시 디스크 HTML 만 보존 (디버그용), Cloudflare 업로드는 PUBLISH 가 떨어진 후에만.

### 8.2 모듈 — `src/agents/desk_editor.py`

```python
class DeskEditor:
    """완성된 보고서 패키지를 보고 publish / hold / KILL 판정.

    두 갈래 입력:
    - composed (JSON):       원고 검토 (논리·정합·발행 적격성)
    - screenshots (image):   페이지 프루프 검수 (렌더된 HTML 시각 결함)

    부분 편집자 (Editor / ChartCritic / LayoutTypesetter) 가 못 보는
    *전체적 정합성* 과 *시각 결함* 을 점검. 발행 가치 없는 보고서는 KILL.
    """
    DESK_MODEL: str = "claude-opus-4-7"  # vision capability 필수 — Opus 4.7
    MAX_TOKENS: int = 8000

    async def review(
        self,
        composed: ComposedReport,
        rendered_html_path: str,                # 렌더된 HTML 의 로컬 path
        screenshots: list[ScreenshotCapture],   # Playwright 캡쳐 결과
        context: ContextAnalysis,
    ) -> DeskVerdict:
        ...

class ScreenshotCapture(BaseModel):
    role: Literal["desktop_full", "mobile_full", "chart_closeup", "map_closeup"]
    image_b64: str          # base64 PNG
    label: str              # "Exhibit 3 close-up" 등 description
    width: int
    height: int

class DeskVerdict(BaseModel):
    decision: Literal["publish", "hold", "kill"]
    logical_rubric_scores: dict[str, int]   # 7개 논리 항목 1~5
    visual_rubric_scores: dict[str, int]    # 8개 시각 항목 1~5
    issues: list[DeskIssue]                 # decision != publish 일 때 비어있지 않음
    kill_reason: str = ""                   # decision == kill 일 때만

class DeskIssue(BaseModel):
    severity: Literal["minor", "major", "blocker"]
    domain: Literal["logical", "visual"]    # 어느 갈래에서 잡혔는지
    rubric: str                             # 어느 rubric 항목
    description: str                        # 1문장
    suggested_action: str                   # "rewrite_headline" | "drop_chart_3" 등
    target_module: str                      # "composer" | "editor" | "chart_critic" | "layout" | "renderer"
    visual_evidence_idx: int | None = None  # visual issue 면 어느 screenshot 에서 발견
```

### 8.3 (가) 원고 검토 — Logical 7-rubric

각 항목 1~5 점수. score ≤ 2 면 issue 발생. *입력은 ComposedReport JSON*.

**(1) Headline-Body 정합 (Headline-Body Match)**
- 헤드라인이 주장한 것을 본문이 *실제로* 입증하는가
- 회귀 사례: 헤드라인 "X가 결정적 변곡" → 본문 결론 "X는 작은 변화 중 하나" → 헤드라인 과장
- score 2 이하: issue (severity=major), action="rewrite_headline"

**(2) Deck-Conclusion 정합 (Deck-Conclusion Match)**
- 부제(deck) 가 미리 보여준 결론이 마지막 섹션에서 *그대로* 도출되는가
- 회귀 사례: 부제 단호한데 결론 양손잡이 ("일면 그렇지만 한편으로는...")
- score 2 이하: action="rewrite_deck" 또는 "rewrite_conclusion"

**(3) 섹션 흐름의 수렴성 (Section Flow Coherence)**
- 각 섹션이 *앞 섹션을 이어받아* 다음 섹션의 토대가 되는가
- 회귀 사례: 섹션 3이 섹션 2와 무관한 새 주제로 점프
- score 2 이하: action="reorder_sections" 또는 "add_bridge_paragraph"

**(4) 차트 횡적 중복 (Chart Cross-Redundancy)**
- 차트 두 개 이상이 *같은 사실을 다른 그림으로* 보여주는가
- ChartCritic 은 차트 하나씩만 봐서 *못 잡음* — Desk 가 처음 보는 항목
- score 2 이하: action="drop_chart_N"

**(5) Watch_signal 의 예측력 (Watch Signal Predictivity)**
- 모든 signal 이 "ambiguous" 면 *예측 가치 0*
- 적어도 하나는 confirms_base 또는 rejects_base 로 시나리오 분기 결정 도구여야 함
- score 2 이하: action="rewrite_watch_signals"

**(6) 출처-주장 비율 (Source-Claim Ratio)**
- 강한 주장 (claim_type=judgment 또는 prediction) 의 evidence 충분한가
- 회귀 사례: "5년 내 위기 가능성 70%" 같은 강주장에 출처 1건만
- score 2 이하: action="add_source_or_soften_claim"

**(7) Smell test (출판 적격성)**
- Foreign Affairs / FT / Bloomberg 데스크가 이 보고서를 *그대로 발행* 할 것인가
- 정량화 어려운 종합 판단. score 1~2면 즉시 hold 또는 kill 후보
- score 2 이하: action="kill_or_major_revision"

### 8.4 (나) 페이지 프루프 검수 — Visual 8-rubric (NEW)

각 항목 1~5 점수. score ≤ 2 면 issue 발생. *입력은 렌더된 HTML 의 스크린샷 (3~5장)*. Vision LLM (Opus 4.7) 이 *눈으로 보고* 판정.

이 rubric 이 catch 하는 것은 JSON 검사로는 *근본적으로 못 보는* 결함 — `docs/CHART_RENDERING_ANTIPATTERNS.md` 의 13개 중 시각 의존 회귀 (AP-5, 6, 10, 11) 와 새로 발견될 시각 결함.

**(시각-1) 차트 라벨/축 잘림**
- 차트 라벨이 박스 밖으로 나가거나, 축 텍스트가 카드 경계로 잘리는가
- AP-5 catch (라벨 zone 밖 잘림)
- score 2 이하: action="rerender_chart" 또는 "drop_chart"

**(시각-2) 지도 범위·중심 적절성**
- 보고서 본문이 다루는 지역이 지도 frame 안에 *명확히 보이는가*
- 너무 작거나 (호른 아프리카 보고서인데 유라시아 전체가 보임) 너무 frame 가장자리에 위치하지 않는가
- AP-9 catch (zoom/center 디폴트 의존)
- score 2 이하: action="adjust_map_zoom_center"

**(시각-3) 데이터 마크 viewport 안**
- 차트의 모든 데이터 점·막대·노드가 visible frame 안에 보이는가
- frame 밖으로 나간 데이터 점 catch (AP-12 의 시각 검증)
- score 2 이하: action="adjust_chart_scale" 또는 "drop_chart"

**(시각-4) 텍스트 오버플로우**
- 본문이 인접 요소로 흘러넘치거나, 헤드라인이 컨테이너에서 wrap 안 되고 잘리는가
- pull_quote / kicker / lede 같은 강조 요소가 *부자연스러운* 위치에 잘려있는가
- score 2 이하: action="adjust_layout" 또는 "shorten_text"

**(시각-5) 색상 톤 일관성**
- 차트·카드·헤더 색이 V5 design token (Editorial Cream 또는 Burgundy Mono) 과 *시각적으로* 일치하는가
- 한 차트만 다른 톤이거나, 다크 카드에 다크 텍스트 같은 가독성 결함이 있는가
- AP-11 의 *시각 확인* (CSS variable resolution 실패 catch)
- score 2 이하: action="reapply_theme"

**(시각-6) 본문-차트 시각 정합**
- 차트가 인접 본문 단락 옆에 *명확히 짝지어져* 보이는가
- 차트 위·아래 공백이 부자연스러워 떠다니는 느낌인가, 다음 섹션과 합쳐 보이는가
- score 2 이하: action="adjust_layout"

**(시각-7) 모바일 반응형 깨짐**
- 375px 폭 mobile_full 스크린샷에서 레이아웃이 깨지거나 차트가 잘리는가
- fact_grid 가 모바일에서 어색하게 stacking 되는가
- score 2 이하: action="adjust_responsive_breakpoints"

**(시각-8) 전체 미적 균형**
- 페이지 전체를 멀리서 봤을 때 *시각적 노이즈·공허·과밀 구간* 이 있는가
- 정량화 어려운 종합 미적 인상. Foreign Affairs 데스크가 page proof 마지막에 보는 항목이다.
- score 2 이하: action="major_layout_revision"

### 8.5 헤드리스 브라우저 캡쳐 파이프라인

Desk Editor 호출 *전* 단계. ReportSynthesizer 가 HTML 을 디스크에 쓴 후, Playwright 가 캡쳐 → Desk 에 전달.

**의존성 (V5 신규):**
```python
# requirements.txt
playwright>=1.40
# 설치: python -m playwright install chromium
```

**캡쳐 명세 (`src/visual/capture.py` 신설):**
```python
async def capture_proofs(html_path: str, exhibit_count: int) -> list[ScreenshotCapture]:
    """Playwright 로 5장 (or fewer) 캡쳐.

    1장: desktop_full   1280×ScrollHeight  — 페이지 전체 스크롤 후 풀 캡쳐
    1장: mobile_full     375×ScrollHeight  — mobile breakpoint
    1~3장: chart_closeup  각 Exhibit 의 .exhibit_card  scroll-into-view + close-up
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ...
```

**캡쳐 정책:**
- 보고서당 최소 2장 (desktop + mobile), 최대 5장 (+ chart close-up 3장).
- chart close-up 은 *첫 3개 Exhibit 만* (시각 결함 발견율 충분, 토큰 절감).
- 캡쳐 timeout 10초. 실패 시 *desktop_full 만이라도* 확보한 후 진행한다.
- 캡쳐 자체 실패 시 Visual rubric 검사 skip + telemetry 로 `proof_capture_failed` 기록 + Logical rubric 만으로 판정한다.

**Anthropic API 호출 시 image content blocks:**
```python
content_blocks = [
    {"type": "text", "text": json.dumps(composed.model_dump())},
]
for shot in screenshots:
    content_blocks.extend([
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": shot.image_b64}},
        {"type": "text", "text": f"[Screenshot: {shot.role} — {shot.label} ({shot.width}×{shot.height})]"},
    ])
```

이미지당 ~1.5K 토큰. 평균 4장 = 6K 추가. Phase 7 총 비용: 7K (logical only) → 13~15K (logical + visual).

### 8.6 KILL 발화 기준 — 자동 (논리 + 시각 통합)

다음 중 *둘 이상* 충족 시 **자동 KILL** (Desk 의 LLM 판단 X, 결정적 규칙):

```python
KILL_RULES_LOGICAL = {
    "insufficient_sources":       len(context.sources) < 2,
    "insufficient_prose":         total_chars < target_total * 0.5,
    "contradiction_overload":     len(contradictions) > len(sections) / 2,
    "watch_signals_useless":      all(s.direction == "ambiguous" for s in watch_signals)
                                  or len(watch_signals) == 0,
    "core_intent_unanswered":     not any(
                                      _section_addresses(s, strategy.user_intent)
                                      for s in sections
                                  ),
}

KILL_RULES_VISUAL = {  # NEW — Phase 7 visual proof 자동 발화
    "majority_charts_visually_broken":  visual_fail_count(charts) >= len(charts) * 0.5,
    "mobile_layout_broken":             visual_rubric_score("시각-7") <= 1,
    "theme_token_mismatch":             visual_rubric_score("시각-5") <= 1,
}
# LOGICAL + VISUAL 합쳐서 둘 이상 True 면 자동 KILL
```

LLM-driven KILL (Desk 가 7+8 rubric 점검 후 score 1점 다수 또는 smell test fail 시) 도 별도 가능. 자동 + LLM 합산.

### 8.7 KILL 처리 — *조용히 실패하지 않음*

KILL 판정 시:
1. **Cloudflare 배포 진행 X** — HTML 생성은 디버그용으로 reports/dev/ 에만 보존.
2. **텔레그램 봇이 사용자에게 명시적 알림**:
   ```
   ❌ 보고서 발행 거부 (Desk Editor KILL)

   사건: <event_name>
   사유: <kill_reason 1줄>
   세부: <어느 KILL_RULE 발화 또는 어느 rubric fail>

   권장: 더 많은 사실 자료 또는 다른 각도 재시도.
   ```
3. **텔레메트리 기록** — `RunTelemetry.kill_event` 에 사유·rubric scores 보존.
4. **Watchlist 등록 X** — KILL 된 보고서의 watch_signals 는 SQLite 에 INSERT 안 함.

이는 v4.5.7 의 "어떻게든 발행 + minimal fallback" 과 정반대 정책. *낮은 품질이면 차라리 안 내보낸다*.

### 8.8 HOLD 처리 — 1회 재호출

HOLD 판정 시 Desk 의 issues 리스트에 따라 *해당 lower editor 만* 재호출:

```python
HOLD_DISPATCH = {
    # 논리 issue → composer / editor / chart_critic 재호출
    "rewrite_headline":           ("composer", "headline_only"),
    "rewrite_deck":               ("composer", "deck_only"),
    "rewrite_conclusion":         ("editor", "section_last"),
    "reorder_sections":           ("editor", "structural"),
    "add_bridge_paragraph":       ("editor", "specific_section"),
    "drop_chart_N":               ("chart_critic", "force_drop"),
    "rewrite_watch_signals":      ("composer", "signals_only"),
    "add_source_or_soften_claim": ("composer", "section_specific"),

    # 시각 issue → renderer / chart_critic / layout 재호출 (Phase 7 신규)
    "rerender_chart":              ("renderer", "chart_only"),         # Vega-Lite spec 재렌더 (label rotation 등 자동 조정)
    "drop_chart":                  ("chart_critic", "force_drop"),     # 차트 통째로 제거
    "adjust_map_zoom_center":      ("visual_planner", "map_only"),     # 지도 spec 재생성
    "adjust_chart_scale":          ("renderer", "chart_only"),         # 스케일 재계산
    "adjust_layout":               ("layout_typesetter", "specific_section"),
    "shorten_text":                ("editor", "section_specific"),
    "reapply_theme":               ("renderer", "css_rebuild"),        # CSS variable 재주입
    "adjust_responsive_breakpoints": ("layout_typesetter", "responsive_review"),
    "major_layout_revision":       ("layout_typesetter", "full_rerun"),
}
```

전체 재실행 X. 재호출 비용 통제 — 평균 추가 ~2K 토큰. *시각 issue HOLD 의 경우 재캡쳐 (~6K 추가) 도 발생* — 합계 평균 ~3K (시각 HOLD 비율 고려한 amortize).

**최대 1회 재호출** (무한 루프 방지). 2번째 HOLD 시 *경고 표시한 채로 publish*:
```
⚠ 발행됨 (Desk 1차 hold 후 재집필 시도, 2차 hold 잔존)
   미해결: <남은 issue 1줄> (논리 또는 시각)
```

KILL 은 재호출 없이 즉시 종료.

### 8.9 publish 분포 — 운영 측정 지표

Desk 가 *너무 느슨해도 너무 보수적이어도* 안 됨. 첫 50건 운영 후 분포:

| 분포 | publish | hold | kill | 진단 |
|------|---------|------|------|------|
| 이상적 | 60~80% | 15~30% | 0~5% | Desk 가 일하고 있음 |
| 통과 도장 | >95% | <5% | 0% | rubric 강화 필요 |
| 발행 거부기 | <50% | 30%+ | 10%+ | composer/editor 부터 점검 |
| Hold 무한 루프 | (HOLD 후 재집필 결과 또 HOLD) | — | — | 1회 cap 작동 확인 |

운영 1주일 후 분포 측정 → rubric prompt tuning.

### 8.10 인수 기준 (Phase 7 Acceptance)

- DeskEditor 호출이 모든 lower phase *이후* 마지막에 추가되어야 한다.
- 자동 KILL_RULES (논리 5종 + 시각 3종) 모두 회귀 테스트 (`tests/test_desk_kill_rules.py`).
- Playwright 캡쳐 파이프라인 동작 검증 — desktop_full / mobile_full / chart_closeup 3종 캡쳐가 성공해야 한다.
- 캡쳐 자체 실패 시 graceful degrade — Logical rubric 만으로 판정한 후 telemetry 에 기록한다.
- KILL 발생 시 Cloudflare 배포 차단 + 텔레그램 사용자 알림 동작을 검증한다.
- 첫 50건 운영 후 publish/hold/kill 분포가 위 §8.9 의 *이상적 범위* 안에 있어야 한다.
- HOLD 재호출 1회 cap 작동 + 2차 HOLD 시 publish-with-warning 동작을 검증한다.
- 시각 issue 의 HOLD 후 재캡쳐 → Desk 재호출 시퀀스를 검증한다.
- **YK 의 캡쳐 → 텔레그램 → AI 재작성 사이클이 *V5 출시 후 30일간* 5건 이하** (목표). 5건 초과 시 Visual rubric 항목 추가 (§8.12 self-improving).

### 8.11 Phase 7 가 *왜 마지막* 인가 — 위계

데스크는 *모든 부분 편집* 이후에 봐야 의미 있음:

- Editor 가 글 다듬기 *전* 에 데스크 호출 → 군더더기 본문에 대해 데스크가 점수 낮게 줌 → Editor 가 어차피 다듬을 부분에 대해 hold 신호. 무의미하다.
- ChartCritic 이 깨진 차트 drop *전* 에 데스크 호출 → 데스크가 깨진 차트 보고 또 hold. 중복된다.
- Layout 결정 *전* 에 데스크 호출 → 미완성 패키지 평가. 부정확하다.
- 렌더링 *전* 에 데스크 호출 → 시각 결함 자체를 못 봄. 페이지 프루프 검수가 불가능하다.

따라서 Phase 1~6 + Renderer + Capture 모두 완료한 *완성된 패키지 + 캡쳐* 만 데스크 입력. 이 위계가 부서 내 데스크 모델 그대로.

### 8.12 Self-improving rubric — YK 가 잡은 결함은 새 항목으로 누적

**한계 솔직 인정:** Vision LLM 도 *완벽한 시각 판단* 은 못 함. 사람만큼 미묘한 미적 결함은 놓칠 수 있음. 따라서:

- **1차 검수 (자동):** Desk Visual 이 명백한 결함 (잘림, 깨짐, frame 밖, 색 어긋남) 자동 catch — 목표 80%.
- **2차 검수 (YK):** YK 가 발행된 보고서 검토. 진짜 미묘한 이슈만 fix. 목표 ≤ 5%.
- **3차 (피드백 루프):** YK 가 catch 한 결함 → `docs/DESK_VISUAL_RUBRIC.md` 에 *append-only* 누적 → 다음 Desk Editor 호출 시 system prompt 에 자동으로 포함시킨다.

```
docs/DESK_VISUAL_RUBRIC.md  (V5 신설, append-only)
─────────────────────────────────────────────────
## (시각-9) — 추가됨 v5.0.3 (2026-06-12)
- 증상: 차트 제목과 본문 thesis 가 *논리적으로는 같은데 표현이 어긋나* 어색해 보인다.
- 사례: <YK 가 보낸 캡쳐의 fingerprint 또는 보고서 ID>
- 검수 기준: 차트 제목과 본문 단락 thesis 가 *어휘 또는 톤* 에서 1줄 거리 안에 있어야 한다.

## (시각-10) — 추가됨 v5.0.5 (2026-07-03)
- 증상: ...
```

이 rubric 이 누적되면서 Desk Editor 의 시각 검수 지점이 *시간이 갈수록 정밀해지는* self-improving 시스템. 첫 시즌 (1~3개월) 운영 후 평가 — YK catch 빈도가 시간에 따라 줄어드는지 확인.

이 구조가 v4.5.7 의 "사용자 발견 → 코드 패치 → 다음 사용자 발견" 의 reactive 루프와 다른 점: *발견된 결함이 시스템의 검수 능력으로 누적* 됨. 같은 결함이 두 번째 보고서에서 다시 발생하면 자동으로 catch.

---

## 17. Phase 8 — Strategic Mode (의사결정 보조 모드)

> **목적.** 분석 모드와 *근본적으로 다른* 보고서 종류 (전략 의사결정 보조) 를 시스템 안에 정식 모드로 도입한다. 사용자가 "*X 를 한다고 했을 때 A·B·C 를 고려했을 때 어떤 전략을 취해야 하지?*" 라고 질의할 때, 옵션 enumeration + 평가 기준 매트릭스 + 권고 + Pre-mortem + 감시 신호로 *처방적 보고서* 를 생성한다.
>
> **비목적.** v3 의 `decision_brief` archetype 부활은 아니다. archetype 은 *고정 섹션 템플릿* 이었다. Phase 8 의 전략 모드는 *intent 분류 + composer 시스템 프롬프트 확장 + 신규 layout primitive 1종* 이다. 섹션 수와 순서를 composer 가 자율 결정한다 (단 옵션 ≥ 3 등 강제 항목은 있다).

### 9.1 분석 모드와 무엇이 다른가

두 모드는 보고서의 *지향점* 이 정반대이다.

| 차원 | 분석 모드 (Analytical) | 전략 모드 (Strategic) |
|------|------------------------|------------------------|
| 시제 | 후행적 (과거 → 현재 분석) + 예측 | 선행적 (미래 행동 결정) |
| 자세 | 서술적 ("X 가 일어났다") | 처방적 ("X 를 해야 한다") |
| 핵심 산출 | 시나리오 + 감시 신호 | 옵션 + 권고 + 감시 신호 |
| user_intent | what_happened, why_happened, what_next 등 | what_to_do (전용) |
| 시각화 강조 | timeline, network, choropleth | decision matrix, bubble (impact × feasibility) |
| 결정 매트릭스 | 부수적 | *필수* |
| 권고 | 흐릿하게 본문에 흩어짐 | 명시적 별도 섹션 |
| Pre-mortem | 선택적 | *deep 모드에서 필수* |

v4.5.7 는 사용자가 전략 질의를 보내도 분석 모드로 처리한다. 결과 보고서는 *옵션이 명시적으로 나열되지 않고, 평가 기준이 사용자 명시 A·B·C 와 매칭되지 않으며, 결정 매트릭스가 그려지지 않고, 권고가 본문에 흩어져 어색한 형태* 로 나온다. Phase 8 가 이 회귀를 해결한다.

### 9.2 전략 질의 감지 — Telegram bot + ContextAnalyst

전략 모드 진입 경로는 세 가지이다.

(가) **명시적 prefix.** 사용자가 `?전략 <질의>` 또는 `/strategy <질의>` 로 호출한다. 가장 명확하고 비용이 들지 않는다.

(나) **패턴 매칭.** Telegram bot 의 `_classify_input` 단계에서 결정적 키워드를 매칭한다.

```python
STRATEGIC_PATTERNS = [
    r"어떤 전략",
    r"어떻게 해야",
    r"어떤 (선택|결정|판단|길)",
    r"취해야 (하|할)",
    r"(고려|반영)했을 때.{0,30}(전략|결정|선택)",
    r"옵션.{0,10}(평가|비교|선택)",
    r"(어떤 길|어디로|어느 방향)으로",
]

def detect_strategic_intent(user_input: str) -> bool:
    """결정적 패턴 매칭으로 전략 질의를 감지한다."""
    return any(re.search(p, user_input) for p in STRATEGIC_PATTERNS)
```

(다) **LLM intent classifier (fallback).** 패턴이 모호하면 ContextAnalyst 가 사실 수집과 함께 intent 를 분류한다 (추가 LLM 호출 없이 기존 ContextAnalyst 호출에서 함께 처리한다). 결과 user_intent 가 `what_to_do` 이면 전략 모드로 분기한다.

### 9.3 Composer 의 전략 모드 system prompt 확장

기존 `narrative_composer.py:SYSTEM_PROMPT` 를 베이스로 사용하되, 전략 모드일 때 다음 지시를 *추가* 한다.

```
=== 전략 모드 추가 지시 (strategic_mode=True 일 때만) ===

본 보고서는 사용자의 *의사결정* 을 보조한다. 분석 보고서가 아니다.

다음 7개 섹션 구조를 *강한 디폴트* 로 사용한다 (사건 성격에 따라 자율 변형 가능하나
옵션 ≥ 3개 + 권고 명시는 강제이다):

1. 결정 컨텍스트 — 무엇을 결정하는가, 누가 결정하는가, 언제까지, 되돌릴 수 있는가
2. 옵션 도출 — 3개 이상 5개 이하. *2개 미만 금지* (이분법적 사고 차단).
                *6개 이상 금지* (분석 마비 차단). 각 옵션은 한 줄 요약 + 핵심 행동.
3. 평가 기준 — 사용자가 명시한 기준 (A, B, C 등) 을 그대로 보존하면서, 누락된 중요
              기준을 추론해 추가한다 (예: 비용, 시간, 가역성, 정치적 비용, 평판 영향).
4. 옵션 × 기준 매트릭스 — 시각화 *필수*. Vega-Lite heatmap 또는 점수표 또는
                         bubble chart (영향 × 실현가능성).
5. Pre-mortem — 옵션별 실패 시나리오. "이 옵션이 실패한다면 *어떤 이유로* 실패할까?"
                옵션당 2~3개 실패 모드 + 각 실패의 leading indicator.
                deep 모드에서 *필수*.
6. 권고 — 한 옵션을 명시적으로 선택한다. "옵션 N 을 권고한다." 형식.
         근거 3개 이상 (어느 기준에서 우위인지). *권고 부재는 KILL 사유*.
7. 감시 신호 — 권고가 *틀렸다고 판단되는 조건* 을 명시한다. "X 가 발생하면 옵션 N 을
              포기하고 옵션 M 으로 전환한다" 형식.

핵심 어법 규칙:
- 모호함 금지. "고려해야 할 수도 있다" 같은 보수 어법보다 "옵션 N 이 옵션 M 보다 X 점
  앞선다" 같은 명료한 표현을 우선한다.
- 권고를 흐리지 않는다. "각 옵션에 장단점이 있다" 식의 봉합은 KILL 사유이다.
- 사용자가 명시한 기준 A·B·C 를 *반드시* 평가 매트릭스의 행 또는 열로 사용한다.
  추가 추론 기준은 명시적 표시 (예: "기준 D — 추론").
```

### 9.4 신규 layout primitive — `decision_brief`

분석 모드의 9종 layout 외에 전략 모드 *전용* 으로 1종을 추가한다. 이 layout 은 분석 모드에서는 사용하지 않는다 (모드 분리 강제).

| layout_id | 시각 효과 | 적용 위치 |
|-----------|-----------|-----------|
| `decision_brief` | 결정 컨텍스트가 hero 영역, 옵션이 numbered cards 그리드, 매트릭스가 full-width, 권고가 signature_summary 위치 | 전략 모드 보고서 전용 |

이 layout 의 추가는 AP-V5-3 (layout primitive 추가 금지) 와 충돌하지 않는다. AP-V5-3 는 *분석 모드 9종의 동결* 을 의미한다. 전략 모드의 `decision_brief` 는 별도 vocab 이다. 단 *전략 모드 1종으로 끝* 이다 — 전략 모드도 layout 추가는 더 이상 받지 않는다.

### 9.5 필수 시각화 — 전략 모드 전용

전략 모드 보고서는 다음 시각화를 *최소 1개 이상* 포함한다 (Phase 6 Chart Critic 이 강제한다).

(가) **결정 매트릭스 (필수).** Vega-Lite heatmap 또는 점수표. 옵션 (행) × 기준 (열) 의 셀이 점수 (예: 1~5) 또는 정성 등급 (강/중/약). 본문 권고가 이 매트릭스의 어느 셀들에서 도출되는지 *직접 인용* 해야 한다 (Phase 6 Critic 의 질문 4번 적용).

(나) **옵션 비교 bubble chart (권고).** x = 영향 (impact), y = 실현가능성 (feasibility), size = 비용 또는 위험. 4분면이 즉시 시각화된다.

(다) **Pre-mortem fishbone (deep 모드 권고).** 권고 옵션의 실패 원인을 fishbone diagram 으로 분해. d3 또는 Vega-Lite 로 구현 가능하다.

### 9.6 KILL 기준 추가 — 전략 모드 전용

분석 모드의 KILL_RULES (논리 5종 + 시각 3종) 는 그대로 적용하면서, 전략 모드는 다음을 추가로 발화한다.

```python
KILL_RULES_STRATEGIC = {
    "options_too_few":          len(strategic_report.options) < 3,
    "no_decision_matrix":       not has_decision_matrix(strategic_report.exhibits),
    "recommendation_absent":    not strategic_report.recommendation
                                or len(strategic_report.recommendation.rationale) < 50,
    "premortem_missing_deep":   mode == "deep" and not strategic_report.premortems,
    "criteria_not_user_aligned": not all_user_criteria_present(
                                     strategic_report.criteria,
                                     user_provided_criteria,
                                 ),
}
```

전략 모드는 발행 기준이 더 엄격하다. 옵션이 2개 이하이면 (이분법) 즉시 KILL. 권고가 없으면 (전략 보고서의 핵심이 권고이다) 즉시 KILL. 사용자가 명시한 기준 A·B·C 가 매트릭스에 누락되어 있으면 KILL. 이 조건들은 *단독으로도* KILL 발화한다 (분석 모드의 "둘 이상 충족" 규칙과 다르다).

### 9.7 인수 기준 (Phase 8 Acceptance)

- 전략 질의 패턴 매칭 정확도 ≥ 90% 이다 (수동 라벨링 30건 검증).
- 전략 모드 보고서의 옵션 enumeration 은 100% 보고서에서 ≥ 3 개이다.
- 결정 매트릭스가 100% 전략 보고서에 등장한다 (Phase 6 Critic 가 강제 검증한다).
- 권고가 100% 전략 보고서에서 명시적이다 ("옵션 N 을 권고한다" 형식).
- 사용자 명시 기준 (A, B, C) 의 매트릭스 누락 사례 0건이다.
- v4.5.7 가 전략 질의를 분석 모드로 잘못 처리했던 사례 (history 5건) 를 V5 가 모두 전략 모드로 라우팅하고 강한 결정 매트릭스 + 명시적 권고로 재생성한다.

### 9.8 한계 — 전략 모드가 *못 하는* 것

솔직히 짚어둔다. 전략 모드는 *제한적인 의사결정 보조* 이다.

- LLM 의 평가 점수는 결국 *학습 데이터 기반 추론* 이다. 사용자의 진짜 utility function 은 모른다. 따라서 매트릭스 점수를 *최종 결정* 으로 받지 말고 *생각의 출발점* 으로 사용해야 한다.
- 권고는 *현재 시점의 일반론적 우위* 를 가리킨다. 사용자의 사적 정보 (예: 평판 자산, 비공개 자원, 정치적 동맹) 를 반영하지 못한다. 권고 채택 전 사용자가 그 정보를 더해 재평가해야 한다.
- 실제 결정에는 LLM 이 잡지 못하는 *암묵 지식* 이 큰 부분을 차지한다. 이 시스템은 *체계적 사고를 보조* 할 뿐 *결정을 대신* 하지 않는다.

이 한계를 보고서 footer 에 명시한다 ("본 권고는 의사결정 보조용이다. 최종 판단은 사용자의 책임이다.").

---

## 18. Phase 8A — Strategic Mode Contract (강한 분리 + 명시 prefix)

### 18.1 What

Phase 8 (Strategic Mode) 의 보고서 구조와 라우팅을 *더 강하게* 분리한다. 전략 보고서를 *분석 보고서의 변형* 이 아닌 *결정 문서* 로 명시화한다.

### 18.2 명시 Prefix 라우팅 — LLM intent classifier 보다 우선

Phase 8 의 전략 모드 감지가 LLM intent classifier 만으로는 불안정하다. 텔레그램에서 짧게 던지는 질의는 모호하기 쉽다. 사용자가 *명시 prefix* 로 모드를 직접 선언하는 경로를 우선시한다.

```
?전략 ...   → strategic mode (Phase 8)
?분석 ...   → analytical mode (default)
?예측 ...   → forecast mode (analytical 의 하위, ResearchDirector 가 forecast method 우선)
?비교 ...   → comparative mode (analytical 의 하위)
?지도 ...   → geo-priority mode (visual_constraints 에 map_required)
?짧게 ...   → fast mode 강제
?심층 ...   → deep mode 강제
```

prefix 가 없으면 ContextAnalyst + LLM intent classifier 가 fallback 으로 분류한다. 모호한 경우 기본값은 *분석 모드* 이다 (AP-V5-23 유지).

### 18.3 Strategic Report 의 *필수 출력 구조* — 8개 항목

Phase 8 의 7-section 디폴트보다 더 강한 강제 항목을 박는다.

```python
class StrategicReport(BaseModel):
    decision_statement: str                  # 1. 사용자가 지금 내려야 하는 결정 한 문장
    options: list[StrategicOption]           # 2. 최소 2개, 최대 5개. 0개면 hold ("전략 질의 성립 불가").
    criteria: list[Criterion]                # 3. 사용자 명시 A/B/C + 추론 기준
    constraints: Constraints                 # 4. 시간, 비용, 리스크 허용도, 실행 권한, 가역성
    decision_matrix: DecisionMatrix          # 5. 옵션 × 기준 점수 + 근거 + 민감도
    recommendation: Recommendation           # 6. 단일 권고 + 예외 조건 + 실행 순서
    kill_switch_conditions: list[str]        # 7. 권고 폐기 신호
    action_plan_30_60_90: ActionPlan         # 8. 30/60/90일 실행계획 — *필수*

class StrategicOption(BaseModel):
    label: str
    one_line_summary: str
    core_actions: list[str]                  # 옵션의 핵심 행동
    pre_mortem: list[FailureMode]            # 옵션별 실패 시나리오 (deep 모드 필수)

class Constraints(BaseModel):
    time_horizon: str                        # "3개월" / "1년" 등
    budget_ceiling: str = ""                 # "₩50억 이내" 등 (모를 경우 빈 문자열)
    risk_tolerance: Literal["low", "medium", "high"]
    execution_authority: str                 # "본인 권한" / "임원 승인 필요" 등
    reversibility: Literal["reversible", "partial", "irreversible"]

class DecisionMatrix(BaseModel):
    options: list[str]                       # 옵션 라벨 (StrategicOption.label 과 일치)
    criteria: list[str]                      # Criterion.name 과 일치
    scores: list[list[float]]                # options × criteria 점수
    rationale: list[list[str]]               # options × criteria 근거 (점수 정당화)
    sensitivity: dict[str, str] = {}         # 가중치 변동 시 권고 변화 분석

class ActionPlan(BaseModel):
    """30/60/90일 실행계획 — 전략 보고서 *필수*. 분석 보고서에는 없다."""
    days_30: list[ActionItem]                # 즉시 착수 항목
    days_60: list[ActionItem]                # 60일까지 검증·확장 항목
    days_90: list[ActionItem]                # 90일까지 평가·결정 분기점

class ActionItem(BaseModel):
    action: str
    owner: str = ""                          # "본인" / "팀" / "외부 vendor" 등 (모를 경우 빈 문자열)
    success_metric: str
    failure_signal: str
```

### 18.4 KILL 기준 강화 — 단독 발화

Phase 8 의 KILL_RULES_STRATEGIC 에 추가 항목.

```python
KILL_RULES_STRATEGIC_ADDITIONAL = {
    "decision_statement_missing":     not strategic_report.decision_statement,
    "action_plan_missing":            not strategic_report.action_plan_30_60_90,
    "kill_switch_missing":            len(strategic_report.kill_switch_conditions) == 0,
    "matrix_score_uniform":           _is_matrix_uniform(decision_matrix.scores),  # 모든 옵션이 같은 점수
    "options_truly_impossible":       len(strategic_report.options) == 0,           # 0개 → "전략 질의 성립 불가" hold
}
```

옵션 0개의 경우는 *KILL 이 아니라 hold* 로 처리한다. 사용자에게 "이 질의는 옵션 도출이 불가능합니다. 질의를 더 구체화하거나 분석 모드 (`?분석`) 로 재시도하시기 바랍니다." 안내. 검수자의 지적 (기존 AP-V5-18 의 "옵션 < 3 → KILL" 이 너무 경직됐다) 을 반영한 정책 완화이다.

### 18.5 인수 기준 (Phase 8A Acceptance)

- 명시 prefix 7종이 텔레그램 봇에서 동작한다.
- 전략 보고서가 8개 필수 출력 항목을 모두 포함해야 한다 (decision_statement, options, criteria, constraints, decision_matrix, recommendation, kill_switch_conditions, action_plan_30_60_90).
- ActionPlan 의 30/60/90 일 항목이 *모두 비어 있지 않아야* 한다.
- 옵션 0개 시 hold 처리 + 사용자 안내 동작이 검증되어야 한다.
- Phase 8 의 기존 AP-V5-18 (옵션 <3 KILL) 은 "옵션 0개 hold" 로 완화 갱신한다 (§23 참조).

---

## 19. 시각 톤 정본 (V5 Design Tokens — `samples/chart_map_mono_compare.html` SSOT)

> **이 섹션은 변경 금지.** Phase 1~7 어느 단계에서도 색·폰트·간격·라인 무게를 *임의로* 바꾸지 않는다. 코드 에이전트는 이 토큰을 `:root` CSS 변수와 Vega-Lite theme config 양쪽에 정확히 동일하게 적용.

### 9.1 테마 라우팅 — 2종 고정

| theme_id | 적용 카테고리 | 인상 |
|----------|---------------|------|
| `editorial` (default) | 그 외 모든 사건 — 정책·기술·시장·산업·인물 분석 | 차분한 cream 위 진한 brown 본문 + terracotta accent. Atlantic 스타일. |
| `burgundy` (specialty) | 위기·분쟁·재난 — geopolitical-conflict / war / accident_forensic | 어두운 burgundy 위 cream 본문 + gold accent. Foreign Affairs 스타일. |

`src/lens_policy.py:select_theme()` 의 라우팅 규칙은 보존. *2종 외* 추가 X.

### 9.2 Editorial Cream — 정본 토큰

```css
:root[data-theme="editorial"] {
  /* surfaces */
  --bg:           #F2EBDB;   /* 보고서 배경 cream */
  --card:         #ECE3D0;   /* 카드 / 차트 배경 */
  --border:       #D4C8B0;
  --border-light: #E2D8C0;

  /* type */
  --text:   #1F1814;   /* 본문 진한 brown */
  --muted:  #6B5C4A;   /* 부제 / caption */
  --faded:  #A89A7E;   /* 매우 약한 라벨 */

  /* accent — terracotta */
  --accent:  #B05A38;  /* 강조 / risk crisis / arc primary */
  --up:      #4A6B3E;  /* 상승 / 우호 */
  --down:    #8B2A2A;  /* 하락 / 충돌 (악센트로만) */

  /* series — 차트 4색 + dash 패턴 */
  --series-1: #1F1814;  /* solid */
  --series-2: #B05A38;  /* dash 5,3 */
  --series-3: #4A6B3E;  /* dash 2,3 */
  --series-4: #6B5C4A;  /* dash 1,3 */

  /* map */
  --map-land:     #F2EBDB;
  --map-water:    #DFD3B8;
  --map-boundary: #1F1814;
}
```

### 9.3 Burgundy Mono — 정본 토큰

```css
:root[data-theme="burgundy"] {
  --bg:           #2A0F18;   /* 어두운 burgundy */
  --card:         #371721;
  --border:       #5A2832;
  --border-light: #371721;

  --text:   #EFE5D1;   /* cream 본문 */
  --muted:  #A88E7A;
  --faded:  #6B5040;

  --accent:  #D4A858;   /* gold */
  --up:      #A8B582;
  --down:    #C9837A;

  --series-1: #EFE5D1;
  --series-2: #D4A858;
  --series-3: #A8B582;
  --series-4: #C9837A;

  --map-land:     #2A0F18;
  --map-water:    #1A0810;
  --map-boundary: #EFE5D1;
}
```

### 9.4 폰트 — 3종 트리플렛 고정

```html
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,700;6..72,800&family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
```

| 용도 | 폰트 | 크기 가이드 |
|------|------|-------------|
| 헤드라인·섹션 제목·차트 제목 | `Newsreader, 'Noto Serif KR', serif` | 영문 ≥18px, 한글 ≥16px |
| 본문·UI·차트 라벨 | `'IBM Plex Sans KR', sans-serif` | 11~13px |
| 수치·일련번호·코드 | `'IBM Plex Mono', monospace` | 9~11px (kicker, exhibit-label) |

### 9.5 차트 시각 규칙 (mono guide §6 강화)

- 단일 액센트만 색상으로 사용. 나머지는 series-1~4 + dash 패턴으로 처리한다.
- 영역 채움은 45° 사선 패턴 (`patternStroke` 토큰 사용). 단색 채움 를 금지한다.
- 차트당 annotation 합계 ≤ 3 (vline 2 + hline 1, 또는 band 1 + point 2 등).
- 이모지 마커 금지 (geopolitical 카드의 emoji 도 V5 에서는 mono 라벨로 대체).
- 그리드 라인 stroke 0.5px, dash 2,3, opacity 0.55. 절대 진하지 않게 적용한다.

### 9.6 디자인 토큰 SSOT 위치

```
samples/chart_map_mono_compare.html  ← 사람-친화 시각 레퍼런스
src/templates/themes/editorial.css   ← :root[data-theme="editorial"] 토큰 (신설)
src/templates/themes/burgundy.css    ← :root[data-theme="burgundy"] 토큰 (신설)
src/visual_builder.py:V5_THEME       ← Vega-Lite config 토큰 (신설, 위 CSS 와 1:1 동기)
```

세 곳이 *byte-equal* 일치 — drift 검증 회귀 테스트 추가 (`tests/test_design_token_drift.py`).

---

## 20. 마이그레이션 전략

### 20.1 in-place vs parallel directory

V5 는 v4.5.7 기반의 **in-place evolution** 으로 진행한다 (v3 → v4 처럼 paradigm shift 가 아니다). 다만 외부 검수 반영으로 *추가 모듈* 의 수가 9개 늘어났다 (Phase 0/0B/0C/1A/2A/2B/6A/7A/8A). 이유는 다음과 같다.

- NarrativeComposer 의 시스템 프롬프트만 *Drafting only* 로 축소하면 된다. 모듈을 통째로 폐기하지 않는다.
- ResearchDirector / Editor / VisualPlanner / LayoutTypesetter / ChartCritic / DeskEditor 는 *추가* 모듈이다. 기존 모듈을 건드리지 않는다.
- visual_builder.py 의 11개 함수는 render_vega_lite() 1개 어댑터로 점진 교체한다 (한 type 씩 마이그레이션한 후 enum 을 폐기한다).
- Phase 8 의 Strategic Mode 는 composer system prompt 분기 + Telegram bot 패턴 매칭 + 신규 layout primitive 1종 추가로 구현한다. 기존 분석 모드 코드 경로를 건드리지 않는다.
- Phase 0 의 SSOT Repair 는 *코드 변경 없이 문서·메타데이터만* 정렬하는 작업이다.

### 20.2 4-Tier 단계별 commit 전략 — 외부 검수 반영 재배치

기존 plan 의 Phase 1 → 2 → 3 → ... → 8 순서를 *상류 우선 4-Tier* 로 재배치했다. Tier 1 미완성 상태로 Tier 2 또는 Tier 3 에 진입하지 않는다.

**Tier 1 — 토대 (필수 선결).**

```
v4.5.8 — Phase 0  (Baseline + SSOT)        문서·코드 버전 정합. v3 잔존 SSOT 를 docs/legacy/ 로 이전한다. 코드 변경 0.
v4.5.9 — Phase 0B (Eval Harness)           Golden Prompt 20건 + 5종 회귀 테스트 (Golden / Visual / Semantic / Cost / Completeness).
v4.6.0 — Phase 0C (State Compaction)       6-tier State 모델 + 각 호출의 입력 제한. token compounding 차단.
v4.6.5 — Phase 1A (ResearchDirector)       Composer 앞에 분석 설계 단계 신설. AnalysisBrief schema + 9종 분석기법 enum.
v4.7.0 — Phase 2A (EvidenceDataset)        차트 데이터 계약 도입. source_id 강제. ChartCritic 이 prose-dataset 일치성 검증.
```

Tier 1 완료 시점: v4.5.7 baseline 대비 *측정 가능한* 분석 품질 향상이 회귀 하네스로 입증되어야 한다.

**Tier 2 — 시각 스택.**

```
v4.7.5 — Phase 2  (Vega-Lite)              11개 type-specific renderer → render_vega_lite() 어댑터.
v4.7.7 — Phase 2B (Capability Registry)    차트 type 의 safe / guarded / experimental 분류.
v4.8.0 — Phase 6  (Chart Gate)             Schema + ChartCritic + Visual Sanity + Fallback Ladder 4중 게이트.
v4.8.3 — Phase 6A (Exhibit Priority)       3-tier 분류 (required / supporting / decorative).
v4.8.7 — Phase 7A (Deterministic Gate)     LLM Desk 이전의 결정적 검사. 11종 hard fail + 5종 soft fail.
```

Tier 2 완료 시점: 13개 antipattern 회귀 0건 + 사용자 캡쳐 보고 0건 (Phase 7A 만으로 잡힘).

**Tier 3 — 시스템 QA + 모드 분기.**

```
v4.9.0 — Phase 7  (LLM Desk Editor)        Logical 7-rubric + Visual 8-rubric + Playwright 캡쳐 + KILL_RULES.
v4.9.3 — Phase 8  (Strategic Mode 기본)    Telegram bot prefix + composer 분기 + decision_brief layout.
v4.9.5 — Phase 8A (Strategic Contract)     8개 필수 출력 + ActionPlan 30/60/90 + 명시 prefix 7종.
```

Tier 3 완료 시점: Desk publish/hold/kill 분포가 60-80%/15-30%/0-5% 안에 안착 + 전략 질의 라우팅 정확도 ≥ 90%.

**Tier 4 — 미적 개선.**

```
v4.9.7 — Phase 1  (Editor Pass)            7-rubric copy editing.
v4.9.8 — Phase 3  (Layout Primitives)      9종 layout (분석 모드).
v4.9.9 — Phase 4  (Exhibit 번호제)         [[ex:N]] cross-ref.
v5.0.0 — Phase 5  (Budget + 절단)          섹션별 word budget + 절단 검출 + 연속 호출 + 적응형 max_tokens. 안정화.
```

Tier 4 완료 시점: 외부 reader test 우위 + 차트·레이아웃 다양성 지표 충족 + v5.0.0 정식 출시.

### 20.3 폴백 전략

각 Phase 의 새 모듈은 호출 실패 시 *이전 단계 결과를 그대로 통과* 시켜야 한다. 단 Phase 6 Chart Gate, Phase 7 Desk Editor (+7A), Phase 8 Strategic Mode 는 예외 처리한다.

- ResearchDirector (Phase 1A) 가 실패하면 *기본 AnalysisBrief* 를 사용한다 (selected_methods 비어 있고, report_shape.section_count=4, must_have_sections=["situation","mechanism","scenarios","watch"]). v4.5.7 동작과 사실상 동일하다.
- EvidenceDataset (Phase 2A) 추출이 실패하면 해당 차트는 *drop* 한다 (source_id 없는 차트는 emit 금지).
- Editor 가 실패하면 DraftReport 를 그대로 사용한다.
- VisualPlanner 가 실패하면 composer 가 emit 한 chart spec 을 사용한다 (단 Phase 2A 의 EvidenceDataset 검증은 여전히 적용된다 — source_id 가 없으면 drop).
- LayoutTypesetter 가 실패하면 모든 섹션을 `standard` layout 으로 적용한다.
- **Chart Critic 이 실패하면 차트를 *drop* 한다** (composer emit 을 그대로 통과시키지 않는다). 단 priority="required" 인 exhibit 은 fallback (fact_grid / table / text) 으로 격하 (Phase 6A).
- **Phase 7A Deterministic Gate 의 hard fail 은 LLM 없이 즉시 KILL.** soft fail 은 DeskEditor 에 신호로 전달.
- **Desk Editor 가 LLM 호출 자체에 실패하면 publish-with-warning 으로 발행한다** (Phase 7A hard fail 이 통과한 경우에 한해). 단 자동 KILL_RULES 는 LLM 호출 없이 결정적으로 발화한다.
- **Phase 8 의 Strategic Mode 분기에 실패하면 분석 모드로 처리한다.** 사용자에게 텔레그램으로 "`?전략` prefix 로 명시 가능" 을 안내한다.
- **Phase 5 의 절단 검출이 실패하면 절단을 부정으로 판정한다** (false negative).

*깨진/부적합 차트 노출 0건* 과 *발행 가치 없는 보고서 0건* 이 우선 원칙이다.

---

## 21. 토큰 예산

### 21.1 단순 합산 vs State Compaction 효과

기존 Phase 1~8 의 토큰 비용을 *단순 합산* 하면 deep 모드가 ~80K 까지 부풀어 v4.5.7 (42K) 대비 +90% 가 된다. 이는 *각 단계가 raw context 를 다시 본다는 가정* 의 결과이다. Phase 0C (State Compaction) 가 이 가정을 깬다. 6-tier State 모델에서 RawContext 는 ContextAnalyst 후 폐기되고 EvidencePack 으로 압축된다. 후속 단계는 EvidencePack + AnalysisBrief 만 받는다.

### 21.2 State Compaction 후 실제 토큰 (deep 모드)

| 단계 | 입력 (압축 후) | 출력 | 비용 |
|------|----------------|------|------|
| Context (intent classifier 포함) | RawContext (~50KB) | EvidencePack (~12K) | ~11K |
| ResearchDirector (Phase 1A 신규) | EvidencePack + user_request | AnalysisBrief (~3K) | ~7K |
| Compose (Drafting) | AnalysisBrief + EvidencePack 압축 (raw 미입력) | DraftReport (~16K) | ~22K (-10K vs v4.5.7) |
| Compose 절단 시 연속 호출 (amortize) | — | — | ~3K |
| Visual Plan | DraftReport + EvidenceDataset (압축) | ChartSpec[] | ~5K |
| Edit | DraftReport + AnalysisBrief.thesis (raw 미입력) | EditedReport | ~10K |
| Layout Typeset | EditedReport + ExhibitPack | LayoutAssignment[] | ~3K |
| Chart Critic (Gate B) | 단일 chart spec + 인접 prose (raw 미입력) | Verdict[] | ~4K |
| Phase 7A Deterministic Gate | rendered HTML | hard/soft fail 리스트 | **0K (LLM 미사용)** |
| Desk Editor — Logical | PublishManifest + DraftReport (raw 미입력) | DeskVerdict | ~6K |
| Desk Editor — Visual Proof | screenshots ×4 | issues[] | ~6K |
| HOLD 재호출 amortize | — | — | ~3K |
| **합계 (deep 기준, 압축 후)** | — | — | **~80K → ~70K (-10K, -12.5%)** |

State compaction 으로 약 10K 절감된다. v4.5.7 (42K) 대비 V5 의 실제 비용은 *+67%* 이다. 단순 합산이 예상한 *+90%* 보다 가볍다.

### 21.3 모드별 실제 비용

| Mode | v4.5.7 | V5 (압축 후) | 차이 | 핵심 추가 비용 |
|------|--------|--------------|------|----------------|
| fast | ~16K | ~28K | +75% | Phase 1A + Phase 6 + Phase 7 (간소화) |
| standard | ~28K | ~50K | +79% | + Phase 7 Visual + Phase 8 |
| deep | ~42K | ~70K | +67% | Phase 1A + 6 + 7 + 8 모두 적용 |
| **deep 전략 모드** | (분석 모드와 동일) | ~72K | +71% | + Phase 8A 의 ActionPlan 검증 (~+2K) |

### 21.4 break-even 분석

자동화 없이의 amortized 비용을 정량화한다.

- **시각 결함 사이클** — 발생률 X1, 사이클당 비용 ~15K (사용자 캡쳐 + AI 분석 + 패치 + 재배포)
- **보고서 절단 사이클** — 발생률 Y, 사이클당 비용 ~10K (사용자 알아챔 + 재요청)
- **전략 질의 오분류** — 발생률 Z, 사이클당 비용 ~20K (잘못된 분석 보고서 + 사용자 재요청)
- **분석기법 부적합 사이클** — 발생률 W (GAP-11), 사이클당 비용 ~12K (얕은 분석 보고서 + 사용자 재요청)
- **차트 데이터-출처 분리 사이클** — 발생률 V (GAP-12), 사이클당 비용 ~5K (사용자 신뢰도 손실, 재집필은 드물지만 신뢰성 기회비용)

자동화 없이 보고서당 amortized 추가 비용 = 15·X1 + 10·Y + 20·Z + 12·W + 5·V (K 단위).

자동화 시 보고서당 추가 비용 = +28K (deep, v4.5.7 대비 +67%).

break-even 식: 15·X1 + 10·Y + 20·Z + 12·W + 5·V > 28.

`docs/CHART_RENDERING_ANTIPATTERNS.md` 의 13개 회귀 누적 + 사용자 캡쳐 사이클 빈도 + GAP-11/12 의 만성적 발생을 고려하면 *X1+Y+Z+W+V 합이 70% 를 넘는 것* 으로 추정된다. break-even 식이 명백히 만족된다. 자동화가 우위이다.

### 21.5 비용 절감 옵션

- ResearchDirector 를 Sonnet 4.6 으로 다운그레이드 가능하나 분석기법 선택 정확도 회귀 테스트 후 결정한다 (~-3K 절감 가능).
- Chart Critic 을 Sonnet 4.6 → Haiku 4.5 로 다운그레이드한다 (1차트당 ~300토큰, 총 ~-3K).
- Desk Editor Logical 은 Opus 4.7 을 유지한다.
- Desk Editor Visual 은 Opus 4.7 vision 필수이다. 캡쳐 수를 4 → 2 로 줄여 ~3K 절감 가능하다.
- Phase 7A Deterministic Gate 가 hard fail 을 잡으면 Phase 7 LLM Desk 호출이 *발생하지 않는다*. hard fail 발생률 약 5~10% 로 추정 시 보고서당 amortize ~-1K.
- HOLD 재호출과 절단 연속 호출은 모두 1회 cap 으로 통제한다.

위 옵션을 모두 적용하면 deep 모드 V5 비용이 ~60K (v4.5.7 대비 +43%) 까지 낮아질 수 있다.

---

## 22. 인수 기준 — 전체 (V5 Definition of Done)

V5 가 v4.5.7 보다 우월하다고 인정되는 조건은 다음과 같다. *Tier 1 의 측정 기준이 충족되지 않은 상태에서 Tier 2 이상의 진입을 허용하지 않는다.*

**Tier 1 — 토대 (필수 선결 측정).**

1. **SSOT 정합성 회복 (Phase 0).** 문서·코드 버전 불일치 0건. v3 잔존 SSOT 모두 `docs/legacy/` 로 이전 완료.
2. **Golden Prompt 회귀 하네스 작동 (Phase 0B).** 20개 Golden Prompt 가 fixture 로 저장. 5종 회귀 테스트 (Golden / Visual / Semantic / Cost / Completeness) 가 자동 실행 가능. v4.5.x baseline 통과율이 측정되어 박혀 있다.
3. **State Compaction 효과 (Phase 0C).** V5 의 총 입력 토큰이 *압축 적용 전 단순 합산 대비 30% 이상 감소*. 응답 정확도 (Golden 회귀) 가 압축으로 떨어지지 않음.
4. **분석기법 라우팅 정확도 (Phase 1A).** Golden Prompt 20건의 expected method 와 ResearchDirector 의 실제 선택이 ≥ 80% 일치. 동일 사건에 *다른 분석기법* 이 선택된 사례 다수 검증.
5. **EvidenceDataset 강제 (Phase 2A).** 모든 차트가 EvidenceDataset 입력. source_id 없는 chart emit 사례 0건. prose 인용 없는 차트 데이터 ChartCritic 이 100% drop.

**Tier 2 — 시각 스택.**

6. **차트 다양성 향상 (Phase 2).** V5 보고서 10건 표본에서 등장한 고유 차트 type 수가 v4.5.7 baseline 의 1.5배 이상.
7. **Capability Registry 강제 (Phase 2B).** experimental 차트가 Registry 등재 없이 emit 된 사례 0건.
8. **차트 품질 회귀 0건 (Phase 6).** V5 출시 후 30일간 새 antipattern (CHART-AP-15+) 0건. "이 차트 왜 여기 있지?" 사용자 보고 0건.
9. **Critic drop 율 적정 범위 (Phase 6).** 10~30% 범위.
10. **Required Exhibit 보존 (Phase 6A).** Critic fail 한 required exhibit 이 drop 되지 않고 fallback (fact_grid/table/text) 으로 대체된 사례 100% 검증.
11. **Deterministic Gate 효과 (Phase 7A).** Hard fail 11종이 모두 회귀 테스트로 검증. Hard fail 시 Desk LLM 호출 발생 0건.

**Tier 3 — 시스템 QA + 모드 분기.**

12. **Desk 판정 분포 적정 범위 (Phase 7).** 첫 50건 운영 후 publish 60~80% / hold 15~30% / kill 0~5% 분포 안.
13. **KILL 사유 명확성 (Phase 7).** 사용자의 "왜 발행 안 됨?" 질문 빈도 월 1건 이하.
14. **YK 시각 검수 부담 감소 (핵심 지표, Phase 7).** V5 출시 후 30일간 YK 의 캡쳐→텔레그램→AI 재작성 요청 횟수 5건 이하.
15. **Playwright 캡쳐 안정성 (Phase 7).** 보고서당 캡쳐 성공률 95% 이상.
16. **전략 모드 라우팅 정확도 (Phase 8).** 패턴 매칭 정확도 90% 이상.
17. **전략 보고서 필수 항목 (Phase 8A).** 8개 필수 출력 (decision_statement, options, criteria, constraints, decision_matrix, recommendation, kill_switch_conditions, action_plan_30_60_90) 100% 포함. ActionPlan 의 30/60/90일 항목 모두 비어 있지 않음.

**Tier 4 — 미적 개선.**

18. **외부 reader test 우위.** 동일 사건 5건에서 V5 가 ≥3건에서 우세.
19. **레이아웃 다양성 향상 (Phase 3).** standard 외 layout primitive 사용률 30% 이상.
20. **Cross-reference 사용 (Phase 4).** `[[ex:N]]` 표기 보고서당 평균 1.5회 이상.
21. **분량 비대칭 강화 (Phase 5).** 섹션 분량의 지니 계수가 v4.5.7 baseline 보다 0.10 이상 증가.
22. **보고서 절단 회귀 해결 (Phase 5).** "보고서가 끊겼다" 사용자 보고 빈도 30일간 2건 이하. 절단 검출이 회귀 테스트의 v4.5.7 회귀 사례 100% 포착.

**전반 회귀 없음.**

23. **회귀 없음.** Watchlist 등록 / 텔레그램 봇 명령 / Cloudflare 배포 / 기존 design token 모두 byte-equal 또는 functional-equal 로 보존.

---

## 23. Anti-pattern 추가 (V5 누적)

| # | 이름 | 설명 |
|---|------|------|
| AP-V5-1 | Editor 우회를 금지한다 | composer 결과를 *직접* renderer 로 보내는 경로를 신설하지 않는다. Editor 실패 시 graceful fallback 만 허용한다. |
| AP-V5-2 | Vega-Lite spec 의 색 직접 지정을 금지한다 | composer 와 VisualPlanner 가 emit 한 spec 의 색·폰트는 `_apply_v5_theme()` 에서 *덮어쓴다*. |
| AP-V5-3 | Layout primitive 추가를 금지한다 | 분석 모드의 9종 외에 layout 을 신설하지 않는다 (전략 모드의 `decision_brief` 1종은 별도 vocab 으로 예외 처리한다). v3 archetype 11종의 회귀를 막기 위함이다. |
| AP-V5-4 | 테마와 폰트 추가를 금지한다 | Editorial Cream + Burgundy Mono + Newsreader/IBM Plex 트리플렛으로 고정한다. 새 카테고리 라우팅도 기존 2종 안에서 결정한다. |
| AP-V5-5 | composer 가 차트 type 을 결정하지 못하게 한다 | Phase 2.5 이후 차트 결정은 VisualPlanner 의 단독 책임이다. composer 는 prose 만 작성한다. |
| AP-V5-6 | Exhibit 번호의 임의 부여를 금지한다 | exhibit_id 는 Renderer 가 자동으로 부여한다. composer 와 Editor 가 직접 숫자를 박지 않는다. cross-ref 는 `[[ex:N]]` 표기로만 한다. |
| AP-V5-7 | 선례 오염을 차단한다 | composer 와 VisualPlanner 가 "주제 카테고리 → 익숙한 차트" 패턴매칭으로 emit 하는 것을 막는다. 호르무즈 = Brent 차트, 반도체 = HBM 그래프 식을 막는다. *이 보고서의 prose 가 그 데이터를 직접 인용하는지* 검증 없이 박는 것을 금지한다. Phase 6 Gate B Critic 의 질문 4번 ("prose 가 차트 데이터를 직접 인용하는가") 이 1차 가드이다. 인용 없으면 drop 한다. |
| AP-V5-8 | Chart Critic 우회를 금지한다 | composer 와 VisualPlanner 가 emit 한 차트는 Phase 6 의 Gate A/B/C 모두를 통과해야 렌더에 도달한다. 어느 한 게이트라도 우회하는 경로를 신설하지 않는다. Critic 호출 실패 시 *drop* 한다 (composer 통과를 허용하지 않는다). |
| AP-V5-9 | Chart 총량 가드를 강제한다 | Critic 통과해도 보고서당 차트가 5개 초과면 score 가장 낮은 차트부터 자동으로 drop 한다. 시각 피로를 방지한다. mode 별 상한은 fast ≤ 2, standard ≤ 4, deep ≤ 5 이다. |
| AP-V5-10 | 타입별 Schema 가드 우회를 금지한다 | bubble x/y finite, gantt start≤end, network nodes≥2 등의 Pydantic 가드를 *런타임에 비활성화* 하는 경로를 신설하지 않는다. 가드 fail 은 render fail 을 의미한다. |
| AP-V5-11 | Desk Editor 우회를 금지한다 | publish/hold/KILL 판정을 거치지 않고 Cloudflare 로 직접 발행하는 경로를 신설하지 않는다. Desk LLM 호출이 실패해 publish-with-warning 으로 fallback 하더라도, *자동 KILL_RULES 는 LLM 없이 결정적으로 작동* 한다. 어느 경로로도 우회 불가능하다. |
| AP-V5-12 | KILL 의 조용한 처리를 금지한다 | Desk 가 KILL 판정 시 *반드시* 텔레그램 사용자에게 명시적으로 알린다 (사유 + 권장 행동을 포함한다). 조용히 발행 실패하지 않는다. v4.5.7 의 "minimal fallback 으로 어떻게든 발행" 정책의 정반대를 채택한다. |
| AP-V5-13 | HOLD 무한 루프를 금지한다 | Desk 의 HOLD 판정 → lower editor 재호출 → 다시 Desk 호출 사이클을 *최대 1회 재호출* 로 제한한다. 2번째 HOLD 시 publish-with-warning 으로 종료한다. 무한 재집필을 방지한다. |
| AP-V5-14 | 자동 KILL_RULES 의 임의 약화를 금지한다 | §8.6 의 KILL_RULES (논리 5종 + 시각 3종) + §9.6 의 KILL_RULES_STRATEGIC (5종) 는 *결정적* 룰이다. 코드에서 threshold 를 임의로 낮추거나 룰을 비활성화하는 변경을 금지한다. 룰 조정은 본 문서 개정 + 운영 통계 근거 후에만 한다. |
| AP-V5-15 | Visual Proof 우회를 금지한다 | Desk Editor 호출 시 *반드시* 캡쳐 입력을 함께 전달한다. 캡쳐 자체 실패는 telemetry 기록 + Logical-only fallback (graceful) 가능하지만, *캡쳐 가능한 환경에서 의도적으로 skip* 하는 경로를 신설하지 않는다. |
| AP-V5-16 | YK 캡쳐 회귀의 무시를 금지한다 | YK 가 발행된 보고서를 캡쳐해 텔레그램으로 보낸 결함은 *반드시* `docs/DESK_VISUAL_RUBRIC.md` 에 신규 항목으로 append 한다. 같은 결함이 다시 나오는 회귀를 막기 위함이다 (§8.12 self-improving rubric 의 강제 발화). |
| AP-V5-17 | Cloudflare 직접 업로드를 금지한다 | Renderer 의 출력은 *로컬 디스크 (`reports/dev/`) 까지만* 쓴다. Cloudflare 업로드는 Desk Editor 가 PUBLISH 판정한 *후에만* 별도 업로드 호출로 한다. KILL 시 dev 디스크에만 보존하고 public 배포를 하지 않는다. |
| **AP-V5-18** | **전략 모드 옵션 < 3 금지** | Phase 8 전략 모드 보고서는 옵션이 3개 이상이어야 한다. 2개 이하 (이분법적 사고) 는 즉시 KILL 사유이다. 6개 이상 (분석 마비) 도 KILL 사유이다. 강제 범위는 3 ≤ 옵션 ≤ 5 이다. |
| **AP-V5-19** | **전략 모드 권고 명시 강제** | 전략 모드 보고서는 권고를 *반드시* 명시한다. "옵션 N 을 권고한다" 형식으로 한 옵션을 선택하고 근거 3개 이상을 제시한다. "각 옵션에 장단점이 있다" 식의 봉합 어법은 KILL 사유이다. |
| **AP-V5-20** | **decision_brief layout 의 분석 모드 사용 금지** | `decision_brief` layout primitive 는 Phase 8 전략 모드 *전용* 이다. 분석 모드 보고서가 이 layout 을 사용하지 못하게 LayoutTypesetter 에서 강제한다. 모드 분리를 layout 차원에서도 강제한다. |
| **AP-V5-21** | **절단 검출 우회 금지** | composer 호출 후 §6.4 의 절단 검출을 *반드시* 실행한다. 검출이 실패하더라도 (예외 발생) telemetry 에 기록한다. 검출 자체를 skip 하는 경로를 신설하지 않는다. 깨진 채로 발행되는 일을 막는다. |
| **AP-V5-22** | **연속 호출 무한 루프 금지** | §6.5 의 연속 호출은 *최대 1회* 로 제한한다. 1회 후에도 절단이 검출되면 publish-with-warning 으로 진행하고 사용자에게 "분량이 충분치 않을 가능성" 을 텔레그램으로 알린다. 무한 재호출로 토큰을 소진하지 않는다. |
| **AP-V5-23** | **모드 분기 모호 시 분석 모드 기본값** | Phase 8 의 전략 질의 감지가 모호한 경우 (패턴 매칭이 충돌하거나 LLM intent classifier 가 ambiguous) 기본값으로 *분석 모드* 로 처리한다. 잘못 처리되는 것보다 안정값으로 처리 후 사용자가 `?전략` prefix 로 재시도하는 것이 안전하다. |
| **AP-V5-24** | **prose 발 차트 데이터 생성 금지** | composer 또는 VisualPlanner 가 prose 에 박힌 숫자를 차트 데이터로 *재구성* 하는 경로를 신설하지 않는다. 모든 차트 데이터는 EvidenceDataset 에서 와야 한다. 위반 시 즉시 차트 drop. |
| **AP-V5-25** | **출처 없는 synthetic value 금지** | EvidenceDataset.source_ids 가 비어 있으면 EvidenceDatasetGuard 가 fail 한다. 출처 없는 데이터로 만든 차트가 발행되는 일이 없다. |
| **AP-V5-26** | **source_id 없는 chart emit 금지** | Phase 6 Gate A schema validation 이 source_id 누락 차트를 차단한다. 어떤 fallback 경로도 이 가드를 우회할 수 없다. |
| **AP-V5-27** | **Capability Registry 미등재 차트 emit 금지** | Phase 2B 의 Registry 에 등재되지 않은 차트 type 을 emit 하는 경로를 신설하지 않는다. 새 차트 type 추가 시 Registry 갱신을 PR 체크리스트로 강제한다. |
| **AP-V5-28** | **Required Exhibit 의 silent drop 금지** | Phase 6A 의 priority="required" exhibit 이 ChartCritic fail 했을 때 *조용히 사라지는* 경로를 신설하지 않는다. 반드시 fact_grid / table / text 중 하나로 fallback 하고 DeskEditor 에 hold 사유로 전달한다. |
| **AP-V5-29** | **Phase 7A 결정적 검사 우회 금지** | LLM Desk Editor 호출은 *반드시* Phase 7A Deterministic Gate 통과 후 발생한다. Hard fail 시 LLM 호출 발생 0이 강제된다. soft fail 은 DeskEditor 의 system prompt 에 명시적으로 전달되어야 한다. |
| **AP-V5-30** | **State Compaction 우회 금지** | 각 LLM 호출이 자기 책임에 *명시된 state* 외의 입력을 받지 못한다. 특히 Composer 와 Editor 가 RawContext 를 직접 보는 경로를 신설하지 않는다. 회귀 테스트로 입력 형태를 검증한다. |
| **AP-V5-31** | **ResearchDirector 우회 금지** | 사용자 질의가 Composer 에 직접 전달되는 경로를 신설하지 않는다. ResearchDirector 가 AnalysisBrief 를 emit 한 후에만 Composer 가 호출된다. ResearchDirector 호출 실패 시 *기본 AnalysisBrief* 로 fallback 한다 (v4.5.7 동작). |
| **AP-V5-32** | **Golden Prompt 회귀 무시 금지** | V5 의 어떤 Phase 도 Golden Prompt 회귀 테스트의 통과율을 *baseline 보다 떨어뜨려선 안 된다*. Tier 진입 전 회귀 테스트 통과를 의무화한다. |
| **AP-V5-18 갱신** | **전략 모드 옵션 정책 — 0개만 hold, 그 외 허용** | 기존 "옵션 < 3 → KILL" 정책을 완화한다. *옵션 0개 (전략 질의 성립 불가) → hold + 사용자 안내*, 옵션 1~5개 → 허용 (단 옵션 1개는 사용자에게 "단일 옵션 권고임" 을 명시한다), 옵션 6개 이상 → KILL (분석 마비). 검수자의 지적 (법적 강제 결정 같은 진짜 단일 옵션 사례) 을 반영한 정책 완화이다. |

---

## 24. 보존 사항 (Non-touch)

다음은 V5 작업 중에 *건드리지 않는다*.

- `src/agents/context_analyst.py` 의 사실 수집 로직을 그대로 보존한다. 단 Phase 0C 적용 후 출력 형태가 *RawContext* 가 아닌 *EvidencePack* 으로 압축된다.
- `src/watchlist/*` 의 Watchlist Registry, SQLite, monitor 를 보존한다.
- `src/telegram_bot.py` 의 봇 인터페이스를 보존한다. 단 Phase 8 의 패턴 매칭과 Phase 8A 의 명시 prefix 7종을 추가 분기로 한다.
- `src/lens_policy.py:select_theme()` 의 테마 라우팅 규칙을 보존한다 (단 mono 2종 라우팅만 사용한다).
- 기존 `samples/chart_map_mono_compare.html` 을 디자인 SSOT 로 보존한다.
- `docs/MONO_THEME_GUIDE.md` 를 V5 §19 의 SSOT 로 보강한다.
- `Strategy.user_intent` enum 을 보존하면서 Phase 8 에서 `what_to_do` 가 strategic mode 라우팅 트리거 역할을 추가로 갖도록 확장한다.
- DEPRECATED 모듈 (player_analyst / dynamics_analyst / chain_reaction_analyst / scenario_architect / visual_analyst / report_synthesizer / quality_inspector / synthesis_judge / lenses/* / archetypes/*) 을 *건드리지 않는다*. v4.0.0 부터 호출되지 않는다. 단 Phase 0 의 SSOT Repair 작업에서 *문서적으로* `docs/legacy/` 로 이전한다.

---

## 25. 다음 액션 (코딩 에이전트용)

순서를 엄수한다. **Tier 가 미완성 상태로 다음 Tier 로 진입하지 않는다**. 외부 검수 반영으로 우선순위가 *상류부터* 로 재배치되었다.

### 25.1 사전 작업 (코드 변경 없음)

1. 본 문서를 `docs/REFACTOR_V5_PLAN.md` 로 commit 한다 (status: proposal).
2. `docs/MONO_THEME_GUIDE.md` 에 §19 의 V5 design token 섹션을 추가한다.
3. 신규 문서를 다음 4종 생성한다.
   - `docs/DESK_VISUAL_RUBRIC.md` — Phase 7 Visual rubric 의 append-only 누적 SSOT.
   - `docs/STRATEGIC_MODE_PROMPT.md` — Phase 8 composer system prompt 확장 SSOT.
   - `docs/VISUAL_CAPABILITY_REGISTRY.yaml` — Phase 2B 의 차트 type capability 분류 SSOT.
   - `docs/RESEARCH_DIRECTOR_METHODS.md` — Phase 1A 의 9종 분석기법 정의 SSOT.

### 25.2 Tier 1 — 토대 (Phase 0 → 0B → 0C → 1A → 2A)

**브랜치 전략 — 단일 장기 브랜치 `v5-main` + Tier 단위 git tag.** 1인 + Claude Code 워크플로우에 per-Phase 브랜치 17개는 과한 마찰을 만든다. `v5-main` 한 개에 모든 Phase 를 sequential commit 으로 쌓고, Tier 완료 시점에 태그로 checkpoint 를 박는다. 문제 발생 시 `git checkout v5-tier1-done` 으로 안전 지점에 즉시 복귀한다.

```bash
git checkout main                    # v4.5.7
git checkout -b v5-main              # 단일 장기 개발 브랜치
git tag v5-baseline                  # 시작점
```

**Commit 메시지 표준** — Phase 단위로 분리하면 `git log --grep="phase-1a"` 로 특정 Phase 작업 이력 발췌가 가능하다.

```
feat(phase-0):  SSOT repair + version alignment
feat(phase-0b): Golden Prompt fixtures + 5-pack regression
feat(phase-0c): 6-tier State model + raw context compaction
feat(phase-1a): ResearchDirector + AnalysisBrief schema
feat(phase-2a): EvidenceDataset contract + source_id enforcement
```

**Tier 1 작업 순서.**

4. **Phase 0 (Baseline + SSOT Repair).** 코드 변경은 `src/orchestrator.py:VERSION` 갱신과 `docs/legacy/` 디렉토리 신설만 이루어진다. `docs/ARCHITECTURE.md` 를 v4.5.x 실제 호출 경로로 재작성한다.
5. **Phase 0B (Eval Harness).** Golden Prompt 20건 fixture 작성 + 5종 회귀 테스트 (`tests/regression/`) 구현. v4.5.x baseline 통과율을 박는다.
6. **Phase 0C (State Compaction).** 6-tier State 모델을 `src/state/` 에 정의한다. ContextAnalyst 와 Composer 의 입력 형태를 *압축 state* 로 전환한다. 회귀 테스트로 raw context 중복 입력 차단을 검증한다.
7. **Phase 1A (ResearchDirector).** `src/agents/research_director.py` 신설. AnalysisBrief schema + 9종 분석기법 enum. Composer 의 system prompt 를 *Drafting only* 로 축소한다.
8. **Phase 2A (EvidenceDataset).** `src/visual/evidence_dataset.py` 신설. 모든 차트가 EvidenceDataset 입력을 받도록 강제한다. ChartCritic 에 질문 8 추가.

**Tier 1 완료 점검.** §22 의 1~5번 인수 기준을 모두 통과하면 태그를 박는다.

```bash
git tag v5-tier1-done
git push origin v5-main --tags
```

태그 후에만 Tier 2 로 진입한다.

### 25.3 Tier 2 — 시각 스택 (Phase 2 → 2B → 6 → 6A → 7A)

9. **Phase 2 (Vega-Lite).** 11개 type-specific renderer 를 render_vega_lite() 어댑터로 점진 교체한다.
10. **Phase 2B (Capability Registry).** Registry yaml 작성 후 VisualPlanner 가 Registry 를 강제 참조하도록 한다.
11. **Phase 6 (Chart Gate).** Schema + ChartCritic + Visual Sanity + Fallback Ladder 4중 게이트 구현.
12. **Phase 6A (Exhibit Priority).** ResearchDirector 가 required exhibit 을 지정하고, Critic fail 시 fallback 정책을 적용한다.
13. **Phase 7A (Deterministic Gate).** LLM Desk 이전 결정적 검사 11종 hard fail + 5종 soft fail 구현.

**Tier 2 완료 점검.** §22 의 6~11번 인수 기준 통과 후 `git tag v5-tier2-done`.

### 25.4 Tier 3 — 시스템 QA + 모드 분기 (Phase 7 → 8 → 8A)

14. **Phase 7 (LLM Desk Editor).** Logical 7-rubric + Visual 8-rubric + Playwright 캡쳐 + KILL_RULES 구현.
15. **Phase 8 (Strategic Mode 기본).** Telegram bot prefix + composer 분기 + decision_brief layout primitive.
16. **Phase 8A (Strategic Contract).** 8개 필수 출력 + ActionPlan 30/60/90 + 명시 prefix 7종.

**Tier 3 완료 점검.** §22 의 12~17번 인수 기준 통과 후 `git tag v5-tier3-done`.

### 25.5 Tier 4 — 미적 개선 (Phase 1 → 3 → 4 → 5)

17. **Phase 1 (Editor Pass).** 7-rubric copy editing.
18. **Phase 3 (Layout Primitives).** 9종 layout (분석 모드).
19. **Phase 4 (Exhibit 번호제).** [[ex:N]] cross-ref.
20. **Phase 5 (Budget + 절단).** 섹션별 word budget + 절단 검출 + 연속 호출 + 적응형 max_tokens.

**Tier 4 완료 점검.** §22 의 18~22번 인수 기준 통과 후 v5.0.0 정식 출시.

```bash
git tag v5.0.0
git checkout main
git merge --ff-only v5-main         # main 을 V5 로 갱신
git push origin main --tags
```

### 25.5b main 동결 원칙 — 중요

V5 개발 중에는 `main` (v4.5.7) 에 patch 를 적용하지 않는다. `v5-main` 이 main 보다 *훨씬 멀리* 가 있어서 cherry-pick / merge 비용이 점점 비싸진다. v4.5.x 의 긴급 버그가 발견되어도 *V5 안에서 함께 고친다* (어차피 V5 가 곧 main 이 된다). 단 운영 중인 텔레그램 봇이 *심각하게 망가지는* 사례 (예: 인증 토큰 만료) 만 main 에 hotfix 한다.

### 25.6 각 Phase 완료 시 공통 작업

- `samples/v5_phase{N}_demo.html` 을 Cloudflare Pages 에 배포한다 (Tier 2 이후).
- `CHANGELOG.md` 에 항목을 추가한다.
- `GOAL.md` 에 `REQ-V5-{N}` 을 추가한다.
- Tier 진입 전 Golden Prompt 회귀 테스트 통과를 확인한다 (AP-V5-32 강제).
- Phase 6 완료 후 `docs/CHART_RENDERING_ANTIPATTERNS.md` 의 13개 항목에 *Phase 6 게이트로 잡힘* 을 표기한다.
- Phase 7 완료 후 `docs/DESK_EDITOR_DECISIONS.md` 를 신설하고 KILL/HOLD 사례를 append-only 로 기록한다.
- Phase 7 운영 후 YK 가 보낸 시각 결함은 *반드시* `docs/DESK_VISUAL_RUBRIC.md` 에 append 한다 (AP-V5-16).
- Phase 8 운영 후 잘못 라우팅된 사례를 telemetry 에 누적한다.

---

**문서 끝.** 문의와 이견은 본 파일의 commit 메시지로 회신한다.
