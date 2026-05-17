"""V5 Phase 0C — State 압축 / 변환 함수 SSOT.

Plan §4.3 의 6-tier 사이를 잇는 변환 함수.

핵심 변환:
    RawContext             ── ContextAnalyst ──→  EvidencePack
    ContextAnalysis (v4.5)            ──── adapter ──→  EvidencePack
    EvidencePack           ── ResearchDirector ──→  AnalysisBrief
    AnalysisBrief + EvidencePack ──── Composer ──→  DraftReport

본 모듈의 *Phase 0C 적용 범위* — 첫 두 변환만 정식 구현. 나머지는 V5 후속 Phase
진입 시 채움.

token_size 추정:
    Plan §4.2 의 단순 합산 vs 압축 후 비교를 회귀 테스트가 측정 가능하도록
    estimate_state_token_size() 제공. *근사값* — 한국어 ~2.5 chars/token, 영어
    ~4 chars/token 의 평균 ~3 chars/token 으로 단순 분할.
"""

from __future__ import annotations

import json
from typing import Any

from src.state.models import (
    Actor,
    Claim as StateClaim,
    Contradiction as StateContradiction,
    EvidencePack,
    RawContext,
    RawSource,
    SearchHit,
    TimelineEvent,
)


# ─── RawContext → EvidencePack (ContextAnalyst 의 *압축 책임* SSOT) ──────


def compact_to_evidence_pack(
    raw: RawContext,
    *,
    summarize_quote_max_chars: int = 280,
) -> EvidencePack:
    """RawContext 를 EvidencePack 으로 압축.

    Plan §4.3 의 정의:
        RawContext (~50KB raw_sources) → EvidencePack (~12K)

    실제 압축 책임은 ContextAnalyst LLM 이 가져가지만, 본 함수는
    *fallback / dry-run 용* 결정적 압축 (LLM 0). 각 RawSource 의 raw_text 를
    summarize_quote_max_chars 로 잘라 quote_or_data 로 직렬화.

    LLM-driven 압축은 ContextAnalyst.SYSTEM_PROMPT 가 EvidencePack JSON 스키마로
    직접 emit 하도록 갱신될 때 (Phase 1A 또는 그 이후) 본격 활성. 그 전엔
    `evidence_pack_from_context_analysis()` 가 사용된다.
    """
    claims: list[StateClaim] = []
    source_index: dict[str, str] = {}

    for i, src in enumerate(raw.raw_sources, start=1):
        sid = f"S-{i:03d}"
        source_index[sid] = src.url or src.title or f"source_{i}"
        if not src.raw_text:
            continue
        snippet = src.raw_text.strip()[:summarize_quote_max_chars]
        claims.append(
            StateClaim(
                claim_id=f"C-{i:03d}",
                statement=src.title or snippet[:80],
                source_ids=[sid],
                quote_or_data=snippet,
                timestamp=src.published_at,
                reliability=src.reliability,
            )
        )

    return EvidencePack(
        claims=claims,
        actors=[],
        timeline=[],
        contradictions=[],
        source_index=source_index,
        category="",
    )


# ─── ContextAnalysis (v4.5.7 모델) → EvidencePack (V5 모델) ──────────────


