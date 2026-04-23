"""
MCP Server for the winmedio library portal.

Exposes the following MCP tools to an AI client:

* get_rented_items   – list currently borrowed books / media with due dates

Configuration (via environment variables):
    LIBRARY_NAME       – library identifier in the URL path,
                         e.g. "buelach" for https://www.winmedio.net/buelach/api/…
    WINMEDIO_USERNAME  – library card number / username
    WINMEDIO_PASSWORD  – account password
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_winmedio.winmedio_client import (
    WinmedioAuthError,
    WinmedioClient,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(
            f"ERROR: Required environment variable '{name}' is not set.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def _get_client() -> WinmedioClient:
    """Create and return an authenticated :class:`WinmedioClient`.

    A new client instance is created for each call so that credentials are
    read fresh from the environment.  The login is performed lazily by the
    client itself on the first API call.
    """
    library_name = _require_env("LIBRARY_NAME")
    username = _require_env("WINMEDIO_USERNAME")
    password = _require_env("WINMEDIO_PASSWORD")
    return WinmedioClient(library_name=library_name, username=username, password=password)


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "winmedio",
    instructions=(
        "MCP server for the winmedio library portal. "
        "Use the available tools to query borrowed items and their due dates."
    ),
)


def _to_json(obj: Any) -> str:
    """Serialize a dataclass or dict to a pretty JSON string."""
    if hasattr(obj, "__dataclass_fields__"):
        return json.dumps(asdict(obj), ensure_ascii=False, indent=2)
    if isinstance(obj, list):
        return json.dumps(
            [asdict(o) if hasattr(o, "__dataclass_fields__") else o for o in obj],
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(obj, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_rented_items() -> str:
    """Return all media currently borrowed from the library, including due dates.

    Each item in the result list contains:
    - title: book/media title (from "TitelKurz" field)
    - due_date: date by which the item must be returned (from "Ausleihen_AuslBis" field)
    """
    client = _get_client()
    try:
        items = client.get_rented_items()
        if not items:
            return "No items are currently borrowed."
        return _to_json(items)
    except WinmedioAuthError as exc:
        return f"Authentication error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error retrieving rented items: {exc}"
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server using stdio transport (default for MCP clients)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
