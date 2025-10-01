"""Client responsible for AI based task planning."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

from homeassistant.util import dt as dt_util

from .const import PROVIDER_GEMINI, PROVIDER_OPENAI

_LOGGER = logging.getLogger(__name__)


class MentalLoadAIError(Exception):
    """Raised when the AI backend cannot be reached or parsed."""


@dataclass
class PlannedTask:
    """Task as returned by the AI model."""

    title: str
    description: str | None = None
    due: datetime | None = None
    effort: str | None = None
    category: str | None = None
    notes: str | None = None


@dataclass
class PlannedResponse:
    """Full response from the AI model."""

    tasks: list[PlannedTask]
    mental_load: str | None
    summary_notes: str | None


class MentalLoadAI:
    """Wrapper around a chat completion API with graceful degradation."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str | None,
        model: str,
        provider: str = PROVIDER_OPENAI,
        base_url: str | None = None,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._model = model
        self._provider = provider
        if base_url:
            self._base_url = base_url.rstrip("/")
        elif provider == PROVIDER_GEMINI:
            self._base_url = "https://generativelanguage.googleapis.com/v1beta"
        else:
            self._base_url = "https://api.openai.com/v1"

    async def async_plan_for_calendar_event(
        self,
        *,
        summary: str,
        description: str | None,
        start: datetime | None,
        end: datetime | None,
        household_context: str | None = None,
    ) -> PlannedResponse:
        """Create a task plan for a calendar event."""

        payload: dict[str, Any] = {
            "type": "calendar_event",
            "summary": summary,
            "description": description,
            "start": dt_util.as_utc(start).isoformat() if start else None,
            "end": dt_util.as_utc(end).isoformat() if end else None,
            "household_context": household_context,
        }
        return await self._async_generate_plan(payload)

    async def async_plan_for_manual_request(
        self,
        *,
        summary: str,
        description: str | None,
        due: datetime | None,
        household_context: str | None = None,
    ) -> PlannedResponse:
        """Create a task plan for a free form manual request."""

        payload: dict[str, Any] = {
            "type": "manual_task",
            "summary": summary,
            "description": description,
            "due": dt_util.as_utc(due).isoformat() if due else None,
            "household_context": household_context,
        }
        return await self._async_generate_plan(payload)

    async def _async_generate_plan(self, payload: dict[str, Any]) -> PlannedResponse:
        """Call the AI backend or use a deterministic fallback."""

        if not self._api_key:
            _LOGGER.debug("No API key configured, using heuristic plan")
            return self._fallback_plan(payload)

        try:
            if self._provider == PROVIDER_GEMINI:
                return await self._async_generate_with_gemini(payload)
            return await self._async_generate_with_openai(payload)
        except (aiohttp.ClientError, KeyError, json.JSONDecodeError, MentalLoadAIError) as err:
            _LOGGER.warning("Falling back to heuristic plan due to AI error: %s", err)
            return self._fallback_plan(payload)

    async def _async_generate_with_openai(self, payload: dict[str, Any]) -> PlannedResponse:
        """Call an OpenAI compatible chat completions endpoint."""

        response = await self._session.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=60),
            json={
                "model": self._model,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "mental_load_task_plan",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "mental_load": {"type": "string"},
                                "summary_notes": {"type": "string"},
                                "tasks": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "description": {"type": "string"},
                                            "due": {"type": "string"},
                                            "effort": {"type": "string"},
                                            "category": {"type": "string"},
                                            "notes": {"type": "string"},
                                        },
                                        "required": ["title"],
                                    },
                                },
                            },
                            "required": ["tasks"],
                        },
                    },
                },
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You break down household calendar events into actionable tasks. "
                            "Keep tasks short and concrete."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"request": payload}),
                    },
                ],
                "temperature": 0.2,
            },
        )
        data = await response.json()
        if response.status >= 400:
            raise MentalLoadAIError(data)
        content = data["choices"][0]["message"]["content"]
        return self._parse_response(content)

    async def _async_generate_with_gemini(self, payload: dict[str, Any]) -> PlannedResponse:
        """Call the Gemini generateContent endpoint."""

        response = await self._session.post(
            f"{self._base_url}/models/{self._model}:generateContent",
            params={"key": self._api_key},
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=60),
            json={
                "system_instruction": {
                    "parts": [
                        {
                            "text": (
                                "You break down household tasks into actionable subtasks and provide "
                                "concise mental load context. Always respond with valid JSON matching "
                                "the schema: {\"tasks\": [ {\"title\": str, \"description\": str?, \"due\": str?, "
                                "\"effort\": str?, \"category\": str?, \"notes\": str? } ], \"mental_load\": str?, "
                                "\"summary_notes\": str?}."
                            )
                        }
                    ]
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": json.dumps({"request": payload}),
                            }
                        ],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                },
            },
        )
        data = await response.json()
        if response.status >= 400:
            raise MentalLoadAIError(data)

        candidates = data.get("candidates") or []
        if not candidates:
            raise MentalLoadAIError("No candidates in Gemini response")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_payload: str | None = None
        for part in parts:
            if "text" in part:
                text_payload = part["text"]
                break

        if not text_payload:
            raise MentalLoadAIError("Gemini response missing text content")

        return self._parse_response(text_payload)

    def _parse_response(self, content: str) -> PlannedResponse:
        """Parse a JSON response from the chat API."""

        parsed = json.loads(content)
        tasks = [self._task_from_dict(item) for item in parsed.get("tasks", [])]
        return PlannedResponse(
            tasks=tasks,
            mental_load=parsed.get("mental_load"),
            summary_notes=parsed.get("summary_notes"),
        )

    def _task_from_dict(self, item: dict[str, Any]) -> PlannedTask:
        """Convert a dictionary to a PlannedTask instance."""

        due_value = item.get("due")
        due_dt: datetime | None = None
        if isinstance(due_value, str):
            try:
                due_dt = dt_util.parse_datetime(due_value)
            except (ValueError, TypeError):
                due_dt = None

        return PlannedTask(
            title=item.get("title", "Unnamed task"),
            description=item.get("description"),
            due=dt_util.as_utc(due_dt) if due_dt else None,
            effort=item.get("effort"),
            category=item.get("category"),
            notes=item.get("notes"),
        )

    def _fallback_plan(self, payload: dict[str, Any]) -> PlannedResponse:
        """Provide a deterministic fallback plan when AI is unavailable."""

        summary = payload.get("summary") or "Aufgabe"
        description = payload.get("description")
        base_due = _parse_dt(payload.get("due")) or _parse_dt(payload.get("end"))

        tasks = _default_breakdown(summary, description)

        planned_tasks = [
            PlannedTask(
                title=title,
                description=details,
                due=base_due,
            )
            for title, details in tasks
        ]

        return PlannedResponse(
            tasks=planned_tasks,
            mental_load="unknown",
            summary_notes="Automatisch erzeugter Plan (Fallback)",
        )


