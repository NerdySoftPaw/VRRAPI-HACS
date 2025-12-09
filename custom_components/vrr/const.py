DOMAIN = "vrr"
DEFAULT_PLACE = "Düsseldorf"
DEFAULT_NAME = "Elbruchstrasse"
DEFAULT_DEPARTURES = 10
DEFAULT_SCAN_INTERVAL = 60

# Configuration keys
CONF_PROVIDER = "provider"  # NEU
CONF_STATION_ID = "station_id"
CONF_DEPARTURES = "departures"
CONF_TRANSPORTATION_TYPES = "transportation_types"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TRAFIKLAB_API_KEY = "trafiklab_api_key"  # For Trafiklab API
CONF_NTA_API_KEY = "nta_api_key"  # For NTA Ireland API (Primary Key)
CONF_NTA_API_KEY_SECONDARY = "nta_api_key_secondary"  # For NTA Ireland API (Secondary Key, optional)
CONF_USE_PROVIDER_LOGO = "use_provider_logo"  # Show provider logo instead of transport icon

# Provider
PROVIDER_VRR = "vrr"
PROVIDER_KVV = "kvv"
PROVIDER_HVV = "hvv"
PROVIDER_TRAFIKLAB_SE = "trafiklab_se"
PROVIDER_NTA_IE = "nta_ie"
PROVIDER_GTFS_DE = "gtfs_de"
PROVIDERS = [PROVIDER_VRR, PROVIDER_KVV, PROVIDER_HVV, PROVIDER_TRAFIKLAB_SE, PROVIDER_NTA_IE, PROVIDER_GTFS_DE]

# Transportation types mapping
TRANSPORTATION_TYPES = {"bus": "Bus", "tram": "Tram", "subway": "U-Bahn", "train": "S-Bahn/Train"}

# API Configuration
API_RATE_LIMIT_PER_MINUTE = 60
API_RATE_LIMIT_PER_HOUR = 1000
API_RATE_LIMIT_PER_DAY = 60000
API_BASE_URL_VRR = "https://openservice-test.vrr.de/static03/XML_DM_REQUEST"
API_BASE_URL_KVV = "https://projekte.kvv-efa.de/sl3-alone/XSLT_DM_REQUEST"
API_BASE_URL_HVV = "https://hvv.efa.de/efa/XML_DM_REQUEST"
API_BASE_URL_TRAFIKLAB = "https://realtime-api.trafiklab.se/v1"
API_BASE_URL_NTA_GTFSR = "https://api.nationaltransport.ie/gtfsr"
API_BASE_URL_NTA_GTFS_STATIC = "https://www.transportforireland.ie/transitData/Data/GTFS_Realtime.zip"
API_BASE_URL_GTFS_DE_GTFSR = "https://realtime.gtfs.de/realtime-free.pb"
# Note: GTFS Static download URL may need to be updated based on actual download link
# The page at https://gtfs.de/de/feeds/de_full/ should have a download button/link
API_BASE_URL_GTFS_DE_GTFS_STATIC = "https://gtfs.de/feeds/de_full.zip"
# Mapping für KVV
KVV_TRANSPORTATION_TYPES = {
    1: "train",  # S-Bahn
    4: "tram",  # Straßenbahn
    5: "bus",  # Bus
}

HVV_TRANSPORTATION_TYPES = {
    0: "train",  # Zug, S-Bahn
    1: "train",  # U-Bahn
    2: "subway",  # U-Bahn
    3: "bus",  # Bus
    4: "tram",  # Straßenbahn
    5: "bus",  # Bus, Metrobus
    6: "ferry",  # Fähre
    7: "on_demand",  # Rufbus, On-Demand
    # ... ergänzen je nach Bedarf und API
}

# Mapping für Trafiklab (Sweden)
TRAFIKLAB_TRANSPORTATION_TYPES = {
    "BUS": "bus",
    "TRAIN": "train",
    "TRAM": "tram",
    "METRO": "subway",
    "FERRY": "ferry",
}

# Mapping für NTA Ireland (GTFS route_type)
# GTFS route_type: 0=Tram, 1=Subway, 2=Rail, 3=Bus, 4=Ferry, 5=Cable tram, 6=Gondola, 7=Funicular
NTA_TRANSPORTATION_TYPES = {
    0: "tram",  # Tram, Streetcar, Light rail
    1: "subway",  # Subway, Metro
    2: "train",  # Rail
    3: "bus",  # Bus
    4: "ferry",  # Ferry
    5: "tram",  # Cable tram
    6: "tram",  # Gondola, Suspended cable car
    7: "train",  # Funicular
}

# Mapping für GTFS-DE (GTFS route_type) - gleiche Mapping wie NTA
GTFS_DE_TRANSPORTATION_TYPES = NTA_TRANSPORTATION_TYPES

# Provider-specific icons (MDI icons as fallback)
PROVIDER_ICONS = {
    "vrr": "mdi:bus-clock",
    "kvv": "mdi:tram",
    "hvv": "mdi:ferry",
    "trafiklab_se": "mdi:train",
    "nta_ie": "mdi:bus-multiple",
    "gtfs_de": "mdi:map-marker-multiple",
}

# Provider-specific entity pictures (logos)
# These can be overridden by the user or use external URLs
# Format: URL to a small logo image (recommended: 256x256 or smaller)
PROVIDER_ENTITY_PICTURES = {
    "vrr": "https://www.vrr.de/favicon.ico",
    "kvv": "https://www.kvv.de/favicon.ico",
    "hvv": "https://www.hvv.de/favicon.ico",
    "trafiklab_se": "https://www.trafiklab.se/favicon.ico",
    "nta_ie": "https://www.transportforireland.ie/favicon.ico",
    "gtfs_de": "https://gtfs.de/favicon.ico",
}
