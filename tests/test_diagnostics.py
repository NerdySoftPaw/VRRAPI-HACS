"""Tests for VRR diagnostics."""
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.vrr.diagnostics import async_get_config_entry_diagnostics
from custom_components.vrr.const import DOMAIN


async def test_diagnostics(hass: HomeAssistant, mock_config_entry, mock_coordinator):
    """Test diagnostics output."""
    mock_config_entry.add_to_hass(hass)

    # Store coordinator in hass.data
    hass.data[DOMAIN] = {f"{mock_config_entry.entry_id}_coordinator": mock_coordinator}

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert "config_entry" in diagnostics
    assert "coordinator_data" in diagnostics
    assert diagnostics["config_entry"]["provider"] == "vrr"
    assert diagnostics["config_entry"]["place"] == "Düsseldorf"
    assert diagnostics["config_entry"]["name"] == "Hauptbahnhof"

    # Verify API stats are included
    assert "api_calls_today" in diagnostics["coordinator_data"]
    assert "last_update_success" in diagnostics["coordinator_data"]


async def test_diagnostics_no_coordinator(hass: HomeAssistant, mock_config_entry):
    """Test diagnostics when coordinator is not available."""
    mock_config_entry.add_to_hass(hass)
    hass.data[DOMAIN] = {}

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["coordinator_data"] is None
