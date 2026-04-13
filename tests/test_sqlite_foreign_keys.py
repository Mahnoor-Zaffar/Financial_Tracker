from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from finance_tracker.extensions import db
from finance_tracker.models import Budget, User


def test_sqlite_foreign_keys_are_enabled(app):
    with app.app_context():
        pragma_value = db.session.execute(text("PRAGMA foreign_keys")).scalar_one()
        assert pragma_value == 1


def test_invalid_foreign_key_commit_is_rejected(app):
    with app.app_context():
        user = User(email="fk-check@example.com", full_name="FK Check", currency_code="USD", timezone="UTC")
        user.set_password("Pass12345")
        db.session.add(user)
        db.session.commit()

        budget = Budget(
            user_id=user.id,
            category_id=999999,
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("10.00"),
        )
        db.session.add(budget)

        with pytest.raises(IntegrityError):
            db.session.commit()

        db.session.rollback()
        assert Budget.query.count() == 0
