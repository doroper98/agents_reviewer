---
tier: 1
status: proposal (초안 — 사용자 게이트 대기, 구현 착수 전)
target_version: v7.0.0
based_on_baseline: v6.2.0
last_synced_with: v6.2.0
ssot_for:
  - "V7 마스터 플랜 (차트 에디토리얼 리디자인 + 스크롤 내러티브 아크 + 기준시점 맥락 검수)"
  - "V7 요구사항 (REQ-V7-N) 정본"
  - "V7 anti-pattern (AP-V7-N) 카탈로그 — append-only"
depends_on:
  - "src/templates/static/charts.js (20종 렌더러 — Track A 주 대상)"
  - "src/templates/archetypes/freeform_essay.html (Track B 주 대상 — 인라인 엔진)"
  - "src/factcheck/critic_loop.py + deterministic_guards.py + src/agents/codex_critic.py (Track C 주 대상)"
  - "docs/MONO_THEME_GUIDE.md / docs/CHART_RENDERING_ANTIPATTERNS.md (Track A 불변 제약)"
  - "REFACTOR_V6_PLAN.md (Track C 는 V6 critic 의 확장 — AP-V6-N 전부 계승)"
proposed_by: 사용자 3건 리팩토링 요청 (2026-06-11 — 차트 디자인 / 스크롤 인터랙션 / critic 맥락 정합)
last_review: 2026-06-11
---

# REFACTOR V7 — 차트 에디토리얼 리디자인 · 스크롤 내러티브 아크 · 기준시점 맥락 검수

> **목적.** v6.2.0 은 사실 거버넌스(V6 critic 루프)와 시각 거버넌스(Gate A~D)를 갖췄다.
> V7 은 세 방향을 다룬다: **(A)** 차트 유형 확장 + 기존 20종의 과감한 에디토리얼
> 리디자인(전문성·맥락·미학), **(B)** 보고서 페이지의 스크롤 인터랙션(차트 진입
> 연출 정련 + 기승전결 한자 배경 아크), **(C)** critic 루프의 구조적 맹점 — *사실은
> 맞지만 보고서가 필요로 하는 시점·맥락에 안 맞는 팩트* 가 검수를 통과하는 문제 —
> 의 교정. 세 트랙은 직교하며, 추진 순서는 **C → B → A** (정확성 > 연출 > 미관,
> 또한 리스크 표면적 오름차순).

---

## §0. 불변 조건 (코어 보존 — 모든 트랙 공통)

1. **데이터 계약 동결.** `ComposedSection.charts` 의 `{type, title, data, note?}` dict 계약,
   chart type 명칭 20종, `ComposedReport` 필수 필드는 변경 금지. 모든 모델 확장은
   *additive Optional* 만 — `reports/*.json` 구 데이터 + [scripts/patch_report.py](scripts/patch_report.py)
   `--recompose`/`--rerender-only` + ReportBundle 계약([docs/CONTRACTS/report_bundle_v1.md](docs/CONTRACTS/report_bundle_v1.md)
   §7 additive=무증분)이 깨지지 않아야 한다.
2. **mono 테마 제약 유지** ([docs/MONO_THEME_GUIDE.md](docs/MONO_THEME_GUIDE.md)): 45° 한 방향
   해치 / 큰 숫자 accent 금지 / mono 팔레트(--text·--accent·--up·--down) / 외부 타일·다색 금지.
   "디자인 리팩토링" = 이 어휘 *안에서* 의 정밀도 향상이지 어휘 교체가 아니다.
3. **CHART-AP 1~29 / WRITE-AP 1~21 / AP-V6-1~13 전부 계승.** 특히 CHART-AP-18(모션:
   ≤700ms·1회 재생·prefers-reduced-motion·unobserve)과 AP-V6-3(flag OFF byte-equal),
   AP-V6-5(루프 제어 0-LLM), AP-V6-8(지적 근거 인용), AP-V6-11(codex 본문 작성 금지).
