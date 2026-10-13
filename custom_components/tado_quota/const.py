"""Constants for Tado API quota."""

from datetime import timedelta

DOMAIN = "tado_quota"
TADO_DOMAIN = "tado"

# The figures are read from memory (the Tado integration keeps the quota
# header of its last Tado response), so reading them often costs nothing.
SCAN_INTERVAL = timedelta(seconds=60)

# Options: serve the Tado data that rarely changes (device offsets, zone
# overlay defaults, the home) from a cache, re-read every N hours (trim.py).
CONF_TRIM_POLLING = "trim_polling"
CONF_STATIC_REFRESH_H = "static_refresh_h"
DEFAULT_STATIC_REFRESH_H = 6
