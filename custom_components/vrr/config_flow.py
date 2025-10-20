"""Config flow for VRR integration with autocomplete support."""
import logging
import voluptuous as vol
import aiohttp
import asyncio
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher
from datetime import datetime, timedelta

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
        self._selected_stop: Optional[Dict[str, Any]] = None

        # API response cache to avoid duplicate requests
        self._search_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl: int = 300  # Cache TTL in seconds (5 minutes)

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step - select provider."""
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            return await self.async_step_stop_search()

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

    async def async_step_stop_search(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle stop/station search step."""
        errors = {}

        if user_input is not None:
            search_term = user_input.get("stop_search", "").strip()

            if not search_term:
                errors["stop_search"] = "empty_search"
            else:
                # Search for stops directly
                stops = await self._search_stops(search_term)

                # Validate that stops is a list
                if not isinstance(stops, list):
                    _LOGGER.error("Search returned invalid type %s, expected list", type(stops))
                    errors["stop_search"] = "api_error"
                elif not stops:
                    errors["stop_search"] = "no_results"
                elif len(stops) == 1:
                    # Only one result, select it automatically
                    self._selected_stop = stops[0]
                    return await self.async_step_settings()
                else:
                    # Multiple results, let user choose
                    return await self.async_step_stop_select(stops)

        schema = vol.Schema({
            vol.Required("stop_search"): str,
        })

        return self.async_show_form(
            step_id="stop_search",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "provider": self._provider.upper(),
                "example": "z.B. Düsseldorf Hauptbahnhof, Köln Heumarkt..."
            }
        )

    async def async_step_stop_select(self, stops: List[Dict[str, Any]] = None, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Let user select from multiple stop results."""
        if user_input is not None:
            # Find selected stop
            selected_id = user_input["stop"]
            for stop in self.hass.data.get(f"{DOMAIN}_temp_stops", []):
                if isinstance(stop, dict) and stop.get("id") == selected_id:
                    self._selected_stop = stop
                    break

            return await self.async_step_settings()

        # Validate stops is a list
        if not isinstance(stops, list):
            _LOGGER.error("Invalid stops data: expected list, got %s", type(stops))
            return await self.async_step_stop_search(user_input=None)

        # Store stops temporarily
        self.hass.data[f"{DOMAIN}_temp_stops"] = stops

        # Create options dict for dropdown - filter out invalid entries
        stop_options = {}
        for stop in stops:
            if isinstance(stop, dict) and "id" in stop and "name" in stop:
                place_suffix = f" ({stop['place']})" if stop.get('place') else ""
                stop_options[stop["id"]] = f"{stop['name']}{place_suffix}"
            else:
                _LOGGER.warning("Skipping invalid stop entry: %s", stop)

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

    async def _search_stops(self, search_term: str) -> List[Dict[str, Any]]:
        """Search for stops/stations using STOPFINDER API with caching.

        Args:
            search_term: Search term for stops

        Returns:
            List of stop dictionaries
        """
        # Check cache first
        cache_key = self._get_cache_key(self._provider, search_term, "stop")
        cached_results = self._get_from_cache(cache_key)

        if cached_results is not None:
            _LOGGER.debug("Returning %d cached results for: %s", len(cached_results), search_term)
            return cached_results

        # Cache miss - fetch from API
        _LOGGER.debug("Cache miss, fetching from API for: %s", search_term)

        api_url = self._get_stopfinder_url()

        params = (
            f"outputFormat=RapidJSON&"
            f"locationServerActive=1&"
            f"type_sf=stop&"
            f"name_sf={search_term}&"
            f"SpEncId=0"
        )

        url = f"{api_url}?{params}"
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                    except (ValueError, aiohttp.ContentTypeError) as e:
                        _LOGGER.error("Invalid JSON response from API: %s", e)
                        return []

                    # Validate response type
                    if not isinstance(data, dict):
                        _LOGGER.error("API returned non-dict response: %s", type(data))
                        return []

                    _LOGGER.debug("API response type: %s, locations count: %s",
                                type(data), len(data.get("locations", [])))

                    result = self._parse_stopfinder_response(data, search_type="stop", search_term=search_term)

                    # Ensure we always return a list
                    if not isinstance(result, list):
                        _LOGGER.error("_parse_stopfinder_response returned %s instead of list", type(result))
                        return []

                    # Store in cache before returning
                    self._store_in_cache(cache_key, result)

                    return result
                elif response.status == 404:
                    _LOGGER.error("API endpoint not found (404)")
                elif response.status >= 500:
                    _LOGGER.error("API server error (status %s)", response.status)
                else:
                    _LOGGER.error("API returned status %s", response.status)
        except asyncio.TimeoutError:
            _LOGGER.error("API request timeout after 10 seconds")
        except Exception as e:
            _LOGGER.error("Error searching stops: %s", e, exc_info=True)

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

    def _parse_stopfinder_response(self, data: Dict[str, Any], search_type: str = "stop", search_term: str = "") -> List[Dict[str, Any]]:
        """Parse STOPFINDER API response."""
        results = []

        try:
            # Validate that data is a dictionary
            if not isinstance(data, dict):
                _LOGGER.error("Invalid API response: expected dict, got %s", type(data))
                return []

            locations = data.get("locations", [])

            # Validate that locations is a list
            if not isinstance(locations, list):
                _LOGGER.error("Invalid locations in API response: expected list, got %s", type(locations))
                return []

            # Extract potential city/place names from search term for filtering
            search_lower = search_term.lower()
            search_words = search_lower.split()

            for location in locations:
                # Skip non-dict entries
                if not isinstance(location, dict):
                    _LOGGER.debug("Skipping non-dict location entry: %s", location)
                    continue
                # Get basic info with validation
                loc_type = location.get("type", "unknown")
                if not isinstance(loc_type, str):
                    loc_type = "unknown"

                name = location.get("name", "")
                if not isinstance(name, str):
                    _LOGGER.debug("Skipping location with invalid name: %s", location)
                    continue

                # Skip entries with empty names
                if not name.strip():
                    _LOGGER.debug("Skipping location with empty name")
                    continue

                # For VRR/KVV/HVV, the ID might be in different fields
                properties = location.get("properties", {})
                if not isinstance(properties, dict):
                    properties = {}

                ref = location.get("ref", {})
                if not isinstance(ref, dict):
                    ref = {}

                loc_id = (
                    location.get("id") or
                    location.get("stateless") or
                    properties.get("stopId") or
                    str(ref.get("id", ""))
                )

                # Validate that we have an ID
                if not loc_id:
                    _LOGGER.debug("Skipping location without valid ID: %s", name)
                    continue

                # Get place/city info with validation
                parent = location.get("parent", {})
                if not isinstance(parent, dict):
                    parent = {}
                place = parent.get("name", "")

                if not place:
                    # Try to extract from disassembledName
                    disassembled = location.get("disassembledName", "")
                    if isinstance(disassembled, str) and disassembled:
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
                            "relevance": self._calculate_relevance(search_lower, name.lower(), place.lower())
                        })
                elif search_type == "stop":
                    # For stop search, prefer stops and stations
                    if loc_type in ["stop", "station", "platform"]:
                        results.append({
                            "id": loc_id,
                            "name": name,
                            "type": loc_type,
                            "place": place,
                            "relevance": self._calculate_relevance(search_lower, name.lower(), place.lower())
                        })

            # Sort by relevance (higher is better)
            results.sort(key=lambda x: x.get("relevance", 0), reverse=True)

            # Remove relevance score before returning (not needed in UI)
            for result in results:
                result.pop("relevance", None)

            # Limit results to top 10
            results = results[:10]

        except Exception as e:
            _LOGGER.error("Error parsing stopfinder response: %s", e, exc_info=True)

        return results

    def _get_cache_key(self, provider: str, search_term: str, search_type: str = "stop") -> str:
        """Generate cache key for search request.

        Args:
            provider: Provider name (vrr, kvv, hvv)
            search_term: Search term
            search_type: Type of search (stop, location)

        Returns:
            Cache key string
        """
        # Normalize search term for consistent caching
        normalized_term = self._normalize_umlauts(search_term.lower().strip())
        return f"{provider}:{search_type}:{normalized_term}"

    def _get_from_cache(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached search results if still valid.

        Args:
            cache_key: Cache key

        Returns:
            Cached results or None if expired/not found
        """
        if cache_key not in self._search_cache:
            return None

        cache_entry = self._search_cache[cache_key]
        cached_time = cache_entry.get("timestamp")
        cached_results = cache_entry.get("results")

        # Check if cache is still valid
        if cached_time and cached_results is not None:
            age = (datetime.now() - cached_time).total_seconds()
            if age < self._cache_ttl:
                _LOGGER.debug("Cache hit for key: %s (age: %.1fs)", cache_key, age)
                return cached_results
            else:
                _LOGGER.debug("Cache expired for key: %s (age: %.1fs)", cache_key, age)
                # Remove expired entry
                del self._search_cache[cache_key]

        return None

    def _store_in_cache(self, cache_key: str, results: List[Dict[str, Any]]) -> None:
        """Store search results in cache.

        Args:
            cache_key: Cache key
            results: Search results to cache
        """
        self._search_cache[cache_key] = {
            "timestamp": datetime.now(),
            "results": results,
        }
        _LOGGER.debug("Stored %d results in cache for key: %s", len(results), cache_key)

        # Limit cache size (keep only last 20 searches)
        if len(self._search_cache) > 20:
            # Remove oldest entry
            oldest_key = min(
                self._search_cache.keys(),
                key=lambda k: self._search_cache[k]["timestamp"]
            )
            del self._search_cache[oldest_key]
            _LOGGER.debug("Cache size limit reached, removed oldest entry: %s", oldest_key)

    def _normalize_umlauts(self, text: str) -> str:
        """Normalize German umlauts for better matching.

        Converts: ä→ae, ö→oe, ü→ue, ß→ss
        """
        replacements = {
            'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
            'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue'
        }
        for umlaut, replacement in replacements.items():
            text = text.replace(umlaut, replacement)
        return text

    def _fuzzy_match_ratio(self, str1: str, str2: str) -> float:
        """Calculate fuzzy match ratio between two strings.

        Uses SequenceMatcher to calculate similarity ratio (0.0 to 1.0).
        Higher values indicate better matches.

        Args:
            str1: First string to compare
            str2: Second string to compare

        Returns:
            Similarity ratio between 0.0 (no match) and 1.0 (perfect match)
        """
        # Convert to lowercase for case-insensitive matching
        str1_lower = str1.lower()
        str2_lower = str2.lower()

        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, str1_lower, str2_lower).ratio()

    def _levenshtein_distance(self, str1: str, str2: str) -> int:
        """Calculate Levenshtein distance between two strings.

        The Levenshtein distance is the minimum number of single-character edits
        (insertions, deletions, or substitutions) required to change one string
        into the other.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Edit distance as integer (0 = identical strings)
        """
        if len(str1) < len(str2):
            return self._levenshtein_distance(str2, str1)

        if len(str2) == 0:
            return len(str1)

        # Create array with distances
        previous_row = range(len(str2) + 1)
        for i, c1 in enumerate(str1):
            current_row = [i + 1]
            for j, c2 in enumerate(str2):
                # Cost of insertions, deletions, or substitutions
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _calculate_relevance(self, search_term: str, name: str, place: str) -> int:
        """Calculate relevance score for a search result.

        Higher score = more relevant result. Includes fuzzy matching for typo tolerance.

        Args:
            search_term: User's search input
            name: Name of the location/stop
            place: City/place name

        Returns:
            Relevance score (higher = more relevant)
        """
        score = 0
        search_words = search_term.split()

        # Normalize umlauts for better matching
        search_term_norm = self._normalize_umlauts(search_term)
        name_norm = self._normalize_umlauts(name)
        place_norm = self._normalize_umlauts(place)
        search_words_norm = search_term_norm.split()

        # === Exact matching bonuses ===

        # Bonus if place name is in search term (with umlaut normalization)
        if place:
            # Check both original and normalized versions
            if any(word in place for word in search_words) or any(word in place_norm for word in search_words_norm):
                score += 100
            # Check if place is a word in search
            if place in search_words or place_norm in search_words_norm:
                score += 200

        # Bonus for exact name match (both versions)
        if name == search_term or name_norm == search_term_norm:
            score += 300

        # Bonus for name starting with search term (both versions)
        if name.startswith(search_term) or name_norm.startswith(search_term_norm):
            score += 150

        # Bonus for each matching word in name
        name_words = name.split()
        name_words_norm = name_norm.split()
        for i, search_word in enumerate(search_words):
            if len(search_word) > 2:  # Only consider words longer than 2 chars
                search_word_norm = search_words_norm[i] if i < len(search_words_norm) else search_word
                for j, name_word in enumerate(name_words):
                    name_word_norm = name_words_norm[j] if j < len(name_words_norm) else name_word
                    # Check both original and normalized
                    if search_word in name_word or search_word_norm in name_word_norm:
                        score += 50

        # === Fuzzy matching bonuses ===

        # Fuzzy match on full strings (for typos)
        fuzzy_ratio = self._fuzzy_match_ratio(search_term_norm, name_norm)
        if fuzzy_ratio > 0.8:  # High similarity (e.g., "Dusseldorf" vs "Düsseldorf")
            score += int(fuzzy_ratio * 200)  # Up to +200 points
        elif fuzzy_ratio > 0.6:  # Medium similarity (e.g., minor typos)
            score += int(fuzzy_ratio * 100)  # Up to +100 points

        # Fuzzy match on individual words (better for multi-word searches)
        for search_word in search_words:
            if len(search_word) > 3:  # Only for meaningful words
                search_word_norm = self._normalize_umlauts(search_word.lower())
                best_word_match = 0.0

                # Find best matching word in name
                for name_word in name_words:
                    name_word_norm = self._normalize_umlauts(name_word.lower())
                    word_ratio = self._fuzzy_match_ratio(search_word_norm, name_word_norm)

                    if word_ratio > best_word_match:
                        best_word_match = word_ratio

                # Bonus for good word matches (typo tolerance)
                if best_word_match > 0.8:
                    score += int(best_word_match * 75)  # Up to +75 per word
                elif best_word_match > 0.7:
                    score += int(best_word_match * 40)  # Up to +40 per word

        # Levenshtein distance bonus for very similar strings (catches small typos)
        if len(search_term_norm) > 3 and len(name_norm) > 3:
            distance = self._levenshtein_distance(search_term_norm, name_norm)
            max_len = max(len(search_term_norm), len(name_norm))

            # If distance is small relative to string length, give bonus
            if distance <= 2 and max_len > 5:  # 1-2 character difference
                score += 120
            elif distance <= 3 and max_len > 8:  # 2-3 character difference
                score += 80

        # === Penalties ===

        # Penalty for very long place names (likely less specific)
        if place and len(place) > 20:
            score -= 10

        return score

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
