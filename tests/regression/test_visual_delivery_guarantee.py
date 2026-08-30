"""V9-0 시각물 전달 보증 (Visual Delivery Guarantee) 회귀 — v8.5.12.

원칙: **방출된 시각물은 (a) 렌더되거나 (b) 드롭 사유가 관측되거나 둘 중 하나다.**
셋째 길(침묵)은 없다.

배경 — 2026-08-29 V9 감사에서 확인된 손실 경로 (발행본 335건 실측):
  · 프롬프트↔가드 계약 불일치로 heatmap·stacked 100% silent drop (CHART-AP-44)
  · 드롭된 type 이 usage_log 에 "0회 emit" = 기아로 위장 → 재균형 힌트가 깨진
    type 을 더 밀어넣고 다시 전부 버리는 악순환
  · 템플릿 has_data 게이트가 두 archetype 에 중복 소유 + 서버 로그 0 (완전 침묵)
  · 파국 폴백(_recover_head_loss)이 charts 를 통째로 버림 (발행본의 9%가 1-섹션)
  · maps.js 가 markers 0개면 지도 전체 미렌더 (rings/regions 만인 payload 손실)
  · world-atlas CDN 단일 의존 — 차단 시 육지 없는 '빈 바다' 지도
"""

from __future__ import annotations

from pathlib import Path

from tests.regression._pytest_compat import pytest

from src.models import ComposedSection
from src.visual.schemas import chart_renderable

_REPO = Path(__file__).resolve().parents[2]


# ─── ① 드롭 기록 (관측 가능성) ─────────────────────────────────────────


def test_dropped_charts_are_recorded_not_silent() -> None:
    """가드가 버린 차트는 `_dropped_charts` 에 사유와 함께 남는다.

    orchestrator 가 이걸 읽어 usage_log(emit/kept)와 드롭 경고에 쓴다.
    기록이 없으면 손실이 bot.log 한 줄 외엔 어디에도 안 남는다.
    """
    sec = ComposedSection(
        heading="테스트", prose="본문",
        charts=[
            {"type": "bar", "title": "정상", "data": [{"label": "A", "value": 1}]},
            # donut 2-segment — CHART-AP-16 가드가 거절
            {"type": "donut", "title": "위반", "data": [
                {"label": "a", "value": 1}, {"label": "b", "value": 2},
            ]},
        ],
    )
    assert [c["title"] for c in sec.charts] == ["정상"]
    assert len(sec._dropped_charts) == 1
    rec = sec._dropped_charts[0]
    assert rec["type"] == "donut"
    assert rec["title"] == "위반"
    assert rec["reason"]  # 사유가 비어 있으면 원인 추적 불가


def test_no_drops_leaves_record_empty() -> None:
    sec = ComposedSection(
        heading="t", prose="p",
        charts=[{"type": "bar", "title": "ok", "data": [{"label": "A", "value": 1}]}],
    )
    assert sec._dropped_charts == []


# ─── ② usage_log emit/kept 2단 (기아 ↔ 배관 이상 구분) ────────────────


def test_usage_log_separates_starvation_from_plumbing_fault(tmp_path) -> None:
    """가드가 전량 버린 type 은 '기아' 가 아니라 '배관 이상' 으로 분류된다.

    구분하지 않으면 재균형 힌트가 깨진 type 을 더 자주 emit 시키고 전부 다시
    버려지는 자기증폭 고리가 돈다 (CHART-AP-44 의 악순환).
    """
    from src.visual.usage_log import analyze, append_run, composer_rebalance_hint

    log = tmp_path / "usage.jsonl"
    for _ in range(12):
        append_run(
            event="e", mode="deep",
            chart_types=["bar", "line"],
            dropped_types=["heatmap"],   # emit 은 됐는데 가드가 전량 drop
            path=log,
        )
    res = analyze(window=30, path=log)
    assert "heatmap" in res["plumbing_suspect_types"], "배관 이상 미검출"
    assert res["dropped_distribution"]["heatmap"] == 12
    # 힌트는 깨진 type 을 밀어넣지 않는다
    assert "heatmap" not in composer_rebalance_hint(window=30, path=log)


def test_usage_log_backward_compatible_without_dropped(tmp_path) -> None:
    """dropped 없이 기록해도 (구 형식) 분석이 깨지지 않는다."""
    from src.visual.usage_log import analyze, append_run

    log = tmp_path / "usage.jsonl"
    append_run(event="e", mode="deep", chart_types=["bar"], path=log)
    res = analyze(window=30, path=log)
    assert res["distribution"]["bar"] == 1
    assert res["dropped_distribution"] == {}
    assert res["plumbing_suspect_types"] == []


