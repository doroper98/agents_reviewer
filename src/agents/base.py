"""Base agent class for the Event Analysis Team."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from typing import Optional, TypeVar, Type

from src.config import Config
from src.telemetry import RunTelemetry

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseAgent:
    """Base class for all analysis agents.

    Supports two modes:
    - CLI mode (default): calls ``claude`` CLI subprocess (Claude Max plan, no API cost)
    - API mode: uses ``anthropic`` SDK when ``ANTHROPIC_API_KEY`` is set
    """

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        config: Config,
        use_light_model: bool = False,
    ) -> None:
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.config = config
        self.model_name = config.model_name_light if use_light_model else config.model_name
        self._api_client: object | None = None
        # v3.1.0: telemetry registry. Orchestrator 가 사건당 인스턴스를 주입.
        # None 이면 telemetry 기록을 스킵 (단위 테스트 / standalone 사용 시).
        self.telemetry: Optional[RunTelemetry] = None

        if not config.use_cli_mode:
            import anthropic  # lazy import – not required in CLI mode

            self._api_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def analyze(self, context: dict) -> str:
        """Call Claude with system_prompt and context, return parsed response.

        Automatically selects CLI or API mode based on ``config.use_cli_mode``.
        """
        if self.config.use_cli_mode:
            return await self._analyze_cli(context)
        return await self._analyze_api(context)

    @staticmethod
    def _serialize_context(context: dict) -> tuple[str, str]:
        """입력 dict → (directive, compact JSON user_message).

        v3.1.0: ``json.dumps(..., indent=2)`` 폐기. 한국어 nested JSON 에서 indent 는
        토큰을 30~50% 더 먹는다. 또한 ``context.pop`` 부작용을 제거 — 호출자 dict 를
        변형하지 않음 (Anti-pattern: side-effect 입력 변형).
        """
        context_for_prompt = dict(context)
        directive = context_for_prompt.pop("strategic_directive", "") or ""
        user_message = json.dumps(
            context_for_prompt, ensure_ascii=False, separators=(",", ":")
        )
        return directive, user_message

    # ------------------------------------------------------------------
    # CLI mode (Claude Max plan via ``claude`` subprocess)
    # ------------------------------------------------------------------

    # v8.2.1 — 일시적(서버측) 실패 마커. Anthropic 과부하(529 Overloaded)·rate
    # limit(429)·5xx 는 우리 버그가 아니라 재시도하면 풀리는 상태다. 2026-06-24
    # 실연동 사고: context_analyst 가 529 한 번에 보고서 전체가 "unknown error" 로
    # 실패. CLI v2 는 이 에러를 *stdout* 에 ("API Error: 529 …") 내보내는데 봇은
    # stderr 만 읽어 "unknown error" 로 폴백했다 (둘 다 본 패치에서 교정).
    _TRANSIENT_MARKERS: tuple[str, ...] = (
        "529", "overloaded", "rate limit", "rate_limit", "429",
        "500", "502", "503", "504", "internal server error",
        "api error: 5", "timeout", "timed out", "econnreset", "connection reset",
    )
    _CLI_MAX_ATTEMPTS: int = 3
    _CLI_RETRY_BACKOFF_S: float = 4.0   # attempt N 전 대기 = backoff*(N-1): 0/4/8s
    _CLI_TIMEOUT_S: float = 300.0       # 단일 호출 상한 (hang 방지). 초과 시 transient 취급.

    # v8.5.5 — 호출별 상한 override. None 이면 위 클래스 기본값(300s) 그대로라
    # 이 값을 안 세팅하는 에이전트는 byte-equal.
    #
    # 왜 필요했나 (2026-08-01 실사고): 장마감 브리핑 소급 발행이 context_analyst
    # 300s 타임아웃 3연속으로 통째 실패. deep 모드 사실수집은 웹검색을 여러 번 돌고
    # 10K 토큰까지 쓰는데 상한이 fast 와 같은 300s 였다. 편집장(narrative_composer)은
    # v8.2.4 에서 이미 같은 실패로 mode 별 상한(deep 1500s)을 받았는데, 사실수집만
    # 평면 300s 로 남아 있었다 — 같은 결함의 미적용 절반.
    _cli_timeout_override: float | None = None

    @property
    def cli_timeout_s(self) -> float:
        """이번 호출의 CLI 상한 (override 우선)."""
        return self._cli_timeout_override or self._CLI_TIMEOUT_S

    async def _analyze_cli(self, context: dict) -> str:
        directive, user_message = self._serialize_context(context)

        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError(
                "claude CLI not found on PATH. "
                "Install it with: npm install -g @anthropic-ai/claude-code && claude login"
            )

        if directive:
            full_prompt = (
                f"{self.system_prompt}\n\n"
                f"=== 전략 지시 (최우선 준수) ===\n{directive}\n"
                f"위 지시에 따라 분석 관점과 기법을 조정할 것. "
                f"JSON 필드 중 이 사건에 불필요한 항목은 빈 값으로 두고, 지시된 분석에 집중.\n"
                f"===\n\n{user_message}"
            )
        else:
            full_prompt = f"{self.system_prompt}\n\n---\n\n{user_message}"

        # v8.2.1 — 일시적 실패(529/429/5xx/timeout) 재시도 루프. 비일시적(인증·인자
        # 오류 등) 은 fast-fail. 마지막 시도까지 실패하면 *진짜* 에러 메시지로 raise.
        last_err = ""
        for attempt in range(1, self._CLI_MAX_ATTEMPTS + 1):
            if attempt > 1:
                wait = self._CLI_RETRY_BACKOFF_S * (attempt - 1)
                logger.warning(
                    "[%s] transient CLI failure — retry %d/%d in %.0fs: %s",
                    self.name, attempt, self._CLI_MAX_ATTEMPTS, wait, last_err[:200],
                )
                await asyncio.sleep(wait)
            raw_text, err, transient = await self._run_cli_once(claude_bin, full_prompt)
            if err is None:
                return raw_text
            last_err = err
            if not transient:
                break  # 비일시적 — 재시도 무의미, 즉시 중단

        raise RuntimeError(
            f"[{self.name}] claude CLI failed after {attempt} attempt(s): {last_err}"
        )

    async def _run_cli_once(
        self, claude_bin: str, full_prompt: str
    ) -> tuple[str, Optional[str], bool]:
        """CLI 1회 호출. ``(raw_text, error_or_None, is_transient)`` 반환.

        v8.2.1 변경 2가지:
        - **중립 cwd 에서 실행.** CLI v2 는 ``-p`` 모드에서도 cwd 의 ``CLAUDE.md`` 를
          자동으로 컨텍스트에 싣는다. 봇 repo 의 CLAUDE.md(54KB, 봇 *개발* 운영문서)는
          뉴스 분석과 무관한데 매 호출 ~45K 토큰을 먹고 과부하 노출만 키운다. 빈 임시
          디렉터리에서 돌려 자동로드를 끊는다 (WebFetch/WebSearch 만 쓰므로 cwd 무관).
        - **stdout 까지 에러 판정.** CLI v2 는 API 에러를 stdout 에 ("API Error: 529 …")
          내보내고 종종 exit 0 으로 끝난다. returncode·stderr 만 보면 "unknown error"
          로 새 버린다 — stdout 의 에러 마커도 함께 본다.
        """
        import os
        import tempfile

        cli_cwd = os.path.join(tempfile.gettempdir(), "agents_reviewer_cli_cwd")
        try:
            os.makedirs(cli_cwd, exist_ok=True)
        except OSError:
            cli_cwd = tempfile.gettempdir()

        cmd = [
            claude_bin,
            "-p", full_prompt,
            "--output-format", "text",
            "--model", self.model_name,
            "--dangerously-skip-permissions",
            "--allowedTools", "WebFetch,WebSearch",
        ]

        logger.info(
            "[%s] Starting CLI analysis (%s, prompt=%d chars, timeout=%.0fs)",
            self.name, self.model_name, len(full_prompt), self.cli_timeout_s,
        )
        start_ts = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cli_cwd,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self.cli_timeout_s
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return "", f"timeout after {self.cli_timeout_s:.0f}s", True

        stdout = stdout_b.decode().strip() if stdout_b else ""
        stderr = stderr_b.decode().strip() if stderr_b else ""

        # API 에러는 exit≠0 이거나 stdout 텍스트로 온다. 둘 다 검사.
        combined = f"{stdout}\n{stderr}".lower()
        is_error = (
            proc.returncode != 0
            or stdout.startswith("API Error")
            or "api error:" in combined
            or "execution error" in combined
        )
        if is_error:
            detail = (stderr or stdout or "unknown error").replace("\n", " ")[:500]
            transient = any(m in combined for m in self._TRANSIENT_MARKERS)
            return "", f"exit={proc.returncode}: {detail}", transient

        raw_text = stdout.replace("**", "")
        elapsed_ms = int((time.time() - start_ts) * 1000)
        logger.info(f"[{self.name}] Received CLI response ({len(raw_text)} chars)")
        if self.telemetry is not None:
            self.telemetry.record_llm_call(
                agent_name=self.name,
                input_chars=len(full_prompt),
                output_chars=len(raw_text),
                elapsed_ms=elapsed_ms,
            )
        return raw_text, None, False


    # ------------------------------------------------------------------
    # API mode (Anthropic SDK – pay-per-use)
    # ------------------------------------------------------------------

    async def _analyze_api(self, context: dict) -> str:
        assert self._api_client is not None, "API client not initialised"
        directive, user_message = self._serialize_context(context)

        system = self.system_prompt
        if directive:
            system += (
                f"\n\n=== 전략 지시 (최우선 준수) ===\n{directive}\n"
                f"위 지시에 따라 분석 관점과 기법을 조정할 것. "
                f"JSON 필드 중 이 사건에 불필요한 항목은 빈 값으로 두고, 지시된 분석에 집중.\n==="
            )

        logger.info(f"[{self.name}] Starting API analysis ({self.model_name})...")
        start_ts = time.time()
        # v4.5.7 — subclass 가 self._max_tokens_override 설정하면 그 값 사용.
        # BaseAgent 디폴트는 4096. ContextAnalyst 가 mode (fast/standard/deep) 별로
        # 분기 적용 — deep 사건은 사실 수집 범위가 커서 4K 부족.
        max_tokens = getattr(self, "_max_tokens_override", None) or 4096
        response = await self._api_client.messages.create(  # type: ignore[union-attr]
            model=self.model_name,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text  # type: ignore[index]
        raw_text = raw_text.replace("**", "")
        elapsed_ms = int((time.time() - start_ts) * 1000)
        logger.info(f"[{self.name}] Received API response ({len(raw_text)} chars)")
        if self.telemetry is not None:
            self.telemetry.record_llm_call(
                agent_name=self.name,
                input_chars=len(system) + len(user_message),
                output_chars=len(raw_text),
                elapsed_ms=elapsed_ms,
            )
        return raw_text

    def _parse_json_response(self, raw_text: str, output_type: Type[T]) -> T:
        """Parse JSON from agent response into a Pydantic model."""
        try:
            if "```json" in raw_text:
                json_str = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                json_str = raw_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = raw_text.strip()

            data = json.loads(json_str)
            return output_type.model_validate(data)
        except (json.JSONDecodeError, IndexError, ValueError) as e:
            logger.warning(
                f"[{self.name}] JSON parse failed: {e}, using raw text as summary"
            )
            fallback_data = {"summary": raw_text[:2000]}
            return output_type.model_validate(fallback_data)
