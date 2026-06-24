"""v8.2.1 — CLI 호출 복원력 회귀.

2026-06-24 실연동 사고: context_analyst 가 Anthropic 과부하(HTTP 529 Overloaded)
한 번에 보고서 전체가 "unknown error" 로 실패. 두 결함:
  ① 일시적 서버 에러(529/429/5xx/timeout)에 재시도 없이 즉시 전체 실패.
  ② CLI v2 가 API 에러를 *stdout* 에 내보내는데 봇은 stderr 만 읽어 "unknown error".

본 테스트가 가드: 일시 에러 재시도 + 비일시 fast-fail + stdout 에러 감지 +
중립 cwd(54KB CLAUDE.md 자동로드 차단) + 마지막 에러가 *진짜* 메시지.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from src.agents.base import BaseAgent
from src.config import Config


def _agent() -> BaseAgent:
    return BaseAgent(
        name="context_analyst",
        role="상황 분석관",
        system_prompt="당신은 상황 분석관.",
        config=Config(_env_file=None),
    )


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# 재시도 루프 (_analyze_cli) — _run_cli_once 를 스텁
# --------------------------------------------------------------------------


def test_retry_on_transient_then_success(monkeypatch) -> None:
    """529(일시) 1회 실패 → 재시도 → 성공. 보고서가 살아난다."""
    agent = _agent()
    monkeypatch.setattr("src.agents.base.shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr("src.agents.base.asyncio.sleep", _noop_sleep)

    calls = {"n": 0}

    async def stub(claude_bin, full_prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            return "", "exit=1: API Error: 529 Overloaded", True
        return "분석 결과 JSON", None, False

    monkeypatch.setattr(agent, "_run_cli_once", stub)
    out = _run(agent._analyze_cli({"event_description": "x"}))
    assert out == "분석 결과 JSON"
    assert calls["n"] == 2  # 1차 실패 + 재시도 성공


def test_fast_fail_on_nontransient(monkeypatch) -> None:
    """비일시(인증·인자 오류)는 재시도하지 않고 즉시 중단 — 헛된 재시도 금지."""
    agent = _agent()
    monkeypatch.setattr("src.agents.base.shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr("src.agents.base.asyncio.sleep", _noop_sleep)

    calls = {"n": 0}

    async def stub(claude_bin, full_prompt):
        calls["n"] += 1
        return "", "exit=1: invalid model id", False

    monkeypatch.setattr(agent, "_run_cli_once", stub)
    with pytest.raises(RuntimeError) as ei:
        _run(agent._analyze_cli({"event_description": "x"}))
    assert calls["n"] == 1  # 단 1회 — fast fail
    assert "invalid model id" in str(ei.value)


def test_exhausts_then_raises_real_error(monkeypatch) -> None:
    """지속적 529 → 한도까지 재시도 후, '진짜' 에러로 raise ('unknown error' 아님)."""
    agent = _agent()
    monkeypatch.setattr("src.agents.base.shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr("src.agents.base.asyncio.sleep", _noop_sleep)

    calls = {"n": 0}

    async def stub(claude_bin, full_prompt):
        calls["n"] += 1
        return "", "exit=1: API Error: 529 Overloaded", True

    monkeypatch.setattr(agent, "_run_cli_once", stub)
    with pytest.raises(RuntimeError) as ei:
        _run(agent._analyze_cli({"event_description": "x"}))
    assert calls["n"] == BaseAgent._CLI_MAX_ATTEMPTS
    msg = str(ei.value)
    assert "529" in msg and "unknown error" not in msg
    assert f"after {BaseAgent._CLI_MAX_ATTEMPTS} attempt" in msg


def test_claude_not_found_raises_early(monkeypatch) -> None:
    agent = _agent()
    monkeypatch.setattr("src.agents.base.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError) as ei:
        _run(agent._analyze_cli({"event_description": "x"}))
    assert "claude CLI not found" in str(ei.value)


# --------------------------------------------------------------------------
# _run_cli_once — subprocess 레벨 (stdout 에러 감지 + cwd + clean 경로)
# --------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, input=None):  # noqa: A002 — asyncio API 시그니처
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass


def _patch_subprocess(monkeypatch, proc: _FakeProc, captured: dict):
    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return proc
    monkeypatch.setattr("src.agents.base.asyncio.create_subprocess_exec", fake_exec)


def test_stdout_api_error_detected_as_transient(monkeypatch) -> None:
    """529 가 stdout(+exit 0)으로 와도 잡아서 transient 로 분류 (회귀의 핵심)."""
    agent = _agent()
    captured: dict = {}
    _patch_subprocess(
        monkeypatch,
        _FakeProc(b'API Error: 529 {"type":"overloaded_error"}', b"", 0),
        captured,
    )
    raw, err, transient = _run(agent._run_cli_once("/usr/bin/claude", "프롬프트"))
    assert raw == ""
    assert err is not None and "529" in err
    assert transient is True
    # 중립 cwd 로 실행됐는지 (CLAUDE.md 자동로드 차단)
    assert captured["kwargs"].get("cwd"), "cwd 가 지정돼야 함 (CLAUDE.md 자동로드 차단)"
    assert "agents_reviewer" not in os.path.realpath(captured["kwargs"]["cwd"]) or \
        captured["kwargs"]["cwd"].startswith(tempfile.gettempdir())


def test_clean_response_returns_text(monkeypatch) -> None:
    agent = _agent()
    captured: dict = {}
    _patch_subprocess(monkeypatch, _FakeProc("분석 **결과**".encode(), b"", 0), captured)
    raw, err, transient = _run(agent._run_cli_once("/usr/bin/claude", "프롬프트"))
    assert err is None and transient is False
    assert raw == "분석 결과"  # ** 제거 확인


def test_nonzero_exit_nontransient(monkeypatch) -> None:
    agent = _agent()
    captured: dict = {}
    _patch_subprocess(monkeypatch, _FakeProc(b"", b"invalid argument", 2), captured)
    raw, err, transient = _run(agent._run_cli_once("/usr/bin/claude", "프롬프트"))
    assert raw == ""
    assert err is not None and "invalid argument" in err
    assert transient is False  # 인자 오류는 재시도 무의미


def test_cwd_is_neutral_empty_dir(monkeypatch) -> None:
    """cwd 가 repo 가 아닌 빈 임시 디렉터리 — CLAUDE.md 자동로드 차단 보장."""
    agent = _agent()
    captured: dict = {}
    _patch_subprocess(monkeypatch, _FakeProc(b"ok", b"", 0), captured)
    _run(agent._run_cli_once("/usr/bin/claude", "프롬프트"))
    cwd = captured["kwargs"]["cwd"]
    assert os.path.isdir(cwd)
    # repo 의 CLAUDE.md 가 그 디렉터리/상위에 없어야 (tempdir 하위라 안전)
    assert cwd.startswith(tempfile.gettempdir())


async def _noop_sleep(_seconds):
    return None
