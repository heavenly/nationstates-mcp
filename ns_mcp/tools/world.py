"""World / global-state API tools for the NationStates MCP server.

Provides ``ns_get_world`` for general world shards and
``ns_get_happenings`` for the happenings/events stream.
"""

from __future__ import annotations

import logging
from typing import Any

from ..client import NationStatesClient
from ..exceptions import NSAPIError, NSRateLimitError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_WORLD_SHARDS: frozenset[str] = frozenset({
    "banner",
    "census",
    "censusid",
    "censusdesc",
    "censusname",
    "censusranks",
    "censusscale",
    "censustitle",
    "dispatch",
    "dispatchlist",
    "faction",
    "factions",
    "featuredregion",
    "happenings",
    "lasteventid",
    "nations",
    "newnations",
    "newnationdetails",
    "numnations",
    "numregions",
    "poll",
    "regions",
    "regionsbytag",
    "tgqueue",
})

USER_AGENT = "ns-mcp/0.1.0"

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_shards(shards: list[str]) -> None:
    """Raise ``ValueError`` if any shard name is not recognised."""
    invalid = [s for s in shards if s not in VALID_WORLD_SHARDS]
    if invalid:
        raise ValueError(
            f"Unknown world shard(s): {', '.join(invalid)}. "
            f"Valid shards: {', '.join(sorted(VALID_WORLD_SHARDS))}"
        )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp: Any) -> None:
    """Register world-related MCP tools on the given server instance."""

    @mcp.tool()
    async def ns_get_world(
        shards: list[str],
        census_scale: str | None = None,
        census_mode: str | None = None,
        census_rank_start: int | None = None,
        dispatch_id: str | None = None,
        dispatch_author: str | None = None,
        dispatch_category: str | None = None,
        dispatch_sort: str | None = None,
        faction_id: str | None = None,
        poll_id: str | None = None,
        region_tags: str | None = None,
        banner_ids: str | None = None,
    ) -> dict:
        """Fetch world-level data from NationStates.

        Args:
            shards: World shard names, e.g. ['numnations', 'numregions',
                'featuredregion'].
            census_scale: Census scale ID(s) — '+' to combine, or 'all'.
            census_mode: Census mode(s) — score, rank, rrank, prank, prrank.
            census_rank_start: Starting rank for censusranks pagination.
            dispatch_id: Specific dispatch ID to fetch.
            dispatch_author: Filter dispatchlist by author nation.
            dispatch_category: Filter dispatchlist by category or
                category:subcategory.
            dispatch_sort: Sort dispatchlist — 'new' or 'best'.
            faction_id: N-Day faction ID.
            poll_id: Specific poll ID to fetch.
            region_tags: Comma-separated tags for regionsbytag (prefix with
                '-' to exclude).
            banner_ids: Comma-separated banner IDs for world banner shard.

        Returns:
            Dict with requested world data.
        """
        try:
            _validate_shards(shards)

            kwargs: dict[str, str] = {}

            # -- Census shard params -------------------------------------------
            if "census" in shards or "censusranks" in shards:
                if census_scale is not None:
                    kwargs["scale"] = census_scale
                if census_mode is not None:
                    kwargs["mode"] = census_mode
                if census_rank_start is not None and "censusranks" in shards:
                    kwargs["start"] = str(census_rank_start)

            # -- Dispatch shard params -----------------------------------------
            if "dispatch" in shards and dispatch_id is not None:
                kwargs["dispatchid"] = dispatch_id

            if "dispatchlist" in shards:
                if dispatch_author is not None:
                    kwargs["dispatchauthor"] = dispatch_author
                if dispatch_category is not None:
                    kwargs["dispatchcategory"] = dispatch_category
                if dispatch_sort is not None:
                    kwargs["dispatchsort"] = dispatch_sort

            # -- Faction shard params ------------------------------------------
            if "faction" in shards and faction_id is not None:
                kwargs["id"] = faction_id

            # -- Poll shard params ---------------------------------------------
            if "poll" in shards and poll_id is not None:
                kwargs["pollid"] = poll_id

            # -- Regions-by-tag params -----------------------------------------
            if "regionsbytag" in shards and region_tags is not None:
                kwargs["tags"] = region_tags

            # -- Banner shard params -------------------------------------------
            if "banner" in shards and banner_ids is not None:
                kwargs["banner"] = banner_ids

            async with NationStatesClient(user_agent=USER_AGENT) as client:
                data = await client.get_world(shards=shards, **kwargs)
            return data

        except ValueError as exc:
            return {"error": str(exc), "recoverable": False}
        except NSRateLimitError as exc:
            return {
                "error": f"Rate limited: {exc.detail}",
                "recoverable": True,
                "retry_after": exc.retry_after,
            }
        except NSAPIError as exc:
            return {
                "error": f"API error: {exc.detail}",
                "recoverable": exc.recoverable,
                "status_code": exc.status_code,
            }
        except Exception as exc:
            logger.exception("Unexpected error in ns_get_world")
            return {"error": f"Unexpected error: {exc}", "recoverable": False}

    @mcp.tool()
    async def ns_get_happenings(
        view: str | None = None,
        event_filter: list[str] | None = None,
        limit: int | None = None,
        since_id: int | None = None,
        before_id: int | None = None,
        since_time: int | None = None,
        before_time: int | None = None,
    ) -> dict:
        """Fetch global, nation, or region happenings/events.

        Args:
            view: Scope filter — 'nation.NATION_NAME' for single nation,
                'nation.name1,name2' for multiple nations,
                'region.REGION_NAME' for single region,
                'region.name1,name2' for multiple regions.
                Omit for global happenings.
            event_filter: Event types to include — any of: law, change,
                dispatch, rmb, embassy, eject, admin, move, founding, cte,
                vote, resolution, member, endo.
            limit: Maximum number of events to return.
            since_id: Only events with higher EVENT ID than this.
            before_id: Only events with older EVENT ID than this.
            since_time: Unix timestamp — only events newer than this.
            before_time: Unix timestamp — only events older than this.

        Returns:
            {"happenings": [{"event_id": "1001", "timestamp": "1720000000",
                              "text": "@@nation@@ did something"}, ...]}
        """
        try:
            kwargs: dict[str, str] = {}

            if view is not None:
                kwargs["view"] = view

            if event_filter:
                kwargs["filter"] = "+".join(event_filter)

            if limit is not None:
                kwargs["limit"] = str(limit)

            # since_id and before_id are mutually exclusive
            if since_id is not None:
                kwargs["sinceid"] = str(since_id)
            elif before_id is not None:
                kwargs["beforeid"] = str(before_id)

            # since_time and before_time are mutually exclusive
            if since_time is not None:
                kwargs["sincetime"] = str(since_time)
            elif before_time is not None:
                kwargs["beforetime"] = str(before_time)

            async with NationStatesClient(user_agent=USER_AGENT) as client:
                data = await client.get_world(shards=["happenings"], **kwargs)
            return data

        except NSRateLimitError as exc:
            return {
                "error": f"Rate limited: {exc.detail}",
                "recoverable": True,
                "retry_after": exc.retry_after,
            }
        except NSAPIError as exc:
            return {
                "error": f"API error: {exc.detail}",
                "recoverable": exc.recoverable,
                "status_code": exc.status_code,
            }
        except Exception as exc:
            logger.exception("Unexpected error in ns_get_happenings")
            return {"error": f"Unexpected error: {exc}", "recoverable": False}
