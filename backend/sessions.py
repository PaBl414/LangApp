"""Shared session lifetime for browser cookies and server-side validation."""
from datetime import datetime, timedelta, timezone

COOKIE_NAME = "langapp_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7


def session_cutoff() -> datetime:
    # Existing SQLite timestamps are UTC without a timezone component.
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=SESSION_MAX_AGE)
