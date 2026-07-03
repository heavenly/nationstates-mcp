"""Domain exception hierarchy for the NationStates MCP server.

Every exception carries a *detail* message and a *recoverable* flag so
callers can decide whether to retry, skip, or escalate.
"""


class NSMCPError(Exception):
    """Base for all NationStates MCP exceptions."""

    def __init__(self, detail: str, recoverable: bool = True) -> None:
        super().__init__(detail)
        self.detail = detail
        self.recoverable = recoverable


class NSAuthError(NSMCPError):
    """Bad password, missing autologin token, or invalid X-Pin."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, recoverable=False)


class NSRateLimitError(NSMCPError):
    """Server-side rate limit hit (HTTP 429 or X-Retry-After header)."""

    def __init__(self, detail: str, retry_after: float = 0.0) -> None:
        super().__init__(detail, recoverable=True)
        self.retry_after = retry_after


class NSAPIError(NSMCPError):
    """Generic 4xx / 5xx from the NationStates API."""

    def __init__(
        self, detail: str, status_code: int, recoverable: bool = True
    ) -> None:
        super().__init__(detail, recoverable=recoverable)
        self.status_code = status_code


class NSCommandError(NSAPIError):
    """Two-step command failure (prepare step failed or token missing)."""

    def __init__(
        self, detail: str, status_code: int, step: str = ""
    ) -> None:
        super().__init__(detail, status_code=status_code, recoverable=True)
        self.step = step