4. **flag 네임스페이스 `V7_*`**, 모든 flag default OFF = v6.2.0 byte-equal. 단 Track A 의
   charts.js 는 백엔드 flag 로 게이트 불가(정적 JS) — §1.6 의 **자산 버저닝** 으로 대체.
5. **2-call 파이프라인 유지.** 신규 LLM 호출 추가 없음(Track C 는 기존 codex 호출의
   입력·판정 기준 확장만).

---

## §1. Track A — 차트 레이아웃·디자인 리팩토링 + 유형 확장

### §1.1 현황 진단 (왜 지루해지는가)

[charts.js](src/templates/static/charts.js) 2,525줄, 20종 렌더러, RENDERERS dict L2312.
구조적 강점: zone 엔진(L67-99) / annotation 렌더러 4종(band·hline·vline·point, L104-245) /
OccupancyTracker 충돌 회피 / sankey content-fit(v6.0.3) / network 인접행렬(v5.5.5) /
slope 라벨 dodge(v5.5.8). 즉 *기반 체력은 좋다*. 지루함의 원인은 렌더러가 아니라
**에디토리얼 레이어의 부재**:

- **D1. 헤더 해부학 미정형.** title(14px serif) + subtitle(이탤릭) 뿐. FT/Economist 의
  "kicker → 주장형 제목 → 단위·기간 라인 → 출처 라인" 4단 해부학이 없어 모든 차트가
  같은 얼굴이다.
- **D2. annotation 레이어가 사실상 미사용.** renderBand/renderHline/renderVlinesStaggered/
  renderPoint 가 구현돼 있으나 composer 스키마에 노출된 type 이 제한적 — 사건 마커·기준선·
  국면 밴드가 빠진 차트는 "데이터는 있는데 *이야기* 가 없다". 사용자가 말한 "맥락을
  충분히 담는" 의 최대 레버.
- **D3. 범례 의존.** stacked/stacked_area/dual_line 이 하단 범례 — 직접 라벨링(선 끝
  라벨)이 가능한 placeEndLabel(L248) 인프라가 있는데도 안 쓴다.
- **D4. 축 경제 미적용.** y 그리드 수·틱 포맷·단위 표기가 타입별 제각각. "최상단 틱에만
  단위" 같은 규율 없음.
- **D5. 숫자 타이포그래피.** tabular-nums 미지정, 천 단위·억/조 포맷터가 렌더러마다 중복.
- **D6. donut 의 빈약함** (CHART-AP-16 으로 최소 3조각은 보장되나 시각 밀도가 낮음),
  bar 의 기본형 편향(결정 트리로 일부 차단 중이나 시각 변별력 부족).

### §1.2 A-1: 공유 에디토리얼 레이어 (기존 20종 일괄 격상)

개별 렌더러를 20번 고치지 않고 **공유 헬퍼 4개를 신설**해 전 타입이 통과하게 한다:

1. `chartHeader(card, spec)` — kicker(섹션 키커 상속, 9.5px caps) / 제목(주장형) /
   단위·기간 라인(`unit_line` 신규 optional 필드, 예: "단위: 조원 · 2024.1Q~2026.1Q") /
   출처 라인 일원화. charts.css 의 `.chart-card-*` 블록 재정의.
2. `axisEconomy(g, scale, opts)` — y틱 ≤5 / 최상단 틱에만 단위 / 0-기준선 강조(0.8px,
   --text) / 그 외 그리드 0.4px --border. 모든 cartesian 타입이 호출.
3. `fmtNum(v, opts)` — tabular-nums + 한국어 단위(만/억/조) + 자릿수 규율 단일 SSOT.
   기존 렌더러 내 중복 포맷 코드 제거.
