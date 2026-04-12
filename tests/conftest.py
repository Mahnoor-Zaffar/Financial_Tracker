from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from finance_tracker import create_app
from finance_tracker.extensions import db
from finance_tracker.models import Account, Category, User


@pytest.fixture()
def app(tmp_path):
    app = create_app("testing")
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'test.db'}",
        SECRET_KEY="test-secret-key",
    )

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_user(app):
    def _make_user(email: str, password: str = "Pass12345", full_name: str = "Test User") -> int:
        with app.app_context():
            user = User(email=email, full_name=full_name, currency_code="USD", timezone="UTC")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return user.id

    return _make_user


@pytest.fixture()
def seed_finance(app):
    def _seed_finance(user_id: int):
        with app.app_context():
            checking = Account(
                user_id=user_id,
                name="Checking",
                account_type="checking",
                opening_balance=Decimal("100.00"),
            )
            cash = Account(
                user_id=user_id,
                name="Cash",
                account_type="cash",
                opening_balance=Decimal("20.00"),
            )
            income_cat = Category(
                user_id=user_id,
                name="Salary",
                kind="income",
                color="#255a44",
            )
            expense_cat = Category(
                user_id=user_id,
                name="Groceries",
                kind="expense",
                color="#873f2d",
            )
            db.session.add_all([checking, cash, income_cat, expense_cat])
            db.session.commit()
            return {
                "checking_id": checking.id,
                "cash_id": cash.id,
                "income_category_id": income_cat.id,
                "expense_category_id": expense_cat.id,
                "today": date.today().isoformat(),
            }

    return _seed_finance


@pytest.fixture()
def login(client):
    def _login(email: str, password: str = "Pass12345"):
        return client.post(
            "/auth/login",
            data={"email": email, "password": password, "remember": "y"},
            follow_redirects=False,
        )

    return _login
