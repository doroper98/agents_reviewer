"""GitHub raw mirror — 보고서 산출물을 공개 GitHub repo 에 미러.

v6.1.0 — 보고서(.html / .md / .json / .bundle.json)는 Cloudflare Pages
(``analysis-reports.pages.dev``) 에 배포된다. 그런데 다른 AI(특히 Claude Code
on the web 같은 *샌드박스 컨테이너*)는 사전 허용목록(egress allowlist)에 있는
호스트로만 나갈 수 있고, 그 목록에 ``*.pages.dev`` 는 보통 없다 — 프록시가
요청을 서버에 보내기도 전에 ``403 host_not_allowed`` 로 막아 텔레그램 링크를
열어볼 수 없다. 반면 ``github.com`` / ``raw.githubusercontent.com`` 은 대부분의
샌드박스 허용목록에 포함된다.

그래서 동일 파일을 공개 GitHub repo 에도 push 하고, 텔레그램 메시지에
``raw.githubusercontent.com/...`` 링크를 함께 실어준다. 받는 쪽 AI 는 설정
변경 없이 보고서를 바로 읽을 수 있다.

[Public API]
    GitHubMirror(config).enabled -> bool
    await GitHubMirror(config).mirror(filepaths) -> str   # raw HTML url 또는 ""

[Graceful degradation]
- 토큰/repo 미설정 → ``enabled`` False, 호출부가 skip (Cloudflare 흐름 불변)
- HTTP fail / 네트워크 차단 / 예외 → warning 로그 + "" 반환 (보고서 정상 진행)
- 일부 파일만 성공해도 HTML 이 올라갔으면 raw HTML base url 반환

[보안]
- PAT(``GITHUB_MIRROR_TOKEN``) 는 *공개* repo 에 Contents 쓰기 권한만 있으면 됨
  (fine-grained PAT 의 단일 repo Contents: read/write 권장). ``.env`` 에만 보관,
  git 커밋 금지.
- 미러 대상은 이미 공개 배포되는 보고서 산출물뿐. 비공개 데이터 없음.

[비고]
- 외부 라이브러리 의존성 추가 X — aiohttp 는 requirements.txt 에 이미 포함.
- GitHub Contents API (PUT /repos/{repo}/contents/{path}) 파일 단위 업로드.
  파일이 이미 있으면(patch 재발행) 기존 sha 를 GET 으로 받아 update.
"""

from __future__ import annotations

import asyncio
import base64
import glob
import logging
import os
import re
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

_API_ROOT = "https://api.github.com"
_RAW_ROOT = "https://raw.githubusercontent.com"
_TIMEOUT = aiohttp.ClientTimeout(total=20)


# ─── 보고서 목록(README) 인덱스 빌더 ─────────────────────────────
# 파일명(analysis_<id>)만으로는 무슨 보고서인지 안 보인다. reports/ 폴더에
# 제목·날짜·링크 표를 담은 README.md 를 생성해 같이 미러 — GitHub 이 폴더
# 화면 아래에 자동 렌더한다. 제목은 .md 첫 헤딩에서 싸게 추출(큰 JSON 안 읽음).

def _report_id_from_md(path: str) -> str:
    base = os.path.basename(path)
    if base.startswith("analysis_") and base.endswith(".md"):
        return base[len("analysis_"):-len(".md")]
    return ""


def _date_from_report_id(rid: str) -> str:
    m = re.match(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})", rid)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}"
    return ""


def _title_category_from_md(path: str) -> tuple[str, str]:
    """보고서 .md 의 첫 헤딩(제목) + Category 줄을 헤더 일부만 읽어 추출."""
    title, category = "", ""
    try:
        with open(path, encoding="utf-8") as f:
            for _ in range(15):
                line = f.readline()
                if not line:
                    break
                s = line.strip()
                if not title and s.startswith("# "):
                    title = s[2:].strip()
                elif s.startswith("**Category:**"):
                    category = s.replace("**Category:**", "").strip()
                if title and category:
                    break
    except Exception:
        pass
    return title, category