4. `applyAnnotations(g, spec.annotations, zones)` — **`annotations` optional 필드를 모든
   cartesian 타입(line/area/bar/dual_line/forecast/candle/scatter/stacked_area/slope/
   range_bar/lollipop)에 공통 개방**. 스키마: `[{kind: "vline|hline|band|point",
   at|from|to, label}]`. 기존 4종 렌더러(L104-245) 재사용이므로 렌더 코드 신규 작성
   최소. Gate A: `schemas.py` 에 `AnnotationGuard` 공통 모델 1개 추가(타입별 가드에
   optional 필드로 합성). composer SYSTEM_PROMPT 에 "사건·기준선이 본문에 있으면
   annotation 으로 차트에 박아라" 지시 + 예시.

**타입별 중점 리디자인** (공유 레이어 위에서 소폭):
- bar: 값 정렬 default + 기준선(평균/목표) hline + 마지막 항목 delta 라벨.
- line/area: 끝점 강조 + 최종값 직접 라벨(이미 placeEndLabel 있음 — default 화),
  사건 배지 번호를 annotation 스키마로 통합.
- donut: 중앙 합계 → "핵심 1조각 강조 + 나머지 muted" 에디토리얼 모드(`emphasis` 키).
- stacked/stacked_area/dual_line: 범례 → 선·블록 끝 직접 라벨(D3 해소).
- candle: MA(20) 점선 오버레이(결정적 계산, LLM 무관) + 마지막 종가 라벨.
- heatmap: 행·열 합계 마진 스트립(작은 bar) 추가 — "표 + 요약" 이중 판독.
- waterfall/sankey: 변경 금지(CHART-AP-20/21/22/27 재발 표면 — 최종 해법 3종이 이미
  안정. 헤더·포맷터만 적용).

### §1.3 A-2: 신규 차트 유형 (후보 7, 채택은 사용자 게이트)

각 후보는 *기존 20종이 못 덮는 에디토리얼 니치* 가 있을 때만. 전부 `guarded` tier 진입,
[Chart System 7단 절차](CLAUDE.md)(RENDERERS → SYSTEM_PROMPT 스키마 → _TYPE_TO_GUARD →
REGISTRY yaml → KNOWN_CHART_TYPES → fixture 시나리오 → 회귀 테스트) + 5-Layer Usage
Guarantee 필수. CHART-AP-17(type starvation) 가드.

| 후보 | 니치 | 기존 유형과의 차별 |
|------|------|--------------------|
| `bump` (순위 변화) | 시기별 순위 경쟁 (점유율 순위 등) | slope 는 2시점뿐, line 은 값 — 순위 축이 없음 |
| `bullet` (목표 대비) | 실적 vs 가이던스/컨센서스 | bar 는 단일 값 — 목표·범위 중첩 불가 |
| `dot_strip` (분포 비교) | 그룹별 값 분포 (애널리스트 전망 분포 등) | scatter 는 2변수, 1변수 분포 표현 없음 |
| `calendar_heatmap` | 일별 강도 (변동성·발언 빈도) | heatmap 은 범주×범주 — 달력 시간축 없음 |
| `connected_scatter` | 2변수의 시간 경로 (금리×환율 궤적) | dual_line 은 두 축 분리 — 궤적 서사 없음 |
| `marimekko` | 2차원 구성 (시장규모×점유율) | stacked 는 1차원 구성 |
| (승격) `treemap` | registry 에 experimental 로 이미 존재 | 계층 구성 — must_have 게이트 유지 여부 결정 |

권장 1차 채택: **bump / bullet / connected_scatter** 3종 (이벤트 분석 보고서와 니치
적합도 최상). 나머지는 usage_log 의 starvation 데이터를 보고 2차.

### §1.4 Gate·테스트 영향

- Gate A: AnnotationGuard + 신규 타입 가드 추가 ([src/visual/schemas.py](src/visual/schemas.py) `_TYPE_TO_GUARD`).
- Gate C(sanity): annotation 추가로 라벨 충돌 표면 증가 — `label_overlap_ratio` 임계 재측정
  (Plan §13.4 정합). zone 엔진의 topMargin stagger 가 1차 방어.
