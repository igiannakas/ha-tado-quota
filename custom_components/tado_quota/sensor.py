"""Sensors: Tado API calls remaining and used, one pair per Tado home."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import trim
from .const import DOMAIN, SCAN_INTERVAL, TADO_DOMAIN

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
UNIT = "calls"


@dataclass(frozen=True)
class Quota:
    """Tado's daily API quota as last reported."""

    limit: int
    remaining: int
    window_s: int | None

    @property
    def used(self) -> int:
        return max(self.limit - self.remaining, 0)


def parse_quota(raw: Any) -> Quota | None:
    """Turn python-tado's rate-limit dict into a Quota (None if incomplete)."""
    if not isinstance(raw, dict):
        return None
    try:
        limit = int(raw["per-day"])
        remaining = int(raw["remaining"])
    except (KeyError, TypeError, ValueError):
        return None
    try:
        window_s: int | None = int(raw["window-seconds"])
    except (KeyError, TypeError, ValueError):
        window_s = None
    return Quota(limit=limit, remaining=remaining, window_s=window_s)


def read_quota(hass: HomeAssistant, tado_entry_id: str) -> Quota | None:
    """The quota held by a loaded Tado config entry, without calling Tado."""
    entry = hass.config_entries.async_get_entry(tado_entry_id)
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        return None
    coordinator = getattr(entry, "runtime_data", None)
    getter = getattr(coordinator, "get_rate_limit", None)
    if getter is None:
        # Older or newer layouts: ask the python-tado client directly.
        client = getattr(coordinator, "_tado", None)
        getter = getattr(client, "rate_limit_info", None)
    if getter is None:
        return None
    try:
        return parse_quota(getter())
    except Exception:  # noqa: BLE001 - never let a Tado internal break us
        _LOGGER.debug("Could not read the Tado quota", exc_info=True)
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a remaining/used pair for every Tado home."""
    entities: list[SensorEntity] = []
    for tado_entry in hass.config_entries.async_entries(TADO_DOMAIN):
        entities.append(TadoQuotaSensor(tado_entry, "remaining"))
        entities.append(TadoQuotaSensor(tado_entry, "used"))
    async_add_entities(entities, update_before_add=True)


class TadoQuotaSensor(SensorEntity):
    """Tado API calls remaining or used in the current daily window."""

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UNIT
    _attr_suggested_display_precision = 0

    def __init__(self, tado_entry: ConfigEntry, kind: str) -> None:
        self._tado_entry_id = tado_entry.entry_id
        self._kind = kind
        key = tado_entry.unique_id or tado_entry.entry_id
        self._attr_unique_id = f"{key}_{kind}"
        self._attr_translation_key = kind
        self._attr_icon = "mdi:api" if kind == "remaining" else "mdi:counter"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, key)},
            name=f"{tado_entry.title} API quota",
            manufacturer="Tado",
            model="API quota",
            entry_type=DeviceEntryType.SERVICE,
        )
        self._quota: Quota | None = None
        self._saved: int | None = None

    @property
    def available(self) -> bool:
        return self._quota is not None

    @property
    def native_value(self) -> int | None:
        if self._quota is None:
            return None
        return self._quota.remaining if self._kind == "remaining" else self._quota.used

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._quota is None:
            return None
        return {
            "limit": self._quota.limit,
            "window_seconds": self._quota.window_s,
            "used_percent": round(100 * self._quota.used / self._quota.limit, 1)
            if self._quota.limit
            else None,
            # Polling trim (option): on, and the calls served from its cache
            # since the Tado integration last loaded.
            "polling_trimmed": self._saved is not None,
            "calls_saved": self._saved,
        }

    async def async_update(self) -> None:
        self._quota = read_quota(self.hass, self._tado_entry_id)
        entry = self.hass.config_entries.async_get_entry(self._tado_entry_id)
        self._saved = trim.calls_saved(trim.client_of(entry)) if entry else None


__all__ = ["SCAN_INTERVAL"]  # read by Home Assistant to set the polling rate