def _md_cell(s: str) -> str:
    """markdown 표 셀 안전화 — 파이프/줄바꿈 이스케이프."""
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def build_reports_index(reports_dir: str, *, limit: int | None = None) -> str:
    """reports/analysis_*.md 를 스캔해 제목·날짜·링크 markdown 표(README) 생성.

    최신순(파일명=시간순) 정렬. 링크는 같은 폴더 상대경로 — GitHub 렌더 시
    md/json/bundle 로 바로 이동. limit 지정 시 최신 N건만.
    """
    mds = sorted(glob.glob(os.path.join(reports_dir, "analysis_*.md")), reverse=True)
    if limit:
        mds = mds[:limit]
    lines = [
        "# 분석 보고서 목록",
        "",
        f"> 자동 생성 (agents_reviewer). 총 {len(mds)}건 · 최신순. "
        "각 보고서는 md(본문) · json(전체 덤프) · bundle(영상용) 3종.",
        "",
        "| 날짜(KST) | 제목 | 분류 | 파일 |",
        "|---|---|---|---|",
    ]
    for md in mds:
        rid = _report_id_from_md(md)
        if not rid:
            continue
        stem = f"analysis_{rid}"
        title, category = _title_category_from_md(md)
        date = _date_from_report_id(rid)
        # v8.0.0 — 르포는 리스트 제목에 [르포] 배지. report_format 은 json 의 request 에.
        badge = ""
        jp = os.path.join(reports_dir, f"{stem}.json")
        if os.path.exists(jp):
            try:
                import json as _json
                with open(jp, encoding="utf-8") as _jf:
                    _d = _json.load(_jf)
                if (_d.get("request") or {}).get("report_format") == "reportage":
                    badge = "[르포] "
            except Exception:
                pass
        links = [f"[md]({stem}.md)"]
        if os.path.exists(jp):
            links.append(f"[json]({stem}.json)")
        if os.path.exists(os.path.join(reports_dir, f"{stem}.bundle.json")):
            links.append(f"[bundle]({stem}.bundle.json)")
        lines.append(
            f"| {date} | {badge}{_md_cell(title) or rid} | {_md_cell(category)} | {' · '.join(links)} |"
        )
    lines.append("")
    return "\n".join(lines)


