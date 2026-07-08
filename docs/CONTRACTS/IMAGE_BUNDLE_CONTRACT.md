---
tier: 2
status: active (v8.3.5 producer emit 배선 완료 — consumer v0.42.0)
contract_version: 1
last_synced_with: v8.3.5
ssot_for:
  - "report_bundle 보도 사진 계약 v1 (images[] + sections[].image_refs)"
  - "BundleImage 필드 / 타입 / 의미 / 권리 상태"
  - "producer 의 사진 emit 작성 규칙 (rights_status 판단 근거)"
depends_on:
  - "docs/CONTRACTS/report_bundle_v1.md (상위 번들 계약 — schema_version 공유)"
  - "src/models.py:BundleImage / ReportBundle.images / BundleSection.image_refs"
  - "src/handoff/bundle_builder.py:_build_images"
  - "src/models.py:ComposedReport.hero_image / ComposedSection.images"
last_review: 2026-07-08
---

# IMAGE_BUNDLE_CONTRACT v1 (agents_reviewer → osint_generator)

> **STATUS: ACTIVE** — consumer(osint_generator) 가 v0.42.0 에 photo 씬(풀블리드 +
> Ken Burns + 캡션/크레딧) 소비를 구현. producer(agents_reviewer) 가 v8.3.5 에
> emit 을 배선. `report_bundle_v1.md` 의 하위 계약 — 전부 **additive**,
> `schema_version` 은 **1 유지**. 이 문서가 보도 사진 계약의 SSOT (양쪽 repo 동기화).

report_bundle 에 보도 사진을 실어 osint_generator 의 영상 파이프라인이 photo 씬으로
소비하게 하는 계약. 상위 번들 계약(참조 무결성 §8, 거버넌스 §7 등)은
[report_bundle_v1.md](report_bundle_v1.md) 를 따른다.

## 1. top-level `images[]` (신설)

```jsonc
"images": [
  {
    "image_id": "img-1",                    // 필수, 번들 내 유일 (img-N 권장)
    "url": "https://.../photo.jpg",         // 필수, 이미지 파일 직링크 (페이지 URL 금지)
    "caption": "울산 AI 데이터센터 예정 부지",  // 필수, ≤60자. 화면 캡션 겸 대체텍스트
    "credit": "SKT 제공",                    // 필수, 출처 표기 (영상 우하단 크레딧)
    "rights_status": "cleared",             // 필수: cleared | needs_review | blocked
    "license": "보도자료",                    // 권장: 재사용 근거
    "source_id": "src-1",                   // 권장: sources[] 역추적 연결
    "focus": "center"                       // 선택: Ken Burns 초점
                                            //   center|top|bottom|left|right
  }
]
```

코드 SSOT: `src/models.py:BundleImage`. `caption` 이 60자를 넘으면 producer 가 말줄임
(`bundle_builder._cap_caption`). `focus` 미지정 시 `center`.

## 2. `sections[].image_refs` (기존 필드 활용)

- 그 섹션 구간에 보여줄 `image_id` 목록. 섹션당 0~2개 권장.
- `image_refs` 의 모든 id 는 `images[].image_id` 로 반드시 resolve —
  상위 계약 §8 참조 무결성 가드(`ReportBundle._validate_refs_and_ids`)가 emit 시
  강제(미해결 참조 → ValidationError). consumer 수신 검증도 **fail-closed**
  (미해결 참조는 번들 거부).
- 영상은 **섹션당 첫 번째 `cleared` 이미지 1장만** 사용한다.

## 3. 작성 규칙 (producer 의무)

