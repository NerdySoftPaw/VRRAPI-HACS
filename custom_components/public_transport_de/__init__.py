from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VRR Departures from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload VRR Departures config entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")
