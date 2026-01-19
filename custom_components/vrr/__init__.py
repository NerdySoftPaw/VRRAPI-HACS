import asyncio
import logging
from datetime import timedelta
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, ServiceCall
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
    PROVIDER_GTFS_DE,
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

# Key for storing the periodic update task
GTFS_UPDATE_TASK_KEY = "gtfs_update_task"
# Key for storing the stop event listener unsub
STOP_LISTENER_KEY = "stop_listener_unsub"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Public Transport DE component."""
    hass.data.setdefault(DOMAIN, {})

    async def periodic_gtfs_update():
        """Periodically check and update GTFS Static data via GTFSManager."""
        from .gtfs_manager import GTFSManager

        while True:
            try:
                await asyncio.sleep(GTFS_UPDATE_CHECK_INTERVAL.total_seconds())

                # Get the GTFSManager instance
                manager = GTFSManager.get_instance_sync(hass)
                if not manager or manager.is_shutting_down():
                    _LOGGER.debug("GTFSManager not available or shutting down, skipping periodic update")
                    continue

                # Check each active provider and update if needed
                # Copy the list to avoid modification during iteration
                for provider in list(manager.active_providers):
                    gtfs_data = None
                    try:
                        gtfs_data = await manager.get_gtfs_data(provider)
                        if gtfs_data and await gtfs_data._should_update():
                            _LOGGER.info("Auto-updating GTFS Static data for provider: %s", provider)
                            if await gtfs_data.force_update():
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
                    finally:
                        # Always release the reference, even on error
                        if gtfs_data is not None:
                            try:
                                await manager.release_gtfs_data(provider)
                            except Exception:
                                pass
            except asyncio.CancelledError:
                _LOGGER.debug("Periodic GTFS update task cancelled")
                break
            except Exception as e:
                _LOGGER.error("Error in periodic GTFS update task: %s", e, exc_info=True)
                await asyncio.sleep(3600)  # Wait 1 hour before retrying on error

    async def _async_cleanup_integration(_event: Optional[Event] = None) -> None:
        """Cleanup integration resources on Home Assistant stop."""
        _LOGGER.info("Cleaning up VRR integration resources...")

        # Cancel periodic update task
        task = hass.data.get(DOMAIN, {}).get(GTFS_UPDATE_TASK_KEY)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            _LOGGER.debug("Cancelled periodic GTFS update task")

        # Shutdown GTFSManager
        from .gtfs_manager import shutdown_gtfs_manager

        await shutdown_gtfs_manager(hass)
        _LOGGER.info("VRR integration cleanup complete")

    # Start the periodic update task and store the reference
    update_task = hass.async_create_task(periodic_gtfs_update())
    hass.data[DOMAIN][GTFS_UPDATE_TASK_KEY] = update_task

    # Register cleanup on Home Assistant stop
    unsub = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_cleanup_integration)
    hass.data[DOMAIN][STOP_LISTENER_KEY] = unsub

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
        # Cleanup coordinator resources before removing from hass.data
        try:
            await coordinator.async_shutdown()
        except Exception as shutdown_err:
            _LOGGER.warning("Error during coordinator shutdown after failed setup: %s", shutdown_err)
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
            from .gtfs_manager import GTFSManager

            provider = call.data.get("provider")
            manager = GTFSManager.get_instance_sync(hass)

            if not manager:
                _LOGGER.warning("GTFSManager not initialized, cannot update GTFS data")
                return

            if provider:
                # Update specific provider
                if provider in manager.active_providers:
                    _LOGGER.info("Manually updating GTFS Static data for provider: %s", provider)
                    gtfs_data = None
                    try:
                        gtfs_data = await manager.get_gtfs_data(provider)
                        if gtfs_data:
                            if await gtfs_data.force_update():
                                _LOGGER.info("Successfully updated GTFS Static data for provider: %s", provider)
                            else:
                                _LOGGER.error("Failed to update GTFS Static data for provider: %s", provider)
                    finally:
                        # Always release reference
                        if gtfs_data is not None:
                            try:
                                await manager.release_gtfs_data(provider)
                            except Exception:
                                pass
                else:
                    _LOGGER.warning("Provider %s not found in active GTFS providers", provider)
            else:
                # Update all providers
                _LOGGER.info("Manually updating GTFS Static data for all providers")
                for prov in list(manager.active_providers):
                    gtfs_data = None
                    try:
                        _LOGGER.info("Updating GTFS Static data for provider: %s", prov)
                        gtfs_data = await manager.get_gtfs_data(prov)
                        if gtfs_data:
                            if await gtfs_data.force_update():
                                _LOGGER.info("Successfully updated GTFS Static data for provider: %s", prov)
                            else:
                                _LOGGER.error("Failed to update GTFS Static data for provider: %s", prov)
                    except Exception as e:
                        _LOGGER.error("Error updating GTFS Static data for provider %s: %s", prov, e, exc_info=True)
                    finally:
                        # Always release reference
                        if gtfs_data is not None:
                            try:
                                await manager.release_gtfs_data(prov)
                            except Exception:
                                pass

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

    # Remove coordinator from hass.data and call shutdown
    coordinator_key = f"{entry.entry_id}_coordinator"
    if coordinator_key in hass.data.get(DOMAIN, {}):
        coordinator = hass.data[DOMAIN].pop(coordinator_key)
        # Call coordinator shutdown to release GTFS resources
        if coordinator and hasattr(coordinator, "async_shutdown"):
            try:
                await coordinator.async_shutdown()
                _LOGGER.debug("Coordinator shutdown completed for entry: %s", entry.entry_id)
            except Exception as e:
                _LOGGER.warning("Error during coordinator shutdown: %s", e)

    # Unregister services and cleanup if no more entries
    if not hass.config_entries.async_entries(DOMAIN):
        # Remove services
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
        hass.services.async_remove(DOMAIN, SERVICE_UPDATE_GTFS)

        # Cancel periodic update task
        task = hass.data.get(DOMAIN, {}).get(GTFS_UPDATE_TASK_KEY)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            _LOGGER.debug("Cancelled periodic GTFS update task on last entry unload")

        # Unsubscribe from stop event
        unsub = hass.data.get(DOMAIN, {}).pop(STOP_LISTENER_KEY, None)
        if unsub:
            unsub()

        # Shutdown GTFSManager
        from .gtfs_manager import shutdown_gtfs_manager

        await shutdown_gtfs_manager(hass)

        # Clean up domain data
        hass.data.pop(DOMAIN, None)
        _LOGGER.info("VRR integration fully unloaded")

    return unload_ok