# ─── ③ 템플릿 has_data 게이트 SSOT ────────────────────────────────────


def test_chart_renderable_is_single_source_for_both_templates() -> None:
    """두 archetype 이 규칙 사본을 갖지 않고 공용 필터를 쓴다.

    중복 소유 시절 freeform 엔 폐기된 `network` 분기가 남고 stakeholder_map
    분기가 없었다 (CHART-AP-38 재발 대기 상태).
    """
    for name in ("freeform_essay.html", "reportage.html"):
        tpl = (_REPO / "src" / "templates" / "archetypes" / name).read_text(encoding="utf-8")
        assert "chart_renderable" in tpl, f"{name}: SSOT 필터 미사용"
        assert "ch.data.scenarios" not in tpl, f"{name}: 규칙 사본 잔존"
        assert "ch.type == 'network'" not in tpl, f"{name}: 폐기 type 분기 잔존"


def test_chart_renderable_rules() -> None:
    ok = [
        {"type": "bar", "data": [{"label": "a", "value": 1}]},
        {"type": "stacked", "data": {"scenarios": [{"name": "s", "segments": [{"label": "x", "value": 1}]}]}},
        {"type": "stakeholder_map", "data": {"nodes": [{"id": "a"}, {"id": "b"}], "edges": []}},
        {"type": "dual_line", "data": {"left": {"series": [1]}, "right": {"series": [2]}}},
        {"type": "heatmap", "data": [{"x": "a", "y": "b", "value": 1}]},
    ]
    bad = [
        {"type": "bar", "data": []},
        {"type": "bar"},
        # 렌더 불가 형태 (구 가드 모양) — 카드조차 만들지 않는다
        {"type": "stacked", "data": {"categories": ["a"], "series": [{"name": "s", "values": [1]}]}},
        {"type": "stakeholder_map", "data": {"nodes": [{"id": "a"}]}},   # 노드 1개
        {"type": "dual_line", "data": {"left": {"series": [1]}, "right": {}}},
        "not-a-dict",
    ]
    for ch in ok:
        assert chart_renderable(ch) is True, f"렌더 가능한데 거절: {ch}"
    for ch in bad:
        assert chart_renderable(ch) is False, f"렌더 불가인데 허용: {ch}"


def test_report_synthesizer_registers_the_filter() -> None:
    src = (_REPO / "src" / "agents" / "report_synthesizer.py").read_text(encoding="utf-8")
    assert 'env.filters["chart_renderable"]' in src


# ─── ④ 파국 폴백의 시각물 보존 ────────────────────────────────────────


def test_head_loss_recovery_salvages_charts() -> None:
    """head-loss 복구가 heading/prose 만 건지고 charts 를 버리지 않는다.

    발행본의 9%가 1-섹션 폴백이었고, 그 전부가 시각물 0 이었다.
    """
    from src.agents.narrative_composer import NarrativeComposer

    raw = (
        '      "heading": "값이 뛴다",\n'
        '      "prose": "본문 내용이다. 두 번째 문장.",\n'
        '      "charts": [{"type":"bar","title":"수출","data":['
        '{"label":"A","value":10},{"label":"B","value":20}]}]\n'
        "    }"
    )
    rep = NarrativeComposer._recover_head_loss(raw)
    assert rep is not None, "복구 자체 실패"
    assert rep.degraded is True
    charts = rep.sections[0].charts or []
    assert [c.get("type") for c in charts] == ["bar"], "차트가 복구에서 유실됨"


# ─── ⑤ 지도 — 렌더 조건 완화 + CDN 단일 의존 제거 ────────────────────


def test_map_renders_without_markers_when_other_content_exists() -> None:
    """rings/regions/sea_labels 만 있는 payload 도 지도를 그린다.

    그전까진 markers 0개면 지도 *전체* 를 안 그려, 제목·줌 버튼만 있는 빈 상자가
    발행됐다 (rings 는 v7.5.0 도입 후 발행 실적 0회였던 배경 중 하나).
    """
    js = (_REPO / "src" / "templates" / "static" / "maps.js").read_text(encoding="utf-8")
    assert "if (!payload || !(payload.markers || []).length) return;" not in js, \
        "markers 필수 조건이 되살아남"
    assert "_hasContent" in js
    for key in ("markers", "rings", "regions", "sea_labels", "arcs"):
        assert f"'{key}'" in js


