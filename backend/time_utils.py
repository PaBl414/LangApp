"""UTC storage and explicit calendar-day semantics for learning statistics."""
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

LEARNING_TIMEZONE = os.getenv("LANGAPP_TIMEZONE", "Europe/Warsaw")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def learning_date(when: datetime | None = None) -> date:
    when = when if when is not None else utc_now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(ZoneInfo(LEARNING_TIMEZONE)).date()
