class JiraError(Exception):
    """Base exception for Jira integration failures."""


class JiraConfigurationError(JiraError):
    """Raised when Jira integration is not configured correctly."""


class JiraAuthenticationError(JiraError):
    """Raised when Jira rejects authentication."""


class JiraRequestError(JiraError):
    """Raised when Jira returns an unexpected response."""

    def __init__(self, message: str, status_code: int | None = None, details: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details
