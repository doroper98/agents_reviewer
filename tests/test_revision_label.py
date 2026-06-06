"""v6.0.5 — 발행본 revision major.minor 분리 회귀.

`revision`(정수부, 내용/데이터 수정) + `render_revision`(소수부, 표현/레이아웃
수정) 의 표기 계약(`revision_label`)과 하위호환을 고정한다. patch_report.py 의
증가 정책(데이터=정수부 +1·소수부 리셋 / --rerender-only=소수부 +1)은 본
property 위에서 동작하므로, 표기가 깨지면 발행본 푸터 'Rev x.y' 가 회귀한다.
"""

from __future__ import annotations

from src.models import FullAnalysisResult


def _r(revision: int = 0, render_revision: int = 0) -> FullAnalysisResult:
    # request 필수 필드 우회 — property 로직만 검증.
    return FullAnalysisResult.model_construct(
        revision=revision, render_revision=render_revision
    )


def test_initial_label_is_zero_zero() -> None:
    assert _r().revision_label == "0.0"


def test_data_revision_is_integer_part() -> None:
    assert _r(revision=1).revision_label == "1.0"
    assert _r(revision=3).revision_label == "3.0"


def test_render_revision_is_decimal_part() -> None:
    assert _r(revision=1, render_revision=2).revision_label == "1.2"


def test_label_is_major_minor_not_float() -> None:
    # 진짜 소수가 아니라 major.minor — 1.10 은 minor=10 (1.9 보다 나중).
    assert _r(revision=1, render_revision=10).revision_label == "1.10"


def test_backward_compat_old_json_without_render_revision() -> None:
    # 구 보고서 JSON 엔 render_revision 키가 없음 → Pydantic 기본 0.
    old = FullAnalysisResult.model_construct(revision=1)
    assert old.render_revision == 0
    assert old.revision_label == "1.0"
