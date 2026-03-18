"""Async client for scraping meter data from istaonline.no.

Uses requests (sync) wrapped with asyncio.to_thread for async compat.
This is necessary because istaonline.no's ASP.NET Telerik forms have encoding
quirks that aiohttp doesn't handle correctly (Telerik EventValidation failures).
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from .const import (
    BASE_URL,
    CSV_CORRECTED_CONSUMPTION,
    CSV_CORRECTED_READING,
    CSV_DATE,
    CSV_DEGREE_DAYS,
    CSV_EXPORT_TARGET,
    CSV_FACTOR,
    CSV_METER,
    CSV_METER_TYPE,
    CSV_READING,
    CSV_ROOM,
    DEFAULT_HEADERS,
    FIELD_EXPORT_ALL_PAGES,
    FIELD_EXPORT_DATA_ONLY,
    FIELD_EXPORT_NEW_WINDOW,
    FIELD_FINGERPRINT,
    FIELD_FROM_YEAR,
    FIELD_LOGIN_BUTTON,
    FIELD_PAGER_STATE,
    FIELD_PASSWORD,
    FIELD_PASSWORD_STATE,
    FIELD_TO_YEAR,
    FIELD_USERNAME,
    FINGERPRINT,
    LOGIN_PATH,
    METER_BUTTON,
    METER_TYPES,
    PAGER_STATE_PAGE0,
)

_LOGGER = logging.getLogger(__name__)


# ── Exception hierarchy ─────────────────────────────────────────────────────


class IstaError(Exception):
    """Base error from istaonline.no."""


class IstaAuthError(IstaError):
    """Raised when authentication fails (bad credentials)."""


class IstaTwoFactorError(IstaError):
    """Raised when 2FA is required (not supported)."""


class IstaConnectionError(IstaError):
    """Raised when connection to istaonline.no fails (network/SSL/timeout)."""


class IstaResponseError(IstaError):
    """Raised when istaonline.no returns an unexpected response (200 with error page)."""


# ── Client ──────────────────────────────────────────────────────────────────


class IstaClient:
    """Async client for istaonline.no meter data.

    Uses requests internally (via asyncio.to_thread) because istaonline.no's
    ASP.NET Telerik forms require exact form encoding that aiohttp doesn't match.
    """

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._authenticated = False

    async def close(self) -> None:
        """Close the underlying requests session."""
        self._session.close()

    # ── HTML parsing helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_hidden_fields(html: str) -> dict[str, str]:
        """Extract hidden <input> fields and TSM fields from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        fields: dict[str, str] = {}
        for inp in soup.find_all("input"):
            name = inp.get("name", "")
            if not name:
                continue
            if inp.get("type") == "hidden" or name.endswith("_TSM"):
                fields[name] = inp.get("value", "")
        return fields

    @staticmethod
    def _aspnet_form_data(
        html: str, extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Return all hidden fields merged with extra overrides."""
        fields = IstaClient._parse_hidden_fields(html)
        if "__VIEWSTATE" not in fields:
            _LOGGER.error(
                "No __VIEWSTATE found in HTML — page may not be an ASP.NET form. "
                "HTML starts with: %.200s",
                html[:200],
            )
            raise IstaResponseError(
                "Expected ASP.NET form but no __VIEWSTATE found in page. "
                "The server may have returned an error page."
            )
        if extra:
            fields.update(extra)
        return fields

    @staticmethod
    def _parse_year_options(html: str) -> list[str]:
        """Extract available year-period options from the popup page.

        Tries three strategies:
        1. RadComboBox <li> items (older UI)
        2. Input field values for FromYear/ToYear (current UI with load-on-demand)
        3. JavaScript _text fields in RadComboBox configs
        """
        date_pattern = re.compile(r"\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}")
        seen: set[str] = set()
        options: list[str] = []

        def _add(text: str) -> None:
            text = text.strip()
            if text and text not in seen and date_pattern.match(text):
                seen.add(text)
                options.append(text)

        # Strategy 1: <li> items in RadComboBox dropdown
        soup = BeautifulSoup(html, "html.parser")
        for li in soup.find_all("li"):
            cls = li.get("class", [])
            cls_str = " ".join(cls) if isinstance(cls, list) else cls
            if "rcbItem" in cls_str or "rcbHovered" in cls_str:
                _add(li.get_text(strip=True))

        # Strategy 2: Input values for ComboBoxFromYear/ToYear
        if not options:
            for inp in soup.find_all("input"):
                inp_id = inp.get("id", "")
                if "ComboBoxFromYear_Input" in inp_id or "ComboBoxToYear_Input" in inp_id:
                    _add(inp.get("value", ""))

        # Strategy 3: _text fields in JavaScript RadComboBox configs
        if not options:
            for m in re.finditer(r'"_text"\s*:\s*"([^"]+)"', html):
                _add(m.group(1))

        # Sort chronologically (earliest first)
        options.sort()

        return options

    @staticmethod
    def _reformat_date(date_str: str) -> str:
        """Convert dd-MM-yyyy to YYYY-MM-DD."""
        try:
            return datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError:
            _LOGGER.warning("Could not parse date '%s', expected dd-MM-yyyy", date_str)
            return date_str

    @staticmethod
    def _parse_norwegian_number(value: str) -> float:
        """Convert Norwegian decimal format (comma separator) to float."""
        if not value:
            return 0.0
        try:
            return float(value.replace(",", "."))
        except ValueError:
            _LOGGER.warning(
                "Could not parse number '%s' as float, returning 0.0", value
            )
            return 0.0

    @staticmethod
    def _extract_page_title(html: str) -> str:
        """Extract <title> text from HTML for error reporting."""
        match = re.search(r"<title>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _check_for_errors(html: str, context: str = "") -> None:
        """Check HTML response for error messages and log/raise them.

        istaonline.no returns HTTP 200 for many error conditions,
        with error details only visible in the HTML body.
        """
        title = IstaClient._extract_page_title(html)

        # WAF / rate-limiting challenge page
        if title == "Validation request":
            # Extract attempts remaining if present
            attempts_match = re.search(
                r"Number of attempts left\s*:\s*(\d+)", html
            )
            attempts = attempts_match.group(1) if attempts_match else "?"
            _LOGGER.error(
                "WAF rate-limit page returned during %s "
                "(attempts remaining: %s). Full page: %.500s",
                context,
                attempts,
                html,
            )
            raise IstaConnectionError(
                f"Rate limited by istaonline.no WAF during {context}. "
                f"Attempts remaining: {attempts}. Wait a few minutes and retry."
            )

        # Generic ASP.NET error page
        if "Server Error" in title or "Runtime Error" in title:
            _LOGGER.error(
                "ASP.NET server error during %s. Title: '%s'. HTML: %.500s",
                context,
                title,
                html,
            )
            raise IstaResponseError(
                f"Server error during {context}: {title}"
            )

        # Check for error divs/spans with Norwegian error messages
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.select(
            ".error, .errormsg, #errormsg, .validation-summary-errors"
        ):
            text = el.get_text(strip=True)
            if text:
                _LOGGER.warning("Server error message during %s: %s", context, text)

        # Specific Norwegian error messages
        if "Feil brukernavn eller passord" in html:
            raise IstaAuthError("Invalid username or password (server message)")
        if "Session expired" in html or "Session utløpt" in html:
            raise IstaResponseError(f"Session expired during {context}")
        if "Uventet feil" in html:
            _LOGGER.error(
                "Unexpected error ('Uventet feil') during %s. HTML: %.500s",
                context,
                html,
            )
            raise IstaResponseError(f"Unexpected server error during {context}")

    # ── Sync HTTP methods (run via to_thread) ───────────────────────────────

    def _sync_get(self, url: str) -> requests.Response:
        """GET request with error handling."""
        try:
            r = self._session.get(url, timeout=30)
            r.raise_for_status()
            return r
        except requests.Timeout as err:
            _LOGGER.error("Request timed out: GET %s", url)
            raise IstaConnectionError(f"Request timed out: {url}") from err
        except requests.SSLError as err:
            _LOGGER.error("SSL error connecting to %s: %s", url, err)
            raise IstaConnectionError(
                f"SSL certificate error connecting to istaonline.no: {err}"
            ) from err
        except requests.ConnectionError as err:
            _LOGGER.error("Connection failed: GET %s: %s", url, err)
            raise IstaConnectionError(f"Connection failed: {err}") from err
        except requests.HTTPError as err:
            status = err.response.status_code if err.response is not None else "?"
            _LOGGER.error("HTTP %s from GET %s", status, url)
            if status == 429:
                raise IstaConnectionError(
                    "Rate limited by istaonline.no (429). Try again later."
                ) from err
            raise IstaConnectionError(f"HTTP error {status}: {err}") from err

    def _sync_post(
        self, url: str, data: dict[str, str]
    ) -> requests.Response:
        """POST request with error handling."""
        try:
            r = self._session.post(url, data=data, allow_redirects=True, timeout=30)
            r.raise_for_status()
            return r
        except requests.Timeout as err:
            _LOGGER.error("Request timed out: POST %s", url)
            raise IstaConnectionError(f"Request timed out: {url}") from err
        except requests.SSLError as err:
            _LOGGER.error("SSL error connecting to %s: %s", url, err)
            raise IstaConnectionError(
                f"SSL certificate error connecting to istaonline.no: {err}"
            ) from err
        except requests.ConnectionError as err:
            _LOGGER.error("Connection failed: POST %s: %s", url, err)
            raise IstaConnectionError(f"Connection failed: {err}") from err
        except requests.HTTPError as err:
            status = err.response.status_code if err.response is not None else "?"
            _LOGGER.error("HTTP %s from POST %s", status, url)
            if status == 429:
                raise IstaConnectionError(
                    "Rate limited by istaonline.no (429). Try again later."
                ) from err
            raise IstaConnectionError(f"HTTP error {status}: {err}") from err

    def _sync_authenticate(self) -> str:
        """Synchronous login flow."""
        login_url = f"{BASE_URL}{LOGIN_PATH}"

        # Step 1 — GET login page
        r = self._sync_get(login_url)
        html = r.text
        self._check_for_errors(html, "login page load")

        # Step 2 — POST credentials
        form = self._aspnet_form_data(html, {
            FIELD_USERNAME: self.username,
            FIELD_PASSWORD: self.password,
            FIELD_PASSWORD_STATE: (
                f'{{"enabled":true,"emptyMessage":"",'
                f'"validationText":"{self.password}",'
                f'"valueAsString":"{self.password}",'
                f'"lastSetTextBoxValue":"{self.password}"}}'
            ),
            FIELD_LOGIN_BUTTON: "Logg inn",
            FIELD_FINGERPRINT: FINGERPRINT,
        })

        r = self._sync_post(login_url, form)
        html = r.text
        final_url = r.url

        # Check for errors in the response
        self._check_for_errors(html, "login POST")

        # Check for 2FA
        if "enter the code to proceed" in html or "authenticator" in html.lower():
            raise IstaTwoFactorError(
                "Two-factor authentication is required but not supported"
            )

        # Check if login succeeded
        if "Forbruk" in html or "PopUp_Table" in html:
            self._authenticated = True
            _LOGGER.debug("Login successful (content verified)")
            return html

        # Check URL — Tenant.aspx means success
        if "Tenant" in final_url and "Login" not in final_url:
            self._authenticated = True
            _LOGGER.debug("Login successful (URL verified: %s)", final_url)
            return html

        # Still on login page = auth failed
        if "edtPassword" in html:
            raise IstaAuthError("Invalid username or password")

        # Ambiguous state — log full details for debugging
        title = self._extract_page_title(html)
        _LOGGER.warning(
            "Login result ambiguous. url=%s, title='%s', "
            "has_forbruk=%s, has_password_field=%s. HTML: %.500s",
            final_url,
            title,
            "Forbruk" in html,
            "edtPassword" in html,
            html,
        )
        self._authenticated = True
        return html

    def _sync_get_popup_page(self) -> tuple[str, str]:
        """GET the PopUp table page."""
        ts = int(datetime.now().timestamp() * 1000)
        url = (
            f"{BASE_URL}/PopUp.aspx"
            f"?Control=PopUp_Table&Metertype=ENERGY&cons_id={self.username}"
            f"&Culture=&rwndrnd=0.{ts}"
        )
        r = self._sync_get(url)

        # Check if we got redirected to login (session expired)
        if "Login.aspx" in r.url and "edtPassword" in r.text:
            _LOGGER.warning(
                "Session expired — popup page redirected to login (url=%s)", r.url
            )
            raise IstaResponseError(
                "Session expired — redirected to login page when accessing meter data"
            )

        self._check_for_errors(r.text, "popup page")

        # Verify the page looks like a meter popup (should have PopUp content)
        if "PopUpContentPlaceHolder" not in r.text:
            title = self._extract_page_title(r.text)
            _LOGGER.error(
                "Popup page missing expected content "
                "(no PopUpContentPlaceHolder). title='%s', url=%s. HTML: %.500s",
                title,
                r.url,
                r.text,
            )
            raise IstaResponseError(
                f"Popup page has unexpected content (title='{title}'). "
                "Login session may have expired."
            )

        return r.text, url

    def _sync_post_form(
        self, url: str, html: str, extra: dict[str, str]
    ) -> requests.Response:
        """Build form data from html + extra and POST."""
        form = self._aspnet_form_data(html, extra)
        r = self._sync_post(url, form)
        self._check_for_errors(r.text, "form post")
        return r

    def _sync_switch_meter_type(
        self, url: str, html: str, meter_type: str
    ) -> str:
        """Click the meter-type image button; return new page HTML."""
        btn = METER_BUTTON[meter_type]
        extra = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            f"{btn}.x": "10",
            f"{btn}.y": "10",
        }
        r = self._sync_post_form(url, html, extra)
        result_html = r.text

        # Verify the switch worked — page should still have popup content
        if "PopUpContentPlaceHolder" not in result_html:
            title = self._extract_page_title(result_html)
            _LOGGER.error(
                "Meter type switch to %s returned unexpected page. "
                "title='%s', url=%s. HTML: %.500s",
                meter_type,
                title,
                r.url,
                result_html,
            )
            raise IstaResponseError(
                f"Meter type switch to {meter_type} failed — "
                f"unexpected page returned (title='{title}')"
            )

        return result_html

    def _sync_export_csv(
        self, url: str, html: str, from_year: str = "", to_year: str = ""
    ) -> str:
        """Click the CSV-export button; return raw CSV text."""
        extra: dict[str, str] = {
            "__EVENTTARGET": CSV_EXPORT_TARGET,
            "__EVENTARGUMENT": "",
            FIELD_EXPORT_DATA_ONLY: "on",
            FIELD_EXPORT_ALL_PAGES: "on",
            FIELD_EXPORT_NEW_WINDOW: "on",
            FIELD_PAGER_STATE: PAGER_STATE_PAGE0,
        }
        if from_year:
            extra[FIELD_FROM_YEAR] = from_year
        if to_year:
            extra[FIELD_TO_YEAR] = to_year

        r = self._sync_post_form(url, html, extra)

        content_type = r.headers.get("Content-Type", "")
        content_disp = r.headers.get("Content-Disposition", "")
        if "text/csv" in content_type or "IstaExportToCSV" in content_disp:
            return r.text

        # Got HTML back instead of CSV — this is an error
        title = self._extract_page_title(r.text)
        _LOGGER.error(
            "CSV export returned text/html instead of text/csv. "
            "Content-Type='%s', title='%s', url=%s. HTML: %.500s",
            content_type,
            title,
            r.url,
            r.text,
        )

        # Try to extract a meaningful error from the HTML
        self._check_for_errors(r.text, "CSV export")

        # If _check_for_errors didn't raise, raise a generic error
        raise IstaResponseError(
            f"CSV export returned HTML instead of CSV "
            f"(Content-Type='{content_type}', title='{title}'). "
            f"The server may have returned an error page."
        )

    def _sync_fetch_all_meters(
        self, from_year: str = "", to_year: str = ""
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch CSV data for all three meter types."""
        popup_html, popup_url = self._sync_get_popup_page()

        if not from_year or not to_year:
            year_options = self._parse_year_options(popup_html)
            if year_options:
                current = year_options[-1]
                from_year = from_year or current
                to_year = to_year or current
                _LOGGER.debug("Using year period: %s", current)
            else:
                _LOGGER.warning(
                    "No year options found in popup page — "
                    "using server defaults for date range"
                )

        results: dict[str, list[dict[str, Any]]] = {}

        for mtype in METER_TYPES:
            page_html = self._sync_switch_meter_type(
                popup_url, popup_html, mtype
            )
            raw_csv = self._sync_export_csv(
                popup_url, page_html, from_year, to_year
            )
            rows = self.parse_csv(raw_csv)
            results[mtype] = rows
            popup_html = page_html

            if rows:
                meters = sorted(set(r["meter"] for r in rows))
                _LOGGER.debug(
                    "%s: %d readings, meters: %s", mtype, len(rows), meters
                )
            else:
                _LOGGER.info("%s: no readings returned", mtype)

        total = sum(len(rows) for rows in results.values())
        if total == 0:
            _LOGGER.warning(
                "All meter types returned zero readings. "
                "from_year=%s, to_year=%s",
                from_year,
                to_year,
            )

        return results

    def _sync_get_available_year_ranges(self) -> list[str]:
        """Get the popup page and parse available year options."""
        html, _ = self._sync_get_popup_page()
        options = self._parse_year_options(html)
        if not options:
            _LOGGER.warning("No year range options found in popup page")
        return options

    # ── Async public API (wraps sync methods via to_thread) ─────────────────

    async def authenticate(self) -> str:
        """Authenticate with istaonline.no."""
        return await asyncio.to_thread(self._sync_authenticate)

    async def get_available_year_ranges(self) -> list[str]:
        """Get available year range options."""
        return await asyncio.to_thread(self._sync_get_available_year_ranges)

    async def fetch_all_meters(
        self, from_year: str = "", to_year: str = ""
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch CSV data for all three meter types."""
        return await asyncio.to_thread(
            self._sync_fetch_all_meters, from_year, to_year
        )

    # ── CSV parsing (static, no I/O) ───────────────────────────────────────

    @staticmethod
    def parse_csv(raw: str) -> list[dict[str, Any]]:
        """Parse an Ista CSV export into a list of dicts."""
        if not raw.strip():
            return []
        raw = raw.lstrip("\ufeff")

        reader = csv.DictReader(io.StringIO(raw))

        # Validate that expected columns exist
        if reader.fieldnames:
            expected = {CSV_METER, CSV_READING, CSV_DATE, CSV_METER_TYPE}
            actual = set(reader.fieldnames)
            missing = expected - actual
            if missing:
                _LOGGER.error(
                    "CSV missing expected columns: %s. "
                    "Got columns: %s. First 200 chars: %.200s",
                    missing,
                    reader.fieldnames,
                    raw,
                )
                return []
        else:
            _LOGGER.error("CSV has no headers. First 200 chars: %.200s", raw)
            return []

        rows = []
        for line_num, row in enumerate(reader, start=2):
            meter = row.get(CSV_METER, "").strip()
            date_raw = row.get(CSV_DATE, "").strip()

            # Skip rows with missing critical fields
            if not meter or not date_raw:
                _LOGGER.warning(
                    "CSV line %d: skipping row with empty meter='%s' or date='%s'",
                    line_num,
                    meter,
                    date_raw,
                )
                continue

            reading_str = row.get(CSV_READING, "").strip()
            consumption_str = row.get(CSV_CORRECTED_CONSUMPTION, "").strip()

            rows.append({
                "meter": meter,
                "room": row.get(CSV_ROOM, "").strip(),
                "reading": IstaClient._parse_norwegian_number(reading_str),
                "reading_raw": reading_str,
                "factor": row.get(CSV_FACTOR, "").strip(),
                "corrected_reading": row.get(CSV_CORRECTED_READING, "").strip(),
                "corrected_consumption": IstaClient._parse_norwegian_number(
                    consumption_str
                ),
                "corrected_consumption_raw": consumption_str,
                "date": IstaClient._reformat_date(date_raw),
                "meter_type": row.get(CSV_METER_TYPE, "").strip(),
                "degree_days": row.get(CSV_DEGREE_DAYS, "").strip(),
            })

        return rows
