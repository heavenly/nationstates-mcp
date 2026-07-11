from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from ns_mcp.auth import AuthManager
from ns_mcp.client import NationStatesClient
from ns_mcp.exceptions import NSAPIError, NSCommandError


class _NoopLimiter:
    async def acquire(self, *args, **kwargs) -> None:
        return None

    def on_response(self, headers) -> None:
        return None


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def _client(self, handler) -> NationStatesClient:
        client = NationStatesClient(
            "ns-mcp-tests/1.0 (test@example.invalid)",
            auth_manager=AuthManager(pin="1234"),
        )
        client._bucket = _NoopLimiter()
        client._telegram_limiter = _NoopLimiter()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)
        return client

    async def test_version_uses_action_endpoint(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(parse_qs(request.url.query.decode()), {"a": ["version"]})
            return httpx.Response(200, text="13\n", headers={"Content-Type": "text/plain"})

        client = await self._client(handler)
        self.assertEqual(await client.get_api_version(), "13")

    async def test_basic_verify_accepts_plain_text_response(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(200, text="1\n", headers={"Content-Type": "text/plain"})
        )
        self.assertEqual(
            await client.verify_nation("test", "checksum"),
            {"nation": {"verify": "1"}},
        )

    async def test_verify_uses_action_and_keeps_requested_shards(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            query = parse_qs(request.url.query.decode())
            self.assertEqual(query["a"], ["verify"])
            self.assertEqual(query["q"], ["name+region"])
            return httpx.Response(200, text="<NATION><VERIFY>1</VERIFY></NATION>")

        client = await self._client(handler)
        await client.verify_nation("test", "checksum", shards=["name", "region"])

    async def test_telegram_uses_documented_parameter_names(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            query = parse_qs(request.url.query.decode())
            self.assertEqual(query["a"], ["sendTG"])
            self.assertEqual(query["client"], ["client-key"])
            self.assertNotIn("client_key", query)
            return httpx.Response(200, text="<SUCCESS>Sent</SUCCESS>")

        client = await self._client(handler)
        await client.send_telegram("client-key", "1", "secret", "test")

    async def test_xml_error_with_http_200_is_an_api_error(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(200, text="<ERROR>Invalid shard</ERROR>")
        )
        with self.assertRaisesRegex(NSAPIError, "Invalid shard"):
            await client.api_get({"q": "bad"})

    async def test_two_step_command_reuses_prepare_parameters(self) -> None:
        requests: list[dict[str, list[str]]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            query = parse_qs(request.url.query.decode())
            requests.append(query)
            if query["mode"] == ["prepare"]:
                return httpx.Response(200, text="<PREPARE><TOKEN>abc</TOKEN></PREPARE>")
            return httpx.Response(200, text="<OK><DESC>Done</DESC></OK>")

        client = await self._client(handler)
        result = await client.execute_command("test", "rmbpost", {"text": "hello"})
        self.assertEqual(result["ok"]["desc"], "Done")
        self.assertEqual(requests[1]["token"], ["abc"])
        self.assertEqual(requests[1]["text"], ["hello"])

    async def test_prepare_error_has_command_context(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(200, text="<ERROR>Denied</ERROR>")
        )
        with self.assertRaises(NSCommandError) as raised:
            await client.execute_command("test", "dispatch", {})
        self.assertEqual(raised.exception.step, "prepare")


class AuthTests(unittest.TestCase):
    def test_explicit_pin_is_a_credential(self) -> None:
        auth = AuthManager(pin="1234")
        self.assertTrue(auth.has_credentials)
        self.assertEqual(auth.auth_headers(), {"X-Pin": "1234"})

    def test_pin_is_persisted_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pin"
            auth = AuthManager(password="secret", pin_cache_path=str(path))
            auth.on_response({"x-pin": "5678"})
            self.assertEqual(path.read_text(), "5678")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
