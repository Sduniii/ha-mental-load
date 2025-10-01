"""Mental Load Assistant integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import aiohttp_client, config_validation as cv

from .ai_client import MentalLoadAI
from .const import (
    CONF_CALENDARS,
    CONF_HOUSEHOLD_CONTEXT,
    CONF_MODEL,
    CONF_POLL_INTERVAL,
    CONF_PROVIDER,
    CONF_TIME_HORIZON,
    DATA_COORDINATOR,
    DATA_MANAGER,
    DATA_UNSUB_UPDATE_LISTENER,
    DEFAULT_MODEL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PROVIDER,
    DEFAULT_TIME_HORIZON,
    DOMAIN,
    SERVICE_ADD_TASK,
    SERVICE_MARK_IN_PROGRESS,
)
from .coordinator import MentalLoadCoordinator
from .task_manager import MentalLoadTaskManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.TODO]


def _get_entry_option(entry: ConfigEntry, option: str, default: Any) -> Any:
    """Return option value from entry with fallback to default."""
    if option in entry.options:
        return entry.options[option]
    return entry.data.get(option, default)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = aiohttp_client.async_get_clientsession(hass)

    model = _get_entry_option(entry, CONF_MODEL, DEFAULT_MODEL)
    provider = _get_entry_option(entry, CONF_PROVIDER, DEFAULT_PROVIDER)
    poll_interval = _get_entry_option(entry, CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    time_horizon = _get_entry_option(entry, CONF_TIME_HORIZON, DEFAULT_TIME_HORIZON)

    ai_client = MentalLoadAI(
        session=session,
        api_key=entry.data.get(CONF_API_KEY),
        model=model,
        provider=provider,
    )

    manager = MentalLoadTaskManager(
        hass=hass,
        ai_client=ai_client,
        title=entry.data.get(CONF_NAME, "Mental Load"),
    )

    coordinator = MentalLoadCoordinator(
        hass=hass,
        calendars=entry.data.get(CONF_CALENDARS, []),
        manager=manager,
        poll_interval=poll_interval,
        time_horizon=time_horizon,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_MANAGER: manager,
        DATA_COORDINATOR: coordinator,
        DATA_UNSUB_UPDATE_LISTENER: entry.add_update_listener(async_update_entry),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    unsub: Callable[[], None] | None = data.get(DATA_UNSUB_UPDATE_LISTENER)
    if unsub is not None:
        unsub()

    if not hass.data[DOMAIN]:
        _unregister_services(hass)

    return unload_ok


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    data = hass.data[DOMAIN][entry.entry_id]

    coordinator: MentalLoadCoordinator = data[DATA_COORDINATOR]
    coordinator.update_parameters(
        calendars=entry.data.get(CONF_CALENDARS, []),
        poll_interval=_get_entry_option(entry, CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        time_horizon=_get_entry_option(entry, CONF_TIME_HORIZON, DEFAULT_TIME_HORIZON),
    )
    await coordinator.async_request_refresh()


def _register_services(hass: HomeAssistant) -> None:
    """Register integration level services."""

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_TASK):
        service_schema = vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Required("summary"): cv.string,
                vol.Optional("description"): cv.string,
                vol.Optional("due"): vol.Any(cv.datetime, cv.string),
                vol.Optional(CONF_HOUSEHOLD_CONTEXT): cv.string,
            }
        )

        async def _async_handle_add_task(call: ServiceCall) -> None:
            entry_id = call.data.get("entry_id")
            manager: MentalLoadTaskManager | None = None

            if entry_id:
                entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
                if entry_data:
                    manager = entry_data.get(DATA_MANAGER)
            else:
                # Pick the first available manager if only one integration is configured
                if len(hass.data.get(DOMAIN, {})) == 1:
                    manager = next(iter(hass.data[DOMAIN].values())).get(DATA_MANAGER)

            if not manager:
                _LOGGER.error(
                    "No Mental Load integration instance available for service call"
                )
                return

            await manager.async_create_manual_entry(
                summary=call.data["summary"],
                description=call.data.get("description"),
                due=call.data.get("due"),
                household_context=call.data.get(CONF_HOUSEHOLD_CONTEXT),
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_TASK,
            _async_handle_add_task,
            schema=service_schema,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_MARK_IN_PROGRESS):
        progress_schema = vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Required("uid"): cv.string,
            }
        )

        async def _async_handle_mark_in_progress(call: ServiceCall) -> None:
            entry_id = call.data.get("entry_id")
            manager: MentalLoadTaskManager | None = None

            if entry_id:
                entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
                if entry_data:
                    manager = entry_data.get(DATA_MANAGER)
            else:
                if len(hass.data.get(DOMAIN, {})) == 1:
                    manager = next(iter(hass.data[DOMAIN].values())).get(DATA_MANAGER)

            if not manager:
                _LOGGER.error(
                    "No Mental Load integration instance available for service call"
                )
                return

            await manager.async_mark_in_progress(call.data["uid"])

        hass.services.async_register(
            DOMAIN,
            SERVICE_MARK_IN_PROGRESS,
            _async_handle_mark_in_progress,
            schema=progress_schema,
        )


def _unregister_services(hass: HomeAssistant) -> None:
    """Remove registered services if no instances remain."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_TASK):
        hass.services.async_remove(DOMAIN, SERVICE_ADD_TASK)
    if hass.services.has_service(DOMAIN, SERVICE_MARK_IN_PROGRESS):
        hass.services.async_remove(DOMAIN, SERVICE_MARK_IN_PROGRESS)
