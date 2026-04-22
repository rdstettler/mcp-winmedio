"""
winmedio OPAC client.

Handles authentication and data retrieval from a winmedio WebOPAC portal.
The winmedio OPAC is an ASP.NET Web Forms application used by libraries
(primarily in German-speaking countries) for their online catalog.

Configuration is done via environment variables:
    WINMEDIO_BASE_URL  – Base URL of the portal, e.g.
                         https://opac.winmedio.net/MyCity
    WINMEDIO_USERNAME  – Library card number / user name
    WINMEDIO_PASSWORD  – Account password
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup


@dataclass
class RentedItem:
    """A single item currently borrowed from the library."""

    title: str
    author: str
    media_type: str
    item_number: str
    due_date: str
    renewals_left: int | None = None
    renewable: bool = True


@dataclass
class Reservation:
    """A media reservation placed by the user."""

    title: str
    author: str
    media_type: str
    status: str
    position: str | None = None
    available_from: str | None = None


@dataclass
class AccountInfo:
    """Basic library account information."""

    name: str
    card_number: str
    valid_until: str | None = None
    open_fees: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single catalog search result."""

    title: str
    author: str
    media_type: str
    year: str | None = None
    availability: str | None = None
    item_number: str | None = None


class WinmedioAuthError(Exception):
    """Raised when authentication fails."""


