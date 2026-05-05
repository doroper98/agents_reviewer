"""V5 Phase 4 — Exhibit 번호제 + cross-reference (Plan §11).

차트가 섹션 안에 갇혀있는 v4.5.7 구조 → *첫째 클래스 Exhibit* 으로 승격.
자동 번호 부여 + 본문 cross-reference.

[Plan §11.2 — Why]
IB 보고서 어법: "Exhibit 4 에서 보듯..." / "(Exhibit 7 참조)" /
"Exhibits 2-3 비교". 차트가 *논거의 anchor* 이자 *공유 참조점*.
본문이 차트를 가리키고, 차트가 본문을 강화하는 양방향 결합.

[Plan §11.3 — Cross-ref 표기]
    [[ex:4]]    → "Exhibit 4"
    [[exr:4]]   → "(Exhibit 4 참조)"
    [[exs:2-3]] → "Exhibits 2~3"

[Plan §11.4 — 시각 표기]
- 좌상단 회색 일련번호: "EXHIBIT 4"
- 차트 위 caption: 제목 / 부제
- 차트 아래 footer: source · takeaway

[Plan §11.5 인수 기준]
- 본문 cross-ref 사례 보고서당 평균 1~3회
- exhibit 번호 충돌 / 미존재 ref 회귀 테스트 통과 (이미 Phase 7A 에서
  exhibit_ref_broken 으로 차단 — 본 모듈은 *번호 부여* 책임만).

[AP-V5-6 — Plan §23]
"Exhibit 번호의 임의 부여 금지. exhibit_id 는 Renderer 가 자동으로 부여한다.
composer / Editor 가 직접 숫자를 박지 않는다. cross-ref 는 [[ex:N]] 표기로만."

Public API:
    from src.visual.exhibit_numbering import (
        assign_exhibit_ids,
        resolve_exhibit_refs,
        collect_exhibit_refs,
        validate_exhibit_refs,
        EXHIBIT_REF_PATTERN,
        EXHIBIT_REF_RANGE_PATTERN,
    )
"""

from __future__ import annotations

import re
from typing import Any

from src.state.models import Exhibit


# ─── Plan §11.3 정규식 SSOT ──────────────────────────────────────


# [[ex:N]] 또는 [[exr:N]] — 단일 참조.
EXHIBIT_REF_PATTERN = re.compile(r"\[\[(ex|exr):\s*(\d+)\s*\]\]")
# [[exs:N-M]] 또는 [[exs:N~M]] — 범위 참조.
EXHIBIT_REF_RANGE_PATTERN = re.compile(r"\[\[exs:\s*(\d+)\s*[-~]\s*(\d+)\s*\]\]")


# ─── 번호 부여 (Plan §11.4 + AP-V5-6) ──────────────────────────────


def assign_exhibit_ids(exhibits: list[Exhibit | dict[str, Any]]) -> list[Exhibit]:
    """Renderer 단계의 *자동 번호 부여*. composer / Editor 가 직접 박은
    exhibit_id 는 *덮어씀* (AP-V5-6 강제).

    Args:
        exhibits: VisualPlanner 또는 ChartGate 통과 후의 exhibit list.

    Returns:
        list[Exhibit] — exhibit_id 가 1부터 순차 부여된 사본.
    """
    out: list[Exhibit] = []
    for i, ex in enumerate(exhibits, start=1):
        if isinstance(ex, dict):
            data = dict(ex)
            data["exhibit_id"] = str(i)   # Pydantic str 모델
            out.append(Exhibit.model_validate(data))
        else:
            # Pydantic model — copy with new exhibit_id.
            ex_copy = ex.model_copy(update={"exhibit_id": str(i)})
            out.append(ex_copy)
    return out


# ─── Cross-ref 치환 (Plan §11.3) ────────────────────────────────


def resolve_exhibit_refs(prose: str, *, total_exhibits: int = 0) -> str:
    """본문 안의 [[ex:N]] / [[exr:N]] / [[exs:N-M]] 를 사람-친화 텍스트로 치환.

    Args:
        prose: composer / Editor 가 emit 한 본문.
        total_exhibits: 보고서의 exhibit 총 개수. 미존재 ref 는 *빈 문자열* 로
            치환 (또는 원본 유지 — 정책 결정).

    Returns:
        치환된 prose.

    [HTML 렌더 시점 정책]
    - [[ex:4]] → '<a href="#exhibit-4">Exhibit 4</a>' (HTML 모드).
    - 본 함수는 *plain text* 치환 — Renderer 의 Jinja filter 에서 HTML 모드
      별도 함수 사용.
    """
    if not prose:
        return ""

    def _replace_single(m: re.Match[str]) -> str:
        kind = m.group(1)            # 'ex' or 'exr'
        n = int(m.group(2))
        if total_exhibits > 0 and (n < 1 or n > total_exhibits):
            return ""                # 미존재 — 빈 문자열로 (Phase 7A 가 fail 처리)
        if kind == "exr":
            return f"(Exhibit {n} 참조)"
        return f"Exhibit {n}"

    def _replace_range(m: re.Match[str]) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        lo, hi = min(a, b), max(a, b)
        if total_exhibits > 0 and (lo < 1 or hi > total_exhibits):
            return ""
        return f"Exhibits {lo}~{hi}"

    text = EXHIBIT_REF_RANGE_PATTERN.sub(_replace_range, prose)
    text = EXHIBIT_REF_PATTERN.sub(_replace_single, text)
    return text