- 회귀: `tests/regression/fixtures/chart_type_scenarios.yaml` 신규 타입 시나리오 append
  (`KNOWN_CHART_TYPES` 1:1 유지), `test_chart_correctness.py` 가드 케이스, 갤러리 샘플
  `samples/chart_gallery_v7.html` 신설(5테마 × 전 타입 — 디자인 리뷰 아티팩트, A-0 산출물).

### §1.5 A-0: 착수 전 베이스라인 (필수 선행)

전 20종 × 5테마를 fixture 데이터로 렌더한 정적 갤러리 페이지 생성 + Playwright capture
([src/visual/capture.py](src/visual/capture.py) 재사용) 로 PNG 세트 확보. **리디자인 전·후
비교가 가능한 상태에서만 A-1 착수** — "과감한 리팩토링" 일수록 시각 회귀 판정 기준이
먼저 있어야 한다. codex 비전(V6_CODEX_VISUAL 경로)으로 전·후 미학 평가를 받는 것도
이 갤러리를 입력으로 쓴다.

### §1.6 ★ 자산 버저닝 (이번 탐색의 핵심 발견 — 구현 전 결정 필요)

[report_synthesizer.py](src/agents/report_synthesizer.py) `_sync_static_assets` 는 charts.js/
charts.css 를 **모든 보고서가 공유하는 reports/ 디렉토리 1곳** 에 복사하고, 템플릿은
상대경로(`src="charts.js"`)로 링크한다. Cloudflare Pages 는 디렉토리 통째로 재업로드.
→ **charts.js 를 리디자인하면 이미 발행된 모든 과거 보고서의 차트가 소급 변형된다.**
구 보고서의 데이터가 신 렌더러의 가정(annotation 등)과 어긋나면 발행본 파손.

**해법(권장): 자산 파일명 버저닝.** `STATIC_ASSETS` 에 `charts.v7.js`/`charts.v7.css` 추가,
freeform_essay.html 은 버전명 참조. 구 보고서는 구 파일 유지(파손 0), 신 보고서부터
신 디자인. 대안(소급 적용 — 과거 보고서도 새 디자인)은 전수 시각 회귀 검증 비용이
크므로 비권장. **이 결정이 AP-V7-1 (아래 §4) 의 가드.**

---

## §2. Track B — 스크롤 인터랙티브 + 기승전결 한자 배경 아크

### §2.1 현황 — 요구사항 절반은 이미 충족

사용자 요구 "차트가 스크롤 진행에 따라 한 번 애니메이션으로 그려지고, 이후 위아래로
움직여도 정보가 사라지지 않아야": **현행 시스템이 정확히 이 스펙이다.**
charts.js L2492-2517 IntersectionObserver(rootMargin -8%, threshold 0.12) → 진입 시
renderStage + 진입 애니메이션(타입별 380~700ms) → `io.unobserve` 로 1회 재생 →
최종 정적 SVG 영구 유지. 섹션 단위 fade-in 도 동일 패턴(freeform_essay.html L586-589,
report.css L847-848). 따라서 Track B 의 신규 작업은 **(i)** 진입 연출의 시퀀싱 정련과
**(ii)** 기승전결 배경 아크 신설이다.

### §2.2 B-1: 기승전결(起承轉結) 한자 배경 아크 — 설계

