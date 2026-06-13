---
tier: 2
status: active (v5.5.0 producer PR — emit 배선 완료)
contract_version: 1
last_synced_with: v7.6.2
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

- **Producer = agents_reviewer.** 모든 보고서에 대해(v5.5.3, `enable_report_bundle`
  디폴트 ON) 버전 박힌 단일 산출물 `analysis_{ts}.bundle.json` 을 emit, Cloudflare
  Pages 배포 + 텔레그램 문서 자동 첨부.
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

**v5.5.6 — B안 구현됨 (additive, schema_version 무증분).** consumer(osint_generator)
가 "전-타입 SVG" 요청을 철회하고 A안(데이터-온리 재렌더)으로 수렴 — B안은 복잡 4종의
*폴백* 으로만 채운다. producer 는 `prerender_svg=True` (config `enable_bundle_prerender`,
디폴트 ON) + Playwright 가용 시 charts.js/maps.js 를 헤드리스 렌더해 해당 4종의
`prerendered_svg` 를 독립 SVG 로 채운다. Playwright/chromium 미설치·렌더 실패·네트워크
차단(map 의 world-atlas fetch) 시 graceful `null` — 본 칸은 *언제나 optional* (§7 의
"optional 은 null/생략/값 모두 valid"). A안 17종 차트는 항상 `null` 유지. SSOT:
`src/handoff/svg_prerender.py`.

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
| optional 객체/참조 (`map_ref`/`prerendered_svg`/`theme`/`map`/`confidence`/`video` [§13]) | `null`·생략·값 모두 | — |
- 지리 없는 보고서: `map`/`signals`/`contradictions`/`confidence` 통째 absent 허용 (seam 검증됨).
- `map.markers[].id`, `map.legend[].kind` 는 consumer 미러됨 — 그대로 emit.

### §12 차트 display (스트립 vs 본문 단일차트) — v6.1.1 additive
`charts[].display` 는 그 차트가 보고서에서 *어떻게* 렌더되는지를 명시한다. 영상
파이프라인(osint_generator)이 "작게 묶여 나오는 보조 지표"와 "본문에 크게 박히는
단일 차트"를 구분해 비주얼을 배치하기 위함. SSOT 는 렌더러(`freeform_essay.html`
의 `ch.role == 'compact'` 분기)와 동일 규칙.

| 값 | 의미 | 영상 사용 가이드 |
|---|---|---|
| `"strip"` | 보고서에서 작은 sparkline 한 줄(compact strip)로 렌더되는 **보조 시계열** 차트. 여러 종목/지표를 한 줄에 묶은 것 (보통 `type: line/candle/area`). | 단독 풀화면 차트로 크게 쓰지 말 것 — 보조 지표 묶음(티커 스트립)으로 취급. 묶어서 한 컷. |
| `"full"` | **본문 단일 차트** (sankey/waterfall/gantt/scatter/bar/donut/…​ 및 strip 아닌 모든 차트). | 개별 비주얼로 한 컷씩 사용. |

- producer 매핑: composed chart 의 `role == "compact"` → `"strip"`, 그 외 → `"full"`.
- **항상 존재** (default `"full"`). `null`/`""` 금지 — §11 의 자유 스칼라 규약과 별개로
  고정 enum(`strip`/`full`).
- additive (§7) — schema_version 증분 안 함. 구 consumer 는 필드 무시해도 무해.

### §13 video 내레이션 (영상 자막·음성 대본) — v7.3.0 additive

영상 파이프라인의 자막·내레이션이 고정 템플릿으로 합성돼 기계적이었던 문제 +
차트 없는 서술(prose) 전용 섹션이 영상에서 통째로 누락되던 문제의 해소.
**내용을 가장 잘 아는 보고서 생성 시점(composer)에 producer 가 대본을 함께
emit** 하고, consumer 는 LLM 호출 없이 결정론 렌더를 유지한다 (사용자 확정,
2026-06-12).