1. **`rights_status` 는 근거와 함께 판단**:
   - `cleared`      = 재사용 근거 확인 — 보도자료 / 회사·정부 공식 배포 / 공공누리 /
                      CC, **또는 본 시스템의 출처표기 갈음(아래 §3.1-a)**
   - `needs_review` = 불확실 (영상은 스킵하고 기록만 남김)
   - `blocked`      = 무단 전재 위험 (emit 은 해도 되나 영상 사용 안 됨)

   consumer 는 `cleared` 외에는 다운로드조차 하지 않고, 전 건을
   `photos_manifest.json` 에 사유와 함께 기록한다(권리 추적 의무).

   > **§3.1-a 출처표기 갈음 (개정 — 사용자 결정 2026-07-08, 양쪽 repo 동기화).**
   > 원 초안은 `cleared` 를 "재사용 라이선스 확인" 으로 엄격히 정의했으나, 본
   > 시스템(agents_reviewer↔osint_generator)은 **봇 본인 사용 목적**이라 저작권을
   > *출처표기(credit)* 로 갈음한다 (agents_reviewer CLAUDE.md 'Report Images'
   > 기존 방침). 따라서 이 계약에서 `cleared` 의 근거를 다음으로 **확장**한다:
   >   - 정부 공식 배포·보도자료 와이어 도메인 → `cleared` (`license="공식 배포"`)
   >   - **credit(출처표기)이 채워진 사진 → `cleared`** (`license="출처표기"`)
   >   - credit 도 근거 도메인도 없는 사진 → `needs_review`
   >
   > ⚠️ 이때 `cleared` 는 "검증된 재사용 라이선스" 가 아니라 **"출처표기로 갈음한
   > 자체 사용"** 을 뜻한다. consumer(osint_generator)는 이 의미로 `cleared` 를
   > 소비한다 (여전히 우하단 credit 표기 필수). 제3자 배포·상업 판매용이 아니라
   > 자체 브리핑 영상 한정. 인물 초상권 우려 등은 아래 규칙 5로 `blocked` 처리.
   >
   > producer SSOT: `bundle_builder._image_rights` / `_CLEARED_HOST_SUFFIXES`.

2. **AI 생성 이미지 금지.** 실사 보도 사진·공식 배포 이미지·문서 스캔만.
3. `url` 은 원본 직링크(빌드 시점 다운로드). 서명 만료 URL(S3 presigned) 지양.
4. `caption` 은 사실 서술만. 미검증 장면이면 caption 에 `<미검증>` 표기.
5. 인물은 공인의 공적 활동 장면만. 초상권 우려 시 `blocked`.
6. 보고서당 2~6장 권장(핵심 섹션 위주 — 발단/현장/인물 언급 지점).

## 4. producer 배선 (v8.3.5)

- 입력: `ComposedReport.hero_image`(보고서 대표 1장) + `ComposedSection.images`
  (섹션당 0~2장) — 둘 다 ContextAnalyst 가 수집한 og:image 후보 중 composer 가
  본문 흐름에 맞게 고른 것. `{image_url, caption, credit, source_url?}`.
- 매핑(`bundle_builder._build_images`):
  - `image_url` → `url`, `caption` → `caption`(≤60 말줄임), `credit` → `credit`.
  - `source_url` → `sources[]` 매칭으로 `source_id` 역추적.
  - **dedup by url** — hero 와 섹션 사진이 같은 url 이면 한 `image_id` 재사용.
  - **hero → 첫 섹션 오프닝** — hero 의 `image_id` 를 `sections[0].image_refs`
    맨 앞에 삽입(발단 장면). 섹션 없으면 `images[]` 에만 존재(참조는 없음, 유효).
- `rights_status`/`license` — `_image_rights(credit, source_url)` (§3.1-a): 공식
  배포 도메인 → `cleared`/`"공식 배포"`, credit 있음 → `cleared`/`"출처표기"`,
  둘 다 없음 → `needs_review`/`""`.
- `focus` 는 현재 항상 `center`(composer 가 초점을 emit 하지 않음).

## 5. 하위 호환

- `images` 부재 시 영상은 기존 동작 그대로. 기존 번들(`image_refs` 빈 배열) 전부 유효.
- producer 는 사진이 없으면 `images: []` + 각 섹션 `image_refs: []` (기존 emit 과
  byte-equal). `schema_version` 불변(1). 회귀: `tests/test_report_bundle.py`
  (`test_images_emit_refs_dedup_rights_caption` / `test_images_absent_backward_compat`
  / `test_image_ref_integrity_guard`).

## 6. 변경 거버넌스

상위 계약 [report_bundle_v1.md §7](report_bundle_v1.md) 을 따른다 —
additive(필드 추가/nullable)= `schema_version` 무증분, breaking= 증분 + 양측 동시
반영. 본 계약의 필드·규칙 변경 시 이 문서 + `src/models.py:BundleImage` +
`bundle_builder._build_images` + 예시(`report_bundle_v1.example.json`) + 회귀
테스트를 **함께** 갱신하고, osint_generator repo 의 동기화 사본과 정합을 맞춘다.
