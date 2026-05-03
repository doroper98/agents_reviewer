---
tier: 2
last_synced_with: v4.4.4
ssot_for:
  - "보고서 본문 작성 anti-patterns (composer prompt 회귀 방지)"
depends_on:
  - "src/agents/narrative_composer.py:SYSTEM_PROMPT"
  - "src/agents/context_analyst.py:SYSTEM_PROMPT (recommended_persona 가이드)"
  - "src/agents/report_synthesizer.py:_format_structured_text (fallback 변환)"
  - "docs/CHART_RENDERING_ANTIPATTERNS.md (코드/렌더링 anti-pattern 별도)"
last_review: 2026-05-02
---

# Report Writing Anti-Patterns

> composer SYSTEM_PROMPT / context_analyst persona 가이드 / 보고서 본문 출력에서
> 발견된 *글쓰기 회귀* 모음. CHART_RENDERING_ANTIPATTERNS.md 가 *시각화 코드*
> 회귀 (charts.js / maps.js) SSOT 라면, 본 문서는 *언어/구조* 회귀 SSOT.
>
> composer prompt 변경 / persona 가이드 변경 / 새 보고서 검증 시 본 문서의
> 체크리스트 위반 여부 *반드시* 점검. 회귀 1건 발견 시 본 문서에 항목 추가
> (append-only) — 같은 실수 반복 방지.

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

## 체크리스트 — composer prompt / persona 가이드 변경 시

### prose 형식
- [ ] 마크다운 강조 금지 명시 (WRITE-AP-1)
- [ ] 진부한 연결어 금지 명시 (WRITE-AP-4)
- [ ] 추정은 hedging 표현 (WRITE-AP-5)
- [ ] 서수는 "첫"/"처음으로", "N번" 금지 (WRITE-AP-7)

### 어휘
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
