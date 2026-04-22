"""
MCP Server for the winmedio library OPAC portal.

Exposes the following MCP tools to an AI client:

* get_rented_items   – list currently borrowed books / media with due dates
* get_reservations   – list active reservations
* get_account_info   – show account details (name, card validity, fees)
* search_catalog     – search the library catalog by title, author, or ISBN
* renew_item         – attempt to renew a borrowed item

Configuration (via environment variables):
    WINMEDIO_BASE_URL  – base URL of the portal, e.g.
                         https://opac.winmedio.net/MyCity
    WINMEDIO_USERNAME  – library card number / username
    WINMEDIO_PASSWORD  – account password
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from functools import lru_cache
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
    base_url = _require_env("WINMEDIO_BASE_URL")
    username = _require_env("WINMEDIO_USERNAME")
    password = _require_env("WINMEDIO_PASSWORD")
    return WinmedioClient(base_url=base_url, username=username, password=password)


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "winmedio",
    instructions=(
        "MCP server for the winmedio library portal. "
        "Use the available tools to query library account information, "
        "list rented items with due dates, manage reservations, search the "
        "catalog, and renew borrowed media."
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
    - title: book/media title
    - author: author or creator
    - media_type: type of media (book, DVD, etc.)
    - item_number: library copy identifier
    - due_date: date by which the item must be returned
    - renewable: whether the item can be renewed
    - renewals_left: remaining renewals (if available)
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


@mcp.tool()
def get_reservations() -> str:
    """Return all active media reservations.

    Each reservation contains:
    - title: reserved item title
    - author: author or creator
    - media_type: type of media
    - status: current reservation status
    - position: queue position (if applicable)
    - available_from: estimated availability date (if known)
    """
    client = _get_client()
    try:
        reservations = client.get_reservations()
        if not reservations:
            return "No active reservations found."
        return _to_json(reservations)
    except WinmedioAuthError as exc:
        return f"Authentication error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error retrieving reservations: {exc}"
    finally:
        client.close()


@mcp.tool()
def get_account_info() -> str:
    """Return library account information.

    Includes:
    - name: account holder name
    - card_number: library card number
    - valid_until: card expiry date (if available)
    - open_fees: outstanding fees (if any)
    - extra: additional account details
    """
    client = _get_client()
    try:
        info = client.get_account_info()
        return _to_json(info)
    except WinmedioAuthError as exc:
        return f"Authentication error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error retrieving account info: {exc}"
    finally:
        client.close()


@mcp.tool()
def search_catalog(query: str, search_type: str = "all", max_results: int = 20) -> str:
    """Search the library catalog.

    Parameters
    ----------
    query:
        Free-text search term (title, author name, keyword, or ISBN).
    search_type:
        Restrict the search field: "all" (default), "title", "author", "isbn".
    max_results:
        Maximum number of results to return (default 20, max 100).

    Each result contains:
    - title: item title
    - author: author or creator
    - media_type: type of media
    - year: publication year (if available)
    - availability: current availability status
    - item_number: catalog number (if available)
    """
    client = _get_client()
    try:
        max_results = min(max(1, max_results), 100)
        results = client.search_catalog(
            query=query, search_type=search_type, max_results=max_results
        )
        if not results:
            return f"No catalog results found for query: {query!r}"
        return _to_json(results)
    except WinmedioAuthError as exc:
        return f"Authentication error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error searching catalog: {exc}"
    finally:
        client.close()


@mcp.tool()
def renew_item(item_number: str) -> str:
    """Attempt to renew a borrowed item.

    Parameters
    ----------
    item_number:
        The copy / exemplar number of the item to renew.
        This can be retrieved from the ``item_number`` field in
        ``get_rented_items``.

    Returns a message indicating success or failure.
    """
    client = _get_client()
    try:
        result = client.renew_item(item_number=item_number)
        return _to_json(result)
    except WinmedioAuthError as exc:
        return f"Authentication error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error renewing item {item_number!r}: {exc}"
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
