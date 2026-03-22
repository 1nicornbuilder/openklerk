"""
Standalone settings -- reads from environment variables.
Replacement for app.config.get_settings() in standalone mode.
"""
import os


class _StandaloneSettings:
    """Reads settings from environment variables."""

    def __getattr__(self, name: str):
        """Dynamically look up any setting from environment."""
        value = os.environ.get(name, "")
        return value


_settings = _StandaloneSettings()


def get_settings():
    """Return standalone settings that read from environment variables."""
    return _settings
