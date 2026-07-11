"""Utility tools for API metadata."""

from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAPIError, NSRateLimitError


def register_tools(mcp) -> None:
    """Register API utility tools."""

    @mcp.tool()
    async def ns_api_version() -> dict:
        """Return the current NationStates API version."""
        try:
            async with NationStatesClient(user_agent="ns-mcp/0.2.0") as client:
                return {"version": await client.get_api_version()}
        except NSRateLimitError as exc:
            return {
                "error": "rate_limited",
                "detail": str(exc),
                "retry_after": exc.retry_after,
            }
        except NSAPIError as exc:
            return {
                "error": "api_error",
                "detail": str(exc),
                "status_code": exc.status_code,
            }
