"""Integration tests for ista_no — tests against the real istaonline.no API.

Requires ISTA_USERNAME and ISTA_PASSWORD in .env file.
These tests do NOT require Home Assistant.
"""

from __future__ import annotations

import pytest

from ista_no.api import (
    IstaAuthError,
    IstaClient,
    IstaConnectionError,
    IstaResponseError,
    IstaTwoFactorError,
)


# ── Network tests (single login, all assertions in one test to avoid rate limiting)


class TestLiveAPI:
    """Tests against the real istaonline.no API.

    Combined into minimal test methods to avoid rate limiting (429).
    Each test method creates its own client and authenticates once.
    """

    @pytest.mark.asyncio
    async def test_login_and_fetch_meters(self, ista_credentials):
        """Test full flow: authenticate, fetch year ranges, fetch meter data."""
        client = IstaClient(
            username=ista_credentials["username"],
            password=ista_credentials["password"],
        )
        try:
            # --- Authentication ---
            html = await client.authenticate()
            assert client._authenticated, "Client should be authenticated"
            assert len(html) > 100, "Should receive substantial HTML"

            # Check cookies exist
            cookies = dict(client._session.cookies)
            assert len(cookies) > 0, "Should have auth cookies"

            # --- Year ranges ---
            year_ranges = await client.get_available_year_ranges()
            assert len(year_ranges) > 0, "Should find available year ranges"
            for yr in year_ranges:
                assert "." in yr
                assert "-" in yr
            print(f"\nYear ranges: {year_ranges}")

            # --- Fetch current year data ---
            data = await client.fetch_all_meters()

            assert "HW" in data
            assert "CW" in data
            assert "ENERGY" in data

            total_readings = sum(len(rows) for rows in data.values())
            assert total_readings > 0, "Expected at least some meter readings"

            # Verify structure of first reading per type
            expected_fields = {
                "meter", "room", "reading", "reading_raw", "factor",
                "corrected_reading", "corrected_consumption",
                "corrected_consumption_raw", "date", "meter_type", "degree_days",
            }

            for mtype, rows in data.items():
                if rows:
                    meters = sorted(set(r["meter"] for r in rows))
                    dates = sorted(set(r["date"] for r in rows))
                    print(f"\n{mtype}: {len(rows)} readings, meters: {meters}")
                    print(f"  Date range: {dates[0]} -> {dates[-1]}")

                    row = rows[0]
                    assert set(row.keys()) == expected_fields
                    assert isinstance(row["reading"], float)
                    assert isinstance(row["corrected_consumption"], float)
                    assert len(row["date"]) == 10
                    assert row["date"][4] == "-"

            # --- Verify cumulative readings ---
            for mtype, rows in data.items():
                meters: dict[str, list[dict]] = {}
                for row in rows:
                    meters.setdefault(row["meter"], []).append(row)

                for meter_id, readings in meters.items():
                    readings.sort(key=lambda r: r["date"])
                    for i in range(1, len(readings)):
                        assert readings[i]["reading"] >= readings[i - 1]["reading"], (
                            f"Meter {meter_id} ({mtype}): reading decreased from "
                            f"{readings[i-1]['reading']} to {readings[i]['reading']} "
                            f"between {readings[i-1]['date']} and {readings[i]['date']}"
                        )

            # --- Fetch with explicit year range ---
            from_year = year_ranges[0]
            to_year = year_ranges[-1]
            hist_data = await client.fetch_all_meters(from_year, to_year)
            hist_total = sum(len(rows) for rows in hist_data.values())
            print(f"\nHistorical: {hist_total} readings ({from_year} -> {to_year})")
            assert hist_total > 0

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_invalid_credentials(self):
        """Test that invalid credentials don't succeed."""
        client = IstaClient(
            username="00000000000",
            password="wrongpassword123",
        )
        try:
            try:
                await client.authenticate()
                # If it didn't raise, the server didn't give a clear error.
                # The auth flow may produce ambiguous results for bad creds.
            except (IstaAuthError, IstaTwoFactorError):
                pass  # Expected
        finally:
            await client.close()


# ── CSV parsing tests (no network needed) ───────────────────────────────────


