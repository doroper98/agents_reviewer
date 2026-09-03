---
tier: 3
last_synced_with: v8.5.15
ssot_for:
  - "외부 참고 자료 원본 보관 (차트 디자인 레퍼런스)"
depends_on:
  - "docs/CHART_REDESIGN_V8_6_PLAN.md"
last_review: 2026-09-03
---

# docs/reference — 외부 참고 자료 원본

| 파일 | 출처 | 보관 사유 | 라이선스·주의 |
|------|------|-----------|---------------|
| `chart_practice_kit_aisyncclub_2026-09-02.pdf` (64쪽, 4.5MB) | AI싱크클럽 (@aisyncclub) "차트 실전 키트 — 차트 64종" 릴스 자료, 2026-09-02. 내용은 Claude Code 스킬 `lieflat-charts` (github.com/larashero3-dotcom/lieflat-charts) 의 카탈로그 64장 실제 출력 | 사용자 지시 (2026-09-03) — 차트 유형·표현 방식 흡수 작업의 시각 기준. 계획 SSOT: [CHART_REDESIGN_V8_6_PLAN.md](../CHART_REDESIGN_V8_6_PLAN.md) §1 | 스킬 코드는 **PolyForm Noncommercial 1.0.0** (MIT 아님). 본 repo 는 그 코드·템플릿·토큰 파일을 *복제하지 않으며* 시각 문법만 charts.js 로 재구현한다. PDF 자체는 제3자 저작물 — **내부 참고용**. 저장소가 public 이면 재배포에 해당하므로 필요 시 삭제·private 전환은 사용자 판단 |

규칙: 이 폴더의 파일을 코드에서 import·fetch 하지 않는다. 갤러리·목업(`samples/`)에
이 PDF 의 이미지를 복사해 넣지 않는다 (비교는 우리 렌더 전·후로만).
