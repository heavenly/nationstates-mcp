"""Verification API tools for the NationStates MCP server."""

from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAuthError, NSAPIError, NSRateLimitError


def register_tools(mcp) -> None:
    """Register all verification-related tools with the MCP server."""

    @mcp.tool()
    async def ns_verify(
        nation: str,
        checksum: str,
        token: str | None = None,
        shards: list[str] | None = None,
    ) -> dict:
        """Verify a nation's ownership via the NationStates verification system.

        Use this to cryptographically prove that you control a specific
        nation on NationStates.

        Flow:
        1. The user visits https://www.nationstates.net/page=verify_login
           (optionally with ?token=YOUR_TOKEN appended) and copies the
           checksum code displayed there.
        2. This tool sends the checksum to the API to verify it matches
           the nation.
        3. The API confirms or rejects the verification.

        Optionally, you can pass a token to bind the verification to a
        specific service, and request additional shards alongside the
        verification result.

        Args:
            nation: Nation name to verify.
            checksum: The checksum code obtained from the
                      nationstates.net/page=verify_login page.
            token: Optional site-specific authentication token for
                   binding verification to an external service.
            shards: Optional list of additional shards to fetch
                    alongside the verification result (e.g. 'name',
                    'region', 'population').

        Returns:
            {"verified": True/False, ...shard data if requested...}

        Example return (verified with no extra shards):
            {"verified": True}

        Example return (verified with extra shards):
            {"verified": True, "name": "Testlandia", "region": "The North Pacific"}

        Example return (not verified):
            {"verified": False, "error": "checksum_mismatch", ...}
        """
        if not checksum or not checksum.strip():
            return {
                "error": "missing_checksum",
                "detail": (
                    "checksum is required. Have the nation owner visit "
                    "https://www.nationstates.net/page=verify_login and "
                    "copy the checksum code."
                ),
            }
        if not nation or not nation.strip():
            return {
                "error": "missing_nation",
                "detail": "nation name is required",
            }

        client = NationStatesClient(user_agent="ns-mcp/0.1.0")
        try:
            await client.start()
            result = await client.verify_nation(
                nation=nation.strip(),
                checksum=checksum.strip(),
                token=token.strip() if token else None,
                shards=shards,
            )
            # Extract the verification result. The API response under the
            # "nation" key contains "verify" with either "1" (verified) or "0" (not).
            nation_data = result.get("nation", {})
            verify_value = nation_data.pop("verify", "0")
            is_verified = verify_value == "1"

            output = {"verified": is_verified}

            # Merge any additional shard data the user requested
            # (everything except "verify" itself)
            output.update(nation_data)

            if not is_verified:
                output["error"] = "verification_failed"
                output["detail"] = (
                    "The checksum does not match this nation. "
                    "Double-check the checksum from "
                    "https://www.nationstates.net/page=verify_login"
                )

            return output
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
