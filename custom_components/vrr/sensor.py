import logging
from datetime import datetime
import aiohttp
import asyncio
import ssl
import pytz
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import (
    DEFAULT_PLACE, 
    DEFAULT_NAME, 
    CONF_STATION_ID,
    CONF_DEPARTURES,
    CONF_TRANSPORTATION_TYPES,
    TRANSPORTATION_TYPES,
    DEFAULT_DEPARTURES,
    API_RATE_LIMIT_PER_DAY
)

_LOGGER = logging.getLogger(__name__)
BASE_URL = "https://openservice-test.vrr.de/static03/XML_DM_REQUEST"

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the VRR sensor from a config entry."""
    place_dm = config_entry.data.get("place_dm", DEFAULT_PLACE)
    name_dm = config_entry.data.get("name_dm", DEFAULT_NAME)
    station_id = config_entry.data.get(CONF_STATION_ID)
    departures = config_entry.data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES)
    transportation_types = config_entry.data.get(CONF_TRANSPORTATION_TYPES, list(TRANSPORTATION_TYPES.keys()))
    
    async_add_entities([VRRSensor(hass, place_dm, name_dm, station_id, departures, transportation_types)], True)

class VRRSensor(SensorEntity):
    """Representation of a sensor showing upcoming departures from VRR."""

    def __init__(self, hass, place_dm: str, name_dm: str, station_id: Optional[str] = None, 
                 departures: int = DEFAULT_DEPARTURES, transportation_types: List[str] = None):
        self._hass = hass
        self._state = None
        self._attributes = {}
        self._available = True
        self._last_update = None
        self._api_calls_today = 0
        self._last_api_reset = datetime.now().date()
        
        # Configuration
        self.place_dm = place_dm
        self.name_dm = name_dm
        self.station_id = station_id
        self.departures_limit = departures
        self.transportation_types = transportation_types or list(TRANSPORTATION_TYPES.keys())
        
        # Setup entity
        self._attr_unique_id = f"vrr_{station_id or f'{place_dm}_{name_dm}'.lower().replace(' ', '_')}"
        self._name = f"VRR {place_dm} - {name_dm}"
        self._berlin_tz = pytz.timezone("Europe/Berlin")  # Zeitzone nur einmal laden
        
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state, which is the departure time of the next departure."""
        return self._state

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def extra_state_attributes(self):
        """Return additional attributes, including all departures."""
        return self._attributes

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:bus-clock"

    def _check_rate_limit(self) -> bool:
        """Check if we're within API rate limits."""
        today = datetime.now().date()
        if today > self._last_api_reset:
            self._api_calls_today = 0
            self._last_api_reset = today
            
        # VRR API limits: 60 per minute, 1000 per hour, let's be conservative
        if self._api_calls_today >= API_RATE_LIMIT_PER_DAY:  # Daily limit with buffer
            _LOGGER.warning("API rate limit approached, skipping update")
            return False
        return True

    async def async_update(self):
        """Fetch new state data for the sensor."""
        if not self._check_rate_limit():
            return
            
        try:
            data = await self._fetch_departures()
            if data:
                await self._process_departure_data(data)
                self._available = True
                self._last_update = dt_util.utcnow()
                self._api_calls_today += 1
            else:
                self._available = False
        except Exception as e:
            _LOGGER.error("Error updating VRR sensor: %s", e)
            self._available = False

    async def _fetch_departures(self) -> Optional[Dict[str, Any]]:
        """Fetch departure data from VRR API."""
        if self.station_id:
            # Use station ID if provided
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
            # Use place and name
            params = (
                f"outputFormat=RapidJSON&"
                f"place_dm={self.place_dm}&"
                f"type_dm=stop&"
                f"name_dm={self.name_dm}&"
                f"mode=direct&"
                f"useRealtime=1&"
                f"limit={self.departures_limit}"
            )
            
        url = f"{BASE_URL}?{params}"
        session = async_get_clientsession(self._hass)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant VRR Integration)"
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        _LOGGER.warning("VRR API returned status %s", response.status)
                        
            except Exception as e:
                _LOGGER.warning("Attempt %s failed: %s", attempt, e)
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
        return None

    async def _process_departure_data(self, data: Dict[str, Any]):
        """Process the departure data from VRR API."""
        stop_events = data.get("stopEvents", [])
        if not stop_events:
            _LOGGER.warning("No departures found in API response")
            self._state = "No departures"
            self._attributes = {
                "departures": [],
                "station_name": f"{self.place_dm} - {self.name_dm}",
                "last_updated": self._last_update.isoformat() if self._last_update else None,
                "next_departure_minutes": None
            }
            return

        departures = []
        berlin_tz = self._berlin_tz  # Verwende die Instanzvariable
        now = datetime.now(berlin_tz)
        
        for stop in stop_events:
            try:
                departure_info = self._parse_departure(stop, berlin_tz, now)
                if departure_info and self._filter_transportation_type(departure_info):
                    departures.append(departure_info)
            except Exception as e:
                _LOGGER.debug("Error parsing departure: %s", e)
                continue

        # Sort by departure time
        departures.sort(key=lambda x: x.get("departure_time_obj", now))
        
        # Limit to requested number
        departures = departures[:self.departures_limit]

        # Set state and attributes
        if departures:
            next_departure = departures[0]
            self._state = next_departure["departure_time"]
            next_minutes = next_departure.get("minutes_until_departure")
        else:
            self._state = "No departures"
            next_minutes = None

        # Remove internal objects before setting attributes
        clean_departures = []
        for dep in departures:
            clean_dep = dep.copy()
            clean_dep.pop("departure_time_obj", None)
            clean_departures.append(clean_dep)

        self._attributes = {
            "departures": clean_departures,
            "station_name": f"{self.place_dm} - {self.name_dm}",
            "last_updated": self._last_update.isoformat() if self._last_update else None,
            "next_departure_minutes": next_minutes,
            "station_id": self.station_id,
            "total_departures": len(clean_departures)
        }

    def _parse_departure(self, stop: Dict[str, Any], berlin_tz, now: datetime) -> Optional[Dict[str, Any]]:
        """Parse a single departure from API response."""
        try:
            # Get times
            planned_time_str = stop.get("departureTimePlanned")
            estimated_time_str = stop.get("departureTimeEstimated") 
            
            if not planned_time_str:
                return None
                
            # Parse times
            planned_time = dt_util.parse_datetime(planned_time_str)
            estimated_time = dt_util.parse_datetime(estimated_time_str) if estimated_time_str else planned_time
            
            if not planned_time:
                return None
                
            # Convert to local timezone
            planned_local = planned_time.astimezone(berlin_tz)
            estimated_local = estimated_time.astimezone(berlin_tz)
            
            # Calculate delay
            delay_minutes = int((estimated_local - planned_local).total_seconds() / 60)
            
            # Get transportation info
            transportation = stop.get("transportation", {})
            destination = transportation.get("destination", {}).get("name", "Unknown")
            line_number = transportation.get("number", "")
            description = transportation.get("description", "")
            
            # Determine transportation type
            transport_type = self._determine_transport_type(transportation)
            
            # Get platform/track info
            platform = stop.get("platform", {}).get("name") or stop.get("platformName", "")
            
            # Calculate minutes until departure
            time_diff = estimated_local - now
            minutes_until = max(0, int(time_diff.total_seconds() / 60))
            
            # Determine if real-time data is available
            is_realtime = "MONITORED" in stop.get("realtimeStatus", [])
            
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
                "departure_time_obj": estimated_local  # For internal sorting
            }
            
        except Exception as e:
            _LOGGER.debug("Error parsing departure: %s", e)
            return None

    def _determine_transport_type(self, transportation: Dict[str, Any]) -> str:
        """Determine the transportation type from API data."""
        product = transportation.get("product", {})
        product_class = product.get("class", 0)
        
        # Map VRR product classes to our types
        # Based on actual VRR API responses and German transport classifications
        type_mapping = {
            0: "train",     # High-speed trains (ICE, IC, EC) - legacy
            1: "train",     # Regional trains (RE, RB) - legacy
            2: "subway",    # U-Bahn (subway/metro) ✓ confirmed
            3: "subway",    # U-Bahn variant
            4: "tram",      # Tram/Streetcar ✓ confirmed
            5: "bus",       # City bus ✓ confirmed
            6: "bus",       # Regional bus
            7: "bus",       # Express bus
            8: "bus",       # Night bus
            9: "ferry",     # Ferry/Ship
            10: "taxi",     # Taxi
            11: "bus",      # Other/Special transport
            13: "train",    # Regionalzug (RE) ✓ confirmed from API
            15: "train",    # InterCity (IC) ✓ confirmed from API
            16: "train",    # InterCityExpress (ICE) ✓ confirmed from API
        }
        
        # Add logging for unmapped classes to help with debugging
        transport_type = type_mapping.get(product_class, "unknown")
        
        if product_class not in type_mapping:
            _LOGGER.debug("Unknown transport class %s for line %s, defaulting to unknown", 
                        product_class, transportation.get("number", "unknown"))
        
        return transport_type

    def _filter_transportation_type(self, departure: Dict[str, Any]) -> bool:
        """Filter departure by transportation type."""
        if not self.transportation_types:
            return True
        return departure.get("transportation_type") in self.transportation_types