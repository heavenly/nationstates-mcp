import unittest

from ns_mcp.server import mcp


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_expected_tools_are_registered(self) -> None:
        names = {tool.name for tool in await mcp.list_tools()}
        self.assertEqual(len(names), 23)
        self.assertTrue({
            "ns_api_version",
            "ns_verify",
            "ns_send_telegram",
            "ns_get_cards_collection",
            "ns_get_cards_auctions",
            "ns_get_cards_trades",
            "ns_answer_issue",
        }.issubset(names))
