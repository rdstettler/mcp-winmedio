"""Tests for the winmedio client parsing logic.

These tests use static HTML fixtures to validate parsing without
requiring a live portal connection.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from mcp_winmedio.winmedio_client import (
    AccountInfo,
    RentedItem,
    Reservation,
    SearchResult,
    WinmedioClient,
)

# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

RENTED_ITEMS_TABLE_HTML = """
<html><body>
<table class="ausgeliehen">
  <tr>
    <th>Titel</th>
    <th>Autor</th>
    <th>Medienart</th>
    <th>Exemplar-Nr.</th>
    <th>Fälligkeit</th>
  </tr>
  <tr>
    <td>Harry Potter und der Stein der Weisen</td>
    <td>Rowling, J.K.</td>
    <td>Buch</td>
    <td>1234567</td>
    <td>31.05.2026</td>
  </tr>
  <tr>
    <td>Der Hobbit</td>
    <td>Tolkien, J.R.R.</td>
    <td>Buch</td>
    <td>7654321</td>
    <td>15.06.2026</td>
  </tr>
</table>
</body></html>
"""

RENTED_ITEMS_DUE_COLUMN_HTML = """
<html><body>
<table>
  <tr>
    <th>Titel</th>
    <th>Verfasser</th>
    <th>Rückgabe</th>
  </tr>
  <tr>
    <td>Dune</td>
    <td>Herbert, Frank</td>
    <td>20.06.2026</td>
  </tr>
</table>
</body></html>
"""

RESERVATIONS_HTML = """
<html><body>
<table>
  <tr>
    <th>Vorbestellung</th>
    <th>Titel</th>
    <th>Autor</th>
    <th>Status</th>
    <th>Position</th>
    <th>Abholdatum</th>
  </tr>
  <tr>
    <td></td>
    <td>Foundation</td>
    <td>Asimov, Isaac</td>
    <td>Verfügbar</td>
    <td>1</td>
    <td>25.05.2026</td>
  </tr>
</table>
</body></html>
"""

ACCOUNT_INFO_HTML = """
<html><body>
<h2>Willkommen, Max Mustermann</h2>
<table>
  <tr>
    <th>Ausweis-Nr.</th>
    <td>LB-123456</td>
  </tr>
  <tr>
    <th>Gültig bis</th>
    <td>31.12.2027</td>
  </tr>
  <tr>
    <th>Offene Gebühren</th>
    <td>CHF 0.00</td>
  </tr>
</table>
</body></html>
"""

SEARCH_RESULTS_HTML = """
<html><body>
<table class="result">
  <tr>
    <th>Titel</th>
    <th>Autor</th>
    <th>Medienart</th>
    <th>Jahr</th>
    <th>Verfügbar</th>
  </tr>
  <tr>
    <td>1984</td>
    <td>Orwell, George</td>
    <td>Buch</td>
    <td>1949</td>
    <td>Ja</td>
  </tr>
  <tr>
    <td>Brave New World</td>
    <td>Huxley, Aldous</td>
    <td>Buch</td>
    <td>1932</td>
    <td>Nein</td>
  </tr>
</table>
</body></html>
"""

EMPTY_HTML = "<html><body><p>No items found.</p></body></html>"


# ---------------------------------------------------------------------------
# parse_rented_items
# ---------------------------------------------------------------------------


def test_parse_rented_items_basic() -> None:
    soup = BeautifulSoup(RENTED_ITEMS_TABLE_HTML, "html.parser")
    items = WinmedioClient._parse_rented_items(soup)
    assert len(items) == 2

    hp = items[0]
    assert "Harry Potter" in hp.title
    assert "Rowling" in hp.author
    assert hp.media_type == "Buch"
    assert hp.item_number == "1234567"
    assert hp.due_date == "31.05.2026"

    hobbit = items[1]
    assert "Hobbit" in hobbit.title
    assert hobbit.due_date == "15.06.2026"


def test_parse_rented_items_ruckgabe_column() -> None:
    soup = BeautifulSoup(RENTED_ITEMS_DUE_COLUMN_HTML, "html.parser")
    items = WinmedioClient._parse_rented_items(soup)
    assert len(items) == 1
    assert items[0].title == "Dune"
    assert items[0].due_date == "20.06.2026"
    assert "Herbert" in items[0].author


def test_parse_rented_items_empty() -> None:
    soup = BeautifulSoup(EMPTY_HTML, "html.parser")
    items = WinmedioClient._parse_rented_items(soup)
    assert items == []


# ---------------------------------------------------------------------------
# parse_reservations
# ---------------------------------------------------------------------------


def test_parse_reservations_basic() -> None:
    soup = BeautifulSoup(RESERVATIONS_HTML, "html.parser")
    reservations = WinmedioClient._parse_reservations(soup)
    assert len(reservations) == 1

    res = reservations[0]
    assert res.title == "Foundation"
    assert "Asimov" in res.author
    assert res.status == "Verfügbar"


def test_parse_reservations_empty() -> None:
    soup = BeautifulSoup(EMPTY_HTML, "html.parser")
    reservations = WinmedioClient._parse_reservations(soup)
    assert reservations == []


# ---------------------------------------------------------------------------
# parse_account_info
# ---------------------------------------------------------------------------


def test_parse_account_info_basic() -> None:
    soup = BeautifulSoup(ACCOUNT_INFO_HTML, "html.parser")
    info = WinmedioClient._parse_account_info(soup, card_number="LB-123456")

    assert "Mustermann" in info.name or "Max" in info.name
    assert info.card_number == "LB-123456"
    assert info.valid_until == "31.12.2027"
    assert info.open_fees is not None
    assert "0.00" in info.open_fees


# ---------------------------------------------------------------------------
# parse_search_results
# ---------------------------------------------------------------------------


def test_parse_search_results_basic() -> None:
    soup = BeautifulSoup(SEARCH_RESULTS_HTML, "html.parser")
    results = WinmedioClient._parse_search_results(soup)
    assert len(results) == 2

    r1984 = results[0]
    assert r1984.title == "1984"
    assert "Orwell" in r1984.author
    assert r1984.year == "1949"
    assert r1984.availability == "Ja"

    brave = results[1]
    assert "Brave New World" in brave.title
    assert brave.availability == "Nein"


def test_parse_search_results_empty() -> None:
    soup = BeautifulSoup(EMPTY_HTML, "html.parser")
    results = WinmedioClient._parse_search_results(soup)
    assert results == []


# ---------------------------------------------------------------------------
# RentedItem / Reservation / AccountInfo / SearchResult dataclasses
# ---------------------------------------------------------------------------


def test_rented_item_defaults() -> None:
    item = RentedItem(
        title="Test Book",
        author="Test Author",
        media_type="Buch",
        item_number="999",
        due_date="01.01.2027",
    )
    assert item.renewable is True
    assert item.renewals_left is None


def test_account_info_defaults() -> None:
    info = AccountInfo(name="Max", card_number="123")
    assert info.valid_until is None
    assert info.open_fees is None
    assert info.extra == {}
