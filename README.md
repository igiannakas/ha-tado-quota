# Tado API quota

![version](https://img.shields.io/badge/version-1.0.0-blue)

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
