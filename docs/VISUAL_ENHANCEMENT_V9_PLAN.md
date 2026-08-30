---
tier: 2
last_synced_with: v8.5.12
ssot_for:
  - "V9 시각 고도화 마스터 플랜 (전황 지도 어휘 · event_timeline · 작전 스키매틱)"
  - "시각물 누락(드롭) 지점 전수 조사 결과 (2026-08-29, 발행본 335건 실측)"
  - "시각물 전달 보증 (Visual Delivery Guarantee) 설계"
  - "Anime.js 도입 검토 결론 (불채택)"
depends_on:
  - "samples/visual_upgrade_v9_reportage_mockup.html"
  - "samples/visual_upgrade_v9_report_mockup.html"
  - "docs/CHART_RENDERING_ANTIPATTERNS.md"
  - "docs/MONO_THEME_GUIDE.md"
  - "docs/CONTRACTS/report_bundle_v1.md"
---

# VISUAL_ENHANCEMENT_V9_PLAN — 시각 고도화 마스터 플랜 (제안)

> **상태: V9-0(배관 수리) 랜딩 완료 · P2~P5(신규 시각 어휘)는 제안 — 사용자 결정 대기.**
> v8.5.11(CHART-AP-44) + v8.5.12(CHART-AP-45)로 §2.1~§2.5·§6·§7.1 이 구현됐고,
> 새 시각물(event_timeline·전황 지도 어휘·작전 스키매틱)은 목업 상태다.
> 본 문서는 2026-08-29 분석 세션의 산출물로, 미러된 발행본
> 335건(르포 29건 포함)의 실측 + 파이프라인 전수 감사에 근거한다. 구현은 본 문서의
> §8 페이즈 순서대로 별도 세션(Opus 5)이 수행한다. 목업(디자인 시트) 2종:
> - 르포 축: [samples/visual_upgrade_v9_reportage_mockup.html](../samples/visual_upgrade_v9_reportage_mockup.html)
> - 일반 보고서 축: [samples/visual_upgrade_v9_report_mockup.html](../samples/visual_upgrade_v9_report_mockup.html)
> - (머지 후 라이브: `doroper98.github.io/agents_reviewer/samples/visual_upgrade_v9_*.html`)

## §0. 요약 — 세 개의 발견, 세 갈래의 제안

**발견 1 — 시각물 "누락"의 주범은 AI 의 선택이 아니라 배관이다.**
- `heatmap` 과 `stacked` 는 **100% silent drop 되고 있었다** (→ ✅ v8.5.11 본 세션 수정, §2.1): composer SYSTEM_PROMPT 가
  가르치는 데이터 모양(heatmap `[{title,severity}]` / stacked `{scenarios:[...]}`)과
  `src/visual/schemas.py` 가드가 요구하는 모양(`{x,y,value}` / `{categories,series}`)이
  상호 배타적이다 (CHART-AP-38 과 동일 클래스, 2건 병존). §2.1 참조.
- v8.3.0 자기교정 힌트는 드롭 *후* 기록을 보므로, 깨진 type 을 "기아"로 오판해
  **더 자주 emit 시키고 전부 다시 버리는 악순환**이 돌고 있다. §2.2.
- 발행본 335건 중 **30건(9%)이 1-섹션 폴백**으로 시각물 전멸 (`_recover_head_loss` 는
  charts 를 복사하지 않고, minimal fallback 은 아예 빈 보고서를 만든다). §2.3.

**발견 2 — 전쟁·분쟁 르포에 공간 어휘가 없다.**
르포 29건 중 전쟁·군사 토픽이 6건인데, 지도는 점(markers)·호(arcs)뿐이라 "전선이
어디 있고 어느 쪽으로 밀리는가"를 못 그린다. 실사례: "전선을 되돌리는 우크라이나"
르포(2026-06-27)의 지도는 마커 4개+호 1개가 전부, 가와나카지마 전투 르포(2026-06-20)는
전술 서사(별동대 우회→선제 강하→회군 협격)를 그릴 수단이 아예 없었다. `rings` 는
v7.5.0 도입 후 **발행 실적 0회** (기능은 있는데 프롬프트 트리거가 없음). §1.

