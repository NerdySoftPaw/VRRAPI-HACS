"""Binary sensor platform for VRR integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    CONF_PROVIDER,
    CONF_TRANSPORTATION_TYPES,
    TRANSPORTATION_TYPES,
)
from .sensor import VRRDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VRR binary sensor from a config entry."""
    # Get coordinator from sensor setup
    # We need to get it from hass.data
    coordinator_key = f"{config_entry.entry_id}_coordinator"
    coordinator = hass.data[DOMAIN].get(coordinator_key)

    if not coordinator:
        return

    provider = config_entry.data.get(CONF_PROVIDER, "vrr")
    transportation_types = config_entry.options.get(
        CONF_TRANSPORTATION_TYPES, config_entry.data.get(CONF_TRANSPORTATION_TYPES, list(TRANSPORTATION_TYPES.keys()))
    )

    async_add_entities([VRRDelayBinarySensor(coordinator, config_entry, transportation_types)])


class VRRDelayBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for VRR delays."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: VRRDataUpdateCoordinator,
        config_entry: ConfigEntry,
        transportation_types: list[str],
    ):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self.transportation_types = transportation_types
        self._attr_is_on = False
        self._attributes = {}

        # Setup entity
        provider = coordinator.provider
        station_id = coordinator.station_id
        place_dm = coordinator.place_dm
        name_dm = coordinator.name_dm

        self._attr_unique_id = f"{provider}_{station_id or f'{place_dm}_{name_dm}'.lower().replace(' ', '_')}_delays"
        self._attr_name = f"{provider.upper()} {place_dm} - {name_dm} Delays"

        # Device info - same device as sensor
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{provider}_{station_id or f'{place_dm}_{name_dm}'.lower().replace(' ', '_')}")},
            suggested_area=place_dm,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return self._attributes

    @property
    def icon(self) -> str:
        """Return the icon."""
        if self._attr_is_on:
            return "mdi:alert-circle"
        return "mdi:check-circle"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._process_delay_data(self.coordinator.data)
        self.async_write_ha_state()

    def _process_delay_data(self, data: dict[str, Any]) -> None:
        """Process delay data from API."""
        stop_events = data.get("stopEvents", [])

        if not stop_events:
            self._attr_is_on = False
            self._attributes = {
                "delayed_departures": 0,
                "on_time_departures": 0,
                "average_delay": 0,
                "max_delay": 0,
                "total_departures": 0,
            }
            return

        delayed_count = 0
        on_time_count = 0
        total_delay = 0
        max_delay = 0
        delays = []

        for stop in stop_events:
            # Get times
            planned_time_str = stop.get("departureTimePlanned")
            estimated_time_str = stop.get("departureTimeEstimated")

            if not planned_time_str:
                continue

            # Parse delay
            if estimated_time_str and estimated_time_str != planned_time_str:
                from homeassistant.util import dt as dt_util

                planned_time = dt_util.parse_datetime(planned_time_str)
                estimated_time = dt_util.parse_datetime(estimated_time_str)

                if planned_time and estimated_time:
                    delay_minutes = int((estimated_time - planned_time).total_seconds() / 60)

                    if delay_minutes > 0:
                        delayed_count += 1
                        total_delay += delay_minutes
                        delays.append(delay_minutes)
                        max_delay = max(max_delay, delay_minutes)
                    else:
                        on_time_count += 1
            else:
                on_time_count += 1

        total_departures = delayed_count + on_time_count
        average_delay = total_delay / delayed_count if delayed_count > 0 else 0

        # Set binary sensor state (on if any delays > 5 minutes)
        self._attr_is_on = max_delay > 5

        self._attributes = {
            "delayed_departures": delayed_count,
            "on_time_departures": on_time_count,
            "average_delay": round(average_delay, 1),
            "max_delay": max_delay,
            "total_departures": total_departures,
            "delays_list": delays[:10] if delays else [],  # First 10 delays
            "delay_threshold": 5,  # Minutes threshold for triggering
        }
