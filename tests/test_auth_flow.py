from __future__ import annotations

from finance_tracker.models import User


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
