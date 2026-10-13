"""Tests for Tado API quota."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.tado_quota.const import DOMAIN
from custom_components.tado_quota.sensor import parse_quota


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
async def detach_fake_tado(hass: HomeAssistant):
    """Mark the fake Tado entries unloaded so shutdown does not unload them."""
    yield
    for entry in hass.config_entries.async_entries("tado"):
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


class FakeCoordinator:
    """Stands in for the Tado integration's coordinator."""

    def __init__(self, rate: dict[str, str]) -> None:
        self.rate = rate

    def get_rate_limit(self) -> dict[str, str]:
        return self.rate


class FakeClient:
    def __init__(self, rate: dict[str, str]) -> None:
        self.rate = rate

    def rate_limit_info(self) -> dict[str, str]:
        return self.rate


def add_tado(hass: HomeAssistant, title: str, uid: str, runtime: Any) -> MockConfigEntry:
    entry = MockConfigEntry(domain="tado", title=title, unique_id=uid)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    entry.runtime_data = runtime
    return entry


async def setup_quota(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Tado API quota")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


RATE = {"per-day": "20000", "window-seconds": "86400", "remaining": "19848"}


def test_parse_quota() -> None:
    q = parse_quota(RATE)
    assert q is not None
    assert (q.limit, q.remaining, q.used, q.window_s) == (20000, 19848, 152, 86400)
    assert parse_quota({}) is None
    assert parse_quota(None) is None
    assert parse_quota({"per-day": "x", "remaining": "1"}) is None
    assert parse_quota({"per-day": "100", "remaining": "3"}).window_s is None
    # Remaining above the limit (a policy change mid-window) never goes negative.
    assert parse_quota({"per-day": "100", "remaining": "150"}).used == 0


async def test_sensors_per_home(hass: HomeAssistant) -> None:
    add_tado(hass, "Our Home", "408311", FakeCoordinator(dict(RATE)))
    add_tado(
        hass,
        "Greece",
        "1632431",
        FakeCoordinator({"per-day": "100", "window-seconds": "86400", "remaining": "40"}),
    )
    await setup_quota(hass)

    rem = hass.states.get("sensor.our_home_api_quota_remaining")
    used = hass.states.get("sensor.our_home_api_quota_used")
    assert rem.state == "19848"
    assert used.state == "152"
    assert rem.attributes["unit_of_measurement"] == "calls"
    assert rem.attributes["state_class"] == "measurement"
    assert used.attributes["limit"] == 20000
    assert used.attributes["used_percent"] == 0.8

    assert hass.states.get("sensor.greece_api_quota_remaining").state == "40"
    assert hass.states.get("sensor.greece_api_quota_used").state == "60"

    reg = er.async_get(hass)
    assert reg.async_get("sensor.our_home_api_quota_used").unique_id == "408311_used"


async def test_updates_without_calls(hass: HomeAssistant) -> None:
    coord = FakeCoordinator(dict(RATE))
    add_tado(hass, "Our Home", "408311", coord)
    await setup_quota(hass)
    coord.rate = {**RATE, "remaining": "19700"}
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.our_home_api_quota_used").state == "300"


async def test_client_fallback(hass: HomeAssistant) -> None:
    class Coord:
        def __init__(self) -> None:
            self._tado = FakeClient(dict(RATE))

    add_tado(hass, "Our Home", "408311", Coord())
    await setup_quota(hass)
    assert hass.states.get("sensor.our_home_api_quota_remaining").state == "19848"


@pytest.mark.parametrize(
    "runtime",
    [None, FakeCoordinator({}), object()],
    ids=["no-runtime", "no-response-yet", "unknown-layout"],
)
async def test_unavailable(hass: HomeAssistant, runtime: Any) -> None:
    add_tado(hass, "Our Home", "408311", runtime)
    await setup_quota(hass)
    assert hass.states.get("sensor.our_home_api_quota_remaining").state == "unavailable"


async def test_getter_raises(hass: HomeAssistant) -> None:
    class Boom:
        def get_rate_limit(self) -> dict[str, str]:
            raise RuntimeError("internal change")

    add_tado(hass, "Our Home", "408311", Boom())
    await setup_quota(hass)
    assert hass.states.get("sensor.our_home_api_quota_used").state == "unavailable"


async def test_tado_not_loaded(hass: HomeAssistant) -> None:
    entry = add_tado(hass, "Our Home", "408311", FakeCoordinator(dict(RATE)))
    entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    await setup_quota(hass)
    assert hass.states.get("sensor.our_home_api_quota_used").state == "unavailable"
    entry.mock_state(hass, ConfigEntryState.LOADED)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.our_home_api_quota_used").state == "152"


async def test_unload(hass: HomeAssistant) -> None:
    add_tado(hass, "Our Home", "408311", FakeCoordinator(dict(RATE)))
    entry = await setup_quota(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_tado"

    add_tado(hass, "Our Home", "408311", FakeCoordinator(dict(RATE)))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Tado API quota"

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
