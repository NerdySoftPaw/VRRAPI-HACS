import logging
from datetime import datetime
import aiohttp

from homeassistant.components.sensor import SensorEntity

_LOGGER = logging.getLogger(__name__)

# Standardwerte für die dynamischen Parameter
DEFAULT_PLACE = "Düsseldorf"
DEFAULT_NAME = "Elbruchstrasse"

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the VRR sensor platform."""
    place_dm = config.get("place_dm", DEFAULT_PLACE)
    name_dm = config.get("name_dm", DEFAULT_NAME)
    async_add_entities([VRRSensor(place_dm, name_dm)], True)

class VRRSensor(SensorEntity):
    """Representation of a sensor showing upcoming departures from VRR."""

    def __init__(self, place_dm, name_dm):
        self._state = None
        self._attributes = {}
        self._name = f"VRRSensor Abfahrten ({place_dm} - {name_dm})"
        self.place_dm = place_dm
        self.name_dm = name_dm

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        # Zum Beispiel die Zeit der nächsten Abfahrt
        return self._state

    @property
    def extra_state_attributes(self):
        # Alle ermittelten Abfahrten als Liste
        return self._attributes

    async def async_update(self):
        """Fetch new state data for the sensor."""
        # Baue die URL dynamisch anhand der Konfiguration
        base_url = "https://openservice-test.vrr.de/static03/XML_DM_REQUEST"
        params = (
            f"outputFormat=RapidJSON&"
            f"place_dm={self.place_dm}&"
            f"type_dm=stop&"
            f"name_dm={self.name_dm}&"
            f"mode=direct&"
            f"useRealtime=1&"
            f"limit=4"
        )
        url = f"{base_url}?{params}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        _LOGGER.error("Fehler beim Abruf der Daten: Status %s", response.status)
                        return
                    data = await response.json()
        except Exception as e:
            _LOGGER.error("Exception beim Abruf der Daten: %s", e)
            return

        stop_events = data.get("stopEvents", [])
        if not stop_events:
            _LOGGER.warning("Keine Stop-Events in der Antwort gefunden")
            self._state = "Keine Daten"
            self._attributes = {}
            return

        departures = []
        for stop in stop_events:
            realtime = "MONITORED" in stop.get("realtimeStatus", [])
            departure_time_str = (
                stop.get("departureTimeEstimated")
                if realtime
                else stop.get("departureTimePlanned")
            )
            try:
                departure_time = datetime.fromisoformat(departure_time_str)
                time_str = departure_time.strftime("%H:%M:%S")
            except Exception:
                time_str = departure_time_str

            transportation = stop.get("transportation", {})
            departures.append({
                "departure_time": time_str,
                "number": transportation.get("number"),
                "destination": transportation.get("destination", {}).get("name"),
                "description": transportation.get("description")
            })

        # Setze den Zustand auf die Zeit der nächsten Abfahrt, sofern vorhanden
        self._state = departures[0]["departure_time"] if departures else "Keine Abfahrten"
        self._attributes = {"departures": departures}