class WinmedioClient:
    """HTTP client for a winmedio OPAC portal.

    Uses a persistent :class:`httpx.Client` to maintain session cookies
    across requests so that a single login suffices for all subsequent calls.
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._client: httpx.Client = httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
            },
        )
        self._logged_in: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        """Build an absolute URL from a relative *path*."""
        return f"{self.base_url}/{path.lstrip('/')}"

    def _get_page(self, url: str, params: dict[str, str] | None = None) -> BeautifulSoup:
        """Fetch a page and return a :class:`BeautifulSoup` object."""
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    @staticmethod
    def _extract_aspnet_hidden_fields(soup: BeautifulSoup) -> dict[str, str]:
        """Extract all hidden ASP.NET form fields (__VIEWSTATE, etc.)."""
        hidden: dict[str, str] = {}
        for tag in soup.find_all("input", {"type": "hidden"}):
            name = tag.get("name", "")
            value = tag.get("value", "")
            if name:
                hidden[name] = value
        return hidden

    @staticmethod
    def _find_input(soup: BeautifulSoup, *patterns: str) -> str | None:
        """Return the *name* attribute of the first input matching one of the patterns."""
        for pattern in patterns:
            regex = re.compile(pattern, re.IGNORECASE)
            tag = soup.find("input", {"name": regex})
            if tag:
                return tag["name"]
            # try by id
            tag = soup.find("input", {"id": regex})
            if tag and tag.get("name"):
                return tag["name"]
        return None

    @staticmethod
    def _cell_text(cell: Any) -> str:
        return cell.get_text(separator=" ", strip=True) if cell else ""

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate against the winmedio portal.

        Fetches the login page to collect the ASP.NET hidden form fields,
        then submits the credentials.  Raises :class:`WinmedioAuthError`
        when the login is rejected.
        """
        # Step 1 – fetch the login page
        login_url = self._url("Default.aspx")
        soup = self._get_page(login_url)

        hidden = self._extract_aspnet_hidden_fields(soup)

        # Determine the actual field names by looking for common patterns
        user_field = self._find_input(
            soup,
            r"txt(Ausweis|Benutzer|Username|User|Login)",
            r"(ausweis|benutzer|user|login)",
        ) or "ctl00$ContentPlaceHolder1$txtAusweis"

        pass_field = self._find_input(
            soup,
            r"txt(Kennwort|Passwort|Password|Pass)",
            r"(kennwort|passwort|password)",
        ) or "ctl00$ContentPlaceHolder1$txtKennwort"

        submit_field = self._find_input(
            soup,
            r"btn(Login|Anmelden|Ok|Submit)",
        )

        form_data: dict[str, str] = {
            **hidden,
            user_field: self.username,
            pass_field: self.password,
        }
        if submit_field:
            form_data[submit_field] = "Anmelden"

        # Step 2 – submit login form
        response = self._client.post(login_url, data=form_data)
        response.raise_for_status()

        result_soup = BeautifulSoup(response.text, "html.parser")

        # Detect login failure: typically an error message or the login form
        # is still present with an error notice.
        error_selectors = [
            "span.error",
            "div.error",
            "span.errorMessage",
            ".loginError",
            "#ErrorMessage",
            ".alert-danger",
        ]
        for selector in error_selectors:
            error_tag = result_soup.select_one(selector)
            if error_tag and error_tag.get_text(strip=True):
                raise WinmedioAuthError(f"Login failed: {error_tag.get_text(strip=True)}")

        # If the login form is still present it usually means the credentials
        # were rejected.
        still_has_login_form = result_soup.find(
            "input",
            {"name": re.compile(r"(Ausweis|Benutzer|Username)", re.IGNORECASE)},
        )
        if still_has_login_form:
            raise WinmedioAuthError(
                "Login failed: credentials rejected by the portal "
                f"(user field still present in response for {login_url})."
            )

        self._logged_in = True

    def _ensure_logged_in(self) -> None:
        if not self._logged_in:
            self.login()

    # ------------------------------------------------------------------
    # My Account – borrowed items
    # ------------------------------------------------------------------

    def get_rented_items(self) -> list[RentedItem]:
        """Return the list of items currently borrowed from the library.

        The account / "Mein Konto" section of winmedio typically lists
        borrowed items in a table with columns for title, author, due date
        and item number.
        """
        self._ensure_logged_in()

        # Try several common URL patterns for the borrowed-items page
        candidate_urls = [
            self._url("Default.aspx?action=meinkonto"),
            self._url("Default.aspx?action=myaccount"),
            self._url("Account.aspx"),
            self._url("MeinKonto.aspx"),
        ]

        soup: BeautifulSoup | None = None
        for url in candidate_urls:
            try:
                soup = self._get_page(url)
                # Check if we got real content (not a redirect back to login)
                if soup.find(
                    lambda tag: tag.name in ("table", "div")
                    and any(
                        kw in (tag.get("class") or [])
                        for kw in ("ausgeliehen", "rented", "lend", "konto", "account")
                    )
                ):
                    break
            except httpx.HTTPStatusError:
                continue

        if soup is None:
            return []

        return self._parse_rented_items(soup)

    @staticmethod
    def _parse_rented_items(soup: BeautifulSoup) -> list[RentedItem]:
        """Parse borrowed-items tables / divs from an account page soup."""
        items: list[RentedItem] = []

        # Strategy 1 – look for a dedicated table with class hints
        table = soup.find(
            "table",
            {"class": re.compile(r"(ausgeliehen|rented|lend|media)", re.IGNORECASE)},
        )
        if table is None:
            # Strategy 2 – find any table that contains "Fälligkeit" or "Due"
            for t in soup.find_all("table"):
                header_text = t.get_text()
                if re.search(r"(Fälligkeit|Faelligkeit|Due|Rückgabe)", header_text, re.IGNORECASE):
                    table = t
                    break

        if table is None:
            return items

        headers: list[str] = []
        header_row = table.find("tr")
        if header_row:
            headers = [
                th.get_text(strip=True).lower()
                for th in header_row.find_all(["th", "td"])
            ]

        def col_index(*keywords: str) -> int | None:
            for kw in keywords:
                for i, h in enumerate(headers):
                    if kw in h:
                        return i
            return None

        title_idx = col_index("titel", "title", "bezeichnung", "medium")
        author_idx = col_index("autor", "author", "verfasser")
        due_idx = col_index("fällig", "due", "rückgabe", "datum")
        type_idx = col_index("medienart", "type", "art")
        nr_idx = col_index("exemplar", "number", "nummer", "nr")

        rows = table.find_all("tr")[1:]  # skip header row
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            def cell(idx: int | None) -> str:
                if idx is None or idx >= len(cells):
                    return ""
                return cells[idx].get_text(separator=" ", strip=True)

            title = cell(title_idx) if title_idx is not None else cell(0)
            author = cell(author_idx) if author_idx is not None else cell(1)
            due_date = cell(due_idx) if due_idx is not None else ""
            media_type = cell(type_idx) if type_idx is not None else ""
            item_number = cell(nr_idx) if nr_idx is not None else ""

            if not title:
                continue

            items.append(
                RentedItem(
                    title=title,
                    author=author,
                    media_type=media_type,
                    item_number=item_number,
                    due_date=due_date,
                )
            )

        # Strategy 3 – div/span based layout (some winmedio themes)
        if not items:
            items = WinmedioClient._parse_rented_items_divs(soup)

        return items

    @staticmethod
    def _parse_rented_items_divs(soup: BeautifulSoup) -> list[RentedItem]:
        """Parse borrowed items from a div-based layout."""
        items: list[RentedItem] = []
        # Look for item containers by common class names
        containers = soup.find_all(
            "div",
            {"class": re.compile(r"(medium|media|item|titel)", re.IGNORECASE)},
        )
        for container in containers:
            title_tag = container.find(
                ["h3", "h4", "span", "a"],
                {"class": re.compile(r"(titel|title)", re.IGNORECASE)},
            )
            due_tag = container.find(
                ["span", "td", "div"],
                {"class": re.compile(r"(faellig|due|datum|date)", re.IGNORECASE)},
            )
            author_tag = container.find(
                ["span", "td"],
                {"class": re.compile(r"(autor|author)", re.IGNORECASE)},
            )
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                continue
            items.append(
                RentedItem(
                    title=title,
                    author=author_tag.get_text(strip=True) if author_tag else "",
                    media_type="",
                    item_number="",
                    due_date=due_tag.get_text(strip=True) if due_tag else "",
                )
            )
        return items

    # ------------------------------------------------------------------
    # My Account – reservations
    # ------------------------------------------------------------------

    def get_reservations(self) -> list[Reservation]:
        """Return the list of active reservations."""
        self._ensure_logged_in()

        candidate_urls = [
            self._url("Default.aspx?action=meinkonto#tabvorbestellungen"),
            self._url("Default.aspx?action=myaccount#tabreservations"),
            self._url("Default.aspx?action=reservierungen"),
            self._url("Default.aspx?action=reservations"),
            self._url("Account.aspx?tab=reservations"),
        ]

        soup: BeautifulSoup | None = None
        for url in candidate_urls:
            try:
                soup = self._get_page(url)
                break
            except httpx.HTTPStatusError:
                continue

        if soup is None:
            return []

        return self._parse_reservations(soup)

    @staticmethod
    def _parse_reservations(soup: BeautifulSoup) -> list[Reservation]:
        """Parse reservation tables from an account page soup."""
        reservations: list[Reservation] = []

        table = None
        for t in soup.find_all("table"):
            text = t.get_text()
            if re.search(r"(Vorbestellung|Reservation|Bestellung)", text, re.IGNORECASE):
                table = t
                break

        if table is None:
            return reservations

        headers = [
            th.get_text(strip=True).lower()
            for th in (table.find("tr") or {}).find_all(["th", "td"])
        ]

        def col_index(*keywords: str) -> int | None:
            for kw in keywords:
                for i, h in enumerate(headers):
                    if kw in h:
                        return i
            return None

        title_idx = col_index("titel", "title")
        author_idx = col_index("autor", "author")
        status_idx = col_index("status", "verfügbar", "available")
        pos_idx = col_index("position", "warteliste", "queue")
        date_idx = col_index("datum", "date", "abhol", "ready")

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            def cell(idx: int | None) -> str:
                if idx is None or idx >= len(cells):
                    return ""
                return cells[idx].get_text(separator=" ", strip=True)

            title = cell(title_idx) if title_idx is not None else cell(0)
            if not title:
                continue
            reservations.append(
                Reservation(
                    title=title,
                    author=cell(author_idx) if author_idx is not None else cell(1),
                    media_type="",
                    status=cell(status_idx) if status_idx is not None else "",
                    position=cell(pos_idx) if pos_idx is not None else None,
                    available_from=cell(date_idx) if date_idx is not None else None,
                )
            )
        return reservations

    # ------------------------------------------------------------------
    # Account information
    # ------------------------------------------------------------------

    def get_account_info(self) -> AccountInfo:
        """Return basic account information."""
        self._ensure_logged_in()

        candidate_urls = [
            self._url("Default.aspx?action=meinkonto"),
            self._url("Default.aspx?action=myaccount"),
            self._url("Account.aspx"),
        ]

        soup: BeautifulSoup | None = None
        for url in candidate_urls:
            try:
                soup = self._get_page(url)
                break
            except httpx.HTTPStatusError:
                continue

        if soup is None:
            return AccountInfo(name="", card_number=self.username)

        return self._parse_account_info(soup, self.username)

    @staticmethod
    def _parse_account_info(soup: BeautifulSoup, card_number: str) -> AccountInfo:
        """Extract account summary from a page soup."""
        name = ""
        valid_until: str | None = None
        open_fees: str | None = None
        extra: dict[str, str] = {}

        # Name is often in a welcome / greeting heading
        for tag in soup.find_all(["h1", "h2", "h3", "span", "div"]):
            text = tag.get_text(strip=True)
            if re.search(r"(Willkommen|Hallo|Welcome|Hello)", text, re.IGNORECASE) and len(text) < 100:
                # Strip greeting prefix to get the name
                name = re.sub(r"^(Willkommen|Hallo|Welcome|Hello)[,\s]+", "", text, flags=re.IGNORECASE).strip()
                break

        # Look for labelled values in definition lists or table rows
        for label_tag in soup.find_all(["dt", "th", "td", "label", "span"]):
            label_text = label_tag.get_text(strip=True).lower()
            sibling = label_tag.find_next_sibling(["dd", "td", "span"])
            if not sibling:
                continue
            value = sibling.get_text(strip=True)

            if re.search(r"(gültig|valid|ablauf)", label_text):
                valid_until = value
            elif re.search(r"(gebühr|fee|kosten|betrag)", label_text):
                open_fees = value
            elif re.search(r"(name|nachname)", label_text):
                name = name or value
            elif value:
                extra[label_tag.get_text(strip=True)] = value

        return AccountInfo(
            name=name,
            card_number=card_number,
            valid_until=valid_until,
            open_fees=open_fees,
            extra=extra,
        )

    # ------------------------------------------------------------------
    # Catalog search
    # ------------------------------------------------------------------

    def search_catalog(
        self,
        query: str,
        search_type: str = "all",
        max_results: int = 20,
    ) -> list[SearchResult]:
        """Search the library catalog.

        Parameters
        ----------
        query:
            Free-text search term.
        search_type:
            One of ``"all"``, ``"title"``, ``"author"``, ``"isbn"``.
        max_results:
            Maximum number of results to return.
        """
        self._ensure_logged_in()

        # Map search type to common winmedio parameter values
        type_map = {
            "all": "0",
            "title": "1",
            "author": "2",
            "isbn": "4",
        }
        search_code = type_map.get(search_type.lower(), "0")

        search_params = {
            "action": "search",
            "query": query,
            "type": search_code,
            "suche": query,
            "suchtyp": search_code,
        }

        search_url = self._url("Default.aspx")

        # Some installations use a dedicated search endpoint
        try:
            soup = self._get_page(search_url, params=search_params)
        except httpx.HTTPStatusError:
            return []

        return self._parse_search_results(soup)[:max_results]

    @staticmethod
    def _parse_search_results(soup: BeautifulSoup) -> list[SearchResult]:
        """Parse catalog search results."""
        results: list[SearchResult] = []

        # Look for result tables or result containers
        table = soup.find(
            "table",
            {"class": re.compile(r"(result|treffer|ergebnis|search)", re.IGNORECASE)},
        )
        if table is None:
            for t in soup.find_all("table"):
                if len(t.find_all("tr")) > 2:
                    table = t
                    break

        if table:
            headers = [
                th.get_text(strip=True).lower()
                for th in (table.find("tr") or {}).find_all(["th", "td"])
            ]

            def col_index(*keywords: str) -> int | None:
                for kw in keywords:
                    for i, h in enumerate(headers):
                        if kw in h:
                            return i
                return None

            title_idx = col_index("titel", "title")
            author_idx = col_index("autor", "author")
            year_idx = col_index("jahr", "year", "erschein")
            avail_idx = col_index("verfügbar", "available", "status", "bestand")
            type_idx = col_index("medienart", "type", "art")

            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue

                def cell(idx: int | None) -> str:
                    if idx is None or idx >= len(cells):
                        return ""
                    return cells[idx].get_text(separator=" ", strip=True)

                title = cell(title_idx) if title_idx is not None else cell(0)
                if not title:
                    continue
                results.append(
                    SearchResult(
                        title=title,
                        author=cell(author_idx) if author_idx is not None else cell(1),
                        media_type=cell(type_idx) if type_idx is not None else "",
                        year=cell(year_idx) if year_idx is not None else None,
                        availability=cell(avail_idx) if avail_idx is not None else None,
                    )
                )

        return results

    # ------------------------------------------------------------------
    # Renew borrowed items
    # ------------------------------------------------------------------

    def renew_item(self, item_number: str) -> dict[str, str]:
        """Attempt to renew a borrowed item by its item/copy number.

        Returns a dict with keys ``"success"`` (bool as string) and
        ``"message"``.
        """
        self._ensure_logged_in()

        # Navigate to account page first to get form state
        account_url = self._url("Default.aspx?action=meinkonto")
        try:
            soup = self._get_page(account_url)
        except httpx.HTTPStatusError as exc:
            return {"success": "false", "message": str(exc)}

        hidden = self._extract_aspnet_hidden_fields(soup)

        # Find the renewal form / button for this item
        renew_form_data: dict[str, str] = {**hidden}

        # winmedio typically uses a button or checkbox per item
        renew_button = soup.find(
            "input",
            {
                "type": re.compile(r"(submit|button)", re.IGNORECASE),
                "name": re.compile(r"renew|verlängern|verlaengern", re.IGNORECASE),
            },
        )
        if renew_button and renew_button.get("name"):
            renew_form_data[renew_button["name"]] = item_number

        # Some portals use checkboxes with the item number as value
        checkbox = soup.find("input", {"type": "checkbox", "value": item_number})
        if checkbox and checkbox.get("name"):
            renew_form_data[checkbox["name"]] = item_number

        if len(renew_form_data) == len(hidden):
            # No specific renew control found; try a generic POST
            renew_form_data["action"] = "renew"
            renew_form_data["itemNumber"] = item_number
            renew_form_data["MedienNrExemplar"] = item_number

        try:
            response = self._client.post(account_url, data=renew_form_data)
            response.raise_for_status()
            result_soup = BeautifulSoup(response.text, "html.parser")

            # Look for success / error messages
            for selector in [".success", ".alert-success", ".successMessage"]:
                tag = result_soup.select_one(selector)
                if tag:
                    return {"success": "true", "message": tag.get_text(strip=True)}

            for selector in [".error", ".alert-danger", ".errorMessage"]:
                tag = result_soup.select_one(selector)
                if tag:
                    return {"success": "false", "message": tag.get_text(strip=True)}

            return {"success": "true", "message": "Renewal request submitted."}

        except httpx.HTTPStatusError as exc:
            return {"success": "false", "message": str(exc)}

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "WinmedioClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()
