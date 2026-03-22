"""Ollama (local models) backend for OpenKlerk -- stub implementation."""
import logging
from typing import Optional

from openclerc.intelligence.backends.base import LLMBackend

logger = logging.getLogger("openclerc")


class OllamaBackend(LLMBackend):
    """
    Ollama backend for running local LLMs.

    TODO: Implement using httpx to call Ollama's REST API.
    Requires: Ollama running locally (https://ollama.ai)
    Default model: llava (vision-capable)
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llava", **kwargs):
        self.base_url = base_url
        self.model = model

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot: Optional[bytes] = None,
    ) -> str:
        raise NotImplementedError(
            "Ollama backend not yet implemented. "
            "Contributions welcome! See CONTRIBUTING.md for details."
        )

    @property
    def name(self) -> str:
        return "ollama"
