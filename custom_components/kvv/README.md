# KVV Home Assistant Integration

Diese Integration zeigt Abfahrten für eine KVV-Haltestelle in Home Assistant an.

## Einrichtung

- Über HACS installieren oder als custom_component einbinden
- Integration "KVV Departures" hinzufügen
- Stadt und Haltestellenname angeben (z.B. Karlsruhe, Essenweinstraße)
- Optional: station_id, Anzahl Abfahrten, Transporttypen

## Unterstützte Transporttypen
- tram (Straßenbahn)
- train (S-Bahn)
- bus (Bus)

## Beispiel
```
sensor:
  - platform: kvv
    place_dm: Karlsruhe
    name_dm: Essenweinstraße
    departures: 5
    transportation_types:
      - tram
      - train
```

## Hinweise
- Die Integration nutzt die öffentliche KVV-API (siehe Beispielantwort in `example_responses/kvv.json`).
- Die Felder werden automatisch aus der API geparst.
