from __future__ import annotations

from datetime import date
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from finance_tracker.extensions import db
from finance_tracker.models import Account, Category, Transaction, User
from finance_tracker.services.transactions import TransactionValidationError


def _make_user_with_finance(app):
    with app.app_context():
        user = User(
            email="invariants@example.com",
            full_name="Invariant User",
            currency_code="USD",
            timezone="UTC",
        )
        user.set_password("Pass12345")
        db.session.add(user)
        db.session.flush()

        checking = Account(
            user_id=user.id,
            name="Checking",
            account_type="checking",
            opening_balance=Decimal("0.00"),
        )
        savings = Account(
            user_id=user.id,
            name="Savings",
            account_type="savings",
            opening_balance=Decimal("0.00"),
        )
        income_category = Category(
            user_id=user.id,
            name="Salary",
            kind="income",
            color="#255a44",
        )
        expense_category = Category(
            user_id=user.id,
            name="Groceries",
            kind="expense",
            color="#873f2d",
        )
        db.session.add_all([checking, savings, income_category, expense_category])
        db.session.commit()

        return {
            "user_id": user.id,
            "checking_id": checking.id,
            "savings_id": savings.id,
            "income_category_id": income_category.id,
            "expense_category_id": expense_category.id,
        }


def _commit_transaction(app, **kwargs):
    with app.app_context():
        transaction = Transaction(
            user_id=kwargs["user_id"],
            transaction_type=kwargs["transaction_type"],
            amount=Decimal("10.00"),
            description=kwargs.get("description", "Invariant check"),
            occurred_on=date.today(),
            account_id=kwargs["account_id"],
            transfer_account_id=kwargs.get("transfer_account_id"),
            category_id=kwargs.get("category_id"),
        )
        db.session.add(transaction)
        db.session.commit()


def _load_migration_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "c0a8d9f4b1a7_enforce_transaction_invariants.py"
    )
    spec = spec_from_file_location("migration_ft001", path)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_direct_write_rejects_uncategorized_income(app):
    setup = _make_user_with_finance(app)

    with pytest.raises(TransactionValidationError, match="Select a category"):
        _commit_transaction(
            app,
            user_id=setup["user_id"],
            transaction_type="income",
            account_id=setup["checking_id"],
        )


def test_direct_write_rejects_uncategorized_expense(app):
    setup = _make_user_with_finance(app)

    with pytest.raises(TransactionValidationError, match="Select a category"):
        _commit_transaction(
            app,
            user_id=setup["user_id"],
            transaction_type="expense",
            account_id=setup["checking_id"],
        )


def test_direct_write_rejects_transfer_without_destination_account(app):
    setup = _make_user_with_finance(app)

    with pytest.raises(TransactionValidationError, match="destination account"):
        _commit_transaction(
            app,
            user_id=setup["user_id"],
            transaction_type="transfer",
            account_id=setup["checking_id"],
        )


def test_direct_write_rejects_transfer_with_category(app):
    setup = _make_user_with_finance(app)

    with pytest.raises(TransactionValidationError, match="Transfers cannot be assigned a category"):
        _commit_transaction(
            app,
            user_id=setup["user_id"],
            transaction_type="transfer",
            account_id=setup["checking_id"],
            transfer_account_id=setup["savings_id"],
            category_id=setup["expense_category_id"],
        )


def test_direct_write_rejects_same_source_and_destination_transfer(app):
    setup = _make_user_with_finance(app)

    with pytest.raises(TransactionValidationError, match="must be different"):
        _commit_transaction(
            app,
            user_id=setup["user_id"],
            transaction_type="transfer",
            account_id=setup["checking_id"],
            transfer_account_id=setup["checking_id"],
        )


def test_direct_write_rejects_category_type_mismatch(app):
    setup = _make_user_with_finance(app)

    with pytest.raises(TransactionValidationError, match="Category type mismatch"):
        _commit_transaction(
            app,
            user_id=setup["user_id"],
            transaction_type="expense",
            account_id=setup["checking_id"],
            category_id=setup["income_category_id"],
        )


def test_migration_detection_fails_for_existing_invalid_rows():
    migration = _load_migration_module()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(120) NOT NULL,
                    currency_code VARCHAR(3) NOT NULL,
                    timezone VARCHAR(64) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    account_type VARCHAR(32) NOT NULL,
                    institution VARCHAR(120),
                    opening_balance NUMERIC(12, 2) NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    user_id INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE categories (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    kind VARCHAR(20) NOT NULL,
                    color VARCHAR(7) NOT NULL,
                    user_id INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY,
                    transaction_type VARCHAR(20) NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL,
                    description VARCHAR(180) NOT NULL,
                    notes TEXT,
                    occurred_on DATE NOT NULL,
                    account_id INTEGER NOT NULL,
                    transfer_account_id INTEGER,
                    category_id INTEGER,
                    user_id INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO users (id, email, password_hash, full_name, currency_code, timezone)
                VALUES (1, 'legacy@example.com', 'hash', 'Legacy User', 'USD', 'UTC')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO accounts (id, name, account_type, opening_balance, is_active, user_id)
                VALUES (1, 'Checking', 'checking', 0.00, 1, 1)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    id,
                    transaction_type,
                    amount,
                    description,
                    occurred_on,
                    account_id,
                    transfer_account_id,
                    category_id,
                    user_id
                ) VALUES (
                    1,
                    'income',
                    10.00,
                    'Legacy invalid transaction',
                    :occurred_on,
                    1,
                    NULL,
                    NULL,
                    1
                )
                """
            ),
            {"occurred_on": date.today().isoformat()},
        )

        with pytest.raises(RuntimeError, match="invalid transactions"):
            migration.raise_for_invalid_transactions(connection)
