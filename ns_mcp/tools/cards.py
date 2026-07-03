"""Trading Cards API tools for the NationStates MCP server."""

import os
from ns_mcp.auth import AuthManager
from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAuthError, NSAPIError, NSRateLimitError, NSCommandError

# Valid card shards (used with the 'card+' prefix query).
VALID_CARD_SHARDS = {"info", "markets", "owners", "trades"}

# Valid deck queries (used with the 'cards+' prefix query).
VALID_DECK_QUERIES = {"deck", "info", "asksbids", "collections"}


def _build_client(
    password: str | None = None,
    autologin: str | None = None,
) -> NationStatesClient:
    """Create an authenticated NationStatesClient for private commands."""
    auth = AuthManager(
        password=password or os.getenv("NS_PASSWORD"),
        autologin=autologin or os.getenv("NS_AUTOLOGIN"),
    )
    return NationStatesClient(user_agent="ns-mcp/0.1.0", auth_manager=auth)


def register_tools(mcp) -> None:
    """Register all trading-cards-related tools with the MCP server."""

    @mcp.tool()
    async def ns_get_card(
        card_id: int,
        season: int,
        shards: list[str],
    ) -> dict:
        """Fetch trading card data by card ID and season.

        Args:
            card_id: The card's numeric ID (e.g. 1 for the first card).
            season: The card season number (1, 2, or 3).
            shards: Data to fetch -- choose from: 'info', 'markets',
                   'owners', 'trades'. Multiple shards can be combined.

        Returns:
            Card data dict with requested information.

        Example return:
            {"cards": {
                "card": {
                    "name": "Testlandia",
                    "category": "Nation",
                    "season": "1",
                    ...
                }
            }}
        """
        if season not in (1, 2, 3):
            return {
                "error": "invalid_season",
                "detail": f"Season must be 1, 2, or 3, got {season}",
            }

        invalid = [s for s in shards if s not in VALID_CARD_SHARDS]
        if invalid:
            return {
                "error": "invalid_shards",
                "detail": f"Unknown shards: {', '.join(invalid)}",
                "valid_shards": sorted(VALID_CARD_SHARDS),
            }

        client = NationStatesClient(user_agent="ns-mcp/0.1.0")
        try:
            await client.start()
            result = await client.get_cards({
                "q": "card+" + "+".join(shards),
                "cardid": str(card_id),
                "season": str(season),
            })
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
    async def ns_get_cards_deck(
        nation: str,
        query: str,
    ) -> dict:
        """Fetch a nation's card deck or related card info.

        Args:
            nation: Nation name (case-insensitive, underscores for spaces).
            query: What to fetch from the card system:
                   - 'deck': List of cards owned by the nation.
                   - 'info': Owner info / card stats.
                   - 'asksbids': Active buy/sell orders by the nation.
                   - 'collections': Collections owned by the nation.

        Returns:
            Card deck data.

        Example return:
            {"cards": {
                "deck": [
                    {"cardid": "1", "season": "1", "name": "Testlandia", ...},
                    ...
                ]
            }}
        """
        if query not in VALID_DECK_QUERIES:
            return {
                "error": "invalid_query",
                "detail": f"Query must be one of: {', '.join(sorted(VALID_DECK_QUERIES))}, got '{query}'",
                "valid_queries": sorted(VALID_DECK_QUERIES),
            }

        client = NationStatesClient(user_agent="ns-mcp/0.1.0")
        try:
            await client.start()
            result = await client.get_cards({
                "q": "cards+" + query,
                "nationname": nation,
            })
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
    async def ns_gift_card(
        nation: str,
        card_id: int,
        season: int,
        to_nation: str,
        password: str | None = None,
        autologin: str | None = None,
        pin: str | None = None,
    ) -> dict:
        """Gift a trading card to another nation. TWO-STEP authenticated command.

        You must own the card you wish to gift. Authentication is required
        -- provide credentials via parameters or NS_PASSWORD/NS_AUTOLOGIN
        environment variables.

        Args:
            nation: Your nation name (must own the card).
            card_id: Card ID to gift.
            season: Card season number.
            to_nation: Recipient nation name.
            password: Your nation's password (or set NS_PASSWORD env var).
            autologin: Autologin token (or set NS_AUTOLOGIN env var).
            pin: X-Pin token (automatically managed, rarely needed manually).

        Returns:
            {"ok": True/False, "description": "Success/failure message"}
        """
        if season not in (1, 2, 3):
            return {
                "error": "invalid_season",
                "detail": f"Season must be 1, 2, or 3, got {season}",
            }

        client = _build_client(password=password, autologin=autologin)
        try:
            await client.start()
            result = await client.execute_command(
                nation=nation,
                command="giftcard",
                params={
                    "cardid": str(card_id),
                    "season": str(season),
                    "to": to_nation,
                },
                two_step=True,
            )
            # Determine success from the response
            return {
                "ok": True,
                "description": "Card gifted successfully",
                "response": result,
            }
        except NSCommandError as e:
            return {
                "error": "command_error",
                "detail": str(e),
                "step": e.step,
            }
        except NSAuthError as e:
            return {
                "error": "auth_error",
                "detail": str(e),
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
        except Exception as e:
            return {
                "error": "unexpected",
                "detail": str(e),
            }
        finally:
            await client.close()

    @mcp.tool()
    async def ns_junk_card(
        nation: str,
        card_id: int,
        season: int,
        password: str | None = None,
        autologin: str | None = None,
        pin: str | None = None,
    ) -> dict:
        """Junk/destroy a trading card. TWO-STEP authenticated command.

        Permanently removes the card from your deck. Authentication is
        required -- provide credentials via parameters or NS_PASSWORD/
        NS_AUTOLOGIN environment variables.

        Args:
            nation: Your nation name (must own the card).
            card_id: Card ID to junk.
            season: Card season number.
            password: Your nation's password (or set NS_PASSWORD env var).
            autologin: Autologin token (or set NS_AUTOLOGIN env var).
            pin: X-Pin token (automatically managed, rarely needed manually).

        Returns:
            {"ok": True/False, "description": "Success/failure message"}
        """
        if season not in (1, 2, 3):
            return {
                "error": "invalid_season",
                "detail": f"Season must be 1, 2, or 3, got {season}",
            }

        client = _build_client(password=password, autologin=autologin)
        try:
            await client.start()
            result = await client.execute_command(
                nation=nation,
                command="junkcard",
                params={
                    "cardid": str(card_id),
                    "season": str(season),
                },
                two_step=True,
            )
            return {
                "ok": True,
                "description": "Card junked successfully",
                "response": result,
            }
        except NSCommandError as e:
            return {
                "error": "command_error",
                "detail": str(e),
                "step": e.step,
            }
        except NSAuthError as e:
            return {
                "error": "auth_error",
                "detail": str(e),
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
        except Exception as e:
            return {
                "error": "unexpected",
                "detail": str(e),
            }
        finally:
            await client.close()