def test_world_atlas_has_local_fallback() -> None:
    """world-atlas 는 CDN 단일 의존이 아니다 (차단 시 '빈 바다' 지도 차단)."""
    assert (_REPO / "src" / "templates" / "static" / "world-atlas-110m.js").exists()
    synth = (_REPO / "src" / "agents" / "report_synthesizer.py").read_text(encoding="utf-8")
    assert '"world-atlas-110m.js"' in synth, "STATIC_ASSETS 미등록 — report dir 로 동기화 안 됨"
    for name in ("maps.js", "charts.js"):
        js = (_REPO / "src" / "templates" / "static" / name).read_text(encoding="utf-8")
        assert "world-atlas-110m.js" in js, f"{name}: 로컬 폴백 미배선"


# ─── ⑥ wrangler 업로드 상한 (2026-08-25 행 사고) ──────────────────────


def test_cloudflare_upload_has_timeout_and_kill() -> None:
    """업로드가 멎어도 파일 첨부 폴백이 도착하도록 상한 + 강제 종료가 있다."""
    src = (_REPO / "src" / "agents" / "report_synthesizer.py").read_text(encoding="utf-8")
    idx = src.find("async def _upload_to_cloudflare")
    assert idx > 0
    body = src[idx:idx + 4000]
    assert "asyncio.wait_for" in body, "업로드 상한 없음 — 무한 대기 회귀"
    assert "asyncio.TimeoutError" in body
    assert "proc.kill()" in body, "타임아웃 후 프로세스 강제 종료 없음"
    cfg = (_REPO / "src" / "config.py").read_text(encoding="utf-8")
    assert "wrangler_timeout_sec" in cfg


def test_cloudflare_upload_timeout_returns_empty_url() -> None:
    """상한 초과 시 예외를 던지지 않고 빈 URL 로 graceful degrade."""
    import asyncio
    from types import SimpleNamespace

    from src.agents.report_synthesizer import ReportSynthesizer

    synth = ReportSynthesizer.__new__(ReportSynthesizer)
    synth.config = SimpleNamespace(
        cloudflare_account_id="acct", cloudflare_api_token="tok",
        cloudflare_project_name="proj", wrangler_timeout_sec=1,
    )

    class _HangingProc:
        returncode = None
        killed = False

        async def communicate(self):
            # 영원히 안 끝나는 wrangler. asyncio.sleep 은 스위트 안 다른 테스트가
            # 전역 패치할 수 있어(즉시 반환) 신뢰 불가 — 절대 set 되지 않는
            # Event 로 대기한다.
            await asyncio.Event().wait()

        def kill(self):
            type(self).killed = True

        async def wait(self):
            return 0

    async def _run():
        import src.agents.report_synthesizer as rs
        orig_exec = asyncio.create_subprocess_exec
        orig_which = rs.shutil.which
        rs.shutil.which = lambda name: "/usr/bin/wrangler" if name == "wrangler" else None

        async def fake_exec(*a, **k):
            return _HangingProc()

        asyncio.create_subprocess_exec = fake_exec
        try:
            return await synth._upload_to_cloudflare("/tmp/x/report.html")
        finally:
            asyncio.create_subprocess_exec = orig_exec
            rs.shutil.which = orig_which

    url = asyncio.run(_run())
    assert url == "", "타임아웃인데 빈 URL 로 폴백하지 않음"
    assert _HangingProc.killed, "멎은 wrangler 를 죽이지 않음 (좀비 프로세스)"


# ─── v8.5.14 — Codex 리뷰 4건 (P1 1 + P2 3) ──────────────────────────
# P1 은 v8.5.12 가 CHART-AP-38/44 를 고치면서 *재생산한* 같은 클래스의 회귀다.
# 가드는 통과하는데 템플릿 게이트가 걸러 카드가 사라지는 형태 — parity 테스트가
# 2층(가드)만 보고 3층(템플릿 게이트)을 안 봐서 랜딩 전에 못 잡았다.


