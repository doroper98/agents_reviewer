---
tier: 2
last_synced_with: v5.8.3
ssot_for:
  - "보고서 본문 작성 anti-patterns (composer prompt 회귀 방지)"
depends_on:
  - "src/agents/narrative_composer.py:SYSTEM_PROMPT"
  - "src/agents/context_analyst.py:SYSTEM_PROMPT"
  - "src/agents/report_synthesizer.py:_format_structured_text (fallback 변환)"
  - "docs/REPORT_STYLE_GUIDE.md (본문 문체 SSOT — v5.2.9 부터)"
  - "docs/CHART_RENDERING_ANTIPATTERNS.md (코드/렌더링 anti-pattern 별도)"
last_review: 2026-05-17
---

# Report Writing Anti-Patterns

> composer SYSTEM_PROMPT / docs/REPORT_STYLE_GUIDE.md / 보고서 본문 출력에서
> 발견된 *글쓰기 회귀* 모음. CHART_RENDERING_ANTIPATTERNS.md 가 *시각화 코드*
> 회귀 (charts.js / maps.js) SSOT 라면, 본 문서는 *언어/구조* 회귀 SSOT.
>
> composer prompt 변경 / STYLE_GUIDE 변경 / 새 보고서 검증 시 본 문서의
> 체크리스트 위반 여부 *반드시* 점검. 회귀 1건 발견 시 본 문서에 항목 추가
> (append-only) — 같은 실수 반복 방지.
>
> **v5.2.9 — persona dict 채널 폐기**: v4.3.0~v5.2.8 의 `recommended_persona`
> 채널이 사실상 dead 였음을 식별 (composer 의 "느슨하게 적용 / 영감용" + context 의
> "디폴트 그대로 권장" 으로 인해). 본문 문체 SSOT 를 [REPORT_STYLE_GUIDE.md](REPORT_STYLE_GUIDE.md)
> 로 통합. 본 문서의 "persona 가이드와 정합" 류 체크리스트 항목은 "STYLE_GUIDE
> 와 정합" 으로 의미 전환 — 본문은 *과거 기록 보존* 차원에서 그대로 유지하되,
> 신규 항목 작성 시 persona 언급 없이 STYLE_GUIDE 만 가리키면 된다.

---

## WRITE-AP-1: 마크다운 강조 기호 raw 노출 ('AI 작성 흔적')

**증상**: 보고서 본문에 ``*..*`` / ``**..**`` / ``_..__`` 같은 마크다운 기호가 변환 안 되고 raw 텍스트로 노출. 독자가 "AI 가 쓴 글" 임을 즉시 인지.

**최초 사례**: 소말릴란드 보고서 (v4.4.3 사용자 보고). composer prompt 에 ``*..*`` 사용 *금지* 가 명시 안 돼 있었고, ``_format_structured_text`` 필터에도 strip 처리가 없었음.

**v4.4.7 재발 (회귀 확장)**: 같은 보고서 contradictions / watch_signals 섹션에서 ``*..*`` 가 다시 노출. 원인: ``_format_structured_text`` 가 *prose* 에만 적용되고 dict 필드 (side_a/side_b/evidence/resolution, watch_signals.* 등) 에는 미적용. 수정: lightweight ``_strip_markdown`` 신규 + jinja2 filter ``strip_md`` 등록 + ``freeform_essay.html`` 의 모든 raw text 출력에 ``| strip_md`` 일괄 적용 (headline / deck / kicker / heading / pull_quote / chart-card 메타 / contradictions / watch_signals / closing / confidence_summary).

**검증 체크리스트**:
- [ ] composer prompt 의 본문 형식 가이드에 *마크다운 강조 금지* 명시?
  ```
  - prose 는 *순수 한국어 산문*. 마크다운 강조 기호 (*..*, _..__, **..**) 사용
    *절대 금지* — raw 텍스트로 노출되어 'AI 가 작성한 느낌' 을 줌. 강조가 필요하면
    ``pull_quote`` 필드 따로 사용. 인용은 마크다운 ``>`` 도 금지.
  ```
- [ ] `_format_structured_text` 필터에 fallback strip 처리?
  ```python
  text = re.sub(r"\*\*([^*\n]{1,300})\*\*", r"\1", text)
  text = re.sub(r"\*([^*\n]{1,300})\*", r"\1", text)
  # 등
  ```
- [ ] 강조 가능한 라우팅 (pull_quote / chart-takeaway) 이 prose 외 별도 필드에 있나?

