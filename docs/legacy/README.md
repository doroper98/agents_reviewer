---
tier: 3
status: legacy_index
last_synced_with: v4.5.7
ssot_for:
  - "Legacy 문서 디렉토리의 인덱스 + 거버넌스 정책"
depends_on:
  - "REFACTOR_V5_PLAN.md (Phase 0 SSOT Repair)"
last_review: 2026-05-05
---

# `docs/legacy/` — Legacy SSOT Archive

본 디렉토리는 **v3 시대의 SSOT 문서** 를 보관합니다. v4.0.0 이후 호출되지 않는 7-agent / 11-lens / 11-archetype / 5-gate 파이프라인의 설계·정책 문서들이 *역사적 참조용* 으로 이전되어 있습니다.

[REFACTOR_V5_PLAN.md](../../REFACTOR_V5_PLAN.md) §2.3 (다) 의 지시에 따라 [Phase 0 (Baseline + SSOT Repair)](../../REFACTOR_V5_PLAN.md) 단계에서 신설되었습니다. 목표는 *현재 SSOT 와 historical SSOT 를 명확히 분리* 하여, 코드와 문서의 baseline 일치 (v4.5.7) 을 회복하는 것입니다.

## 1. 이전된 문서 카탈로그

| 문서 | 마지막 활성 버전 | 이전 사유 |
|------|------------------|-----------|
| [REFACTOR_V3_PLAN.md](REFACTOR_V3_PLAN.md) | v3.5.0 | v3 의 7-agent / 11-lens / 11-archetype / 5-gate 리팩토링 마스터 플랜. v4.0.0 부터 흐름 비활성. |

> 다른 v3 시대 문서들 (`docs/TESTING.md` 의 5-gate quality_gates 등) 은 *legacy 마킹* 만 추가되고 본 디렉토리로 이전하지 않았습니다. 이는 단위 테스트 자체는 여전히 실행 가능하고 (호출되지 않는 모듈의 동작 검증) v5 Phase 0B 에서 Golden Prompt 회귀 하네스가 신설되면 그 시점에 함께 정리될 예정이기 때문입니다. [DOCS_GOVERNANCE_V3.md](../../DOCS_GOVERNANCE_V3.md) 는 이름은 V3 brand 이지만 *현재도 거버넌스 SSOT 로 사용* 중이라 이전 대상이 아닙니다 ([CLAUDE.md](../../CLAUDE.md) 의 depends_on 에 명시).

## 2. Redirect Stub 정책

깊은 링크 호환을 위해 root 에 redirect stub 을 남겨둔 문서가 있습니다.

- [`/REFACTOR_V3_PLAN.md`](../../REFACTOR_V3_PLAN.md) — root 에 stub. 실제 본문은 [REFACTOR_V3_PLAN.md](REFACTOR_V3_PLAN.md).

DEVLOG.md 의 append-only 항목과 `src/lenses/*.py` / `src/models.py` 의 코드 주석에서 옛 경로로 참조하는 링크가 깨지지 않도록 stub 을 유지합니다.

## 3. Legacy 문서의 수정 정책

- 본문 수정은 *원칙적으로 금지*. 역사적 SSOT 의 보존이 목적.
- 헤더의 `last_synced_with` / `last_review` 는 갱신 가능 (메타데이터 정합성).
- 새 정정·추가가 필요하면 `legacy/` 가 아닌 *현재 SSOT* (예: docs/ARCHITECTURE.md, REFACTOR_V5_PLAN.md) 에 기록.
- legacy 파일에 `status: legacy` 와 `moved_to_legacy: <date>`, `moved_by: <reason>` 를 헤더에 명시.

## 4. 향후 정리 (V5 cleanup commit)

V5 의 정식 출시 (v5.0.0) 시점에 추가 cleanup 이 가능합니다.

- v3 시대 코드 (`src/lenses/`, `src/agents/{player,dynamics,chain_reaction,scenario,visual,quality_inspector,synthesis_judge}.py`, `src/archetypes/` (freeform_essay 외), `src/templates/blocks/`) 의 일괄 삭제 시점에 본 legacy 문서들도 함께 검토.
- 단 [REFACTOR_V5_PLAN.md §24](../../REFACTOR_V5_PLAN.md) 의 보존 사항 (Non-touch) 에 따라 v5 본격 작업 중에는 *건드리지 않음*.

## 5. 참고

- 현재 시스템 baseline → [docs/ARCHITECTURE.md](../ARCHITECTURE.md) (v4.5.7)
- V5 리팩토링 마스터 플랜 → [REFACTOR_V5_PLAN.md](../../REFACTOR_V5_PLAN.md)
- 현재 거버넌스 SSOT → [DOCS_GOVERNANCE_V3.md](../../DOCS_GOVERNANCE_V3.md) (이름은 V3 brand)
