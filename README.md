# Tado API quota

![version](https://img.shields.io/badge/version-1.1.0-blue)

Sensors for how much of your daily Tado API quota is left and used, one pair per Tado home in Home Assistant.

Tado limits API calls per account per day (100 without a subscription, 20,000 with Auto-Assist). It reports the quota on every API response. Home Assistant's Tado integration keeps that figure and uses it to pace its polling, but it doesn't show it as an entity. This integration reads it from memory, so it **makes no Tado API calls of its own**.

## Sensors

For each Tado home (for example "Our Home") you get a device, "Our Home API quota", with two sensors:

| Entity | State | Attributes |
|---|---|---|
| `sensor.our_home_api_quota_remaining` | Calls left in the current window | `limit`, `window_seconds`, `used_percent` |
| `sensor.our_home_api_quota_used` | Calls used: limit − remaining | same |

Both sensors have the `measurement` state class, so they keep long-term statistics. "Used" climbs through the day and drops back when Tado refills the quota. The quota belongs to the Tado account, so it counts every client: Home Assistant, the Tado app and anything else using the API.

The sensors read the figure every 60 seconds and change whenever the Tado integration talks to Tado. They're unavailable until that integration has had its first response, or while it isn't loaded.

## Optional: trim Tado polling

Every refresh of Home Assistant's Tado integration also asks Tado for each device's temperature offset and each zone's default overlay, and fetches the device list twice. Those values change only when you edit them in the Tado app, yet they're most of each refresh: for a home with 6 temperature-measuring devices and 6 zones, a refresh costs **19 calls**, and only 5 of them fetch data that changes (the device list, zone states, weather, home state and the zone list).

Turn on **Trim Tado polling** under *Configure*, and the integration caches the static data, so the same home's refresh costs **5 calls**. Every command you send through Tado is followed by a refresh, so commands get cheaper too (about 6 calls instead of 20).

- Offsets, overlay defaults and the home's details are re-read every 6 hours by default (1–24 h, *Re-read static data every*). Setting an offset with Tado's *Set temperature offset* action is picked up at the next refresh.
- The device list is fetched once per refresh instead of twice, so battery and connection states stay as fresh as before.
- It works by wrapping the Tado integration's python-tado client in memory; Home Assistant's own code is untouched. Turning the option off, or removing this integration, restores the client. If a Home Assistant update changes the client so the trim doesn't fit any more, it stays off and polling is as before (there's a warning in the log).
- The quota sensors' `polling_trimmed` and `calls_saved` attributes show that it's on and how many calls it has saved since the Tado integration last loaded.

## Install

1. In HACS, add this repository as a custom repository of type *Integration*, then download **Tado API quota**.
2. Restart Home Assistant.
3. Go to *Settings → Devices & services → Add integration* and pick **Tado API quota**. There's nothing to configure. One entry covers every Tado home.

If you add a Tado home later, reload this integration to get sensors for it.

## Requirements

- Home Assistant 2026.5 or later, where the Tado integration keeps the quota.
- The core Tado integration, set up.

## How it works

The Tado integration's coordinator exposes `get_rate_limit()`, which returns what python-tado parsed from Tado's `RateLimit-Policy` and `RateLimit` headers. If a future Home Assistant version renames it, the sensors go unavailable rather than causing errors.

## Development

```bash
uv venv -p 3.13 .venv && uv pip install -p .venv/bin/python pytest-homeassistant-custom-component
.venv/bin/python -m pytest -q
uvx ruff check . && uvx ruff format --check .
```

## License

MIT