---

## WRITE-AP-2: 전문 용어 첫 등장 시 풀이 누락

**증상**: 호른 아프리카 / 우티 포시데티스 / EUV 같은 *전문 지명·개념·약어* 가 처음 등장할 때 한 줄 풀이 없이 사용. 일반 독자가 막힘 — 페르소나 가이드의 "내가 전문 지식이어도 일반인도 이해할 수 있는" 원칙 위반.

**최초 사례**: 소말릴란드 보고서에서 "호른 아프리카" 가 풀이 없이 등장 (v4.4.3 사용자 보고).

**검증 체크리스트**:
- [ ] composer prompt 에 *전문 용어 풀이* 가이드 명시?
  ```
  - 지명·전문 개념·제도 용어가 처음 등장할 때 *한 줄 풀이* 필수.
    예: '호른 아프리카' 첫 등장 → '호른 아프리카 (소말리아·에티오피아·지부티·
        에리트레아 등 아프리카 동북단 지역)'
        'EUV' 첫 등장 → 'EUV (극자외선 노광 공정)'
  - 두 번째 등장부터는 풀이 생략 OK.
  ```
- [ ] persona 가이드의 vocabulary 항목과 정합? (recommended_persona.vocabulary 가 "어려운 개념 한두 문장 풀이" 명시)

---

## WRITE-AP-3: 지리적 사건의 지도 후행 배치

**증상**: 소말릴란드 / 호르무즈 / 우크라이나 같이 *어디에 있는지가 핵심* 인 사건에서, 지도가 보고서 *맨 뒤* 에 배치. 독자가 사건 위치를 모르고 분석을 읽어야 하는 구조.

**최초 사례**: 소말릴란드 보고서 (v4.4.3 사용자 인용: "누가 소말릴란드가 어딨는지 알겠어. 근데 보고서에 맨 아래 구석에 있으니 굉장히 위치가 적절하지 않은거 같음").

**검증 체크리스트**:
- [ ] composer prompt 에 *섹션 배치 가이드* 명시?
  ```
  - 지리적 사건 (영토 / 항만 / 회랑 / 분쟁 지역 / 조약 등) 은 지도 + 지리 맥락
    섹션을 보고서 *상위 (1~2번째)* 에 배치. 독자가 '어디 있는지' 모르면 후속
    분석이 무의미.
  ```
- [ ] 지도가 본문 흐름 *어디에 들어가는지* 도 composer 가 결정? (현재는 ComposedReport.embedded_map 이 보고서 레벨 단일 — section 흐름과 분리. 향후 섹션 inline 으로 emit 가능하게 검토)

---

## WRITE-AP-4: AI 작성 느낌의 표현 (clichés)

**증상**: "다양한 측면에서 살펴보면" / "결론적으로 이는" / "주목할 만한 점은" / "다시 말해" 같은 진부한 연결어. 또는 "더 깊은 분석이 필요하다" 같은 escape 표현. AI 가 자주 쓰는 구문 → 자연스럽지 않음.

**최초 사례**: (잠재적, v4.4.4 시점 신설 — 향후 사용자 피드백으로 누적)

**검증 체크리스트**:
- [ ] composer prompt 의 음슴체 가이드에 *진부한 연결어 금지* 추가?
  - 금지 예: 다양한 측면에서 / 결론적으로 / 주목할 만한 점은 / 다시 말해
  - 허용 예: 사실은 / 단 / 즉 / 그러나 / 반면 / 핵심은
- [ ] persona tone 의 "지적 유희가 살아있되" 가이드와 정합 — 진부한 연결어는 *지적 유희* 의 반대

---

## WRITE-AP-5: 출처 없는 추정을 단정으로 진술

**증상**: composer 가 추정을 *사실처럼* 단정. 예: "북한이 곧 7차 핵실험을 할 것이다" (실제론 추정) → 독자가 사실로 오해.

**최초 사례**: (잠재적 — recommended_persona 의 numeric_principle 가이드와 정합 점검 필요)

**검증 체크리스트**:
- [ ] composer prompt 에 *추정 표현* 가이드?
  ```
  - 출처가 없는 추론은 '~라고 추정' / '~할 가능성' / '~로 보임' 같은
    보수 표현으로 명시. 단정 표현 (할 것이다 / 한다) 금지.
  ```
- [ ] context.sources 에 없는 사실은 *반드시* hedging 표현?

---

## WRITE-AP-6: 모순을 자연스럽게 봉합

