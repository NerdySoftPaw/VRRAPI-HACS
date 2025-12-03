import asyncio
import logging
import ssl
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union
from zoneinfo import ZoneInfo

import aiohttp
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    API_BASE_URL_HVV,
    API_BASE_URL_KVV,
    API_BASE_URL_VRR,
    API_RATE_LIMIT_PER_DAY,
    CONF_DEPARTURES,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    CONF_TRANSPORTATION_TYPES,
    DEFAULT_DEPARTURES,
    DEFAULT_NAME,
    DEFAULT_PLACE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HVV_TRANSPORTATION_TYPES,
    KVV_TRANSPORTATION_TYPES,
    PROVIDER_HVV,
    PROVIDER_KVV,
    PROVIDER_VRR,
    TRANSPORTATION_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class VRRDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching VRR/KVV/HVV data from API."""

    def __init__(
        self,
        hass: HomeAssistant,
        provider: str,
        place_dm: str,
        name_dm: str,
        station_id: Optional[str],
        departures_limit: int,
        scan_interval: int,
        config_entry: Optional[ConfigEntry] = None,
    ):
        """Initialize."""
        self.provider = provider
        self.place_dm = place_dm
        self.name_dm = name_dm
        self.station_id = station_id
        self.departures_limit = departures_limit
        self._api_calls_today = 0
        self._last_api_reset = datetime.now().date()

        # Note: config_entry parameter was added in HA 2024.11+
        # We store it ourselves for compatibility with older versions
        self._config_entry = config_entry

        super().__init__(
            hass,
            _LOGGER,
            name=f"{provider.upper()} {place_dm} - {name_dm}",
            update_interval=timedelta(seconds=scan_interval),
        )

    def _check_rate_limit(self) -> bool:
        """Check if we're within API rate limits."""
        today = datetime.now().date()
        if today > self._last_api_reset:
            self._api_calls_today = 0
            self._last_api_reset = today
            # Clear rate limit repair issue when new day starts
            ir.async_delete_issue(self.hass, DOMAIN, f"rate_limit_{self.provider}")

        if self._api_calls_today >= API_RATE_LIMIT_PER_DAY:
            _LOGGER.warning("API rate limit approached, skipping update")
            # Create repair issue
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"rate_limit_{self.provider}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="rate_limit_reached",
                translation_placeholders={
                    "provider": self.provider.upper(),
                    "limit": str(API_RATE_LIMIT_PER_DAY),
                },
            )
            return False
        return True

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API."""
        if not self._check_rate_limit():
            # Return last known data instead of failing
            if self.data:
                return self.data
            raise UpdateFailed("API rate limit reached")

        try:
            data = await self._fetch_departures()
            if data and isinstance(data, dict):
                self._api_calls_today += 1
                # Clear API error repair issue on successful fetch
                ir.async_delete_issue(self.hass, DOMAIN, f"api_error_{self.provider}")
                return data
            else:
                # Create repair issue for invalid API response
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"api_error_{self.provider}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="api_error",
                    translation_placeholders={
                        "provider": self.provider.upper(),
                    },
                )
                raise UpdateFailed("Invalid or empty API response")
        except UpdateFailed:
            raise
        except Exception as err:
            # Create repair issue for API errors
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"api_error_{self.provider}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="api_error",
                translation_placeholders={
                    "provider": self.provider.upper(),
                },
            )
            raise UpdateFailed(f"Error fetching data: {err}")

    async def _fetch_departures(self) -> Optional[Dict[str, Any]]:
        """Fetch departure data from the API."""
        if self.provider == PROVIDER_VRR:
            base_url = API_BASE_URL_VRR
        elif self.provider == PROVIDER_KVV:
            base_url = API_BASE_URL_KVV
        elif self.provider == PROVIDER_HVV:
            base_url = API_BASE_URL_HVV
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        if self.station_id:
            params = (
                f"outputFormat=RapidJSON&"
                f"stateless=1&"
                f"type_dm=any&"
                f"name_dm={self.station_id}&"
                f"mode=direct&"
                f"useRealtime=1&"
                f"limit={self.departures_limit}"
            )
        else:
            params = (
                f"outputFormat=RapidJSON&"
                f"place_dm={self.place_dm}&"
                f"type_dm=stop&"
                f"name_dm={self.name_dm}&"
                f"mode=direct&"
                f"useRealtime=1&"
                f"limit={self.departures_limit}"
            )

        url = f"{base_url}?{params}"
        session = async_get_clientsession(self.hass)

        headers = {"User-Agent": f"Mozilla/5.0 (compatible; HomeAssistant {self.provider.upper()} Integration)"}

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        try:
                            json_data = await response.json()
                            # Validate response structure
                            if not isinstance(json_data, dict):
                                _LOGGER.warning(
                                    "%s API returned non-dict response: %s", self.provider.upper(), type(json_data)
                                )
                                return None

                            # Validate that response contains expected data
                            if "stopEvents" not in json_data:
                                _LOGGER.debug("%s API response missing 'stopEvents' field", self.provider.upper())
                                # Return empty structure instead of None to avoid errors
                                return {"stopEvents": []}

                            return json_data
                        except (ValueError, aiohttp.ContentTypeError) as e:
                            _LOGGER.warning("%s API returned invalid JSON: %s", self.provider.upper(), e)
                            return None
                        except Exception as e:
                            _LOGGER.warning("%s API JSON parsing failed: %s", self.provider.upper(), e)
                            return None
                    elif response.status == 404:
                        _LOGGER.warning("%s API endpoint not found (404)", self.provider.upper())
                        return None
                    elif response.status >= 500:
                        _LOGGER.warning("%s API server error (status %s)", self.provider.upper(), response.status)
                    else:
                        _LOGGER.warning("%s API returned status %s", self.provider.upper(), response.status)

            except asyncio.TimeoutError:
                _LOGGER.warning("%s API timeout on attempt %s", self.provider.upper(), attempt)
            except Exception as e:
                _LOGGER.warning("Attempt %s failed: %s", attempt, e)

            if attempt < max_retries:
                await asyncio.sleep(2**attempt)

        return None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VRR/KVV sensor from a config entry."""
    # Reuse coordinator created in __init__.py
    coordinator_key = f"{config_entry.entry_id}_coordinator"
    coordinator = hass.data[DOMAIN].get(coordinator_key)

    if coordinator is None:
        # Fallback: create coordinator if not found (shouldn't happen in normal flow)
        provider = config_entry.data.get(CONF_PROVIDER, PROVIDER_VRR)
        place_dm = config_entry.data.get("place_dm", DEFAULT_PLACE)
        name_dm = config_entry.data.get("name_dm", DEFAULT_NAME)
        station_id = config_entry.data.get(CONF_STATION_ID)

        departures = config_entry.options.get(
            CONF_DEPARTURES, config_entry.data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES)
        )
        scan_interval = config_entry.options.get(
            CONF_SCAN_INTERVAL, config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        coordinator = VRRDataUpdateCoordinator(
            hass,
            provider,
            place_dm,
            name_dm,
            station_id,
            departures,
            scan_interval,
            config_entry=config_entry,
        )
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][coordinator_key] = coordinator
        await coordinator.async_config_entry_first_refresh()

    # Use options if available, otherwise fall back to data
    transportation_types = config_entry.options.get(
        CONF_TRANSPORTATION_TYPES, config_entry.data.get(CONF_TRANSPORTATION_TYPES, list(TRANSPORTATION_TYPES.keys()))
    )

    # Create sensor
    async_add_entities(
        [
            MultiProviderSensor(
                coordinator,
                config_entry,
                transportation_types,
            )
        ]
    )


