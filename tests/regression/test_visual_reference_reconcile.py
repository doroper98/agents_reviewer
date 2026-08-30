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


# ─── WRITE-AP-28 (v8.5.13) — 괄호 없는 *문장형* dangling 참조 ──────────
# 2026-08-29 르포 실사고: 마지막 섹션이 "아래 표는 앞으로 지켜볼 지점들을 위험도
# 순으로 정리한 것이다." 로 끝났는데 그 섹션에 차트가 0개였다. v8.2.9 안전망은
# *괄호 안* 만 매칭했고 토큰 목록에 '표' 도 없어 통째로 놓쳤다.


def test_removes_bare_sentence_reference_real_incident() -> None:
    """실사고 재현 — 괄호 없는 메타 문장이 제거되고 앞뒤 문장은 온전하다."""
    prose = (
        "그때 조정되는 것은 수요가 아니라 조달 속도다. "
        "아래 표는 앞으로 지켜볼 지점들을 위험도 순으로 정리한 것이다. "
        "한 걸음 물러서서 보면, 진짜 주제는 40억 달러가 아니다."
    )
    cr = _report([_sec(prose)])
    assert _reconcile_visual_references(cr) == 1
    out = cr.sections[0].prose
    assert "아래 표" not in out
    assert "조달 속도다." in out and "40억 달러가 아니다." in out


def test_table_token_is_covered() -> None:
    """'표' 는 렌더 채널이 아예 없다 — 차트가 있어도 '도표/그래프' 와 같은 그룹."""
    cr = _report([_sec("다음 표는 비중을 정리한 것이다. 이어지는 문장.")])
    assert _reconcile_visual_references(cr) == 1
    assert "다음 표" not in cr.sections[0].prose


def test_keeps_sentence_carrying_facts() -> None:
    """문장 중간·부사격 지시어는 **제거하지 않는다** — 사실을 함께 잃기 때문.

    "아래 표에서 보듯 매출은 12% 늘었다" 를 통째로 지우면 12% 라는 사실이 사라진다.
    조사(는/은/가/이 = 주제격 → 메타 문장 / 에서·를 = 다른 사실 서술)로 가른다.
    """
    for prose in (
        "아래 표에서 보듯 매출은 12% 늘었다.",
        "아래 그래프를 보면 흐름이 뒤집힌다.",
    ):
        cr = _report([_sec(prose)])
        assert _reconcile_visual_references(cr) == 0, f"사실 문장이 제거됨: {prose}"
        assert cr.sections[0].prose == prose


def test_sentence_reference_preserved_when_chart_exists() -> None:
    cr = _report([_sec("아래 그래프는 추이를 보여준다.", charts=[{"type": "bar"}])])
    assert _reconcile_visual_references(cr) == 0
    assert "아래 그래프는" in cr.sections[0].prose


def test_no_false_positive_on_common_nouns() -> None:
    """'발표 / 대표 / 표시 / 표결' 은 시각물 지시어가 아니다 (위치어 없음)."""
    prose = "재무부가 발표한 대표 지표를 표시한다. 표결이 있었다."
    cr = _report([_sec(prose)])
    assert _reconcile_visual_references(cr) == 0
    assert cr.sections[0].prose == prose


def test_reportage_block_bans_table_reference() -> None:
    """르포엔 표 렌더 채널이 없으므로 프롬프트가 '아래 표' 를 금지한다 (1차 방어)."""
    from src.agents.narrative_composer import _REPORTAGE_BLOCK
    assert "'아래 표' 는 절대 쓰지 마라" in _REPORTAGE_BLOCK