**증상**: composer 가 contradictions 필드는 emit 했지만, 본문 prose 에서는 *서로 충돌하는 두 입장* 을 자연스럽게 한 방향으로 봉합. v4.0.0 의 Anti-pattern #5 (모순 봉합 금지) 위반.

**최초 사례**: (잠재적 — 페르소나 의 "지적 유희" 톤이 과해 자연스러움 우선시할 위험)

**검증 체크리스트**:
- [ ] composer prompt 에 *모순 봉합 금지* 명시?
  ```
  - 본문 안에서도 모순·반대 가설을 명시적으로 드러낼 것. 자연스럽게 한 입장으로
    수렴시키지 말 것 — 어느 손 들었는지 + 패배한 입장이 살아나는 조건 함께.
  ```

---

## WRITE-AP-7: 서수와 기수의 모호한 혼용 ('N번' 의 두 얼굴)

**증상**: composer 가 *서수 (첫 번째)* 의미로 "N번" 을 사용. 한국어에서 "N번"
은 식별번호 / 순번 / 문항 뉘앙스가 강해 *서수* 로 즉시 안 읽힘. 결과: 독자가
"무슨 의미지?" 하고 멈춤.

**최초 사례**: 소말릴란드 v4.4.6 보고서 deck — *"유엔 회원국 1번이 호른
아프리카 지도를 흔드는 중"*. composer 의도는 "유엔 회원국 가운데 첫 번째로
[승인했다]" 였으나 "1번" 이 회원국 ID / 등록순서 (예: 알파벳 1번 아프가니스탄)
처럼 읽힘. 사용자 피드백: "유엔 회원국 1번이라는게 무슨 의미야?"

**검증 체크리스트**:
- [ ] composer prompt 의 *수치 / 서수 가이드* 명시?
  ```
  - 서수 (첫 번째 / 두 번째 / N 번째) 의미일 때 *"N번"* 형식 금지.
    "첫", "처음으로", "첫 번째", "가운데 첫" 사용.
    "N번" 은 식별번호 (1번 출입구, 2번 후보) 뉘앙스가 강해 의미 모호.
  - 기수 (개수) 일 때만 "1개", "1국" 사용. 사람·국가 단위는 "한 명" /
    "한 국가" 더 자연스러움.
  ```
- [ ] persona 의 "수치에 굉장히 강하며" 가이드와 정합 — 정확한 수치 표현은
  *모호한 단축형* 의 반대.

**고친 예**:
- 나쁨: `유엔 회원국 1번이 호른 아프리카 지도를 흔드는 중`
- 좋음: `유엔 회원국 가운데 첫 공식 승인. 다음 도미노는 미국·UAE·에티오피아.`
- 좋음: `회원국으로는 처음 — 호른 아프리카 지도가 흔들린다.`

---

## WRITE-AP-8: max_tokens 한도로 보고서 본문 중간 절단

**증상**: 보고서가 *분량이 정해진 듯* 항상 비슷한 길이에서 끝남. 사건이 복잡해
서 더 길게 작성돼야 할 상황에도 본문이 *중간에 끊긴 느낌*. JSON 파싱은 성공
하지만 마지막 섹션 / 모순 / 감시 신호 등이 누락되거나 짧음.

**최초 사례**: 20260503_142254 보고서 (v4.5.3 사용자 보고). "보고서가 내용을
검토 하다가 중간에 끊긴 느낌" — 사용자 인용. 자율주행 일정 비교라 다중
플레이어 + 시계열 + 시나리오 + 정책 환경까지 폭넓게 다뤄야 했으나 본문이
일정 길이에서 종료.

**원인**: `narrative_composer.MAX_TOKENS = 8192` 고정. fast/standard/deep 동일.
한국어는 영문보다 토큰 효율이 낮아 (글자당 1.5~2 토큰) deep 모드에서 5~7 섹션
+ 시나리오 + 모순 + 차트 데이터 + 지도 emit 까지 하면 8K 가 초과 — 응답이
*중간에 잘림*. Anthropic API 는 잘리면 `finish_reason='max_tokens'` 로 알려
주지만 코드는 그걸 안 보고 그대로 파싱 → 부분 보고서 출력.

**검증 체크리스트**:
- [ ] composer max_tokens 가 mode 별로 분기되어 있나? (fast/standard/deep)
- [ ] deep 모드는 *충분히 큰* 한도 (Opus 4.7 기준 32K 권장).
- [ ] API 응답의 `stop_reason` / `finish_reason` 검사 — `max_tokens` 면
  warning 로깅 (telemetry).
