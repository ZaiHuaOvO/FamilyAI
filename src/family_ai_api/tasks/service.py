from datetime import datetime

from family_ai_api.config import Settings
from family_ai_api.tasks.store import Task, TaskStore, parse_due_at
from family_ai_api.tasks.weather import Weather, get_weather

MAX_TITLE_CHARS = 200
MAX_NOTES_CHARS = 2000


class TaskValidationError(Exception):
    pass


def normalize_title(title: str) -> str:
    value = title.strip()
    if not value:
        raise TaskValidationError("title must not be empty")
    if len(title) > MAX_TITLE_CHARS:
        raise TaskValidationError("title is too long")
    return value


def normalize_notes(notes: str) -> str:
    if len(notes) > MAX_NOTES_CHARS:
        raise TaskValidationError("notes are too long")
    return notes


def normalize_due_at(due_at: str | None) -> str | None:
    if due_at is None or due_at == "":
        return None
    try:
        parse_due_at(due_at)
    except ValueError as exc:
        raise TaskValidationError("due_at must be ISO 8601") from exc
    return due_at


async def build_briefing(settings: Settings) -> dict:
    now = datetime.now().astimezone()
    store = TaskStore(settings.tasks_db_path)
    try:
        open_tasks = store.list(status="open", now=now)
    finally:
        store.close()

    today: list[Task] = []
    overdue: list[Task] = []
    for task in open_tasks:
        try:
            due_at = parse_due_at(task.due_at)
        except ValueError:
            continue
        if due_at is None:
            continue
        if due_at.date() == now.date():
            today.append(task)
        elif due_at.date() < now.date():
            overdue.append(task)

    weather: Weather | None = await get_weather(settings)

    return {
        "date": now.date().isoformat(),
        "counts": {
            "today": len(today),
            "overdue": len(overdue),
            "open": len(open_tasks),
        },
        "tasks": {"today": today, "overdue": overdue},
        "weather": weather,
        "weather_configured": (
            settings.weather_latitude is not None
            and settings.weather_longitude is not None
        ),
    }
