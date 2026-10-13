"""Tado API quota: sensors for the Tado API calls left and used per Tado home.

Home Assistant's Tado integration (via python-tado) keeps the quota that
Tado reports on every API response (``RateLimit`` and ``RateLimit-Policy``
headers) but does not expose it as an entity.  This integration reads that
figure from memory, so it makes no Tado API calls of its own.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the sensors."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the sensors."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