def test_gantt_list_form_renders() -> None:
    """P1 — gantt 프롬프트 계약은 list. dict{rows} 전용으로 막으면 전량 사라진다.

    실제 발행본의 gantt 도 전부 list 형태다. `validate_chart_data` 는 양형을
    받는데 `chart_renderable` 만 dict 를 요구하면 가드 통과 → 카드 소멸.
    """
    rows = [
        {"label": "협상", "start": "2026-01", "end": "2026-03"},
        {"label": "비준", "start": "2026-03", "end": "2026-06"},
    ]
    from src.visual.schemas import validate_chart_data
    ok, _ = validate_chart_data("gantt", rows)
    assert ok, "list 형 gantt 가 가드에서 탈락"
    assert chart_renderable({"type": "gantt", "data": rows}), "list 형 gantt 카드 소멸"
    # dict{rows} 형태도 계속 지원
    assert chart_renderable({"type": "gantt", "data": {"rows": rows}})
    # 빈 데이터는 양형 모두 거절
    assert not chart_renderable({"type": "gantt", "data": []})
    assert not chart_renderable({"type": "gantt", "data": {"rows": []}})


def test_table_reference_not_satisfied_by_unrelated_chart() -> None:
    """P2 — '표' 는 렌더 채널이 없으므로 무관한 차트가 대신 충족시킬 수 없다.

    v8.5.13 은 '표' 를 그래프와 같은 그룹(needed=None)에 넣어, 섹션에 bar 차트
    하나만 있어도 "아래 표는 …" 이 살아남았다 — 고치려던 깨진 약속이 그대로 남는다.
    """
    from types import SimpleNamespace

    from src.orchestrator import _reconcile_visual_references

    sec = SimpleNamespace(
        heading="s", prose="아래 표는 지켜볼 지점을 정리한 것이다. 다음 문장.",
        charts=[{"type": "bar"}],          # 표와 무관한 차트
    )
    n = _reconcile_visual_references(SimpleNamespace(sections=[sec], embedded_map=None))
    assert n == 1, "무관한 차트가 '표' 참조를 충족시켜 버림"
    assert "아래 표" not in sec.prose
    # 반면 '그래프' 는 차트가 있으면 정상 충족 (기존 동작 유지)
    sec2 = SimpleNamespace(heading="s", prose="아래 그래프는 추이를 보여준다.",
                           charts=[{"type": "bar"}])
    assert _reconcile_visual_references(
        SimpleNamespace(sections=[sec2], embedded_map=None)) == 0


def test_topojson_runtime_has_local_fallback() -> None:
    """P2 — atlas 만 벤더링하면 소용없다. 런타임(topojson-client)도 로컬 폴백 필요.

    CDN 차단 시 `!window.topojson` 에서 maps.js 가 즉시 return 해 atlas 로컬
    폴백까지 도달조차 못 한다.
    """
    assert (_REPO / "src" / "templates" / "static" / "topojson-client.min.js").exists()
    synth = (_REPO / "src" / "agents" / "report_synthesizer.py").read_text(encoding="utf-8")
    assert '"topojson-client.min.js"' in synth, "STATIC_ASSETS 미등록"
    for name in ("freeform_essay.html", "reportage.html"):
        tpl = (_REPO / "src" / "templates" / "archetypes" / name).read_text(encoding="utf-8")
        assert "topojson-client.min.js" in tpl, f"{name}: 템플릿 폴백 미배선"
    charts = (_REPO / "src" / "templates" / "static" / "charts.js").read_text(encoding="utf-8")
    assert "topojson-client.min.js" in charts, "charts.js 동적 로더 폴백 미배선"


def test_heatmap_grid_viewbox_grows_with_columns() -> None:
    """P2 — 넓은 격자가 고정 720px viewBox 밖으로 잘리지 않는다.

    `cellW = max(56, …)` 는 11열부터 padL + xs*cellW 가 720 을 넘긴다. 가드도
    프롬프트도 열 수 상한을 두지 않으므로 폭이 따라 자라야 한다.
    """
    js = (_REPO / "src" / "templates" / "static" / "charts.js").read_text(encoding="utf-8")
    idx = js.find("function drawHeatmapGrid")
    assert idx > 0
    body = js[idx:idx + 2500]
    assert "const W = Math.max(720, padL + xs.length * cellW + padR)" in body, \
        "viewBox 폭이 열 수에 따라 자라지 않음 (넓은 격자 잘림)"
    # 산술 검산 — 3~20열에서 콘텐츠가 항상 viewBox 안에 든다
    pad_l, pad_r = 128, 14
    for n in range(2, 25):
        cell_w = max(56, (720 - pad_l - pad_r) // n)
        w = max(720, pad_l + n * cell_w + pad_r)
        assert pad_l + n * cell_w + pad_r <= w, f"{n}열에서 잘림"
