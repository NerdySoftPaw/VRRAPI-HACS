import logging
from datetime import datetime
import aiohttp
import asyncio
from typing import Any, Dict, List, Optional
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, DEFAULT_PLACE, DEFAULT_NAME, DEFAULT_DEPARTURES, API_URL, TRANSPORTATION_TYPES

_LOGGER = logging.getLogger(__name__)

class KVVSensor(SensorEntity):
    def __init__(self, hass, place_dm: str, name_dm: str, station_id: Optional[str] = None, 
                 departures: int = DEFAULT_DEPARTURES, transportation_types: List[str] = None):
        self._hass = hass
        self._state = None
        self._attributes = {}
        self._available = True
        self._last_update = None
        self.place_dm = place_dm
        self.name_dm = name_dm
        self.station_id = station_id
        self.departures_limit = departures
        self.transportation_types = transportation_types or ["tram", "train", "bus"]
        self._attr_unique_id = f"kvv_{station_id or f'{place_dm}_{name_dm}'.lower().replace(' ', '_')}"
        self._name = f"KVV {place_dm} - {name_dm}"

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def available(self):
        return self._available

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def icon(self):
        return "mdi:tram"

    async def async_update(self):
        try:
            data = await self._fetch_departures()
            if data:
                await self._process_departure_data(data)
                self._available = True
                self._last_update = dt_util.utcnow()
            else:
                self._available = False
        except Exception as e:
            _LOGGER.error("Error updating KVV sensor: %s", e)
            self._available = False

    async def _fetch_departures(self) -> Optional[Dict[str, Any]]:
        params = (
            f"outputFormat=RapidJSON&"
            f"place_dm={self.place_dm}&"
            f"name_dm={self.name_dm}&"
            f"type_dm=stop&"
            f"mode=direct&"
            f"useRealtime=1&"
            f"limit={self.departures_limit}"
        )
        url = f"{API_URL}?{params}"
        session = async_get_clientsession(self._hass)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; HomeAssistant KVV Integration)"}
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    _LOGGER.warning("KVV API returned status %s", response.status)
        except Exception as e:
            _LOGGER.warning("KVV API request failed: %s", e)
        return None

    async def _process_departure_data(self, data: Dict[str, Any]):
        stop_events = data.get("stopEvents", [])
        if not stop_events:
            self._state = "No departures"
            self._attributes = {
                "departures": [],
                "station_name": f"{self.place_dm} - {self.name_dm}",
                "last_updated": self._last_update.isoformat() if self._last_update else None,
                "next_departure_minutes": None
            }
            return
        departures = []
        berlin_tz = dt_util.get_time_zone("Europe/Berlin")
        now = dt_util.now()
        for stop in stop_events:
            dep = self._parse_departure(stop, berlin_tz, now)
            if dep and dep["transportation_type"] in self.transportation_types:
                departures.append(dep)
        departures.sort(key=lambda x: x.get("departure_time_obj", now))
        departures = departures[:self.departures_limit]
        if departures:
            next_departure = departures[0]
            self._state = next_departure["departure_time"]
            next_minutes = next_departure.get("minutes_until_departure")
        else:
            self._state = "No departures"
            next_minutes = None
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
        try:
            planned_time_str = stop.get("departureTimePlanned")
            estimated_time_str = stop.get("departureTimeEstimated")
            if not planned_time_str:
                return None
            planned_time = dt_util.parse_datetime(planned_time_str)
            estimated_time = dt_util.parse_datetime(estimated_time_str) if estimated_time_str else planned_time
            if not planned_time:
                return None
            planned_local = planned_time.astimezone(berlin_tz)
            estimated_local = estimated_time.astimezone(berlin_tz)
            delay_minutes = int((estimated_local - planned_local).total_seconds() / 60)
            transportation = stop.get("transportation", {})
            destination = transportation.get("destination", {}).get("name", "Unknown")
            line_number = transportation.get("number", "")
            description = transportation.get("description", "")
            product_class = transportation.get("product", {}).get("class", 0)
            transport_type = TRANSPORTATION_TYPES.get(product_class, "unknown")
            platform = stop.get("location", {}).get("disassembledName") or stop.get("platformName", "")
            time_diff = estimated_local - now
            minutes_until = max(0, int(time_diff.total_seconds() / 60))
            is_realtime = stop.get("isRealtimeControlled", False)
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
                "departure_time_obj": estimated_local
            }
        except Exception as e:
            _LOGGER.debug("Error parsing KVV departure: %s", e)
            return None
