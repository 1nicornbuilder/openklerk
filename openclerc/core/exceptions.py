"""OpenClerc exception hierarchy."""


class OpenClercError(Exception):
    """Base exception for all OpenClerc errors."""
    pass


class FilingError(OpenClercError):
    """Error during filing execution."""
    pass


class PreFlightError(OpenClercError):
    """Pre-flight validation failed."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(f"Pre-flight check failed: {'; '.join(issues)}")


class InvalidTransitionError(OpenClercError):
    """Raised when an invalid state transition is attempted."""
    pass


class BrowserError(OpenClercError):
    """Error with browser automation."""
    pass


class FilerNotFoundError(OpenClercError):
    """No filer registered for the given filing code."""
    pass
