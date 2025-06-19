import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, DEFAULT_PLACE, DEFAULT_NAME, DEFAULT_DEPARTURES

class KVVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=f"KVV {user_input['place_dm']} - {user_input['name_dm']}", data=user_input)
        data_schema = vol.Schema({
            vol.Required("place_dm", default=DEFAULT_PLACE): str,
            vol.Required("name_dm", default=DEFAULT_NAME): str,
            vol.Optional("station_id"): str,
            vol.Optional("departures", default=DEFAULT_DEPARTURES): int,
            vol.Optional("transportation_types", default=["tram", "train", "bus"]): vol.All([str])
        })
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)
