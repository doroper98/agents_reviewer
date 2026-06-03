"""V6 Phase V6-4 — Codex 미학 검수 (vision) 회귀 (T-5).

REFACTOR_V6_PLAN.md §4.4 T-5. codex 비전 실호출은 모킹 (CI 결정적, 실연동은 VM).
검증: 이미지 경로 전달(-i) / 비주얼 verdict 파싱 / flag·이미지 degrade / 데이터 digest.
"""

from __future__ import annotations

import asyncio
import json

from src.agents.codex_critic import CodexCritic
from src.config import Config
from src.models import ComposedReport, ComposedSection


def _cfg(**kw) -> Config:
    base = dict(enable_codex_visual=True, codex_bin="codex")
    base.update(kw)
    return Config(_env_file=None, **base)


def _report() -> ComposedReport:
    return ComposedReport(
        headline="시장 브리핑",
        sections=[ComposedSection(
            heading="지표",
            prose="코스피 동향",
            charts=[{"type": "bar", "title": "지수 등락", "data": [
                {"label": "코스피", "value": 0.15}, {"label": "나스닥", "value": 0.8},
            ]}],
        )],
    )


def _critic(config, *, bin_path="/usr/bin/codex", call_stub=None) -> CodexCritic:
    c = CodexCritic(config)
    c._resolve_bin = lambda: bin_path  # type: ignore[method-assign]
    if call_stub is not None:
        c._call_codex_cli = call_stub  # type: ignore[method-assign]
    return c


def _stub(stdout: str, returncode: int = 0):
    async def _s(bin_path, prompt, image_paths=None):  # noqa: ANN001
        _s.seen_images = list(image_paths or [])
        _s.seen_prompt = prompt
        return stdout, "", returncode, 30
    _s.seen_images = []
    _s.seen_prompt = ""
    return _s


def _run(coro):
    return asyncio.run(coro)


_VISUAL_VERDICT = json.dumps({
    "verdict_status": "violations",
    "claims": [{
        "location": "외국인 순매도",
        "error_class": "chart_readability",
        "quote": "lollipop 1개 항목",
        "evidence_conflict": "데이터가 1개뿐이라 막대 비교 의미 없음",
        "fix_instruction": "항목 5개 이상으로 늘리거나 bar 로 교체",
        "severity": "medium",
    }],
}, ensure_ascii=False)


def test_visual_verdict_parsed_and_images_passed() -> None:
    stub = _stub(_VISUAL_VERDICT)
    critic = _critic(_cfg(), call_stub=stub)
    v = _run(critic.critique_visual(_report(), ["/tmp/a.png", "/tmp/b.png"]))
    assert v.verdict_status == "violations" and v.violation_count == 1
    assert v.claims[0].error_class == "chart_readability"
    assert v.model_label == "OpenAI Codex (vision)"
    assert stub.seen_images == ["/tmp/a.png", "/tmp/b.png"]  # -i 로 전달됨
    assert "차트 데이터 digest" in stub.seen_prompt  # 숫자 대조용 digest 포함


def test_build_cmd_appends_image_flags() -> None:
    critic = CodexCritic(_cfg())
    cmd = critic._build_cmd("/usr/bin/codex", ["/tmp/x.png", "/tmp/y.png"])
    assert cmd[-4:] == ["-i", "/tmp/x.png", "-i", "/tmp/y.png"]


def test_flag_off_skips() -> None:
    critic = _critic(_cfg(enable_codex_visual=False), call_stub=_stub(_VISUAL_VERDICT))
    v = _run(critic.critique_visual(_report(), ["/tmp/a.png"]))
    assert v.skipped and v.skip_reason == "flag_off"


def test_no_images_skips() -> None:
    critic = _critic(_cfg(), call_stub=_stub(_VISUAL_VERDICT))
    v = _run(critic.critique_visual(_report(), []))
    assert v.skipped and v.skip_reason == "no_images"


def test_codex_not_found_skips() -> None:
    critic = CodexCritic(_cfg())
    critic._resolve_bin = lambda: None  # type: ignore[method-assign]
    v = _run(critic.critique_visual(_report(), ["/tmp/a.png"]))
    assert v.skipped and v.skip_reason == "codex_not_found"


def test_report_visuals_skips_when_flag_off() -> None:
    critic = CodexCritic(_cfg(enable_codex_visual=False))
    v = _run(critic.critique_report_visuals(_report(), "/tmp/nonexistent.html"))
    assert v.skipped and v.skip_reason == "flag_off"
