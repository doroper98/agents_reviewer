"""V6 Phase V6-5 — Codex 웹 verify 회귀 (T-6).

REFACTOR_V6_PLAN.md §4.4 T-6. codex 실웹검색은 모킹 (CI 결정적, 실연동은 VM).
검증: 웹검색 인자(--enable) 전달 / 프롬프트 웹verify 블록 / cited_urls 집계 / cap /
flag OFF 불변.
"""

from __future__ import annotations

import asyncio
import json

from src.agents.codex_critic import CodexCritic
from src.config import Config
from src.models import ComposedReport, ComposedSection, ContextAnalysis


def _cfg(**kw) -> Config:
    base = dict(enable_codex_critic=True, codex_bin="codex")
    base.update(kw)
    return Config(_env_file=None, **base)


def _report() -> ComposedReport:
    return ComposedReport(headline="h", sections=[ComposedSection(heading="s", prose="블랙웰 300 출시")])


def _stub(stdout: str, returncode: int = 0):
    async def _s(bin_path, prompt, image_paths=None, webverify=False):  # noqa: ANN001
        _s.seen_webverify = webverify
        _s.seen_prompt = prompt
        return stdout, "", returncode, 30
    _s.seen_webverify = None
    _s.seen_prompt = ""
    return _s


def _critic(config, *, call_stub=None) -> CodexCritic:
    c = CodexCritic(config)
    c._resolve_bin = lambda: "/usr/bin/codex"  # type: ignore[method-assign]
    if call_stub is not None:
        c._call_codex_cli = call_stub  # type: ignore[method-assign]
    return c


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# cmd / prompt — 웹검색 인자 + 블록
# --------------------------------------------------------------------------


def test_build_cmd_adds_websearch_args_when_webverify() -> None:
    critic = CodexCritic(_cfg())
    on = critic._build_cmd("/usr/bin/codex", webverify=True)
    off = critic._build_cmd("/usr/bin/codex", webverify=False)
    assert "--enable" in on and "web_search" in on
    assert "--enable" not in off  # OFF 면 불변


def test_prompt_has_webverify_block_with_cap() -> None:
    critic = CodexCritic(_cfg(codex_websearch_cap=3))
    p_on = critic._build_prompt(_report(), ContextAnalysis(), publication_date="", pre_flags=None, webverify=True)
    p_off = critic._build_prompt(_report(), ContextAnalysis(), publication_date="", pre_flags=None, webverify=False)
    assert "웹 verify" in p_on and "≤3" in p_on
    assert "웹 verify" not in p_off  # OFF byte-equal


# --------------------------------------------------------------------------
# critique() 통합 — flag 가 webverify 를 켠다
# --------------------------------------------------------------------------


def test_critique_passes_webverify_when_flag_on() -> None:
    clean = json.dumps({"verdict_status": "clean", "claims": []})
    stub = _stub(clean)
    critic = _critic(_cfg(enable_codex_webverify=True), call_stub=stub)
    _run(critic.critique(_report(), ContextAnalysis()))
    assert stub.seen_webverify is True
    assert "웹 verify" in stub.seen_prompt


def test_critique_no_webverify_when_flag_off() -> None:
    clean = json.dumps({"verdict_status": "clean", "claims": []})
    stub = _stub(clean)
    critic = _critic(_cfg(enable_codex_webverify=False), call_stub=stub)
    _run(critic.critique(_report(), ContextAnalysis()))
    assert stub.seen_webverify is False
    assert "웹 verify" not in stub.seen_prompt


# --------------------------------------------------------------------------
# cited_urls 집계 (T-6 — URL 추적)
# --------------------------------------------------------------------------


def test_cited_urls_aggregated_from_claims() -> None:
    verdict_json = json.dumps({
        "claims": [{
            "location": "s", "error_class": "unsourced_number", "quote": "블랙웰 300",
            "evidence_conflict": "웹 확인 결과 제품명은 B300",
            "source_urls": ["https://nvidia.com/b300"],
            "fix_instruction": "B300 으로 교정", "severity": "high",
        }],
    }, ensure_ascii=False)
    critic = _critic(_cfg(enable_codex_webverify=True), call_stub=_stub(verdict_json))
    v = _run(critic.critique(_report(), ContextAnalysis()))
    assert v.violation_count == 1
    assert "https://nvidia.com/b300" in v.cited_urls  # claim source_urls → cited_urls 집계
