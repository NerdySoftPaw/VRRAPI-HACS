import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

DOMAIN = "vrr"

TRANSPORT_NETWORKS = {
    "VRR": "https://efa.vrr.de/vrr/XML_STOPFINDER_REQUEST?type_sf=stop&outputFormat=JSON&name_sf={query}",
    "KVV": "https://projekte.kvv-efa.de/sl3/XML_STOPFINDER_REQUEST?type_sf=stop&outputFormat=JSON&name_sf={query}",
    # Weitere EFA-kompatible Verbünde können hier ergänzt werden
}

class VrrApiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.network = None
        self.api_url = None
        self.location = None
        self.location_id = None

    async def async_step_user(self, user_input=None):
        """Schritt 1: Auswahl des Verkehrsverbundes"""
        errors = {}
        if user_input is not None:
            self.network = user_input["network"]
            self.api_url = TRANSPORT_NETWORKS[self.network]
            return await self.async_step_location()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("network", default="VRR"): vol.In(list(TRANSPORT_NETWORKS.keys()))
            }),
        )

    async def async_step_location(self, user_input=None):
        """Schritt 2: Ort/Haltestelle suchen und auswählen"""
        errors = {}
        suggestions = []
        query = ""
        if user_input is not None:
            query = user_input.get("location", "")
            if query:
                suggestions = await self._get_stopfinder_suggestions(query)
                if "location_select" in user_input:
                    selected = next((s for s in suggestions if s["name"] == user_input["location_select"]), None)
                    if selected:
                        self.location = selected["name"]
                        self.location_id = selected["id"]
                        return await self.async_step_stop()
                if not suggestions:
                    errors["location"] = "no_locations_found"
        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema({
                vol.Optional("location", default=query): str,
                vol.Optional("location_select"): vol.In([s["name"] for s in suggestions]) if suggestions else str,
            }),
            errors=errors,
            description_placeholders={
                "hint": "Tippe einen Ort oder eine Haltestelle ein und wähle dann einen Vorschlag."
            }
        )

    async def async_step_stop(self, user_input=None):
        """Schritt 3: (Optional) weitere Filterung oder 'genaue' Haltestelle wählen"""
        errors = {}
        suggestions = []
        query = ""
        if user_input is not None:
            query = user_input.get("stop", "")
            if query:
                # Suche weiter einschränken; z.B. Stationsname plus Eingabe
                search_string = f"{self.location} {query}".strip()
                suggestions = await self._get_stopfinder_suggestions(search_string)
                if "stop_select" in user_input:
                    selected = next((s for s in suggestions if s["name"] == user_input["stop_select"]), None)
                    if selected:
                        return self.async_create_entry(
                            title=f"{selected['name']} ({self.network})",
                            data={
                                "network": self.network,
                                "api_url": self.api_url,
                                "location": self.location,
                                "location_id": self.location_id,
                                "stop": selected["name"],
                                "stop_id": selected["id"],
                            }
                        )
                if not suggestions:
                    errors["stop"] = "no_stops_found"
        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema({
                vol.Optional("stop", default=query): str,
                vol.Optional("stop_select"): vol.In([s["name"] for s in suggestions]) if suggestions else str,
            }),
            errors=errors,
            description_placeholders={
                "hint": "Tippe eine Haltestelle ein und wähle dann einen Vorschlag."
            }
        )

    async def _get_stopfinder_suggestions(self, query):
        session = aiohttp_client.async_get_clientsession(self.hass)
        url = self.api_url.format(query=query)
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    stop_finder = data.get("stopFinder", {})
                    # VRR: response["stopFinder"]["points"]["point"] (kann dict oder list sein)
                    # KVV: response["stopFinder"]["points"] ist direkt eine Liste
                    points = stop_finder.get("points", [])
                    if isinstance(points, dict) and "point" in points:
                        # VRR-Style
                        points = points["point"]
                        if isinstance(points, dict):
                            points = [points]
                    elif isinstance(points, list):
                        # KVV-Style
                        pass
                    else:
                        points = []

                    results = []
                    for p in points:
                        # VRR: "ref" ist string, KVV: "ref" ist dict mit "id"
                        ref_val = ""
                        if isinstance(p.get("ref"), dict):
                            ref_val = p["ref"].get("id", "")
                        else:
                            ref_val = p.get("ref", "")
                        name_val = p.get("name", "")
                        if name_val and ref_val:
                            results.append({"name": name_val, "id": ref_val})
                    return results[:10]
        except Exception as e:
            print(f"StopFinder API error: {e}")
        return []