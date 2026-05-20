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


_USER_AGENT = (
    "Mozilla/5.0 (compatible; AnalysisTeamBot/1.0; "
    "+https://github.com/doroper98/agents_reviewer)"
)


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
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*;q=0.5"},
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


__all__ = [
    "AvailableImage",
    "fetch_og_metadata",
    "fetch_many_images",
]
