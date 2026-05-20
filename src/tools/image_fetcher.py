"""Image metadata fetcher — og:image / og:title / og:description extraction.

v5.4.0 — 사진 데이터 수집. ContextAnalyst 가 ``sources`` 에 인용한 기사 URL 들의
HTML 을 fetch 해 OpenGraph / Twitter Card 메타태그에서 사진 정보를 추출한다.
composer 가 그 후보 풀에서 본문 흐름에 맞는 사진을 골라 hero_image / 섹션
images 로 emit. 보고서 본문은 모두 mono 톤 SVG 차트지만, hero/inline 사진은
FT/Economist 스타일로 컬러 그대로 렌더 + 캡션·credit (출처) 첨부.

[Public API]
    fetch_og_metadata(url, session) -> AvailableImage | None
    fetch_many_images(urls, *, max_count, per_url_timeout, total_timeout) -> list[AvailableImage]

[Graceful degradation]
- 어떤 URL 이 og:image 없거나 HTTP fail / timeout → 빈 항목 (composer 호출 영향 X)
- 전체 fetch timeout 초과 → 그때까지 모은 항목만 반환
- 외부 의존성 ImportError → 빈 list (운영자에게 warning, 보고서 진행)

[보안]
- 다운로드는 *메타데이터 HTML* 만. 이미지 자체는 다운로드 X, URL 만 참조.
- HTML 첫 64KB 까지만 읽음 (og 메타태그는 <head> 안에 있음).
- redirect 따라가지만 최대 3회 + 같은 도메인 안 (외부 spam 방지).

[비고]
- 외부 라이브러리 의존성 추가 X — stdlib regex 로 og 태그 파싱. 메이저 언론사
  (FT/NYT/조선/한겨레/Reuters 등) 의 og:image 형식은 매우 표준적이라 regex 로 충분.
- aiohttp 는 requirements.txt 에 이미 포함 (market_fetcher 와 공유).
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp

from src.models import AvailableImage

logger = logging.getLogger(__name__)


# ─── 도메인 → 표시명 매핑 ──────────────────────────────────────
# 메이저 언론사는 사람-친화 이름으로. 누락 시 도메인 자체를 사용.

_PUBLISHER_MAP: dict[str, str] = {
    # 영문 매체
    "ft.com": "FT",
    "nytimes.com": "NYT",
    "wsj.com": "WSJ",
    "bloomberg.com": "Bloomberg",
    "reuters.com": "Reuters",
    "economist.com": "The Economist",
    "theguardian.com": "The Guardian",
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "cnbc.com": "CNBC",
    "cnn.com": "CNN",
    "apnews.com": "AP",
    "washingtonpost.com": "Washington Post",
    "techcrunch.com": "TechCrunch",
    "scmp.com": "SCMP",
    "nikkei.com": "Nikkei",
    "asia.nikkei.com": "Nikkei Asia",
    # 한국 매체
    "chosun.com": "조선일보",
    "joongang.co.kr": "중앙일보",
    "donga.com": "동아일보",
    "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문",
    "yna.co.kr": "연합뉴스",
    "yonhapnews.co.kr": "연합뉴스",
    "mk.co.kr": "매일경제",
    "hankyung.com": "한국경제",
    "edaily.co.kr": "이데일리",
    "newsis.com": "뉴시스",
    "biz.chosun.com": "조선비즈",
}


def _publisher_from_url(url: str) -> str:
    """URL 도메인에서 publisher 표시명 추출."""
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if not netloc:
        return ""
    # ``www.`` / ``m.`` / ``mobile.`` 같은 일반적 prefix 제거
    for prefix in ("www.", "m.", "mobile.", "amp."):
        if netloc.startswith(prefix):
            netloc = netloc[len(prefix):]
    if netloc in _PUBLISHER_MAP:
        return _PUBLISHER_MAP[netloc]
    # 서브도메인 매핑 (e.g. ``edition.cnn.com`` → ``cnn.com``)
    parts = netloc.split(".")
    if len(parts) >= 2:
        base = ".".join(parts[-2:])
        if base in _PUBLISHER_MAP:
            return _PUBLISHER_MAP[base]
    return netloc  # fallback — raw 도메인


# ─── og 메타태그 파싱 ─────────────────────────────────────────
# regex 는 og:image / og:title / og:description / twitter:image 만 캐치.
# meta 태그의 property/name 순서, content 따옴표 종류 모두 허용.

_META_PATTERN = re.compile(
    r'<meta\s+[^>]*?'                                  # <meta + 임의 속성
    r'(?:property|name)\s*=\s*["\']([^"\']+)["\']'      # property="..." 또는 name="..."
    r'[^>]*?content\s*=\s*["\']([^"\']+)["\']'          # content="..."
    r'[^>]*?>',
    re.IGNORECASE | re.DOTALL,
)
_META_PATTERN_REVERSE = re.compile(
    r'<meta\s+[^>]*?'
    r'content\s*=\s*["\']([^"\']+)["\']'                # content 가 먼저 오는 케이스
    r'[^>]*?(?:property|name)\s*=\s*["\']([^"\']+)["\']'
    r'[^>]*?>',
    re.IGNORECASE | re.DOTALL,
)


def _parse_og_meta(html: str, base_url: str) -> dict[str, str]:
    """HTML 에서 og:* / twitter:* 메타태그 추출.

    Returns dict with optional keys: ``image``, ``title``, ``description``.
    image 는 절대 URL 로 변환 (urljoin) 되며 빈 문자열이면 누락.
    """
    if not html:
        return {}
    # 효율 — head 닫히면 그 뒤는 안 봄
    head_end = html.lower().find("</head>")
    snippet = html[: head_end + 7] if head_end > 0 else html[:65536]

    meta: dict[str, str] = {}
    for m in _META_PATTERN.finditer(snippet):
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        if key in ("og:image", "og:image:secure_url") and "image" not in meta:
            meta["image"] = val
        elif key in ("og:title",) and "title" not in meta:
            meta["title"] = val
        elif key in ("og:description",) and "description" not in meta:
            meta["description"] = val
        elif key in ("twitter:image", "twitter:image:src") and "image" not in meta:
            meta["image"] = val
        elif key in ("twitter:title",) and "title" not in meta:
            meta["title"] = val
        elif key in ("twitter:description",) and "description" not in meta:
            meta["description"] = val
    # 일부 사이트는 content 가 property 앞에 옴
    for m in _META_PATTERN_REVERSE.finditer(snippet):
        val = m.group(1).strip()
        key = m.group(2).strip().lower()
        if key in ("og:image", "og:image:secure_url") and "image" not in meta:
            meta["image"] = val
        elif key in ("og:title",) and "title" not in meta:
            meta["title"] = val
        elif key in ("og:description",) and "description" not in meta:
            meta["description"] = val
        elif key in ("twitter:image", "twitter:image:src") and "image" not in meta:
            meta["image"] = val

    # HTML entity unescape (e.g. "&amp;" → "&")
    for k in list(meta.keys()):
        meta[k] = unescape(meta[k])

    # image 가 상대 URL 이면 절대 URL 로
    if "image" in meta:
        img = meta["image"]
        if img.startswith("//"):
            meta["image"] = "https:" + img
        elif not img.startswith(("http://", "https://")):
            try:
                meta["image"] = urljoin(base_url, img)
            except Exception:
                meta.pop("image", None)
    return meta


# ─── HTTP fetch ───────────────────────────────────────────────


# 뉴스 사이트는 'bot' 시그너처 UA 를 403 으로 차단하는 경우 다수 (BBC / Reuters
# / 한겨레 운영 확인). 평범한 데스크탑 브라우저 UA + Accept 헤더로 위장 — robots.txt
# 위배 아님 (메타태그만 읽고 본문 / 기사 페이로드는 안 읽음, 64KB cap).
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
_FETCH_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "DNT": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


async def fetch_og_metadata(
    url: str,
    session: aiohttp.ClientSession,
    *,
    timeout_s: float = 5.0,
) -> AvailableImage | None:
    """단일 URL → AvailableImage. 실패 시 None.

    HTML 첫 64KB 만 읽음 (og 메타는 <head> 안). 5초 타임아웃.
    redirect 자동 추적. og:image 없으면 None.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with session.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=_FETCH_HEADERS,
        ) as resp:
            if resp.status != 200:
                logger.debug("[image_fetcher] %s HTTP %d", url, resp.status)
                return None
            # HEAD/Content-Type 검증 — HTML 만 (이미지 / PDF 직접 링크 차단)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "html" not in ctype and "xml" not in ctype:
                return None
            # 64KB cap — og 태그는 <head> 안에 있으니 충분
            chunk = await resp.content.read(65536)
            html = chunk.decode("utf-8", errors="replace") if chunk else ""
            final_url = str(resp.url)
    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
        logger.debug("[image_fetcher] %s fetch error: %s", url, e)
        return None
    except Exception as e:  # pragma: no cover  — 예상 못한 에러는 조용히 None
        logger.debug("[image_fetcher] %s unexpected error: %s", url, e)
        return None

    meta = _parse_og_meta(html, base_url=final_url)
    image = meta.get("image")
    if not image:
        return None

    return AvailableImage(
        source_url=url,
        image_url=image,
        title=meta.get("title", "")[:300],
        description=meta.get("description", "")[:500],
        publisher=_publisher_from_url(final_url),
    )


