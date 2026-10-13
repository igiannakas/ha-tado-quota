"""Config flow for Tado API quota: one entry covers every Tado home."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_STATIC_REFRESH_H,
    CONF_TRIM_POLLING,
    DEFAULT_STATIC_REFRESH_H,
    DOMAIN,
    TADO_DOMAIN,
)


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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TadoQuotaOptionsFlow()


class TadoQuotaOptionsFlow(OptionsFlow):
    """Turn the polling trim on or off."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TRIM_POLLING, default=bool(opts.get(CONF_TRIM_POLLING, False))
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_STATIC_REFRESH_H,
                    default=opts.get(CONF_STATIC_REFRESH_H, DEFAULT_STATIC_REFRESH_H),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=24,
                        step=1,
                        unit_of_measurement="h",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
