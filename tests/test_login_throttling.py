from __future__ import annotations

from datetime import datetime, timedelta, timezone

import finance_tracker.services.auth_throttling as auth_throttling
from finance_tracker.extensions import db
from finance_tracker.models import LoginThrottle, User


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


def test_login_throttling_ignores_spoofed_forwarded_ip_by_default(app, client):
    app.config.update(
        AUTH_LOGIN_ACCOUNT_LIMIT=99,
        AUTH_LOGIN_IP_LIMIT=2,
        AUTH_LOGIN_WINDOW_SECONDS=300,
        AUTH_LOGIN_COOLDOWN_SECONDS=300,
    )
    _create_user(app)

    first = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Wrong1234", "submit": "Sign in"},
        headers={"X-Forwarded-For": "198.51.100.10"},
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        follow_redirects=False,
    )
    second = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Wrong1234", "submit": "Sign in"},
        headers={"X-Forwarded-For": "198.51.100.11"},
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        follow_redirects=False,
    )

    assert first.status_code == 200
    assert second.status_code == 429

    with app.app_context():
        ip_records = LoginThrottle.query.filter_by(scope="ip").all()
        assert [record.key for record in ip_records] == ["127.0.0.1"]


def test_login_throttling_uses_forwarded_ip_from_trusted_proxy(app, client):
    app.config.update(
        AUTH_LOGIN_ACCOUNT_LIMIT=99,
        AUTH_LOGIN_IP_LIMIT=2,
        AUTH_LOGIN_WINDOW_SECONDS=300,
        AUTH_LOGIN_COOLDOWN_SECONDS=300,
        TRUSTED_PROXY_CIDRS=("127.0.0.1/32",),
    )
    _create_user(app)

    first = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Wrong1234", "submit": "Sign in"},
        headers={"X-Forwarded-For": "198.51.100.10"},
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        follow_redirects=False,
    )
    second = client.post(
        "/auth/login",
        data={"email": "throttle@example.com", "password": "Wrong1234", "submit": "Sign in"},
        headers={"X-Forwarded-For": "198.51.100.11"},
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        follow_redirects=False,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    with app.app_context():
        ip_records = LoginThrottle.query.filter_by(scope="ip").order_by(LoginThrottle.key).all()
        assert [record.key for record in ip_records] == ["198.51.100.10", "198.51.100.11"]