**발견 3 — 시간 전개를 그릴 차트가 없다.**
르포 5막(발단→전개→전망)과 일반 사건 보고서의 뼈대는 시간 서사인데, point event
나열용 type 이 없다 (gantt 는 기간 막대 전용 — zero-duration 금지 CHART-AP-15,
timeline_flow 는 르포에서 강제 null). `_REPORTAGE_BLOCK` 은 "timeline_flow 또는
gantt" 를 지시하면서 동시에 timeline_flow=null 을 지시하는 자기모순 상태다
([narrative_composer.py:1113](../src/agents/narrative_composer.py) vs `:1120`).

**제안 (사용자 결정 요청):**

| # | 제안 | 대상 | 성격 | 목업 |
|---|------|------|------|------|
| P1 | 배관 수리 — ~~heatmap/stacked 스키마 통일 + parity fixture (v8.5.11)~~ · ~~usage_log 2단화 + 드롭 표면화 + has_data SSOT + 폴백 salvage + 지도 조건·CDN 폴백 (v8.5.12)~~ → **✅ 완료** (잔여: MapPayloadGuard · 렌더러 경계 정합) | 공통 | **버그 수정 (최우선)** | S-3 |
| P2 | `event_timeline` 신규 차트 type (사건 전개 세로 타임라인) | 공통 (르포·일반 공용) | 신규 type 1개 | R-2 / S-2 |
| P3 | 전황 지도 어휘 — `paths`(front/advance/route) + `zones` + `phases` | 르포 (front·phases) / 일반 (zones) | embedded_map additive | R-1 / S-1 |
| P4 | 작전 스키매틱 — `basemap:"schematic"` + `terrain` | 르포 | embedded_map additive | R-3 |
| P5 | rings·zones 발동 트리거 프롬프트 명문화 + 르포 타임라인 모순 해소 | 공통 | 프롬프트만 | S-1 |
| P6 | Anime.js — **불채택 권고** (기존 d3 모션 프레임워크 확장으로 갈음) | — | 결정 | §5 |
| P7 | (이월) ~~wrangler 업로드 타임아웃~~ (✅ v8.5.12) + CLAUDE.md 토큰 다이어트 (잔여) | 운영 | 별도 트랙 | §7 |

P1 은 P2~P5 보다 먼저다 — **배관이 새는 채로 새 시각물을 부으면 목업만 늘어난다.**

## §1. 근거 — 발행본 코퍼스 실측 (2026-08-29, JSON 보존분 335건)

- 포맷: standard 306 / reportage 29. 지도 첨부: standard 102 / reportage 14.
- 차트 type 사용 (르포 29건 누적): bar 29, stakeholder_map 14, line 13, sankey 10,
  donut 6, dot_matrix 6, gantt 5, bullet 5, diverging_bar 4, waterfall 3, slope 3 …
- 차트 type 사용 (standard, 8월 이후): line 299 (시장 주입 채널 포함), diverging_bar 45,
  combo_candle 38, bar 35 … **heatmap 0, stacked 0, bump 0, small_multiples 0** —
  heatmap/stacked 는 §2.1 의 100% 드롭, bump/small_multiples 는 실제 기아.
- 지도 어휘: marker kind (port 127 / military 86 / chokepoint 70), arc kind
  (flow 117 / tension 63 / alt 15) — v7.2.0 어휘는 **살아있고 잘 쓰인다**.
  projection globe 21 / flat 95. **rings 0회** (v7.5.0 도입 후 한 번도 발행 안 됨).
- annotation: 108개 보고서에서 190개 — 잘 쓰임.
- 1-섹션 degraded 폴백: standard 27 + reportage 3 = **30건, 시각물 0**.
- 다중 섹션인데 시각물 0 인 보고서: 르포 2건 (금융 토픽) + standard 2건.
- JSON→발행 HTML 렌더 단계의 누락은 **0건** (173쌍 대조) — 누락은 전부
  ① JSON 저장 *이전* (composer 실패·validator drop) ② 브라우저 런타임 (빈 카드)
  ③ 애초 미방출(프롬프트/기아) 에서 발생한다.