**DOM/레이어.**
```
<div class="arc-backdrop" aria-hidden="true">   ← position:fixed; inset:0; z-index:0;
  <span class="arc-glyph" data-phase="기">起</span>   pointer-events:none; overflow:hidden
  <span class="arc-glyph" data-phase="승">承</span>
  <span class="arc-glyph" data-phase="전">轉</span>
  <span class="arc-glyph" data-phase="결">結</span>
</div>
<main class="freeform-body">…기존 콘텐츠 (position:relative; z-index:1)…</main>
```
- 글리프: Noto Serif KR, `font-size: min(70vh, 70vw)`, 화면 중앙 고정.
- 색: 테마 토큰 `--text` 를 **opacity 0.04~0.07** (라이트 테마) / 0.06~0.09 (다크 4종) —
  본문 대비(WCAG)에 간섭하지 않는 워터마크 레벨. accent 사용 금지(mono guide §3.3 정신).
- 블러: `filter: blur(14px)` 를 글리프 요소에 1회 적용 + `will-change: transform` —
  블러 래스터는 1번, 이후 움직임은 transform(translateY)만이므로 합성만 발생(저비용).
  60vh 텍스트 노드에 매 프레임 blur 재계산을 시키지 않는 것이 성능 핵심.

**스크롤 엔진 (인라인 `<script>`, freeform_essay.html 내장 — §2.5 참조).**
- 섹션 → phase 매핑(§2.3)으로 각 phase 의 [시작 섹션, 끝 섹션] 문서 y 범위를 계산.
- rAF-throttle 된 scroll 핸들러가 진행도 p∈[0,1] (현재 phase 구간 내 위치) 산출 →
  현재 글리프 `translateY(-p × 100vh)`, 다음 글리프 `translateY((1-p) × 100vh)` —
  **다음 한자가 이전 한자를 위로 밀어올리는** 연속 보간. 스크롤 역방향도 동일 식으로
  자연 복원(사용자 요구 "위아래 움직임에 계속 인터랙티브").
- CSS Scroll-Driven Animations(`animation-timeline: view()`) 단독 채택은 보류 — Safari
  구버전 미지원. JS 엔진을 기본으로, `@supports` 시 CSS 타임라인 전환은 후속.
- `prefers-reduced-motion: reduce` → 보간 비활성, 현재 phase 글리프만 고정 표시(또는
  전체 숨김 — A/B 는 게이트 결정). `@media print` → display:none. JS 미동작 → backdrop
  자체가 안 뜸(점진적 향상, graceful degrade).
- 모바일(≤540px): 글리프 크기 축소(50vh) + blur 10px. 구형 기기 프레임 드랍 시
  `matchMedia('(hover: none)')` 기반 보간 간소화(phase 경계에서만 전환) 폴백.

### §2.3 섹션 → 기승전결 매핑 (모델 + 결정적 폴백)

[src/models.py](src/models.py) `ComposedSection` 에 **additive optional 필드**
`narrative_phase: Literal["기","승","전","결"] | None = None` 추가. composer SYSTEM_PROMPT
에 "각 섹션의 서사 단계 1자 라벨" 지시(±20 토큰 수준).

**결정적 폴백(필드 부재 시 — 구 JSON·recompose·LLM 누락 전부 커버, 0-LLM):**
- 섹션 n 개를 위치 기반 분할: 1번째=기, 마지막 본문 섹션=전 직전까지 승, contradictions
  섹션=전, watch_signals/timeline/closing=결. 섹션 ≤2 개면 기·결만 표시.
- 폴백은 템플릿 렌더 시점에 Python 에서 계산(Jinja2 컨텍스트로 주입) — JS 는 매핑
  결과만 소비. ReportBundle 에는 additive 필드로만 노출(schema_version 무증분, 계약 §7).

### §2.4 B-2: 진입 연출 정련 (소폭)

- 차트 진입과 섹션 fade-in 의 타이밍 위계: 섹션 fade(0.5s) → 차트 draw 가 현재 독립
  observer 2개 — 동일 섹션 내 stagger 를 `data-chart-id` 인덱스 기반 80ms 지연으로 연결
  (Apple 식 "순차 등장" 인상). CHART-AP-18 한도(개별 ≤700ms) 불변.
