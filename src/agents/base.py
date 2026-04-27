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

        cmd = [
            claude_bin,
            "-p", full_prompt,
            "--output-format", "text",
            "--model", self.model_name,
            "--dangerously-skip-permissions",
            "--allowedTools", "WebFetch,WebSearch",
        ]

        logger.info(f"[{self.name}] Starting CLI analysis ({self.model_name})...")
        start_ts = time.time()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "unknown error"
            raise RuntimeError(
                f"[{self.name}] claude CLI exited with code {proc.returncode}: {err_msg}"
            )

        raw_text = stdout.decode().strip()
        raw_text = raw_text.replace("**", "")
        elapsed_ms = int((time.time() - start_ts) * 1000)
        logger.info(f"[{self.name}] Received CLI response ({len(raw_text)} chars)")
        if self.telemetry is not None:
            self.telemetry.record_llm_call(
                agent_name=self.name,
                input_chars=len(full_prompt),
                output_chars=len(raw_text),
                elapsed_ms=elapsed_ms,
            )
        return raw_text

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
        response = await self._api_client.messages.create(  # type: ignore[union-attr]
            model=self.model_name,
            max_tokens=4096,
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
