# NRW/KVV Home Assistant Integration

Diese Integration zeigt Abfahrten für VRR- und KVV-Haltestellen in Home Assistant an.

## Einrichtung

- Über HACS installieren oder als custom_component einbinden
- Integration "NRW/KVV Departures" hinzufügen
- Provider auswählen: `vrr` (Standard) oder `kvv`
- Stadt und Haltestellenname angeben (z.B. Düsseldorf, Elbruchstrasse oder Karlsruhe, Essenweinstraße)
- Optional: station_id, Anzahl Abfahrten, Transporttypen

## Unterstützte Provider
- vrr: Verkehrsverbund Rhein-Ruhr (Standard)
- kvv: Karlsruher Verkehrsverbund

## Unterstützte Transporttypen
- bus
- tram
- subway
- train

## Beispiel
```
sensor:
  - platform: public_transport_de
    provider: kvv
    place_dm: Karlsruhe
    name_dm: Essenweinstraße
    departures: 5
    transportation_types:
      - tram
      - train
```

## Hinweise
- Die Integration nutzt die öffentliche VRR- und KVV-API (siehe Beispielantworten in `example_responses/`).
- Die Felder werden automatisch aus der API geparst.
## HVV Support

HVV (Hamburger Verkehrsverbund) is now supported!

- Use `provider: hvv` in your configuration to fetch departures from any HVV stop.
- Platform information is parsed from `location.properties.platform` in the HVV API response.
- All relevant transport types (bus, metrobus, expressbus, etc.) are mapped.
- Real-time data is shown if HVV provides it via deviations between `departureTimePlanned` and `departureTimeEstimated`.

**Example HVV API response:**
```json
{
  "stopEvents": [
    {
      "location": {
        "name": "Stadionstraße",
        "properties": {
          "stopId": "28582004",
          "platform": "1"
        }
      },
      "departureTimePlanned": "2025-06-22T20:00:00Z",
      "transportation": {
        "number": "2",
        "description": "Berliner Tor > Hbf. > Altona > Schenefeld",
        "product": {
          "class": 5,
          "name": "Bus"
        },
        "destination": {
          "name": "Schenefeld, Schenefelder Platz"
        }
      }
    }
  ]
}
```