- fade-in threshold 0.06 → 0.12 로 차트 observer 와 통일(체감 일관성).

### §2.5 ★ 배포 격리 (Track A §1.6 과 동일 원리)

Track B 엔진·CSS 는 **freeform_essay.html 인라인** 으로만 구현(외부 charts.js 에 넣지
않음). 템플릿과 report.css 는 보고서 HTML 에 *인라인* 되므로 신 보고서에만 적용되고
발행본은 불변 — 자산 버저닝 없이도 소급 오염이 없다. backend flag `V7_SCROLL_ARC`
(default OFF) 로 템플릿 분기 → OFF 시 v6.2.0 byte-equal.

### §2.6 테스트

- 회귀: flag OFF byte-equal (golden HTML diff), 섹션 0~2개 엣지, narrative_phase 누락
  폴백, prefers-reduced-motion 분기.
- 수동/캡처: 5테마 × (라이트·다크) 글리프 가독 간섭 체크 — capture.py 로 스크롤 3지점
  PNG, codex 비전 미학 패스(V6_CODEX_VISUAL 인프라 재사용).

---

## §3. Track C — "사실은 맞지만 맥락이 틀린 팩트" 검수 (기준시점 계약)

### §3.1 근본 원인 (탐색 결론 — 사용자 증상의 정확한 메커니즘)

사용자 보고 증상: *6/5 발행 보고서에 6/1 지수가 필요 자리에 들어가고, codex 가 "6/1
수치로서 정확한가" 만 교정 → 정확한-그러나-시점이-틀린 문장으로 수렴.* (참고: 실제
교정 주체는 codex 가 아니라 Opus `revise_for_facts` — codex 는 지적만 하고 Opus 가
고친다, AP-V6-11. 수렴 실패는 *두 패스 모두* 같은 맹점을 공유하기 때문.)

코드 추적 결과 맹점의 위치:
1. [codex_critic.py](src/agents/codex_critic.py) 는 `publication_date` 를 받지만(L481),
   **"이 보고서가 어느 시점의 사실을 필요로 하는가" 라는 계약이 없다.** 기존 error_class
   14종 중 `recency_violation`/`stale_sourcing`/`novelty_conflation` 은 모두 *출처의
   신선도* 를 판정 — "팩트 자체는 정확하나 보고서 프레임과 다른 날짜" 는 분류 불가.
2. [deterministic_guards.py](src/factcheck/deterministic_guards.py) `MarketDataSourceGuard`
   (L259-306)는 본문 수치가 time_series 의 *어느 날짜든* close 와 ±0.5% 일치하면 통과 —
   **날짜 비앵커 매칭**. 6/1 종가를 정확히 쓰면 통과한다. 한편 `OHLCBar` 는 per-bar
   `date` 를 갖고 있어([market_fetcher.py](src/tools/market_fetcher.py)) 날짜 앵커 판정의
   데이터는 *이미 존재*한다.
3. `_evidence_digest`(codex_critic.py L475-543)의 time_series 전달에 "최신 가용 일자"
   메타가 없어 codex 가 "더 최신 데이터가 있는데 옛 날짜를 썼다" 를 알 수 없다.

### §3.2 C-1: 결정적 가드 2건 (최대 레버리지, 0-LLM — 1순위)

`V7_REF_FRAME` flag (default OFF), [deterministic_guards.py](src/factcheck/deterministic_guards.py) 에 추가:

1. **`DateAnchoredMarketGuard`** — 본문에서 `날짜 표현 + 수치` 쌍을 추출(기존
   MarketDataSourceGuard 의 수치 추출 + 날짜 정규식)하고, time_series 에서 **그 날짜의**
   close 와 대조. "6월 1일 코스피 2,950" 인데 6/1 close 가 2,910 이면 기존 가드는
   (다른 날짜에 2,950 이 있으면) 통과시켰던 케이스를 잡는다. flag id: `date_anchor_mismatch`.
