---
tier: 2
status: active (v5.5.0 producer PR — emit 배선 완료)
contract_version: 1
last_synced_with: v5.5.0
ssot_for:
  - "agents_reviewer ↔ osint_generator report_bundle 핸드오프 계약 v1"
  - "ReportBundle JSON 필드 / 타입 / 의미"
  - "origin → verification 기본 매핑"
  - "schema_version 거버넌스 규약 (계약 버전 ↔ producer.version 분리)"
depends_on:
  - "src/visual/schemas.py (차트 21종 data shape SSOT — pin only, 재정의 금지)"
  - "src/models.py:ComposedReport / ContextAnalysis"
  - "src/lens_policy.py:ALL_THEMES + src/templates/report.css ([data-theme] 토큰)"
  - "src/tools/market_fetcher.py:MarketSeries (출처 provenance)"
last_review: 2026-05-25
---

# report_bundle 핸드오프 계약 v1 (agents_reviewer → osint_generator)

> **STATUS: ACTIVE** — osint_generator 가 §1~9 를 확정 회신(2026-05-25),
> 예시 번들 seam 통과(GREEN, consumer v0.18.1). agents_reviewer producer PR
> (`v5.5.0`: `ReportBundle` 모델 + `.bundle.json` emit + 결정론 provenance +
> `/analyze --bundle` / `/bundle <id>`) 머지로 active 전환. 이 문서가 계약의 SSOT.
> 실제 emit 의 필드 충실도(§11 빈값 규약 등) 재검증은 consumer 측 후속.

## 0. 역할

- **Producer = agents_reviewer.** "중요" 보고서에 대해 버전 박힌 단일 산출물
  `analysis_{ts}.bundle.json` 을 emit, Cloudflare Pages 로 배포.
- **Consumer = osint_generator.** bundle 을 수신 Pydantic 모델로 받아
  `bundle → research_dossier` 어댑터로 자기 파이프라인(research → script →
  scene → render) 에 주입. verification 라벨을 무손실 전파.
- **연동 방식**: A안(차트 데이터만 받아 osint_generator 의 Remotion/React 로
  재렌더) 기본 + 복잡 3종(map/choropleth/network/sankey)만 B안(정적 SVG 수신).
  C안(charts.js 흡수)은 채택하지 않음.

## 1. 확정된 의미론 (canonical — 변경은 §7 거버넌스 따름)

### §1 verification enum (5값, 글자 고정)
```
confirmed | inferred | claim | unverified | disputed
```
consumer 화면 라벨 `<확인>/<추론>/<주장>/<미검증>/<반박됨>` 은 **오직 이 단일
축에서만** 파생된다.

### §2 origin → verification 기본 매핑
| origin | 기본 verification |
|---|---|
| `measured` (KRX/FRED/ECOS/YAHOO 실측) | `confirmed` |
| `narrative_inference` | `inferred` |
| `model_forecast` (예측·시나리오) | `inferred` |

개별 차트/주장이 `verification` 을 **직접 지정하면 그 값이 우선**한다.
producer 는 market_fetcher 출처 차트에 `measured`/`confirmed` 를 **자동 주입**한다.

### §3 검증 권위
verification 의 권위는 **producer(agents_reviewer)** 에 있다. consumer 는
재검증/강등 floor 를 두지 않고 값을 그대로 신뢰한다. → 차트·주장별
`verification` 정확도가 그대로 consumer 화면 라벨이 된다. **이것이 본 연동
품질의 단일 병목**이며, producer 의 Q5(차트별 `provenance.verification` +
시장데이터 source 자동주입)가 최우선 정확도 대상이다.

### §4 confidence / evidence.stance
- `confidence`: `low | medium | high` (3값 고정)
- `evidence.stance`: `supports | refutes | contextual` (3값 고정)
- 필드명(`quote_or_data` 등)은 producer 표기 유지 — consumer 어댑터가 매핑.

