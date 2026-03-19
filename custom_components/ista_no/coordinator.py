"""DataUpdateCoordinator for Ista Norway."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    IstaAuthError,
    IstaClient,
    IstaConnectionError,
    IstaResponseError,
    IstaTwoFactorError,
)
from .const import DOMAIN, LABEL, METER_TYPES, UNIT

_LOGGER = logging.getLogger(__name__)

# Polling schedule:
# - Check at 4am daily
# - After 4am, check every hour until today's data is received
# - If no data received for 24h, fall back to once daily at 4am
DAILY_CHECK_HOUR = 4
HOURLY_INTERVAL = timedelta(hours=1)
DAILY_INTERVAL = timedelta(hours=24)


class IstaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls istaonline.no for meter readings."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: IstaClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=HOURLY_INTERVAL,
        )
        self.client = client
        self.entry = entry
        self._historical_imported = False
        self._last_data_date: str | None = None
        self._has_today_data = False

    def _compute_next_interval(self) -> timedelta:
        """Compute the next poll interval based on data freshness.

        Schedule:
        - At 4am, always poll
        - After 4am, poll every hour until today's data arrives
        - Once today's data is received, wait until next 4am
        - If no data for 24h, only check at 4am
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # Check if we already have today's data
        if self._last_data_date == today_str:
            # Got today's data — sleep until next 4am
            next_4am = datetime.combine(
                now.date() + timedelta(days=1),
                time(hour=DAILY_CHECK_HOUR),
            )
            wait = next_4am - now
            _LOGGER.debug(
                "Have today's data, next check at 4am (%s)", next_4am.isoformat()
            )
            return max(wait, timedelta(minutes=5))

        # No data for today yet
        if now.hour >= DAILY_CHECK_HOUR:
            # It's after 4am — poll hourly until we get today's data
            _LOGGER.debug("No data for today yet, checking hourly")
            return HOURLY_INTERVAL

        # Before 4am — wait until 4am
        next_4am = datetime.combine(now.date(), time(hour=DAILY_CHECK_HOUR))
        wait = next_4am - now
        return max(wait, timedelta(minutes=5))

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest meter data."""
        try:
            if not self.client._authenticated:
                await self.client.authenticate()
            data = await self.client.fetch_all_meters()
        except (IstaAuthError, IstaTwoFactorError) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except IstaConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except IstaResponseError as err:
            # Session expired or unexpected page — try re-auth once
            _LOGGER.info("Got response error, re-authenticating: %s", err)
            try:
                self.client._authenticated = False
                await self.client.authenticate()
                data = await self.client.fetch_all_meters()
            except (IstaAuthError, IstaTwoFactorError) as auth_err:
                raise ConfigEntryAuthFailed(str(auth_err)) from auth_err
            except Exception as retry_err:
                raise UpdateFailed(
                    f"Failed to fetch meter data after re-auth: {retry_err}"
                ) from retry_err
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching meter data")
            raise UpdateFailed(
                f"Unexpected error: {err}"
            ) from err

        # Organize data by meter_id
        meters: dict[str, dict[str, Any]] = {}
        latest_date: str | None = None

        for mtype in METER_TYPES:
            rows = data.get(mtype, [])
            for row in rows:
                meter_id = row["meter"]
                if meter_id not in meters:
                    meters[meter_id] = {
                        "meter_id": meter_id,
                        "meter_type": mtype,
                        "readings": [],
                    }
                meters[meter_id]["readings"].append(row)

        # Sort readings and pick latest for each meter
        for meter_info in meters.values():
            meter_info["readings"].sort(key=lambda r: r["date"])
            latest = meter_info["readings"][-1]
            meter_info["latest_reading"] = latest["reading"]
            meter_info["latest_consumption"] = latest["corrected_consumption"]
            meter_info["latest_date"] = latest["date"]

            # Track the most recent data date across all meters
            if latest_date is None or latest["date"] > latest_date:
                latest_date = latest["date"]

        # Update polling schedule
        if latest_date:
            self._last_data_date = latest_date
        self.update_interval = self._compute_next_interval()

        result = {"meters": meters, "raw": data}

        # Trigger historical import on first successful fetch
        if not self._historical_imported:
            self._historical_imported = True
            self.hass.async_create_task(self._import_historical_data())

        return result

    async def _import_historical_data(self) -> None:
        """Import all available historical data into HA long-term statistics."""
        try:
            _LOGGER.info("Starting historical data import from istaonline.no")

            # Use the data we already have from the first fetch if possible,
            # but also try to get the full historical range
            year_options = await self.client.get_available_year_ranges()

            if year_options:
                from_year = year_options[0]
                to_year = year_options[-1]
                _LOGGER.info(
                    "Importing historical data from %s to %s", from_year, to_year
                )
                data = await self.client.fetch_all_meters(from_year, to_year)
            else:
                _LOGGER.warning(
                    "No year ranges found — using current data for historical import"
                )
                # Fall back to fetching with default (current year)
                data = await self.client.fetch_all_meters()

            meter_readings: dict[str, list[dict[str, Any]]] = {}
            meter_types: dict[str, str] = {}

            for mtype in METER_TYPES:
                for row in data.get(mtype, []):
                    meter_id = row["meter"]
                    meter_readings.setdefault(meter_id, []).append(row)
                    meter_types[meter_id] = mtype

            total_imported = 0
            for meter_id, readings in meter_readings.items():
                mtype = meter_types[meter_id]
                # Use integration domain as source for external statistics
                statistic_id = f"{DOMAIN}:{meter_id}"
                unit = UNIT[mtype]

                if unit == "kWh":
                    ha_unit = UnitOfEnergy.KILO_WATT_HOUR
                else:
                    ha_unit = UnitOfVolume.CUBIC_METERS

                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=f"Ista {LABEL[mtype]} {meter_id}",
                    source=DOMAIN,
                    statistic_id=statistic_id,
                    unit_of_measurement=ha_unit,
                )

                readings.sort(key=lambda r: r["date"])
                statistics: list[StatisticData] = []

                for reading in readings:
                    try:
                        dt = datetime.strptime(reading["date"], "%Y-%m-%d")
                        dt = dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue

                    statistics.append(
                        StatisticData(
                            start=dt,
                            state=reading["reading"],
                            sum=reading["reading"],
                        )
                    )

                if statistics:
                    async_add_external_statistics(self.hass, metadata, statistics)
                    total_imported += len(statistics)
                    _LOGGER.info(
                        "Imported %d statistics for meter %s (%s)",
                        len(statistics),
                        meter_id,
                        mtype,
                    )

            if total_imported > 0:
                _LOGGER.info(
                    "Historical data import complete: %d total data points",
                    total_imported,
                )
            else:
                _LOGGER.warning("Historical data import found no data to import")

        except Exception:
            _LOGGER.exception("Failed to import historical data")
