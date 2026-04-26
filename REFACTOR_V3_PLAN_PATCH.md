# Patch — REFACTOR_V3_PLAN.md에 Step 0 참조 추가

> **Purpose:** 기존 `REFACTOR_V3_PLAN.md`에 `DOCS_GOVERNANCE_V3.md`(Step 0)와의 의존 관계를 명시한다.
> **How to apply:** 아래 두 곳에 추가/수정한다.

---

## Patch 1 — Section 0 상단에 추가

`REFACTOR_V3_PLAN.md`의 `## 0. How to Use This Document` 섹션 *맨 앞*에 다음을 추가한다.

```markdown
> **Prerequisite:** 본 리팩토링을 시작하기 전에 `DOCS_GOVERNANCE_V3.md`의 Step 0를 먼저 완료해야 한다. 거버넌스가 적용되지 않은 상태에서 V3 리팩토링을 진행하면 신규 파일·신규 카탈로그가 추가될 때마다 문서 파편이 늘어난다.
```

---

## Patch 2 — Section 5 시작 부분 수정

`REFACTOR_V3_PLAN.md`의 `## 5. Migration Plan — 5 Steps` 시작 부분을 다음으로 교체한다.

```markdown
## 5. Migration Plan — Step 0 + 5 Steps

### Step 0: 문서 거버넌스 적용 (선결 조건)

`DOCS_GOVERNANCE_V3.md` 전체를 따른다. 본 문서는 코드 리팩토링 명세이지 거버넌스 명세가 아니다.

**Step 0 완료 기준 (요약):**
- 3-Tier 계층 적용 (Tier 1: GOAL/CLAUDE/STYLEGUIDE, Tier 2: ARCHITECTURE/DATA_MODELS/CATALOGS, Tier 3: DEVLOG/WORKFLOWS/CHANGELOG)
- 모든 문서에 거버넌스 YAML 헤더
- SSOT 매트릭스 적용 (사실 중복 제거)
- `docs_canonical/` → `docs/` 이름 변경
- `overall_structure.md`, 루트의 `prototype_*.html` 정리
- CHANGELOG.md 신설
- README.md 슬림화 (60줄 이내)
- CLAUDE.md에 Change Propagation 매트릭스 추가

**커밋:** `v2.4.1: 문서 거버넌스 V3 적용`

Step 0 완료 후 Step 1로 진행한다.

---

### Step 1: AnalysisStrategy 정식 모델 (1주, 무파괴)

[기존 내용 그대로]
```

---

## Patch 3 — Section 6 (File Change Matrix) 보강

`## 6. File Change Matrix` 표에 다음 행들을 *맨 위*에 추가한다.

| 파일/디렉토리 | 작업 | Step |
|---------------|------|------|
| `docs/` | `docs_canonical/`에서 이름 변경 | 0 |
| `overall_structure.md` | `docs/ARCHITECTURE.md`로 흡수 후 삭제 | 0 |
| `prototype_*.html` | `docs/references/`로 이동 | 0 |
| `CHANGELOG.md` | 신규 | 0 |
| `docs/CATALOGS.md` | 신규 (V3에서 archetype/lens/block 추가) | 0, 2, 3, 5 |
| `docs/DATA_MODELS.md` | 신규 (V3에서 신규 모델 추가) | 0, 4, 5 |
| 모든 *.md 헤더 | 거버넌스 YAML 헤더 추가 | 0 |

---

## Patch 4 — Section 9 Final Checklist 보강

`## 9. Final Checklist Before v3.0.0 Release`에 다음 항목 추가:

```markdown
- [ ] 모든 문서의 `last_synced_with: v3.0.0`으로 갱신
- [ ] CHANGELOG.md v3.0.0 항목 작성 완료
- [ ] docs/CATALOGS.md에 신규 archetype·lens·block 모두 등록
- [ ] docs/DATA_MODELS.md에 신규 Pydantic 모델 도식 갱신
- [ ] SSOT 위반 검사 통과 (`grep` 자동 검사)
- [ ] 분기 검토 일정 등록 (3개월 후 재검토)
```

---

## Patch 5 — Anti-Patterns Section 8 보강

`## 8. Critical Anti-Patterns`에 다음 항목 추가:

```markdown
13. ❌ **Step 0(거버넌스) 건너뛰고 Step 1부터 시작.** 거버넌스 없이는 V3 종료 시점에 문서 파편이 더 심해진다.
14. ❌ **신규 archetype/lens/block을 코드에 추가하면서 docs/CATALOGS.md 갱신 누락.**
15. ❌ **신규 Pydantic 모델 추가하면서 docs/DATA_MODELS.md 도식 갱신 누락.**
16. ❌ **DOCS_GOVERNANCE_V3.md의 SSOT 규칙을 우회하여 사실을 두 곳에 작성.**
```

---

**End of Patch**

이 패치를 적용하면 `REFACTOR_V3_PLAN.md`와 `DOCS_GOVERNANCE_V3.md`가 짝이 되어 작동한다.