### §5 prerendered_svg 위치
`charts[]` **그리고** `map` 객체 양쪽에 `prerendered_svg` 칸을 둔다.
B안(정적 SVG) 대상: map / choropleth / network / sankey. A안 대상 차트는 `null`.

### §6 텍스트 레지스터
`prose` / `headline` / `deck` / `pull_quote` 는 **편집체 그대로** 둔다.
TTS 발화형 한국어 변환은 consumer 의 ScriptWorker 책임. producer 는 TTS 정제를
하지 않는다 — `prose` 는 나레이션의 *원천*이지 최종 나레이션이 아니다.

### §7 schema_version 거버넌스
- `schema_version` = **이 계약의 버전**. `producer.version`(예: `v5.4.9`)과 분리.
- **additive**(optional 필드 추가) = 증분 안 함.
- **breaking**(필드 제거/타입 변경/의미 변경) = 증분 + 양측 동시 반영.
- 증분은 **양측 협의로만**.

### §8 참조 무결성
- `sections[].chart_refs / claim_refs / image_refs`, `sections[].map_ref`,
  `charts[].provenance.sources[].source_id`, `claims[].evidence[].source_id`,
  `claims[].chart_refs` 는 모두 **같은 bundle 내 id 로 resolve** 돼야 한다.
- `sections[].map_ref` 는 `map.id` 로 resolve 또는 null (§10).
- 모든 id(`section_id`/`chart_id`/`claim_id`/`source_id`/`map.id`/이미지 id)는
  bundle 내 **unique**. producer 는 emit 시 `model_validator` 로 강제(미해결 ref /
  중복 id → reject).

### §9 차트 data shape SSOT
차트 21종의 `data` 모양은 **`src/visual/schemas.py` 가 유일 SSOT**.
본 계약은 그 버전을 **pin 만** 하고 shape 을 재정의하지 않는다(이중 SSOT 회피).
consumer 는 schemas.py 를 자기 Pydantic 으로 미러한다.

> **Pinned**: `src/visual/schemas.py` @ `producer.version = v5.4.9`
> (`_TYPE_TO_GUARD` 21종: bar/line/area/donut/stacked/stacked_bar/bubble/heatmap/
> gantt/network/candle/dual_line/forecast/choropleth/scatter/stacked_area/
> lollipop/slope/small_multiples/waterfall/range_bar/sankey).
> shape 변경 시 producer 가 본 pin 갱신 + §7 절차.

### §10 map 참조 해소 (v1 draft 보정 — 2026-05-25 seam 발견)
초안에서 `section.map_ref="m-1"` 이 resolve 안 되는 갭 발견(map 객체에 id 없음 +
`map.markers[].id="mk-1"` 와 불일치).
**확정: map 은 보고서당 단일 optional 객체이며 `id` 필드(예: `"map-1"`)를 가진다.
`section.map_ref` 는 `map.id` 로 resolve 또는 null.**
- **A안(list[Map]) 미채택** — producer 는 구조적으로 보고서당 ≤1 map
  (`ComposedReport.embedded_map: dict|None`)만 emit. 다중 지도는 speculative generality.
- **B안(bool/생략) 미채택** — §8 의 균일한 "ref=id 포인터" 모델을 깨고 map 만 특수화.
- producer 현실: map 은 report-level 요소(특정 섹션에 바인딩 안 됨). composer 가
  섹션↔지도 바인딩을 emit 하기 전까지 `section.map_ref` 는 **null 이 기본**. 바인딩
  신호가 생기면 해당 섹션이 `map.id` 를 가리킨다.

