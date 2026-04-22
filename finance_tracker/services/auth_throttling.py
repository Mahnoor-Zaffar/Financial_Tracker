from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from flask import current_app

from finance_tracker.extensions import db
from finance_tracker.models import LoginThrottle


@dataclass(frozen=True)
class ThrottleDecision:
    blocked: bool
    retry_after_seconds: int | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalized_window_start(now: datetime, window_seconds: int) -> datetime:
    return now if window_seconds <= 0 else now - timedelta(seconds=window_seconds)


def _throttle_targets(client_ip: str, email: str) -> list[tuple[str, str, int]]:
    return [
        ("ip", client_ip, int(current_app.config.get("AUTH_LOGIN_IP_LIMIT", 10))),
        ("account", email, int(current_app.config.get("AUTH_LOGIN_ACCOUNT_LIMIT", 5))),
    ]


def _window_seconds() -> int:
    return int(current_app.config.get("AUTH_LOGIN_WINDOW_SECONDS", 900))


def _cooldown_seconds() -> int:
    return int(current_app.config.get("AUTH_LOGIN_COOLDOWN_SECONDS", 900))


def _prune_or_refresh(record: LoginThrottle, now: datetime) -> None:
    window_start = _normalized_window_start(now, _window_seconds())
    blocked_until = _as_utc(record.blocked_until)
    first_failed_at = _as_utc(record.first_failed_at)
    if blocked_until and blocked_until <= now:
        db.session.delete(record)
        return
    if first_failed_at and first_failed_at < window_start and not blocked_until:
        db.session.delete(record)


def check_login_throttle(client_ip: str, email: str) -> ThrottleDecision:
    now = _utcnow()
    retry_after_seconds = None

    for scope, key, _limit in _throttle_targets(client_ip, email):
        record = LoginThrottle.query.filter_by(scope=scope, key=key).first()
        if record is None:
            continue
        _prune_or_refresh(record, now)
        blocked_until = _as_utc(record.blocked_until)
        if blocked_until and blocked_until > now:
            remaining = int((blocked_until - now).total_seconds())
            retry_after_seconds = max(remaining, retry_after_seconds or 0)

    if retry_after_seconds is None:
        return ThrottleDecision(blocked=False)
    return ThrottleDecision(blocked=True, retry_after_seconds=retry_after_seconds)


def record_failed_login(client_ip: str, email: str) -> ThrottleDecision:
    now = _utcnow()
    window_start = _normalized_window_start(now, _window_seconds())
    cooldown_until = now + timedelta(seconds=_cooldown_seconds())
    retry_after_seconds = None

    for scope, key, limit in _throttle_targets(client_ip, email):
        record = LoginThrottle.query.filter_by(scope=scope, key=key).first()
        if record is None:
            record = LoginThrottle(scope=scope, key=key, failures=1, first_failed_at=now)
            db.session.add(record)
            continue

        _prune_or_refresh(record, now)
        if record in db.session.deleted:
            record = LoginThrottle(scope=scope, key=key, failures=1, first_failed_at=now)
            db.session.add(record)
            continue

        blocked_until = _as_utc(record.blocked_until)
        first_failed_at = _as_utc(record.first_failed_at)
        if blocked_until and blocked_until > now:
            remaining = int((blocked_until - now).total_seconds())
            retry_after_seconds = max(remaining, retry_after_seconds or 0)
            continue

        if first_failed_at and first_failed_at < window_start:
            record.failures = 1
            record.first_failed_at = now
            record.blocked_until = None
        else:
            record.failures += 1
            if record.failures >= limit:
                record.blocked_until = cooldown_until
                remaining = int((cooldown_until - now).total_seconds())
                retry_after_seconds = max(remaining, retry_after_seconds or 0)

    return ThrottleDecision(blocked=retry_after_seconds is not None, retry_after_seconds=retry_after_seconds)


def reset_login_throttle(client_ip: str, email: str) -> None:
    for scope, key, _limit in _throttle_targets(client_ip, email):
        LoginThrottle.query.filter_by(scope=scope, key=key).delete()
