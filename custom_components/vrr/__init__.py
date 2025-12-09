import asyncio
import logging
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_DEPARTURES,
    CONF_NTA_API_KEY,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    CONF_TRAFIKLAB_API_KEY,
    DEFAULT_DEPARTURES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PROVIDER_NTA_IE,
    PROVIDER_TRAFIKLAB_SE,
)
from .sensor import VRRDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH = "refresh_departures"
SERVICE_UPDATE_GTFS = "update_gtfs_static"

SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): str,
    }
)

SERVICE_UPDATE_GTFS_SCHEMA = vol.Schema(
    {
        vol.Optional("provider"): str,
    }
)

# Interval for automatic GTFS Static updates (check every 12 hours)
GTFS_UPDATE_CHECK_INTERVAL = timedelta(hours=12)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Public Transport DE component."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["gtfs_instances"] = {}  # Store GTFS instances for updates

    # Start periodic GTFS update task
    async def periodic_gtfs_update():
        """Periodically check and update GTFS Static data."""
        while True:
            try:
                await asyncio.sleep(GTFS_UPDATE_CHECK_INTERVAL.total_seconds())

                # Get all GTFS instances
                gtfs_instances = hass.data.get(DOMAIN, {}).get("gtfs_instances", {})

                if not gtfs_instances:
                    continue

                # Check each GTFS instance and update if needed
                for provider, gtfs_instance in gtfs_instances.items():
                    try:
                        # Check if update is needed (this checks the timestamp)
                        if await gtfs_instance._should_update():
                            _LOGGER.info("Auto-updating GTFS Static data for provider: %s", provider)
                            if await gtfs_instance._download_and_load():
                                _LOGGER.info("Successfully auto-updated GTFS Static data for provider: %s", provider)
                            else:
                                _LOGGER.warning("Failed to auto-update GTFS Static data for provider: %s", provider)
                    except Exception as e:
                        _LOGGER.error(
                            "Error during auto-update of GTFS Static data for provider %s: %s",
                            provider,
                            e,
                            exc_info=True,
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in periodic GTFS update task: %s", e, exc_info=True)
                await asyncio.sleep(3600)  # Wait 1 hour before retrying on error

    # Start the periodic update task
    hass.async_create_task(periodic_gtfs_update())

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Public Transport DE from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create coordinator and do initial refresh before forwarding entry setups
    # This allows ConfigEntryNotReady to be raised before async_forward_entry_setups
    provider = entry.data.get(CONF_PROVIDER, "vrr")
    place_dm = entry.data.get("place_dm", "")
    name_dm = entry.data.get("name_dm", "")
    station_id = entry.data.get(CONF_STATION_ID)
    trafiklab_api_key = entry.data.get(CONF_TRAFIKLAB_API_KEY)  # For Trafiklab
    nta_api_key = entry.data.get(CONF_NTA_API_KEY)  # For NTA

    # Use appropriate API key based on provider
    api_key = None
    if provider == PROVIDER_TRAFIKLAB_SE:
        api_key = trafiklab_api_key
    elif provider == PROVIDER_NTA_IE:
        api_key = nta_api_key

    departures = entry.options.get(CONF_DEPARTURES, entry.data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES))
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    coordinator = VRRDataUpdateCoordinator(
        hass,
        provider,
        place_dm,
        name_dm,
        station_id,
        departures,
        scan_interval,
        config_entry=entry,
        api_key=api_key,
    )

    # Store coordinator before first refresh
    coordinator_key = f"{entry.entry_id}_coordinator"
    hass.data[DOMAIN][coordinator_key] = coordinator

    # Do initial refresh - this can raise ConfigEntryNotReady
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        # Remove coordinator from hass.data if setup fails
        hass.data[DOMAIN].pop(coordinator_key, None)
        raise ConfigEntryNotReady(f"Failed to initialize VRR API: {err}") from err

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
            entities = [e for e in entity_registry.entities.values() if e.platform == DOMAIN]

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

    # Register service for manual GTFS Static update (only register once)
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_GTFS):

        async def handle_update_gtfs(call: ServiceCall) -> None:
            """Handle the update GTFS Static service call."""
            provider = call.data.get("provider")
            gtfs_instances = hass.data.get(DOMAIN, {}).get("gtfs_instances", {})

            if provider:
                # Update specific provider
                if provider in gtfs_instances:
                    _LOGGER.info("Manually updating GTFS Static data for provider: %s", provider)
                    if await gtfs_instances[provider].force_update():
                        _LOGGER.info("Successfully updated GTFS Static data for provider: %s", provider)
                    else:
                        _LOGGER.error("Failed to update GTFS Static data for provider: %s", provider)
                else:
                    _LOGGER.warning("Provider %s not found in GTFS instances", provider)
            else:
                # Update all providers
                _LOGGER.info("Manually updating GTFS Static data for all providers")
                for prov, gtfs_instance in gtfs_instances.items():
                    try:
                        _LOGGER.info("Updating GTFS Static data for provider: %s", prov)
                        if await gtfs_instance.force_update():
                            _LOGGER.info("Successfully updated GTFS Static data for provider: %s", prov)
                        else:
                            _LOGGER.error("Failed to update GTFS Static data for provider: %s", prov)
                    except Exception as e:
                        _LOGGER.error("Error updating GTFS Static data for provider %s: %s", prov, e, exc_info=True)

        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_GTFS,
            handle_update_gtfs,
            schema=SERVICE_UPDATE_GTFS_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Public Transport DE config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"])

    # Remove coordinator from hass.data
    coordinator_key = f"{entry.entry_id}_coordinator"
    if coordinator_key in hass.data.get(DOMAIN, {}):
        coordinator = hass.data[DOMAIN].pop(coordinator_key)
        # Remove GTFS instance if this coordinator had one
        if coordinator and hasattr(coordinator, "gtfs_static") and coordinator.gtfs_static:
            provider = coordinator.provider
            gtfs_instances = hass.data.get(DOMAIN, {}).get("gtfs_instances", {})
            if provider in gtfs_instances:
                # Only remove if no other coordinator uses this provider
                # Check if any other coordinator uses this provider
                has_other = False
                for key, other_coordinator in hass.data.get(DOMAIN, {}).items():
                    if key.endswith("_coordinator") and key != coordinator_key:
                        if hasattr(other_coordinator, "provider") and other_coordinator.provider == provider:
                            has_other = True
                            break
                if not has_other:
                    gtfs_instances.pop(provider, None)

    # Unregister services if no more entries
    if not hass.config_entries.async_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
        hass.services.async_remove(DOMAIN, SERVICE_UPDATE_GTFS)

    return unload_ok