async def fetch_many_images(
    urls: list[str],
    *,
    max_count: int = 5,
    per_url_timeout: float = 5.0,
    total_timeout: float = 12.0,
) -> list[AvailableImage]:
    """병렬 fetch — 일부 실패해도 나머지 진행.

    Args:
        urls: ContextAnalysis.sources 등에서 가져온 URL list.
        max_count: 반환 list 의 최대 개수. composer 가 보는 후보 풀 크기.
        per_url_timeout: 각 URL fetch 의 timeout (초).
        total_timeout: 전체 wait timeout (초). 초과하면 그때까지 모은 항목만.

    Returns:
        AvailableImage list. og:image 가 있는 URL 만 (없으면 항목 자체 누락).
        모든 URL 실패하면 빈 list. composer 호출 흐름에 영향 없음.
    """
    if not urls:
        return []
    # 중복 제거 + max_count 의 2배까지만 시도 (실패 대비 여유)
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            unique.append(u)
    target_urls = unique[: max_count * 2]

    try:
        connector = aiohttp.TCPConnector(limit=8, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                fetch_og_metadata(u, session, timeout_s=per_url_timeout)
                for u in target_urls
            ]
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=total_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[image_fetcher] total timeout (%ss) — returning partial results",
                    total_timeout,
                )
                results = []
    except Exception as e:  # pragma: no cover — session 생성 자체 실패
        logger.warning("[image_fetcher] session error: %s", e)
        return []

    out: list[AvailableImage] = []
    for r in results:
        if isinstance(r, AvailableImage):
            out.append(r)
        elif isinstance(r, Exception):
            logger.debug("[image_fetcher] gather exception: %s", r)
        if len(out) >= max_count:
            break
    return out