**`sections[].video`** (optional 객체 — `null`·생략·값 모두 valid, §11):

| 키 | 타입 | 규칙 |
|---|---|---|
| `narration` | `string[]` | 2~4문장. 그 섹션 씬(차트 씬 포함)의 자막·음성 대본. **한 문장 ≤75자** (v7.6.0 1차 음성 검수 — 축약 금지·말하듯 풀어쓰기 위해 58→75 완화, 양측 합의값. 자막 줄바꿈은 consumer 처리, 초과분만 … 절단) |
| `highlights` | `string[]` | 1~3개. 화면에 크게 띄울 key takeaway — 스테이트먼트 씬(대형 타이포). 문장보다 문구, **≤40자** |
| `emphasis` | `string[]` | narration/highlights 안의 **정확한 부분 문자열**만. 화면에서 액센트 색 강조 |
| `narration_tts` | `string[]` | **자막=narration, 음성=narration_tts (표기용/발화용 분리).** narration 에 TTS가 깨뜨릴 표기(숫자·영문 약어·기호·단위)가 한 문장이라도 있으면 producer 가 채운다 — narration 과 *같은 순서·개수*, 바꿀 게 없는 문장은 동일하게 둠. 순한 한국어뿐이면 생략 OK (그땐 consumer 발음 사전이 처리). 작성 규칙 SSOT: `prompts/tts_narration_guide.md` (v7.4.0) |

**`report.video`** (optional 객체): `{ "intro_narration": string[] (1~2문장,
타이틀 씬), "outro_narration": string[] (1~2문장, 클로징 씬),
"intro_narration_tts": string[], "outro_narration_tts": string[] }`.
`*_narration_tts` (v7.4.1 additive) 는 섹션 `narration_tts` 와 같은 규칙 —
intro/outro 에 TTS 위험 표기가 있으면 같은 순서·개수의 발화용 배열을 채운다
(자막=`*_narration`, 음성=`*_narration_tts`). 비면 consumer 발음 사전이 처리.

**`timeline.video`** (optional 객체 — v7.6.0 additive, 1차 음성 검수 반영):
`{ "narration": string[] (3~4문장, 각 ≤75자), "narration_tts": string[] }`.
타임라인 씬에 video 가 없어 consumer 가 기계 문장으로 메우던 것을 producer
대본으로 대체. narration 은 분기점들을 *이야기로 잇는* 문장 — **분기점 라벨
낭독 금지** (라벨은 화면이 보여줌). composer 는 `timeline_flow.video` 로 emit,
`src/timeline_flow.py` 패스스루 → `bundle_builder._timeline_video` 결정론 가드
(≤4 캡, 길이·TTS gap warn). highlights/emphasis 없음.

**`contradictions[].video`** (optional 객체 — v7.6.2 additive, 2차 음성 검수 반영):

| 키 | 타입 | 규칙 |
|---|---|---|
| `label_a` / `label_b` | `string` | 두 입장의 진영 이름. 한 단어 명사구, **≤8자** (예: "묵인론"/"전술론") |
| `line_a` / `line_b` | `string` | 각 입장의 한 줄 요약 — 다큐 경어체, **≤40자** (스테이트먼트 씬, 카드에 크게). "~입니다/~수도 있습니다" 로 끝냄 |
| `narration` | `string[]` | 쟁점 씬 자막 2~3문장(경어체, 각 ≤75자) |
| `narration_tts` | `string[]` | 섹션과 같은 표기용/발화용 분리 규칙 |

영상이 `side_a`/`side_b` *논설체 원문* ("…정책 전환이다") 을 카드·자막에 그대로
노출하던 것을 producer 의 다큐 경어체 대본으로 대체. `side_a`/`side_b` 원문은
그대로 두고 `video` 만 **더한다** (additive). composer 가 `contradictions[].video`
로 emit → `bundle_builder._contradiction_video` 결정론 가드 (label ≤8 / line ≤40 /
narration ≤4 캡·길이 warn, TTS gap warn). 모든 필드 비면 `null` (= consumer 기존
원문 폴백).

