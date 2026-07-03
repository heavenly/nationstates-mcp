"""Nation API tools for the NationStates MCP server.

Provides five MCP tools that wrap the NationStates nation-related API
endpoints.  Handles shard validation, authentication, credential fallback,
and structured error responses.

Usage::

    from ns_mcp.tools.nation import register_tools

    mcp = FastMCP("ns-mcp")
    register_tools(mcp)
    mcp.run()
"""

from __future__ import annotations

import os
from typing import Any

from ns_mcp.auth import AuthManager
from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAuthError, NSAPIError, NSRateLimitError

# ---------------------------------------------------------------------------
# Shard-name catalogs
# ---------------------------------------------------------------------------

PUBLIC_SHARDS: set[str] = {
    "admirable",
    "admirables",
    "animal",
    "animaltrait",
    "answered",
    "banner",
    "banners",
    "capital",
    "category",
    "census",
    "crime",
    "currency",
    "customleader",
    "customcapital",
    "customreligion",
    "dbid",
    "deaths",
    "demonym",
    "demonym2",
    "demonym2plural",
    "dispatches",
    "dispatchlist",
    "endorsements",
    "factbooks",
    "factbooklist",
    "firstlogin",
    "flag",
    "founded",
    "foundedtime",
    "freedom",
    "fullname",
    "gavote",
    "gdp",
    "govt",
    "govtdesc",
    "govtpriority",
    "happenings",
    "income",
    "industrydesc",
    "influence",
    "influencenum",
    "lastactivity",
    "lastlogin",
    "leader",
    "legislation",
    "majorindustry",
    "motto",
    "name",
    "notable",
    "notables",
    "nstats",
    "policies",
    "poorest",
    "population",
    "publicsector",
    "rcensus",
    "region",
    "religion",
    "richest",
    "sectors",
    "sensibilities",
    "scvote",
    "tax",
    "tgcanrecruit",
    "tgcancampaign",
    "type",
    "wa",
    "wabadges",
    "wcensus",
    "zombie",
}

PRIVATE_SHARDS: set[str] = {
    "dossier",
    "issues",
    "issuesummary",
    "nextissue",
    "nextissuetime",
    "notices",
    "packs",
    "ping",
    "rdossier",
    "unread",
}