def evidence_pack_from_context_analysis(
    context: Any,                     # src.models.ContextAnalysis (lazy import 회피)
    *,
    summarize_quote_max_chars: int = 280,
) -> EvidencePack:
    """v4.5.7 의 ContextAnalysis → V5 EvidencePack 변환.

    Phase 0C 의 *adapter*. 실제 ContextAnalyst 출력이 V5 형식으로 갱신되기
    전까지의 가교. Plan §4.4 의 후속 단계 (Composer / Editor / Visual / Desk) 는
    EvidencePack 만 받는다는 강제 규칙을 *현재 코드 변경 없이* 시뮬레이션 가능.

    매핑:
        context.event_name / category    → EvidencePack.category
        context.summary                  → 추가 Claim (요약)
        context.timeline (list[dict])    → EvidencePack.timeline
        context.key_figures (list[dict]) → EvidencePack.claims (각 수치 → Claim)
        context.sources (list[str])      → EvidencePack.source_index + Claim.source_ids
    """
    # source_index 먼저 구축.
    source_index: dict[str, str] = {}
    sources = list(getattr(context, "sources", None) or [])
    for i, url in enumerate(sources, start=1):
        sid = f"S-{i:03d}"
        source_index[sid] = url

    sids = list(source_index.keys()) or ["S-000"]
    if "S-000" in sids:
        source_index.setdefault("S-000", "")

    claims: list[StateClaim] = []

    # summary → 1개 종합 Claim.
    summary = (getattr(context, "summary", "") or "").strip()
    if summary:
        snippet = summary[:summarize_quote_max_chars]
        claims.append(
            StateClaim(
                claim_id="C-summary",
                statement=snippet[:80],
                source_ids=sids[:],
                quote_or_data=snippet,
                timestamp="",
                reliability="model_inference" if not sources else "secondary",
            )
        )

    # key_figures → 각 수치마다 Claim.
    for i, kf in enumerate(getattr(context, "key_figures", None) or [], start=1):
        if not isinstance(kf, dict):
            continue
        label = (kf.get("label") or "").strip()
        value = str(kf.get("value", "")).strip()
        ctx = (kf.get("context") or "").strip()
        if not (label or value):
            continue
        statement = f"{label}: {value}".strip(": ")
        quote = ctx or statement
        claims.append(
            StateClaim(
                claim_id=f"C-fig-{i:03d}",
                statement=statement[:80],
                source_ids=sids[:1] if sources else ["S-000"],
                quote_or_data=quote[:summarize_quote_max_chars],
                timestamp="",
                reliability="primary" if sources else "model_inference",
            )
        )

    # timeline → TimelineEvent.
    timeline_events: list[TimelineEvent] = []
    for ev in getattr(context, "timeline", None) or []:
        if not isinstance(ev, dict):
            continue
        timeline_events.append(
            TimelineEvent(
                when=str(ev.get("date") or ev.get("when") or ""),
                what=str(ev.get("event") or ev.get("what") or ""),
                impact=str(ev.get("impact") or ""),
                source_ids=sids[:1] if sources else [],
            )
        )

    return EvidencePack(
        claims=claims,
        actors=[],            # v4.5.7 ContextAnalysis 에 actors 없음 — Phase 1A 가 채움.
        timeline=timeline_events,
        contradictions=[],    # v4.5.7 에선 ComposedReport 가 발견. EvidencePack 으론 비어 있음.
        source_index=source_index,
        category=str(getattr(context, "category", "") or ""),
    )


# ─── 토큰 크기 추정 (회귀 테스트의 30% 절감 검증용) ───────────────────────


def estimate_state_token_size(state: Any) -> int:
    """Pydantic 모델의 직렬화된 JSON 길이를 *근사 토큰 수* 로 환산.

    한국어 + 영어 혼합 ~3 chars/token 가정. Plan §4.5 의 인수 기준
    "v4.5.x 와 동일 prompt 에서 V5 의 총 입력 토큰이 *압축 적용 전 단순 합산
    대비 30% 이상 감소*" 측정의 결정적 보조 도구.

    LLM 의 실제 tokenizer (cl100k_base 등) 로 측정하는 것이 정확하지만, 본
    함수는 *상대 비교* 용이라 근사로 충분. tokenizer 미설치 환경에서도 동작.
    """
    if hasattr(state, "model_dump_json"):
        text = state.model_dump_json()
    elif isinstance(state, str):
        text = state
    elif isinstance(state, (dict, list)):
        text = json.dumps(state, ensure_ascii=False)
    else:
        text = str(state)
    # 한국어가 섞인 JSON 의 평균 char-to-token 비율은 약 3.0.
    return max(1, len(text) // 3)