**작성 규칙 개정:**
스키마 구조는 그대로, "쓰는 법" 개정. 전체 기준서 SSOT 는
`prompts/tts_narration_guide.md`:
- **v7.6.0 (1차 검수, §1/§2/§6):**
  1. **축약 금지 — 말하듯 풀어쓰기 (최우선).** narration 은 자막용 요약문이 아니라
     성우가 읽는 구어체 대본. 한 문장 한 정보, 명사 나열 대신 주어-동사 문장.
     한도 75자로 완화된 만큼 조사·서술어를 삭제하지 말 것.
  2. **날짜 콤마 나열 금지** — "{날짜}, {문장}" 가 아니라 "{날짜}에는 ~했습니다".
  3. **제목·라벨 낭독 금지** — 섹션/차트 제목·타임라인 분기점 라벨은 화면이 보여줌.
  4. **narration_tts 발음 강화** — 숫자 전부 한글+자연 띄어쓰기("삼십이 개월",
     "일곱 개"), 경음화 표기("해지꿘", "조껀"). 원칙: "한글로 받아쓴 발음 그대로".
- **v7.6.2 (2차 검수, §1 + §0-2-3):**
  5. **무기 체계명 음차 표기 금지 → 영문** — "장보고-엔"·"장보고 엔" → "장보고 N"
     (headline/heading/highlights/prose 전반).
  6. **highlights 가 heading 을 그대로 반복 금지** — heading 이 안 보여준 구체
     수치·고유명사를 담는다 (producer `_section_video` 가 정확 일치 시 warn).
  7. **가운뎃점(·)으로 항목 두 개 붙이기 금지** — 조사로 풀거나 ` · `(앞뒤 공백).
  8. **narration 각 항목은 완결된 한 문장** — 비교·연결 도중 절단 금지.

**의미론 (consumer 측 확정 동작):**
- `video` 있음 → highlights 는 스테이트먼트 씬, narration 은 해당 구간 자막.
  **차트 있는 섹션의 narration 은 그 차트 씬의 자막이 된다** (템플릿 문장 대체).
- `video` 없음(`null`) → 기존 동작 (서술 전용 섹션은 영상에서 누락).
- **사실 근거(최우선)**: narration/highlights 의 모든 수치·날짜·고유명사는 같은
  섹션 `prose` 또는 번들 구조화 데이터(charts/timeline/signals/…)에 실재해야
  한다. consumer 검증기가 대조해 **불일치 문장은 폐기 + 템플릿 폴백**.
- 미검증 주장(verification ≠ official/confirmed)을 문장에 쓰면 문장 안에
  `<미검증>` 명시 (영상에 그대로 노출 — 원칙).
- 문체: 다큐 브리핑체("~입니다/했습니다"), 과장·수사 금지, 핵심 먼저, 문장 간
  연결 의식 (나열식 금지). 분량 감각: 한 문장 ≈ 화면 4~6초.
- producer 작성 페르소나 (v7.3.1, 사용자 지시): *시사 교양 다큐 내레이션 작가* —
  귀로 듣는 말, 짧은 문장의 연쇄(앞 문장을 다음 문장이 받아 잇기), 한 문장 한
  정보, 명사 나열 대신 동사, 쉽되 가볍지 않은 경어체. SSOT 는 composer
  SYSTEM_PROMPT 의 "★ 내레이터 페르소나" 블록 (consumer 계약 의미론 무변경).
