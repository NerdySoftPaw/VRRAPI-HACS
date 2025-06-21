import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from typing import Any, Dict, Optional

from .const import (
    DOMAIN,
    DEFAULT_PLACE,
    DEFAULT_NAME,
    DEFAULT_DEPARTURES,
    DEFAULT_SCAN_INTERVAL,
    CONF_PROVIDER,
    CONF_STATION_ID,
    CONF_DEPARTURES,
    CONF_TRANSPORTATION_TYPES,
    CONF_SCAN_INTERVAL,
    CONF_SEARCH_TERM,
    CONF_SELECTED_STATION,
    TRANSPORTATION_TYPES,
    PROVIDERS,
    MIN_SEARCH_LENGTH
)
from .autocomplete import StationAutocomplete

_LOGGER = logging.getLogger(__name__)

class VRRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VRR integration."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self._provider = "vrr"
        self._autocomplete = None
        self._station_suggestions = []
        self._user_input = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self._user_input.update(user_input)
            self._provider = user_input.get(CONF_PROVIDER, "vrr")

            # Check if user wants to use autocomplete
            search_term = user_input.get(CONF_SEARCH_TERM, "").strip()
            selected_station = user_input.get(CONF_SELECTED_STATION)

            if search_term and len(search_term) >= MIN_SEARCH_LENGTH:
                # User entered search term, show suggestions
                return await self.async_step_station_search(user_input)
            elif selected_station:
                # User selected a station from suggestions
                return await self._create_entry_from_selection(selected_station)
            else:
                # Validate manual input
                station_id = user_input.get(CONF_STATION_ID, "").strip()
                place_dm = user_input.get("place_dm", "").strip()
                name_dm = user_input.get("name_dm", "").strip()

                if not station_id and (not place_dm or not name_dm):
                    errors["base"] = "missing_location"
                else:
                    # Create entry with manual input
                    return await self._create_entry_from_manual_input(user_input)

        # Show initial form
        schema = vol.Schema({
            vol.Required(CONF_PROVIDER, default=self._provider): vol.In(PROVIDERS),
            vol.Optional(CONF_SEARCH_TERM, default=""): str,
            vol.Optional(CONF_STATION_ID, default=""): str,
            vol.Optional("place_dm", default=DEFAULT_PLACE): str,
            vol.Optional("name_dm", default=DEFAULT_NAME): str,
            vol.Optional(CONF_DEPARTURES, default=DEFAULT_DEPARTURES): vol.All(int, vol.Range(min=1, max=20)),
            vol.Optional(CONF_TRANSPORTATION_TYPES, default=list(TRANSPORTATION_TYPES.keys())): cv.multi_select(list(TRANSPORTATION_TYPES.keys())),
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=10, max=3600)),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "search_help": f"Enter at least {MIN_SEARCH_LENGTH} characters to search for stations",
                "station_id_help": "Optional: Use specific Station ID instead of place/name",
                "place_help": "City or area name (e.g., Düsseldorf)",
                "name_help": "Station or stop name (e.g., Hauptbahnhof)"
            }
        )

    async def async_step_station_search(self, user_input=None):
        """Handle station search with autocomplete."""
        errors = {}

        if user_input is not None:
            selected_station = user_input.get(CONF_SELECTED_STATION)
            new_search_term = user_input.get(CONF_SEARCH_TERM, "").strip()

            if selected_station:
                # User selected a station
                return await self._create_entry_from_selection(selected_station)
            elif new_search_term != self._user_input.get(CONF_SEARCH_TERM, ""):
                # User changed search term
                self._user_input[CONF_SEARCH_TERM] = new_search_term
                if len(new_search_term) >= MIN_SEARCH_LENGTH:
                    await self._update_station_suggestions(new_search_term)
                else:
                    self._station_suggestions = []
        else:
            # Initial search
            search_term = self._user_input.get(CONF_SEARCH_TERM, "")
            if len(search_term) >= MIN_SEARCH_LENGTH:
                await self._update_station_suggestions(search_term)

        # Create dynamic schema with station suggestions
        schema_dict = {
            vol.Required(CONF_PROVIDER, default=self._provider): vol.In(PROVIDERS),
            vol.Optional(CONF_SEARCH_TERM, default=self._user_input.get(CONF_SEARCH_TERM, "")): str,
        }

        # Add station selection if we have suggestions
        if self._station_suggestions:
            station_options = {}
            for station in self._station_suggestions:
                key = f"{station['place']}|{station['name']}|{station['id']}"
                station_options[key] = station['display_name']

            schema_dict[vol.Optional(CONF_SELECTED_STATION)] = vol.In(station_options)

        # Add other configuration options
        schema_dict.update({
            vol.Optional(CONF_DEPARTURES, default=self._user_input.get(CONF_DEPARTURES, DEFAULT_DEPARTURES)): vol.All(int, vol.Range(min=1, max=20)),
            vol.Optional(CONF_TRANSPORTATION_TYPES, default=self._user_input.get(CONF_TRANSPORTATION_TYPES, list(TRANSPORTATION_TYPES.keys()))): cv.multi_select(list(TRANSPORTATION_TYPES.keys())),
            vol.Optional(CONF_SCAN_INTERVAL, default=self._user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(int, vol.Range(min=10, max=3600)),
        })

        schema = vol.Schema(schema_dict)

        description_placeholders = {
            "search_results": f"Found {len(self._station_suggestions)} stations" if self._station_suggestions else "Enter search term to find stations"
        }

        return self.async_show_form(
            step_id="station_search",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders
        )

    async def _update_station_suggestions(self, search_term: str):
        """Update station suggestions based on search term."""
        if not self._autocomplete:
            self._autocomplete = StationAutocomplete(self.hass)

        try:
            self._station_suggestions = await self._autocomplete.search_stations(
                self._provider, search_term
            )
            _LOGGER.debug("Found %d station suggestions for '%s'",
                          len(self._station_suggestions), search_term)
        except Exception as e:
            _LOGGER.error("Error getting station suggestions: %s", e)
            self._station_suggestions = []

    async def _create_entry_from_selection(self, selected_station: str) -> FlowResult:
        """Create config entry from selected station."""
        try:
            # Parse the selected station key: "place|name|id"
            parts = selected_station.split("|")
            if len(parts) != 3:
                raise ValueError("Invalid station selection format")

            place, name, station_id = parts

            # Create entry data
            entry_data = {
                CONF_PROVIDER: self._provider,
                "place_dm": place,
                "name_dm": name,
                CONF_STATION_ID: station_id if station_id != "None" else None,
                CONF_DEPARTURES: self._user_input.get(CONF_DEPARTURES, DEFAULT_DEPARTURES),
                CONF_TRANSPORTATION_TYPES: self._user_input.get(CONF_TRANSPORTATION_TYPES, list(TRANSPORTATION_TYPES.keys())),
                CONF_SCAN_INTERVAL: self._user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            }

            # Create unique ID and title
            if station_id and station_id != "None":
                unique_id = f"{self._provider}_{station_id}"
                title = f"{self._provider.upper()} Station {station_id}"
            else:
                unique_id = f"{self._provider}_{place}_{name}".lower().replace(" ", "_")
                title = f"{self._provider.upper()} {place} - {name}"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=title, data=entry_data)

        except Exception as e:
            _LOGGER.error("Error creating entry from selection: %s", e)
            return self.async_show_form(
                step_id="station_search",
                errors={"base": "invalid_selection"}
            )

    async def _create_entry_from_manual_input(self, user_input: Dict[str, Any]) -> FlowResult:
        """Create config entry from manual input."""
        provider = user_input.get(CONF_PROVIDER, "vrr")
        station_id = user_input.get(CONF_STATION_ID, "").strip()
        place_dm = user_input.get("place_dm", "").strip()
        name_dm = user_input.get("name_dm", "").strip()

        # Create unique ID and title
        if station_id:
            unique_id = f"{provider}_{station_id}"
            title = f"{provider.upper()} Station {station_id}"
        else:
            unique_id = f"{provider}_{place_dm}_{name_dm}".lower().replace(" ", "_")
            title = f"{provider.upper()} {place_dm} - {name_dm}"

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=title, data=user_input)

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