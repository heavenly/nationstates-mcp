"""Telegram API tools for the NationStates MCP server."""

from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAuthError, NSAPIError, NSRateLimitError


def register_tools(mcp) -> None:
    """Register all telegram-related tools with the MCP server."""

    @mcp.tool()
    async def ns_send_telegram(
        client_key: str,
        tgid: str,
        secret_key: str,
        to_nation: str,
    ) -> dict:
        """Send an API telegram to a nation.

        Requires an API Client Key (requested from NationStates moderators)
        and a pre-composed telegram template (composed via the 'tag:api'
        recipient in the Telegram Centre).

        Rate limits per Client Key:
        - Recruitment telegrams: 1 per 180 seconds
        - Non-recruitment telegrams: 1 per 30 seconds

        The rate limiter is applied automatically by the client.

        Args:
            client_key: Your API Client Key (obtained from NS moderators).
            tgid: Telegram template ID (found in Delivery Reports after
                  composing via 'tag:api').
            secret_key: The template's Secret Key (never share this token).
            to_nation: Recipient nation name.

        Returns:
            {"ok": True/False, "message": "Result description"}
        """
        # Basic input validation
        if not client_key or not client_key.strip():
            return {
                "error": "missing_client_key",
                "detail": "client_key is required to send telegrams",
            }
        if not tgid or not tgid.strip():
            return {
                "error": "missing_tgid",
                "detail": "tgid (telegram template ID) is required",
            }
        if not secret_key or not secret_key.strip():
            return {
                "error": "missing_secret_key",
                "detail": "secret_key is required to send telegrams",
            }
        if not to_nation or not to_nation.strip():
            return {
                "error": "missing_to_nation",
                "detail": "to_nation (recipient) is required",
            }

        # Telegram API uses a separate auth mechanism (API Client Key),
        # not the standard password/autologin/X-Pin system.
        client = NationStatesClient(user_agent="ns-mcp/0.1.0")
        try:
            await client.start()
            result = await client.send_telegram(
                client_key=client_key.strip(),
                tgid=tgid.strip(),
                secret_key=secret_key.strip(),
                to_nation=to_nation.strip(),
            )
            return {
                "ok": True,
                "message": "Telegram sent successfully",
                "response": result,
            }
        except NSAPIError as e:
            return {
                "error": "api_error",
                "detail": str(e),
                "status_code": e.status_code,
            }
        except NSRateLimitError as e:
            return {
                "error": "rate_limited",
                "detail": str(e),
                "retry_after": e.retry_after,
            }
        except NSAuthError as e:
            return {
                "error": "auth_error",
                "detail": str(e),
            }
        except Exception as e:
            return {
                "error": "unexpected",
                "detail": str(e),
            }
        finally:
            await client.close()