2. **`StaleAnchorGuard`** — 보고서가 인용한 instrument 별 *가장 최신* 시장 날짜 D_cited 와
   time_series 의 마지막 가용 거래일 D_last 를 비교. `D_last - D_cited > 임계(기본 1거래일,
   mode 별 조정)` 이면 `stale_anchor` flag — **"6/4 종가가 있는데 본문 최신 수치가 6/1"**
   을 직격으로 잡는 가드. 날짜 무언급 수치는 D_cited 산정에서 제외(기존 unsourced 경로).

둘 다 V6 가드 관례 동일: log-only 적립 → 검증 후 hard 승격은 사용자 게이트(AP-V6-9).
T-1 기준: fixture 시나리오에서 검출 100% / good_prose FP 0.

### §3.3 C-2: 기준시점 계약(Reference Frame) 블록 — composer·codex 양측 주입

결정적으로 조립되는 소형 JSON 블록(0-LLM):
```json
{"publication_date": "...", "event_date": "...", "report_mode": "...",
 "instruments": [{"name": "...", "last_available_date": "...", "last_close": ...}]}
```
- **composer**: `_build_unified_payload`(이미 publication_date 주입 중, WRITE-AP-11) 에
  `reference_frame` 추가 + SYSTEM_PROMPT `=== 시점 앵커링 ===` 에 1줄 — "시장 수치는
  reference_frame 의 last_available_date 데이터를 기본으로, 더 옛 날짜 인용 시 절대
  날짜 명기 + 이유 서술". 작성 단계에서 6/1 선택 자체를 차단(1차 방어).
- **codex**: `_PROMPT_TEMPLATE` 에 `__REF_FRAME__` 슬롯 + instruction — "검수 0순위:
  각 시장 수치가 *이 보고서가 필요로 하는 시점* 의 값인가. 수치가 정확해도
  reference_frame 의 최신 가용 일자보다 옛 데이터를 무표기·무사유로 쓰면 위반."
- **Opus revise**: `revise_for_facts` payload 에 동일 블록 + "시점 교정 지시는
  time_series 의 해당 일자 데이터로 교체, 해당 일자 데이터가 없으면 그 수치 문장을
  절대 날짜 명기로 헤지하거나 제거" 지시. 이로써 **루프 양 패스의 맹점 공유가 해소**된다.

### §3.4 C-3: error_class `wrong_timeframe` 신설 — ★ 사용자 게이트 필요

"사실로서 정확하나 보고서의 기준 시점과 다른 날짜·기간의 값" 전용 클래스. severity
기본 high. **error_class 동결 확장은 사용자 게이트로만 가능** (CLAUDE.md V6 트랙 규정,
AP-V6-9) — 본 plan 승인 시 함께 승인 항목으로 처리. 동시 갱신(SOP 준수):
- [prompts/codex_critic_persona.md](prompts/codex_critic_persona.md)(단축본) +
  [prompts/market_factcheck_desk_v6.md](prompts/market_factcheck_desk_v6.md)(기준서) *동시·정합*.
  출력 형식(FactVerdict JSON) 불변.
- `tests/regression/fixtures/fact_discipline_scenarios.yaml` 에 `wrong_timeframe_01`
  (6/1↔6/5 케이스 그대로 박제) append.

### §3.5 C-4: 착지(landing) 확장

`apply_landing` 현행: `unsourced_number`/`market_data_mismatch` quote drop. 추가:
미해소 `wrong_timeframe`(high) 는 **drop** (정확하지만 시점이 틀린 수치를 무표기로
내보내는 것이 무수치보다 해롭다 — 본 트랙의 존재 이유). medium/low 는 헤지 유지.

### §3.6 테스트·측정

- T-1 확장: 신규 가드 2종 fixture 검출/FP 기준.
- T-3/T-4 확장: 모킹 codex 가 `wrong_timeframe` 반환 → revise 가 올바른 일자 데이터로
  교체하는 수렴 케이스 + 데이터 부재 시 drop 케이스.
