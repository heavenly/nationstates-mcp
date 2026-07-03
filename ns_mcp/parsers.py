"""Specialized XML parsers for every NationStates API response type.

Each function takes a raw XML string and returns a plain Python dict (or list).
All parsers use ``xml.etree.ElementTree`` (stdlib only) and are robust against
missing or malformed input.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


# ===================================================================
# Internal helpers
# ===================================================================


def _text(parent: ET.Element | None, tag: str, default: str = "") -> str:
    """Return the text content of the first *tag* child of *parent*."""
    if parent is None:
        return default
    el = parent.find(tag)
    if el is None:
        return default
    return (el.text or "").strip()


def _int(
    parent: ET.Element | None, tag: str, default: int | None = None
) -> int | None:
    """Return the integer value of the first *tag* child, or *default*."""
    v = _text(parent, tag)
    if not v:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def _float(
    parent: ET.Element | None, tag: str, default: float | None = None
) -> float | None:
    """Return the float value of the first *tag* child, or *default*."""
    v = _text(parent, tag)
    if not v:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _attr(
    element: ET.Element | None, attr: str, default: Any = None
) -> Any:
    """Return an attribute value from *element*, or *default*."""
    if element is None:
        return default
    return element.get(attr, default)


def _split_colon(text: str) -> list[str]:
    """Split a colon-separated string into a list of non-empty tokens."""
    if not text:
        return []
    return [s.strip() for s in text.split(":") if s.strip()]


def _split_comma(text: str) -> list[str]:
    """Split a comma-separated string into a list of non-empty tokens."""
    if not text:
        return []
    return [s.strip() for s in text.split(",") if s.strip()]


def _text_list(parent: ET.Element, tag: str) -> list[str]:
    """Return the (stripped) text of every child *tag* element as a list."""
    return [
        (el.text or "").strip()
        for el in parent.findall(tag)
        if el.text is not None
    ]


def _bool_flag(text: str) -> bool:
    """Convert ``'1'`` to ``True``, everything else to ``False``."""
    return text.strip() == "1"


# ===================================================================
# Nation shards
# ===================================================================


def parse_nation(xml: str) -> dict[str, Any]:
    """Parse a ``<NATION>`` response into a flat-ish dict.

    Handles text shards, census sub-structure, freedom sub-structure,
    sectors list, banners list, policies, legislation, notables,
    admirables, notices, dispatch lists, factbook lists, colon-separated
    lists (endorsements), comma-separated lists (sensibilities), and
    all other standard nation shards.
    """
    root = ET.fromstring(xml)
    if root.tag.lower() != "nation":
        raise ValueError(f"Expected <NATION> root, got <{root.tag}>")

    data: dict[str, Any] = {}

    # id attribute on the root element
    nation_id = root.get("id")
    if nation_id is not None:
        data["id"] = nation_id

    # Tags that have specialised sub-structures handled below
    skip_tags = {
        "sectors", "freedom", "banners", "notables", "admirables",
        "policies", "census", "notices", "dispatchlist", "factbooklist",
    }

    for child in root:
        tag = child.tag.lower()
        if tag in skip_tags:
            continue
        data[tag] = (child.text or "").strip()

    # -- SECTORS --------------------------------------------------------
    sectors_el = root.find("SECTORS")
    if sectors_el is not None:
        data["sectors"] = [
            {
                "name": s.get("name", ""),
                "value": (s.text or "").strip(),
            }
            for s in sectors_el.findall("SECTOR")
        ]

    # -- FREEDOM --------------------------------------------------------
    freedom_el = root.find("FREEDOM")
    if freedom_el is not None:
        data["freedom"] = {
            "civilrights": _text(freedom_el, "CIVILRIGHTS"),
            "economy": _text(freedom_el, "ECONOMY"),
            "politicalfreedom": _text(freedom_el, "POLITICALFREEDOM"),
        }

    # -- BANNERS --------------------------------------------------------
    banners_el = root.find("BANNERS")
    if banners_el is not None:
        data["banners"] = [
            s.get("code", "") for s in banners_el.findall("BANNER")
        ]

    # -- NOTABLES (plural list) -----------------------------------------
    notables_el = root.find("NOTABLES")
    if notables_el is not None:
        data["notables"] = _text_list(notables_el, "NOTABLE")

    # -- ADMIRABLES (plural list) ---------------------------------------
    admirables_el = root.find("ADMIRABLES")
    if admirables_el is not None:
        data["admirables"] = _text_list(admirables_el, "ADMIRABLE")

    # -- POLICIES -------------------------------------------------------
    policies_el = root.find("POLICIES")
    if policies_el is not None:
        data["policies"] = [
            {
                "name": s.get("name", ""),
                "value": (s.text or "").strip(),
            }
            for s in policies_el.findall("POLICY")
        ]

    # -- CENSUS ---------------------------------------------------------
    census_el = root.find("CENSUS")
    if census_el is not None:
        data["census"] = {
            "id": census_el.get("id"),
            "scale": _text(census_el, "SCALE"),
            "score": _float(census_el, "SCORE"),
            "rank": _int(census_el, "RANK"),
            "rrank": _int(census_el, "RRANK"),
        }

    # -- NOTICES (private shard) ----------------------------------------
    notices_el = root.find("NOTICES")
    if notices_el is not None:
        data["notices"] = []
        for notice in notices_el.findall("NOTICE"):
            data["notices"].append({
                "id": _int(notice, "ID"),
                "title": _text(notice, "TITLE"),
                "timestamp": _int(notice, "TIMESTAMP"),
                "type": _text(notice, "TYPE"),
            })

    # -- DISPATCHLIST ---------------------------------------------------
    dl_el = root.find("DISPATCHLIST")
    if dl_el is not None:
        data["dispatchlist"] = [
            {
                "id": d.get("id"),
                "title": d.get("title", ""),
            }
            for d in dl_el.findall("DISPATCH")
        ]

    # -- FACTBOOKLIST ---------------------------------------------------
    fl_el = root.find("FACTBOOKLIST")
    if fl_el is not None:
        data["factbooklist"] = [
            {
                "id": f.get("id"),
                "title": f.get("title", ""),
            }
            for f in fl_el.findall("FACTBOOK")
        ]

    # -- Comma-separated lists ------------------------------------------
    for comma_field in ("sensibilities", "endorsements"):
        val = data.get(comma_field)
        if isinstance(val, str):
            data[comma_field] = _split_comma(val)

    return data


# ===================================================================
# Issues
# ===================================================================


def parse_issues_list(xml: str) -> list[dict[str, Any]]:
    """Parse an ``<ISSUES>`` response into a list of issue summaries.

    Returns::

        [{"id": 12345, "title": "Should We ..."}, ...]
    """
    root = ET.fromstring(xml)
    # Accept either <ISSUES> or a root that contains <ISSUE> children
    container = root if root.tag.lower() == "issues" else root
    issues: list[dict[str, Any]] = []
    for issue in container.findall("ISSUE"):
        entry: dict[str, Any] = {
            "title": (issue.text or "").strip(),
        }
        raw_id = issue.get("id")
        if raw_id is not None:
            try:
                entry["id"] = int(raw_id)
            except ValueError:
                entry["id"] = raw_id
        issues.append(entry)
    return issues


def parse_issue_detail(xml: str) -> dict[str, Any]:
    """Parse an ``<ISSUE>`` detail response.

    Returns::

        {
            "id": 12345,
            "title": "...",
            "text": "...",
            "options": [{"id": 0, "text": "..."}, ...],
            "deadline": "...",
        }
    """
    root = ET.fromstring(xml)
    if root.tag.lower() != "issue":
        raise ValueError(f"Expected <ISSUE> root, got <{root.tag}>")

    options: list[dict[str, Any]] = []
    for opt in root.findall("OPTION"):
        options.append({
            "id": int(opt.get("id", 0)),
            "text": (opt.text or "").strip(),
        })

    return {
        "id": int(root.get("id", 0)),
        "title": _text(root, "TITLE"),
        "text": _text(root, "TEXT"),
        "options": options,
        "deadline": _text(root, "DEADLINE"),
    }


# ===================================================================
# OK / Error (issue answer, dispatch create, etc.)
# ===================================================================


def parse_ok_error(xml: str) -> dict[str, Any]:
    """Parse an ``<OK>`` or ``<ERROR>`` response.

    Returns::

        {
            "ok": True/False,
            "description": "...",
            "rankings": {"civilrights": "+1.5", ...},
            "unlocks": ["Space Elevator Construction", ...],
            "reclassifications": [{"type": "..."}, ...],
            "new_policies": [{"name": "...", "value": "..."}, ...],
            "removed_policies": [{"name": "...", "value": "..."}, ...],
        }
    """
    root = ET.fromstring(xml)
    tag = root.tag.lower()

    result: dict[str, Any] = {
        "ok": tag == "ok",
        "description": _text(root, "DESC"),
    }

    # -- RANKINGS ------------------------------------------------------
    rankings_el = root.find("RANKINGS")
    if rankings_el is not None:
        rankings: dict[str, str] = {}
        for child in rankings_el:
            rankings[child.tag.lower()] = (child.text or "").strip()
        result["rankings"] = rankings

    # -- UNLOCKS -------------------------------------------------------
    unlocks_el = root.find("UNLOCKS")
    if unlocks_el is not None:
        result["unlocks"] = [
            (el.text or "").strip()
            for el in unlocks_el.findall("UNLOCK")
        ]

    # -- RECLASSIFICATIONS ---------------------------------------------
    reclass_el = root.find("RECLASSIFICATIONS")
    if reclass_el is not None:
        result["reclassifications"] = [
            {"type": el.get("type", "")}
            for el in reclass_el.findall("RECLASSIFICATION")
        ]

    # -- NEW_POLICIES ---------------------------------------------------
    new_pol_el = root.find("NEW_POLICIES")
    if new_pol_el is not None:
        result["new_policies"] = [
            {
                "name": el.get("name", ""),
                "value": (el.text or "").strip(),
            }
            for el in new_pol_el.findall("POLICY")
        ]

    # -- REMOVED_POLICIES -----------------------------------------------
    rem_pol_el = root.find("REMOVED_POLICIES")
    if rem_pol_el is not None:
        result["removed_policies"] = [
            {
                "name": el.get("name", ""),
                "value": (el.text or "").strip(),
            }
            for el in rem_pol_el.findall("POLICY")
        ]

    return result


# ===================================================================
# Region shards
# ===================================================================


def parse_region(xml: str) -> dict[str, Any]:
    """Parse a ``<REGION>`` response.

    Handles text shards, messages (array of posts with nested fields),
    officers, embassies (colon-separated → list), nations list
    (colon-separated → list), tags (comma-separated → list),
    GAVOTE/SCVOTE sub-structures.
    """
    root = ET.fromstring(xml)
    if root.tag.lower() != "region":
        raise ValueError(f"Expected <REGION> root, got <{root.tag}>")

    skip_tags = {
        "officers", "messages", "gavote", "scvote",
    }

    data: dict[str, Any] = {}

    for child in root:
        tag = child.tag.lower()
        if tag in skip_tags:
            continue
        data[tag] = (child.text or "").strip()

    # -- OFFICERS ------------------------------------------------------
    officers_el = root.find("OFFICERS")
    if officers_el is not None:
        data["officers"] = []
        for o in officers_el.findall("OFFICER"):
            officer: dict[str, Any] = {
                "nation": o.get("nation", ""),
                "office": o.get("office", ""),
                "authority": o.get("authority", ""),
                "by": o.get("by", ""),
            }
            raw_time = o.get("time")
            if raw_time is not None:
                try:
                    officer["time"] = int(raw_time)
                except ValueError:
                    officer["time"] = raw_time
            raw_order = o.get("order")
            if raw_order is not None:
                try:
                    officer["order"] = int(raw_order)
                except ValueError:
                    officer["order"] = raw_order
            data["officers"].append(officer)

    # -- MESSAGES -------------------------------------------------------
    messages_el = root.find("MESSAGES")
    if messages_el is not None:
        data["messages"] = []
        for post in messages_el.findall("POST"):
            data["messages"].append({
                "id": int(post.get("id", 0)),
                "timestamp": _int(post, "TIMESTAMP"),
                "nation": _text(post, "NATION"),
                "status": _text(post, "STATUS"),
                "likes": _int(post, "LIKES"),
                "message": _text(post, "MESSAGE"),
            })

    # -- GAVOTE ---------------------------------------------------------
    gavote_el = root.find("GAVOTE")
    if gavote_el is not None:
        data["gavote"] = {
            "for": _int(gavote_el, "FOR"),
            "against": _int(gavote_el, "AGAINST"),
        }

    # -- SCVOTE ---------------------------------------------------------
    scvote_el = root.find("SCVOTE")
    if scvote_el is not None:
        data["scvote"] = {
            "for": _int(scvote_el, "FOR"),
            "against": _int(scvote_el, "AGAINST"),
        }

    # -- Colon-separated lists ------------------------------------------
    for colon_field in ("nations", "embassies"):
        val = data.get(colon_field)
        if isinstance(val, str):
            data[colon_field] = _split_colon(val)

    # -- Comma-separated lists ------------------------------------------
    for comma_field in ("tags",):
        val = data.get(comma_field)
        if isinstance(val, str):
            data[comma_field] = _split_comma(val)

    return data


# ===================================================================
# World shards
# ===================================================================


def parse_world(xml: str) -> dict[str, Any]:
    """Parse a ``<WORLD>`` response.

    Handles census, census ranks (array of ranks), happenings (array
    of events), plus generic text shards (numnations, numregions,
    featuredregion, lasteventid, etc.).
    """
    root = ET.fromstring(xml)
    if root.tag.lower() != "world":
        raise ValueError(f"Expected <WORLD> root, got <{root.tag}>")

    skip_tags = {"census", "censusranks", "happenings"}

    data: dict[str, Any] = {}

    for child in root:
        tag = child.tag.lower()
        if tag in skip_tags:
            continue
        data[tag] = (child.text or "").strip()

    # -- CENSUS ---------------------------------------------------------
    census_el = root.find("CENSUS")
    if census_el is not None:
        data["census"] = {
            "id": census_el.get("id"),
            "scale": _text(census_el, "SCALE"),
            "desc": _text(census_el, "DESC"),
            "name": _text(census_el, "NAME"),
            "title": _text(census_el, "TITLE"),
        }

    # -- CENSUSRANKS ----------------------------------------------------
    cr_el = root.find("CENSUSRANKS")
    if cr_el is not None:
        ranks: list[dict[str, Any]] = []
        for rank in cr_el.findall("RANK"):
            ranks.append({
                "id": int(rank.get("id", 0)),
                "nation": _text(rank, "NATION"),
                "score": _float(rank, "SCORE"),
            })
        data["censusranks"] = ranks

    # -- HAPPENINGS -----------------------------------------------------
    happenings_el = root.find("HAPPENINGS")
    if happenings_el is not None:
        events: list[dict[str, Any]] = []
        for event in happenings_el.findall("EVENT"):
            events.append({
                "id": int(event.get("id", 0)),
                "timestamp": _int(event, "TIMESTAMP"),
                "text": _text(event, "TEXT"),
            })
        data["happenings"] = events

    return data


# ===================================================================
# WA shards
# ===================================================================


def parse_wa(xml: str) -> dict[str, Any]:
    """Parse a ``<WA council="N">`` response.

    Handles resolution sub-structure, numnations, numdelegates,
    and colon-separated lists (members, delegates).
    """
    root = ET.fromstring(xml)
    if root.tag.lower() != "wa":
        raise ValueError(f"Expected <WA> root, got <{root.tag}>")

    data: dict[str, Any] = {
        "council": root.get("id") or root.get("council"),
    }

    skip_tags = {"resolution"}

    for child in root:
        tag = child.tag.lower()
        if tag in skip_tags:
            continue
        data[tag] = (child.text or "").strip()

    # -- RESOLUTION -----------------------------------------------------
    res_el = root.find("RESOLUTION")
    if res_el is not None:
        data["resolution"] = {
            "name": _text(res_el, "NAME"),
            "category": _text(res_el, "CATEGORY"),
            "option": _text(res_el, "OPTION"),
            "proposed_by": _text(res_el, "PROPOSED_BY"),
            "desc": _text(res_el, "DESC"),
            "total_nations_for": _int(res_el, "TOTAL_NATIONS_FOR"),
            "total_nations_against": _int(res_el, "TOTAL_NATIONS_AGAINST"),
            "implemented": _text(res_el, "IMPLEMENTED"),
        }

    # -- Colon-separated lists ------------------------------------------
    for colon_field in ("members", "delegates"):
        val = data.get(colon_field)
        if isinstance(val, str):
            data[colon_field] = _split_colon(val)

    return data


# ===================================================================
# Cards
# ===================================================================


def parse_cards(xml: str) -> dict[str, Any]:
    """Parse a ``<CARD>`` or ``<CARDS>`` response.

    For a single ``<CARD>`` root (card detail)::

        {
            "cardid": "12345",
            "season": 3,
            "name": "Testlandia",
            "classification": "Common",
            ...
            "markets": {"ask": {"nation": "...", "price": ..., ...}},
            "owners": [{"nation": "...", "count": 3}, ...],
            "trades": [{"buyer": "...", "seller": "...", ...}, ...],
        }

    For a ``<CARDS>`` root (deck listing)::

        {
            "deck": [
                {"cardid": "100", "season": 3, "name": "...", ...},
                ...
            ],
        }
    """
    root = ET.fromstring(xml)
    tag = root.tag.lower()

    if tag == "card":
        return _parse_single_card(root)
    elif tag == "cards":
        return _parse_card_deck(root)
    else:
        raise ValueError(
            f"Expected <CARD> or <CARDS> root, got <{root.tag}>"
        )


def _parse_single_card(root: ET.Element) -> dict[str, Any]:
    """Parse a single ``<CARD>`` element into a dict."""
    skip_tags = {"markets", "owners", "trades"}

    data: dict[str, Any] = {}

    for child in root:
        tag = child.tag.lower()
        if tag in skip_tags:
            continue
        data[tag] = (child.text or "").strip()

    # Normalise numeric fields
    for num_field in ("season",):
        val = data.get(num_field)
        if isinstance(val, str) and val.isdigit():
            data[num_field] = int(val)

    # -- MARKETS --------------------------------------------------------
    markets_el = root.find("MARKETS")
    if markets_el is not None:
        ask_el = markets_el.find("ASK")
        ask: dict[str, Any] = {}
        if ask_el is not None:
            ask["nation"] = _text(ask_el, "NATION")
            ask["price"] = _float(ask_el, "PRICE")
            ask["timestamp"] = _int(ask_el, "TIMESTAMP")

            bids: list[dict[str, Any]] = []
            for bid in ask_el.findall("BID"):
                bids.append({
                    "id": int(bid.get("id", 0)),
                    "nation": _text(bid, "NATION"),
                    "price": _float(bid, "PRICE"),
                    "timestamp": _int(bid, "TIMESTAMP"),
                })
            if bids:
                ask["bids"] = bids

        data["markets"] = {"ask": ask}

    # -- OWNERS ---------------------------------------------------------
    owners_el = root.find("OWNERS")
    if owners_el is not None:
        data["owners"] = [
            {
                "nation": _text(owner, "NATION"),
                "count": _int(owner, "COUNT"),
            }
            for owner in owners_el.findall("OWNER")
        ]

    # -- TRADES ---------------------------------------------------------
    trades_el = root.find("TRADES")
    if trades_el is not None:
        data["trades"] = [
            {
                "buyer": _text(trade, "BUYER"),
                "seller": _text(trade, "SELLER"),
                "price": _float(trade, "PRICE"),
                "timestamp": _int(trade, "TIMESTAMP"),
            }
            for trade in trades_el.findall("TRADE")
        ]

    return data


def _parse_card_deck(root: ET.Element) -> dict[str, Any]:
    """Parse a ``<CARDS>`` deck listing into a dict with a ``deck`` key."""
    deck_el = root.find("DECK")
    if deck_el is None:
        return {"deck": []}

    cards: list[dict[str, Any]] = []
    for card in deck_el.findall("CARD"):
        entry: dict[str, Any] = {}
        for child in card:
            entry[child.tag.lower()] = (child.text or "").strip()
        # Normalise numeric fields
        for num_field in ("season", "cardid"):
            val = entry.get(num_field)
            if isinstance(val, str) and val.isdigit():
                entry[num_field] = int(val)  # type: ignore[assignment]
        market_val = entry.get("market_value")
        if isinstance(market_val, str):
            try:
                entry["market_value"] = float(market_val)
            except ValueError:
                pass
        cards.append(entry)

    return {"deck": cards}


# ===================================================================
# Verification
# ===================================================================


def parse_verify(xml: str) -> dict[str, Any]:
    """Parse a verification response.

    The NS API returns::

        <NATION id="testlandia"><VERIFY>1</VERIFY></NATION>

    Returns ``{"verified": True}`` or ``{"verified": False}``.
    """
    root = ET.fromstring(xml)
    # Walk down to <VERIFY>
    verify_el = root.find(".//VERIFY")
    if verify_el is None:
        return {"verified": False}
    return {"verified": _bool_flag(verify_el.text or "0")}


# ===================================================================
# Two-step command
# ===================================================================


def parse_command_prepare(xml: str) -> dict[str, Any]:
    """Parse a ``<PREPARE>`` response from the prepare step.

    Returns ``{"success": True/False, "token": "abc123..."}``.
    """
    root = ET.fromstring(xml)
    if root.tag.lower() != "prepare":
        raise ValueError(f"Expected <PREPARE> root, got <{root.tag}>")

    success = _bool_flag(_text(root, "SUCCESS"))
    token = _text(root, "TOKEN")

    return {
        "success": success,
        "token": token if success else None,
    }


def parse_command_execute(xml: str) -> dict[str, Any]:
    """Parse a command execution ``<OK>`` / ``<ERROR>`` response.

    Returns ``{"ok": True/False, "description": "..."}``.
    """
    root = ET.fromstring(xml)
    tag = root.tag.lower()

    return {
        "ok": tag == "ok",
        "description": _text(root, "DESC"),
    }


# ===================================================================
# API version
# ===================================================================


def parse_api_version(xml: str) -> str:
    """Extract the version number from ``<VERSION>12</VERSION>``.

    Returns the version string (e.g. ``"12"``).
    """
    root = ET.fromstring(xml)
    if root.tag.lower() != "version":
        raise ValueError(f"Expected <VERSION> root, got <{root.tag}>")
    return (root.text or "").strip()
