---
tier: 3
last_synced_with: v4.5.7
ssot_for: []
depends_on:
  - "docs/legacy/REFACTOR_V3_PLAN.md (실제 SSOT)"
last_review: 2026-05-05
---

# REFACTOR V3 Plan — Redirect Stub

> **이 파일은 stub 입니다.** v3 시대의 마스터 플랜은 [REFACTOR_V5_PLAN.md](REFACTOR_V5_PLAN.md) 의 Phase 0 (Baseline + SSOT Repair) 에 따라 [docs/legacy/REFACTOR_V3_PLAN.md](docs/legacy/REFACTOR_V3_PLAN.md) 로 이전되었습니다.

이 stub 은 [DEVLOG.md](DEVLOG.md) 의 append-only 항목과 `src/lenses/*.py` / `src/models.py` 의 코드 주석에서 옛 경로 (`REFACTOR_V3_PLAN.md`) 로 참조하던 링크가 깨지지 않도록 root 에 남겨둔 redirect 입니다.

- 실제 v3 마스터 플랜 본문 → [docs/legacy/REFACTOR_V3_PLAN.md](docs/legacy/REFACTOR_V3_PLAN.md)
- 현재 V5 마스터 플랜 → [REFACTOR_V5_PLAN.md](REFACTOR_V5_PLAN.md)
- 현재 시스템 baseline 설명 → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (v4.5.7)
- v3 시대 SSOT 모음 → [docs/legacy/](docs/legacy/)

v3 의 7-agent / 11-lens / 11-archetype / 5-gate 파이프라인은 v4.0.0 부터 호출되지 않습니다. 코드 자체는 보존되어 있으나 (cleanup commit 미정), 현재 v4.5.7 의 호출 경로는 ContextAnalyst → NarrativeComposer → Renderer → Watchlist 의 4 phase 입니다 ([docs/ARCHITECTURE.md §1](docs/ARCHITECTURE.md) 참조).