## §2. 시각물 누락 전수 조사 — 드롭 지점 지도

> 전체 감사 원본은 본 세션 분석 기록. 여기엔 조치가 필요한 것만 우선순위로 적는다.
> 표기: `파일:라인` 은 2026-08-29 v8.5.10 기준.

### §2.1 🔴 P0 — 살아있는 100% silent drop 2건 (CHART-AP-38 클래스) — ✅ **v8.5.11 에서 수정 완료 (본 세션)**

| type | 프롬프트가 가르치는 모양 | 가드가 요구하는 모양 | 결과 |
|------|--------------------------|----------------------|------|
| `heatmap` | `[{title, severity}]` ([narrative_composer.py:304](../src/agents/narrative_composer.py)) | `[{x, y, value}]` ([schemas.py:428-444](../src/visual/schemas.py)) | 프롬프트 준수 emit → 전량 드롭 |
| `stacked` | `{scenarios:[...]}` (`:301`, `:406`) | `{categories, series}` ([schemas.py:446-470](../src/visual/schemas.py)) | 동일. 역방향도 사망 — 가드 준수 모양은 템플릿 `has_data` (`freeform_essay.html:437` 의 `ch.data.scenarios` 체크) 가 거른다 |

렌더러(`charts.js drawHeatmap/drawStacked`)와 템플릿은 *프롬프트* 편이고 가드만 다른
모양이라, 어느 방향으로 맞춰도 **세 층(프롬프트·가드·템플릿/렌더러)을 동시에** 맞춰야
한다. `docs/CONTRACTS/report_bundle_v1.md:428-431` 의 "라이브 composer 는 guard 통과
차트만 emit" 각주는 사실과 다름 — 함께 정정할 것.

**수정 (v8.5.11 반영 완료, CHART-AP-44):** heatmap 은 **양형 수용** — 가드가 격자형
(`[{x,y,value}]`, 결정 트리 정본·목업 S-3)과 강도 트랙형(`[{title,severity}]`,
v7.1.0 사용자 승인 계약 + 발행본 12건 재발행 하위호환)을 모두 통과시키고, 렌더러에
격자 분기(`drawHeatmapGrid`, 잉크 사다리)를 신설, 프롬프트에 격자형을 명기. stacked
는 가드를 렌더 계약(`{scenarios}`)으로 재작성 (구 `{categories,series}` 는 reject).
재발 차단: `tests/regression/test_prompt_guard_parity.py` (전 type 프롬프트-모양
라운드트립 + 신규 type fixture 강제). 경험 검증: 수정 전 두 모양 모두 가드 reject
재현 → 수정 후 통과, 회귀 스위트 신규 파손 0 + 기존 실패 2건 해소.

### §2.2 🔴 P0 — 자기교정 루프의 계측 오염 — ✅ **v8.5.12 완료**

`usage_log.append_run` 은 `_drop_invalid_charts` **이후** 의 type 을 기록한다
([orchestrator.py:2343-2352](../src/orchestrator.py)). 드롭된 type 은 "0회 emit"
으로 위장 → `composer_rebalance_hint` 가 기아로 판정 → 프롬프트에 우선-고려로 주입
→ 또 전량 드롭. **수정:** emit(드롭 전) / kept(드롭 후) 2단 기록 + 힌트는 kept 기준,
`emit−kept` 차이가 누적되는 type 은 "배관 이상" 으로 경고 로그 (기아와 구분).

### §2.3 P0 — 파국 폴백의 시각물 전멸 (발행본 9%) — ✅ **v8.5.12 부분 완료** (head-loss salvage)

- `_recover_head_loss` ([narrative_composer.py:2117-2177](../src/agents/narrative_composer.py))
  는 부분 객체에서 heading/prose 만 salvage — **charts·embedded_map·images 를 버린다.**
  부분 JSON 에 완결된 chart dict 가 있으면 함께 salvage 하도록 확장.
