"""VM-AP-13 재발 차단 — `.env` 의 미지원 키가 봇 기동을 막지 않는다 (v8.5.15).

2026-08-30 실사고: 운영자가 앞으로 쓸 증권사 API 키(`KIS_APP_KEY` /
`KIS_APP_SECRET`)를 VM `.env` 에 미리 적어둔 상태에서 systemd 재시작 →
pydantic-settings 기본값 `extra="forbid"` 가 `Config()` 생성을 통째로 실패시켜
서비스가 `status=1` 로 무한 auto-restart (봇 전면 정지). 같은 지점을 지나는
`scripts/patch_report.py` 등 CLI 도 전부 동일하게 죽었다.

미래에 쓸 키를 미리 적어두는 것은 정상 운영 행위다. 그 대가가 서비스 전면
정지여선 안 된다 — 모르는 키는 무시하고 뜬다.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

from tests.regression._pytest_compat import pytest

from src.config import Config


def _config_with_env(body: str) -> Config:
    """임시 디렉터리에 `.env` 를 쓰고 그 안에서 Config() 를 만든다."""
    d = tempfile.mkdtemp()
    pathlib.Path(d, ".env").write_text(body, encoding="utf-8")
    cwd = os.getcwd()
    try:
        os.chdir(d)
        return Config()
    finally:
        os.chdir(cwd)


def test_unknown_env_keys_do_not_block_startup() -> None:
    """실사고와 동일한 `.env` (KIS 키 2종) 로도 Config() 가 떠야 한다."""
    config = _config_with_env(
        "TELEGRAM_BOT_TOKEN=dummy-token\n"
        "KIS_APP_KEY=dummy-key\n"
        "KIS_APP_SECRET=dummy-secret\n"
    )
    assert config.telegram_bot_token == "dummy-token"


def test_arbitrary_future_env_key_is_ignored() -> None:
    """KIS 뿐 아니라 *어떤* 미지원 키든 기동을 막지 않는다 (클래스 차단)."""
    config = _config_with_env(
        "TELEGRAM_BOT_TOKEN=dummy-token\n"
        "SOME_FUTURE_VENDOR_KEY=1\n"
        "ANOTHER_UNSUPPORTED_THING=abc\n"
    )
    assert config.telegram_bot_token == "dummy-token"
    assert not hasattr(config, "some_future_vendor_key")


def test_declared_fields_still_load() -> None:
    """extra 무시가 *선언된* 필드 로딩을 망가뜨리지 않았는지 (회귀 방향 반대편)."""
    config = _config_with_env(
        "TELEGRAM_BOT_TOKEN=dummy-token\n"
        "WRANGLER_TIMEOUT_SEC=42\n"
        "UNKNOWN_KEY=x\n"
    )
    assert config.wrangler_timeout_sec == 42
