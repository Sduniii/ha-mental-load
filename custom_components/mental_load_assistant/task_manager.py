"""Task management for the Mental Load Assistant."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Callable, Iterable

from homeassistant.components.calendar import CalendarEvent
from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .ai_client import PlannedResponse
from .const import (
    ATTR_MENTAL_LOAD,
    ATTR_PARENT_UID,
    ATTR_SOURCE,
    CALENDAR_SOURCE,
    MANUAL_SOURCE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class StoredTask:
    """Internal representation of a task."""

    item: TodoItem
    parent_key: str
    is_parent: bool


class MentalLoadTaskManager:
    """Handle mental load tasks and synchronize them with Home Assistant."""

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        ai_client,
        title: str,
    ) -> None:
        self._hass = hass
        self._ai_client = ai_client
        self._title = title
        self._tasks: dict[str, StoredTask] = {}
        self._parent_children: dict[str, set[str]] = defaultdict(set)
        self._parent_meta: dict[str, dict[str, str | None]] = {}
        self._event_signatures: dict[str, str] = {}
        self._listeners: list[Callable[[], None]] = []

    @property
    def title(self) -> str:
        """Return the configured title for the todo list."""

        return self._title

    def async_add_listener(self, listener: Callable[[], None]) -> None:
        """Listen for updates."""

        self._listeners.append(listener)

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    def iter_items(self) -> list[TodoItem]:
        """Return items sorted by due date then summary."""

        items = [stored.item for stored in self._tasks.values()]
        items.sort(key=_todo_sort_key)
        return items

    async def async_process_calendar_event(
        self,
        *,
        calendar_id: str,
        parent_key: str,
        event: CalendarEvent,
    ) -> bool:
        """Process a calendar event and update tasks if necessary."""

        signature = _event_signature(event)
        if self._event_signatures.get(parent_key) == signature:
            return False

        plan = await self._ai_client.async_plan_for_calendar_event(
            summary=event.summary,
            description=event.description,
            start=event.start,
            end=event.end,
        )

        self._event_signatures[parent_key] = signature
        self._parent_meta[parent_key] = {
            ATTR_SOURCE: CALENDAR_SOURCE,
            "summary": event.summary,
            ATTR_MENTAL_LOAD: plan.mental_load,
            "notes": plan.summary_notes,
        }
        due_dt = _parse_due(event.start) or _parse_due(event.end)
        self._replace_parent_tasks(parent_key, plan, due_override=due_dt)
        return True

    async def async_create_manual_entry(
        self,
        *,
        summary: str,
        description: str | None,
        due,
        household_context: str | None = None,
    ) -> str:
        """Create a manual task request and return the parent uid."""

        due_dt = _parse_due(due)
        plan = await self._ai_client.async_plan_for_manual_request(
            summary=summary,
            description=description,
            due=due_dt,
            household_context=household_context,
        )
        parent_key = f"manual:{uuid.uuid4()}"
        self._parent_meta[parent_key] = {
            ATTR_SOURCE: MANUAL_SOURCE,
            "summary": summary,
            ATTR_MENTAL_LOAD: plan.mental_load,
            "notes": plan.summary_notes,
        }
        self._replace_parent_tasks(parent_key, plan, due_override=due_dt)
        parent_uid = self._parent_meta[parent_key]["parent_uid"]
        return parent_uid

    def remove_missing_calendar_events(self, valid_parent_keys: Iterable[str]) -> int:
        """Remove tasks for calendar events that are no longer returned."""

        valid = set(valid_parent_keys)
        to_remove = [key for key in self._parent_meta if key.startswith("calendar:") and key not in valid]
        for parent_key in to_remove:
            self._remove_parent(parent_key)
        if to_remove:
            self._notify_listeners()
        return len(to_remove)

    def _replace_parent_tasks(
        self,
        parent_key: str,
        plan: PlannedResponse,
        *,
        due_override: datetime | None = None,
    ) -> None:
        """Replace parent tasks with a new plan."""

        existing = self._parent_children.pop(parent_key, set())
        for uid in existing:
            self._tasks.pop(uid, None)
        parent_uid = str(uuid.uuid4())

        meta = self._parent_meta.get(parent_key, {}).copy()
        parent_summary = meta.get("summary") or "Mental Load Aufgabe"
        notes = plan.summary_notes
        if plan.mental_load:
            notes = (notes or "") + f"\nMental Load Bewertung: {plan.mental_load}"

        parent_item = TodoItem(
            summary=parent_summary,
            uid=parent_uid,
            description=notes,
            status=self._derive_parent_status(plan.tasks),
            due=due_override,
            extra={
                ATTR_SOURCE: meta.get(ATTR_SOURCE),
                ATTR_PARENT_UID: None,
                ATTR_MENTAL_LOAD: plan.mental_load,
            },
        )

        self._tasks[parent_uid] = StoredTask(parent_item, parent_key, True)
        self._parent_children[parent_key] = set()
        self._parent_meta[parent_key]["parent_uid"] = parent_uid

        for planned in plan.tasks:
            child_uid = str(uuid.uuid4())
            child_item = TodoItem(
                summary=f"{parent_summary}: {planned.title}",
                uid=child_uid,
                description=_child_description(planned),
                status=TodoItemStatus.NEEDS_ACTION,
                due=planned.due or due_override,
                extra={
                    ATTR_SOURCE: self._parent_meta[parent_key][ATTR_SOURCE],
                    ATTR_PARENT_UID: parent_uid,
                    ATTR_MENTAL_LOAD: planned.effort,
                },
            )
            self._tasks[child_uid] = StoredTask(child_item, parent_key, False)
            self._parent_children[parent_key].add(child_uid)

        self._notify_listeners()

    def _remove_parent(self, parent_key: str) -> None:
        children = self._parent_children.pop(parent_key, set())
        for uid in children:
            self._tasks.pop(uid, None)
        meta = self._parent_meta.pop(parent_key, None)
        if meta and (parent_uid := meta.get("parent_uid")):
            self._tasks.pop(parent_uid, None)

    async def async_update_item(self, item: TodoItem) -> None:
        """Handle item updates from Home Assistant."""

        stored = self._tasks.get(item.uid)
        if not stored:
            _LOGGER.debug("Unknown task %s", item.uid)
            return

        new_status = item.status or TodoItemStatus.NEEDS_ACTION
        stored.item = replace(stored.item, status=new_status)

        if stored.is_parent:
            # Propagate to children if user marks parent completed
            if new_status == TodoItemStatus.COMPLETED:
                for child_uid in self._parent_children.get(stored.parent_key, set()):
                    child = self._tasks[child_uid]
                    child.item = replace(child.item, status=TodoItemStatus.COMPLETED)
            elif new_status == TodoItemStatus.NEEDS_ACTION:
                for child_uid in self._parent_children.get(stored.parent_key, set()):
                    child = self._tasks[child_uid]
                    if child.item.status == TodoItemStatus.COMPLETED:
                        child.item = replace(child.item, status=TodoItemStatus.NEEDS_ACTION)
        else:
            parent_uid = (stored.item.extra or {}).get(ATTR_PARENT_UID)
            if parent_uid and (parent := self._tasks.get(parent_uid)):
                parent.item = replace(
                    parent.item,
                    status=self._derive_parent_status_from_children(parent_uid),
                )

        self._notify_listeners()

    async def async_delete_item(self, uid: str) -> None:
        """Remove an item from the list."""

        stored = self._tasks.get(uid)
        if not stored:
            return
        if stored.is_parent:
            self._remove_parent(stored.parent_key)
        else:
            self._tasks.pop(uid, None)
            children = self._parent_children.get(stored.parent_key)
            if children and uid in children:
                children.remove(uid)
            parent_uid = (stored.item.extra or {}).get(ATTR_PARENT_UID)
            if parent_uid and (parent := self._tasks.get(parent_uid)):
                parent.item = replace(
                    parent.item,
                    status=self._derive_parent_status_from_children(parent_uid),
                )
        self._notify_listeners()

    def _derive_parent_status(self, tasks) -> TodoItemStatus:
        if not tasks:
            return TodoItemStatus.NEEDS_ACTION
        return TodoItemStatus.IN_PROGRESS

    def _derive_parent_status_from_children(self, parent_uid: str) -> TodoItemStatus:
        parent_task = self._tasks.get(parent_uid)
        if not parent_task:
            return TodoItemStatus.NEEDS_ACTION
        children = [
            self._tasks[uid].item
            for uid in self._parent_children.get(parent_task.parent_key, set())
            if uid in self._tasks
        ]
        if not children:
            return TodoItemStatus.NEEDS_ACTION
        if all(child.status == TodoItemStatus.COMPLETED for child in children):
            return TodoItemStatus.COMPLETED
        if any(child.status == TodoItemStatus.IN_PROGRESS for child in children):
            return TodoItemStatus.IN_PROGRESS
        if any(child.status == TodoItemStatus.COMPLETED for child in children):
            return TodoItemStatus.IN_PROGRESS
        return TodoItemStatus.NEEDS_ACTION


def _child_description(planned) -> str | None:
    parts = []
    if planned.description:
        parts.append(planned.description)
    if planned.effort:
        parts.append(f"Mental Load: {planned.effort}")
    if planned.notes:
        parts.append(planned.notes)
    return "\n".join(parts) if parts else None


def _event_signature(event: CalendarEvent) -> str:
    return "|".join(
        (
            event.summary or "",
            event.description or "",
            _iso_or_empty(event.start),
            _iso_or_empty(event.end),
        )
    )


def _iso_or_empty(value) -> str:
    if isinstance(value, datetime):
        return dt_util.as_utc(value).isoformat()
    return ""


def _parse_due(value) -> datetime | None:
    if isinstance(value, datetime):
        return dt_util.as_utc(value)
    if isinstance(value, date):
        return dt_util.as_utc(dt_util.start_of_local_day(value))
    if isinstance(value, str):
        try:
            return dt_util.as_utc(dt_util.parse_datetime(value))
        except (ValueError, TypeError):
            return None
    return None


def _todo_sort_key(item: TodoItem):
    return (
        item.due or datetime.max.replace(tzinfo=dt_util.UTC),
        item.summary.lower(),
    )
