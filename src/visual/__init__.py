"""V5 Phase 2 / 2A / 2B / 6 — Visualization layer.

본 모듈은 V5 의 시각 스택 (Vega-Lite 어댑터 / EvidenceDataset Contract /
Capability Registry / Chart Gate) 의 SSOT 가 모이는 곳. v4.5.7 의
``src/visual_builder.py`` (deprecated) 와는 별개.

Phase 2A (현재) — EvidenceDataset Contract:
    from src.visual import (
        EvidenceDatasetGuard,
        EvidenceDatasetGuardError,
        ensure_chart_has_source_ids,
        ensure_chart_data_cited_in_prose,
    )

[향후 추가 — Phase 2 / 2B / 6]
- src/visual/vega_adapter.py        — Vega-Lite spec → SVG (V5 §3 Phase 2)
- src/visual/capability_registry.py — VISUAL_CAPABILITY_REGISTRY.yaml 로더 (Phase 2B)
- src/visual/chart_gate.py          — 4중 게이트 (Phase 6)
- src/visual/sanity_check.py        — Plan §7.4 SVG 정적 검증 (Phase 6 Gate C)
"""

from __future__ import annotations

from src.visual.evidence_dataset import (
    EvidenceDatasetGuard,
    EvidenceDatasetGuardError,
    ensure_chart_data_cited_in_prose,
    ensure_chart_has_source_ids,
    extract_chart_numbers,
    validate_evidence_dataset,
)

__all__ = [
    "EvidenceDatasetGuard",
    "EvidenceDatasetGuardError",
    "ensure_chart_data_cited_in_prose",
    "ensure_chart_has_source_ids",
    "extract_chart_numbers",
    "validate_evidence_dataset",
]