- minimal fallback ([orchestrator.py:1989-2015](../src/orchestrator.py)) 은 차트 0.
  standard 는 최소한 주입 채널(시장 시계열 카드)이라도 붙이도록 — 폴백 이후에
  `_ensure_time_series_chart` 를 태우면 0-LLM 으로 가능.
- degraded 경고문에 "시각물 소실" 여부를 명시 (지금은 텍스트 절단만 알림).

### §2.4 P1 — 관측 불가능한 드롭 층 2곳 — ✅ **v8.5.12 완료** (템플릿 게이트 SSOT; 렌더러 경계 정합은 잔여)

- **템플릿 `has_data` 게이트** (`freeform_essay.html:429-445` / `reportage.html:143-151`):
  서버 로그 0. 두 템플릿이 규칙을 **중복 소유** — freeform 쪽은 폐기된 `network` 분기가
  남아 있고 `stakeholder_map` 분기가 없다 (CHART-AP-38 재발 대기 상태). 규칙을 서버측
  사전계산(`ch["_renderable"]` 주입 또는 Jinja 공용 매크로) 1곳으로 통합.
- **렌더러 조기 return** (`charts.js` 각 함수 선두, 예: lollipop 8~15행, slope 3~10,
  small_multiples 4~9, waterfall total-북엔드): 가드 경계값의 **비동기화 사본**이라
  가드 통과 → 렌더러 침묵 → "제목·출처만 있는 빈 카드" (CHART-AP-28 류). 경계값을
  가드와 1:1 로 맞추고, parity fixture(§6.1)로 drift 를 회귀 차단.

### §2.5 P1 — 지도의 무방비 — ✅ **v8.5.12 부분 완료** (markers 조건 완화 + CDN 폴백; MapPayloadGuard 는 잔여)

- `embedded_map` 은 **서버측 검증 0** ([models.py:856](../src/models.py) — 맨 dict).
  경량 `MapPayloadGuard` (markers/arcs/regions/rings/paths/zones 필드형 + 좌표 유한성
  + 상한) 신설, `_drop_invalid_charts` 급의 log-only 정제.
- `maps.js:945` — **markers 0개면 지도 전체 미렌더** (rings/regions/zones 만 있는
  payload 는 빈 프레임). markers·rings·zones·paths 중 1개 이상으로 완화.
- world-atlas 는 CDN 단일 의존 (`maps.js:51`) — 실패 시 육지 없는 지도. 로컬 사본
  (`samples/vendor/countries-110m.js` 가 이미 있음) 을 `STATIC_ASSETS` 에 편입해
  CDN 실패 시 폴백.

### §2.6 P2 — 죽어 있는 품질 게이트 (참고)

V5 의 chart_gate/sanity/critic/desk 게이트는 전부 flag OFF + orchestrator 미배선
(호출 코드 자체가 없음). 특히 chart_gate 의 **폴백 사다리(fact_grid→표→텍스트→드롭)**
는 드롭 대신 강등을 주는 설계인데 죽어 있다. V9 범위에선 게이트 부활은 하지 않되
(스코프 통제), §6 의 전달 보증이 그 최소 기능(관측+정합)을 대신한다.

## §3. 르포 제안 (목업: visual_upgrade_v9_reportage_mockup.html)

### R-1. 전황 지도 어휘 — embedded_map additive 확장

```jsonc
"embedded_map": {
  // ... 기존 markers/arcs/regions/rings/sea_labels 동일 ...
  "paths": [           // ≤4
    {"points": [[lng,lat], ...],   // 3~24점
     "kind": "front" | "advance" | "route",
     "label": "?", "side": "a"|"b",   // front: 틱을 그릴 통제측
     "phase": 1}                       // 생략 시 전 국면 공통
  ],
  "zones": [           // ≤4
    {"points": [[lng,lat], ...],   // 3~12점 폴리곤
     "kind": "contested" | "control" | "buildup" | "strike",
     "label": "?", "phase": 1}
  ],
  "phases": [ {"id":1, "label":"2월"}, ... ]   // ≤4, 있으면 하단 국면 버튼
}
```

