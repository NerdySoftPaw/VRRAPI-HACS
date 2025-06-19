# VRR/KVV Home Assistant Integration

Diese Integration zeigt Abfahrten für VRR- und KVV-Haltestellen in Home Assistant an.

## Einrichtung

- Über HACS installieren oder als custom_component einbinden
- Integration "VRR/KVV Departures" hinzufügen
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
  - platform: vrr
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
