"""Claude CLI 구독 인증 만료 판별 + 조치형 경고 (v8.7.1, VM-AP-14).

봇은 Claude Code CLI 구독 플랜으로 돈다 (CLAUDE.md '운영 모드 SSOT'). CLI 의 OAuth
토큰이 만료되면 봇·텔레그램은 멀쩡한데 **모든 LLM 호출이 401** 로 실패한다.

2026-09-27 ~ 10-27 실사고: 한 달 동안 아침 브리핑·장마감 브리핑이 전부 실패했는데
아무도 몰랐다. 봇은 매번 ``❌ 일일 브리핑 생성 실패: [context_analyst] claude CLI
failed ... 401 {"type":"error",...`` 를 보냈지만, 200자에서 잘린 오류 원문(JSON)이라
*무엇을 해야 하는지* 읽히지 않았다 (7/31 에 이은 두 번째 같은 사고).

본 모듈은 두 가지를 한다.
- ``failure_message`` — 실패 원인이 인증 만료면 원문 대신 *복구 명령* 을 담은 경고로
  바꾼다. 다른 실패는 기존 문구 그대로 (byte-equal).
- ``probe_cli_auth`` — ``claude -p ping`` 으로 인증 상태를 미리 점검한다
  (``src/scheduler/cli_auth_watch.py`` 가 브리핑 전에 호출).

[Public API]
    is_cli_auth_error(err) -> bool
    failure_message(prefix, err) -> str
    await probe_cli_auth(timeout_s=90.0) -> CliAuthProbe
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# CLI 가 인증 실패 시 내보내는 문구. 2026-09-27 실로그:
#   Failed to authenticate. API Error: 401 {"type":"error","error":{"type":
#   "authentication_error","message":"OAuth access token has expired. ..."}}
# 소문자로 비교한다. "401" 단독은 넣지 않는다 — request_id 등 다른 숫자열과 우연히
# 겹칠 수 있어 오탐이 난다.
_AUTH_MARKERS: tuple[str, ...] = (
    "oauth access token has expired",
    "authentication_error",
    "failed to authenticate",
    "re-authenticate",
    "invalid api key",
    "please run /login",
)

# 복구 절차. SSOT 는 docs/VM_DEPLOY_PLAYBOOK.md §3 'CLI 구독 인증 만료 점검' —
# 바뀌면 두 곳을 같이 고친다.
CLI_AUTH_FIX = (
    "🔑 VM 에서 다시 로그인해 주세요 (봇 재시작 불필요):\n"
    "cd ~/agents_reviewer && claude\n"
    "→ /login 입력 → 출력된 URL 을 브라우저에서 열어 로그인 → 코드 붙여넣기 → /exit\n"
    "확인: claude -p \"ping\" --output-format json\n"
    "(\"is_error\":false 가 나오면 복구)"
)


def is_cli_auth_error(err: BaseException | str | None) -> bool:
    """오류 메시지가 CLI 구독 인증 실패(만료·무효)인지."""
    if err is None:
        return False
    text = str(err).lower()
    return any(m in text for m in _AUTH_MARKERS)


def failure_message(prefix: str, err: BaseException | str) -> str:
    """텔레그램 실패 알림 문구.

    인증 만료면 원문 대신 복구 명령을 담는다. 그 밖의 실패는 기존 형식
    ``f"{prefix}: {str(err)[:200]}"`` 그대로다 (호출부 문구 byte-equal).
    """
    text = str(err)
    if is_cli_auth_error(text):
        return f"{prefix} — Claude CLI 로그인 만료\n\n{CLI_AUTH_FIX}"
    return f"{prefix}: {text[:200]}"


class CliAuthProbe(BaseModel):
    """``claude -p ping`` 점검 결과."""

    ok: bool
    """응답이 정상(``is_error:false``)이었나."""
    auth_expired: bool = False
    """실패 원인이 인증 만료·무효인가. ok=False 여도 이 값이 False 면 경고하지 않는다
    (타임아웃·CLI 부재 같은 다른 실패는 오경보를 피해 로그만 남긴다)."""
    detail: str = ""


async def probe_cli_auth(timeout_s: float = 90.0) -> CliAuthProbe:
    """``claude -p "ping" --output-format json`` 으로 인증 상태를 점검한다.

    중립 cwd 에서 돌린다 — repo 루트에서 돌리면 CLI 가 CLAUDE.md(봇 개발 문서)를
    자동으로 실어 ping 한 번에 수만 토큰을 쓴다 (base.py ``_run_cli_once`` 와 같은 이유).
    """
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        return CliAuthProbe(ok=False, detail="claude CLI not found on PATH")

    cli_cwd = os.path.join(tempfile.gettempdir(), "agents_reviewer_cli_cwd")
    try:
        os.makedirs(cli_cwd, exist_ok=True)
    except OSError:
        cli_cwd = tempfile.gettempdir()

    try:
        proc = await asyncio.create_subprocess_exec(
            claude_bin, "-p", "ping", "--output-format", "json",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cli_cwd,
        )
    except OSError as e:
        return CliAuthProbe(ok=False, detail=f"spawn failed: {e}")

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return CliAuthProbe(ok=False, detail=f"timeout after {timeout_s:.0f}s")

    stdout = stdout_b.decode(errors="replace").strip() if stdout_b else ""
    stderr = stderr_b.decode(errors="replace").strip() if stderr_b else ""
    combined = f"{stdout}\n{stderr}"

    is_error = proc.returncode != 0
    try:
        envelope = json.loads(stdout)
        if isinstance(envelope, dict) and envelope.get("is_error"):
            is_error = True
    except (json.JSONDecodeError, ValueError):
        is_error = True

    detail = (stderr or stdout or "").replace("\n", " ")[:300]
    if not is_error:
        return CliAuthProbe(ok=True, detail="")
    return CliAuthProbe(ok=False, auth_expired=is_cli_auth_error(combined), detail=detail)
