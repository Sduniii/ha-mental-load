"""Todo platform for the Mental Load Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_MANAGER, DOMAIN
from .task_manager import MentalLoadTaskManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the todo entity."""

    data = hass.data[DOMAIN][entry.entry_id]
    manager: MentalLoadTaskManager = data[DATA_MANAGER]

    async_add_entities([MentalLoadTodoList(manager, entry)])


class MentalLoadTodoList(TodoListEntity):
    """Representation of the mental load todo list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO
        | TodoListEntityFeature.UPDATE_TODO
        | TodoListEntityFeature.DELETE_TODO
    )

    def __init__(self, manager: MentalLoadTaskManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_unique_id = entry.entry_id
        self._attr_name = f"{manager.title} Aufgaben"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._manager.async_add_listener(self.async_write_ha_state)

    async def async_get_items(self) -> list[TodoItem]:
        return self._manager.iter_items()

    async def async_create_item(self, item: TodoItem) -> str:
        parent_uid = await self._manager.async_create_manual_entry(
            summary=item.summary,
            description=item.description,
            due=item.due,
            household_context=None,
        )
        return parent_uid

    async def async_update_item(self, item: TodoItem) -> None:
        await self._manager.async_update_item(item)

    async def async_delete_item(self, uid: str) -> None:
        await self._manager.async_delete_item(uid)

    @property
    def icon(self) -> str | None:
        return "mdi:clipboard-text-multiple"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {}
