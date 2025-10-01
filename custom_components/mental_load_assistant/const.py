"""Constants for the Mental Load Assistant integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_API_KEY

DOMAIN = "mental_load_assistant"

CONF_CALENDARS = "calendars"
CONF_MODEL = "model"
CONF_POLL_INTERVAL = "poll_interval"
CONF_TIME_HORIZON = "time_horizon"

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_POLL_INTERVAL = timedelta(minutes=15)
DEFAULT_TIME_HORIZON = timedelta(days=14)

DATA_MANAGER = "manager"
DATA_COORDINATOR = "coordinator"
DATA_UNSUB_UPDATE_LISTENER = "update_listener"

SERVICE_ADD_TASK = "add_manual_task"

ATTR_SOURCE = "source"
ATTR_PARENT_UID = "parent_uid"
ATTR_MENTAL_LOAD = "mental_load"

MANUAL_SOURCE = "manual"
CALENDAR_SOURCE = "calendar"

CONF_HOUSEHOLD_CONTEXT = "household_context"

STORAGE_KEY_EVENTS = "events"