class MultiProviderSensor(CoordinatorEntity, SensorEntity):
    """Sensor für VRR/KVV/HVV using DataUpdateCoordinator."""

    def __init__(
        self,
        coordinator: VRRDataUpdateCoordinator,
        config_entry: ConfigEntry,
        transportation_types: List[str],
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self.transportation_types = transportation_types or list(TRANSPORTATION_TYPES.keys())
        self._state = None
        self._attributes = {}

        # Setup entity
        provider = coordinator.provider
        station_id = coordinator.station_id
        place_dm = coordinator.place_dm
        name_dm = coordinator.name_dm

        self._attr_unique_id = f"{provider}_{station_id or f'{place_dm}_{name_dm}'.lower().replace(' ', '_')}"
        self._attr_name = f"{provider.upper()} {place_dm} - {name_dm}"

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{provider}_{station_id or f'{place_dm}_{name_dm}'.lower().replace(' ', '_')}")},
            name=f"{place_dm} - {name_dm}",
            manufacturer=f"{provider.upper()} Public Transport",
            model="Departure Monitor",
            sw_version="4.1.0",
            configuration_url=f"https://github.com/NerdySoftPaw/VRRAPI-HACS",
            suggested_area=place_dm,
        )

        # Listen to options updates
        self._config_entry.async_on_unload(self._config_entry.add_update_listener(self._async_update_listener))

    @property
    def state(self):
        """Return the state, which is the departure time of the next departure."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return additional attributes, including all departures."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def icon(self):
        """Return the icon to use in the frontend based on next departure."""
        # Icon mapping for different transportation types
        icon_mapping = {
            "bus": "mdi:bus-clock",
            "tram": "mdi:tram",
            "subway": "mdi:subway-variant",
            "train": "mdi:train",
            "ferry": "mdi:ferry",
            "taxi": "mdi:taxi",
            "on_demand": "mdi:bus-alert",
        }

        # Try to get the transportation type of the next departure
        departures = self._attributes.get("departures", [])
        if departures and len(departures) > 0:
            next_transport_type = departures[0].get("transportation_type", "bus")
            return icon_mapping.get(next_transport_type, "mdi:bus-clock")

        return "mdi:bus-clock"  # Default icon

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._process_departure_data(self.coordinator.data)
        self.async_write_ha_state()

    async def _async_update_listener(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Handle options update."""
        # Update transportation types
        self.transportation_types = config_entry.options.get(
            CONF_TRANSPORTATION_TYPES,
            config_entry.data.get(CONF_TRANSPORTATION_TYPES, list(TRANSPORTATION_TYPES.keys())),
        )

        # Update coordinator settings
        departures = config_entry.options.get(
            CONF_DEPARTURES, config_entry.data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES)
        )
        scan_interval = config_entry.options.get(
            CONF_SCAN_INTERVAL, config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        # Update coordinator
        self.coordinator.departures_limit = departures
        self.coordinator.update_interval = timedelta(seconds=scan_interval)

        # Force refresh
        await self.coordinator.async_request_refresh()

    def _process_departure_data(self, data: Dict[str, Any]) -> None:
        """Process the departure data from VRR/KVV/HVV API.

        Parses raw API response, filters departures by configured transportation types,
        calculates statistics, and updates sensor state and attributes.

        Args:
            data: Raw API response containing stopEvents
        """
        # Validate response structure
        if not isinstance(data, dict):
            _LOGGER.error("Invalid API response: expected dict, got %s", type(data))
            return

        stop_events = data.get("stopEvents", [])

        # Validate stopEvents is a list
        if not isinstance(stop_events, list):
            _LOGGER.error("Invalid stopEvents in API response: expected list, got %s", type(stop_events))
            return

        # Cache frequently accessed values
        station_name = f"{self.coordinator.place_dm} - {self.coordinator.name_dm}"
        station_id = self.coordinator.station_id

        if not stop_events:
            self._state = "No departures"
            self._attributes = {
                "departures": [],
                "next_3_departures": [],
                "station_name": station_name,
                "last_updated": dt_util.utcnow().isoformat(),
                "next_departure_minutes": None,
                "station_id": station_id,
                "total_departures": 0,
                "delayed_count": 0,
                "on_time_count": 0,
                "average_delay": 0,
                "earliest_departure": None,
                "latest_departure": None,
            }
            return

        departures = []
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        now = dt_util.now()

        # Cache provider and transportation_types to avoid repeated lookups
        provider = self.coordinator.provider
        transport_types_set = set(self.transportation_types)  # Set lookup is O(1) vs list O(n)

        # Select parser function once instead of checking in loop
        if provider == PROVIDER_VRR:
            parse_fn = self._parse_departure_vrr
        elif provider == PROVIDER_KVV:
            parse_fn = self._parse_departure_kvv
        elif provider == PROVIDER_HVV:
            parse_fn = self._parse_departure_hvv
        else:
            parse_fn = None

        if parse_fn:
            for stop in stop_events:
                dep = parse_fn(stop, berlin_tz, now)
                # Filter by configured transportation types (set lookup is faster)
                if dep and dep.get("transportation_type") in transport_types_set:
                    departures.append(dep)

        # Sort by departure time
        departures.sort(key=lambda x: x.get("departure_time_obj", now))

        # Limit to requested number
        departures_limit = self.coordinator.departures_limit
        departures = departures[:departures_limit]

        # Set state and attributes
        if departures:
            next_departure = departures[0]
            self._state = next_departure["departure_time"]
            next_minutes = next_departure.get("minutes_until_departure")
        else:
            self._state = "No departures"
            next_minutes = None

        # Calculate statistics and clean departures in one pass
        clean_departures = []
        departure_times = []
        delayed_count = 0
        on_time_count = 0
        total_delay = 0

        for dep in departures:
            # Extract and remove departure_time_obj for stats before cleaning
            dep_time_obj = dep.pop("departure_time_obj", None)
            if dep_time_obj:
                departure_times.append(dep_time_obj)

            # Count delays
            delay = dep.get("delay", 0)
            if delay > 0:
                delayed_count += 1
                total_delay += delay
            else:
                on_time_count += 1

            # Add to clean list (departure_time_obj already removed)
            clean_departures.append(dep)

        # Next 3 departures (simplified)
        next_3_departures = clean_departures[:3]

        # Average delay
        average_delay = round(total_delay / delayed_count, 1) if delayed_count > 0 else 0

        # Earliest and latest departure times
        earliest_departure = None
        latest_departure = None
        if departure_times:
            earliest_departure = min(departure_times).strftime("%H:%M")
            latest_departure = max(departure_times).strftime("%H:%M")

        self._attributes = {
            "departures": clean_departures,
            "next_3_departures": next_3_departures,
            "station_name": station_name,
            "last_updated": dt_util.utcnow().isoformat(),
            "next_departure_minutes": next_minutes,
            "station_id": station_id,
            "total_departures": len(clean_departures),
            "delayed_count": delayed_count,
            "on_time_count": on_time_count,
            "average_delay": average_delay,
            "earliest_departure": earliest_departure,
            "latest_departure": latest_departure,
        }

    def _parse_departure_generic(
        self,
        stop: Dict[str, Any],
        berlin_tz: Union[ZoneInfo, Any],
        now: datetime,
        get_transport_type_fn: Callable[[Dict[str, Any]], str],
        get_platform_fn: Callable[[Dict[str, Any]], str],
        get_realtime_fn: Callable[[Dict[str, Any], Optional[str], Optional[str]], bool],
    ) -> Optional[Dict[str, Any]]:
        """Generic parser for departure data - shared logic across all providers.

        Args:
            stop: Stop event data from API
            berlin_tz: Berlin timezone object
            now: Current datetime
            get_transport_type_fn: Function to determine transportation type
            get_platform_fn: Function to extract platform information
            get_realtime_fn: Function to check if realtime data is available

        Returns:
            Parsed departure dictionary or None if parsing fails
        """
        try:
            # Validate stop data structure
            if not isinstance(stop, dict):
                _LOGGER.debug("Invalid stop data: expected dict, got %s", type(stop))
                return None

            # Get times
            planned_time_str = stop.get("departureTimePlanned")
            estimated_time_str = stop.get("departureTimeEstimated")

            if not planned_time_str:
                _LOGGER.debug("Missing departureTimePlanned in stop data")
                return None

            # Validate time strings
            if not isinstance(planned_time_str, str):
                _LOGGER.debug("Invalid departureTimePlanned: expected str, got %s", type(planned_time_str))
                return None

            # Parse times
            planned_time = dt_util.parse_datetime(planned_time_str)
            estimated_time = dt_util.parse_datetime(estimated_time_str) if estimated_time_str else planned_time

            if not planned_time:
                _LOGGER.debug("Failed to parse departureTimePlanned: %s", planned_time_str)
                return None

            # Convert to local timezone with validation
            try:
                planned_local = planned_time.astimezone(berlin_tz)
                estimated_local = estimated_time.astimezone(berlin_tz) if estimated_time else planned_local
            except (ValueError, TypeError) as e:
                _LOGGER.debug("Failed to convert timezone: %s", e)
                return None

            # Calculate delay
            delay_minutes = int((estimated_local - planned_local).total_seconds() / 60)

            # Get transportation info with validation
            transportation = stop.get("transportation", {})
            if not isinstance(transportation, dict):
                _LOGGER.debug("Invalid transportation data: expected dict, got %s", type(transportation))
                transportation = {}

            destination_obj = transportation.get("destination", {})
            if not isinstance(destination_obj, dict):
                destination_obj = {}
            destination = destination_obj.get("name", "Unknown")

            line_number = str(transportation.get("number", ""))
            description = str(transportation.get("description", ""))

            # Determine transportation type using provider-specific function
            transport_type = get_transport_type_fn(transportation)

            # Get platform/track info using provider-specific function
            platform = get_platform_fn(stop)

            # Calculate minutes until departure
            time_diff = estimated_local - now
            minutes_until = max(0, int(time_diff.total_seconds() / 60))

            # Determine if real-time data is available using provider-specific function
            is_realtime = get_realtime_fn(stop, estimated_time_str, planned_time_str)

            return {
                "line": line_number,
                "destination": destination,
                "departure_time": estimated_local.strftime("%H:%M"),
                "planned_time": planned_local.strftime("%H:%M"),
                "real_time": estimated_local.strftime("%H:%M") if is_realtime else None,
                "delay": delay_minutes,
                "platform": platform,
                "transportation_type": transport_type,
                "description": description,
                "is_realtime": is_realtime,
                "minutes_until_departure": minutes_until,
                "departure_time_obj": estimated_local,  # For internal sorting
            }

        except Exception as e:
            _LOGGER.debug("Error parsing departure: %s", e)
            return None

    def _parse_departure_vrr(
        self, stop: Dict[str, Any], berlin_tz: Union[ZoneInfo, Any], now: datetime
    ) -> Optional[Dict[str, Any]]:
        """Parse a single departure from VRR API response.

        Args:
            stop: Stop event data from VRR API
            berlin_tz: Berlin timezone object
            now: Current datetime

        Returns:
            Parsed departure dictionary or None if parsing fails
        """
        return self._parse_departure_generic(
            stop,
            berlin_tz,
            now,
            get_transport_type_fn=self._determine_transport_type_vrr,
            get_platform_fn=lambda s: s.get("platform", {}).get("name") or s.get("platformName", ""),
            get_realtime_fn=lambda s, est, plan: "MONITORED" in s.get("realtimeStatus", []),
        )

    def _parse_departure_kvv(
        self, stop: Dict[str, Any], berlin_tz: Union[ZoneInfo, Any], now: datetime
    ) -> Optional[Dict[str, Any]]:
        """Parse a single departure from KVV API response.

        Args:
            stop: Stop event data from KVV API
            berlin_tz: Berlin timezone object
            now: Current datetime

        Returns:
            Parsed departure dictionary or None if parsing fails
        """
        return self._parse_departure_generic(
            stop,
            berlin_tz,
            now,
            get_transport_type_fn=lambda t: KVV_TRANSPORTATION_TYPES.get(
                t.get("product", {}).get("class", 0), "unknown"
            ),
            get_platform_fn=lambda s: s.get("location", {}).get("disassembledName") or s.get("platformName", ""),
            get_realtime_fn=lambda s, est, plan: s.get("isRealtimeControlled", False),
        )

    def _parse_departure_hvv(
        self, stop: Dict[str, Any], berlin_tz: Union[ZoneInfo, Any], now: datetime
    ) -> Optional[Dict[str, Any]]:
        """Parse a single departure from HVV API response.

        Args:
            stop: Stop event data from HVV API
            berlin_tz: Berlin timezone object
            now: Current datetime

        Returns:
            Parsed departure dictionary or None if parsing fails
        """
        return self._parse_departure_generic(
            stop,
            berlin_tz,
            now,
            get_transport_type_fn=lambda t: HVV_TRANSPORTATION_TYPES.get(
                t.get("product", {}).get("class", 0), "unknown"
            ),
            get_platform_fn=lambda s: (
                s.get("location", {}).get("properties", {}).get("platform")
                or s.get("location", {}).get("platformName", "")
            ),
            get_realtime_fn=lambda s, est, plan: est != plan if est and plan else False,
        )

    def _determine_transport_type_vrr(self, transportation: Dict[str, Any]) -> str:
        """Determine the transportation type from VRR API data."""
        product = transportation.get("product", {})
        product_class = product.get("class", 0)

        # Map VRR product classes to our types
        type_mapping = {
            0: "train",  # High-speed trains (ICE, IC, EC)
            1: "train",  # Regional trains (RE, RB)
            2: "subway",  # U-Bahn (subway/metro)
            3: "subway",  # U-Bahn variant
            4: "tram",  # Tram/Streetcar
            5: "bus",  # City bus
            6: "bus",  # Regional bus
            7: "bus",  # Express bus
            8: "bus",  # Night bus
            9: "ferry",  # Ferry/Ship
            10: "taxi",  # Taxi
            11: "bus",  # Other/Special transport
            13: "train",  # Regionalzug (RE)
            15: "train",  # InterCity (IC)
            16: "train",  # InterCityExpress (ICE)
        }

        transport_type = type_mapping.get(product_class, "unknown")

        if product_class not in type_mapping:
            _LOGGER.debug(
                "Unknown transport class %s for line %s, defaulting to unknown",
                product_class,
                transportation.get("number", "unknown"),
            )

        return transport_type
