"""v8.2.9 — 깨진 시각물 약속(dangling visual reference) 제거 회귀 (사용자 catch).

2026-06-27 르포(`analysis_20260627_151401`): 본문이 '(아래 관계도)'로 stakeholder_map
을 약속했는데 composer 가 차트를 emit 하지 않아 독자가 빈 자리를 봤다. 또 '(아래
지도)'/'(아래 그래프)'도 같은 위험. 재발방지 = ① composer 프롬프트가 지시어를 쓰면
시각물 emit 강제(1차) + ② 결정적 안전망 `_reconcile_visual_references` 가 충족 안 된
괄호 지시어를 제거(없는 그림 가리키기 차단). 본 테스트는 ②를 고정한다.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.orchestrator import _reconcile_visual_references


def _sec(prose, charts=None):
    # 리컨실러는 duck-typed getattr 만 쓴다 (prose/charts) — 모델 차트 검증과 무관하게
    # '차트 존재' 자체를 모사하려고 경량 객체를 쓴다.
    return SimpleNamespace(prose=prose, charts=charts or [])


def _report(sections, embedded_map=None):
    return SimpleNamespace(sections=sections, embedded_map=embedded_map)


def test_strips_dangling_relation_reference() -> None:
    cr = _report([_sec("네 회사가 있다(아래 관계도). 파는 쪽이 무게중심이다.")])
    n = _reconcile_visual_references(cr)
    assert n == 1
    assert "관계도" not in cr.sections[0].prose
    assert cr.sections[0].prose == "네 회사가 있다. 파는 쪽이 무게중심이다."


def test_keeps_relation_reference_when_stakeholder_map_present() -> None:
    cr = _report([_sec("네 회사가 있다(아래 관계도).", [{"type": "stakeholder_map"}])])
    n = _reconcile_visual_references(cr)
    assert n == 0
    assert "(아래 관계도)" in cr.sections[0].prose


def test_strips_graph_reference_without_chart_keeps_with_chart() -> None:
    # 그래프 지시어 + 차트 없음 → 제거
    cr1 = _report([_sec("값이 뛴다(아래 그래프).")])
    assert _reconcile_visual_references(cr1) == 1
    assert "그래프" not in cr1.sections[0].prose
    # 그래프 지시어 + bar 차트 있음 → 보존
    cr2 = _report([_sec("값이 뛴다(아래 그래프).", [{"type": "bar"}])])
    assert _reconcile_visual_references(cr2) == 0
    assert "(아래 그래프)" in cr2.sections[0].prose


def test_map_reference_depends_on_embedded_map() -> None:
    # embedded_map 없음 → '(아래 지도)' 제거
    cr_no = _report([_sec("한국이다(아래 지도).")])
    assert _reconcile_visual_references(cr_no) == 1
    assert "지도" not in cr_no.sections[0].prose
    # embedded_map 있음 → 보존
    cr_yes = _report([_sec("한국이다(아래 지도).")], embedded_map={"markers": [{"id": "a"}]})
    assert _reconcile_visual_references(cr_yes) == 0
    assert "(아래 지도)" in cr_yes.sections[0].prose


def test_narrative_bare_mention_not_touched() -> None:
    # 괄호 지시어가 아닌 서술적 언급('지도 위 한 점')은 건드리지 않는다.
    cr = _report([_sec("향하는 곳은 지도 위 한 점, 한국이다.")])
    n = _reconcile_visual_references(cr)
    assert n == 0
    assert cr.sections[0].prose == "향하는 곳은 지도 위 한 점, 한국이다."


def test_reportage_block_has_visual_consistency_rule() -> None:
    """v8.2.9 — _REPORTAGE_BLOCK 에 시각물-본문 일치 강제 규칙 marker."""
    from src.agents.narrative_composer import _REPORTAGE_BLOCK
    for marker in ("시각물-본문 일치", "깨진 약속", "반드시 emit", "위치-비의존"):
        assert marker in _REPORTAGE_BLOCK, f"시각물 일치 규칙 marker '{marker}' 누락"
