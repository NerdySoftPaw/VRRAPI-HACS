![logo]
# NRW/KVV Departures Home Assistant Integration
[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![HACS][hacsbadge]][hacs]

![Project Maintenance][maintenance-shield]


A Home Assistant integration for the public transport networks VRR (Verkehrsverbund Rhein-Ruhr) and KVV (Karlsruher Verkehrsverbund). This integration provides real-time departure information for public transport in NRW and Karlsruhe.

## Features

- **Real-time Departures**: Shows current departure times with delays
- **Multiple Transport Types**: Supports trains (ICE, IC, RE), subway, trams, and buses
- **Smart Filtering**: Filter by specific transportation types
- **Rate Limiting**: Automatic API rate limiting to prevent overload
- **Error Handling**: Robust error handling with exponential backoff strategy
- **Timezone Support**: Proper handling of German timezone

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right and select "Custom repositories"
4. Add this repository URL: `https://github.com/username/VRRAPI-HACS`
5. Select "Integration" as category
6. Click "Add"
7. Search for "VRR" and install the integration
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/vrr` folder to your `custom_components` directory
2. Restart Home Assistant

## Configuration

### YAML Configuration

```yaml
sensor:
  - platform: public_transport_de
    place_dm: "Düsseldorf"
    name_dm: "Hauptbahnhof"
    departures: 10
    transportation_types:
      - train
      - subway
      - tram
      - bus
    scan_interval: 60
```

### Configuration Options

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `place_dm` | string | Yes* | - | Name of the city/place |
| `name_dm` | string | Yes* | - | Name of the stop |
| `station_id` | string | Yes* | - | VRR Station ID (alternative to place_dm/name_dm) |
| `departures` | integer | No | 5 | Number of departures to display |
| `transportation_types` | list | No | all | List of transportation types to filter |
| `scan_interval` | integer | No | 60 | Update interval in seconds |

*Either `station_id` OR `place_dm` + `name_dm` are required.

### Transportation Types

- `train` - Trains (ICE, IC, RE, RB)
- `subway` - Subway/Metro (U-Bahn)
- `tram` - Tram/Streetcar
- `bus` - Bus
- `ferry` - Ferry
- `taxi` - Taxi

### Examples

#### With Station ID (Recommended)
```yaml
sensor:
  - platform: public_transport_de
    station_id: "20018235"  # Düsseldorf Hauptbahnhof
    departures: 10
    transportation_types:
      - train
      - subway
```

#### With Place and Stop Name
```yaml
sensor:
  - platform: public_transport_de
    place_dm: "Düsseldorf"
    name_dm: "Hauptbahnhof"
    departures: 5
    transportation_types:
      - train
```

#### Buses and Trams Only
```yaml
sensor:
  - platform: public_transport_de
    place_dm: "Essen"
    name_dm: "Hauptbahnhof"
    transportation_types:
      - bus
      - tram
```

## Sensor Attributes

The sensor provides the following attributes:

```yaml
state: "20:45"  # Next departure time
attributes:
  departures:
    - line: "U79"
      destination: "Duisburg Hbf"
      departure_time: "20:45"
      planned_time: "20:43"
      real_time: "20:45"
      delay: 2
      platform: "2"
      transportation_type: "subway"
      description: "U-Bahn"
      is_realtime: true
      minutes_until_departure: 15
  station_name: "Düsseldorf - Hauptbahnhof"
  station_id: "20018235"
  next_departure_minutes: 15
  total_departures: 10
  last_updated: "2025-06-11T18:30:00+02:00"
```

## API Limits and Rate Limiting

The integration implements intelligent rate limiting:

- **Daily Limit**: 800 API calls per day (with buffer)
- **Retry Logic**: Exponential backoff on errors
- **Timeout**: 10 seconds per API call
- **Max Retries**: 3 attempts per update

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

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Create a Pull Request

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

## Changelog

### Latest Changes
- Added comprehensive transport type mapping (ICE, IC, RE trains)
- Implemented intelligent API rate limiting
- Enhanced error handling with exponential backoff
- Added debug logging for transport classification
- Improved timezone handling for German local time
- Added support for both station ID and place/name queries
- Enhanced real-time data processing and delay calculations

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
[logo]: img/logo.png
