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
    BarOptions,
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
    validate_chart_options,
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
from src.visual.deterministic_gate import (
    HARD_FAIL_RULES,
    MODE_LOWER_BOUND,
    SOFT_FAIL_RULES,
    ChartCountLimits,
    DeterministicGateResult,
    run_deterministic_gate,
)
from src.visual.exhibit_numbering import (
    EXHIBIT_REF_PATTERN,
    EXHIBIT_REF_RANGE_PATTERN,
    assign_exhibit_ids,
    collect_exhibit_refs,
    count_exhibit_refs,
    resolve_exhibit_refs,
    resolve_exhibit_refs_html,
    validate_exhibit_refs,
)
from src.visual.word_budget import (
    COMPOSER_MAX_TOKENS_V5,
    MODE_BUDGET_BANDS,
    MODE_TARGET_CHARS_LOWER,
    TruncationStatus,
    WordBudget,
    adaptive_max_tokens,
    complexity_score_from_context,
    compute_word_budgets,
    detect_truncation,
    gini_coefficient,
    section_length_distribution,
    stitch_continuation,
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
    # Phase 6 — Schema Pydantic guards (Gate A)
    "BarChartGuard",
    "BarOptions",
    "BubbleChartGuard",
    "DonutGuard",
    "GanttGuard",
    "HeatmapGuard",
    "LineChartGuard",
    "NetworkGuard",
    "StackedBarGuard",
    "guard_for_type",
    "parse_time",
    "validate_chart_data",
    "validate_chart_options",
    # Phase 6 — Visual Sanity (Gate C)
    "DEFAULT_THRESHOLDS",
    "SanityCheckThresholds",
    "SanityResult",
    "visual_sanity_check_svg",
    # Phase 6 — Chart Gate D + 통합
    "ChartGateResult",
    "FallbackLadder",
    "run_chart_gate",
    # Phase 7A — Deterministic Publish Gate
    "DeterministicGateResult",
    "run_deterministic_gate",
    "HARD_FAIL_RULES",
    "SOFT_FAIL_RULES",
    "MODE_LOWER_BOUND",
    "ChartCountLimits",
    # Phase 4 — Exhibit 번호제
    "EXHIBIT_REF_PATTERN",
    "EXHIBIT_REF_RANGE_PATTERN",
    "assign_exhibit_ids",
    "collect_exhibit_refs",
    "count_exhibit_refs",
    "resolve_exhibit_refs",
    "resolve_exhibit_refs_html",
    "validate_exhibit_refs",
    # Phase 5 — Word Budget + 절단 검출
    "TruncationStatus",
    "WordBudget",
    "MODE_TARGET_CHARS_LOWER",
    "MODE_BUDGET_BANDS",
    "COMPOSER_MAX_TOKENS_V5",
    "detect_truncation",
    "adaptive_max_tokens",
    "complexity_score_from_context",
    "compute_word_budgets",
    "gini_coefficient",
    "section_length_distribution",
    "stitch_continuation",
]