- [ ] 한국어 보고서 토큰 효율 계산 (영문 대비 1.5~2배) 가 prompt 가이드의
  섹션 수 / 길이 권장에 반영돼있나?

**Fix (v4.5.4)**:
- `narrative_composer.MAX_TOKENS_BY_MODE`: fast 12K / standard 20K / deep 32K.
- `_call_api(user_message, mode)` 에 mode 인자 추가 → mode 별 max_tokens 적용.
- 단일 8K 폐기 (legacy MAX_TOKENS 는 default fallback 으로만 32K 보존).

## WRITE-AP-9: 모순 섹션의 정적 메타-라벨 제목 (결론 회피 인상 + 단조로움)

**증상**: 모든 보고서의 모순 섹션 제목이 동일한 정적 문구 ("봉합하지 않은 충돌"
/ "모순" / "반대 관점"). 두 가지 해악 — (1) 제목이 *내용이 아니라 보고서의
인식론* 을 말해서 "이 보고서는 결론을 안 냈다" 로 읽힘 → 앞 본문을 다 읽은
독자가 시간낭비 느낌. (2) 매 보고서 동일 문구라 단조롭고 불편.

**최초 사례**: v5.5.0 까지 `freeform_essay.html` 의 고정 `<h2>봉합하지 않은 충돌</h2>`
(사용자 보고). 정작 결론인 `resolution` 은 "분석가의 정리 —" 라는 *각주형
border-left 박스* 로 뒤에 붙어, 독자가 판단이 아니라 의심으로 끝남.

**원인**: 제목·라벨이 템플릿에 하드코딩. composer 가 내용 기반 제목을 emit 할
경로 없음. resolution 이 시각적으로 "본문의 착지" 가 아니라 "추가 메모" 로 렌더.

**검증 체크리스트**:
- [ ] 모순 섹션 제목이 composer 동적 emit 인가? (`ComposedReport.contradictions_heading`)
- [ ] 정적 fallback 도 "봉합하지 않은 충돌" 류 메타-라벨이 아닌가? (reframe: '쟁점과 판단')
- [ ] `resolution` 이 단락의 *마지막 문장으로 흐르나*? (각주형 라벨/박스 아님)
- [ ] composer SYSTEM_PROMPT 가 "정적 메타-라벨 금지 + 판단으로 착지" 를 지시하나?

**Fix (v5.5.1)**:
- `ComposedReport.contradictions_heading: str = ""` 추가 — composer 가 판단형 제목
  emit (예: '정전이냐 잠복이냐'). 비면 템플릿 fallback '쟁점과 판단'.
- `freeform_essay.html` — 정적 `<h2>봉합하지 않은 충돌</h2>` 폐기. 서술형 prose 로
  전환: side_a → '그러나' (accent) → side_b → resolution (fg-1 bold, 단락 착지).
  각주형 "근거 충돌:" / "분석가의 정리 —" 라벨 + border-left 박스 제거.
- composer SYSTEM_PROMPT — contradictions_heading 동적 작성 + resolution 결론적
  문장 지시, 정적 메타-라벨 금지.

---

## WRITE-AP-10: 전문 용어·영어 표현을 평이화도 주석도 없이 본문에 방치

**증상**: composer 가 `rate card` / `rate limit premium` 같은 영어 표현·업계 은어·
전문 용어를 *평이한 우리말로 바꾸지도 않고, 문단 하단 주석으로 풀지도 않고* 본문에
그대로 박음. 일반 독자가 막힘. WRITE-AP-2 (첫 등장 한 줄 풀이) 의 강화·확장 — 일반
독자 우선이 본 시스템의 *최우선 가치* (REPORT_STYLE_GUIDE §0.1) 임을 명문화하면서
신설.

**최초 사례**: analysis_20260525_233612 보고서 (사용자 보고). API 요금 구조를
다루는 본문에 `rate card` / `rate limit premium` 이 풀이 없이 그대로 노출 — "일반인이
이해할 수 있는 평이한 용어 + 전문용어 문단 하단 주석" 을 최우선 가치로 요청.

**원인**: 전문 용어 처리가 "첫 등장 시 한 줄 괄호 풀이" (WRITE-AP-2) 한 단계뿐이었고,
*평이화* 와 *문단 하단 주석* 경로가 SYSTEM_PROMPT·데이터 모델·템플릿에 없었음.
composer 가 영어 표현을 "정확한 용어" 라는 이유로 그대로 두는 편향.

