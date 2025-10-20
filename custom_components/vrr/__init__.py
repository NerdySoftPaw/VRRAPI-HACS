from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DOMAIN

SERVICE_REFRESH = "refresh_departures"

SERVICE_REFRESH_SCHEMA = vol.Schema({
    vol.Optional("entity_id"): str,
})

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Public Transport DE component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Public Transport DE from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])

    # Register service for manual refresh
    async def handle_refresh(call: ServiceCall) -> None:
        """Handle the refresh service call."""
        entity_id = call.data.get("entity_id")

        if entity_id:
            # Refresh specific entity
            entity_registry = er.async_get(hass)
            entity_entry = entity_registry.async_get(entity_id)

            if entity_entry and entity_entry.platform == DOMAIN:
                # Get the entity and trigger refresh
                entity_obj = hass.data.get("entity_components", {}).get("sensor")
                if entity_obj:
                    for ent in entity_obj.entities:
                        if ent.entity_id == entity_id:
                            await ent.coordinator.async_request_refresh()
                            break
        else:
            # Refresh all VRR entities
            entity_registry = er.async_get(hass)
            entities = [
                e for e in entity_registry.entities.values()
                if e.platform == DOMAIN
            ]

            entity_obj = hass.data.get("entity_components", {}).get("sensor")
            if entity_obj:
                for entity_entry in entities:
                    for ent in entity_obj.entities:
                        if ent.entity_id == entity_entry.entity_id:
                            await ent.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        handle_refresh,
        schema=SERVICE_REFRESH_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Public Transport DE config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"])

    # Remove coordinator from hass.data
    coordinator_key = f"{entry.entry_id}_coordinator"
    if coordinator_key in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(coordinator_key)

    # Unregister service if no more entries
    if not hass.config_entries.async_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH)

    return unload_ok