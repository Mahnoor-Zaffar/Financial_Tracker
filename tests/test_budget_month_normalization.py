from __future__ import annotations

from datetime import date
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from finance_tracker.extensions import db
from finance_tracker.models import Account, Budget, Category, Transaction, User
from finance_tracker.services.reporting import get_budget_progress_rows


def _make_user_with_budget_context(app):
    with app.app_context():
        user = User(
            email="budget-normalization@example.com",
            full_name="Budget User",
            currency_code="USD",
            timezone="UTC",
        )
        user.set_password("Pass12345")
        db.session.add(user)
        db.session.flush()

        account = Account(
            user_id=user.id,
            name="Checking",
            account_type="checking",
            opening_balance=Decimal("0.00"),
        )
        category = Category(
            user_id=user.id,
            name="Groceries",
            kind="expense",
            color="#873f2d",
        )
        db.session.add_all([account, category])
        db.session.commit()

        return {
            "user_id": user.id,
            "account_id": account.id,
            "category_id": category.id,
        }


def _load_migration_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "8a1d9c6e4b2f_normalize_budget_months.py"
    )
    spec = spec_from_file_location("migration_ft003", path)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_non_first_day_budget_month_is_normalized_on_persist(app):
    setup = _make_user_with_budget_context(app)

    with app.app_context():
        budget = Budget(
            user_id=setup["user_id"],
            category_id=setup["category_id"],
            month_start=date(2026, 4, 23),
            amount_limit=Decimal("125.00"),
        )
        db.session.add(budget)
        db.session.commit()

        stored = db.session.get(Budget, budget.id)
        assert stored is not None
        assert stored.month_start == date(2026, 4, 1)


def test_duplicate_budgets_for_same_logical_month_are_rejected(app):
    setup = _make_user_with_budget_context(app)

    with app.app_context():
        db.session.add(
            Budget(
                user_id=setup["user_id"],
                category_id=setup["category_id"],
                month_start=date(2026, 4, 1),
                amount_limit=Decimal("100.00"),
            )
        )
        db.session.commit()

        duplicate = Budget(
            user_id=setup["user_id"],
            category_id=setup["category_id"],
            month_start=date(2026, 4, 23),
            amount_limit=Decimal("150.00"),
        )
        db.session.add(duplicate)

        with pytest.raises(IntegrityError):
            db.session.commit()

        db.session.rollback()
        assert (
            Budget.query.filter_by(
                user_id=setup["user_id"],
                category_id=setup["category_id"],
                month_start=date(2026, 4, 1),
            ).count()
            == 1
        )


def test_reporting_resolves_normalized_budget_months(app):
    setup = _make_user_with_budget_context(app)

    with app.app_context():
        budget = Budget(
            user_id=setup["user_id"],
            category_id=setup["category_id"],
            month_start=date(2026, 4, 23),
            amount_limit=Decimal("200.00"),
        )
        expense = Transaction(
            user_id=setup["user_id"],
            transaction_type="expense",
            amount=Decimal("80.00"),
            description="Groceries",
            occurred_on=date(2026, 4, 10),
            account_id=setup["account_id"],
            category_id=setup["category_id"],
        )
        db.session.add_all([budget, expense])
        db.session.commit()

        rows = get_budget_progress_rows(setup["user_id"], date(2026, 4, 30))
        assert len(rows) == 1
        assert rows[0]["budget"].month_start == date(2026, 4, 1)
        assert rows[0]["spent"] == Decimal("80.00")
        assert rows[0]["limit"] == Decimal("200.00")


def test_migration_normalizes_and_deduplicates_existing_budget_rows():
    migration = _load_migration_module()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE budgets (
                    id INTEGER PRIMARY KEY,
                    category_id INTEGER NOT NULL,
                    month_start DATE NOT NULL,
                    amount_limit NUMERIC(12, 2) NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO budgets (
                    id, category_id, month_start, amount_limit, user_id, created_at, updated_at
                ) VALUES
                    (1, 7, '2026-04-23', 100.00, 5, '2026-04-01 09:00:00', '2026-04-01 09:00:00'),
                    (2, 7, '2026-04-01', 150.00, 5, '2026-04-02 09:00:00', '2026-04-02 09:00:00'),
                    (3, 9, '2026-05-19', 75.00, 5, '2026-05-01 09:00:00', '2026-05-03 12:00:00')
                """
            )
        )

        conflicts = migration.find_budget_month_conflicts(connection)
        assert conflicts["non_normalized_ids"] == [1, 3]
        assert conflicts["duplicate_groups"] == [
            {
                "user_id": 5,
                "category_id": 7,
                "month_start": date(2026, 4, 1),
                "budget_ids": [1, 2],
            }
        ]

        summary = migration.normalize_and_deduplicate_budgets(connection)
        assert summary["deleted_ids"] == [1]
        assert summary["updated_ids"] == [3]

        rows = connection.execute(
            text(
                """
                SELECT id, category_id, month_start, amount_limit, user_id
                FROM budgets
                ORDER BY id
                """
            )
        ).mappings().all()
        assert len(rows) == 2
        assert rows[0]["id"] == 2
        assert rows[0]["category_id"] == 7
        assert str(rows[0]["month_start"]) == "2026-04-01"
        assert Decimal(str(rows[0]["amount_limit"])) == Decimal("150.00")
        assert rows[0]["user_id"] == 5
        assert rows[1]["id"] == 3
        assert rows[1]["category_id"] == 9
        assert str(rows[1]["month_start"]) == "2026-05-01"
        assert Decimal(str(rows[1]["amount_limit"])) == Decimal("75.00")
        assert rows[1]["user_id"] == 5
