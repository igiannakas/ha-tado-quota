"""Tests for the optional polling trim (trim.py)."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tado_quota import trim
from custom_components.tado_quota.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
async def detach_fake_tado(hass: HomeAssistant):
    yield
    for entry in hass.config_entries.async_entries("tado"):
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


class FakeApi:
    """Stands in for python-tado's API object, counting Tado calls."""

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.offsets = {"VA1": {"celsius": -5.0}, "VA2": {"celsius": -9.9}}

    def get_me(self):
        self.calls["get_me"] += 1
        return {"homes": [{"id": 1, "name": "Our Home"}]}

    def get_devices(self):
        self.calls["get_devices"] += 1
        return [{"shortSerialNo": "VA1"}, {"shortSerialNo": "VA2"}]

    def get_device_info(self, device_id, cmd=""):
        self.calls[f"get_device_info:{cmd}"] += 1
        return self.offsets[device_id] if cmd == "temperatureOffset" else {"serial": device_id}

    def get_zone_overlay_default(self, zone):
        self.calls["get_zone_overlay_default"] += 1
        return {"terminationCondition": {"type": "MANUAL"}, "zone": zone}

    def set_temp_offset(self, device_id, offset=0, measure="celsius"):
        self.calls["set_temp_offset"] += 1
        self.offsets[device_id] = {"celsius": offset}

    def get_zone_states(self):
        self.calls["get_zone_states"] += 1
        return {"zoneStates": {}}


class FakeTado:
    """Like python-tado's ``Tado``: delegates unknown attributes to the API."""

    def __init__(self) -> None:
        self._api = FakeApi()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._api, name)


def refresh(client) -> None:
    """The calls one Tado coordinator refresh makes (2 devices, 2 zones)."""
    client.get_me()
    client.get_devices()
    client.get_devices()
    for serial in ("VA1", "VA2"):
        client.get_device_info(serial, "temperatureOffset")
    client.get_zone_states()
    for zone in (1, 2):
        client.get_zone_overlay_default(zone)


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(trim.time, "monotonic", lambda: now[0])
    return now


def test_static_data_is_read_once(clock) -> None:
    client = FakeTado()
    assert trim.wrap(client, 3600)
    refresh(client)
    first = sum(client._api.calls.values())
    assert first == 7  # me, devices once (second from cache), 2 offsets, states, 2 overlays
    clock[0] += 180
    refresh(client)
    assert sum(client._api.calls.values()) - first == 2  # devices, zone states
    assert (
        trim.calls_saved(client) == 1 + 6
    )  # 1st: devices; 2nd: me, devices, 2 offsets, 2 overlays


def test_without_trim_every_refresh_reads_everything() -> None:
    client = FakeTado()
    refresh(client)
    refresh(client)
    assert sum(client._api.calls.values()) == 2 * 8


def test_static_data_is_read_again_after_max_age(clock) -> None:
    client = FakeTado()
    trim.wrap(client, 3600)
    refresh(client)
    clock[0] += 3601
    before = client._api.calls.copy()
    refresh(client)
    delta = client._api.calls - before
    assert delta["get_device_info:temperatureOffset"] == 2
    assert delta["get_zone_overlay_default"] == 2
    assert delta["get_me"] == 1


def test_device_list_is_cached_only_briefly(clock) -> None:
    client = FakeTado()
    trim.wrap(client, 3600)
    client.get_devices()
    client.get_devices()
    assert client._api.calls["get_devices"] == 1
    clock[0] += trim.DEVICES_MAX_AGE_S + 1
    client.get_devices()
    assert client._api.calls["get_devices"] == 2


def test_setting_an_offset_drops_that_offset(clock) -> None:
    client = FakeTado()
    trim.wrap(client, 3600)
    assert client.get_device_info("VA1", "temperatureOffset") == {"celsius": -5.0}
    client.get_device_info("VA2", "temperatureOffset")
    client.set_temp_offset("VA1", -6.0)
    assert client._api.calls["set_temp_offset"] == 1
    assert client.get_device_info("VA1", "temperatureOffset") == {"celsius": -6.0}
    client.get_device_info("VA2", "temperatureOffset")
    assert client._api.calls["get_device_info:temperatureOffset"] == 3  # VA2 still cached


