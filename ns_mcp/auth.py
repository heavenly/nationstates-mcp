"""Authentication manager for the NationStates API.

NationStates authenticates by sending X-Password (or X-Autologin) as an HTTP
header alongside your first private-shard request.  The server responds with
an X-Pin header that must be sent on all subsequent private requests.

This manager:
- Sends X-Password/X-Autologin when no cached pin exists
- Captures X-Pin from any response that includes it
- Persists the pin to disk so restarts don't force re-auth
- Clears the pin on auth failures (403/409)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages NationStates API authentication lifecycle.

    Credentials can be provided explicitly or loaded from the ``NS_PASSWORD``
    and ``NS_AUTOLOGIN`` environment variables.
    """

    def __init__(
        self,
        password: str | None = None,
        autologin: str | None = None,
        pin: str | None = None,
        pin_cache_path: str = ".pin_cache",
    ) -> None:
        # Use explicit value; fall back to env var when None
        self._password = (
            password if password is not None else os.getenv("NS_PASSWORD")
        )
        self._autologin = (
            autologin if autologin is not None else os.getenv("NS_AUTOLOGIN")
        )
        self._pin_cache_path = Path(pin_cache_path)
        self._pin = pin

        if password and autologin:
            logger.debug("Both password and autologin supplied; autologin takes precedence")

        if not self._password and not self._autologin and not self._pin:
            logger.debug(
                "No credentials configured — X-Password/X-Autologin not set. "
                "Set NS_PASSWORD or NS_AUTOLOGIN environment variables."
            )

    @property
    def has_credentials(self) -> bool:
        """Whether this manager can authenticate a private request."""
        return bool(self._pin or self._load_cached_pin() or self._password or self._autologin)

    # ---- Public API ------------------------------------------------------------

    def auth_headers(self) -> dict[str, str]:
        """Return the auth headers for the next request.

        Uses cached X-Pin if available, otherwise falls back to X-Password
        or X-Autologin for first-time auth.
        """
        # Try cache first
        if self._pin is None:
            self._pin = self._load_cached_pin()

        if self._pin:
            return {"X-Pin": self._pin}

        # No pin yet — use raw credentials
        if self._autologin:
            return {"X-Autologin": self._autologin}
        if self._password:
            return {"X-Password": self._password}

        return {}

    def on_auth_failure(self) -> None:
        """Clear the cached pin after a 403/409 so the next request
        re-authenticates with raw credentials."""
        self._pin = None
        self._clear_cached_pin()
        logger.warning("Auth failure — cleared cached X-Pin, will re-authenticate")

    def on_response(self, headers: dict[str, str]) -> None:
        """Inspect response headers for X-Pin and cache it.

        Call this after every API response.  If the server sends an X-Pin
        (which it does on first successful authenticated request), we
        capture and persist it for subsequent requests.
        """
        # Case-insensitive search — NS API may return x-pin, X-Pin, X-PIN, etc.
        pin = None
        for key, val in headers.items():
            if key.lower() == "x-pin":
                pin = val
                break
        if pin and pin != self._pin:
            self._pin = pin
            self._persist_pin(pin)
            logger.info("Captured X-Pin from response (pin=%s…)", pin[:8])
        elif not self._pin:
            # No pin cached yet and no pin in response — log for debugging
            pin_keys = [k for k in headers if "pin" in k.lower()]
            logger.debug(
                "No X-Pin in response headers (keys with 'pin': %s, total keys: %d)",
                pin_keys, len(headers),
            )

    # ---- Disk cache ------------------------------------------------------------

    def _load_cached_pin(self) -> str | None:
        """Read the cached X-Pin from disk, if present."""
        if self._pin_cache_path.exists():
            try:
                return self._pin_cache_path.read_text().strip()
            except OSError:
                logger.warning("Could not read pin cache file", exc_info=True)
        return None

    def _persist_pin(self, pin: str) -> None:
        """Write X-Pin to disk with restrictive permissions (0o600)."""
        try:
            fd = os.open(
                self._pin_cache_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            with os.fdopen(fd, "w") as fh:
                fh.write(pin)
            logger.debug("Persisted X-Pin to %s", self._pin_cache_path)
        except OSError:
            logger.warning("Could not persist pin cache", exc_info=True)

    def _clear_cached_pin(self) -> None:
        """Remove the pin cache file from disk."""
        try:
            self._pin_cache_path.unlink(missing_ok=True)
        except OSError:
            pass
