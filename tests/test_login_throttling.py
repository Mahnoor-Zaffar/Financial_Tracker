from __future__ import annotations

from datetime import datetime, timedelta, timezone

import finance_tracker.services.auth_throttling as auth_throttling
from finance_tracker.extensions import db
from finance_tracker.models import User


def _create_user(app, email: str = "throttle@example.com", password: str = "Pass12345") -> None:
    with app.app_context():
        user = User(email=email, full_name="Throttle User", currency_code="USD", timezone="UTC")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()


def _configure_throttling(app) -> None:
    app.config.update(
        AUTH_LOGIN_ACCOUNT_LIMIT=3,
        AUTH_LOGIN_IP_LIMIT=4,
        AUTH_LOGIN_WINDOW_SECONDS=300,
        AUTH_LOGIN_COOLDOWN_SECONDS=300,
    )


def test_repeated_failed_login_attempts_trigger_throttling(app, client):
    _configure_throttling(app)
    _create_user(app)

    for _attempt in range(2):
        response = client.post(
            "/auth/login",
            data={"email": "throttle@example.com", "password": "Wrong1234", "submit": "Sign in"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Invalid credentials." in response.get_data(as_text=True)

    throttled = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Wrong1234", "submit": "Sign in"},
        follow_redirects=False,
    )

    assert throttled.status_code == 429
    assert "Too many login attempts. Try again later." in throttled.get_data(as_text=True)


def test_valid_login_works_when_under_threshold(app, client):
    _configure_throttling(app)
    _create_user(app)

    failed = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Wrong1234", "submit": "Sign in"},
        follow_redirects=False,
    )
    assert failed.status_code == 200

    success = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Pass12345", "submit": "Sign in"},
        follow_redirects=False,
    )

    assert success.status_code == 302
    assert success.headers["Location"].endswith("/dashboard")


def test_valid_login_works_after_cooldown(app, client, monkeypatch):
    _configure_throttling(app)
    _create_user(app)
    current_time = {"value": datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)}

    monkeypatch.setattr(auth_throttling, "_utcnow", lambda: current_time["value"])

    for _attempt in range(3):
        client.post(
            "/auth/login",
            data={"email": "throttle@example.com", "password": "Wrong1234", "submit": "Sign in"},
            follow_redirects=False,
        )

    blocked = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Pass12345", "submit": "Sign in"},
        follow_redirects=False,
    )
    assert blocked.status_code == 429

    current_time["value"] = current_time["value"] + timedelta(seconds=301)

    recovered = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Pass12345", "submit": "Sign in"},
        follow_redirects=False,
    )

    assert recovered.status_code == 302
    assert recovered.headers["Location"].endswith("/dashboard")