class GitHubMirror:
    """보고서 산출물을 공개 GitHub repo 로 미러하는 graceful 헬퍼."""

    def __init__(
        self,
        config: "Config",
        *,
        token: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        prefix: str | None = None,
    ) -> None:
        # 명시 override 가 있으면 그 값, 없으면 github_mirror_* config 를 읽는다.
        # override 는 osint_generator 같은 *두 번째* 미러 타깃을 위한 것.
        self._token = (
            token if token is not None else getattr(config, "github_mirror_token", "") or ""
        ).strip()
        self._repo = (
            repo if repo is not None else getattr(config, "github_mirror_repo", "") or ""
        ).strip().strip("/")
        _branch = branch if branch is not None else getattr(config, "github_mirror_branch", "") or "main"
        self._branch = (_branch or "main").strip() or "main"
        # repo 안에서 보고서를 둘 경로 prefix (예: "reports"). 빈 값이면 repo 루트.
        _prefix = prefix if prefix is not None else getattr(config, "github_mirror_path", "") or ""
        self._prefix = (_prefix or "").strip().strip("/")

    @classmethod
    def for_osint(cls, config: "Config") -> "GitHubMirror":
        """osint_generator(영상 파이프라인) repo 로 번들을 미러하는 변형.

        github_osint_* config 를 읽되, 토큰이 비면 github_mirror_token 으로 폴백
        (같은 PAT 가 양쪽 접근 권한을 가지는 경우). 토큰/repo 미설정 시 ``enabled``
        False → 호출부 graceful skip.
        """
        token = (getattr(config, "github_osint_token", "") or "").strip()
        if not token:
            token = (getattr(config, "github_mirror_token", "") or "").strip()
        return cls(
            config,
            token=token,
            repo=getattr(config, "github_osint_repo", "") or "",
            branch=getattr(config, "github_osint_branch", "") or "main",
            prefix=getattr(config, "github_osint_path", "") or "",
        )

    @property
    def enabled(self) -> bool:
        """토큰과 repo(owner/name) 가 모두 설정됐을 때만 동작."""
        return bool(self._token and self._repo and "/" in self._repo)

    @property
    def path_prefix(self) -> str:
        """repo 안 보고서 경로 prefix. 빈 값이면 repo 루트(이 경우 README 인덱스
        미생성 — 루트 README 덮어쓰기 방지)."""
        return self._prefix

    def _repo_path(self, filename: str) -> str:
        """repo 안에서의 파일 경로 (prefix 적용)."""
        return f"{self._prefix}/{filename}" if self._prefix else filename

    def raw_url(self, filename: str) -> str:
        """주어진 파일명의 raw.githubusercontent.com URL."""
        return f"{_RAW_ROOT}/{self._repo}/{self._branch}/{self._repo_path(filename)}"

    async def mirror(self, filepaths: list[str]) -> str:
        """파일들을 GitHub repo 에 push. HTML 미러 성공 시 그 raw URL 반환.

        graceful — 비활성/실패 시 "" 반환. 첫 파일(HTML)이 성공해야 raw URL 을
        돌려준다 (텔레그램은 그 base 에서 .md/.bundle.json 을 파생).
        """
        if not self.enabled:
            return ""

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agents-reviewer-mirror",
        }
        html_raw_url = ""
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=headers) as session:
                for fp in filepaths:
                    if not fp or not os.path.isfile(fp):
                        continue
                    filename = os.path.basename(fp)
                    ok = await self._put_file(session, fp, filename)
                    if ok and filename.endswith(".html"):
                        html_raw_url = self.raw_url(filename)
        except Exception as e:  # 네트워크 차단·예외 → 보고서 진행 우선
            logger.warning("[github_mirror] mirror failed: %s", e)
            return ""

        if html_raw_url:
            logger.info("[github_mirror] mirrored to %s", html_raw_url)
        return html_raw_url

    async def push_files(self, filepaths: list[str]) -> int:
        """파일들을 repo 에 push 하고 성공 개수를 반환. HTML raw url 을 돌려주는
        ``mirror`` 와 달리 산출물 종류에 무관하게 순수 업로드만 한다 (osint 번들
        미러용). graceful — 비활성/실패 시 0.
        """
        if not self.enabled:
            return 0

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agents-reviewer-mirror",
        }
        ok_count = 0
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=headers) as session:
                for fp in filepaths:
                    if not fp or not os.path.isfile(fp):
                        continue
                    if await self._put_file(session, fp, os.path.basename(fp)):
                        ok_count += 1
        except Exception as e:  # 네트워크 차단·예외 → 보고서 진행 우선
            logger.warning("[github_mirror] push_files failed: %s", e)
            return ok_count
        return ok_count

    async def _put_file(
        self, session: aiohttp.ClientSession, filepath: str, filename: str
    ) -> bool:
        """파일 1개를 Contents API 로 업로드/갱신. 성공 True."""
        path = self._repo_path(filename)
        url = f"{_API_ROOT}/repos/{self._repo}/contents/{path}"
        try:
            with open(filepath, "rb") as f:
                content_b64 = base64.b64encode(f.read()).decode("ascii")

            body: dict[str, str] = {
                "message": f"mirror {filename}",
                "content": content_b64,
                "branch": self._branch,
            }
            # 이미 존재하면 update 를 위해 기존 sha 필요 (patch 재발행 케이스).
            existing_sha = await self._get_sha(session, url)
            if existing_sha:
                body["sha"] = existing_sha

            async with session.put(url, json=body) as resp:
                if resp.status in (200, 201):
                    return True
                detail = (await resp.text())[:300]
                logger.warning(
                    "[github_mirror] PUT %s -> HTTP %s: %s", path, resp.status, detail
                )
                return False
        except Exception as e:
            logger.warning("[github_mirror] PUT %s failed: %s", path, e)
            return False

    async def _get_sha(self, session: aiohttp.ClientSession, contents_url: str) -> str:
        """파일이 이미 있으면 그 blob sha, 없으면 "" (404)."""
        try:
            async with session.get(
                contents_url, params={"ref": self._branch}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sha = data.get("sha", "") if isinstance(data, dict) else ""
                    return sha or ""
                return ""
        except Exception:
            return ""


async def mirror_report_files(config: "Config", filepaths: list[str]) -> str:
    """편의 함수 — GitHubMirror 를 생성해 미러. raw HTML url 또는 ""."""
    return await GitHubMirror(config).mirror(filepaths)
