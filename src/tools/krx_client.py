"""KRX 정보데이터시스템(data.krx.co.kr) 공개 JSON 접근 SSOT — v7.9.1.

derivatives_fetcher / breadth_fetcher 가 공유하는 무로그인 getJsonData 클라이언트.

왜 별도 모듈인가: KRX WAF 는 *콜드* POST(쿠키 없이 바로 getJsonData)를 **HTTP 400**
으로 막는다. pykrx 가 동작하는 이유는 ① 풀 Chrome User-Agent ② 데이터 요청 전 페이지
GET 으로 ``JSESSIONID``/``WMONID`` 쿠키를 받는 *웜업* 때문이다(VM 실측 400 회귀,
2026-06-17). 두 fetcher 가 같은 메커니즘을 쓰도록 여기에 SSOT 로 둔다.

사용 패턴:
    async with aiohttp.ClientSession(...) as s:   # cookie_jar 기본 ON
        await warmup(s)                            # 쿠키 확보 (실패해도 진행)
        rows = await post_json_rows(s, bld, params)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

KRX_JSON_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
# 웜업: 쿠키(JSESSIONID/WMONID) 확보용 GET 대상. 데이터 메뉴 로더 + 루트.
KRX_WARMUP_URLS = (
    "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
    "https://data.krx.co.kr/",
)

# pykrx 검증 — 풀 Chrome UA(바로 'Mozilla/5.0' 만 쓰면 400).
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


async def warmup(session) -> bool:
    """데이터 요청 전 1회 — KRX 페이지 GET 으로 세션 쿠키 확보.

    aiohttp ClientSession 의 cookie_jar 에 Set-Cookie 가 적재돼 이후 POST 에 자동 첨부.
    실패해도 예외 없이 False (POST 단계에서 graceful degrade).
    """
    for url in KRX_WARMUP_URLS:
        try:
            async with session.get(url, headers={"User-Agent": _UA}) as resp:
                await resp.read()
                if resp.status == 200:
                    return True
        except Exception as e:  # pragma: no cover — 네트워크 차단 환경
            logger.debug("[krx] warmup GET 실패 (%s): %s", url, e)
    return False


async def post_json_rows(session, bld: str, params: dict) -> list[dict]:
    """getJsonData POST → output rows. KRX 는 output / OutBlock_1 / block1 중 하나로 반환."""
    body = {"bld": bld, **params}
    async with session.post(KRX_JSON_URL, data=body, headers=HEADERS) as resp:
        if resp.status != 200:
            raise RuntimeError(f"KRX {bld} HTTP {resp.status}")
        data = await resp.json(content_type=None)
    if not isinstance(data, dict):
        return []
    for key in ("OutBlock_1", "output", "block1"):
        rows = data.get(key)
        if isinstance(rows, list):
            return rows
    return []
