import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, DEFAULT_PLACE, DEFAULT_NAME

class VRRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VRR integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Hier kannst du auch Validierungen einbauen, falls nötig
            return self.async_create_entry(
                title=f"VRR Abfahrten {user_input.get('place_dm')} - {user_input.get('name_dm')}",
                data=user_input,
            )

        schema = vol.Schema({
            vol.Required("place_dm", default=DEFAULT_PLACE): str,
            vol.Required("name_dm", default=DEFAULT_NAME): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
