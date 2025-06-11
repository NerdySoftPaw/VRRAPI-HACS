DOMAIN = "vrr"
DEFAULT_PLACE = "Düsseldorf"
DEFAULT_NAME = "Elbruchstrasse"
DEFAULT_DEPARTURES = 10
DEFAULT_SCAN_INTERVAL = 60

# Configuration keys
CONF_STATION_ID = "station_id"
CONF_DEPARTURES = "departures"
CONF_TRANSPORTATION_TYPES = "transportation_types"
CONF_SCAN_INTERVAL = "scan_interval"

# Transportation types mapping
TRANSPORTATION_TYPES = {
    "bus": "Bus",
    "tram": "Tram", 
    "subway": "U-Bahn",
    "train": "S-Bahn/Train"
}

# API Configuration
API_RATE_LIMIT_PER_MINUTE = 60
API_RATE_LIMIT_PER_HOUR = 1000
API_BASE_URL = "https://openservice-test.vrr.de/static03/XML_DM_REQUEST"