"""v8.5.5 — 사실수집 CLI 상한의 mode 인지 (2026-08-01 실사고 회귀).

**사고**: 장마감 브리핑 소급 발행이 ``context_analyst`` 300s 타임아웃 3연속으로
보고서 통째 실패 (``RuntimeError: claude CLI failed after 3 attempt(s):
timeout after 300s``). deep 사실수집은 웹검색을 여러 번 돌고 10K 토큰까지 쓰는데
상한이 fast 와 같은 평면 300s 였다.

**같은 결함의 절반은 이미 고쳐져 있었다** — 편집장(`narrative_composer`)은
v8.2.4 에서 정확히 같은 실패(deep 900s 초과 → minimal fallback, WRITE-AP-25)로
mode 별 상한(deep 1500s)을 받았다. 사실수집만 평면 상한으로 남아 있던 것.

가드:
  ① deep 사실수집 상한 > fast 상한 (평면 회귀 차단)
  ② fast/standard 는 기존 300s 유지 (무관한 경로 동작 불변)
  ③ 상한이 실제 ``asyncio.wait_for`` 에 배선 (상수만 있고 미사용 회귀 차단)
  ④ override 미설정 에이전트는 기존 기본값 그대로
"""

from __future__ import annotations

import re
from pathlib import Path

from src.agents.base import BaseAgent
from src.agents.context_analyst import ContextAnalyst
from src.agents.narrative_composer import NarrativeComposer

_BASE_SRC = (Path(__file__).resolve().parents[2] / "src" / "agents" / "base.py").read_text(
    encoding="utf-8"
)


def test_deep_fact_gathering_gets_more_time_than_fast() -> None:
    m = ContextAnalyst.CLI_TIMEOUT_BY_MODE
    assert m["deep"] > m["fast"], (
        "deep 사실수집이 fast 와 같은 상한 — 웹검색 다회 + 10K 토큰이 300s 를 "
        "넘기면 3회 재시도가 전부 죽고 보고서가 통째로 실패한다 (2026-08-01 실사고)"
    )
    assert m["deep"] >= 600.0, "deep 상한이 실측 초과분을 못 덮는다"


def test_fast_and_standard_keep_previous_ceiling() -> None:
    """무거운 deep 만 늘린다 — 나머지는 기존 동작 유지."""
    for mode in ("fast", "standard"):
        assert ContextAnalyst.CLI_TIMEOUT_BY_MODE[mode] == BaseAgent._CLI_TIMEOUT_S


def test_override_is_actually_wired_to_wait_for() -> None:
    """상한 상수를 만들어 놓고 wait_for 는 옛 상수를 쓰는 회귀 차단."""
    assert "timeout=self.cli_timeout_s" in _BASE_SRC, (
        "wait_for 가 override 를 안 본다 — 상한을 올려도 실제로는 300s 로 죽는다"
    )
    assert not re.search(r"timeout=self\._CLI_TIMEOUT_S\b", _BASE_SRC), (
        "옛 평면 상수가 wait_for 에 남아 있음"
    )


def test_context_analyst_sets_override_before_calling_cli(monkeypatch) -> None:
    """★ 실제 배선 — analyze() 가 CLI 를 부르기 *전에* mode 상한을 심어야 한다.

    맵만 선언하고 인스턴스에 안 꽂으면 런타임은 여전히 평면 300s 다 (사고 그대로).
    """
    import asyncio

    from src.config import Config
    from src.models import AnalysisRequest

    seen: dict[str, float] = {}

    async def _capture(self, context):  # type: ignore[no-untyped-def]
        seen["timeout"] = self.cli_timeout_s
        raise RuntimeError("stop-here")  # 실제 CLI 호출로 진행시키지 않는다

    monkeypatch.setattr(BaseAgent, "analyze", _capture)

    cfg = Config(_env_file=None)
    object.__setattr__(cfg, "anthropic_api_key", "")
    analyst = ContextAnalyst(cfg)

    for mode, expected in (("deep", 900.0), ("fast", 300.0)):
        seen.clear()
        req = AnalysisRequest(event_description="장마감 브리핑", mode=mode)
        try:
            asyncio.run(analyst.analyze(req))
        except RuntimeError:
            pass
        assert seen.get("timeout") == expected, (
            f"mode={mode}: CLI 호출 시점 상한이 {seen.get('timeout')} — "
            f"{expected} 여야 한다 (맵 선언만 하고 인스턴스에 미배선)"
        )


def test_default_agent_keeps_flat_ceiling() -> None:
    """override 를 안 세팅하는 에이전트는 기존 300s 그대로."""
    assert BaseAgent._cli_timeout_override is None
    agent = BaseAgent.__new__(BaseAgent)
    assert agent.cli_timeout_s == BaseAgent._CLI_TIMEOUT_S


def test_composer_still_has_its_own_mode_map() -> None:
    """편집장의 v8.2.4 mode 별 상한이 유지돼야 (두 단계가 같은 정책)."""
    assert NarrativeComposer.CLI_TIMEOUT_BY_MODE["deep"] > (
        NarrativeComposer.CLI_TIMEOUT_BY_MODE["fast"]
    )
