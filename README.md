# VRR API - Home Assistant Custom Component

![VRR API Banner](images/banner.png)

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![HACS][hacsbadge]][hacs]

![Project Maintenance][maintenance-shield]

A Home Assistant custom component that provides real-time departure information from VRR (Verkehrsverbund Rhein-Ruhr) public transportation network through their official API.

![Home Assistant Integration](images/ha-integration-preview.png)

## Features

- 🚌 **Real-time departures** - Get live departure times for buses, trams, and trains
- 🔄 **Auto-refresh** - Automatic updates of departure information
- 🎯 **Multi-station support** - Monitor multiple stations simultaneously  
- 📍 **Location-based** - Easy station lookup by name or ID
- 🏠 **Native HA integration** - Seamless integration with Home Assistant
- 📊 **Rich attributes** - Detailed information including delays, platforms, and destinations
- 🌐 **German public transport** - Full support for VRR network coverage

![Features Overview](images/features-overview.png)

## Installation

### HACS (Recommended)

1. **Add Custom Repository**
   - Open HACS in Home Assistant
   - Go to "Integrations"
   - Click the three dots menu and select "Custom repositories"
   - Add `https://github.com/NerdySoftPaw/VRRAPI-HACS` as repository
   - Select "Integration" as category

![HACS Installation Step 1](images/hacs-install-1.png)

2. **Install Integration**
   - Search for "VRR API" in HACS
   - Click "Download"
   - Restart Home Assistant

![HACS Installation Step 2](images/hacs-install-2.png)

### Manual Installation

1. Download the latest release from the [releases page][releases]
2. Extract the `custom_components/vrr_api` directory to your Home Assistant `custom_components` folder
3. Restart Home Assistant

```
custom_components/
├── vrr_api/
│   ├── __init__.py
│   ├── manifest.json
│   ├── sensor.py
│   └── ...
```

## Configuration

### Via Home Assistant UI (Recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **"+ ADD INTEGRATION"**
3. Search for **"VRR API"**
4. Follow the configuration wizard

![UI Configuration](images/ui-config.png)

### Via YAML Configuration

Add the following to your `configuration.yaml` file:

```yaml
sensor:
  - platform: vrr_api
    name: "Station Name"
    station_id: "20009289"  # VRR Station ID
    departures: 10          # Number of departures to show
    scan_interval: 60       # Update interval in seconds
    transportation_types:   # Optional: filter transport types
      - bus
      - tram
      - train
```

![YAML Configuration Example](images/yaml-config.png)

#### Configuration Variables

