"""
MCP Server for the winmedio library portal.

Exposes the following MCP tools to an AI client:

* get_rented_items   – list currently borrowed books / media with due dates

Configuration (via environment variables):
    WINMEDIO_LIBRARY_NAME – library identifier in the URL path,
                          e.g. "buelach" for https://www.winmedio.net/buelach/api/…
    WINMEDIO_USERNAME     – library card number / username
    WINMEDIO_PASSWORD     – account password
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from typing import Any

from fastmcp import FastMCP

from winmedio_client import (
    WinmedioAuthError,
    WinmedioClient,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Required environment variable '{name}' is not set.")
    return value


def _get_client() -> WinmedioClient:
    """Create and return an authenticated :class:`WinmedioClient`."""
    library_name = _require_env("WINMEDIO_LIBRARY_NAME")
    username = str(_require_env("WINMEDIO_USERNAME"))
    password = str(_require_env("WINMEDIO_PASSWORD"))
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
    """Return all media currently borrowed from the library, including due dates."""
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

@mcp.tool()
def is_allow_extend(id: str) -> str:
    """Return true if the item with the given id can be extended."""
    client = _get_client()
    try:
        is_allowed_extend = client.get_is_allowed_extend(id)
        if not is_allowed_extend:
            return "Book cannot be extended any more."
        else:
            return "Book can be extended."
    except WinmedioAuthError as exc:
        return f"Authentication error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error checking if book can be extended: {exc}"
    finally:
        client.close()

@mcp.tool()
def extend(id: str) -> str:
    """Extend the item with the given id."""
    client = _get_client()
    try:
        is_allowed_extend = client.get_is_allowed_extend(id)
        if not is_allowed_extend:
            return "Book cannot be extended any more."
        else:
            result = client.extend(id)
            return _to_json(result)
    except WinmedioAuthError as exc:
        return f"Authentication error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error extending book: {exc}"
    finally:
        client.close()
