"""KRX 정보데이터시스템(data.krx.co.kr) 인증 JSON 접근 SSOT — v7.9.2.

derivatives_fetcher / breadth_fetcher 가 공유하는 KRX getJsonData 클라이언트.

⚠️ 2026-06 변경: data.krx.co.kr 의 getJsonData 가 **로그인 필수**로 바뀌었다(무로그인
POST 는 HTTP 400 + 본문 'LOGOUT', VM 실측 2026-06-17). 따라서 KRX 계정으로 로그인한
세션이 필요하다. pykrx 1.2.8 이 로그인 핸드셰이크(`build_krx_session` →
warmup → MDCCOMS001D1.cmd POST → 중복로그인 skipDup 처리)를 이미 구현하므로 그
세션을 재사용한다. 자격증명은 `Config.krx_id`/`krx_pw`(.env: KRX_ID/KRX_PW) 또는
환경변수에서 읽는다.

설계:
- pykrx 의 인증 세션(`auth.get_auth_session()`)을 쓰되, 요청은 우리 bld/params 로 직접
  POST(파라미터 제어 유지). 세션이 없거나 만료면 자격증명으로 로그인.
- 모든 호출은 sync(requests) → caller 가 ``asyncio.to_thread`` 로 감싸는 ``post_json_rows``
  async 래퍼 제공.
- 자격증명 없음·로그인 실패·pykrx 미설치는 *조용히* graceful — RuntimeError 를 던져
  fetcher 의 try/except 가 빈 snapshot + warning 으로 흡수(보고서 흐름 무영향).

v8.7.1 (VM-AP-15) — 로그인 실패를 *구분해서* 알린다. 2026-10-27 실사고: KRX 가
비밀번호 변경 주기 만료(오류코드 CD010)로 로그인을 거부했는데, pykrx 는 경고를 stdout 에
print 만 하고 None 을 돌려줘 봇 로그에는 "자격증명 확인" 만 남았다(원인 오도). 선물·옵션
·시장 폭이 빈 채로 장마감 브리핑이 나갔다. 이제
- pykrx 출력을 잡아 원인을 분류한다 (비밀번호 변경 필요 / 로그인 실패).
- 로그인은 락 하나로 직렬화하고, 실패하면 쿨다운 동안 재시도하지 않는다 — 한 보고서
  안에서 여러 스레드가 동시에 틀린 비밀번호로 로그인해 계정이 잠기는 것을 막는다.
- ``login_problem()`` 이 사용자용 조치 문구를 돌려줘 장마감 브리핑 메시지에 붙는다.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

KRX_JSON_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

# v8.7.1 — 로그인 실패 원인 → 조치 문구 (텔레그램에 그대로 나간다).
LOGIN_PROBLEM_MESSAGES: dict[str, str] = {
    # v8.7.3 — '90일 뒤 변경' 을 먼저 안내 (2026-10-27 실복구 경로, .env·재시작 불요).
    "password_change_required": (
        "KRX 비밀번호 변경 필요 (KRX 응답 CD010) → KRX 사이트에 로그인해 '90일 뒤 변경' 을 "
        "누르면 재시작 없이 복구. 비밀번호를 바꿨다면 .env 의 KRX_PW 갱신 후 "
        "sudo systemctl restart agents-reviewer.service"
    ),
    "login_failed": (
        "KRX 로그인 실패 → .env 의 KRX_ID·KRX_PW 확인 후 "
        "sudo systemctl restart agents-reviewer.service"
    ),
}
# 실패 후 재로그인 금지 시간. 틀린 비밀번호로 반복 로그인하면 계정이 잠길 수 있다.
LOGIN_FAIL_COOLDOWN_S = 600.0

_login_lock = threading.Lock()
_last_failure: tuple[float, str] | None = None  # (time.monotonic(), 원인 코드)


def classify_login_output(text: str) -> str:
    """pykrx 로그인 출력(stdout) → 원인 코드."""
    if any(m in text for m in ("비밀번호 변경", "패스워드 변경", "CD010")):
        return "password_change_required"
    return "login_failed"


def login_problem() -> str:
    """마지막 로그인 실패의 조치 문구. 성공했거나 시도 전이면 ""."""
    if _last_failure is None:
        return ""
    return LOGIN_PROBLEM_MESSAGES.get(_last_failure[1], "")


def _reset_login_state() -> None:
    """테스트용 — 실패 기록 초기화."""
    global _last_failure
    _last_failure = None


def _creds(config: "Config | None") -> tuple[str, str]:
    kid = (getattr(config, "krx_id", "") or os.getenv("KRX_ID") or "").strip()
    kpw = (getattr(config, "krx_pw", "") or os.getenv("KRX_PW") or "").strip()
    return kid, kpw


def ensure_session(config: "Config | None"):
    """pykrx 인증 KRXSession 보장. 없거나 만료면 자격증명으로 로그인.

    반환: 유효 세션 객체 | None(자격증명 없음/로그인 실패/pykrx 미설치).
    """
    try:
        from pykrx.website.comm import auth
    except Exception as e:  # pragma: no cover — pykrx 미설치
        logger.warning("[krx] pykrx import 실패: %s", e)
        return None

    sess = auth.get_auth_session()
    try:
        if sess is not None and sess.is_valid():
            return sess
    except Exception:
        pass

    kid, kpw = _creds(config)
    if not (kid and kpw):
        logger.warning(
            "[krx] KRX_ID/KRX_PW 미설정 — data.krx 로그인 불가 (지수는 Yahoo 폴백, 선물·옵션·breadth skip). "
            "무료 data.krx.co.kr 계정 후 .env 에 KRX_ID/KRX_PW 설정."
        )
        return None

    global _last_failure
    with _login_lock:
        # 기다리는 사이 다른 스레드가 로그인했으면 그 세션을 쓴다.
        sess = auth.get_auth_session()
        try:
            if sess is not None and sess.is_valid():
                return sess
        except Exception:
            pass
        if _last_failure is not None and (
            time.monotonic() - _last_failure[0] < LOGIN_FAIL_COOLDOWN_S
        ):
            return None  # 쿨다운 — 같은 실패를 반복하지 않는다

        # pykrx 는 실패 원인을 print 로만 알린다. 잡아서 분류하고 로그로 옮긴다.
        # (스레드들은 위 락에서 기다리므로 그동안 stdout 을 바꿔도 서로 섞이지 않는다.)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                new = auth.build_krx_session(kid, kpw)  # warmup + 로그인 핸드셰이크
        except Exception as e:  # pragma: no cover — 네트워크 예외는 원인 분류 대상 아님
            logger.warning("[krx] 로그인 예외: %s", e)
            return None
        out = buf.getvalue().strip()
        if out:
            logger.info("[krx] pykrx: %s", " / ".join(l.strip() for l in out.splitlines() if l.strip()))
        if new is None:
            reason = classify_login_output(out)
            _last_failure = (time.monotonic(), reason)
            logger.warning("[krx] %s", LOGIN_PROBLEM_MESSAGES[reason])
            return None
        _last_failure = None
        auth.set_auth_session(new)
        return new


def _post_rows_sync(config: "Config | None", bld: str, params: dict) -> list[dict]:
    """인증 세션으로 getJsonData POST → output rows (sync). 실패 시 RuntimeError."""
    sess = ensure_session(config)
    if sess is None:
        raise RuntimeError(
            login_problem() or "KRX 인증 세션 없음 (KRX_ID/KRX_PW 미설정 또는 로그인 실패)"
        )
    headers = sess.get_headers()  # User-Agent/Referer/Cookie(로그인 쿠키) 포함
    body = {"bld": bld, **params}
    resp = sess.session.post(KRX_JSON_URL, data=body, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"KRX {bld} HTTP {resp.status_code}")
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"KRX {bld} JSON 파싱 실패: {e} (body head={resp.text[:80]!r})")
    if not isinstance(data, dict):
        return []
    for key in ("OutBlock_1", "output", "block1"):
        rows = data.get(key)
        if isinstance(rows, list):
            return rows
    return []


async def post_json_rows(config: "Config | None", bld: str, params: dict) -> list[dict]:
    """``_post_rows_sync`` 의 async 래퍼 (requests 호출을 스레드로 오프로드)."""
    return await asyncio.to_thread(_post_rows_sync, config, bld, params)
