from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

DOMAIN = "vrr"
PLATFORMS = [Platform.SENSOR]

async def async_setup(hass: HomeAssistant, config):
    """Set up the VRR integration from configuration.yaml."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VRR Departures from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload VRR Departures config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
