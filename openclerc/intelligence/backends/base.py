"""Abstract base class for LLM backends."""
from abc import ABC, abstractmethod
from typing import Optional


class LLMBackend(ABC):
    """Abstract LLM backend for OpenKlerk intelligence."""

    @abstractmethod
    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot: Optional[bytes] = None,
    ) -> str:
        """
        Send a prompt (with optional screenshot) to the LLM and return the response text.

        Args:
            system_prompt: System/context prompt
            user_prompt: User/analysis prompt
            screenshot: Optional PNG screenshot bytes for vision analysis

        Returns:
            Raw text response from the LLM
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this backend."""
        pass
