# VRR Departures

Diese Custom Component ruft direkt die Abfahrtszeiten der Rheinbahn über die öffentliche API ab und stellt sie als Sensor in Home Assistant bereit.

## Installation

1. Füge dieses Repository in HACS als benutzerdefiniertes Repository hinzu.
2. Installiere die Integration über HACS.
3. Starte Home Assistant neu.
4. Füge in deiner `configuration.yaml` Folgendes hinzu:

   ```yaml
   sensor:
     - platform: vrr