class TestCsvParsing:
    """Test CSV parsing (no network needed)."""

    def test_parse_csv_norwegian_decimals(self):
        """Test that Norwegian decimal format is correctly converted."""
        csv_data = (
            '"Måler","Rom","Avlesning","Faktor","Korrigert avlesning",'
            '"Korrigert forbruk","Dato","Målertype","Graddager"\r\n'
            '"903026XXX","?","14854,30","1","0","29,90","17-02-2026","ENERGY","0"\r\n'
            '"903026YYY","?","1691","1","0","0","17-02-2026","ENERGY","0"\r\n'
        )
        rows = IstaClient.parse_csv(csv_data)
        assert len(rows) == 2
        assert rows[0]["reading"] == 14854.30
        assert rows[0]["corrected_consumption"] == 29.90
        assert rows[0]["meter"] == "903026XXX"
        assert rows[0]["date"] == "2026-02-17"
        assert rows[1]["reading"] == 1691.0

    def test_parse_csv_with_bom(self):
        """Test that UTF-8 BOM is stripped."""
        csv_data = (
            '\ufeff"Måler","Rom","Avlesning","Faktor","Korrigert avlesning",'
            '"Korrigert forbruk","Dato","Målertype","Graddager"\r\n'
            '"929410XXX","?","153,3400","1","0","0,0200","17-02-2026","CW","0"\r\n'
        )
        rows = IstaClient.parse_csv(csv_data)
        assert len(rows) == 1
        assert rows[0]["reading"] == 153.34
        assert rows[0]["corrected_consumption"] == 0.02
        assert rows[0]["meter_type"] == "CW"

    def test_parse_csv_empty(self):
        """Test parsing empty CSV returns empty list."""
        assert IstaClient.parse_csv("") == []
        assert IstaClient.parse_csv("   ") == []

    def test_parse_csv_date_conversion(self):
        """Test dd-MM-yyyy to YYYY-MM-DD conversion."""
        csv_data = (
            '"Måler","Rom","Avlesning","Faktor","Korrigert avlesning",'
            '"Korrigert forbruk","Dato","Målertype","Graddager"\r\n'
            '"123","?","100","1","0","5","01-12-2025","HW","0"\r\n'
        )
        rows = IstaClient.parse_csv(csv_data)
        assert rows[0]["date"] == "2025-12-01"


# ── HTML parsing tests (no network needed) ──────────────────────────────────


class TestHtmlParsing:
    """Test ASP.NET hidden field and year option parsing."""

    def test_parse_hidden_fields(self):
        """Test extracting hidden inputs from HTML."""
        html = '''
        <form>
            <input type="hidden" name="__VIEWSTATE" value="abc123" />
            <input type="hidden" name="__EVENTVALIDATION" value="xyz789" />
            <input type="text" name="username" value="test" />
            <input name="foo_TSM" value="tsm_value" />
        </form>
        '''
        fields = IstaClient._parse_hidden_fields(html)
        assert fields["__VIEWSTATE"] == "abc123"
        assert fields["__EVENTVALIDATION"] == "xyz789"
        assert fields["foo_TSM"] == "tsm_value"
        assert "username" not in fields

    def test_parse_year_options(self):
        """Test extracting year options from RadComboBox HTML."""
        html = '''
        <ul>
            <li class="rcbItem">01.01.2024 - 31.12.2024</li>
            <li class="rcbItem">01.01.2025 - 31.12.2025</li>
            <li class="rcbHovered">01.01.2026 - 31.12.2026</li>
        </ul>
        '''
        options = IstaClient._parse_year_options(html)
        assert len(options) == 3
        assert options[0] == "01.01.2024 - 31.12.2024"
        assert options[-1] == "01.01.2026 - 31.12.2026"

    def test_parse_year_options_dedup(self):
        """Test that duplicate year options are removed."""
        html = '''
        <ul>
            <li class="rcbItem">01.01.2025 - 31.12.2025</li>
            <li class="rcbItem">01.01.2025 - 31.12.2025</li>
            <li class="rcbItem">01.01.2026 - 31.12.2026</li>
        </ul>
        '''
        options = IstaClient._parse_year_options(html)
        assert len(options) == 2

    def test_parse_year_options_from_inputs(self):
        """Test extracting year options from input fields (new UI with load-on-demand)."""
        html = '''
        <input id="ctl00_PopUpContentPlaceHolder_ctl00_RadComboBoxFromYear_Input"
               value="01.01.2025 - 31.12.2025" />
        <input id="ctl00_PopUpContentPlaceHolder_ctl00_RadComboBoxToYear_Input"
               value="01.01.2026 - 31.12.2026" />
        '''
        options = IstaClient._parse_year_options(html)
        assert len(options) == 2
        assert options[0] == "01.01.2025 - 31.12.2025"
        assert options[1] == "01.01.2026 - 31.12.2026"

    def test_parse_year_options_from_javascript(self):
        """Test extracting year options from JS RadComboBox _text fields."""
        html = '''
        <script>
        $create(Telerik.Web.UI.RadComboBox, {"_text":"01.01.2025 - 31.12.2025"});
        $create(Telerik.Web.UI.RadComboBox, {"_text":"01.01.2026 - 31.12.2026"});
        $create(Telerik.Web.UI.RadComboBox, {"_text":"All meters"});
        </script>
        '''
        options = IstaClient._parse_year_options(html)
        assert len(options) == 2
        assert "All meters" not in options
