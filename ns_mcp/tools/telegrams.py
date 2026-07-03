"""Telegram API tools for the NationStates MCP server."""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from typing import Any

from ns_mcp.auth import AuthManager
from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAuthError, NSAPIError, NSRateLimitError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(
    password: str | None = None,
    autologin: str | None = None,
    pin: str | None = None,
) -> NationStatesClient:
    """Create an authenticated client with credential fallback to env vars."""
    auth = AuthManager(
        password=password if password is not None else os.getenv("NS_PASSWORD"),
        autologin=autologin if autologin is not None else os.getenv("NS_AUTOLOGIN"),
    )
    if pin is not None:
        object.__setattr__(auth, "_pin", pin)
    return NationStatesClient(user_agent="ns-mcp/0.1.0", auth_manager=auth)


def _has_credentials(password: str | None, autologin: str | None) -> bool:
    """Return True if any credential source is available."""
    return bool(
        password
        or autologin
        or os.getenv("NS_PASSWORD")
        or os.getenv("NS_AUTOLOGIN"),
    )


def _error_response(error_type: str, detail: str, **extra: Any) -> dict[str, Any]:
    """Build a structured error dict."""
    result: dict[str, Any] = {"error": error_type, "detail": detail}
    result.update(extra)
    return result


# ---- Telegram page HTML parser ----------------------------------------------

# The NS telegram page at /page=tg/id=N contains:
#   <p class="tg-sender">From: <a ...>NationName</a></p>
#   <div class="tg-content">Telegram body...</div>
#   <p class="tg-subject">Subject line</p>
#   <time>Timestamp</time>

class _TelegramPageParser(HTMLParser):
    """Extract telegram data from the NationStates telegram page."""

    def __init__(self) -> None:
        super().__init__()
        self.sender: str = ""
        self.subject: str = ""
        self.body: str = ""
        self.timestamp: str = ""
        self._in_message: bool = False
        self._in_subject: bool = False
        self._in_sender: bool = False
        self._current_data: str = ""
        self._body_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        if tag == "div" and "ladder" in cls:
            self._in_message = True
        elif tag == "p" and cls == "reading-subject":
            self._in_subject = True
        elif tag == "p" and cls == "reading-head":
            self._in_sender = True

    def handle_endtag(self, tag: str) -> None:
        if self._in_message and tag == "div":
            self._in_message = False
            self.body = "\n".join(self._body_parts).strip()
        elif self._in_subject and tag == "p":
            self._in_subject = False
        elif self._in_sender and tag == "p":
            self._in_sender = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_subject:
            self.subject = text
        elif self._in_sender:
            # Extract just the nation name from "From: NationName"
            text = text.replace("From:", "").strip()
            if text:
                self.sender = text
        elif self._in_message:
            self._body_parts.append(data)

    def error(self, message: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp) -> None:
    """Register all telegram-related tools with the MCP server."""

    @mcp.tool()
    async def ns_read_telegrams(
        nation: str,
        telegram_id: str | None = None,
        password: str | None = None,
        autologin: str | None = None,
        pin: str | None = None,
    ) -> dict:
        """Read telegrams for a nation. Requires authentication.

        Without ``telegram_id``: returns a list of recent telegram metadata
        (from the notices feed — subject, sender, timestamp, id).

        With ``telegram_id``: fetches and returns the **full content** of a
        specific telegram (sender, subject, body, timestamp).

        Args:
            nation: Your nation name.
            telegram_id: Optional — a specific telegram/notice ID to read
                in full.  Get IDs from the list returned when calling
                without this parameter.
            password: Nation password (or set ``NS_PASSWORD`` env var).
            autologin: Autologin token (or set ``NS_AUTOLOGIN`` env var).
            pin: X-Pin session token (cached automatically).

        Returns (list mode):
            {"telegrams": [{"id": 123, "subject": "...", "sender": "...",
              "timestamp": 1720000000, "type": "telegram"}, ...]}

        Returns (single mode):
            {"id": 123, "subject": "...", "sender": "...",
             "body": "Full message text...", "timestamp": "..."}
        """
        if not _has_credentials(password, autologin):
            return _error_response(
                "auth_required",
                "Reading telegrams requires authentication. Provide "
                "``password`` or ``autologin``, or set the "
                "``NS_PASSWORD`` / ``NS_AUTOLOGIN`` environment variables.",
            )

        client = _build_client(password=password, autologin=autologin, pin=pin)
        try:
            await client.start()

            # ---- Single telegram: scrape the page ----------------------------
            if telegram_id is not None:
                # Fetch the telegram page (requires authentication via X-Pin)
                page_url = (
                    f"https://www.nationstates.net/page=tg/id={telegram_id}"
                )
                auth_headers = client._auth.auth_headers()
                response = await client.client.get(
                    page_url, headers=auth_headers
                )

                if response.status_code != 200:
                    return _error_response(
                        "api_error",
                        f"Failed to read telegram (HTTP {response.status_code})",
                        status_code=response.status_code,
                    )

                # Parse the HTML to extract telegram content
                parser_cte = _TelegramPageParser()
                parser_cte.feed(response.text)

                return {
                    "id": telegram_id,
                    "subject": parser_cte.subject,
                    "sender": parser_cte.sender,
                    "body": parser_cte.body,
                    "timestamp": parser_cte.timestamp,
                }

            # ---- List mode: get recent telegrams from notices ----------------
            raw = await client.api_get({"nation": nation, "q": "notices"})
            nation_data = raw.get("nation", raw)
            notices = nation_data.get("notices", [])

            # Filter for telegram-type notices only
            telegrams: list[dict[str, Any]] = []
            for notice in notices:
                if isinstance(notice, dict) and notice.get("type") == "telegram":
                    telegrams.append(notice)

            return {"telegrams": telegrams}

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
