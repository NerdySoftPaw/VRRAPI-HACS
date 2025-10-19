"""Tests for VRR config flow with multi-step autocomplete."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.vrr.const import (
    DOMAIN,
    CONF_PROVIDER,
    CONF_STATION_ID,
    CONF_DEPARTURES,
    CONF_TRANSPORTATION_TYPES,
    CONF_SCAN_INTERVAL,
    PROVIDER_VRR,
    DEFAULT_DEPARTURES,
    DEFAULT_SCAN_INTERVAL,
)


@pytest.fixture
def mock_stopfinder_locations():
    """Mock stopfinder response for locations."""
    return [
        {
            "id": "placeID:5113000:10",
            "name": "Düsseldorf",
            "type": "locality",
            "place": "Düsseldorf",
        }
    ]


@pytest.fixture
def mock_stopfinder_stops():
    """Mock stopfinder response for stops."""
    return [
        {
            "id": "de:05111:5650",
            "name": "Hauptbahnhof",
            "type": "stop",
            "place": "Düsseldorf",
        }
    ]


async def test_user_step_provider_selection(hass: HomeAssistant):
    """Test initial step - provider selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_full_flow_with_single_results(hass: HomeAssistant, mock_stopfinder_stops):
    """Test complete flow when search returns single result."""
    # Step 1: Select provider
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Step 2: Select provider
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_PROVIDER: PROVIDER_VRR},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "stop_search"

    with patch(
        "custom_components.vrr.config_flow.VRRConfigFlow._search_stops",
        return_value=mock_stopfinder_stops,
    ), patch(
        "custom_components.vrr.async_setup_entry",
        return_value=True,
    ):
        # Step 3: Enter stop (single result, auto-advance to settings)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"stop_search": "Hauptbahnhof"},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "settings"

        # Step 4: Complete
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEPARTURES: 10,
                CONF_TRANSPORTATION_TYPES: ["bus", "train"],
                CONF_SCAN_INTERVAL: 60,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "VRR Düsseldorf - Hauptbahnhof"
        assert result["data"][CONF_PROVIDER] == PROVIDER_VRR
        assert result["data"][CONF_STATION_ID] == "de:05111:5650"
        assert result["data"]["place_dm"] == "Düsseldorf"
        assert result["data"]["name_dm"] == "Hauptbahnhof"


async def test_stop_search_no_results(hass: HomeAssistant):
    """Test stop search with no results."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Select provider
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_PROVIDER: PROVIDER_VRR},
    )

    with patch(
        "custom_components.vrr.config_flow.VRRConfigFlow._search_stops",
        return_value=[],
    ):
        # Search stop with no results
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"stop_search": "NonexistentStop"},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "stop_search"
        assert result["errors"]["stop_search"] == "no_results"


async def test_stop_select_with_multiple_results(hass: HomeAssistant):
    """Test stop selection when multiple results are found."""
    # Multiple stops
    multiple_stops = [
        {"id": "stop1", "name": "Hauptbahnhof", "type": "stop", "place": "Düsseldorf"},
        {"id": "stop2", "name": "Hauptbahnhof Gleis 1", "type": "stop", "place": "Düsseldorf"},
    ]

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Select provider
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_PROVIDER: PROVIDER_VRR},
    )

    with patch(
        "custom_components.vrr.config_flow.VRRConfigFlow._search_stops",
        return_value=multiple_stops,
    ):
        # Search stop (multiple results)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"stop_search": "Hauptbahnhof"},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "stop_select"


async def test_empty_stop_search(hass: HomeAssistant):
    """Test empty stop search."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Select provider
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_PROVIDER: PROVIDER_VRR},
    )

    # Empty search
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"stop_search": ""},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "stop_search"
    assert result["errors"] == {"stop_search": "empty_search"}


async def test_options_flow(hass: HomeAssistant, mock_config_entry):
    """Test options flow."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEPARTURES: 15,
            CONF_TRANSPORTATION_TYPES: ["bus", "train", "tram"],
            CONF_SCAN_INTERVAL: 120,
        },
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_DEPARTURES] == 15
    assert result2["data"][CONF_SCAN_INTERVAL] == 120


async def test_parse_stopfinder_response():
    """Test parsing of stopfinder API response."""
    from custom_components.vrr.config_flow import VRRConfigFlow

    flow = VRRConfigFlow()
    flow._provider = PROVIDER_VRR

    # Mock API response
    api_response = {
        "locations": [
            {
                "type": "stop",
                "name": "Hauptbahnhof",
                "id": "de:05111:5650",
                "parent": {"name": "Düsseldorf"},
            },
            {
                "type": "locality",
                "name": "Düsseldorf",
                "id": "placeID:5113000:10",
                "parent": {"name": ""},
            },
        ]
    }

    # Test stop parsing
    stops = flow._parse_stopfinder_response(api_response, search_type="stop")
    assert len(stops) == 1
    assert stops[0]["type"] == "stop"
    assert stops[0]["name"] == "Hauptbahnhof"

    # Test location parsing
    locations = flow._parse_stopfinder_response(api_response, search_type="location")
    assert len(locations) == 1
    assert locations[0]["type"] == "locality"
    assert locations[0]["name"] == "Düsseldorf"
