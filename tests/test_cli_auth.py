"""v8.7.1 — Claude CLI 인증 만료 경고 + 사전 점검 회귀 테스트 (VM-AP-14).

2026-09-27 ~ 10-27 실사고: CLI OAuth 만료로 한 달간 브리핑이 전부 실패했는데,
텔레그램에는 200자에서 잘린 오류 원문만 가서 아무도 조치하지 못했다. 여기서는
① 만료 판별 ② 조치형 문구 ③ 비인증 실패 문구 byte-equal ④ ping 점검 파싱
⑤ 점검 시각 계산 ⑥ 만료 시에만 경고 ⑦ 브리핑 실패 경로 배선 을 결정적으로 검증한다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.scheduler import cli_auth_watch
from src.scheduler.cli_auth_watch import (
    AuthCheckSlot,
    check_time_before,
    clamp_lead,
    next_check,
    run_cli_auth_check_once,
)
from src.tools import cli_auth
from src.tools.cli_auth import (
    CLI_AUTH_FIX,
    CliAuthProbe,
    failure_message,
    is_cli_auth_error,
    probe_cli_auth,
)

# 2026-10-27 VM journal 실로그 그대로.
REAL_AUTH_ERROR = (
    '[context_analyst] claude CLI failed after 1 attempt(s): exit=1: Failed to '
    'authenticate. API Error: 401 {"type":"error","error":{"type":'
    '"authentication_error","message":"OAuth access token has expired. '
    'Re-authenticate to continue."},"request_id":"req_011CgRXCjZaNUv2H8tyxkAeF"}'
)
REAL_OVERLOAD_ERROR = (
    "[context_analyst] claude CLI failed after 3 attempt(s): exit=1: "
    "API Error: 529 Overloaded"
)


# ─── ① 판별 ──────────────────────────────────────────────────────


def test_detects_real_oauth_expiry() -> None:
    assert is_cli_auth_error(REAL_AUTH_ERROR)
    assert is_cli_auth_error(RuntimeError(REAL_AUTH_ERROR))


def test_detects_not_logged_in() -> None:
    assert is_cli_auth_error("Invalid API key · Please run /login")


def test_transient_and_empty_are_not_auth() -> None:
    assert not is_cli_auth_error(REAL_OVERLOAD_ERROR)
    assert not is_cli_auth_error("timeout after 300s")
    assert not is_cli_auth_error("")
    assert not is_cli_auth_error(None)


# ─── ②③ 문구 ─────────────────────────────────────────────────────


def test_failure_message_auth_has_recovery_commands() -> None:
    msg = failure_message("❌ 일일 브리핑 (2026-10-27) 생성 실패", RuntimeError(REAL_AUTH_ERROR))
    assert msg.startswith("❌ 일일 브리핑 (2026-10-27) 생성 실패 — Claude CLI 로그인 만료")
    assert "/login" in msg and "claude -p \"ping\"" in msg
    # 원문 JSON 은 싣지 않는다 (읽히지 않아 조치로 이어지지 않던 문제).
    assert "request_id" not in msg
    assert CLI_AUTH_FIX in msg
    assert len(msg) < 4096  # 텔레그램 한 메시지


def test_failure_message_other_errors_byte_equal() -> None:
    e = RuntimeError(REAL_OVERLOAD_ERROR + " " + "x" * 300)
    run_date = "2026-10-27"
    assert failure_message(f"❌ 일일 브리핑 ({run_date}) 생성 실패", e) == (
        f"❌ 일일 브리핑 ({run_date}) 생성 실패: {str(e)[:200]}"
    )
    assert failure_message("❌ 분석 실패", e) == f"❌ 분석 실패: {str(e)[:200]}"


# ─── ④ ping 점검 ─────────────────────────────────────────────────


class _FakeProc:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0,
                 hang: bool = False) -> None:
        self._out = stdout.encode()
        self._err = stderr.encode()
        self.returncode = returncode
        self._hang = hang
        self.killed = False

    async def communicate(self):
        if self._hang:
            # asyncio.sleep 이 아니라 영원히 안 끝나는 future 로 멈춘다 — 다른 테스트가
            # asyncio.sleep 을 전역 패치해도 타임아웃 경로를 결정적으로 탄다.
            await asyncio.get_running_loop().create_future()
        return self._out, self._err

    def kill(self) -> None:
        self.killed = True


def _patch_cli(monkeypatch, proc: _FakeProc, calls: list | None = None) -> None:
    monkeypatch.setattr(cli_auth.shutil, "which", lambda name: "/usr/bin/claude")

    async def fake_exec(*args, **kw):
        if calls is not None:
            calls.append((args, kw))
        return proc

    monkeypatch.setattr(cli_auth.asyncio, "create_subprocess_exec", fake_exec)


def test_probe_ok(monkeypatch) -> None:
    calls: list = []
    _patch_cli(monkeypatch, _FakeProc('{"type":"result","is_error":false,"result":"pong"}'), calls)
    probe = asyncio.run(probe_cli_auth())
    assert probe.ok and not probe.auth_expired
    args, kw = calls[0]
    assert args[1:] == ("-p", "ping", "--output-format", "json")
    # repo 루트(CLAUDE.md 자동 로드)가 아니라 중립 cwd 에서 돈다.
    assert kw["cwd"].endswith("agents_reviewer_cli_cwd")


def test_probe_auth_expired_envelope(monkeypatch) -> None:
    # 실 VM 출력: exit 0 이어도 envelope 의 is_error=true 로 실패를 알린다.
    out = (
        '{"type":"result","subtype":"success","is_error":true,"result":"Failed to '
        'authenticate. API Error: 401 {\\"type\\":\\"error\\",\\"error\\":{\\"type\\":'
        '\\"authentication_error\\",\\"message\\":\\"OAuth access token has expired.'
        ' Re-authenticate to continue.\\"}}"}'
    )
    _patch_cli(monkeypatch, _FakeProc(out, returncode=0))
    probe = asyncio.run(probe_cli_auth())
    assert not probe.ok and probe.auth_expired


def test_probe_other_failure_is_not_auth(monkeypatch) -> None:
    _patch_cli(monkeypatch, _FakeProc("", stderr="API Error: 529 Overloaded", returncode=1))
    probe = asyncio.run(probe_cli_auth())
    assert not probe.ok and not probe.auth_expired


def test_probe_timeout(monkeypatch) -> None:
    proc = _FakeProc("", hang=True)
    _patch_cli(monkeypatch, proc)
    probe = asyncio.run(probe_cli_auth(timeout_s=0.05))
    assert not probe.ok and not probe.auth_expired
    assert proc.killed and "timeout" in probe.detail, probe.detail


def test_probe_cli_missing(monkeypatch) -> None:
    monkeypatch.setattr(cli_auth.shutil, "which", lambda name: None)
    probe = asyncio.run(probe_cli_auth())
    assert not probe.ok and not probe.auth_expired


# ─── ⑤ 점검 시각 ─────────────────────────────────────────────────

KST = ZoneInfo("Asia/Seoul")
SLOTS = [
    AuthCheckSlot(label="일일 브리핑", briefing_time="06:00", tz_name="Asia/Seoul"),
    AuthCheckSlot(label="장마감 브리핑", briefing_time="18:30", tz_name="Asia/Seoul"),
]


def test_check_time_before_wraps_midnight() -> None:
    assert check_time_before("06:00", 60) == "05:00"
    assert check_time_before("00:30", 60) == "23:30"
    assert check_time_before("18:30", 45) == "17:45"


def test_clamp_lead() -> None:
    assert clamp_lead(0) == 5
    assert clamp_lead(60) == 60
    assert clamp_lead(10_000) == 720


@pytest.mark.parametrize(
    "now_hm, expect_day, expect_hm, expect_label",
    [
        ((4, 0), 27, (5, 0), "일일 브리핑"),
        ((5, 30), 27, (17, 30), "장마감 브리핑"),
        ((18, 0), 28, (5, 0), "일일 브리핑"),
    ],
)
def test_next_check_picks_earliest(now_hm, expect_day, expect_hm, expect_label) -> None:
    now = datetime(2026, 10, 27, *now_hm, tzinfo=KST)
    when, slot = next_check(SLOTS, 60, now=now)
    assert (when.day, when.hour, when.minute) == (expect_day, *expect_hm)
    assert slot.label == expect_label


# ─── ⑥ 만료일 때만 경고 ──────────────────────────────────────────


def _run_once(probe: CliAuthProbe, recipients: list[int]) -> list[tuple[int, str]]:
    sent: list[tuple[int, str]] = []

    async def send(chat_id: int, text: str) -> None:
        sent.append((chat_id, text))

    async def fake_probe() -> CliAuthProbe:
        return probe

    asyncio.run(run_cli_auth_check_once(
        slot=SLOTS[0], recipients_fn=lambda: recipients,
        send_text_fn=send, probe_fn=fake_probe,
    ))
    return sent


def test_expired_alerts_each_recipient_once() -> None:
    # 일일·장마감 둘 다 구독한 채팅은 한 번만 받는다.
    sent = _run_once(CliAuthProbe(ok=False, auth_expired=True), [111, 222, 111])
    assert [cid for cid, _ in sent] == [111, 222]
    assert "06:00 일일 브리핑이 실패합니다" in sent[0][1]
    assert "/login" in sent[0][1]


def test_ok_and_non_auth_failure_do_not_alert() -> None:
    assert _run_once(CliAuthProbe(ok=True), [111]) == []
    assert _run_once(CliAuthProbe(ok=False, detail="timeout after 90s"), [111]) == []


def test_watch_loop_without_slots_returns() -> None:
    async def send(chat_id: int, text: str) -> None:  # pragma: no cover
        raise AssertionError("must not send")

    asyncio.run(cli_auth_watch.run_cli_auth_watch_loop(
        slots=[], recipients_fn=lambda: [1], send_text_fn=send,
    ))


# ─── ⑦ 브리핑 실패 경로 배선 ────────────────────────────────────


class _FakeSubscribers:
    def list_all(self):
        return [(50717095, "deep")]

    def start_run(self, run_date, subscribers):
        return True

    def finish_run(self, run_date, succeeded, failed):
        self.result = (succeeded, failed)


class _AuthFailingOrchestrator:
    async def run_analysis(self, **kw):
        raise RuntimeError(REAL_AUTH_ERROR)


def test_daily_briefing_failure_sends_recovery_message() -> None:
    from src.scheduler.daily_briefing import _run_one_briefing_cycle

    sent: list[tuple[int, str]] = []

    async def send(chat_id: int, text: str) -> None:
        sent.append((chat_id, text))

    subs = _FakeSubscribers()
    asyncio.run(_run_one_briefing_cycle(
        orchestrator=_AuthFailingOrchestrator(), subscribers=subs,
        send_text_fn=send, send_document_fn=None,
        tz_name="Asia/Seoul", enabled=True,
    ))
    assert subs.result == (0, 1)
    last = sent[-1][1]
    assert "Claude CLI 로그인 만료" in last and "/login" in last
    assert "request_id" not in last
