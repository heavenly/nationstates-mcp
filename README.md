# ns-mcp -- NationStates MCP Server

Exposes the interactive HTTP portions of the [NationStates API](https://www.nationstates.net/pages/api.html) as MCP (Model Context Protocol) tools. Daily data dumps and the separate SSE stream are intentionally out of scope.

## Features

- **23 MCP tools** covering all interactive NS API categories
- **Public + private shards** with automatic auth handling (X-Password -> X-Pin)
- **Rate limiting** -- respects NS API limits (50 req/30s)
- **Two-step command support** for dispatch management, card gifting/junking
- **Telegram sending** with separate API Client Key rate limits
- **Nation verification** support
- **Zero-config defaults** -- set `NS_PASSWORD` in your environment and most tools just work

## Installation

```bash
cd mcp
pip install -e .
```

## Quickstart

Set your credentials (optional -- can also be passed per-call):

```bash
export NS_PASSWORD="your-nation-password"
# or: export NS_AUTOLOGIN="your-autologin-token"
export NS_USER_AGENT="my-ns-tool/1.0 (contact: you@example.com)"
```

## MCP Client Configuration

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ns-mcp": {
      "command": "ns-mcp",
      "args": [],
      "env": {
        "NS_PASSWORD": "your-password"
      }
    }
  }
}
```

### Pi / Generic MCP Clients

```json
{
  "mcpServers": {
    "ns-mcp": {
      "type": "stdio",
      "command": "ns-mcp",
      "args": [],
      "env": {
        "NS_PASSWORD": "${NS_PASSWORD}"
      }
    }
  }
}
```

## Tools Reference

### Nation API and commands (7 tools)

| Tool | Description | Auth |
|------|-------------|------|
| `ns_get_nation` | Fetch nation data by shard (public + private) | Optional |
| `ns_get_nation_issues` | List pending issues | Required |
| `ns_get_nation_issue` | Get issue detail with options | Required |
| `ns_answer_issue` | Answer or dismiss an issue (options are **0-indexed**!) | Required |
| `ns_get_nation_notices` | Fetch unread notices | Required |
| `ns_manage_dispatch` | Add, edit, or remove a dispatch | Required |
| `ns_post_rmb` | Post to a regional message board | Required |

### Region API (1 tool)

| Tool | Description | Auth |
|------|-------------|------|
| `ns_get_region` | Fetch region data by shard | None |

### World API (2 tools)

| Tool | Description | Auth |
|------|-------------|------|
| `ns_get_world` | World-level data (census, rankings, etc.) | None |
| `ns_get_happenings` | Global/nation/region happenings with filters | None |

### World Assembly (2 tools)

| Tool | Description | Auth |
|------|-------------|------|
| `ns_get_wa` | WA data (council 1=GA, 2=SC) | None |
| `ns_get_wa_resolution` | Specific resolution text | None |

### Trading Cards (7 tools)

| Tool | Description | Auth |
|------|-------------|------|
| `ns_get_card` | Card info, markets, owners, trades | None |
| `ns_get_cards_deck` | Nation's deck, info, asks/bids | None |
| `ns_get_cards_collection` | Fetch a collection by ID | None |
| `ns_get_cards_auctions` | Fetch current auctions | None |
| `ns_get_cards_trades` | Fetch global trades with time filters | None |
| `ns_gift_card` | Gift a card to another nation | Required |
| `ns_junk_card` | Junk/destroy a card | Required |

### Telegrams (2 tools)

| Tool | Description | Auth |
|------|-------------|------|
| `ns_read_telegrams` | List recent telegram metadata from notices | Required |
| `ns_send_telegram` | Send API telegram | Client Key |

### Verification (1 tool)

| Tool | Description | Auth |
|------|-------------|------|
| `ns_verify` | Verify nation ownership | None |

### Utility (1 tool)

| Tool | Description | Auth |
|------|-------------|------|
| `ns_api_version` | Fetch the current API version | None |

## ⚠️ Option IDs are 0-indexed

When answering issues with `ns_answer_issue`, **option IDs start at 0**, not 1. So for an issue with 4 options:

| Text order | `option_id` |
|-----------|------------|
| 1st option | `0` |
| 2nd option | `1` |
| 3rd option | `2` |
| 4th option | `3` |
| Dismiss | `-1` |

This matches the `@id` attribute returned by `ns_get_nation_issue` and `ns_get_nation` (issues shard).  Passing an out-of-range ID like `4` for a 4-option issue will succeed silently but the issue won't be answered.

## Authentication

Two authentication mechanisms:

1. **Password-based** (most tools):
   - Set `NS_PASSWORD` env var, or pass `password=` per-call
   - First request logs in, subsequent requests reuse X-Pin (cached to disk)
   - Supports `NS_AUTOLOGIN` as alternative

2. **API Client Key** (telegrams only):
   - Requested from NS moderators via Help Request
   - Pass `client_key` and `secret_key` per-call

## Rate Limits

- General API: 50 requests per 30 seconds (enforced automatically)
- Recruitment telegrams: 1 per 180 seconds per Client Key
- Non-recruitment telegrams: 1 per 30 seconds per Client Key

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `NS_PASSWORD` | NationStates password (default auth) |
| `NS_AUTOLOGIN` | Autologin token (alternative to password) |
| `NS_NATION` | Default nation name |
| `NS_USER_AGENT` | Informative User-Agent required by NationStates (include contact info) |

## Development

```bash
# Run tests
cd mcp
pip install -e ".[dev]"
pytest
# or, without pytest:
python -m unittest discover -s tests -v

# Run server locally for testing
ns-mcp --sse 8080
```

## License

MIT
