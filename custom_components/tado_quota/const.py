"""Constants for Tado API quota."""

from datetime import timedelta

DOMAIN = "tado_quota"
TADO_DOMAIN = "tado"

# The figures are read from memory (the Tado integration keeps the quota
# header of its last Tado response), so reading them often costs nothing.
SCAN_INTERVAL = timedelta(seconds=60)