**검증 체크리스트**:
- [ ] composer SYSTEM_PROMPT 최상단에 "★ 최우선 원칙 — 일반 독자 우선" 블록이 있고,
  (1) 평이화 (2) 문단 하단 주석 2단계를 다른 지시보다 *우선* 으로 명시하는가?
- [ ] `ComposedSection.footnotes` 필드가 있고, composer 가 불가피한 용어를
  `{term, explanation}` 으로 emit 하는가?
- [ ] `freeform_essay.html` 이 `sec.footnotes` 를 그 섹션 본문 *하단* 에
  "용어 풀이" 블록으로 렌더하는가? (`.freeform-footnotes`)
- [ ] REPORT_STYLE_GUIDE §2.1 어휘표에 영어·은어 항목 (rate card / rate limit
  premium / 익스포저 / 가이던스 / 헤지 등) 이 있는가?
- [ ] "평이화 가능한데 주석으로 떠넘기기" 가 아닌가? (먼저 (1), 못 바꿀 때만 (2))

**Fix (v5.5.5)**:
- `src/agents/narrative_composer.py:SYSTEM_PROMPT` — 본문 최상단에 "★ 최우선 원칙"
  블록 + JSON 스키마에 `footnotes` 추가.
- `src/models.py:ComposedSection.footnotes` — `list[{term, explanation}]`,
  None/비정형 항목 정규화 validator.
- `src/templates/archetypes/freeform_essay.html` — prose 직후 `.freeform-footnotes`
  블록 (term + explanation) 렌더 + CSS.
- `docs/REPORT_STYLE_GUIDE.md` §0.1 / §2.1 / §2.2 — 최우선 가치 명문화 + 어휘표
  확장 + 3단 사다리.

**재발 사례**: analysis_20260530_163305 보고서 (tinygrad 소프트웨어 다룬 본문).
`1급 시민` (first-class citizen, 프로그래밍 은어) 이 평이화도 주석도 없이 본문에 노출
— "여러 칩 위에서 도는 코드를 한 프레임워크가 1급 시민으로 다룰 수 있다". 일반
독자는 '시민' 의 함의를 모름. `1급 시민 → 곁다리가 아니라 정식 지원 대상으로
동등하게 다룸` 으로 어휘표(§2.1) + SYSTEM_PROMPT 평이화 예시에 추가.

---

## WRITE-AP-11: 발행일과 사건일이 다른데 본문에 시점 앵커가 없음 (v5.6.4 신설)

**증상**: 보고서 발행 시점(예: 5/29)이 분석 대상 사건 발생일(예: 5/26)과 다른데
본문이 그 시간 거리를 명시 안 함 → 첫 단락부터 "5월 26일 코스피는 8,047 신고가"
처럼 사건일을 단독으로 박아 독자에게 "오늘 보고서인데 왜 갑자기 며칠 전 얘기?"
인지부조화. 더 미묘한 형태 — "같은 시각, 원/달러 환율은 7거래일 연속 1,500원
위에 머물렀다" 처럼 *지속 상태* 를 사건일 시점으로 묶어버려, 사실은 발행일 현재
누적된 상태인데도 5/26 에 멈춰 있는 듯이 들림. 데일리 브리핑(매일 06:00 KST)
에서 빈발 — 분석 윈도우는 어제~오늘이라도 *원인 사건* 이 며칠 전이면 발생.

**원인**: composer SYSTEM_PROMPT 에 "오늘=발행일" anchor 가 없고, payload 에도
publication_date 가 없어 composer 가 today 를 모름. `context.date` 는 사건일이
박혀와 본문 시제가 그날에 고정됨. 데일리 브리핑 prompt 는 "오늘"을 ContextAnalyst
에게 줬지만 composer 단까지 전달이 안 됐다.

**Fix (v5.6.4)**:

- `_build_unified_payload` 가 `publication_date` (`datetime.now().strftime("%Y-%m-%d")`)
  를 payload 에 주입. composer 가 today 와 event.date 를 직접 비교 가능.
- SYSTEM_PROMPT 에 **=== 시점 앵커링 ===** 섹션 신설:
  · 첫 단락에 시간 거리를 발행일 시점 표현으로 명시 ('지난 26일' / '사흘 전').
  · '같은 시각' / '같은 날' 표현 주의 — 시점을 사건일에 고정시킴.
  · 지속 상태(누적/연속)는 *발행일 현재* 기준 ('5/29 현재 7거래일째 1500원 위').
  · 결론·시사점도 발행일 시점의 판단.
  · publication_date == event.date 면 적용 불필요.
  · broadcast_summary 에도 동일 적용.

