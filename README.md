![logo]
# NRW/KVV/VRR Departures Home Assistant Integration
[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![HACS][hacsbadge]][hacs]

![Project Maintenance][maintenance-shield]
[![HACS Validation](https://github.com/NerdySoftPaw/VRRAPI-HACS/actions/workflows/hacs.yaml/badge.svg)](https://github.com/NerdySoftPaw/VRRAPI-HACS/actions/workflows/hacs.yaml)
[![Code Quality](https://github.com/NerdySoftPaw/VRRAPI-HACS/actions/workflows/lint.yaml/badge.svg)](https://github.com/NerdySoftPaw/VRRAPI-HACS/actions/workflows/lint.yaml)
[![Tests](https://github.com/NerdySoftPaw/VRRAPI-HACS/actions/workflows/tests.yaml/badge.svg)](https://github.com/NerdySoftPaw/VRRAPI-HACS/actions/workflows/tests.yaml)


A Home Assistant integration for the public transport networks VRR (Verkehrsverbund Rhein-Ruhr), KVV (Karlsruher Verkehrsverbund) and HVV (Hochbahn). This integration provides real-time departure information for public transport in NRW, Karlsruhe and Hamburg.

## Features

- **Smart Setup Wizard**: Intuitive multi-step configuration with autocomplete for locations and stops
- **Real-time Departures**: Shows current departure times with delays
- **Multiple Transport Types**: Supports trains (ICE, IC, RE), subway, trams, and buses
- **Smart Filtering**: Filter by specific transportation types
- **Binary Sensor for Delays**: Automatic detection of delays > 5 minutes
- **Device Support**: Entities are grouped together with suggested areas
- **Repair Issues Integration**: Automatic notifications for API errors or rate limits
- **Rate Limiting**: Intelligent API rate limiting to prevent overload (60,000 calls/day)
- **Error Handling**: Robust error handling with exponential backoff strategy
- **Timezone Support**: Proper handling of German timezone (Europe/Berlin)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right and select "Custom repositories"
4. Add this repository URL: `https://github.com/nerdysoftpaw/VRRAPI-HACS`
5. Select "Integration" as category
6. Click "Add"
7. Search for "VRR" and install the integration
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/public_transport_de` folder to your `custom_components` directory
2. Restart Home Assistant

## Configuration

Die Integration verwendet einen **intuitiven Multi-Step Setup-Wizard** mit Autocomplete-Funktion:

### Setup Wizard

1. **Anbieter auswählen**
   - Wähle zwischen VRR (NRW), KVV (Karlsruhe) oder HVV (Hamburg)

2. **Stadt/Ort suchen**
   - Gib deine Stadt ein (z.B. "Düsseldorf", "Köln", "Hamburg")
   - Die Integration sucht automatisch nach passenden Orten

3. **Haltestelle auswählen**
   - Gib den Namen deiner Haltestelle ein (z.B. "Hauptbahnhof", "Marktplatz")
   - Die Integration schlägt automatisch Haltestellen in deinem Ort vor

4. **Einstellungen konfigurieren**
   - Anzahl der Abfahrten (1-20)
   - Verkehrsmittel-Filter (Bus, Bahn, Tram, etc.)
   - Update-Intervall (10-3600 Sekunden)

### Schritte zur Installation

1. Gehe zu **Einstellungen** > **Geräte & Dienste**
2. Klicke auf **+ Integration hinzufügen**
3. Suche nach "VRR" oder "NRW/KVV Departures"
4. Folge dem Setup-Wizard

### Transportation Types

- `train` - Trains (ICE, IC, RE, RB)
- `subway` - Subway/Metro (U-Bahn)
- `tram` - Tram/Streetcar
- `bus` - Bus
- `ferry` - Ferry
- `taxi` - Taxi

### Examples

#### Configuration Example

After installation, add the integration via UI:
1. Go to Settings > Devices & Services
2. Click "+ Add Integration"
3. Search for "VRR" or "NRW/KVV Departures"
4. Follow the setup wizard

## Lovelace Dashboard Examples

### 1. Simple Entities Card

```yaml
type: entities
title: Düsseldorf Hauptbahnhof
entities:
  - entity: sensor.vrr_dusseldorf_hauptbahnhof
    name: Nächste Abfahrt
  - type: attribute
    entity: sensor.vrr_dusseldorf_hauptbahnhof
    attribute: next_departure_minutes
    name: In Minuten
    suffix: min
  - type: attribute
    entity: sensor.vrr_dusseldorf_hauptbahnhof
    attribute: total_departures
    name: Verfügbare Verbindungen
```

### 2. Markdown Card with Departures List

```yaml
type: markdown
title: Abfahrten - Hauptbahnhof
content: >
  {% set departures = state_attr('sensor.vrr_dusseldorf_hauptbahnhof',
  'departures') %}

  {% if departures %}
    {% for departure in departures[:5] %}
      **{{ departure.line }}** → {{ departure.destination }}
      🕐 {{ departure.departure_time }} {% if departure.delay > 0 %}(+{{ departure.delay }} min){% endif %}
      📍 Gleis {{ departure.platform }}

    {% endfor %}
  {% else %}
    Keine Abfahrten verfügbar
  {% endif %}
```

### 3. Custom Button Card for Manual Refresh

```yaml
type: button
name: Abfahrten aktualisieren
icon: mdi:refresh
tap_action:
  action: call-service
  service: vrr.refresh_departures
  service_data:
    entity_id: sensor.vrr_dusseldorf_hauptbahnhof
```

### 4. Multiple Departures with Auto-Entities (requires custom:auto-entities)

```yaml
type: custom:auto-entities
card:
  type: entities
  title: Alle Abfahrten
filter:
  template: >
    {% set departures = state_attr('sensor.vrr_dusseldorf_hauptbahnhof',
    'departures') %}

    {% for departure in departures %}
      {{
        {
          'type': 'custom:template-entity-row',
          'name': departure.line + ' → ' + departure.destination,
          'icon': 'mdi:train',
          'state': departure.departure_time,
          'secondary': 'Gleis ' + departure.platform + ' | in ' + departure.minutes_until_departure|string + ' min'
        }
      }},
    {% endfor %}
```

### 5. Template Sensor for "Minutes Until Departure"

Add this to your `configuration.yaml`:

```yaml
template:
  - sensor:
      - name: "Next Train Minutes"
        state: >
          {{ state_attr('sensor.vrr_dusseldorf_hauptbahnhof', 'next_departure_minutes') }}
        unit_of_measurement: "min"
        icon: mdi:clock-outline

      - name: "Next Train Line"
        state: >
          {% set departures = state_attr('sensor.vrr_dusseldorf_hauptbahnhof', 'departures') %}
          {% if departures and departures|length > 0 %}
            {{ departures[0].line }}
          {% else %}
            -
          {% endif %}
        icon: mdi:train
```

### 6. Conditional Card (only show if departure soon)

```yaml
type: conditional
conditions:
  - entity: sensor.next_train_minutes
    state_not: unavailable
    state_not: unknown
  - entity: sensor.next_train_minutes
    state_below: 10
card:
  type: markdown
  content: >
    ⚠️ **Achtung!** Dein Zug fährt in {{ states('sensor.next_train_minutes') }} Minuten!
```

### 7. Full Dashboard Example

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: 🚉 Düsseldorf Hauptbahnhof
    content: >
      Nächste Abfahrt: **{{ states('sensor.vrr_dusseldorf_hauptbahnhof') }}**

      In {{ state_attr('sensor.vrr_dusseldorf_hauptbahnhof', 'next_departure_minutes') }} Minuten

  - type: custom:mushroom-chips-card
    chips:
      - type: entity
        entity: sensor.vrr_dusseldorf_hauptbahnhof
        icon: mdi:train
        content_info: state
      - type: template
        icon: mdi:clock-outline
        content: >
          {{ state_attr('sensor.vrr_dusseldorf_hauptbahnhof', 'next_departure_minutes') }} min
      - type: template
        icon: mdi:refresh
        tap_action:
          action: call-service
          service: vrr.refresh_departures

  - type: markdown
    content: >
      {% set departures = state_attr('sensor.vrr_dusseldorf_hauptbahnhof', 'departures') %}

      {% if departures %}
        | Linie | Ziel | Abfahrt | Gleis |
        |-------|------|---------|-------|
        {% for dep in departures[:5] %}
        | **{{ dep.line }}** | {{ dep.destination }} | {{ dep.departure_time }}{% if dep.delay > 0 %} <font color="red">(+{{ dep.delay }})</font>{% endif %} | {{ dep.platform }} |
        {% endfor %}
      {% endif %}
```

## Services

### Refresh Departures

Manually refresh departure data from the API.

```yaml
service: vrr.refresh_departures
data:
  entity_id: sensor.vrr_dusseldorf_hauptbahnhof  # Optional
```

**Examples:**

Refresh all VRR sensors:
```yaml
service: vrr.refresh_departures
```

Refresh specific sensor:
```yaml
service: vrr.refresh_departures
data:
  entity_id: sensor.vrr_dusseldorf_hauptbahnhof
```

Use in automation:
```yaml
automation:
  - alias: "Refresh departures when arriving home"
    trigger:
      - platform: state
        entity_id: person.john
        to: home
    action:
      - service: vrr.refresh_departures
        data:
          entity_id: sensor.vrr_dusseldorf_hauptbahnhof
```

## API Limits and Rate Limiting

The integration implements intelligent rate limiting:

- **Daily Limit**: 800 API calls per day (with buffer)
- **Retry Logic**: Exponential backoff on errors
- **Timeout**: 10 seconds per API call
- **Max Retries**: 3 attempts per update

## Diagnostics

The integration supports Home Assistant's diagnostics feature for easier troubleshooting.

### How to Download Diagnostics:

1. Go to **Settings** > **Devices & Services**
2. Find your VRR integration
3. Click on the integration
4. Click the **3 dots** menu
5. Select **Download Diagnostics**

The diagnostics file contains:
- Configuration details (anonymized)
- Coordinator status
- API call statistics
- Sample API response structure
- Last update information

This information is helpful when reporting issues on GitHub.

## Troubleshooting

### Finding Station ID

To find the station ID, use the VRR API:
```
https://openservice-test.vrr.de/static03/XML_STOPFINDER_REQUEST?outputFormat=RapidJSON&locationServerActive=1&type_sf=stop&name_sf=Düsseldorf%20Hauptbahnhof
```

### Enable Debug Logging

```yaml
logger:
  default: warning
  logs:
    custom_components.vrr: debug
```

### Common Issues

1. **"No departures" State**: 
   - Check station ID or place_dm/name_dm
   - Verify the stop exists

2. **API Rate Limit Reached**:
   - Increase scan_interval
   - Reduce number of VRR sensors

3. **Unknown Transportation Types**:
   - Check debug logs for new product.class values
   - Report missing mappings as an issue

## Transport Class Mapping

The integration maps VRR API Product Classes:

| Class | Transport Type | Description |
|-------|---------------|-------------|
| 0, 1 | train | Legacy trains |
| 2, 3 | subway | Subway/Metro (U-Bahn) |
| 4 | tram | Tram/Streetcar |
| 5-8, 11 | bus | Various bus types |
| 9 | ferry | Ferry |
| 10 | taxi | Taxi |
| 13 | train | Regional train (RE) |
| 15 | train | InterCity (IC) |
| 16 | train | InterCityExpress (ICE) |

## Development and Testing

This integration includes a comprehensive test suite to ensure quality and reliability.

### Running Tests

1. Install test dependencies:
   ```bash
   pip install -r requirements_test.txt
   ```

2. Run the test suite:
   ```bash
   pytest
   ```

3. Run tests with coverage report:
   ```bash
   pytest --cov=custom_components/vrr --cov-report=html
   ```

4. Run specific test files:
   ```bash
   pytest tests/test_sensor.py
   pytest tests/test_binary_sensor.py
   ```

### Test Coverage

The test suite includes:
- **Coordinator Tests**: Rate limiting, API error handling, data updates
- **Sensor Tests**: State updates, icon changes, transportation filtering, attribute validation
- **Binary Sensor Tests**: Delay detection, threshold testing, icon states
- **Config Flow Tests**: User flow, options flow, validation
- **Diagnostics Tests**: Diagnostic data output
- **Integration Tests**: Setup, unload, service registration

### Code Quality

The project uses automated code quality tools:
- **Black**: Code formatting
- **isort**: Import sorting
- **Flake8**: Linting
- **mypy**: Type checking

Run code quality checks:
```bash
black custom_components/vrr/
isort custom_components/vrr/
flake8 custom_components/vrr/
mypy custom_components/vrr/
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for new features
4. Ensure all tests pass
5. Run code quality checks
6. Commit your changes
7. Create a Pull Request

## License

This project is licensed under the MIT License.

## Support

For issues or questions:

1. Check the debug logs
2. Search existing issues for similar problems
3. Create a new issue with debug information

## API Example URLs

### Using Station ID
```
https://openservice-test.vrr.de/static03/XML_DM_REQUEST?outputFormat=RapidJSON&stateless=1&type_dm=any&name_dm=20018235&mode=direct&useRealtime=1&limit=10
```

### Using Place and Stop Name
```
https://openservice-test.vrr.de/static03/XML_DM_REQUEST?outputFormat=RapidJSON&place_dm=Düsseldorf&type_dm=stop&name_dm=Hauptbahnhof&mode=direct&useRealtime=1&limit=10
```


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

## Changelog

### Version 4.1.0 - UX Enhancement Update
#### New Features
- **Smart Setup Wizard with Autocomplete**: Multi-step configuration flow
  - Search for locations (cities) with autocomplete via STOPFINDER API
  - Search for stops/stations based on selected location
  - Automatic suggestions for both locations and stops
  - Support for all 3 providers (VRR, KVV, HVV)
- **Comprehensive Test Suite**: 50+ unit tests for all components
- **GitHub Actions CI/CD**: Automated testing, linting, and releases
- **Enhanced Error Messages**: Better German and English translations

### Version 4.0.0 - Major Update
#### New Features
- **DataUpdateCoordinator Pattern**: Modern Home Assistant best practice implementation
- **Binary Sensor for Delays**: Automatic delay detection (>5 minutes threshold)
- **Device Support**: Entities grouped together with suggested areas
- **Repair Issues Integration**: Notifications for API errors or rate limits
- **Diagnostics Support**: Download diagnostics for easier troubleshooting
- **Manual Refresh Service**: `vrr.refresh_departures` service for manual updates
- **Dynamic Icons**: Icon changes based on next departure type (bus, train, tram, etc.)
- **Transportation Type Filtering**: Now actually works! Filter departures by type
- **Options Flow Support**: Change settings without removing/re-adding integration
- **Enhanced Sensor Attributes**:
  - `next_3_departures`: Quick overview of upcoming departures
  - `delayed_count` / `on_time_count`: Departure statistics
  - `average_delay`: Average delay across all departures
  - `earliest_departure` / `latest_departure`: Time range of departures

#### Improvements
- **Code Optimization**: Eliminated ~200 lines of duplicate code
- **API Response Validation**: Better error handling and validation
- **Scan Interval**: Actually configurable now (10s - 3600s)
- **Enhanced Logging**: Better error messages with context
- **Rate Limiting**: Smarter handling of API limits (60,000 calls/day)
- **Code Quality**: Black, isort, Flake8, mypy integration

#### Bug Fixes
- Fixed transportation type filtering not working
- Fixed options not being applied
- Fixed scan interval being ignored
- Fixed missing imports and type hints

### Previous Changes
- Added comprehensive transport type mapping (ICE, IC, RE trains)
- Implemented intelligent API rate limiting
- Enhanced error handling with exponential backoff
- Added debug logging for transport classification
- Improved timezone handling for German local time
- Added support for both station ID and place/name queries
- Enhanced real-time data processing and delay calculations
- Improved sensor attributes for better usability

**Made with ❤️ for the Home Assistant community**
<!-- Links -->
[releases-shield]: https://img.shields.io/github/release/NerdySoftPaw/VRRAPI-HACS.svg?style=for-the-badge
[releases]: https://github.com/NerdySoftPaw/VRRAPI-HACS/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/NerdySoftPaw/VRRAPI-HACS.svg?style=for-the-badge
[commits]: https://github.com/NerdySoftPaw/VRRAPI-HACS/commits/main
[license-shield]: https://img.shields.io/github/license/NerdySoftPaw/VRRAPI-HACS.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-NerdySoftPaw-blue.svg?style=for-the-badge
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
[logo]: https://brands.home-assistant.io/vrr/icon.png
