"""Config flow for VRR integration with autocomplete support."""
import logging
import voluptuous as vol
import aiohttp
import asyncio
from typing import Any, Dict, List, Optional

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_DEPARTURES,
    DEFAULT_SCAN_INTERVAL,
    CONF_PROVIDER,
    CONF_STATION_ID,
    CONF_DEPARTURES,
    CONF_TRANSPORTATION_TYPES,
    CONF_SCAN_INTERVAL,
    TRANSPORTATION_TYPES,
    PROVIDERS,
    PROVIDER_VRR,
    PROVIDER_KVV,
    PROVIDER_HVV,
)

_LOGGER = logging.getLogger(__name__)


class VRRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VRR integration with autocomplete."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._provider: Optional[str] = None
        self._selected_location: Optional[Dict[str, Any]] = None
        self._selected_stop: Optional[Dict[str, Any]] = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step - select provider."""
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            return await self.async_step_location()

        schema = vol.Schema({
            vol.Required(CONF_PROVIDER, default=PROVIDER_VRR): vol.In(PROVIDERS),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "info": "Wähle deinen ÖPNV-Anbieter aus"
            }
        )

    async def async_step_location(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle location search step."""
        errors = {}

        if user_input is not None:
            search_term = user_input.get("location_search", "").strip()

            if not search_term:
                errors["location_search"] = "empty_search"
            else:
                # Search for locations
                locations = await self._search_locations(search_term)

                if not locations:
                    errors["location_search"] = "no_results"
                elif len(locations) == 1:
                    # Only one result, select it automatically
                    self._selected_location = locations[0]
                    return await self.async_step_stop()
                else:
                    # Multiple results, let user choose
                    return await self.async_step_location_select(locations)

        schema = vol.Schema({
            vol.Required("location_search"): str,
        })

        return self.async_show_form(
            step_id="location",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "provider": self._provider.upper(),
                "example": "z.B. Düsseldorf, Köln, Hamburg..."
            }
        )

    async def async_step_location_select(self, locations: List[Dict[str, Any]] = None, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Let user select from multiple location results."""
        if user_input is not None:
            # Find selected location
            selected_id = user_input["location"]
            for loc in self.hass.data.get(f"{DOMAIN}_temp_locations", []):
                if loc["id"] == selected_id:
                    self._selected_location = loc
                    break

            return await self.async_step_stop()

        # Store locations temporarily
        self.hass.data[f"{DOMAIN}_temp_locations"] = locations

        # Create options dict for dropdown
        location_options = {
            loc["id"]: f"{loc['name']} ({loc['type']})"
            for loc in locations
        }

        schema = vol.Schema({
            vol.Required("location"): vol.In(location_options),
        })

        return self.async_show_form(
            step_id="location_select",
            data_schema=schema,
            description_placeholders={
                "count": str(len(locations))
            }
        )

    async def async_step_stop(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle stop/station search step."""
        errors = {}

        if user_input is not None:
            search_term = user_input.get("stop_search", "").strip()

            if not search_term:
                errors["stop_search"] = "empty_search"
            else:
                # Search for stops in the selected location
                stops = await self._search_stops(search_term, self._selected_location)

                if not stops:
                    errors["stop_search"] = "no_results"
                elif len(stops) == 1:
                    # Only one result, select it automatically
                    self._selected_stop = stops[0]
                    return await self.async_step_settings()
                else:
                    # Multiple results, let user choose
                    return await self.async_step_stop_select(stops)

        location_name = self._selected_location.get("name", "Unknown") if self._selected_location else "Unknown"

        schema = vol.Schema({
            vol.Required("stop_search"): str,
        })

        return self.async_show_form(
            step_id="stop",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "location": location_name,
                "example": "z.B. Hauptbahnhof, Marktplatz..."
            }
        )

    async def async_step_stop_select(self, stops: List[Dict[str, Any]] = None, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Let user select from multiple stop results."""
        if user_input is not None:
            # Find selected stop
            selected_id = user_input["stop"]
            for stop in self.hass.data.get(f"{DOMAIN}_temp_stops", []):
                if stop["id"] == selected_id:
                    self._selected_stop = stop
                    break

            return await self.async_step_settings()

        # Store stops temporarily
        self.hass.data[f"{DOMAIN}_temp_stops"] = stops

        # Create options dict for dropdown
        stop_options = {
            stop["id"]: f"{stop['name']}" + (f" ({stop.get('place', '')})" if stop.get('place') else "")
            for stop in stops
        }

        schema = vol.Schema({
            vol.Required("stop"): vol.In(stop_options),
        })

        return self.async_show_form(
            step_id="stop_select",
            data_schema=schema,
            description_placeholders={
                "count": str(len(stops))
            }
        )

    async def async_step_settings(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle settings step - departures, transport types, scan interval."""
        if user_input is not None:
            # Combine all collected data
            data = {
                CONF_PROVIDER: self._provider,
                CONF_STATION_ID: self._selected_stop.get("id"),
                "place_dm": self._selected_stop.get("place", ""),
                "name_dm": self._selected_stop.get("name", ""),
                CONF_DEPARTURES: user_input[CONF_DEPARTURES],
                CONF_TRANSPORTATION_TYPES: user_input[CONF_TRANSPORTATION_TYPES],
                CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
            }

            # Create unique ID
            unique_id = f"{self._provider}_{self._selected_stop['id']}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Create title
            place = self._selected_stop.get("place", "")
            name = self._selected_stop.get("name", "")
            title = f"{self._provider.upper()} {place} - {name}".strip()

            # Cleanup temp data
            self.hass.data.pop(f"{DOMAIN}_temp_locations", None)
            self.hass.data.pop(f"{DOMAIN}_temp_stops", None)

            return self.async_create_entry(title=title, data=data)

        schema = vol.Schema({
            vol.Optional(CONF_DEPARTURES, default=DEFAULT_DEPARTURES): vol.All(
                int, vol.Range(min=1, max=20)
            ),
            vol.Optional(
                CONF_TRANSPORTATION_TYPES,
                default=list(TRANSPORTATION_TYPES.keys())
            ): cv.multi_select(TRANSPORTATION_TYPES),
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                int, vol.Range(min=10, max=3600)
            ),
        })

        stop_name = self._selected_stop.get("name", "Unknown") if self._selected_stop else "Unknown"

        return self.async_show_form(
            step_id="settings",
            data_schema=schema,
            description_placeholders={
                "stop": stop_name
            }
        )

    async def _search_locations(self, search_term: str) -> List[Dict[str, Any]]:
        """Search for locations (cities/areas) using STOPFINDER API."""
        api_url = self._get_stopfinder_url()

        params = (
            f"outputFormat=RapidJSON&"
            f"locationServerActive=1&"
            f"type_sf=any&"
            f"name_sf={search_term}&"
            f"SpEncId=0"
        )

        url = f"{api_url}?{params}"
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_stopfinder_response(data, search_type="location")
        except Exception as e:
            _LOGGER.error("Error searching locations: %s", e)

        return []

    async def _search_stops(self, search_term: str, location: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search for stops/stations using STOPFINDER API."""
        api_url = self._get_stopfinder_url()

        # If we have a location, search within that location
        if location:
            search_query = f"{location.get('name', '')} {search_term}".strip()
        else:
            search_query = search_term

        params = (
            f"outputFormat=RapidJSON&"
            f"locationServerActive=1&"
            f"type_sf=stop&"
            f"name_sf={search_query}&"
            f"SpEncId=0"
        )

        url = f"{api_url}?{params}"
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_stopfinder_response(data, search_type="stop")
        except Exception as e:
            _LOGGER.error("Error searching stops: %s", e)

        return []

    def _get_stopfinder_url(self) -> str:
        """Get the STOPFINDER API URL based on provider."""
        if self._provider == PROVIDER_VRR:
            return "https://openservice-test.vrr.de/static03/XML_STOPFINDER_REQUEST"
        elif self._provider == PROVIDER_KVV:
            return "https://projekte.kvv-efa.de/sl3-alone/XML_STOPFINDER_REQUEST"
        elif self._provider == PROVIDER_HVV:
            return "https://efa-api.hochbahn.de/gti/XML_STOPFINDER_REQUEST"
        else:
            return "https://openservice-test.vrr.de/static03/XML_STOPFINDER_REQUEST"

    def _parse_stopfinder_response(self, data: Dict[str, Any], search_type: str = "stop") -> List[Dict[str, Any]]:
        """Parse STOPFINDER API response."""
        results = []

        try:
            locations = data.get("locations", [])

            for location in locations:
                # Get basic info
                loc_type = location.get("type", "unknown")
                name = location.get("name", "")

                # For VRR/KVV/HVV, the ID might be in different fields
                loc_id = (
                    location.get("id") or
                    location.get("stateless") or
                    location.get("properties", {}).get("stopId") or
                    str(location.get("ref", {}).get("id", ""))
                )

                # Get place/city info
                place = location.get("parent", {}).get("name", "")
                if not place:
                    # Try to extract from disassembledName
                    disassembled = location.get("disassembledName", "")
                    if disassembled:
                        place = disassembled.split(",")[0] if "," in disassembled else ""

                # Filter based on search type
                if search_type == "location":
                    # For location search, prefer localities and places
                    if loc_type in ["locality", "place", "poi"]:
                        results.append({
                            "id": loc_id,
                            "name": name,
                            "type": loc_type,
                            "place": place,
                        })
                elif search_type == "stop":
                    # For stop search, prefer stops and stations
                    if loc_type in ["stop", "station", "platform"]:
                        results.append({
                            "id": loc_id,
                            "name": name,
                            "type": loc_type,
                            "place": place,
                        })

            # Limit results to top 10
            results = results[:10]

        except Exception as e:
            _LOGGER.error("Error parsing stopfinder response: %s", e)

        return results

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

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values from options or fall back to data
        current_departures = self.config_entry.options.get(
            CONF_DEPARTURES,
            self.config_entry.data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES)
        )
        current_scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        current_transport_types = self.config_entry.options.get(
            CONF_TRANSPORTATION_TYPES,
            self.config_entry.data.get(CONF_TRANSPORTATION_TYPES, list(TRANSPORTATION_TYPES.keys()))
        )

        schema = vol.Schema({
            vol.Optional(CONF_DEPARTURES, default=current_departures): vol.All(
                int, vol.Range(min=1, max=20)
            ),
            vol.Optional(CONF_SCAN_INTERVAL, default=current_scan_interval): vol.All(
                int, vol.Range(min=30, max=3600)
            ),
            vol.Optional(CONF_TRANSPORTATION_TYPES, default=current_transport_types): cv.multi_select(
                TRANSPORTATION_TYPES
            ),
        })

        return self.async_show_form(step_id="init", data_schema=schema)
