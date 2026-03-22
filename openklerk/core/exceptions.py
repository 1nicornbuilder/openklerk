"""OpenKlerk exception hierarchy."""


class OpenKlerkError(Exception):
    """Base exception for all OpenKlerk errors."""
    pass


class FilingError(OpenKlerkError):
    """Error during filing execution."""
    pass


class PreFlightError(OpenKlerkError):
    """Pre-flight validation failed."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(f"Pre-flight check failed: {'; '.join(issues)}")


class InvalidTransitionError(OpenKlerkError):
    """Raised when an invalid state transition is attempted."""
    pass


class BrowserError(OpenKlerkError):
    """Error with browser automation."""
    pass


class FilerNotFoundError(OpenKlerkError):
    """No filer registered for the given filing code."""
    pass
