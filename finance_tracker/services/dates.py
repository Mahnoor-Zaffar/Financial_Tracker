from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from finance_tracker.extensions import db
from finance_tracker.models import User

DEFAULT_TIMEZONE = "UTC"


def utc_now() -> datetime:
    return datetime.now(UTC)


def user_local_today(timezone_name: str | None, now: datetime | None = None) -> date:
    try:
        timezone = ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo(DEFAULT_TIMEZONE)

    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(timezone).date()


def user_local_today_for_user(user_id: int, now: datetime | None = None) -> date:
    timezone_name = db.session.query(User.timezone).filter(User.id == user_id).scalar()
    return user_local_today(timezone_name, now=now)