- TTS 발화 규칙 (v7.4.0, 사용자 제공 가이드 반영): AI 음성 티는 *사람이라면 안 읽는
  표기 해석* 에서 난다. `narration_tts` 는 TTS가 틀릴 표기를 발화형으로 미리 바꾼다 —
  숫자 이중 체계(2차전지→이차전지, 6월→유월, 3개→세 개), 영문 약어 한글 음·영상 내
  통일(HBM→에이치비엠), 기호 의미 변환(`→`→'…에서 …로'), URL·파일명 미낭독. 전체
  기준서 SSOT: `prompts/tts_narration_guide.md`, 런타임 단축본: composer SYSTEM_PROMPT
  "★ TTS 발화 규칙" 블록 (둘은 항상 정합). producer 는 narration 에 위험 표기가 있는데
  narration_tts 누락/개수불일치면 `bundle_builder._warn_tts_gap` 로 warn (자동 보정 X —
  문맥 의존이라 결정적 변환이 오독을 만든다). consumer 계약 의미론 무변경.

**producer 측 결정론 가드** (`src/handoff/bundle_builder.py:_section_video` /
`_timeline_video`):
- `narration` ≤4 / `highlights` ≤3 / intro·outro ≤2 / timeline narration ≤4 캡
  (초과분 절단).
- `emphasis` 불일치 항목(부분 문자열 아님)은 emit 전에 drop + warn — consumer
  액센트 매칭이 어차피 실패하므로 producer 가 미리 정리.
- 길이 한도(75/40자) 초과는 **drop 하지 않고 warn** — consumer 의 … 절단이
  정보 파괴보다 낫다. 1차 방어는 composer SYSTEM_PROMPT 의 길이 지시.
- `narration`/`highlights` 둘 다 비면 `video: null` (= 부재).
- WRITE-AP-12 기호 정화(`_sanitize_symbols`)는 video 텍스트에도 적용 —
  narration 과 emphasis 가 *같은 변환* 을 거치므로 부분 문자열 관계 보존.

