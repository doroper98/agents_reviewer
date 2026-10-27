"""v8.7.1 — KRX 로그인 실패 원인 구분 + 재시도 억제 회귀 테스트 (VM-AP-15).

2026-10-27 실사고: KRX 가 비밀번호 변경 주기 만료(CD010)로 로그인을 거부했다. pykrx 는
원인을 print 만 하고 None 을 돌려줘 봇 로그엔 "자격증명 확인" 만 남았고, 선물·옵션·
시장 폭이 빈 채로 장마감 브리핑이 나갔다. 한 보고서 안에서 여러 스레드가 동시에 같은
실패 로그인을 반복하기도 했다(계정 잠금 위험).
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from pykrx.website.comm import auth

from src.tools import krx_client
from src.tools.krx_client import (
    _post_rows_sync,
    classify_login_output,
    ensure_session,
    login_problem,
)

# pykrx 1.2.9 auth.login_krx / build_krx_session 이 실제로 찍는 문구 (VM 화면 그대로).
CD010_OUTPUT = (
    "KRX 로그인 시도...\n"
    "  로그인 ID: someone\n"
    "⚠️ KRX 비밀번호 변경이 필요합니다.\n"
    "   오류 메시지: 패스워드 변경 필요\n"
    "   https://www.krx.co.kr 에서 비밀번호를 변경한 후 다시 시도하세요.\n"
    "KRX 로그인 실패: 자격 증명을 확인하세요.\n"
)
BAD_PW_OUTPUT = "KRX 로그인 시도...\n  로그인 ID: someone\nKRX 로그인 실패: 자격 증명을 확인하세요.\n"

CFG = SimpleNamespace(krx_id="someone", krx_pw="pw")


class _Sess:
    def is_valid(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    krx_client._reset_login_state()
    holder: dict = {"sess": None}
    monkeypatch.setattr(auth, "get_auth_session", lambda: holder["sess"])
    monkeypatch.setattr(auth, "set_auth_session", lambda s: holder.__setitem__("sess", s))
    yield holder
    krx_client._reset_login_state()


def _fake_build(output: str, result, calls: list):
    def build(kid, kpw):
        calls.append((kid, kpw))
        print(output, end="")
        return result
    return build


def test_classify_login_output() -> None:
    assert classify_login_output(CD010_OUTPUT) == "password_change_required"
    assert classify_login_output(BAD_PW_OUTPUT) == "login_failed"
    assert classify_login_output("") == "login_failed"


def test_password_expiry_is_named_and_not_printed(monkeypatch, capsys) -> None:
    calls: list = []
    monkeypatch.setattr(auth, "build_krx_session", _fake_build(CD010_OUTPUT, None, calls))
    assert ensure_session(CFG) is None
    msg = login_problem()
    assert "비밀번호 변경 필요" in msg and "KRX_PW" in msg and "systemctl restart" in msg
    assert "90일 뒤 변경" in msg  # v8.7.3 — 재시작 없는 복구 경로를 먼저 안내
    # pykrx 출력은 stdout 이 아니라 로그로 옮겨진다.
    assert capsys.readouterr().out == ""


def test_failed_login_is_not_retried_during_cooldown(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(auth, "build_krx_session", _fake_build(BAD_PW_OUTPUT, None, calls))
    assert ensure_session(CFG) is None
    assert ensure_session(CFG) is None
    assert len(calls) == 1  # 두 번째는 쿨다운으로 로그인 시도 자체를 안 한다
    assert "KRX 로그인 실패" in login_problem()


def test_retry_after_cooldown_and_success_clears_problem(monkeypatch, _clean) -> None:
    calls: list = []
    monkeypatch.setattr(auth, "build_krx_session", _fake_build(CD010_OUTPUT, None, calls))
    ensure_session(CFG)
    # 쿨다운이 지난 것으로 만든다.
    krx_client._last_failure = (time.monotonic() - krx_client.LOGIN_FAIL_COOLDOWN_S - 1,
                                "password_change_required")
    good = _Sess()
    monkeypatch.setattr(auth, "build_krx_session", _fake_build("KRX 로그인 완료.\n", good, calls))
    assert ensure_session(CFG) is good
    assert login_problem() == ""
    assert _clean["sess"] is good


def test_concurrent_callers_log_in_once(monkeypatch) -> None:
    calls: list = []

    def slow_fail(kid, kpw):
        calls.append(kid)
        time.sleep(0.05)
        print(CD010_OUTPUT, end="")
        return None

    monkeypatch.setattr(auth, "build_krx_session", slow_fail)
    threads = [threading.Thread(target=ensure_session, args=(CFG,)) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_missing_credentials_is_not_a_problem(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(auth, "build_krx_session", _fake_build("", None, calls))
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    assert ensure_session(SimpleNamespace(krx_id="", krx_pw="")) is None
    assert calls == [] and login_problem() == ""  # 의도적으로 끈 상태 — 경고 대상 아님


def test_post_raises_with_actionable_reason(monkeypatch) -> None:
    monkeypatch.setattr(auth, "build_krx_session", _fake_build(CD010_OUTPUT, None, []))
    with pytest.raises(RuntimeError, match="비밀번호 변경 필요"):
        _post_rows_sync(CFG, "dbms/MDC/STAT/standard/MDCSTAT01501", {})


def test_market_briefing_line(monkeypatch) -> None:
    from src.scheduler.market_briefing import _krx_warning_line

    assert _krx_warning_line() == ""
    monkeypatch.setattr(auth, "build_krx_session", _fake_build(CD010_OUTPUT, None, []))
    ensure_session(CFG)
    line = _krx_warning_line()
    assert line.startswith("\n⚠️ 선물·옵션·시장 폭 데이터 빠짐 — KRX 비밀번호 변경 필요")