def resolve_exhibit_refs_html(prose: str, *, total_exhibits: int = 0) -> str:
    """HTML 모드 — 클릭 가능한 anchor 로 치환.

    Renderer 의 Jinja filter 가 호출. Plan §11.4 의 anchor 점프 활성.
    """
    if not prose:
        return ""

    def _replace_single(m: re.Match[str]) -> str:
        kind = m.group(1)
        n = int(m.group(2))
        if total_exhibits > 0 and (n < 1 or n > total_exhibits):
            return ""
        href = f'#exhibit-{n}'
        if kind == "exr":
            return f'(<a href="{href}" class="exhibit-ref">Exhibit {n}</a> 참조)'
        return f'<a href="{href}" class="exhibit-ref">Exhibit {n}</a>'

    def _replace_range(m: re.Match[str]) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        lo, hi = min(a, b), max(a, b)
        if total_exhibits > 0 and (lo < 1 or hi > total_exhibits):
            return ""
        href_lo = f'#exhibit-{lo}'
        href_hi = f'#exhibit-{hi}'
        return (
            f'<a href="{href_lo}" class="exhibit-ref">Exhibits {lo}</a>'
            f'~<a href="{href_hi}" class="exhibit-ref">{hi}</a>'
        )

    text = EXHIBIT_REF_RANGE_PATTERN.sub(_replace_range, prose)
    text = EXHIBIT_REF_PATTERN.sub(_replace_single, text)
    return text


# ─── 검증 — Phase 7A deterministic_gate 와 결합 ──────────────────


def collect_exhibit_refs(prose: str) -> set[int]:
    """본문 안의 모든 exhibit ref 번호 수집 (단일 + 범위).

    Phase 7A 의 _collect_exhibit_refs 와 동일 형식 — 본 모듈이 SSOT.
    """
    refs: set[int] = set()
    for m in EXHIBIT_REF_PATTERN.finditer(prose or ""):
        try:
            refs.add(int(m.group(2)))
        except (ValueError, IndexError):
            continue
    for m in EXHIBIT_REF_RANGE_PATTERN.finditer(prose or ""):
        try:
            a, b = int(m.group(1)), int(m.group(2))
            for i in range(min(a, b), max(a, b) + 1):
                refs.add(i)
        except (ValueError, IndexError):
            continue
    return refs


def validate_exhibit_refs(
    composed: dict[str, Any],
) -> tuple[bool, list[int]]:
    """본문의 모든 ref 번호가 *실제 exhibit* 에 존재하는지 검증.

    Phase 7A 의 exhibit_ref_broken hard fail 의 사전 가드.

    Args:
        composed: ComposedReport 또는 EditedReport dict.
            exhibits 또는 charts 필드를 검사.

    Returns:
        (all_valid, broken_refs) — broken_refs 는 미존재 번호 list.
    """
    exhibits = composed.get("exhibits") or composed.get("charts") or []
    if not isinstance(exhibits, list):
        exhibits = []
    valid_ids = set(range(1, len(exhibits) + 1))
    # exhibit_id 가 명시적 박힌 경우도 valid.
    for ex in exhibits:
        if isinstance(ex, dict):
            xid = ex.get("exhibit_id")
            if xid:
                try:
                    valid_ids.add(int(str(xid)))
                except ValueError:
                    pass

    sections = composed.get("sections") or []
    broken: set[int] = set()
    for s in sections:
        prose = ((s or {}).get("prose") or "")
        refs = collect_exhibit_refs(prose)
        for ref in refs:
            if ref not in valid_ids:
                broken.add(ref)

    return (not broken), sorted(broken)


# ─── Cross-ref 카운팅 (Plan §11.5 인수 기준 — 보고서당 평균 1~3회) ──


def count_exhibit_refs(composed: dict[str, Any]) -> dict[str, Any]:
    """보고서 전체의 cross-ref 통계.

    Returns:
        {"total_refs": int, "ref_density": float, "unique_exhibits_referenced": int}
        ref_density = total_refs / n_exhibits (보고서당 평균 1~3 권장).
    """
    sections = composed.get("sections") or []
    exhibits = composed.get("exhibits") or composed.get("charts") or []
    n_exhibits = len(exhibits) if isinstance(exhibits, list) else 0

    total = 0
    unique_refs: set[int] = set()
    for s in sections:
        prose = ((s or {}).get("prose") or "")
        refs = collect_exhibit_refs(prose)
        total += len(refs)
        unique_refs.update(refs)

    density = (total / n_exhibits) if n_exhibits > 0 else 0.0
    return {
        "total_refs": total,
        "ref_density": round(density, 2),
        "unique_exhibits_referenced": len(unique_refs),
        "n_exhibits": n_exhibits,
    }
