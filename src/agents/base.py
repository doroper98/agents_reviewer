"""Base agent class for the Event Analysis Team."""

from __future__ import annotations

import json
import logging
from typing import TypeVar, Type

import anthropic

from src.config import Config

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseAgent:
    """Base class for all analysis agents.

    Uses Anthropic AsyncAnthropic client for Claude API calls.
    """

    def __init__(self, name: str, role: str, system_prompt: str, config: Config) -> None:
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.config = config
        self.client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    async def analyze(self, context: dict) -> str:
        """Call Claude API with system_prompt and context, return parsed response."""
        user_message = json.dumps(context, ensure_ascii=False, indent=2)

        logger.info(f"[{self.name}] Starting analysis...")
        response = await self.client.messages.create(
            model=self.config.model_name,
            max_tokens=4096,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text
        logger.info(f"[{self.name}] Received response ({len(raw_text)} chars)")
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