- flag OFF byte-equal (AP-V6-3 상속). VM 실연동 측정은 [docs/V6_TEST_RESULTS.md](docs/V6_TEST_RESULTS.md)
  관례대로 append-only — 6/1↔6/5 유형 실보고서 재현 1건 포함.

---

## §4. Anti-Patterns (AP-V7-N — append-only)

- **AP-V7-1**: 공유 정적 자산(charts.js/css) 무버저닝 변경 — 발행된 전 보고서 소급 변형.
  신 디자인은 반드시 버전 파일명(`charts.v7.js`)으로 분리, 템플릿만 신버전 참조 (§1.6).
- **AP-V7-2**: 배경 아크가 본문 가독에 간섭 — 글리프 opacity 는 테마별 상한(라이트 0.07
  / 다크 0.09) 고정, accent 색 사용 금지, blur 는 요소 1회 래스터 + transform 보간만 (§2.2).
- **AP-V7-3**: 배경 아크/진입 연출이 정보를 휘발 — 차트는 1회 draw 후 정적 영구 유지
  (CHART-AP-18 상속). 스크롤 연동 재렌더·역재생 금지.
- **AP-V7-4**: narrative_phase 를 필수 필드화하거나 LLM 출력에만 의존 — 결정적 위치 기반
  폴백 항시 보존 (§2.3). 구 JSON recompose 가 항상 성공해야 한다.
- **AP-V7-5**: 시장 수치의 날짜 비앵커 검증 — 수치 일치 판정은 반드시 날짜 앵커와 함께
  (§3.2). "어느 날짜든 맞으면 통과" 회귀 금지.
- **AP-V7-6**: annotation 남발 — 차트당 annotation ≤3, 본문에 언급된 사건·기준만
  (Gate B 7질문에 연동). "맥락" 이 "소음" 이 되는 지점.

---

## §5. 추진 순서·Phase 분해 (요약)

| Phase | 내용 | flag / 격리 | 선행 조건 |
|-------|------|-------------|-----------|
| V7-C1 | 결정적 가드 2종 (§3.2) | `V7_REF_FRAME` OFF | 없음 — 즉시 가능 |
| V7-C2 | reference_frame 양측 주입 (§3.3) | 동일 flag | C1 |
| V7-C3 | `wrong_timeframe` + 페르소나·fixture (§3.4~3.5) | 동일 flag | ★ 사용자 게이트 |
| V7-B1 | narrative_phase 필드 + 폴백 + 배경 아크 (§2.2~2.3) | `V7_SCROLL_ARC` OFF, 템플릿 인라인 | 없음 |
| V7-B2 | 진입 연출 시퀀싱 정련 (§2.4) | 템플릿 인라인 | B1 |
| V7-A0 | 갤러리 베이스라인 + 캡처 (§1.5) | 산출물만 (samples/) | 없음 |
| V7-A1 | 공유 에디토리얼 레이어 + 타입별 격상 (§1.2) | `charts.v7.js` 자산 버저닝 | A0 + ★ §1.6 결정 |
| V7-A2 | 신규 타입 (1차 3종, §1.3) | guarded tier, 7단 절차 | A1 + ★ 채택 게이트 |

## §6. 사용자 결정 필요 항목 (구현 착수 전)

1. **§1.6 자산 버저닝 vs 소급 적용** — 권장: 버저닝(발행본 불변).
2. **§1.3 신규 차트 1차 채택 3종** — 권장: bump / bullet / connected_scatter.
3. **§3.4 error_class `wrong_timeframe` 신설 승인** (스스로 정한 사용자 게이트 규정).
4. **§2.2 prefers-reduced-motion 시 배경 아크**: 정적 1글자 표시 vs 전체 숨김 — 권장: 전체 숨김.
