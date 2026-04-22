from __future__ import annotations

from datetime import date
from decimal import Decimal

from finance_tracker.extensions import db
from finance_tracker.models import Account, Budget, Category, Transaction


def test_deleting_unreferenced_category_succeeds(app, client, login, make_user):
    user_id = make_user("category-delete-safe-empty@example.com")
    assert login("category-delete-safe-empty@example.com").status_code == 302

    with app.app_context():
        category = Category(
            user_id=user_id,
            name="Side Projects",
            kind="expense",
            color="#123456",
        )
        db.session.add(category)
        db.session.commit()
        category_id = category.id

    response = client.post(
        f"/finance/categories/{category_id}/delete",
        data={"submit": "Delete"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Category deleted." in response.data

    with app.app_context():
        assert db.session.get(Category, category_id) is None


def test_deleting_transaction_referenced_category_is_blocked_and_preserves_link(
    app, client, login, make_user
):
    user_id = make_user("category-delete-referenced@example.com")
    assert login("category-delete-referenced@example.com").status_code == 302

    with app.app_context():
        account = Account(
            user_id=user_id,
            name="Checking",
            account_type="checking",
            opening_balance=Decimal("0.00"),
        )
        category = Category(
            user_id=user_id,
            name="Groceries",
            kind="expense",
            color="#123456",
        )
        db.session.add_all([account, category])
        db.session.flush()

        transaction = Transaction(
            user_id=user_id,
            transaction_type="expense",
            amount=Decimal("18.00"),
            description="Lunch",
            occurred_on=date.today(),
            account_id=account.id,
            category_id=category.id,
        )
        db.session.add(transaction)
        db.session.commit()
        category_id = category.id
        transaction_id = transaction.id

    response = client.post(
        f"/finance/categories/{category_id}/delete",
        data={"submit": "Delete"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Category has historical transactions and cannot be deleted." in response.data

    with app.app_context():
        category = db.session.get(Category, category_id)
        transaction = db.session.get(Transaction, transaction_id)
        assert category is not None
        assert transaction is not None
        assert transaction.category_id == category_id


def test_deleting_budget_referenced_category_remains_blocked(app, client, login, make_user):
    user_id = make_user("category-delete-budget-safe@example.com")
    assert login("category-delete-budget-safe@example.com").status_code == 302

    with app.app_context():
        category = Category(
            user_id=user_id,
            name="Groceries",
            kind="expense",
            color="#123456",
        )
        db.session.add(category)
        db.session.flush()

        budget = Budget(
            user_id=user_id,
            category_id=category.id,
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("100.00"),
        )
        db.session.add(budget)
        db.session.commit()
        category_id = category.id
        budget_id = budget.id

    response = client.post(
        f"/finance/categories/{category_id}/delete",
        data={"submit": "Delete"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Category has budgets and cannot be deleted. Remove the budgets first." in response.data

    with app.app_context():
        assert db.session.get(Category, category_id) is not None
        assert db.session.get(Budget, budget_id) is not None
