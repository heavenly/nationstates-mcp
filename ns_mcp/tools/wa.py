"""World Assembly API tools for the NationStates MCP server."""

from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAuthError, NSAPIError, NSRateLimitError

# Valid WA shards (per NS API documentation).
VALID_WA_SHARDS = {
    "numnations", "numdelegates", "delegates", "members",
    "happenings", "proposals", "resolution", "voters", "votetrack",
    "dellog", "delvotes", "lastresolution",
}

# Shards that require a current-at-vote resolution context.
_RESOLUTION_CONTEXT_SHARDS = {"voters", "votetrack", "dellog", "delvotes"}


def register_tools(mcp) -> None:
    """Register all World-Assembly-related tools with the MCP server."""

    @mcp.tool()
    async def ns_get_wa(
        council: int,
        shards: list[str],
    ) -> dict:
        """Fetch World Assembly data for a given council.

        Args:
            council: Council number -- 1 = General Assembly, 2 = Security Council.
            shards: Data shards to fetch. Valid shards:
                numnations, numdelegates, delegates, members, happenings,
                proposals, resolution, voters, votetrack, dellog, delvotes,
                lastresolution

                For overall WA data (numnations, numdelegates), either council works.
                Shards like voters, votetrack, dellog, delvotes only work together
                with resolution for the current at-vote resolution.

        Returns:
            Dict with requested WA data. Top-level key is "wa".

        Example return:
            {"wa": {"council": "1", "numnations": "300", "numdelegates": "200"}}
        """
        # Validate council
        if council not in (1, 2):
            return {
                "error": "invalid_council",
                "detail": f"Council must be 1 (GA) or 2 (SC), got {council}",
            }

        # Validate shards
        invalid = [s for s in shards if s not in VALID_WA_SHARDS]
        if invalid:
            return {
                "error": "invalid_shards",
                "detail": f"Unknown shards: {', '.join(invalid)}",
                "valid_shards": sorted(VALID_WA_SHARDS),
            }

        # Warn about resolution-context shards without resolution
        resolution_shards = _RESOLUTION_CONTEXT_SHARDS & set(shards)
        if resolution_shards and "resolution" not in shards:
            return {
                "error": "missing_resolution_shard",
                "detail": (
                    f"Shards {sorted(resolution_shards)} require the 'resolution'"
                    f" shard to be included together. Add 'resolution' to shards."
                ),
            }

        client = NationStatesClient(user_agent="ns-mcp/0.2.0")
        try:
            await client.start()
            result = await client.get_wa(council=council, shards=shards)
            return result
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

    @mcp.tool()
    async def ns_get_wa_resolution(
        council: int,
        resolution_id: int,
    ) -> dict:
        """Fetch a specific past WA resolution by council and resolution ID.

        Args:
            council: Council number -- 1 = General Assembly, 2 = Security Council.
            resolution_id: The numeric ID of the resolution to fetch.

        Returns:
            Dict containing council info and the full resolution data.

        Example return:
            {"council": 1, "resolution": {
                "name": "G.R. 1: Example Resolution",
                "category": "Civil Rights",
                ...
            }}
        """
        if council not in (1, 2):
            return {
                "error": "invalid_council",
                "detail": f"Council must be 1 (GA) or 2 (SC), got {council}",
            }

        client = NationStatesClient(user_agent="ns-mcp/0.2.0")
        try:
            await client.start()
            result = await client.get_wa(
                council=council,
                shards=["resolution"],
                resolution_id=resolution_id,
            )
            return result
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
