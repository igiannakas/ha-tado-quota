"""Optional: serve Tado data that rarely changes from a cache.

Every refresh of Home Assistant's Tado integration asks Tado for each
device's temperature offset and each zone's default overlay, and fetches the
device list twice.  Those values change only when someone edits them in the
Tado app, yet they make up about two thirds of the calls in a refresh
(e.g. 13 of 19 for a home with 6 devices and 6 zones).

The trim wraps a few methods of the Tado integration's python-tado client
(``entry.runtime_data._tado``) per instance, so Home Assistant's own code is
untouched:

- ``get_device_info(serial, "temperatureOffset")`` and
  ``get_zone_overlay_default(zone)``: cached for ``static_max_age_s``;
- ``get_me()``: the home's id and name, cached the same way;
- ``get_devices()``: cached for a few seconds, so the second call in the same
  refresh is served from the first;
- ``set_temp_offset(serial, ...)`` (the Tado "set temperature offset" action)
  drops that device's cached offset, so the next refresh reads the new one.

Anything unexpected (a renamed attribute, a newer layout) leaves the client
unwrapped: Home Assistant then polls as it always did.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

TEMP_OFFSET_CMD = "temperatureOffset"
DEVICES_MAX_AGE_S = 20.0

_MARK = "_tado_quota_trim"


class _Cache:
    """Thread-safe (python-tado runs in executor threads) value cache."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[tuple, tuple[float, Any]] = {}
        self.saved = 0

    def get(self, key: tuple, max_age_s: float) -> tuple[bool, Any]:
        with self._lock:
            hit = self._values.get(key)
            if hit is not None and time.monotonic() - hit[0] < max_age_s:
                self.saved += 1
                return True, hit[1]
        return False, None

    def put(self, key: tuple, value: Any) -> None:
        with self._lock:
            self._values[key] = (time.monotonic(), value)

    def drop(self, match: Callable[[tuple], bool]) -> None:
        with self._lock:
            for key in [k for k in self._values if match(k)]:
                del self._values[key]


class _Trim:
    """What one wrapped client carries: its cache and the original methods."""

    def __init__(self, originals: dict[str, Callable[..., Any]], static_max_age_s: float):
        self.originals = originals
        self.static_max_age_s = static_max_age_s
        self.cache = _Cache()


WRAPPED = (
    "get_device_info",
    "get_zone_overlay_default",
    "get_me",
    "get_devices",
    "set_temp_offset",
)


def is_wrapped(client: Any) -> bool:
    return isinstance(getattr(client, "__dict__", {}).get(_MARK), _Trim)


def calls_saved(client: Any) -> int | None:
    trim = getattr(client, "__dict__", {}).get(_MARK)
    return trim.cache.saved if isinstance(trim, _Trim) else None


def wrap(client: Any, static_max_age_s: float) -> bool:
    """Wrap *client* in place.  True when it is (now or already) wrapped."""
    if client is None or not hasattr(client, "__dict__"):
        return False
    existing = client.__dict__.get(_MARK)
    if isinstance(existing, _Trim):
        existing.static_max_age_s = static_max_age_s
        return True
    originals: dict[str, Callable[..., Any]] = {}
    for name in WRAPPED:
        try:
            method = getattr(client, name)
        except Exception:  # noqa: BLE001 - an unknown client layout: leave it alone
            method = None
        if not callable(method):
            _LOGGER.warning("Tado client has no %s; polling is left as it is", name)
            return False
        originals[name] = method

    trim = _Trim(originals, static_max_age_s)
    cache = trim.cache

    def get_device_info(device_id, cmd="", *args, **kwargs):
        if cmd != TEMP_OFFSET_CMD or args or kwargs:
            return originals["get_device_info"](device_id, cmd, *args, **kwargs)
        key = ("offset", device_id)
        hit, value = cache.get(key, trim.static_max_age_s)
        if hit:
            return value
        value = originals["get_device_info"](device_id, cmd)
        cache.put(key, value)
        return value

    def get_zone_overlay_default(zone, *args, **kwargs):
        if args or kwargs:
            return originals["get_zone_overlay_default"](zone, *args, **kwargs)
        key = ("overlay_default", zone)
        hit, value = cache.get(key, trim.static_max_age_s)
        if hit:
            return value
        value = originals["get_zone_overlay_default"](zone)
        cache.put(key, value)
        return value

    def get_me(*args, **kwargs):
        if args or kwargs:
            return originals["get_me"](*args, **kwargs)
        hit, value = cache.get(("me",), trim.static_max_age_s)
        if hit:
            return value
        value = originals["get_me"]()
        cache.put(("me",), value)
        return value

    def get_devices(*args, **kwargs):
        if args or kwargs:
            return originals["get_devices"](*args, **kwargs)
        hit, value = cache.get(("devices",), DEVICES_MAX_AGE_S)
        if hit:
            return value
        value = originals["get_devices"]()
        cache.put(("devices",), value)
        return value

    def set_temp_offset(device_id, *args, **kwargs):
        try:
            return originals["set_temp_offset"](device_id, *args, **kwargs)
        finally:
            cache.drop(lambda k: k == ("offset", device_id))

    client.__dict__[_MARK] = trim
    for name, func in (
        ("get_device_info", get_device_info),
        ("get_zone_overlay_default", get_zone_overlay_default),
        ("get_me", get_me),
        ("get_devices", get_devices),
        ("set_temp_offset", set_temp_offset),
    ):
        client.__dict__[name] = func
    return True


def unwrap(client: Any) -> None:
    """Undo :func:`wrap` (no-op for a client that is not wrapped)."""
    if not is_wrapped(client):
        return
    for name in WRAPPED:
        client.__dict__.pop(name, None)
    client.__dict__.pop(_MARK, None)


def client_of(entry: Any) -> Any:
    """The python-tado client of a loaded Tado config entry, or None."""
    return getattr(getattr(entry, "runtime_data", None), "_tado", None)
