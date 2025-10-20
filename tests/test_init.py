"""Tests for VRR integration initialization."""
import pytest
from unittest.mock import patch, AsyncMock
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.vrr import async_setup, async_setup_entry, async_unload_entry
from custom_components.vrr.const import DOMAIN


async def test_async_setup(hass: HomeAssistant):
    """Test the component setup."""
    assert await async_setup(hass, {}) is True


async def test_async_setup_entry(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    """Test setting up a config entry."""
    # mock_config_entry already added to hass in fixture
    with patch(
        "custom_components.vrr.async_setup_entry",
        return_value=True,
    ):
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ):
            assert await async_setup_entry(hass, mock_config_entry) is True
            assert DOMAIN in hass.data


async def test_async_unload_entry(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    """Test unloading a config entry."""
    # mock_config_entry already added to hass in fixture
    hass.data[DOMAIN] = {f"{mock_config_entry.entry_id}_coordinator": {}}

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=True,
    ):
        assert await async_unload_entry(hass, mock_config_entry) is True
        assert f"{mock_config_entry.entry_id}_coordinator" not in hass.data.get(DOMAIN, {})


async def test_refresh_service(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    """Test the refresh_departures service."""
    # mock_config_entry already added to hass in fixture

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=AsyncMock(),
    ):
        await async_setup_entry(hass, mock_config_entry)

        # Verify service is registered
        assert hass.services.has_service(DOMAIN, "refresh_departures")