ALL_SHARDS: set[str] = PUBLIC_SHARDS | PRIVATE_SHARDS

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_client(
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> NationStatesClient:
    """Create a client with credential fallback chain.

    Credentials are resolved in this priority order:
      1. Explicit function argument
      2. ``NS_PASSWORD`` / ``NS_AUTOLOGIN`` environment variable

    The X-Pin is managed automatically by the auth manager (disk cache +
    response-header capture), but an explicit *pin* can be provided to
    bypass the cache.

    Args:
        password: Nation password (falls back to ``NS_PASSWORD`` env var).
        autologin: Autologin token (falls back to ``NS_AUTOLOGIN`` env var).
        pin: Explicit X-Pin value (bypasses disk cache).

    Returns:
        A configured but *not yet started* :class:`NationStatesClient`.
    """
    auth = AuthManager(
        password=password if password is not None else os.getenv("NS_PASSWORD"),
        autologin=autologin if autologin is not None else os.getenv("NS_AUTOLOGIN"),
    )
    if pin is not None:
        # Bypass disk cache — set the pin directly on the auth manager.
        object.__setattr__(auth, "_pin", pin)

    return NationStatesClient(
        user_agent="ns-mcp/0.1.0",
        auth_manager=auth,
    )


def _has_credentials(password: str | None, autologin: str | None) -> bool:
    """Return ``True`` if any credential source is available."""
    return bool(
        password
        or autologin
        or os.getenv("NS_PASSWORD")
        or os.getenv("NS_AUTOLOGIN"),
    )


def _error_response(error_type: str, detail: str, **extra: Any) -> dict[str, Any]:
    """Build a structured error dict for tool return."""
    result: dict[str, Any] = {"error": error_type, "detail": detail}
    result.update(extra)
    return result


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def ns_get_nation(
    nation: str,
    shards: list[str],
    census_scale: str | None = None,
    census_mode: str | None = None,
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> dict:
    """Fetch nation data from NationStates by shard.

    Args:
        nation: The nation name (case-insensitive).
        shards: List of shard names, e.g. ``["population", "region", "flag"]``.
        census_scale: Census scale IDs (use ``'+'`` to combine, or ``'all'``).
        census_mode: Census mode(s) — ``score``, ``rank``, ``rrank``,
            ``prank``, ``prrank``.
        password: Nation password (or set ``NS_PASSWORD`` env var).
        autologin: Autologin token (or set ``NS_AUTOLOGIN`` env var).
        pin: X-Pin session token (cached automatically).

    Returns:
        Dict with requested nation data.  The top-level ``"nation"`` key
        from the raw XML response is unwrapped for convenience::

            {"population": "15.432", "region": "The North Pacific", ...}
    """
    # -- Validate shards -------------------------------------------------------
    unknown = set(shards) - ALL_SHARDS
    if unknown:
        return _error_response(
            "invalid_shards",
            f"Unknown shard(s): {sorted(unknown)}. "
            f"See ``valid_shards`` for the full list.",
            valid_shards=sorted(ALL_SHARDS),
        )

    # -- Auth check (private shards need credentials) --------------------------
    needs_auth = bool(set(shards) & PRIVATE_SHARDS)
    if needs_auth and not _has_credentials(password, autologin):
        return _error_response(
            "auth_required",
            "One or more requested shards require authentication "
            "(password or autologin token). Provide ``password`` "
            "or ``autologin``, or set the ``NS_PASSWORD`` / "
            "``NS_AUTOLOGIN`` environment variables.",
        )

    client = _build_client(password=password, autologin=autologin, pin=pin)

    try:
        await client.start()
        raw = await client.get_nation(
            nation=nation,
            shards=shards,
            census_scale=census_scale,
            census_mode=census_mode,
        )
        # Unwrap the ``{"nation": {...}}`` wrapper for a cleaner response.
        return raw.get("nation", raw)
    except NSAuthError as e:
        return _error_response("auth_failed", str(e))
    except NSRateLimitError as e:
        return _error_response(
            "rate_limited", str(e), retry_after=e.retry_after,
        )
    except NSAPIError as e:
        return _error_response(
            "api_error", str(e), status_code=e.status_code,
        )
    except Exception as e:
        return _error_response("unexpected", str(e))
    finally:
        await client.close()


async def ns_get_nation_issues(
    nation: str,
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> dict:
    """Get list of pending issues for a nation.

    Requires authentication.

    Args:
        nation: The nation name (case-insensitive).
        password: Nation password (or set ``NS_PASSWORD`` env var).
        autologin: Autologin token (or set ``NS_AUTOLOGIN`` env var).
        pin: X-Pin session token (cached automatically).

    Returns:
        ``{"issues": [{"id": 123, "title": "..."}, ...]}``
    """
    if not _has_credentials(password, autologin):
        return _error_response(
            "auth_required",
            "Fetching issues requires authentication. Provide ``password`` "
            "or ``autologin``, or set the ``NS_PASSWORD`` / "
            "``NS_AUTOLOGIN`` environment variables.",
        )

    client = _build_client(password=password, autologin=autologin, pin=pin)

    try:
        await client.start()
        raw = await client.api_get({"nation": nation, "c": "issues"})

        # Parse the issues list from the XML -> dict response.
        issues_container = raw.get("issues", {})
        issues_raw = issues_container.get("issue", [])

        # Normalise to a list (single issue comes back as a bare dict).
        if isinstance(issues_raw, dict):
            issues_raw = [issues_raw]
        if not isinstance(issues_raw, list):
            issues_raw = [issues_raw] if issues_raw else []

        issues: list[dict[str, Any]] = []
        for issue in issues_raw:
            if isinstance(issue, str):
                # Fallback for old parser behaviour (bare string)
                issues.append({"id": 0, "title": issue})
                continue
            iid = issue.get("@id", "")
            title = issue.get("#text") or issue.get("title", "")
            try:
                issues.append({"id": int(iid), "title": title})
            except (ValueError, TypeError):
                issues.append({"id": iid, "title": title})

        return {"issues": issues}
    except NSAuthError as e:
        return _error_response("auth_failed", str(e))
    except NSRateLimitError as e:
        return _error_response(
            "rate_limited", str(e), retry_after=e.retry_after,
        )
    except NSAPIError as e:
        return _error_response(
            "api_error", str(e), status_code=e.status_code,
        )
    except Exception as e:
        return _error_response("unexpected", str(e))
    finally:
        await client.close()


async def ns_get_nation_issue(
    nation: str,
    issue_id: int,
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> dict:
    """Get full text and options for a single issue.

    Requires authentication.

    Args:
        nation: The nation name (case-insensitive).
        issue_id: The issue ID number.
        password: Nation password (or set ``NS_PASSWORD`` env var).
        autologin: Autologin token (or set ``NS_AUTOLOGIN`` env var).
        pin: X-Pin session token (cached automatically).

    Returns:
        Issue detail dict::

            {"issue_id": 123, "title": "...", "text": "...",
             "options": [{"id": 0, "text": "..."}, ...], "deadline": "..."}
    """
    if not _has_credentials(password, autologin):
        return _error_response(
            "auth_required",
            "Fetching an issue requires authentication. Provide ``password`` "
            "or ``autologin``, or set the ``NS_PASSWORD`` / "
            "``NS_AUTOLOGIN`` environment variables.",
        )

    client = _build_client(password=password, autologin=autologin, pin=pin)

    try:
        await client.start()
        raw = await client.api_get({
            "nation": nation,
            "c": "issue",
            "id": str(issue_id),
        })

        issue = raw.get("issue", {})

        # Parse options
        options_raw = issue.get("option", [])
        if isinstance(options_raw, dict):
            options_raw = [options_raw]

        options: list[dict[str, Any]] = []
        for opt in options_raw:
            oid = opt.get("@id", "")
            otext = opt.get("text", "")
            try:
                options.append({"id": int(oid), "text": otext})
            except (ValueError, TypeError):
                options.append({"id": oid, "text": otext})

        return {
            "issue_id": issue.get("@id", issue_id),
            "title": issue.get("title", ""),
            "text": issue.get("text", ""),
            "options": options,
            "deadline": issue.get("deadline", ""),
            "author": issue.get("author", ""),
            "editor": issue.get("editor", ""),
            "picture": issue.get("picture", ""),
        }
    except NSAuthError as e:
        return _error_response("auth_failed", str(e))
    except NSRateLimitError as e:
        return _error_response(
            "rate_limited", str(e), retry_after=e.retry_after,
        )
    except NSAPIError as e:
        return _error_response(
            "api_error", str(e), status_code=e.status_code,
        )
    except Exception as e:
        return _error_response("unexpected", str(e))
    finally:
        await client.close()


async def ns_answer_issue(
    nation: str,
    issue_id: int,
    option_id: int,
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> dict:
    """Answer a pending issue. Use ``option_id=-1`` to dismiss.

    Requires authentication.  This is a single-step command (no prepare /
    execute split).

    Args:
        nation: The nation name (case-insensitive).
        issue_id: The issue ID number.
        option_id: The option ID to select (``-1`` to dismiss).
        password: Nation password (or set ``NS_PASSWORD`` env var).
        autologin: Autologin token (or set ``NS_AUTOLOGIN`` env var).
        pin: X-Pin session token (cached automatically).

    Returns:
        Dict with the outcome::

            {"ok": True, "description": "...", "rankings": {...},
             "unlocks": [...], "reclassifications": [...],
             "new_policies": {...}, "removed_policies": {...}}
    """
    if not _has_credentials(password, autologin):
        return _error_response(
            "auth_required",
            "Answering an issue requires authentication. Provide "
            "``password`` or ``autologin``, or set the ``NS_PASSWORD`` "
            "/ ``NS_AUTOLOGIN`` environment variables.",
        )

    client = _build_client(password=password, autologin=autologin, pin=pin)

    try:
        await client.start()
        raw = await client.execute_command(
            nation=nation,
            command="issue",
            params={"issue": str(issue_id), "option": str(option_id)},
            two_step=False,
        )

        issue = raw.get("issue", raw)

        # Parse census-score rankings
        rankings_raw = issue.get("ranking", {})
        rankings: dict[str, str] = {}
        scores = rankings_raw.get("score", [])
        if isinstance(scores, dict):
            scores = [scores]
        for score in scores:
            sid = score.get("@id", "")
            value = score.get("", None) or score.get("text", "")
            rankings[str(sid) if sid else "?"] = str(value) if value else ""

        # Normalise list fields
        unlocks_raw = issue.get("unlock", [])
        if isinstance(unlocks_raw, str):
            unlocks: list[str] = [unlocks_raw]
        elif isinstance(unlocks_raw, list):
            unlocks = [str(u) for u in unlocks_raw]
        else:
            unlocks = []

        reclassifications_raw = issue.get("reclassification", [])
        if isinstance(reclassifications_raw, str):
            reclassifications: list[str] = [reclassifications_raw]
        elif isinstance(reclassifications_raw, list):
            reclassifications = [str(r) for r in reclassifications_raw]
        else:
            reclassifications = []

        new_policies = issue.get("newpolicy", {})
        removed_policies = issue.get("removedpolicy", {})

        return {
            "ok": True,
            "description": issue.get("description", ""),
            "rankings": rankings,
            "unlocks": unlocks,
            "reclassifications": reclassifications,
            "new_policies": new_policies if isinstance(new_policies, dict) else {},
            "removed_policies": removed_policies if isinstance(removed_policies, dict) else {},
        }
    except NSAuthError as e:
        return _error_response("auth_failed", str(e))
    except NSRateLimitError as e:
        return _error_response(
            "rate_limited", str(e), retry_after=e.retry_after,
        )
    except NSAPIError as e:
        return _error_response(
            "api_error", str(e), status_code=e.status_code,
        )
    except Exception as e:
        return _error_response("unexpected", str(e))
    finally:
        await client.close()


async def ns_get_nation_notices(
    nation: str,
    from_timestamp: str | None = None,
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> dict:
    """Get unread notices for a nation.

    Requires authentication (notices is a private shard).

    Args:
        nation: The nation name (case-insensitive).
        from_timestamp: Unix timestamp — only fetch notices newer than this.
        password: Nation password (or set ``NS_PASSWORD`` env var).
        autologin: Autologin token (or set ``NS_AUTOLOGIN`` env var).
        pin: X-Pin session token (cached automatically).

    Returns:
        Dict with notices data, unwrapped from the ``"nation"`` key::

            {"notices": {"notice": [...]}, ...}
    """
    if not _has_credentials(password, autologin):
        return _error_response(
            "auth_required",
            "Fetching notices requires authentication. Provide ``password`` "
            "or ``autologin``, or set the ``NS_PASSWORD`` / "
            "``NS_AUTOLOGIN`` environment variables.",
        )

    client = _build_client(password=password, autologin=autologin, pin=pin)

    try:
        await client.start()
        params: dict[str, str] = {"nation": nation, "q": "notices"}
        if from_timestamp is not None:
            params["from"] = from_timestamp

        raw = await client.api_get(params)
        # Unwrap the ``{"nation": {...}}`` wrapper.
        return raw.get("nation", raw)
    except NSAuthError as e:
        return _error_response("auth_failed", str(e))
    except NSRateLimitError as e:
        return _error_response(
            "rate_limited", str(e), retry_after=e.retry_after,
        )
    except NSAPIError as e:
        return _error_response(
            "api_error", str(e), status_code=e.status_code,
        )
    except Exception as e:
        return _error_response("unexpected", str(e))
    finally:
        await client.close()


# ---- Private commands (two-step prepare/execute) -------------------------


async def ns_manage_dispatch(
    nation: str,
    action: str,
    title: str,
    text: str,
    category: int,
    subcategory: int,
    dispatch_id: int | None = None,
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> dict:
    """Create, edit, or remove a dispatch. TWO-STEP authenticated command.

    Args:
        nation: Your nation name.
        action: One of ``'add'``, ``'edit'``, or ``'remove'``.
        title: Dispatch title.
        text: Dispatch body text (BBCode allowed).
        category: Dispatch category number.
        subcategory: Dispatch subcategory number.
        dispatch_id: Required for ``'edit'`` and ``'remove'`` actions.
        password: Nation password (or set ``NS_PASSWORD`` env var).
        autologin: Autologin token (or set ``NS_AUTOLOGIN`` env var).
        pin: X-Pin session token (cached automatically).

    Returns:
        ``{"ok": True/False, "description": "..."}``
    """
    if action not in ("add", "edit", "remove"):
        return _error_response(
            "invalid_action",
            f"Action must be 'add', 'edit', or 'remove', got '{action}'",
        )
    if action in ("edit", "remove") and dispatch_id is None:
        return _error_response(
            "missing_dispatch_id",
            f"dispatch_id is required for action '{action}'",
        )
    if not _has_credentials(password, autologin):
        return _error_response(
            "auth_required",
            "Dispatch management requires authentication. Provide "
            "``password`` or ``autologin``, or set the ``NS_PASSWORD`` / "
            "``NS_AUTOLOGIN`` environment variables.",
        )

    client = _build_client(password=password, autologin=autologin, pin=pin)
    try:
        await client.start()
        cmd_params: dict[str, str] = {
            "dispatch": action,
            "title": title,
            "text": text,
            "category": str(category),
            "subcategory": str(subcategory),
        }
        if dispatch_id is not None:
            cmd_params["dispatchid"] = str(dispatch_id)

        result = await client.execute_command(
            nation, "dispatch", cmd_params, two_step=True
        )
        return result
    except NSAuthError as e:
        return _error_response("auth_failed", str(e))
    except NSRateLimitError as e:
        return _error_response(
            "rate_limited", str(e), retry_after=e.retry_after,
        )
    except NSAPIError as e:
        return _error_response(
            "api_error", str(e), status_code=e.status_code,
        )
    except Exception as e:
        return _error_response("unexpected", str(e))
    finally:
        await client.close()


async def ns_post_rmb(
    nation: str,
    region: str,
    text: str,
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> dict:
    """Post to a regional message board (RMB). TWO-STEP authenticated command.

    Args:
        nation: Your nation name.
        region: Target region name.
        text: Message text (BBCode allowed).
        password: Nation password (or set ``NS_PASSWORD`` env var).
        autologin: Autologin token (or set ``NS_AUTOLOGIN`` env var).
        pin: X-Pin session token (cached automatically).

    Returns:
        ``{"ok": True/False, "description": "..."}``
    """
    if not _has_credentials(password, autologin):
        return _error_response(
            "auth_required",
            "RMB posting requires authentication. Provide ``password`` "
            "or ``autologin``, or set the ``NS_PASSWORD`` / "
            "``NS_AUTOLOGIN`` environment variables.",
        )

    client = _build_client(password=password, autologin=autologin, pin=pin)
    try:
        await client.start()
        result = await client.execute_command(
            nation, "rmbpost", {
                "nation": nation,
                "region": region,
                "text": text,
            }, two_step=True
        )
        return result
    except NSAuthError as e:
        return _error_response("auth_failed", str(e))
    except NSRateLimitError as e:
        return _error_response(
            "rate_limited", str(e), retry_after=e.retry_after,
        )
    except NSAPIError as e:
        return _error_response(
            "api_error", str(e), status_code=e.status_code,
        )
    except Exception as e:
        return _error_response("unexpected", str(e))
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_tools(mcp) -> None:
    """Register all nation-related tools with the MCP server.

    Call this during server initialisation::

        from ns_mcp.tools.nation import register_tools

        mcp = FastMCP("ns-mcp")
        register_tools(mcp)
        mcp.run()

    Each tool is registered using the ``mcp.tool()`` method with an
    explicit ``name`` so the tool name is independent of the Python
    function name.
    """
    mcp.tool(name="ns_get_nation")(ns_get_nation)
    mcp.tool(name="ns_get_nation_issues")(ns_get_nation_issues)
    mcp.tool(name="ns_get_nation_issue")(ns_get_nation_issue)
    mcp.tool(name="ns_answer_issue")(ns_answer_issue)
    mcp.tool(name="ns_get_nation_notices")(ns_get_nation_notices)
    mcp.tool(name="ns_manage_dispatch")(ns_manage_dispatch)
    mcp.tool(name="ns_post_rmb")(ns_post_rmb)
