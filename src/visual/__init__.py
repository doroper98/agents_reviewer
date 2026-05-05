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
from src.visual.v5_theme import (
    BURGUNDY_TOKENS,
    EDITORIAL_TOKENS,
    V5_FONTS,
    V5_THEME,
    apply_theme_to_spec,
    get_theme_config,
    get_token_set,
)
from src.visual.vega_adapter import (
    VegaSpecError,
    chart_dict_to_vega_spec,
    is_vega_cli_available,
    is_vl_convert_available,
    render_vega_lite,
    validate_vega_spec,
)
from src.visual.capability_registry import (
    REGISTRY_PATH,
    CapabilityRegistryError,
    assert_chart_in_registry,
    check_required_fields,
    get_capability,
    is_chart_type_allowed,
    list_all_types,
    list_experimental_types,
    list_guarded_types,
    list_safe_types,
    load_registry,
)
from src.visual.schemas import (
    BarChartGuard,
    BubbleChartGuard,
    DonutGuard,
    GanttGuard,
    HeatmapGuard,
    LineChartGuard,
    NetworkGuard,
    StackedBarGuard,
    guard_for_type,
    parse_time,
    validate_chart_data,
)
from src.visual.sanity_check import (
    DEFAULT_THRESHOLDS,
    SanityCheckThresholds,
    SanityResult,
    visual_sanity_check_svg,
)
from src.visual.chart_gate import (
    ChartGateResult,
    FallbackLadder,
    run_chart_gate,
)

__all__ = [
    # Phase 2A — EvidenceDataset Contract
    "EvidenceDatasetGuard",
    "EvidenceDatasetGuardError",
    "ensure_chart_data_cited_in_prose",
    "ensure_chart_has_source_ids",
    "extract_chart_numbers",
    "validate_evidence_dataset",
    # Phase 2 — V5 design token SSOT
    "EDITORIAL_TOKENS",
    "BURGUNDY_TOKENS",
    "V5_THEME",
    "V5_FONTS",
    "get_theme_config",
    "apply_theme_to_spec",
    "get_token_set",
    # Phase 2 — Vega-Lite adapter
    "render_vega_lite",
    "validate_vega_spec",
    "chart_dict_to_vega_spec",
    "is_vl_convert_available",
    "is_vega_cli_available",
    "VegaSpecError",
    # Phase 2B — Capability Registry
    "REGISTRY_PATH",
    "CapabilityRegistryError",
    "assert_chart_in_registry",
    "check_required_fields",
    "get_capability",
    "is_chart_type_allowed",
    "list_all_types",
    "list_experimental_types",
    "list_guarded_types",
    "list_safe_types",
    "load_registry",
]
