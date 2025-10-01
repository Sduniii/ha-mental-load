"""Config flow for the Mental Load Assistant."""

from __future__ import annotations

import voluptuous as vol

from datetime import timedelta

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CALENDARS,
    CONF_MODEL,
    CONF_POLL_INTERVAL,
    CONF_TIME_HORIZON,
    DEFAULT_MODEL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TIME_HORIZON,
    DOMAIN,
)


def _duration_to_selector(value: timedelta | dict[str, int]) -> dict[str, int]:
    if isinstance(value, dict):
        return value
    total_seconds = int(value.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return {
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
    }


def _selector_to_timedelta(value: dict[str, int] | timedelta) -> timedelta:
    if isinstance(value, timedelta):
        return value
    return timedelta(
        days=value.get("days", 0),
        hours=value.get("hours", 0),
        minutes=value.get("minutes", 0),
        seconds=value.get("seconds", 0),
    )


class MentalLoadConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            calendars = list(self.hass.states.async_entity_ids("calendar"))
            data_schema = vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Mental Load"): str,
                    vol.Optional(CONF_API_KEY): str,
                    vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): str,
                    vol.Required(CONF_CALENDARS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=calendars,
                            multiple=True,
                            custom_value=False,
                        )
                    ),
                }
            )
            return self.async_show_form(step_id="user", data_schema=data_schema)

        return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

    async def async_step_import(self, user_input: dict) -> FlowResult:
        return await self.async_step_user(user_input)

    async def async_step_options(self) -> FlowResult:
        return await self.async_step_user()


class MentalLoadOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for an existing entry."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            data_schema = vol.Schema(
                {
                    vol.Optional(CONF_MODEL, default=self._entry.options.get(CONF_MODEL, self._entry.data.get(CONF_MODEL, DEFAULT_MODEL))): str,
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=_duration_to_selector(
                            self._entry.options.get(
                                CONF_POLL_INTERVAL,
                                self._entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                            )
                        ),
                    ): selector.DurationSelector(),
                    vol.Optional(
                        CONF_TIME_HORIZON,
                        default=_duration_to_selector(
                            self._entry.options.get(
                                CONF_TIME_HORIZON,
                                self._entry.data.get(CONF_TIME_HORIZON, DEFAULT_TIME_HORIZON),
                            )
                        ),
                    ): selector.DurationSelector(),
                }
            )
            return self.async_show_form(step_id="init", data_schema=data_schema)

        data = dict(user_input)
        for key in (CONF_POLL_INTERVAL, CONF_TIME_HORIZON):
            if key in data and isinstance(data[key], dict):
                data[key] = _selector_to_timedelta(data[key])

        return self.async_create_entry(title="Options", data=data)


async def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> MentalLoadOptionsFlowHandler:
    return MentalLoadOptionsFlowHandler(config_entry)