- **렌더**: front = 굵은 `--text` 대비선 + 통제측 수직 틱(군사지도 관례), advance =
  테이퍼드 화살표 (`--up`=주체측 / `--down`=상대측), route = 점선. zones = 45° 해치
  폴리곤 (contested=`--down` 해치 / buildup=`--muted` 점선 테두리 / strike=`--down`
  저농도, hue 금지 — mono guide §4 준수). phases = iv_skew 날짜 화살표(◀▶) 패턴
  재사용, 전환 500ms 보간, reduced-motion 즉시 상태.
- **모션**: front/advance stroke-dashoffset draw-in — 기존 `_applyMapEntryAnimation`
  의 arc 패턴 확장. 신규 라이브러리 불요.
- **프롬프트 발동 조건**: 전선·점령·탈환·공세·포위 서사가 본문에 있을 때만. 좌표는
  본문 근거 지명 기준 개략 표시, note 나 범례에 "개략" 명시 의무 (르포 표현 3등급의
  추론 라벨과 동일 원칙, WRITE-AP-5 연장).
- **가드**: points 좌표 유한성 + 개수 상한, phase id 는 phases 목록과 정합, front 는
  르포 전용 (standard 에서 emit 시 드롭 아닌 **kind 강등** — route 로 렌더).
- **osint 계약**: additive (무지정 payload 렌더 동일) — `reviewer_osint_q_a` 에
  통지(n) 1건, ReportBundle schema_version 무증분.

### R-2. event_timeline — 신규 차트 type (르포·일반 공용)

```jsonc
{"type": "event_timeline", "title": "...",
 "data": {"events": [
   {"date": "2026-07-15", "title": "수송기 1차 왕복", "desc": "?", "pivot": true, "act": "전개"}
 ]}}
```

- events 3~12, pivot ≤3, act(국면 라벨) 선택 — 있으면 좌측 밴드로 묶어 표시.
- 세로 스파인 + 날짜(Newsreader) + 이벤트 제목, pivot 은 ◆ 액센트. 진입 모션:
  스파인 draw-in 후 노드 40ms 스태거 (기존 `_applyEntryAnimation` 확장).
- **르포**: `_REPORTAGE_BLOCK` 의 "timeline_flow 또는 gantt" 지시를 event_timeline
  으로 교체 (timeline_flow=null 모순 해소). **일반**: 결정 트리에 "시간 순서가
  서사의 뼈대인데 수치 축이 없다 → event_timeline (line/gantt 금지)" negative
  constraint 로 편입.
- **신규 type 절차는 §6.2 의 9단계** (기존 7단계 + 템플릿 has_data + parity fixture)
  + osint 통지(신규 type 은 영상 렌더러 관점에서 파급 — 질문(q)로 폴백 협의).

### R-3. 작전 스키매틱 — `basemap:"schematic"` (embedded_map additive)

- `basemap:"schematic"` 이면 world-atlas fetch 생략, `terrain:[{kind:"river"|"ridge"|
  "road", points:[[x,y],...], label?}]` 를 0~100 상대 좌표로 렌더 (강 리본·능선 해치).
  markers/paths/zones/phases 는 R-1 과 동일 계약을 상대 좌표로 해석.
- 발동 조건: 역사 전투·국지 전술·시설 구도 등 **국가 윤곽이 정보가 되지 않는** 사건만.
  현대 지정학은 항상 실지도 우선 (프롬프트 negative constraint).
- 축척·좌표계 비표시, "개략 작전도, 실축척 아님" note 의무.

## §4. 일반 보고서 제안 (목업: visual_upgrade_v9_report_mockup.html)

