async def async_setup_entry(hass, config_entry, async_add_entities):
    from .sensor import KVVSensor
    place_dm = config_entry.data.get("place_dm", "Karlsruhe")
    name_dm = config_entry.data.get("name_dm", "Essenweinstraße")
    station_id = config_entry.data.get("station_id")
    departures = config_entry.data.get("departures", 10)
    transportation_types = config_entry.data.get("transportation_types", ["tram", "train", "bus"])
    async_add_entities([
        KVVSensor(hass, place_dm, name_dm, station_id, departures, transportation_types)
    ], True)
