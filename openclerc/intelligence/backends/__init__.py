"""LLM backend implementations for OpenKlerk."""

from openclerc.intelligence.backends.base import LLMBackend


def get_backend(name: str, **kwargs) -> LLMBackend:
    """Factory function to get an LLM backend by name."""
    name = name.lower()
    if name == "google":
        from openclerc.intelligence.backends.google import GoogleVertexBackend
        return GoogleVertexBackend(**kwargs)
    elif name == "anthropic":
        from openclerc.intelligence.backends.anthropic import AnthropicBackend
        return AnthropicBackend(**kwargs)
    elif name == "openai":
        from openclerc.intelligence.backends.openai import OpenAIBackend
        return OpenAIBackend(**kwargs)
    elif name == "ollama":
        from openclerc.intelligence.backends.ollama import OllamaBackend
        return OllamaBackend(**kwargs)
    elif name == "mock":
        return MockBackend(**kwargs)
    else:
        raise ValueError(f"Unknown LLM backend: {name}. Available: google, anthropic, openai, ollama, mock")


class MockBackend(LLMBackend):
    """Mock backend that returns empty responses (for testing)."""

    async def call(self, system_prompt: str, user_prompt: str, screenshot: bytes = None) -> str:
        return ""

    @property
    def name(self) -> str:
        return "mock"


__all__ = ["LLMBackend", "get_backend", "MockBackend"]