### §11 빈값 / optional emit 규약 (seam 확정 — 2026-05-25)
consumer 수신 모델(v0.18.0)의 확정 규약. producer 는 이대로 emit:
| 종류 | 허용 | 금지 |
|---|---|---|
| 문자열 스칼라 (`deck`/`closing`/`note`/`pull_quote`/`heading`/`kicker` 등; `headline` 제외) | `""` 또는 키 생략 | `null` |
| 리스트 (`chart_refs`/`image_refs`/`claim_refs`/`markers`/`arcs`/`legend`/`sections`/`charts`/`claims`/`signals`/`contradictions`/`sources`) | `[]` 또는 생략 (`image_refs` 는 `[]` 권장) | `null` |
| optional 객체/참조 (`map_ref`/`prerendered_svg`/`theme`/`map`/`confidence`) | `null`·생략·값 모두 | — |
- 지리 없는 보고서: `map`/`signals`/`contradictions`/`confidence` 통째 absent 허용 (seam 검증됨).
- `map.markers[].id`, `map.legend[].kind` 는 consumer 미러됨 — 그대로 emit.

## 2. 번들 스키마 (필드 / 타입)

> chart `data` 내부 모양은 §9 에 따라 schemas.py 참조. 아래는 *컨테이너* 계약.
> 출처 범례: `[기존]` = 현재 `analysis_{ts}.json`(FullAnalysisResult dump)에
> 이미 존재 → 매핑만. `[신규]` = producer PR 에서 신설(주로 provenance/claims).

```jsonc
{
  "schema_version": 1,                       // 계약 버전 (§7)
  "bundle_kind": "report_bundle",
  "generated_at": "ISO-8601 (+09:00)",
  "producer": { "system": "agents_reviewer", "version": "v5.4.9", "mode": "fast|standard|deep" },

  "report": {
    "report_id": "analysis_{ts}",            // [기존] 파일 stem, bundle 식별자
    "headline": "str",                        // [기존] 편집체 (§6)
    "deck": "str",                            // [기존]
    "closing": "str",                         // [기존] optional
    "html_url": "str",                        // [기존] Pages 보고서 URL
    "theme": {                                // [신규] 선택된 테마 박제 (random 이므로 필수)
      "id": "editorial_cream|burgundy_mono|slate_steel|forest_sage|midnight_indigo|dusk_rose|paper_classic",
      "tokens": { "bg","card","text","muted","accent","up","down","border": "#hex" },
      "fonts": { "serif":"Noto Serif KR", "sans":"Noto Sans KR", "mono":"IBM Plex Mono" }
    }
  },

  "sections": [{                             // [기존] composed_report.sections
    "section_id": "str (unique)",
    "heading": "str",
    "kicker": "str",                          // optional
    "prose": "markdown str",                  // 나레이션 원천 (§6)
    "pull_quote": "str",                      // optional
    "chart_refs": ["chart_id"],               // §8 resolve
    "map_ref": "map id | null",               // §8
    "image_refs": ["image id"],
    "claim_refs": ["claim_id"]                // §8
  }],

  "charts": [{                               // data shape = §9 schemas.py
    "chart_id": "str (unique)",
    "type": "schemas.py _TYPE_TO_GUARD 21종 중 1",
    "title": "str",
    "data": "<schemas.py type별 shape>",
    "note": "str | null",
    "provenance": {                           // [신규] §2/§3/§4
      "origin": "measured|narrative_inference|model_forecast",
      "verification": "<§1 enum>",            // 미지정 시 §2 매핑
      "confidence": "low|medium|high",
      "sources": [{ "source_id":"str","provider":"KRX|FRED|ECOS|YAHOO|web","code":"str","unit":"str","fetched_at":"str","url":"str" }]
    },
    "prerendered_svg": "str | null"           // §5 — A안 차트는 null
  }],

  "map": {                                   // [기존] embedded_map + [신규] id/provenance/svg
    "id": "str (unique)",                     // [신규] §10 — section.map_ref resolve 대상
    "center": [lng, lat], "zoom": 0.0,
    "markers": [{ "id","name","lng","lat","highlight" }],
    "arcs": [{ "from_id","to_id","label" }],
    "legend": [{ "label","kind","highlight" }],
    "provenance": { "origin","verification","confidence","sources": [] },  // [신규]
    "prerendered_svg": "str | null"           // §5
  },

  "claims": [{                               // [신규] §8 — consumer ResearchDossier 직매핑
    "claim_id": "str (unique)",
    "statement": "str",
    "status": "<§1 enum>",                    // = 화면 라벨 결정축
    "confidence": "low|medium|high",
    "cross_checked": true,
    "evidence": [{ "source_id":"str","quote_or_data":"str","locator":"str","reliability":"primary|secondary|expert|model_inference","stance":"supports|refutes|contextual" }],
    "chart_refs": ["chart_id"]                // §8
  }],

  "signals": [{ "signal","description","indicates","deadline","verification" }],  // [기존] watch_signals
  "contradictions": [{ "side_a","side_b","evidence","resolution" }],              // [기존] (봉합 금지 보존)
  "sources": [{ "source_id":"str (unique)","url","publisher","title","fetched_at" }],  // [신규] context.sources 정규화
  "confidence": { "score": 0.0, "summary": "str" }                                // [기존] report-level
}
```

