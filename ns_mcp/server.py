"""NationStates MCP Server -- main entry point.

Exposes the full NationStates API as MCP tools for AI assistants.

Usage:
    ns-mcp                  # stdio transport (Claude Desktop, Pi, etc.)
    ns-mcp --sse 8080       # SSE transport on port 8080
    python -m ns_mcp.server # equivalent to ns-mcp
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

from ns_mcp import __version__

# Auto-load .env from the project root (walk up until found, or use cwd)
_env_path = Path.cwd()
for _parent in [_env_path, *_env_path.parents]:
    _candidate = _parent / ".env"
    if _candidate.exists():
        load_dotenv(_candidate)
        break
else:
    load_dotenv()  # fallback: load from cwd

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="ns-mcp",
    instructions=(
        "NationStates API -- query nations, regions, world data, "
        "World Assembly, trading cards, telegrams, and more. "
        "Supports public and private (authenticated) shards."
    ),
    version=__version__,
)

# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def _register_all_tools() -> None:
    """Import and register all tool modules on the shared ``mcp`` instance.

    Each module exports a ``register_tools(mcp)`` function that registers
    its tools via ``mcp.tool()`` (either decorator or call style).  This
    function is called once at module-import time so that all tools are
    available before ``mcp.run()`` is invoked.
    """
    from ns_mcp.tools.nation import register_tools as reg_nation
    from ns_mcp.tools.region import register_tools as reg_region
    from ns_mcp.tools.world import register_tools as reg_world
    from ns_mcp.tools.wa import register_tools as reg_wa
    from ns_mcp.tools.cards import register_tools as reg_cards
    from ns_mcp.tools.telegrams import register_tools as reg_telegrams
    from ns_mcp.tools.verification import register_tools as reg_verification
    from ns_mcp.tools.utility import register_tools as reg_utility

    reg_nation(mcp)
    reg_region(mcp)
    reg_world(mcp)
    reg_wa(mcp)
    reg_cards(mcp)
    reg_telegrams(mcp)
    reg_verification(mcp)
    reg_utility(mcp)


_register_all_tools()

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for the MCP server.

    Parses command-line arguments, configures logging, and starts the
    FastMCP server with the requested transport.

    Transport modes:
    - **stdio** (default): For use with Claude Desktop, Pi, and other
      MCP hosts that spawn a subprocess.
    - **sse**: Server-Sent Events transport, useful for remote access
      and testing.  Bind address defaults to ``127.0.0.1:8080``.

    Environment variables (optional):
        ``NS_PASSWORD``     Nation password (auto-login on first request).
        ``NS_AUTOLOGIN``    Autologin token (alternative to password).
        ``NS_NATION``       Default nation name.
    """
    parser = argparse.ArgumentParser(
        description="NationStates MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ns-mcp                       # stdio transport (Claude Desktop, Pi, etc.)
  ns-mcp --sse                 # SSE transport on 127.0.0.1:8080
  ns-mcp --sse 8080            # SSE transport on port 8080
  ns-mcp --sse 0.0.0.0:8080    # SSE transport bound to all interfaces
  ns-mcp --verbose             # stdio transport with debug logging
        """,
    )
    parser.add_argument(
        "--sse",
        nargs="?",
        const="127.0.0.1:8080",
        default=None,
        metavar="HOST:PORT",
        help="Run with SSE transport on HOST:PORT (default: 127.0.0.1:8080)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # -- Logging setup -------------------------------------------------------
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("fastmcp").setLevel(logging.INFO)

    # -- Transport -----------------------------------------------------------
    if args.sse:
        # Parse optional host:port
        if ":" in args.sse:
            host, port_str = args.sse.rsplit(":", 1)
            port = int(port_str)
        else:
            host, port = "127.0.0.1", int(args.sse)

        print(
            f"Starting ns-mcp SSE server on http://{host}:{port}/sse",
            file=sys.stderr,
        )
        mcp.run(transport="sse", host=host, port=port)
    else:
        print("Starting ns-mcp server (stdio transport)", file=sys.stderr)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
