from pathlib import Path
import unittest

from ns_mcp.parsers import (
    parse_api_version,
    parse_cards,
    parse_issue_detail,
    parse_nation,
    parse_ok_error,
    parse_region,
    parse_verify,
    parse_wa,
    parse_world,
)


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class ParserTests(unittest.TestCase):
    def test_nation(self) -> None:
        parsed = parse_nation(fixture("nation_public.xml"))
        self.assertEqual(parsed["id"], "testlandia")
        self.assertEqual(parsed["freedom"]["economy"], "Frightening")
        self.assertEqual(parsed["banners"], ["c10", "p5", "t3"])

    def test_issue_detail_preserves_zero_based_options(self) -> None:
        parsed = parse_issue_detail(fixture("nation_issue_detail.xml"))
        self.assertEqual([option["id"] for option in parsed["options"]], [0, 1, 2, 3])

    def test_command_result(self) -> None:
        parsed = parse_ok_error(fixture("nation_submit_ok.xml"))
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["rankings"]["civilrights"], "+1.5")

    def test_remaining_public_parsers(self) -> None:
        self.assertEqual(parse_region(fixture("region_complete.xml"))["messages"][0]["id"], 1001)
        self.assertEqual(parse_world(fixture("world_census.xml"))["numnations"], "250000")
        self.assertEqual(parse_wa(fixture("wa_resolution.xml"))["resolution"]["name"], "Freedom of Speech Resolution")
        self.assertEqual(parse_cards(fixture("cards_card.xml"))["season"], 3)
        self.assertTrue(parse_verify(fixture("verify_ok.xml"))["verified"])
        self.assertEqual(parse_api_version(fixture("api_version.xml")), "12")
