"""Turns an email into a ParsedCommand via the LLM, never trusting the raw output.

Retries once (configurable) on invalid JSON/schema before giving up. A parsing failure must
never be silently coerced into a guessed command - CommandParsingFailed is raised instead, and
the caller is responsible for turning that into a safe clarification/failure reply and an admin
alert, never into an executed action.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Protocol

from pydantic import ValidationError

from app.commands.schema import CommandParsingFailed, ParsedCommand
from app.llm.prompt import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

_RETRY_SYSTEM_SUFFIX = (
    "\n\nIMPORTANT: your previous response could not be parsed as valid JSON matching the "
    "schema above. Return ONLY the JSON object, with no other text, code fences, or commentary."
)


class GeneratesText(Protocol):
    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str: ...


class EmailCommandParser:
    def __init__(
        self,
        ollama_client: GeneratesText,
        max_retries: int = 2,
        max_body_chars: int = 20000,
    ):
        self._ollama = ollama_client
        self._max_retries = max_retries
        self._max_body_chars = max_body_chars

    def parse_email(
        self,
        body_text: str,
        attachment_filenames: list[str],
        thread_job_id_hint: Optional[str] = None,
        subject: str = "",
    ) -> ParsedCommand:
        truncated_body = (body_text or "")[: self._max_body_chars]
        user_prompt = build_user_prompt(
            truncated_body, attachment_filenames, thread_job_id_hint, subject=subject
        )

        system_prompt = SYSTEM_PROMPT
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            raw = self._ollama.generate(system_prompt, user_prompt)

            try:
                data = json.loads(raw)
                return ParsedCommand.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                logger.warning("LLM output failed to parse (attempt %s): %s", attempt + 1, e)
                system_prompt = SYSTEM_PROMPT + _RETRY_SYSTEM_SUFFIX

        raise CommandParsingFailed(
            f"Could not parse a valid command after {self._max_retries + 1} attempts: {last_error}"
        )