| Variable | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `name` | string | Yes | - | Friendly name for the sensor |
| `station_id` | string | Yes | - | VRR station ID (see [Finding Station IDs](#finding-station-ids)) |
| `departures` | integer | No | 10 | Number of upcoming departures to retrieve |
| `scan_interval` | integer | No | 60 | Update frequency in seconds |
| `transportation_types` | list | No | all | Filter by transport type: `bus`, `tram`, `train`, `subway` |

## Finding Station IDs

### Method 1: VRR Website
1. Visit the [VRR Journey Planner](https://www.vrr.de)
2. Search for your station
3. The station ID is in the URL: `...&from=20009289:...`

![Station ID from Website](images/station-id-website.png)

### Method 2: EFA API
Use the VRR EFA API to search for stations:
```
https://app.vrr.de/standard/XML_STOPFINDER_REQUEST?outputFormat=JSON&type_sf=any&name_sf=YOUR_STATION_NAME
```

### Method 3: Integration Logs
Enable debug logging to see available stations:
```yaml
logger:
  logs:
    custom_components.vrr_api: debug
```

## Usage Examples

### Basic Sensor

![Basic Sensor Card](images/basic-sensor.png)

```yaml
# Lovelace card example
type: entities
title: Next Departures
entities:
  - entity: sensor.hauptbahnhof_departures
    name: Düsseldorf Hauptbahnhof
```

### Custom Card with Departures

![Custom Departures Card](images/custom-card.png)

```yaml
type: markdown
content: |
  ## 🚌 Next Departures
  {% for departure in state_attr('sensor.hauptbahnhof_departures', 'departures') %}
  **{{ departure.line }}** to {{ departure.destination }}  
  ⏰ {{ departure.departure_time }} {% if departure.delay > 0 %}(+{{ departure.delay }} min){% endif %}  
  🚏 Platform {{ departure.platform }}
  {% endfor %}
```

### Automation Example

![Automation Example](images/automation.png)

```yaml
automation:
  - alias: "Notify of Next Bus"
    trigger:
      - platform: numeric_state
        entity_id: sensor.bus_stop_departures
        attribute: next_departure_minutes
        below: 10
    action:
      - service: notify.mobile_app
        data:
          message: "Bus arriving in {{ states.sensor.bus_stop_departures.attributes.next_departure_minutes }} minutes!"
```

## Sensor Attributes

Each VRR sensor provides rich attributes with departure information:

![Sensor Attributes](images/sensor-attributes.png)

| Attribute | Description |
|-----------|-------------|
| `departures` | List of upcoming departures |
| `station_name` | Name of the monitored station |
| `last_updated` | Timestamp of last API call |
| `next_departure_minutes` | Minutes until next departure |

### Departure Object Structure

```json
{
  "line": "U74",
  "destination": "Lörick",
  "departure_time": "14:23",
  "real_time": "14:25",
  "delay": 2,
  "platform": "1",
  "transportation_type": "subway"
}
```

## API Rate Limits

The VRR API has rate limits to ensure fair usage:

- **60 requests per minute** per IP address
- **1000 requests per hour** per IP address

The integration automatically handles rate limiting and will adjust polling intervals if needed.

![API Status](images/api-status.png)

## Troubleshooting

### Common Issues

#### Sensor Shows "Unknown"
![Troubleshooting Unknown](images/troubleshoot-unknown.png)

**Possible causes:**
- Invalid station ID
- API temporarily unavailable
- Network connectivity issues

**Solutions:**
1. Verify station ID is correct
2. Check Home Assistant logs for error messages
3. Restart the integration

#### No Departures Shown
![Troubleshooting No Departures](images/troubleshoot-no-departures.png)

**Possible causes:**
- Station has no scheduled departures
- All transportation types filtered out
- Outside service hours

**Solutions:**
1. Check transportation_types filter
2. Verify station operates at current time
3. Increase number of departures requested

### Debug Logging

Enable detailed logging to troubleshoot issues:

```yaml
logger:
  default: warning
  logs:
    custom_components.vrr_api: debug
```

![Debug Logs](images/debug-logs.png)

## Advanced Configuration

### Multiple Stations

Monitor multiple stations with different configurations:

```yaml
sensor:
  - platform: vrr_api
    name: "Home Bus Stop"
    station_id: "20009289"
    departures: 5
    transportation_types: [bus]
    
  - platform: vrr_api
    name: "Work Station"
    station_id: "20009145"
    departures: 8
    transportation_types: [train, subway]
```

### Template Sensors

Create custom template sensors for specific use cases:

```yaml
template:
  - sensor:
      - name: "Next Bus Minutes"
        state: >
          {% set next = state_attr('sensor.bus_stop_departures', 'next_departure_minutes') %}
          {{ next if next is not none else 'unknown' }}
        unit_of_measurement: 'min'
```

## Development

### Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/NerdySoftPaw/VRRAPI-HACS.git
   cd VRRAPI-HACS
   ```

2. **Set up development environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements_dev.txt
   ```

3. **Run tests:**
   ```bash
   pytest tests/
   ```

![Development Setup](images/dev-setup.png)

### Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting pull requests.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

![Contributing Workflow](images/contributing.png)

## Supported Transportation Types

![Transport Types](images/transport-types.png)

| Type | Description | VRR Code |
|------|-------------|----------|
| `bus` | City and regional buses | 5, 6, 7 |
| `tram` | Trams and light rail | 4 |
| `subway` | U-Bahn/Metro | 1 |
| `train` | S-Bahn and regional trains | 2, 3 |

## VRR Network Coverage

The integration supports the entire VRR network, covering:

- **Düsseldorf** and surrounding areas
- **Essen** metropolitan region  
- **Duisburg** and neighboring cities
- **Wuppertal** and Bergisches Land
- **Krefeld** and Niederrhein region

![VRR Coverage Map](images/vrr-coverage.png)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes and version history.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

![License Badge](images/license-badge.png)

## Support

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/NerdySoftPaw/VRRAPI-HACS/issues)
- 💡 **Feature Requests**: [GitHub Discussions](https://github.com/NerdySoftPaw/VRRAPI-HACS/discussions)
- 📖 **Documentation**: [Wiki](https://github.com/NerdySoftPaw/VRRAPI-HACS/wiki)

![Support Options](images/support.png)

## Acknowledgments

- Thanks to VRR for providing the public API
- Home Assistant community for development guidelines
- All contributors who help improve this integration

![Contributors](images/contributors.png)

---

**Made with ❤️ for the Home Assistant community**

[![GitHub followers](https://img.shields.io/github/followers/NerdySoftPaw.svg?style=social&label=Follow&maxAge=2592000)](https://github.com/NerdySoftPaw?tab=followers)

<!-- Links -->
[releases-shield]: https://img.shields.io/github/release/NerdySoftPaw/VRRAPI-HACS.svg?style=for-the-badge
[releases]: https://github.com/NerdySoftPaw/VRRAPI-HACS/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/NerdySoftPaw/VRRAPI-HACS.svg?style=for-the-badge
[commits]: https://github.com/NerdySoftPaw/VRRAPI-HACS/commits/main
[license-shield]: https://img.shields.io/github/license/NerdySoftPaw/VRRAPI-HACS.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-NerdySoftPaw-blue.svg?style=for-the-badge
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