- **S-1. zones·rings 개방**: zones 는 R-1 계약 그대로 standard 에도 (훈련·봉쇄·분쟁
  수역 등 면(面) 사건). rings 는 코드 변경 불요 — **프롬프트 결정 트리에 발동 트리거
  명문화** ("본문에 사거리·도달권·작전반경 수치가 있으면 rings 후보, radius_km 는 본문
  근거 수치만"). front·phases 는 르포 전용 유지 (일반 보고서의 담백함 보존, 사용자
  게이트로 추후 개방 가능).
- **S-2. event_timeline 공용**: type 1개를 두 포맷이 공유, 테마 토큰만 분기 (르포
  다크/플랫 vs editorial 세리프/라운드). 렌더러 분기 없음 — 기존 테마 토큰 시스템이
  자동 처리.
- **S-3. heatmap·stacked 소생**: §2.1 수정의 시각 결과물. heatmap 표준형 = 국가×항목
  2D 격자, 잉크 농도 사다리 ≤4단 + 액센트 0~1셀 (mono guide §10 정합).
- stakeholder_map 의 standard 개방은 **이번 범위에서 제외** (르포 정체성 요소 — 개방
  여부는 사용자 결정 대기. 단, `freeform_essay.html` 의 죽은 network 분기 정리 +
  stakeholder_map has_data 분기 추가는 §6 배관 수리에 포함 — 현재는 가드-템플릿
  불일치 재발 대기 상태).

## §5. Anime.js 검토 — 불채택 권고

**결론: 도입하지 않는다.** 근거:

1. **필요 기능이 이미 있다.** 진입 애니는 `charts.js:_applyEntryAnimation`
   (IntersectionObserver + d3 transition — bar 성장·donut 스윕·선 draw-in·점 스태거)
   에 중앙화돼 있고, ambient 는 CSS keyframes (`.sm-flow`/`.sm-pulse`) + `d3.timer`
   (지구본 자전) 로 구현돼 있다. V9 신규 모션(전선 draw-in, 국면 보간, 타임라인
   스태거)은 전부 이 프레임워크의 확장으로 충분하다 — 목업 2종이 실제로 d3 만으로
   해당 모션을 시연한다.
2. **의존성 비용이 이득보다 크다.** CHART-AP 43개의 역사가 보여주듯 렌더 계층의
   회귀 표면이 이미 넓다. 라이브러리 1개 추가 = STATIC_ASSETS 동기화·standalone
   인라인·osint 재렌더 계약·reduced-motion 정책의 4중 접점이 늘어난다. Anime.js 가
   주는 차별 기능(스프링 물리·타임라인 오케스트레이션)은 정적 보고서의 mono 미학에서
   쓸 곳이 없다.
3. **참고**: 기술적으로 vendoring 은 쉽다 (`STATIC_ASSETS` 튜플 1곳 + 템플릿 script
   태그 — `report_synthesizer.py:32` 의 기존 패턴). 향후 osint 영상 쪽(영상미 최우선
   가치)이 요구하면 그쪽 repo 에서 독립 채택하는 것이 맞고, 보고서 HTML 은 무관하다.

**대신 하는 것 (기존 프레임워크 확장):** ① 전선·경로 draw-in ② 국면 전환 보간
③ event_timeline 스파인+스태거 ④ (문서 drift 해소) CLAUDE.md 가 이미 구현됐다고
기술한 "sankey 중심선 입자" ambient 는 **코드에 없다** — 구현하거나 문서에서 삭제
(사용자 결정, §9).

## §6. 시각물 전달 보증 (Visual Delivery Guarantee)

"목업은 좋은데 실보고서에서 사라진다"의 구조적 재발 방지. 원칙: **방출된 시각물은
(a) 렌더되거나 (b) 드롭 사유가 관측되거나** 둘 중 하나여야 한다. 셋째 길(침묵)은 없다.

1. **3중 parity fixture (최고 가치 1개).** `_TYPE_TO_GUARD` 등록 전 type 에 대해
   "SYSTEM_PROMPT 가 문서화한 데이터 모양 → ① `validate_chart_data` 통과 → ② 두
   템플릿 has_data 통과 → ③ 렌더러가 읽는 필드명·경계값 일치" 를 한 fixture 로 검증.
   B5/B6(heatmap/stacked)·CHART-AP-38·템플릿 drift·렌더러 경계 drift 를 전부 한
   테스트 클래스로 잡는다. 신규 type 은 이 fixture 에 등록돼야 랜딩 가능.
