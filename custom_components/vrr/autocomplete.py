"""Station autocomplete functionality for VRR/KVV integration."""
import logging
import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import quote

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_STOPFINDER_URL_VRR,
    API_STOPFINDER_URL_KVV,
    PROVIDER_VRR,
    PROVIDER_KVV,
    MIN_SEARCH_LENGTH,
    MAX_SUGGESTIONS,
    AUTOCOMPLETE_TIMEOUT
)

_LOGGER = logging.getLogger(__name__)

class StationAutocomplete:
    """Handle station autocomplete requests for VRR and KVV."""

    def __init__(self, hass):
        """Initialize the autocomplete handler."""
        self._hass = hass
        self._session = async_get_clientsession(hass)

    async def search_stations(
            self,
            provider: str,
            search_term: str
    ) -> List[Dict[str, Any]]:
        """Search for stations matching the search term."""

        if len(search_term.strip()) < MIN_SEARCH_LENGTH:
            return []

        try:
            if provider == PROVIDER_VRR:
                return await self._search_vrr_stations(search_term)
            elif provider == PROVIDER_KVV:
                return await self._search_kvv_stations(search_term)
            else:
                _LOGGER.error("Unknown provider: %s", provider)
                return []

        except Exception as e:
            _LOGGER.error("Error searching stations for %s: %s", provider, e)
            return []

    async def _search_vrr_stations(self, search_term: str) -> List[Dict[str, Any]]:
        """Search VRR stations."""
        url = API_STOPFINDER_URL_VRR

        params = {
            "outputFormat": "rapidJSON",
            "type_sf": "any",
            "name_sf": search_term,
            "stateless": "1",
            "locationServerActive": "1",
            "useHouseNumberList": "0"
        }

        return await self._make_request(url, params, self._parse_vrr_response)

    async def _search_kvv_stations(self, search_term: str) -> List[Dict[str, Any]]:
        """Search KVV stations."""
        url = API_STOPFINDER_URL_KVV

        params = {
            "outputFormat": "rapidJSON",
            "type_sf": "any",
            "name_sf": search_term,
            "stateless": "1",
            "locationServerActive": "1"
        }

        return await self._make_request(url, params, self._parse_kvv_response)

    async def _make_request(
            self,
            url: str,
            params: Dict[str, str],
            parser_func
    ) -> List[Dict[str, Any]]:
        """Make the API request and parse response."""

        # Build query string manually to ensure proper encoding
        query_parts = []
        for key, value in params.items():
            query_parts.append(f"{key}={quote(str(value))}")
        query_string = "&".join(query_parts)

        full_url = f"{url}?{query_string}"

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant VRR/KVV Integration)",
            "Accept": "application/json",
        }

        try:
            async with self._session.get(
                    full_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=AUTOCOMPLETE_TIMEOUT)
            ) as response:

                if response.status == 200:
                    data = await response.json()
                    return parser_func(data)
                else:
                    _LOGGER.warning("API returned status %s", response.status)
                    return []

        except asyncio.TimeoutError:
            _LOGGER.warning("Request timeout for station search")
            return []
        except Exception as e:
            _LOGGER.error("Request failed: %s", e)
            return []

    def _parse_vrr_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse VRR API response for station suggestions."""
        suggestions = []

        locations = data.get("locations", [])
        for location in locations[:MAX_SUGGESTIONS]:
            if location.get("type") == "stop":
                station = self._extract_station_info_vrr(location)
                if station:
                    suggestions.append(station)

        return suggestions

    def _parse_kvv_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse KVV API response for station suggestions."""
        suggestions = []

        locations = data.get("locations", [])
        for location in locations[:MAX_SUGGESTIONS]:
            if location.get("type") == "stop":
                station = self._extract_station_info_kvv(location)
                if station:
                    suggestions.append(station)

        return suggestions

    def _extract_station_info_vrr(self, location: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract station information from VRR location data."""
        try:
            # VRR format: usually has place and name separated
            name = location.get("name", "")
            place = location.get("place", "")
            station_id = location.get("id", "")

            # Sometimes the name includes the place, let's handle both cases
            if place and place.lower() not in name.lower():
                display_name = f"{place} - {name}"
            else:
                display_name = name

            return {
                "id": station_id,
                "name": name,
                "place": place,
                "display_name": display_name,
                "coordinates": {
                    "lat": location.get("coord", [None, None])[1],
                    "lon": location.get("coord", [None, None])[0]
                }
            }
        except Exception as e:
            _LOGGER.debug("Error extracting VRR station info: %s", e)
            return None

    def _extract_station_info_kvv(self, location: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract station information from KVV location data."""
        try:
            # KVV format might be slightly different
            name = location.get("name", "")
            place = location.get("place", "")
            station_id = location.get("id", "")

            # Handle KVV naming format
            if place and place.lower() not in name.lower():
                display_name = f"{place} - {name}"
            else:
                display_name = name

            return {
                "id": station_id,
                "name": name,
                "place": place,
                "display_name": display_name,
                "coordinates": {
                    "lat": location.get("coord", [None, None])[1],
                    "lon": location.get("coord", [None, None])[0]
                }
            }
        except Exception as e:
            _LOGGER.debug("Error extracting KVV station info: %s", e)
            return None