"""Asynchronous HTTP client for the NationStates API.

Provides a single-funnel :meth:`api_get` method that handles authentication,
rate limiting, error classification, and XML-to-dict parsing.  Convenience
methods on top of it mirror the NS API's shard categories.

Usage::

    from mcp.ns_mcp.auth import AuthManager
    from mcp.ns_mcp.client import NationStatesClient

    async with NationStatesClient("my-app/1.0") as client:
        data = await client.get_nation("testlandia", shards=["population"])
        print(data)
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from .auth import AuthManager
from .exceptions import NSAuthError, NSAPIError, NSCommandError, NSRateLimitError
from .ratelimit import TelegramRateLimiter, get_shared_bucket

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# XML parsing helper (temporary – Package B will provide specialised parsers)
# ---------------------------------------------------------------------------

def _element_to_dict(element: ET.Element) -> Any:
    """Recursively convert an XML element to a plain Python object.

    * Attributes become ``@{key}`` entries in the dict.
    * Child elements are converted recursively.
    * Multiple children with the same tag become a list.
    * Elements with only text content return that text (as a string).
    * Empty elements return ``""``.
    """
    children = list(element)
    text = (element.text or "").strip()

    if not children:
        # Leaf element — return text, but if it has attributes return a dict
        if not element.attrib:
            return text if text else ""
        result: dict[str, Any] = {}
        for key, val in element.attrib.items():
            result[f"@{key}"] = val
        if text:
            result["#text"] = text
        return result

    result: dict[str, Any] = {}
    if element.attrib:
        for key, val in element.attrib.items():
            result[f"@{key}"] = val

    for child in children:
        tag = child.tag.lower()
        child_data = _element_to_dict(child)

        if tag in result:
            existing = result[tag]
            if not isinstance(existing, list):
                result[tag] = [existing]
            result[tag].append(child_data)
        else:
            result[tag] = child_data

    return result


def _parse_xml(xml: str) -> dict[str, Any]:
    """Parse NS API XML response into a nested dict.

    The root element tag (lowercased) becomes the top-level key::

        <NATION id="testlandia">
          <NAME>Testlandia</NAME>
          <POPULATION>1234</POPULATION>
        </NATION>

    yields::

        {"nation": {"@id": "testlandia", "name": "Testlandia", "population": "1234"}}
    """
    root = ET.fromstring(xml)
    data = _element_to_dict(root)
    return {root.tag.lower(): data}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class NationStatesClient:
    """Async HTTP client for the NationStates API.

    Handles authentication, rate limiting, error classification and basic
    XML parsing.  The :meth:`api_get` method is the single funnel all
    requests pass through; category convenience methods build parameter
    dicts and delegate to it.
    """

    API_BASE = "https://www.nationstates.net/cgi-bin/api.cgi"

    def __init__(
        self,
        user_agent: str,
        auth_manager: AuthManager | None = None,
        telegram_key: str | None = None,
    ) -> None:
        #: User-Agent string sent with every request (required by NS API).
        self._user_agent = user_agent

        #: Auth manager – created from env vars if not provided.
        self._auth = auth_manager if auth_manager is not None else AuthManager()

        #: Optional API telegram key (needed for send_telegram).
        self._telegram_key = telegram_key

        #: Shared token-bucket rate limiter.
        self._bucket = get_shared_bucket()

        #: Telegram-specific rate limiter.
        self._telegram_limiter = TelegramRateLimiter()

        self._client: httpx.AsyncClient | None = None

    # ---- Lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        """Open the underlying ``httpx.AsyncClient``.

        Must be called once before any requests (or use ``async with``).
        """
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self._user_agent},
            timeout=httpx.Timeout(30.0),
        )
        logger.info(
            "NationStatesClient started (user-agent: %s)", self._user_agent
        )

    async def close(self) -> None:
        """Close the underlying ``httpx.AsyncClient``."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("NationStatesClient closed")

    async def __aenter__(self) -> NationStatesClient:
        await self.start()
        return self

    async def __aexit__(self, *exc_args: Any) -> None:
        await self.close()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Client not started — call start() first")
        return self._client

    # ---- Core request funnel --------------------------------------------------

    async def api_get(self, params: dict[str, str]) -> dict[str, Any]:
        """Make an API call and return the parsed response.

        Handles:
        * Rate-limit token acquisition (shared bucket)
        * Auth headers (X-Pin / X-Password / X-Autologin)
        * X-Pin capture from response headers
        * Server rate-limit header observation
        * 403 → re-auth with raw credentials (once)
        * Error classification into domain exceptions
        * XML → dict parsing

        Args:
            params: Flat dict of query parameters, e.g.
                ``{"nation": "testlandia", "q": "population+region"}``.

        Returns:
            Parsed response dict (XML converted to nested dict).

        Raises:
            NSAuthError: On 403 after a single re-auth attempt.
            NSRateLimitError: On 429.
            NSAPIError: On other 4xx/5xx responses.
        """
        # 1. Acquire rate-limit token
        await self._bucket.acquire()

        # 2. Build request headers
        headers = {**self._auth.auth_headers()}

        logger.debug("API GET %s (headers: %s)", params, list(headers.keys()))

        # 3. Make the request
        response = await self.client.get(
            self.API_BASE, params=params, headers=headers
        )

        # 4. Always capture X-Pin (if present)
        self._auth.on_response(dict(response.headers))

        # 5. Observe rate-limit headers
        self._bucket.on_response(dict(response.headers))

        # 6. Handle 403 – clear pin, re-auth once with raw credentials, retry
        if response.status_code == 403:
            logger.warning("Got 403, clearing pin and retrying with raw credentials")
            self._auth.on_auth_failure()
            await self._bucket.acquire()
            retry_headers = {**self._auth.auth_headers()}
            response = await self.client.get(
                self.API_BASE, params=params, headers=retry_headers,
            )
            self._auth.on_response(dict(response.headers))
            self._bucket.on_response(dict(response.headers))

            if response.status_code == 403:
                raise NSAuthError(
                    "Authentication failed after re-auth attempt "
                    "(still 403 after clearing pin)"
                )

        # 7. Handle 429
        if response.status_code == 429:
            retry_after_str = response.headers.get("X-Retry-After", "0")
            try:
                retry_after = float(retry_after_str)
            except ValueError:
                retry_after = 0.0
            raise NSRateLimitError(
                f"Rate limited (429). Retry-After: {retry_after_str}",
                retry_after=retry_after,
            )

        # 8. Handle 400 / 409 (non-recoverable)
        if response.status_code == 400:
            raise NSAPIError(
                f"Bad Request (400): {response.text[:300]}",
                status_code=400,
                recoverable=False,
            )
        if response.status_code == 409:
            raise NSAPIError(
                f"Conflict (409): {response.text[:200]}",
                status_code=409,
                recoverable=False,
            )

        # 9. Handle other 4xx/5xx
        if response.status_code >= 400:
            raise NSAPIError(
                f"API error {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
                recoverable=True,
            )

        # 10. Parse XML → dict
        return _parse_xml(response.text)

    # ---- Category convenience methods -----------------------------------------

    async def get_nation(
        self,
        nation: str,
        shards: list[str] | None = None,
        census_scale: str | None = None,
        census_mode: str | None = None,
    ) -> dict:
        """Fetch one or more nation shards.

        Args:
            nation: Nation name.
            shards: List of shard names (e.g. ``["population", "region"]``).
                Joined with ``+`` to form the ``q`` parameter.
            census_scale: Optional census scale ID (e.g. ``"1"`` for
                "Wealth").
            census_mode: Optional census mode (e.g. ``"history"`` or
                ``"scale"``).

        Returns:
            Parsed response dict.
        """
        params: dict[str, str] = {"nation": nation}
        if shards:
            params["q"] = "+".join(shards)
        if census_scale is not None:
            params["scale"] = census_scale
        if census_mode is not None:
            params["mode"] = census_mode
        return await self.api_get(params)

    async def get_region(
        self,
        region: str,
        shards: list[str] | None = None,
        msg_limit: int | None = None,
        msg_offset: int | None = None,
        msg_fromid: int | None = None,
    ) -> dict:
        """Fetch one or more region shards.

        Args:
            region: Region name.
            shards: List of shard names.
            msg_limit: Max messages to return (used with ``messages`` shard).
            msg_offset: Message offset (used with ``messages`` shard).
            msg_fromid: Start message ID (used with ``messages`` shard).

        Returns:
            Parsed response dict.
        """
        params: dict[str, str] = {"region": region}
        if shards:
            params["q"] = "+".join(shards)
        if msg_limit is not None:
            params["limit"] = str(msg_limit)
        if msg_offset is not None:
            params["offset"] = str(msg_offset)
        if msg_fromid is not None:
            params["fromid"] = str(msg_fromid)
        return await self.api_get(params)

    async def get_world(
        self, shards: list[str], **kwargs: str
    ) -> dict:
        """Fetch world shards.

        Args:
            shards: List of shard names.
            **kwargs: Additional query parameters (e.g. ``census_scale=...``,
                ``happenings=...``).

        Returns:
            Parsed response dict.
        """
        params: dict[str, str] = {"world": "1", "q": "+".join(shards)}
        params.update(kwargs)
        return await self.api_get(params)

    async def get_wa(
        self,
        council: int,
        shards: list[str],
        resolution_id: int | None = None,
    ) -> dict:
        """Fetch World Assembly shards.

        Args:
            council: Council number (1 = General Assembly, 2 = Security
                Council).
            shards: List of shard names.
            resolution_id: Optional resolution ID for the ``del`` shard.

        Returns:
            Parsed response dict.
        """
        params: dict[str, str] = {
            "wa": str(council),
            "q": "+".join(shards),
        }
        if resolution_id is not None:
            params["id"] = str(resolution_id)
        return await self.api_get(params)

    async def execute_command(
        self,
        nation: str,
        command: str,
        params: dict[str, str],
        two_step: bool = True,
    ) -> dict:
        """Execute a private nation command.

        Two-step commands (the default) first send ``mode=prepare``, extract
        the security token from the response, then send
        ``mode=execute&token=...`` to commit the action.

        Single-step commands (e.g. answering an issue) are sent directly.

        Args:
            nation: Nation name.
            command: Command name (e.g. ``"issue"``, ``"dispatch"``).
            params: Additional command-specific parameters.
            two_step: Whether this is a two-step command.

        Returns:
            Parsed response dict from the execute (or only) step.

        Raises:
            NSCommandError: If the prepare step succeeds but no token is
                found in the response.
        """
        base_params: dict[str, str] = {"nation": nation, "c": command}
        base_params.update(params)

        if not two_step:
            return await self.api_get(base_params)

        # -- Two-step: prepare --
        prepare_params = dict(base_params)
        prepare_params["mode"] = "prepare"
        prepare_response = await self.api_get(prepare_params)

        # Extract token from the prepare response
        token = self._extract_token(prepare_response)
        if not token:
            raise NSCommandError(
                f"No token found in prepare response for command '{command}'",
                status_code=0,
                step="prepare",
            )

        # -- Two-step: execute --
        execute_params = dict(base_params)
        execute_params["mode"] = "execute"
        execute_params["token"] = token
        return await self.api_get(execute_params)

    async def send_telegram(
        self,
        client_key: str,
        tgid: str,
        secret_key: str,
        to_nation: str,
    ) -> dict:
        """Send an API telegram.

        Uses the :class:`TelegramRateLimiter` to respect per-client-key
        timing limits separately from the shared token bucket.

        Args:
            client_key: Your API client key.
            tgid: Telegram ID to send.
            secret_key: The telegram's secret key.
            to_nation: Target nation name.

        Returns:
            Parsed response dict.
        """
        await self._telegram_limiter.acquire(client_key, is_recruitment=False)

        params: dict[str, str] = {
            "a": "telegram",
            "tgid": tgid,
            "key": secret_key,
            "to": to_nation,
            "client_key": client_key,
        }
        return await self.api_get(params)

    async def verify_nation(
        self,
        nation: str,
        checksum: str,
        token: str | None = None,
        shards: list[str] | None = None,
    ) -> dict:
        """Verify nation ownership.

        Args:
            nation: Nation name.
            checksum: The verification checksum from the nation's
                "Verify Nation" page.
            token: Optional authentication token.
            shards: Optional list of shards to include after verification.

        Returns:
            Parsed response dict.
        """
        params: dict[str, str] = {
            "nation": nation,
            "q": "verify",
            "checksum": checksum,
        }
        if token is not None:
            params["token"] = token
        if shards:
            params["q"] = "verify+" + "+".join(shards)
        return await self.api_get(params)

    async def get_cards(self, params: dict[str, str]) -> dict:
        """Fetch trading cards data.

        Args:
            params: Card-specific parameters (e.g. ``{"cards": "1",
                "q": "deck"}``).

        Returns:
            Parsed response dict.
        """
        return await self.api_get(params)

    async def get_api_version(self) -> str:
        """Fetch the current NationStates API version string.

        Returns:
            The version string (e.g. ``"12"``).
        """
        result = await self.api_get({"q": "version"})
        return str(result.get("api", {}).get("version", ""))

    # ---- Internal helpers -----------------------------------------------------

    @staticmethod
    def _extract_token(response: dict) -> str:
        """Search a prepare-step response dict for a security token.

        Looks for ``"token"`` or ``"TOKEN"`` (case-insensitive via the
        lowercased keys produced by :func:`_parse_xml`) in the first level
        of the payload dict.
        """
        for key, value in response.items():
            if isinstance(value, dict):
                token = value.get("token") or value.get("token", "")
                if token and str(token).strip():
                    return str(token).strip()
                # One level deeper (some commands nest the token)
                for sub_val in value.values():
                    if isinstance(sub_val, dict):
                        t = sub_val.get("token") or sub_val.get("token", "")
                        if t and str(t).strip():
                            return str(t).strip()
        return ""