2. **usage_log 2단화**: `emit`(드롭 전) / `kept`(드롭 후) + 드롭 사유 상위 N 요약.
   rebalance 힌트는 kept 기준. `emit−kept` 누적 type 은 "배관 이상" 경고 (기아와 구분).
3. **드롭 표면화**: `_drop_invalid_charts` 드롭 수 > 0 이면 발행 후 텔레그램 관리자
   라인에 1줄 요약 (degraded 배너 인프라 재사용, 구독자 브로드캐스트 아님).
4. **템플릿 has_data 규칙의 SSOT 화**: 서버측 사전계산 1곳 (렌더 직전 `_renderable`
   플래그) → 두 템플릿은 플래그만 본다. freeform 의 죽은 network 분기 제거.
5. **폴백 시각물 보존**: §2.3 (head-loss chart salvage + minimal fallback 주입 차트).
6. **지도 최소 가드 + 로컬 아틀라스 폴백**: §2.5.
7. **9단계 신규 type 절차** (CLAUDE.md Chart System 의 7단계를 대체): 기존 ①~⑦ +
   ⑧ 두 템플릿 has_data(또는 `_renderable` SSOT) 등록 + ⑨ parity fixture 등록.
   그리고 신규 type/payload 확장은 **osint 통지(n) 후 랜딩** (PROTOCOL.md 준수).

## §7. 이월 2건 (이전 세션 지적 사항) — 구현 스펙

### §7.1 wrangler 무한 대기 → 타임아웃 + 강제 종료 — ✅ **v8.5.12 완료**

- 위치: [report_synthesizer.py:1011-1018](../src/agents/report_synthesizer.py) —
  `await proc.communicate()` 에 타임아웃이 없다 (8/25 브리핑 행 원인).
- 스펙: `asyncio.wait_for(proc.communicate(), timeout=config.wrangler_timeout_sec)`
  (기본 180s, env `WRANGLER_TIMEOUT_SEC`). TimeoutError 시 `proc.kill()` +
  `await proc.wait()` + warning 로그 + `return ""` — 기존 graceful degrade 경로
  (자격증명 없음과 동일)로 합류해 **파일 첨부 폴백이 항상 도착**한다.
- 동일 패턴 점검 대상: `telegram_bot.py:867` (재배포 경로 — 같은 함수라 자동 해결),
  codex/claude CLI subprocess 호출부는 기존 타임아웃 유무 확인만 (별건).
- 회귀: 모킹 proc 로 timeout→kill→"" 경로 테스트.

### §7.2 CLAUDE.md 43.8k 토큰 다이어트

- 실측 88KB. CLI 호출마다 실리므로 보고서 1건(context+composer+critic 루프)당 수 회
  누적. 목표 **≤ 25KB** (–70%).
- 방법 (거버넌스 준수 — 사실은 한 곳, 나머지는 링크):
  1. V6 트랙 서사 단락(§Project Overview 의 3KB 짜리 이력 문단), v8.2.x 개별 릴리스
     서사, Change Propagation Matrix 의 V5 전용 행들 → `docs/` 해당 SSOT 로 이관하고
     CLAUDE.md 엔 표 링크 1줄.
  2. CHART-AP/WRITE-AP 요약 리스트(이미 SSOT 가 docs 에 있음) → 개수 + 최신 5개 +
     링크로 축약.
  3. 유지하는 것: 🔴 불변 규칙 블록(운영 모드·systemd·핫픽스 시퀀스·osint 교신·명령어
     없는 지시 금지), Execution Rules, 신규 type 9단계, 디렉토리 지도.
  4. 검증: 다이어트 후 `wc -c CLAUDE.md` ≤ 25600, 삭제된 사실이 docs 링크로 전부
     도달 가능한지 체크리스트.
