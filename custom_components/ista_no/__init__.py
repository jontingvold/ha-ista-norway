"""The Ista Norway (unofficial) integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .api import IstaClient
from .const import DOMAIN
from .coordinator import IstaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

SERVICE_IMPORT_HISTORY = "import_historical_data"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ista Norway from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    client = IstaClient(username, password)
    await client.authenticate()

    coordinator = IstaCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register service to manually trigger historical data import
    async def handle_import_history(call: ServiceCall) -> None:
        """Handle the import_historical_data service call."""
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, IstaCoordinator):
                _LOGGER.info("Manual historical data import triggered")
                coord._historical_imported = False
                await coord._import_historical_data()

    if not hass.services.has_service(DOMAIN, SERVICE_IMPORT_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_IMPORT_HISTORY,
            handle_import_history,
            schema=vol.Schema({}),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: IstaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()

        # Remove service if no more entries
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_IMPORT_HISTORY)

    return unload_ok
