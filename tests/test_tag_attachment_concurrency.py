from __future__ import annotations

from datetime import date
from decimal import Decimal

from finance_tracker.extensions import db
from finance_tracker.models import Account, Category, Tag, Transaction, User
from finance_tracker.services.transactions import attach_tags
import finance_tracker.services.transactions as transaction_services


def _make_user_with_transactions(app):
    with app.app_context():
        user = User(
            email="tag-race@example.com",
            full_name="Tag Race",
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
        db.session.flush()

        first = Transaction(
            user_id=user.id,
            transaction_type="expense",
            amount=Decimal("10.00"),
            description="First tagged transaction",
            occurred_on=date.today(),
            account_id=account.id,
            category_id=category.id,
        )
        second = Transaction(
            user_id=user.id,
            transaction_type="expense",
            amount=Decimal("12.00"),
            description="Second tagged transaction",
            occurred_on=date.today(),
            account_id=account.id,
            category_id=category.id,
        )
        db.session.add_all([first, second])
        db.session.commit()

        return {
            "user_id": user.id,
            "transaction_ids": [first.id, second.id],
        }


def test_concurrent_same_tag_creation_is_idempotent(app, monkeypatch):
    setup = _make_user_with_transactions(app)
    original_loader = transaction_services._load_existing_tags
    forced_stale_reads = {"remaining": 2}

    def synchronized_loader(user_id: int, names: list[str]):
        if names == ["shared"] and forced_stale_reads["remaining"] > 0:
            forced_stale_reads["remaining"] -= 1
            return {}
        return original_loader(user_id, names)

    monkeypatch.setattr(transaction_services, "_load_existing_tags", synchronized_loader)

    for transaction_id in setup["transaction_ids"]:
        with app.app_context():
            transaction = db.session.get(Transaction, transaction_id)
            attach_tags(transaction, "shared", setup["user_id"])
            db.session.commit()

    with app.app_context():
        tags = Tag.query.filter_by(user_id=setup["user_id"], name="shared").all()
        assert len(tags) == 1

        transactions = (
            Transaction.query.filter(Transaction.id.in_(setup["transaction_ids"]))
            .order_by(Transaction.id.asc())
            .all()
        )
        assert len(transactions) == 2
        assert all(len(transaction.tags) == 1 for transaction in transactions)
        assert {transaction.tags[0].id for transaction in transactions} == {tags[0].id}
