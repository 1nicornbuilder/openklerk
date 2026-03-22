"""Anthropic (Claude) backend for OpenKlerk -- stub implementation."""
import logging
from typing import Optional

from openclerc.intelligence.backends.base import LLMBackend

logger = logging.getLogger("openclerc")


class AnthropicBackend(LLMBackend):
    """
    Anthropic Claude backend.

    TODO: Implement using the Anthropic Python SDK.
    Requires: pip install anthropic
    Set ANTHROPIC_API_KEY environment variable.
    """

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-5-20250929", **kwargs):
        self.api_key = api_key
        self.model = model

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot: Optional[bytes] = None,
    ) -> str:
        raise NotImplementedError(
            "Anthropic backend not yet implemented. "
            "Contributions welcome! See CONTRIBUTING.md for details."
        )

    @property
    def name(self) -> str:
        return "anthropic"
