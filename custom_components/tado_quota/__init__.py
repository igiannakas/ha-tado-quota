"""Tado API quota: sensors for the Tado API calls left and used per Tado home.

Home Assistant's Tado integration (via python-tado) keeps the quota that
Tado reports on every API response (``RateLimit`` and ``RateLimit-Policy``
headers) but does not expose it as an entity.  This integration reads that
figure from memory, so it makes no Tado API calls of its own.

Optionally (option ``trim_polling``) it also serves Tado data that rarely
changes from a cache, cutting the calls each Tado refresh makes (trim.py).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from . import trim
from .const import (
    CONF_STATIC_REFRESH_H,
    CONF_TRIM_POLLING,
    DEFAULT_STATIC_REFRESH_H,
    TADO_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

# How often to check for a Tado client that is not wrapped yet (a Tado entry
# that was set up or reloaded since): its first refresh runs untrimmed.
TRIM_CHECK_INTERVAL = timedelta(seconds=30)


def _tado_clients(hass: HomeAssistant) -> list:
    return [
        client
        for entry in hass.config_entries.async_entries(TADO_DOMAIN)
        if entry.state is ConfigEntryState.LOADED and (client := trim.client_of(entry)) is not None
    ]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the sensors, and the polling trim when it is enabled."""
    if entry.options.get(CONF_TRIM_POLLING, False):
        max_age_s = 3600.0 * float(
            entry.options.get(CONF_STATIC_REFRESH_H, DEFAULT_STATIC_REFRESH_H)
        )

        @callback
        def _apply(_now=None) -> None:
            for client in _tado_clients(hass):
                newly = not trim.is_wrapped(client)
                if trim.wrap(client, max_age_s) and newly:
                    _LOGGER.info(
                        "Tado polling trimmed: offsets, overlay defaults and the home "
                        "are read from Tado every %s h instead of on every refresh",
                        entry.options.get(CONF_STATIC_REFRESH_H, DEFAULT_STATIC_REFRESH_H),
                    )

        _apply()
        entry.async_on_unload(async_track_time_interval(hass, _apply, TRIM_CHECK_INTERVAL))

    @callback
    def _unwrap_all() -> None:
        for client in _tado_clients(hass):
            trim.unwrap(client)

    entry.async_on_unload(_unwrap_all)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the sensors (and undo the trim, via async_on_unload)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
