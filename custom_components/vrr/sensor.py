import logging
from datetime import datetime
import aiohttp
import asyncio
import ssl
import pytz

from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util
from .const import DEFAULT_PLACE, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)
BASE_URL = "https://openservice-test.vrr.de/static03/XML_DM_REQUEST"

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the VRR sensor from a config entry."""
    place_dm = config_entry.data.get("place_dm", DEFAULT_PLACE)
    name_dm = config_entry.data.get("name_dm", DEFAULT_NAME)
    async_add_entities([VRRSensor(place_dm, name_dm)], True)

class VRRSensor(SensorEntity):
    """Representation of a sensor showing upcoming departures from VRR."""

    def __init__(self, place_dm, name_dm):
        self._state = None
        self._attributes = {}
        self._name = f"VRR Abfahrten ({place_dm} - {name_dm})"
        self.place_dm = place_dm
        self.name_dm = name_dm

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state, which is the departure time of the next departure."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return additional attributes, including all departures."""
        return self._attributes

    async def async_update(self):
        """Fetch new state data for the sensor."""
        params = (
            f"outputFormat=RapidJSON&"
            f"place_dm={self.place_dm}&"
            f"type_dm=stop&"
            f"name_dm={self.name_dm}&"
            f"mode=direct&"
            f"useRealtime=1&"
            f"limit=4"
        )
        url = f"{BASE_URL}?{params}"
        timeout = aiohttp.ClientTimeout(total=10)

        # SSL-Context zum Testen (Achtung: In Produktion nicht Zertifikatprüfung deaktivieren)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Zusätzliche Header, um der Anfrage einen Browser-ähnlichen User-Agent zu geben
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant/1.0)"
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            _LOGGER.error("Fehler beim Abruf der Daten: Status %s", response.status)
                            return
                        data = await response.json()
                        break  # Erfolgreicher Abruf, verlasse die Retry-Schleife
            except Exception as e:
                _LOGGER.error("Attempt %s: Exception beim Abruf der Daten: %s", attempt, e)
                if attempt == max_retries:
                    return
                await asyncio.sleep(2)

        stop_events = data.get("stopEvents", [])
        if not stop_events:
            _LOGGER.warning("Keine Stop-Events in der Antwort gefunden")
            self._state = "Keine Daten"
            self._attributes = {}
            return

        departures = []
        # Explizit die Zeitzone Europe/Berlin festlegen (das entspricht CEST/CET)
        berlin_tz = pytz.timezone("Europe/Berlin")
        for stop in stop_events:
            realtime = "MONITORED" in stop.get("realtimeStatus", [])
            departure_time_str = (
                stop.get("departureTimeEstimated")
                if realtime
                else stop.get("departureTimePlanned")
            )
            try:
                # Parse die UTC-Zeit, die vom Server geliefert wird
                departure_time = dt_util.parse_datetime(departure_time_str)
                # Konvertiere in die Europe/Berlin-Zeitzone
                local_time = departure_time.astimezone(berlin_tz)
                time_str = local_time.strftime("%H:%M:%S")
            except Exception:
                time_str = departure_time_str

            transportation = stop.get("transportation", {})
            departures.append({
                "departure_time": time_str,
                "number": transportation.get("number"),
                "destination": transportation.get("destination", {}).get("name"),
                "description": transportation.get("description")
            })

        self._state = departures[0]["departure_time"] if departures else "Keine Abfahrten"
        self._attributes = {"departures": departures}
