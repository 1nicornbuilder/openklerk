"""OpenAI (GPT) backend for OpenKlerk -- stub implementation."""
import logging
from typing import Optional

from openclerc.intelligence.backends.base import LLMBackend

logger = logging.getLogger("openclerc")


class OpenAIBackend(LLMBackend):
    """
    OpenAI GPT backend.

    TODO: Implement using the OpenAI Python SDK.
    Requires: pip install openai
    Set OPENAI_API_KEY environment variable.
    """

    def __init__(self, api_key: str = "", model: str = "gpt-4o", **kwargs):
        self.api_key = api_key
        self.model = model

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot: Optional[bytes] = None,
    ) -> str:
        raise NotImplementedError(
            "OpenAI backend not yet implemented. "
            "Contributions welcome! See CONTRIBUTING.md for details."
        )

    @property
    def name(self) -> str:
        return "openai"
