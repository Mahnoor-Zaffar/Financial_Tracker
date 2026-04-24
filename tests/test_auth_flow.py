from __future__ import annotations

from finance_tracker.extensions import db
from finance_tracker.models import User


def _field_error_text(response, field_id: str) -> str:
    html = response.get_data(as_text=True)
    marker = f'id="{field_id}-error"'
    idx = html.find(marker)
    assert idx != -1, f"Could not find field error for {field_id!r}"
    start = html.rfind('<p class="field-error"', 0, idx)
    end = html.find("</p>", idx)
    assert start != -1 and end != -1, f"Could not parse field error for {field_id!r}"
    message_start = html.find(">", start, end) + 1
    return html[message_start:end]


def test_register_login_logout_flow(app, client):
    register_response = client.post(
        "/auth/register",
        data={
            "full_name": "QA User",
            "email": "qa-user@example.com",
            "password": "Pass12345",
            "confirm_password": "Pass12345",
            "submit": "Create account",
        },
        follow_redirects=False,
    )
    assert register_response.status_code == 302
    assert register_response.headers["Location"].endswith("/dashboard")

    with app.app_context():
        created = User.query.filter_by(email="qa-user@example.com").first()
        assert created is not None
        assert created.password_hash != "Pass12345"
        assert created.check_password("Pass12345")

    logout_response = client.post("/auth/logout", data={"submit": "Log out"}, follow_redirects=False)
    assert logout_response.status_code == 302
    assert logout_response.headers["Location"].endswith("/auth/login")

    login_response = client.post(
        "/auth/login",
        data={"email": "qa-user@example.com", "password": "Pass12345", "submit": "Sign in"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith("/dashboard")


def test_login_required_redirects_to_auth(client):
    response = client.get("/transactions/", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_register_accepts_email_with_spaces(app, client):
    response = client.post(
        "/auth/register",
        data={
            "full_name": "Spacing User",
            "email": "  Spacing.User@Example.com  ",
            "password": "Pass12345",
            "confirm_password": "Pass12345",
            "submit": "Create account",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    with app.app_context():
        created = User.query.filter_by(email="spacing.user@example.com").first()
        assert created is not None


def test_login_accepts_email_with_spaces(app, client):
    with app.app_context():
        user = User(email="spaces@example.com", full_name="Spaces", currency_code="USD", timezone="UTC")
        user.set_password("Pass12345")
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/auth/login",
        data={
            "email": "  spaces@example.com  ",
            "password": "Pass12345",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_login_ignores_external_next_when_host_is_forged(app, client):
    with app.app_context():
        user = User(email="redirect@example.com", full_name="Redirect", currency_code="USD", timezone="UTC")
        user.set_password("Pass12345")
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/auth/login?next=https://evil.example/pwn",
        base_url="https://evil.example",
        data={
            "email": "redirect@example.com",
            "password": "Pass12345",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_login_allows_internal_relative_next(app, client):
    with app.app_context():
        user = User(email="internal-next@example.com", full_name="Internal Next", currency_code="USD", timezone="UTC")
        user.set_password("Pass12345")
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/auth/login?next=/transactions/",
        data={
            "email": "internal-next@example.com",
            "password": "Pass12345",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/transactions/")


def test_register_invalid_email_still_fails(client):
    response = client.post(
        "/auth/register",
        data={
            "full_name": "Bad Email",
            "email": "not-an-email",
            "password": "Pass12345",
            "confirm_password": "Pass12345",
            "submit": "Create account",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert _field_error_text(response, "email") == "Invalid email address."