## 3. 전달 · 트리거

- 경로: **HTTP (Cloudflare Pages)**.
- URL: `{pages}/analysis_{ts}.bundle.json`.
- 트리거: `/analyze <주제> --bundle` 또는 `/bundle <report_id>`. "중요" 보고서만
  온디맨드 emit.

## 4. 예시

schema-valid 예시 1건: [`report_bundle_v1.example.json`](report_bundle_v1.example.json)
(차트 없이 텍스트 슬라이드 seam 검증용으로도 충분 — chart/map 은 consumer 가
무시 가능). **단 이 손예시는 `claims` 가 채워져 있어** seam 의 라벨 척추를 claim
경로로 시연한다 — v5.5.0 라이브 emit 의 실제 `claims=[]` 현실과 다르다.

**realistic 샘플 2건 (v5.5.0, fixture-derived)** — 실제 composer 형태 ComposedReport
fixture 를 실제 `src/handoff/bundle_builder.py` 빌더에 통과시킨 결과 (LLM run 아님,
producer 코드 경로·직렬화는 real emit 과 동일). `claims=[]` 현실 + 라벨 척추가
`charts[].provenance.verification` 를 타는 모습을 보여준다:
- [`report_bundle_v1.realistic_geo.json`](report_bundle_v1.realistic_geo.json) — 지정학
  (map 객체 존재, gantt/bubble 차트 모두 `inferred`, signals 5 / contradictions 3).
- [`report_bundle_v1.realistic_fin.json`](report_bundle_v1.realistic_fin.json) — 금융
  (`line` 차트가 market_fetcher time_series 매칭 → `measured/confirmed` + `sources:[YAHOO]`,
  나머지 `inferred`, `map: null`).

**§11 빈값 규약 — 위 샘플로 확정**: producer 는 키를 *생략하지 않는다*. `note`/
`pull_quote` → `""`, `map_ref` → `null`, `claim_refs`/`image_refs` → `[]`,
`prerendered_svg` → `null`, `map`/`confidence` 부재 시 키 존재 + `null`. consumer 는
옵셔널 객체(`map`/`confidence`) 만 null 체크하면 된다.

> fixture 의 heatmap 차트는 `ComposedSection._drop_invalid_charts` (HeatmapGuard,
> `{x,y,value}` 요구) 가 fixture 의 `{title,severity}` 형태를 guard-drop 해 번들에
> 미포함 — fixture 가 오래된 탓이지 빌더 결함 아님 (라이브 composer 는 guard 통과
> 차트만 emit).

## 5. 변경 이력

| contract_version | 날짜 | 변경 | 비고 |
|---|---|---|---|
| 1 (draft) | 2026-05-25 | 초안 확정 (§1~9) | producer PR 머지 시 active |
| 1 (draft) | 2026-05-25 | seam 보정: §10 map 참조 해소 (map.id) + §11 빈값/optional emit 규약 | schema_version 무증분 (draft 보정, 양측 합의) |