**적용 SSOT**: `src/agents/narrative_composer.py` SYSTEM_PROMPT `=== 시점 앵커링 ===`
블록 + `_build_unified_payload` 의 publication_date 주입.

**후속 Fix (v5.7.0) — 더 깊은 원인: timezone 누락**:

v5.6.4 의 시점 앵커링은 "발행일 ≠ 사건일" 을 *표현* 으로 다뤘지만, 더 근본적인
회귀가 따로 있었다 — **발행일 자체가 하루 어긋남**. 5/31 06:00 KST 에 트리거된
일일 브리핑이 제목·본문 전체에 "5/30" 을 박았다. 안내·스코프 문구(스케줄러가
`ZoneInfo("Asia/Seoul")` 로 생성)는 5/31 로 맞는데, 보고서 내용만 5/30 이라 더
혼란스러웠다.

원인은 봇이 도는 VM/컨테이너가 **UTC** 인데 아래 4곳이 timezone 없는
`datetime.now()` 를 썼던 것. 06:00 KST = 전날 21:00 UTC 이므로 naive `now()` 는
*전날* 을 돌려준다.

- `context_analyst.py` — `current_date` (composer 가 보는 '오늘' 의 진짜 출처)
- `narrative_composer.py` — `publication_date` (주석에 "VM=KST 가정" 이라 적혀
  있었으나 그 가정이 깨진 상태)
- `bundle_builder.py` — `fetched_at` fallback / `generated_at` (계약서는
  `+09:00` 요구인데 `.astimezone()` 가 UTC offset 을 냄)
- `models.py` — `analysis_timestamp` default

**Fix**: `src/timeutil.py` 신설 (`KST` / `now_kst()` / `today_kst()` SSOT —
stdlib 고정 +09:00, tzdata 미설치 환경도 안전). 위 4곳 + `report_synthesizer.py`
의 중복 `KST` 정의를 모두 이 모듈로 통합. 사용자 노출 날짜는 *항상* KST 기준.
naive `datetime.now()` 로 사용자 노출 날짜 생성 금지 (이 회귀의 SSOT 차단점).

---

## WRITE-AP-12: AI 가 인지되는 기호 (마크다운 강조 / em·en dash) 사용 (v5.6.7 신설)

**증상**: 보고서 headline·deck·본문·캡션·`broadcast_summary` 에 `**굵게**` /
`*기울임*` 같은 마크다운 강조나 긴 줄표(em dash `—`)·en dash(`–`)가 노출. 사람은
잘 안 쓰는 기호라 "AI 가 썼다" 는 인상을 즉시 준다. 사용자 최우선 규칙으로 금지.

**원인**: LLM 이 영어권 편집 관습(em dash 선호) + 마크다운 강조 습관을 한국어
출력에 그대로 가져옴. WRITE-AP-1(마크다운 강조)의 확장 — dash 까지 포함하고,
프롬프트 지시만으론 100% 차단 안 되는 점을 결정적 후처리로 보강.

**Fix (v5.6.7)** — 2중 방어:

1. **프롬프트**: `narrative_composer.py:SYSTEM_PROMPT` 에 "★ 기호 금지 (최우선,
   WRITE-AP-12)" 블록 추가 — `*`/`**`/백틱/em·en dash 금지, 부연은 쉼표·마침표,
   숫자 범위는 `~`, 제목 부제 구분은 쉼표·줄바꿈.
2. **결정적 후처리**: `NarrativeComposer._sanitize_symbols` 가 파싱된
   ComposedReport 의 *모든* 사용자 노출 텍스트(headline/deck/heading/prose/
   pull_quote/lede/캡션/chart 라벨·note/watch_signals/contradictions/
   timeline_flow/map 라벨/broadcast_summary)에서 강조 기호 제거 + dash 자연
   치환(공백 둘러싼 삽입구 → 쉼표, 숫자 사이 → `~`, 단어 직접 인접 → 공백).
   URL(source_url/image_url)·좌표·bool 은 보존. orchestrator 가 최종
   `_sanitize_symbols` 를 한 번 더 호출 — minimal fallback / hook 추가 텍스트 /
   context 기반 합성본까지 *모든 경로* 보장. broadcast 폴백의 `_strip_inline_md`
   도 동일 dash 규칙으로 확장.