def _default_breakdown(summary: str, description: str | None) -> list[tuple[str, str | None]]:
    """Simple heuristic breakdown for offline mode."""

    components: list[tuple[str, str | None]] = []
    normalized = summary.lower()

    if any(keyword in normalized for keyword in ("repar", "fix", "repair")):
        components.extend(
            [
                ("Problem verstehen und Dokumentation prüfen", description),
                ("Benötigte Teile oder Service organisieren", None),
                ("Reparatur durchführen und testen", None),
            ]
        )
    elif any(keyword in normalized for keyword in ("geburtstag", "party", "feier")):
        components.extend(
            [
                ("Gästeliste und Einladungen", description),
                ("Einkaufsliste und Dekoration planen", None),
                ("Vorbereitung am Veranstaltungstag", None),
            ]
        )
    else:
        components.extend(
            [
                ("Aufgabe planen", description),
                ("Ressourcen beschaffen", None),
                ("Durchführung abschließen", None),
            ]
        )

    return components


def _parse_dt(value: Any) -> datetime | None:
    """Parse a datetime value."""

    if isinstance(value, datetime):
        return dt_util.as_utc(value)
    if isinstance(value, str):
        try:
            return dt_util.as_utc(dt_util.parse_datetime(value))
        except (ValueError, TypeError):
            return None
    return None
