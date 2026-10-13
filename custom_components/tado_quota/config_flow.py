"""Config flow for Tado API quota: one entry covers every Tado home."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, TADO_DOMAIN


class TadoQuotaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the integration; there is nothing to configure."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm, then create the single entry."""
        if not self.hass.config_entries.async_entries(TADO_DOMAIN):
            return self.async_abort(reason="no_tado")
        if user_input is not None:
            return self.async_create_entry(title="Tado API quota", data={})
        return self.async_show_form(step_id="user")
