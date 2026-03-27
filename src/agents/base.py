"""Base agent class with dual-mode support: API Mode & Claude Code Mode.

Mode A (API): Direct Anthropic API calls — requires ANTHROPIC_API_KEY
Mode B (Claude Code): Uses `claude` CLI subprocess — uses Max subscription tokens
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import TypeVar, Type

from src.config import ANTHROPIC_API_KEY, MODEL, MAX_TOKENS
from src.models import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _get_mode() -> str:
    """Determine which mode to use based on available credentials."""
    if ANTHROPIC_API_KEY:
        return "api"
    return "claude_code"


class BaseAgent:
    """Base class for all analysis agents.

    Supports two execution modes:
    - API Mode: Direct Anthropic API calls (fast, parallel, costs API credits)
    - Claude Code Mode: Uses `claude` CLI (uses Max subscription tokens)
    """

    name: str = "base_agent"
    role: str = "Base Agent"
    system_prompt: str = ""

    def __init__(self) -> None:
        self.mode = _get_mode()
        if self.mode == "api":
            import anthropic
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        else:
            self.client = None

    async def run(self, user_message: str, output_type: Type[T]) -> T:
        """Execute the agent and return structured output."""
        logger.info(f"[{self.name}] Starting analysis (mode={self.mode})...")

        if self.mode == "api":
            raw_text = await self._run_api(user_message)
        else:
            raw_text = await self._run_claude_code(user_message)

        logger.info(f"[{self.name}] Received response ({len(raw_text)} chars)")
        return self._parse_response(raw_text, output_type)

    async def _run_api(self, user_message: str) -> str:
        """Mode A: Direct API call."""
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    async def _run_claude_code(self, user_message: str) -> str:
        """Mode B: Call `claude` CLI as subprocess (uses Max subscription tokens).

        This runs the claude CLI with --print flag for non-interactive output,
        passing the system prompt and user message.
        """
        prompt = f"{self.system_prompt}\n\n---\n\n{user_message}"

        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--model", MODEL,
            "--max-tokens", str(MAX_TOKENS),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate(input=prompt.encode("utf-8"))

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            logger.error(f"[{self.name}] Claude Code failed: {error_msg}")
            raise RuntimeError(f"Claude Code failed: {error_msg[:200]}")

        return stdout.decode("utf-8", errors="replace")

    def _parse_response(self, raw_text: str, output_type: Type[T]) -> T:
        """Parse JSON from agent response into Pydantic model."""
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

    def build_context_message(self, event_text: str, **kwargs: str) -> str:
        """Build a structured message for the agent with event context."""
        parts = [f"## Event to Analyze\n{event_text}"]
        for key, value in kwargs.items():
            parts.append(f"\n## {key}\n{value}")
        parts.append(
            "\n## Output Format\n"
            "Respond ONLY with a valid JSON object matching the expected schema. "
            "Do not include any text outside the JSON block."
        )
        return "\n".join(parts)