- 참고: `osint_generator/CLAUDE.md` 는 8KB 로 건전 — 대상 아님.

## §8. 구현 페이즈 (Opus 5 실행용)

> 공통 원칙: 페이즈당 1 커밋 이상, 각 페이즈는 독립 배포 가능. **모든 신규 렌더
> 어휘는 additive** — 무지정 payload byte-equal. 페이즈 완료 시 CHANGELOG + 본 문서
> 헤더 `last_synced_with` 갱신. VM 반영은 `git pull` + `sudo systemctl restart
> agents-reviewer.service` (playbook §1).

- **V9-0 배관 수리 (P1, 최우선)** — ✅ **완료 (v8.5.11 + v8.5.12)**.
  v8.5.11: §2.1 heatmap/stacked 통일 + parity fixture (CHART-AP-44).
  v8.5.12: §2.2 usage_log emit/kept 2단 · §2.3 폴백 salvage · §2.4 has_data SSOT ·
  §2.5 지도 조건 완화 + world-atlas 로컬 폴백 · §6.3 드롭 표면화 · §7.1 wrangler
  상한 (CHART-AP-45, `test_visual_delivery_guarantee.py` 12종).
  잔여: MapPayloadGuard(§2.5) · 렌더러 경계값 가드 정합(§2.4) · CLAUDE.md 다이어트(§7.2) · 잔여: §6.2 usage_log 2단화 · §6.3 드롭 표면화 · §6.4
  has_data SSOT 화 · §2.3 폴백 salvage · §7.1 wrangler 타임아웃 · report_bundle_v1.md
  §해당 각주 정정. 검증: `pytest tests/regression/` 전체 + parity fixture 신규 통과.
- **V9-1 event_timeline (P2)** — 9단계 절차 + 두 포맷 프롬프트 편입 + 르포 타임라인
  모순 해소 + osint 질문(q) 스레드 (영상 렌더 폴백 협의). 목업 R-2/S-2 가 시각 기준.
- **V9-2 전황 어휘 (P3)** — maps.js `paths`/`zones`/`phases` + MapPayloadGuard +
  maps.js markers-필수 완화 + world-atlas 로컬 폴백 + 프롬프트 (르포 front/phases,
  공통 zones, rings 트리거) + osint 통지(n). 목업 R-1/S-1 이 시각 기준.
- **V9-3 작전 스키매틱 (P4)** — `basemap:"schematic"` + `terrain`. 목업 R-3.
- **V9-4 CLAUDE.md 다이어트 (P7 후반)** — §7.2. 코드 무변경 커밋.
- 각 페이즈에서 지켜야 할 기존 안티패턴: CHART-AP-17 (5-Layer Usage Guarantee — 신규
  type 은 결정 트리·fixture 까지 한 번에), CHART-AP-14/15/16/28/36/37/38/39,
  WRITE-AP-5/26, AP-V7-6 (annotation ≤3), mono guide §4/§6/§10.

## §9. 문서 drift 정리 목록 (구현 페이즈에서 함께)

1. CLAUDE.md "27종 type" — 실제 RENDERERS 는 **31종** (combo_candle/iv_skew/
   indicator/stakeholder_map 추가 후 미갱신).
2. CLAUDE.md "sankey(중심선 입자)" ambient — **코드에 없음** (charts.js 에 d3.timer/
   입자 없음). 구현 or 문구 삭제 (사용자 결정).
3. `freeform_essay.html:438` 죽은 `network` has_data 분기 + stakeholder_map 분기 부재.
4. `VISUAL_CAPABILITY_REGISTRY.yaml` 유령 type 3종 (decision_matrix/chord/treemap —
   렌더러·프롬프트 부재) + `stacked_bar`↔`stacked` 명칭 drift + candle/combo_candle/
   iv_skew/indicator 미등록.
5. `report_bundle_v1.md:428-431` heatmap 각주 오류 (§2.1).
6. `research_director.design_via_heuristics` 가 폐기된 `network` 를 allowed/forbidden
   에 여전히 emit (`research_director.py:307,327`).
