"""
winmedio JSON API client.

Handles authentication and data retrieval from a winmedio library portal
via its REST/JSON API.

Configuration is done via environment variables:
    LIBRARY_NAME       – Library identifier used in the URL path,
                         e.g. "buelach" → https://www.winmedio.net/buelach/api/…
    WINMEDIO_USERNAME  – Library card number / user name
    WINMEDIO_PASSWORD  – Account password
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


BASE_URL = "https://www.winmedio.net"


@dataclass
class RentedItem:
    """A single item currently borrowed from the library."""

    title: str
    due_date: str
    id: str
    canRenew: bool


class WinmedioAuthError(Exception):
    """Raised when authentication fails."""


class WinmedioClient:
    """HTTP client for the winmedio JSON API.

    Uses a persistent :class:`httpx.Client` to maintain session cookies
    across requests so that a single login suffices for all subsequent calls.
    """

    def __init__(self, library_name: str, username: str, password: str) -> None:
        self.library_name = library_name
        self.username = username
        self.password = password
        self._client: httpx.Client = httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        self._adresse_id: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _api_url(self, path: str) -> str:
        """Build an absolute API URL from a relative *path*."""
        return f"{BASE_URL}/{self.library_name}/api/{path.lstrip('/')}"

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate against the winmedio portal.

        POSTs credentials to the login endpoint and stores the returned
        ``adresseId`` for subsequent API calls.

        Raises :class:`WinmedioAuthError` when the login is rejected.
        """
        login_url = self._api_url("auth/login")
        payload = {
            "email": "",
            "password": str(self.password),
            "stayLoggedIn": True,
            "username": str(self.username),
            "verbundBibliothek": 0,
        }

        response = self._client.post(login_url, json=payload)
        response.raise_for_status()

        data = response.json()

        if data.get("hasErrors"):
            messages = data.get("validationMessages") or data.get("exceptions") or []
            msg = "; ".join(str(m) for m in messages) if messages else "Unknown error"
            raise WinmedioAuthError(f"Login failed: {msg}")

        data_object = data.get("dataObject")
        if not data_object or not data_object.get("adresseId"):
            raise WinmedioAuthError(
                "Login failed: no adresseId in response. "
                "Check credentials and library name."
            )

        self._adresse_id = data_object["adresseId"]

    def _ensure_logged_in(self) -> None:
        if self._adresse_id is None:
            self.login()

    # ------------------------------------------------------------------
    # Rented items (Ausleihen)
    # ------------------------------------------------------------------

    def get_rented_items(self) -> list[RentedItem]:
        """Return the list of items currently borrowed from the library.

        Each item contains:
        - title: extracted from the "TitelKurz" field
        - due_date: extracted from the "Ausleihen_AuslBis" field
        """
        self._ensure_logged_in()

        url = self._api_url(f"account/ausleihen/{self._adresse_id}/2")
        response = self._client.get(url)
        response.raise_for_status()

        data = response.json()

        if data.get("hasErrors"):
            messages = data.get("validationMessages") or data.get("exceptions") or []
            msg = "; ".join(str(m) for m in messages) if messages else "Unknown error"
            raise RuntimeError(f"Error fetching rented items: {msg}")

        items: list[RentedItem] = []
        for entry in data.get("dataObject") or []:
            title = ""
            due_date = ""
            id = entry.get("exemplarId", "")
            can_renew = entry.get("canRenew", True)

            for feld in entry.get("felder") or []:
                label = feld.get("label", "")
                if label == "TitelKurz":
                    title = feld.get("value", "")
                elif label == "Ausleihen_AuslBis":
                    due_date = feld.get("value", "")

            if title:
                items.append(RentedItem(title=title, due_date=due_date, id=id, canRenew=can_renew))

        return items

    # ------------------------------------------------------------------
    # Is allowed extend (Ausleihen_Verlaengern)
    # ------------------------------------------------------------------

    def get_is_allowed_extend(self, id: str) -> bool:
        """Return true if the item with the given id can be extended."""
        self._ensure_logged_in()

        adresse_id = self._adresse_id

        url = self._api_url(f"account/renew")
        response = self._client.post(url, json={
            "adresseId": adresse_id,
            "childId": "",
            "id": id,
            "isAnfrage": True,
            "isLehrer": False,
            "transHerkunft": 2,
        })
        response.raise_for_status()

        data = response.json()

        if data.get("hasErrors"):
            messages = data.get("validationMessages") or data.get("exceptions") or []
            msg = "; ".join(str(m) for m in messages) if messages else "Unknown error"
            raise RuntimeError(f"Error checking if book can be extended: {msg}")

        return data.get("dataObject") == "true"

    # ------------------------------------------------------------------
    # Extend (Ausleihen_Verlaengern)
    # ------------------------------------------------------------------

    def extend(self, id: str) -> str:
        """Extend the item with the given id."""
        self._ensure_logged_in()

        adresse_id = self._adresse_id

        url = self._api_url(f"account/renew")
        response = self._client.post(url, json={
            "adresseId": adresse_id,
            "childId": "",
            "id": id,
            "isAnfrage": False,
            "isLehrer": False,
            "transHerkunft": 2,
        })
        response.raise_for_status()

        data = response.json()

        if data.get("hasErrors"):
            messages = data.get("validationMessages") or data.get("exceptions") or []
            msg = "; ".join(str(m) for m in messages) if messages else "Unknown error"
            raise RuntimeError(f"Error checking if book can be extended: {msg}")

        return data.get("dataObject") == "true"

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "WinmedioClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()