additive (§7) — schema_version **1 유지**. 구 consumer 는 필드 무시해도 무해.
emit 주체는 composer (LLM, 본문과 단일 호출) — V6 critic 루프의 Opus 보완 패스
뒤에도 원본 video 가 보존되며, prose 교정으로 narration 과 어긋난 사실은 consumer
검증기의 결정론 폐기·폴백 경로가 흡수한다.

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
      "id": "editorial_cream|burgundy_mono|midnight_indigo|pine_forest|graphite_slate",  // v6.2.0 5종 풀
      "tokens": { "bg","card","text","muted","accent","up","down","border": "#hex" },
      "fonts": { "serif":"Noto Serif KR", "sans":"Noto Sans KR", "mono":"IBM Plex Mono" }
    },
    "video": {                                // [신규 v7.3.0] §13 — 타이틀/클로징 씬 대본 (optional)
      "intro_narration": ["str (1~2문장, ≤75자)"],
      "outro_narration": ["str (1~2문장, ≤75자)"],
      "intro_narration_tts": ["str (선택 — 발화용, v7.4.1)"],
      "outro_narration_tts": ["str (선택 — 발화용, v7.4.1)"]
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
    "claim_refs": ["claim_id"],               // §8
    "video": {                                // [신규 v7.3.0] §13 — 섹션 씬 대본 (optional)
      "narration": ["str (2~4문장, 각 ≤75자 — v7.6.0 풀어쓰기 완화)"],
      "highlights": ["str (1~3개, ≤40자)"],
      "emphasis": ["narration/highlights 의 정확한 부분 문자열만"],
      "narration_tts": ["str (선택 — 발음용)"]
    }
  }],

  "charts": [{                               // data shape = §9 schemas.py
    "chart_id": "str (unique)",
    "type": "schemas.py _TYPE_TO_GUARD 21종 중 1",
    "title": "str",
    "data": "<schemas.py type별 shape>",
    "note": "str | null",
    "display": "strip|full",                  // §12 — 스트립(보조) vs 본문 단일차트
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
  "contradictions": [{ "side_a","side_b","evidence","resolution",                // [기존] (봉합 금지 보존)
    "video": { "label_a","label_b","line_a","line_b","narration":[],"narration_tts":[] } }],  // [신규 v7.6.2] §13 — 쟁점 카드 대본 (optional)
  "sources": [{ "source_id":"str (unique)","url","publisher","title","fetched_at" }],  // [신규] context.sources 정규화
  "confidence": { "score": 0.0, "summary": "str" },                               // [기존] report-level

  "timeline": {                              // [v5.5.2] 시간 척추 (optional, §7 additive)
    "heading": "str",
    "points": [{ "date":"YYYY-MM-DD", "label":"str", "phase":"past|present|future", "note":"str" }],
    "video": {                                // [신규 v7.6.0] §13 — 타임라인 씬 대본 (optional)
      "narration": ["str (3~4문장, 각 ≤75자 — 분기점 라벨 낭독 금지)"],
      "narration_tts": ["str (선택 — 발화용)"]
    }
  }
}
```

## 3. 전달 · 트리거

- 경로: **HTTP (Cloudflare Pages)** + **텔레그램 문서 자동 첨부** (v5.5.3).
- URL: `{pages}/analysis_{ts}.bundle.json`.
- 트리거 (v5.5.3): **모든 보고서에 항상 emit** (`config.enable_report_bundle`
  디폴트 ON). `/analyze` 완료 시 텔레그램에 bundle.json 파일+URL 자동 송신.
  기존 보고서는 `/bundle <report_id>` 로 재생성·회수. (v5.5.0~5.5.2 의 `--bundle`
  온디맨드 트리거는 no-op 으로 호환 유지.)

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
| 1 | 2026-06-12 | §13 video 내레이션 (`sections[].video` + `report.video`) — 영상 자막·음성 대본을 producer 가 emit | additive (§7), schema_version 무증분. osint_generator 검수 대기 (샘플: `reports/analysis_20260612_061311_2c19018118.bundle.json`) |
| 1 | 2026-06-12 | §13 TTS 발화 규칙 명문화 — 표기용(narration)/발화용(narration_tts) 분리 + 작성 가이드 SSOT(`prompts/tts_narration_guide.md`) | additive, schema_version 무증분 (필드 의미 정밀화, 새 필드 없음). 샘플 2건 narration_tts 채움 |
| 1 | 2026-06-12 | §13 `report.video.intro_narration_tts` / `outro_narration_tts` 추가 — 타이틀/클로징 씬도 표기/발화 분리 (사용자 확정) | additive (§7), schema_version 무증분. 구 consumer 는 무시해도 무해 |
| 1 | 2026-06-12 | §13 1차 음성 영상 검수 반영 (v7.6.0): `timeline.video` 신설 (타임라인 씬 대본 — 라벨 낭독 금지) + narration 문장 한도 58→75자 완화 (축약 금지·말하듯 풀어쓰기, 양측 합의값) + 작성 규칙 개정 (날짜 조사 연결 / 제목·라벨 낭독 금지 / 발음 강화 — 숫자 전부 한글·띄어쓰기, 경음화) | additive (§7), schema_version 무증분. 영상 쪽도 같은 검수 반영 (템플릿 문장·발음 사전·자막 폭) |
| 1 | 2026-06-13 | §13 2차 음성 영상 검수 반영 (v7.6.2): `contradictions[].video` 신설 (쟁점 카드 대본 — label_a/b ≤8자 / line_a/b ≤40자 경어체 / narration / narration_tts, side 논설체 원문 대체) + 작성 규칙 개정 (무기 체계명 영문 표기 '장보고 N' / highlights 의 heading 반복 금지+producer warn / 가운뎃점 항목 붙이기 금지 / narration 완결 문장) | additive (§7), schema_version 무증분. 영상 쪽도 같은 검수 반영 (쟁점 카드 경어체 변환 제거·자막 폭) |
