"""Data update coordinator for calendar sync."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Iterable

from homeassistant.components.calendar import CalendarEvent, async_get_events
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .task_manager import MentalLoadTaskManager

_LOGGER = logging.getLogger(__name__)


class MentalLoadCoordinator(DataUpdateCoordinator[None]):
    """Coordinate updates between calendars and task manager."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        calendars: Iterable[str],
        manager: MentalLoadTaskManager,
        poll_interval: timedelta,
        time_horizon: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Mental Load Coordinator",
            update_interval=poll_interval,
        )
        self._calendars = list(calendars)
        self._manager = manager
        self._time_horizon = time_horizon

    def update_parameters(
        self,
        *,
        calendars: Iterable[str] | None = None,
        poll_interval: timedelta | None = None,
        time_horizon: timedelta | None = None,
    ) -> None:
        """Update runtime parameters."""

        if calendars is not None:
            self._calendars = list(calendars)
        if poll_interval is not None:
            self.update_interval = poll_interval
        if time_horizon is not None:
            self._time_horizon = time_horizon

    async def _async_update_data(self) -> None:
        """Fetch events and update tasks."""
        if not self._calendars:
            return

        now = dt_util.utcnow()
        start = now - timedelta(days=1)
        end = now + self._time_horizon
        observed_parents: set[str] = set()

        for calendar_id in self._calendars:
            try:
                events = await async_get_events(self.hass, calendar_id, start, end)
            except Exception as err:  # noqa: BLE001 - propagate into UpdateFailed
                raise UpdateFailed(f"Failed to read calendar {calendar_id}") from err

            for event in events:
                parent_key = self._make_parent_key(calendar_id, event)
                observed_parents.add(parent_key)
                updated = await self._manager.async_process_calendar_event(
                    calendar_id=calendar_id,
                    parent_key=parent_key,
                    event=event,
                )
                if updated:
                    _LOGGER.debug("Updated tasks for %s", parent_key)

        removed = self._manager.remove_missing_calendar_events(observed_parents)
        if removed:
            _LOGGER.debug("Removed %s obsolete calendar derived tasks", removed)

    def _make_parent_key(self, calendar_id: str, event: CalendarEvent) -> str:
        """Generate a stable parent key for an event."""
        uid = event.uid or f"{event.start}_{event.end}_{event.summary}"
        return f"calendar:{calendar_id}:{uid}"
