"""Fixtures for VRR integration tests."""
import pytest
from unittest.mock import patch, MagicMock
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.const import CONF_NAME

from custom_components.vrr.const import (
    DOMAIN,
    CONF_PROVIDER,
    CONF_STATION_ID,
    CONF_DEPARTURES,
    CONF_TRANSPORTATION_TYPES,
    CONF_SCAN_INTERVAL,
    PROVIDER_VRR,
)


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    from homeassistant.config_entries import ConfigEntry

    return ConfigEntry(
        version=1,
        domain=DOMAIN,
        title="Test Station",
        data={
            CONF_PROVIDER: PROVIDER_VRR,
            "place_dm": "Düsseldorf",
            "name_dm": "Hauptbahnhof",
            CONF_STATION_ID: None,
            CONF_DEPARTURES: 10,
            CONF_TRANSPORTATION_TYPES: ["bus", "train", "tram"],
            CONF_SCAN_INTERVAL: 60,
        },
        options={},
        source="user",
        entry_id="test_entry_id",
    )


@pytest.fixture
def mock_api_response():
    """Return a mock API response."""
    return {
        "stopEvents": [
            {
                "departureTimePlanned": "2025-01-15T10:00:00Z",
                "departureTimeEstimated": "2025-01-15T10:05:00Z",
                "transportation": {
                    "number": "U79",
                    "destination": {"name": "Duisburg Hbf"},
                    "description": "U-Bahn nach Duisburg",
                    "product": {"class": 4, "name": "Tram"},
                },
                "platform": {"name": "2"},
                "realtimeStatus": ["MONITORED"],
            },
            {
                "departureTimePlanned": "2025-01-15T10:10:00Z",
                "departureTimeEstimated": "2025-01-15T10:10:00Z",
                "transportation": {
                    "number": "721",
                    "destination": {"name": "Krefeld"},
                    "description": "Bus nach Krefeld",
                    "product": {"class": 5, "name": "Bus"},
                },
                "platform": {"name": "5"},
                "realtimeStatus": ["MONITORED"],
            },
        ]
    }


@pytest.fixture
def mock_coordinator(mock_api_response):
    """Return a mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = mock_api_response
    coordinator.last_update_success = True
    coordinator.provider = PROVIDER_VRR
    coordinator.place_dm = "Düsseldorf"
    coordinator.name_dm = "Hauptbahnhof"
    coordinator.station_id = None
    coordinator.departures_limit = 10
    return coordinator


@pytest.fixture
async def hass_with_integration(hass: HomeAssistant):
    """Set up the integration."""
    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return hass
