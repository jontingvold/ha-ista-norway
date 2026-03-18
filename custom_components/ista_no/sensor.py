"""Sensor platform for ista online (Norway)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LABEL
from .coordinator import IstaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ista sensors from a config entry."""
    coordinator: IstaCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[IstaMeterSensor] = []
    meters = coordinator.data.get("meters", {})
    for meter_id, meter_info in meters.items():
        entities.append(IstaMeterSensor(coordinator, meter_id, meter_info))

    async_add_entities(entities)


class IstaMeterSensor(CoordinatorEntity[IstaCoordinator], SensorEntity):
    """Sensor representing a single ista meter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IstaCoordinator,
        meter_id: str,
        meter_info: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._meter_id = meter_id
        self._meter_type = meter_info["meter_type"]

        self._attr_unique_id = f"ista_no_{meter_id}"
        self._attr_name = f"{LABEL.get(self._meter_type, self._meter_type)} {meter_id}"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        if self._meter_type == "ENERGY":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        else:
            self._attr_device_class = SensorDeviceClass.WATER
            self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS

    @property
    def device_info(self) -> dict[str, Any]:
        """Group all meters under one device per username."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.client.username)},
            "name": f"Ista Norway ({self.coordinator.client.username})",
            "manufacturer": "ista",
            "model": "istaonline.no",
        }

    @property
    def native_value(self) -> float | None:
        """Return the latest cumulative meter reading."""
        meters = self.coordinator.data.get("meters", {})
        meter_info = meters.get(self._meter_id)
        if meter_info:
            return meter_info.get("latest_reading")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        meters = self.coordinator.data.get("meters", {})
        meter_info = meters.get(self._meter_id)
        if not meter_info:
            return {}
        return {
            "daily_consumption": meter_info.get("latest_consumption"),
            "last_reading_date": meter_info.get("latest_date"),
            "meter_type": self._meter_type,
            "meter_id": self._meter_id,
        }