# ─── v5.4.1 — 이미지 로컬 다운로드 + URL 치환 ─────────────────────
# Composer 가 emit 한 og:image URL 을 보고서 도메인 (Cloudflare Pages) 에서
# 직접 serve 하기 위한 helper. 두 가지 문제 동시 해소:
#   ① hotlink 차단 — 메이저 매체 (FT/Reuters/Bloomberg 등) CDN 이 외부 도메인
#     `<img src>` 의 referrer / origin 을 검증해 403 반환. 원본 보고서에서
#     이미지 깨져 보이는 v5.4.0 회귀의 원인.
#   ② 영구 보존 — 원본 URL 이 만료 / 변경되면 보고서 자체가 깨짐. 봇이
#     다운로드해 함께 업로드하면 보고서 자체로 self-contained.
#
# 파일명은 image URL 의 SHA256[:16] + Content-Type 기반 확장자 — 같은 URL 이
# 두 번 등장해도 한 번만 다운로드 (dedup). reports/img/<hash>.<ext> 에 저장하면
# Cloudflare Pages 업로드 시 reports 디렉토리 통째로 올라감.


import hashlib
import os
from pathlib import Path


_CTYPE_EXT_MAP: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
}


async def download_image_to_dir(
    url: str,
    dst_dir: str,
    *,
    session: aiohttp.ClientSession | None = None,
    timeout_s: float = 10.0,
    max_bytes: int = 12 * 1024 * 1024,  # 12 MB cap — 메이저 매체 og:image 충분
) -> str | None:
    """단일 image URL 을 dst_dir 에 다운로드. 반환은 *파일명만* (상대 경로).

    파일명 = SHA256(URL)[:16] + Content-Type 기반 확장자.
    같은 URL 이 이미 dst_dir 에 있으면 다운로드 안 하고 캐시된 파일명 반환.

    Args:
        url: og:image 절대 URL.
        dst_dir: 저장할 디렉토리 절대 경로 (없으면 자동 생성).
        session: 재사용할 aiohttp 세션 (없으면 매 호출 새로 만듦).
        timeout_s: HTTP timeout.
        max_bytes: 단일 이미지 최대 크기. 초과하면 abort.

    Returns:
        성공 시 *파일명 only* (e.g. "a3f5...c8.jpg"). 호출자가 보고서 HTML 의
        src 값으로 사용할 상대 경로. 실패 시 None — 호출자가 원본 URL 유지 또는
        figure 자체 제거 결정.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None

    Path(dst_dir).mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]

    # 캐시 hit — 이미 다운로드된 파일 (확장자 모름 → 스캔)
    for ext in _CTYPE_EXT_MAP.values():
        cached = os.path.join(dst_dir, f"{url_hash}{ext}")
        if os.path.exists(cached) and os.path.getsize(cached) > 0:
            return f"{url_hash}{ext}"

    own_session = session is None
    if own_session:
        connector = aiohttp.TCPConnector(limit=4, ttl_dns_cache=300)
        session = aiohttp.ClientSession(connector=connector)

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        # 이미지 fetch — referrer 보냄 (CDN 일부는 referrer 있어야 200, 없으면
        # 403). 메타 HTML fetch 와 달리 같은 매체 도메인을 referrer 로 보냄.
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
        except Exception:
            referer = ""

        headers = dict(_FETCH_HEADERS)
        headers["Accept"] = "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8"
        if referer:
            headers["Referer"] = referer

        async with session.get(url, timeout=timeout, allow_redirects=True, headers=headers) as resp:
            if resp.status != 200:
                logger.warning(
                    "[image_fetcher] download %s HTTP %d (skip)", url, resp.status,
                )
                return None
            ctype = (resp.headers.get("Content-Type") or "").lower().split(";")[0].strip()
            ext = _CTYPE_EXT_MAP.get(ctype)
            if ext is None:
                # 알 수 없는 type 이면 URL 의 확장자 추측 (메이저 매체는 대부분 jpg)
                from urllib.parse import urlparse as _up
                path_lower = _up(url).path.lower()
                for k_ext in _CTYPE_EXT_MAP.values():
                    if path_lower.endswith(k_ext):
                        ext = k_ext
                        break
                if ext is None:
                    logger.warning(
                        "[image_fetcher] %s: unknown content-type %r — skip", url, ctype,
                    )
                    return None

            # 본문 chunked read — max_bytes 초과 시 abort
            buf = bytearray()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    logger.warning(
                        "[image_fetcher] %s exceeds %d bytes (skip)", url, max_bytes,
                    )
                    return None
            if len(buf) < 1024:
                # 1KB 미만이면 placeholder / error page 일 가능성
                logger.warning(
                    "[image_fetcher] %s too small (%d bytes, skip)", url, len(buf),
                )
                return None
    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
        logger.warning("[image_fetcher] download %s error: %s", url, e)
        return None
    except Exception as e:  # pragma: no cover  — 예상 못한 에러는 조용히 fail
        logger.warning("[image_fetcher] download %s unexpected: %s", url, e)
        return None
    finally:
        if own_session and session is not None:
            await session.close()

    fname = f"{url_hash}{ext}"
    dst_path = os.path.join(dst_dir, fname)
    try:
        with open(dst_path, "wb") as f:
            f.write(bytes(buf))
    except OSError as e:
        logger.warning("[image_fetcher] write %s failed: %s", dst_path, e)
        return None

    logger.info("[image_fetcher] saved %s → %s (%d bytes)", url, fname, len(buf))
    return fname


async def localize_image_urls(
    image_urls: list[str],
    dst_dir: str,
    *,
    url_prefix: str = "img",
) -> dict[str, str]:
    """다수 image URL 을 병렬 다운로드 → URL → 상대경로 매핑 반환.

    Args:
        image_urls: composed_report 에 박힌 image_url 들의 list (중복 OK).
        dst_dir: 다운로드 대상 디렉토리 절대 경로.
        url_prefix: HTML 의 ``<img src>`` 에 박을 prefix. dst_dir 가
            ``reports/img/`` 면 ``url_prefix="img"`` → 보고서 HTML 에서
            ``src="img/<hash>.jpg"`` 로 참조 (HTML 도 reports/ 아래 있으므로).

    Returns:
        ``{원본 URL: 상대 경로}`` dict. 다운로드 실패한 URL 은 dict 에 X.
        호출자가 composed_report 의 image_url 을 이 dict 로 swap.
    """
    if not image_urls:
        return {}

    # 중복 제거
    unique = list(dict.fromkeys(u for u in image_urls if u))
    if not unique:
        return {}

    connector = aiohttp.TCPConnector(limit=4, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            download_image_to_dir(u, dst_dir, session=session, timeout_s=10.0)
            for u in unique
        ]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[image_fetcher] localize total timeout — partial result",
            )
            return {}

    mapping: dict[str, str] = {}
    for url, r in zip(unique, results):
        if isinstance(r, str) and r:
            mapping[url] = f"{url_prefix.rstrip('/')}/{r}"
        elif isinstance(r, Exception):
            logger.debug("[image_fetcher] localize gather exception: %s", r)
    return mapping


__all__ = [
    "AvailableImage",
    "fetch_og_metadata",
    "fetch_many_images",
    "download_image_to_dir",
    "localize_image_urls",
]