def test_other_device_info_is_not_cached() -> None:
    client = FakeTado()
    trim.wrap(client, 3600)
    client.get_device_info("VA1")
    client.get_device_info("VA1")
    assert client._api.calls["get_device_info:"] == 2


def test_unwrap_restores_the_client() -> None:
    client = FakeTado()
    trim.wrap(client, 3600)
    assert trim.is_wrapped(client)
    trim.unwrap(client)
    assert not trim.is_wrapped(client)
    assert trim.calls_saved(client) is None
    refresh(client)
    refresh(client)
    assert sum(client._api.calls.values()) == 16
    trim.unwrap(client)  # no-op


def test_unknown_client_layout_is_left_alone() -> None:
    class Partial:
        def get_me(self):
            return {}

    client = Partial()
    assert not trim.wrap(client, 3600)
    assert not trim.is_wrapped(client)
    assert "get_me" not in client.__dict__
    assert not trim.wrap(None, 3600)


def test_wrapping_twice_keeps_one_cache(clock) -> None:
    client = FakeTado()
    trim.wrap(client, 3600)
    client.get_me()
    assert trim.wrap(client, 60)
    client.get_me()
    assert client._api.calls["get_me"] == 1
    clock[0] += 61
    client.get_me()
    assert client._api.calls["get_me"] == 2  # new max age applies


# --- Through the integration ------------------------------------------------


class FakeCoordinator:
    def __init__(self) -> None:
        self._tado = FakeTado()

    def get_rate_limit(self) -> dict[str, str]:
        return {"per-day": "20000", "window-seconds": "86400", "remaining": "19000"}


def add_tado(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain="tado", title="Our Home", unique_id="408311")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    entry.runtime_data = FakeCoordinator()
    return entry


async def setup(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Tado API quota", options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_off_by_default(hass: HomeAssistant) -> None:
    tado = add_tado(hass)
    await setup(hass)
    assert not trim.is_wrapped(tado.runtime_data._tado)
    attrs = hass.states.get("sensor.our_home_api_quota_used").attributes
    assert attrs["polling_trimmed"] is False and attrs["calls_saved"] is None


async def test_option_wraps_and_unload_unwraps(hass: HomeAssistant) -> None:
    tado = add_tado(hass)
    entry = await setup(hass, trim_polling=True, static_refresh_h=6)
    client = tado.runtime_data._tado
    assert trim.is_wrapped(client)
    refresh(client)
    refresh(client)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not trim.is_wrapped(client)


async def test_attributes_show_the_savings(hass: HomeAssistant) -> None:
    tado = add_tado(hass)
    await setup(hass, trim_polling=True, static_refresh_h=6)
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "homeassistant", {})
    refresh(tado.runtime_data._tado)
    refresh(tado.runtime_data._tado)  # straight after: the device list is cached too
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {"entity_id": "sensor.our_home_api_quota_used"},
        blocking=True,
    )
    attrs = hass.states.get("sensor.our_home_api_quota_used").attributes
    assert attrs["polling_trimmed"] is True
    assert attrs["calls_saved"] == 1 + 7


async def test_reloaded_tado_client_gets_wrapped(hass: HomeAssistant) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tado = add_tado(hass)
    await setup(hass, trim_polling=True)
    tado.runtime_data = FakeCoordinator()  # the Tado entry reloaded: a new client
    assert not trim.is_wrapped(tado.runtime_data._tado)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert trim.is_wrapped(tado.runtime_data._tado)


async def test_options_flow(hass: HomeAssistant) -> None:
    add_tado(hass)
    entry = await setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"trim_polling": True, "static_refresh_h": 3}
    )
    await hass.async_block_till_done()
    assert entry.options == {"trim_polling": True, "static_refresh_h": 3}
    client = hass.config_entries.async_entries("tado")[0].runtime_data._tado
    assert trim.is_wrapped(client)  # the entry reloaded with the trim on
