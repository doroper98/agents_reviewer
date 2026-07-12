"""v6.1.0 — github_mirror 회귀 테스트.

HTTP 호출 모킹 — enabled 게이팅 / raw URL 구성 / graceful degrade /
happy-path PUT 만 결정적 검증. 실 GitHub 연동은 운영 환경에서 PAT 로 별도 검증.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from src.tools.github_mirror import GitHubMirror, build_reports_index


def _cfg(**kw) -> SimpleNamespace:
    base = dict(
        github_mirror_token="",
        github_mirror_repo="",
        github_mirror_branch="main",
        github_mirror_path="reports",
        # v8.4.0 — osint_generator 번들 미러
        github_osint_token="",
        github_osint_repo="doroper98/osint_generator",
        github_osint_branch="main",
        github_osint_path="json",
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ─── enabled 게이팅 ──────────────────────────────────────────────


def test_disabled_without_token_or_repo() -> None:
    assert GitHubMirror(_cfg()).enabled is False
    assert GitHubMirror(_cfg(github_mirror_token="t")).enabled is False
    assert GitHubMirror(_cfg(github_mirror_repo="o/r")).enabled is False


def test_disabled_when_repo_missing_slash() -> None:
    m = GitHubMirror(_cfg(github_mirror_token="t", github_mirror_repo="noslash"))
    assert m.enabled is False


def test_enabled_with_token_and_repo() -> None:
    m = GitHubMirror(_cfg(github_mirror_token="t", github_mirror_repo="owner/repo"))
    assert m.enabled is True


# ─── raw URL 구성 ────────────────────────────────────────────────


def test_raw_url_with_prefix() -> None:
    m = GitHubMirror(_cfg(github_mirror_token="t", github_mirror_repo="owner/repo"))
    assert m.raw_url("analysis_x.md") == (
        "https://raw.githubusercontent.com/owner/repo/main/reports/analysis_x.md"
    )


def test_raw_url_without_prefix() -> None:
    m = GitHubMirror(
        _cfg(github_mirror_token="t", github_mirror_repo="o/r", github_mirror_path="")
    )
    assert m.raw_url("a.html") == "https://raw.githubusercontent.com/o/r/main/a.html"


def test_raw_url_custom_branch() -> None:
    m = GitHubMirror(
        _cfg(github_mirror_token="t", github_mirror_repo="o/r", github_mirror_branch="reports")
    )
    assert m.raw_url("a.html").startswith("https://raw.githubusercontent.com/o/r/reports/")


# ─── graceful degrade ───────────────────────────────────────────


def test_mirror_returns_empty_when_disabled() -> None:
    m = GitHubMirror(_cfg())
    assert asyncio.run(m.mirror(["/nonexistent.html"])) == ""


# ─── happy-path PUT (aiohttp 모킹) ───────────────────────────────


class _FakeResp:
    def __init__(self, status: int, json_data=None) -> None:
        self.status = status
        self._json = json_data or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._json

    async def text(self):
        return ""


class _FakeSession:
    """PUT 은 201, GET(sha 조회) 는 404 로 응답하는 최소 세션."""

    def __init__(self, *a, **kw) -> None:
        self.puts: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, **kw):
        return _FakeResp(404)

    def put(self, url, **kw):
        self.puts.append(url)
        return _FakeResp(201)


def test_mirror_happy_path(tmp_path) -> None:
    html = tmp_path / "analysis_20260606_x.html"
    md = tmp_path / "analysis_20260606_x.md"
    html.write_text("<html></html>", encoding="utf-8")
    md.write_text("# report", encoding="utf-8")

    m = GitHubMirror(_cfg(github_mirror_token="t", github_mirror_repo="owner/repo"))
    fake = _FakeSession()
    with patch("src.tools.github_mirror.aiohttp.ClientSession", return_value=fake):
        url = asyncio.run(m.mirror([str(html), str(md)]))

    # HTML raw URL 반환 + 두 파일 모두 PUT
    assert url == (
        "https://raw.githubusercontent.com/owner/repo/main/reports/analysis_20260606_x.html"
    )
    assert len(fake.puts) == 2


# ─── 보고서 목록 인덱스(README) ─────────────────────────────────


def test_build_reports_index(tmp_path) -> None:
    # 두 보고서 .md (헤더에 제목/분류) + 일부 산출물
    (tmp_path / "analysis_20260606_114653_aa.md").write_text(
        "# SpaceX 구글 컴퓨팅 임대\n\n**Category:** 기업·AI\n\n본문", encoding="utf-8"
    )
    (tmp_path / "analysis_20260606_114653_aa.json").write_text("{}", encoding="utf-8")
    (tmp_path / "analysis_20260606_114653_aa.bundle.json").write_text("{}", encoding="utf-8")
    (tmp_path / "analysis_20260501_090000_bb.md").write_text(
        "# 환율 급등 분석\n\n**Category:** 거시", encoding="utf-8"
    )

    md = build_reports_index(str(tmp_path))
    # 최신순 — 6/6 가 5/1 보다 먼저
    assert md.index("SpaceX") < md.index("환율 급등")
    # 제목·분류·상대링크
    assert "SpaceX 구글 컴퓨팅 임대" in md and "기업·AI" in md
    assert "[md](analysis_20260606_114653_aa.md)" in md
    assert "[json](analysis_20260606_114653_aa.json)" in md
    assert "[bundle](analysis_20260606_114653_aa.bundle.json)" in md
    # 날짜 파생 + 산출물 없는 항목은 링크 생략 (bb 는 json/bundle 없음)
    assert "2026-06-06 11:46" in md
    assert "[json](analysis_20260501_090000_bb.json)" not in md


def test_build_reports_index_limit(tmp_path) -> None:
    for i in range(5):
        (tmp_path / f"analysis_2026060{i}_090000_x.md").write_text(
            f"# 보고서{i}", encoding="utf-8"
        )
    md = build_reports_index(str(tmp_path), limit=2)
    assert "총 2건" in md
    assert "보고서4" in md and "보고서3" in md and "보고서2" not in md


def test_mirror_skips_missing_files(tmp_path) -> None:
    html = tmp_path / "a.html"
    html.write_text("<html></html>", encoding="utf-8")
    m = GitHubMirror(_cfg(github_mirror_token="t", github_mirror_repo="o/r"))
    fake = _FakeSession()
    with patch("src.tools.github_mirror.aiohttp.ClientSession", return_value=fake):
        url = asyncio.run(m.mirror([str(html), str(tmp_path / "missing.md")]))
    assert url.endswith("/a.html")
    assert len(fake.puts) == 1


# ─── v8.4.0 osint_generator 번들 미러 ────────────────────────────


def test_for_osint_reads_osint_config() -> None:
    m = GitHubMirror.for_osint(_cfg(github_osint_token="ot"))
    assert m.enabled is True
    assert m._repo == "doroper98/osint_generator"
    assert m.path_prefix == "json"
    assert m._repo_path("analysis_x.bundle.json") == "json/analysis_x.bundle.json"


def test_for_osint_disabled_without_any_token() -> None:
    # osint 토큰도 mirror 토큰도 없으면 graceful skip
    assert GitHubMirror.for_osint(_cfg()).enabled is False


def test_for_osint_falls_back_to_mirror_token() -> None:
    # osint 전용 토큰이 비면 mirror 토큰으로 폴백 (같은 PAT 양쪽 권한 시)
    m = GitHubMirror.for_osint(_cfg(github_mirror_token="mtok"))
    assert m.enabled is True
    assert m._token == "mtok"


def test_for_osint_prefers_osint_token() -> None:
    m = GitHubMirror.for_osint(_cfg(github_osint_token="ot", github_mirror_token="mtok"))
    assert m._token == "ot"


def test_push_files_returns_success_count(tmp_path) -> None:
    b1 = tmp_path / "analysis_a.bundle.json"
    b2 = tmp_path / "analysis_b.bundle.json"
    b1.write_text("{}", encoding="utf-8")
    b2.write_text("{}", encoding="utf-8")
    m = GitHubMirror.for_osint(_cfg(github_osint_token="ot"))
    fake = _FakeSession()
    with patch("src.tools.github_mirror.aiohttp.ClientSession", return_value=fake):
        n = asyncio.run(m.push_files([str(b1), str(b2), str(tmp_path / "missing.json")]))
    assert n == 2
    # json/ prefix 경로로 PUT
    assert all("/contents/json/" in u for u in fake.puts)


def test_push_files_disabled_returns_zero(tmp_path) -> None:
    b1 = tmp_path / "analysis_a.bundle.json"
    b1.write_text("{}", encoding="utf-8")
    m = GitHubMirror.for_osint(_cfg())  # 토큰 없음 → disabled
    assert asyncio.run(m.push_files([str(b1)])) == 0
