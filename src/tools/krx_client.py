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
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

KRX_JSON_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"


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
            "[krx] KRX_ID/KRX_PW 미설정 — data.krx 로그인 불가 (선물·옵션·breadth skip). "
            "무료 data.krx.co.kr 계정 후 .env 에 KRX_ID/KRX_PW 설정."
        )
        return None

    try:
        new = auth.build_krx_session(kid, kpw)  # warmup + 로그인 핸드셰이크
    except Exception as e:  # pragma: no cover
        logger.warning("[krx] 로그인 예외: %s", e)
        return None
    if new is None:
        logger.warning("[krx] 로그인 실패 — 자격증명 확인(KRX_ID/KRX_PW).")
        return None
    auth.set_auth_session(new)
    return new


def _post_rows_sync(config: "Config | None", bld: str, params: dict) -> list[dict]:
    """인증 세션으로 getJsonData POST → output rows (sync). 실패 시 RuntimeError."""
    sess = ensure_session(config)
    if sess is None:
        raise RuntimeError("KRX 인증 세션 없음 (KRX_ID/KRX_PW 미설정 또는 로그인 실패)")
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
