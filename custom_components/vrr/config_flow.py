import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, 
    DEFAULT_PLACE, 
    DEFAULT_NAME, 
    DEFAULT_DEPARTURES,
    DEFAULT_SCAN_INTERVAL,
    CONF_STATION_ID,
    CONF_DEPARTURES,
    CONF_TRANSPORTATION_TYPES,
    CONF_SCAN_INTERVAL,
    TRANSPORTATION_TYPES
)

class VRRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VRR integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Validate station ID or place/name
            station_id = user_input.get(CONF_STATION_ID, "").strip()
            place_dm = user_input.get("place_dm", "").strip()
            name_dm = user_input.get("name_dm", "").strip()
            
            if not station_id and (not place_dm or not name_dm):
                errors["base"] = "missing_location"
            else:
                # Create unique ID
                if station_id:
                    unique_id = f"vrr_{station_id}"
                    title = f"VRR Station {station_id}"
                else:
                    unique_id = f"vrr_{place_dm}_{name_dm}".lower().replace(" ", "_")
                    title = f"VRR {place_dm} - {name_dm}"
                
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                )

        # Default transportation types selection
        default_transport_types = list(TRANSPORTATION_TYPES.keys())

        schema = vol.Schema({
            vol.Optional(CONF_STATION_ID, default=""): str,
            vol.Optional("place_dm", default=DEFAULT_PLACE): str,
            vol.Optional("name_dm", default=DEFAULT_NAME): str,
            vol.Optional(CONF_DEPARTURES, default=DEFAULT_DEPARTURES): vol.All(int, vol.Range(min=1, max=20)),
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=30, max=600)),
            vol.Optional(CONF_TRANSPORTATION_TYPES, default=default_transport_types): cv.multi_select(TRANSPORTATION_TYPES),
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=schema, 
            errors=errors,
            description_placeholders={
                "station_id_help": "Optional: Use VRR Station ID instead of place/name",
                "place_help": "City or area name (e.g., Düsseldorf)",
                "name_help": "Station or stop name (e.g., Hauptbahnhof)"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return VRROptionsFlowHandler(config_entry)


class VRROptionsFlowHandler(config_entries.OptionsFlow):
    """Handle VRR options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_departures = self.config_entry.data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES)
        current_scan_interval = self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        current_transport_types = self.config_entry.data.get(CONF_TRANSPORTATION_TYPES, list(TRANSPORTATION_TYPES.keys()))

        schema = vol.Schema({
            vol.Optional(CONF_DEPARTURES, default=current_departures): vol.All(int, vol.Range(min=1, max=20)),
            vol.Optional(CONF_SCAN_INTERVAL, default=current_scan_interval): vol.All(int, vol.Range(min=30, max=600)),
            vol.Optional(CONF_TRANSPORTATION_TYPES, default=current_transport_types): cv.multi_select(TRANSPORTATION_TYPES),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema
        )