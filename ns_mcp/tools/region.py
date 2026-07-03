"""Region API tools for the NationStates MCP server."""

import os
from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAuthError, NSAPIError, NSRateLimitError

VALID_REGION_SHARDS = {
    "banlist", "banner", "bannerby", "bannerurl", "census", "censusranks",
    "dbid", "delegate", "delegateauth", "delegatevotes", "dispatches",
    "embassies", "embassyrmb", "factbook", "flag", "founded", "foundedtime",
    "founder", "frontier", "gavote", "governor", "governortitle",
    "happenings", "history", "lastupdate", "lastmajorupdate",
    "lastminorupdate", "magnetism", "messages", "name", "nations",
    "numnations", "wanations", "numwanations", "officers", "poll", "power",
    "recruiters", "scvote", "tags", "wabadges", "zombie",
}

# Default limit for the messages shard if not overridden by the caller.
_DEFAULT_MESSAGES_LIMIT = 10


def register_tools(mcp) -> None:
    """Register all region-related tools with the MCP server."""

    @mcp.tool()
    async def ns_get_region(
        region: str,
        shards: list[str],
        messages_limit: int | None = None,
        messages_offset: int | None = None,
        messages_fromid: int | None = None,
    ) -> dict:
        """Fetch region data from NationStates by shard.

        Region names with spaces: use underscore or +, e.g. 'the_north_pacific'.

        Args:
            region: Region name.
            shards: List of shard names, e.g. ['name', 'numnations', 'delegate'].
            messages_limit: For 'messages' shard -- max posts (1-100, default 10).
            messages_offset: Skip most recent N posts.
            messages_fromid: Start from a specific post ID.

        Returns:
            Dict with requested region data.

        Example return for shards=['name', 'numnations', 'delegate']:
            {"name": "The North Pacific", "numnations": "8000", "delegate": "ExampleNation"}

        Example return for shards=['messages', 'numnations'] with messages_limit=5:
            {"numnations": "8000", "messages": [
                {"id": "1001", "timestamp": "1720000000", "nation": "...",
                 "status": "0", "likes": "5", "message": "..."},
                ...
            ]}
        """
        # Validate shards against the known list.
        invalid = [s for s in shards if s not in VALID_REGION_SHARDS]
        if invalid:
            return {
                "error": "invalid_shards",
                "detail": f"Unknown shards: {', '.join(invalid)}",
                "valid_shards": sorted(VALID_REGION_SHARDS),
            }

        # Apply default message limit when the messages shard is requested.
        msg_limit = messages_limit
        if "messages" in shards and msg_limit is None:
            msg_limit = _DEFAULT_MESSAGES_LIMIT

        client = NationStatesClient(user_agent="ns-mcp/0.1.0")
        try:
            await client.start()
            result = await client.get_region(
                region=region,
                shards=shards,
                msg_limit=msg_limit,
                msg_offset=messages_offset,
                msg_fromid=messages_fromid,
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