**회귀 테스트**: `_clean_text` 13케이스 + `_sanitize_symbols` e2e(중첩 구조 +
URL/좌표 보존 23검사) 오프라인 통과. 회귀 발견 시 케이스 추가.

---

## WRITE-AP-13: LLM 이 SYSTEM_PROMPT 의 JSON 예시 들여쓰기를 따라 응답 시작을 누락 (v5.6.8 신설)

**증상**: composer 응답이 ``` ```json``` 직후 ``{`` 가 아니라 ``      "prose": "..."`` /
``      "side_a": "..."`` 같은 sections 또는 contradictions 객체의 *중간 줄* 부터
시작. 정상 종료(timeout 아님)지만 JSON 시작(``{``, headline, deck, sections 배열
시작)이 통째로 누락돼 파싱 실패 → 두 번 재시도 모두 같은 회귀 → 0% minimal fallback.

**원인**: Claude Opus 4.7 이 SYSTEM_PROMPT 안의 JSON 예시(들여쓰기 6 spaces 의
sections 객체 필드들)를 보고, 자기 응답을 **예시의 깊은 줄부터** 이어서 시작.
일종의 prompt cache / few-shot 따라하기 회귀. 큰 prompt(32K+ chars)에서 빈발.

**Fix (v5.6.8)** — 2중 방어:

1. **프롬프트**: `narrative_composer.py:SYSTEM_PROMPT` 의 ``=== JSON 응답 형식 ===``
   섹션 *직후* (예시 직전) 에 ★★★ 강조 박스 추가 — "응답은 반드시 ``{`` 한 글자로
   시작. 코드펜스 ``` ```json``` 직후 첫 비공백 글자가 ``{`` 가 아니면 응답 *전부
   무효*. 아래 예시의 중간 줄(``      "prose":`` / ``      "side_a":`` / ``      "lede":``)
   부터 시작 금지. 응답이 폐기되고 minimal fallback 으로 격하됨". LLM 이 깊은 줄부터
   출력하지 않도록 명시적 instruction.
2. **결정적 후처리**: `NarrativeComposer._recover_head_loss` 가 정상 파싱 + 절단 복구
   모두 실패한 뒤 호출 — body 가 ``{`` 가 아니라 ``"key":`` 패턴으로 시작하면 ``{...}``
   로 wrap 해 부분 객체 파싱 시도. ``prose`` 가 있으면 ``heading``/``kicker``/``lede``/
   ``pull_quote`` 와 함께 1-섹션 ComposedReport 재조립 (confidence 0.3, summary
   "응답 시작 부분이 누락돼 본문 일부만 복구함"). headline 은 빈 문자열 (orchestrator
   가 hook 으로 context.event_name 으로 덮어쓸 수 있음). 0% fallback 대신 일부 살림.

**적용 SSOT**: `src/agents/narrative_composer.py:SYSTEM_PROMPT` ``=== JSON 응답 형식
===`` 직후 강조 박스 + `NarrativeComposer._recover_head_loss` + `_parse_response` 의
호출부.

---

## WRITE-AP-14: 미래 사건 카운트다운(D-N)을 발행일이 아닌 출처 작성일 기준으로 표기 (v5.8.3 신설)

**증상**: 6/1 발행 보고서가 6/3 지방선거를 "사흘 앞으로 다가온 6·3 지방선거" /
"사흘 뒤 지방선거" 로 표기. 6/1 → 6/3 은 **이틀 뒤 / 모레**인데 사흘로 셌다.
"사흘"은 5/31 기준 표현 — 즉 *출처 기사(5/31 작성)의 카운트다운을 그대로 베낀*
것. WRITE-AP-11 의 거울상: AP-11 은 *과거* 사건의 시간 거리("사흘 전") 누락,
AP-14 는 *미래* 사건의 카운트다운("사흘 앞")을 잘못된 기준으로 고정.

**원인**: v5.6.4 의 시점 앵커링 블록이 *과거* 방향("지난 26일" / "사흘 전")만
다루고, *미래* 방향 카운트다운(D-N, "사흘 앞" / "내일" / "모레")은 언급이
없었다. composer 는 웹 검색으로 가져온 출처 기사의 상대 표현을 그대로 옮겼고,
그 기사들은 발행일보다 하루 이상 전에 쓰였다. publication_date 는 payload 에
있었지만(v5.6.4) "미래 카운트다운도 다시 계산하라"는 지시가 없었다. 선거·정상
회담·만기일 등 *예정된 미래 사건* 을 다루는 일일 브리핑에서 빈발.

**Fix (v5.8.3)**: composer SYSTEM_PROMPT `=== 시점 앵커링 ===` 블록에 미래
카운트다운 규칙 추가:
- D-N·'사흘 앞'·'이틀 뒤'·'내일'·'모레' 같은 상대 표현은 *publication_date 와
  사건일의 실제 차이* 로 직접 셈한다. 출처 문구를 그대로 옮기지 말 것.
- 출처 기사는 기사 작성일 기준 카운트다운을 쓴다는 점 명시 (베끼기 차단).
- 확실치 않으면 상대 표현 대신 'M월 D일' 절대 날짜만 (틀린 카운트다운보다 나음).

**적용 SSOT**: `src/agents/narrative_composer.py:SYSTEM_PROMPT` `=== 시점 앵커링 ===`
블록의 미래 카운트다운 항목. WRITE-AP-11 과 같은 블록 — 과거/미래 양방향을 함께 다룸.

**발행본 핫픽스**: 이미 나간 보고서는 `scripts/patch_report.py <id> --replace`
로 "사흘 앞=이틀 앞" / "사흘 뒤=이틀 뒤" 등 실제 차이에 맞춰 치환 (D-N 은
publication_date 와 사건일을 직접 계산해 보정). 단, 보고서마다 사건일·발행일이
다르므로 일괄 매핑은 위험 — `--dry-run` 으로 매치 문맥 확인 후 건별 보정.

**회귀 테스트**: 사용자 회귀 case 6/6 통과 (실제 raw head:
``      "prose": "GPU 부족이 사이클의 첫 병목..."`` 165자 prose 살림 + side_a/side_b
contradictions 부분은 정상 None / 정상 응답 / 빈 응답 / heading 포함 케이스).

---

## 체크리스트 — composer prompt / persona 가이드 변경 시

### prose 형식
- [ ] 마크다운 강조 금지 명시 (WRITE-AP-1)
- [ ] 진부한 연결어 금지 명시 (WRITE-AP-4)
- [ ] 추정은 hedging 표현 (WRITE-AP-5)
- [ ] 서수는 "첫"/"처음으로", "N번" 금지 (WRITE-AP-7)

### 어휘
- [ ] **(최우선) 전문 용어·영어 표현·은어를 평이한 우리말로 바꿈 (WRITE-AP-10, §0.1)**
- [ ] **(최우선) 못 바꾼 핵심 용어는 footnotes 로 문단 하단 주석 (WRITE-AP-10, §2.2)**
- [ ] 전문 용어 첫 등장 시 한 줄 풀이 (WRITE-AP-2)
- [ ] 영어 약어 풀어쓰기

### 섹션 배치
- [ ] 사건 성격별 섹션 우선순위 가이드 (WRITE-AP-3)
- [ ] 모순/반대 가설은 후행 섹션

### 무결성
- [ ] 모순 봉합 금지 명시 (WRITE-AP-6)
- [ ] 출처 추적성 강제

### 템플릿 fallback
- [ ] `_format_structured_text` 가 마크다운 강조 raw 노출 차단 (WRITE-AP-1 백업)

---

## 회귀 발견 시 — 표준 프로토콜

CHART_RENDERING_ANTIPATTERNS.md §회귀 발견 시와 동일:
1. 본 문서의 패턴 중 어디에 해당하는지 분류 (또는 새 WRITE-AP-N 추가)
2. composer prompt / persona 가이드 / 템플릿 fallback 중 어디서 발생하는지 식별
3. 시스템적 회귀 (모든 보고서 영향) → composer prompt 또는 템플릿 수정. 새 패턴이면 본 문서에 항목 추가
4. 이 보고서만 영향 → `scripts/patch_report.py` 로 데이터 수정 (LLM 0)
5. fix 후 DEVLOG.md 에 commit 사유 + 본 문서 항목 reference

---

## 본 문서 갱신 규칙

- **append-only**: 발견된 회귀는 새 항목으로 추가. 기존 항목 수정 금지.
- **회귀 ID 명시**: WRITE-AP-N 으로 일관 부여. commit 메시지에서 reference (예: "fix WRITE-AP-1: markdown emphasis raw exposure").
- **`last_synced_with` 갱신**: 항목 추가 시 헤더의 version 갱신.
- **chart 와 분리 유지**: 시각화 코드 회귀 → CHART-AP-N. 본문 작성 회귀 → WRITE-AP-N.
