from __future__ import annotations

from datetime import date
from decimal import Decimal

from finance_tracker.extensions import db
from finance_tracker.models import Budget, Transaction
from finance_tracker.services import (
    account_balance,
    build_monthly_summary_series,
    get_budget_progress_rows,
)


def _create_transaction(client, payload: dict, follow_redirects: bool = False):
    data = {
        "new-transaction_type": payload["transaction_type"],
        "new-account_id": str(payload["account_id"]),
        "new-to_account_id": str(payload.get("to_account_id", 0)),
        "new-category_id": str(payload.get("category_id", 0)),
        "new-amount": payload["amount"],
        "new-occurred_on": payload["occurred_on"],
        "new-description": payload["description"],
        "new-notes": payload.get("notes", ""),
        "new-tag_names": payload.get("tag_names", ""),
        "new-submit": "Save transaction",
    }
    return client.post("/transactions/new", data=data, follow_redirects=follow_redirects)


def test_transfer_and_balance_integrity(app, client, login, make_user, seed_finance):
    user_id = make_user("owner@example.com")
    setup = seed_finance(user_id)

    assert login("owner@example.com").status_code == 302

    income = _create_transaction(
        client,
        {
            "transaction_type": "income",
            "account_id": setup["checking_id"],
            "category_id": setup["income_category_id"],
            "amount": "1000.00",
            "occurred_on": setup["today"],
            "description": "Salary payout",
        },
    )
    assert income.status_code == 302

    expense = _create_transaction(
        client,
        {
            "transaction_type": "expense",
            "account_id": setup["checking_id"],
            "category_id": setup["expense_category_id"],
            "amount": "120.00",
            "occurred_on": setup["today"],
            "description": "Groceries run",
            "tag_names": "home, essentials",
        },
    )
    assert expense.status_code == 302

    transfer = _create_transaction(
        client,
        {
            "transaction_type": "transfer",
            "account_id": setup["checking_id"],
            "to_account_id": setup["cash_id"],
            "amount": "200.00",
            "occurred_on": setup["today"],
            "description": "ATM withdrawal",
        },
    )
    assert transfer.status_code == 302

    with app.app_context():
        checking_balance = account_balance(setup["checking_id"], user_id)
        cash_balance = account_balance(setup["cash_id"], user_id)
        assert checking_balance == Decimal("780.00")  # 100 + 1000 - 120 - 200
        assert cash_balance == Decimal("220.00")  # 20 + 200 transfer in

        transfer_tx = Transaction.query.filter_by(
            user_id=user_id, transaction_type="transfer"
        ).first()
        assert transfer_tx is not None
        assert transfer_tx.category_id is None
        assert transfer_tx.transfer_account_id == setup["cash_id"]


def test_invalid_transaction_type_category_mismatch_rejected(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("mismatch@example.com")
    setup = seed_finance(user_id)
    assert login("mismatch@example.com").status_code == 302

    response = _create_transaction(
        client,
        {
            "transaction_type": "expense",
            "account_id": setup["checking_id"],
            "category_id": setup["income_category_id"],  # wrong kind
            "amount": "5.00",
            "occurred_on": setup["today"],
            "description": "Invalid combo",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Category type mismatch" in response.data

    with app.app_context():
        assert Transaction.query.filter_by(user_id=user_id).count() == 0


def test_authorization_blocked_for_other_users_resources(
    app, client, login, make_user, seed_finance
):
    owner_id = make_user("owner2@example.com")
    make_user("attacker@example.com")
    setup = seed_finance(owner_id)

    with app.app_context():
        tx = Transaction(
            user_id=owner_id,
            transaction_type="expense",
            amount=Decimal("20.00"),
            description="Owner only record",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            category_id=setup["expense_category_id"],
        )
        db.session.add(tx)
        db.session.commit()
        tx_id = tx.id

    assert login("attacker@example.com").status_code == 302

    get_response = client.get(f"/transactions/{tx_id}/edit")
    assert get_response.status_code == 404

    post_response = client.post(
        f"/transactions/{tx_id}/delete",
        data={"submit": "Delete"},
        follow_redirects=False,
    )
    assert post_response.status_code == 404


def test_filters_and_pagination_work_together(app, client, login, make_user, seed_finance):
    user_id = make_user("filters@example.com")
    setup = seed_finance(user_id)
    assert login("filters@example.com").status_code == 302

    with app.app_context():
        for idx in range(35):
            tx = Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("1.00"),
                description=f"Item {idx:02d}",
                occurred_on=date.today(),
                account_id=setup["checking_id"],
                category_id=setup["expense_category_id"],
            )
            db.session.add(tx)
        db.session.commit()

    response = client.get(
        f"/transactions/?transaction_type=expense&account_id={setup['checking_id']}&per_page=20&page=2",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Page 2 of 2" in response.data
    assert b"Apply filters" in response.data


def test_budget_progress_marks_overspend(app, client, login, make_user, seed_finance):
    user_id = make_user("budget@example.com")
    setup = seed_finance(user_id)
    assert login("budget@example.com").status_code == 302

    with app.app_context():
        budget = Budget(
            user_id=user_id,
            category_id=setup["expense_category_id"],
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("50.00"),
        )
        db.session.add(budget)
        db.session.add(
            Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("80.00"),
                description="Over budget",
                occurred_on=date.today(),
                account_id=setup["checking_id"],
                category_id=setup["expense_category_id"],
            )
        )
        db.session.commit()

        rows = get_budget_progress_rows(user_id, date.today().replace(day=1))
        assert len(rows) == 1
        assert rows[0]["is_overspent"] is True
        assert rows[0]["remaining"] == Decimal("-30.00")


def test_analytics_series_uses_correct_income_and_expense_points(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("charts@example.com")
    setup = seed_finance(user_id)
    assert login("charts@example.com").status_code == 302

    with app.app_context():
        db.session.add_all(
            [
                Transaction(
                    user_id=user_id,
                    transaction_type="income",
                    amount=Decimal("900.00"),
                    description="Income row",
                    occurred_on=date.today().replace(day=2),
                    account_id=setup["checking_id"],
                    category_id=setup["income_category_id"],
                ),
                Transaction(
                    user_id=user_id,
                    transaction_type="expense",
                    amount=Decimal("250.00"),
                    description="Expense row",
                    occurred_on=date.today().replace(day=3),
                    account_id=setup["checking_id"],
                    category_id=setup["expense_category_id"],
                ),
            ]
        )
        db.session.commit()

        snapshot = build_monthly_summary_series(user_id, months=1)
        assert snapshot["flow_labels"] == [date.today().strftime("%Y-%m")]
        assert snapshot["income_points"] == ["900.00"]
        assert snapshot["expense_points"] == ["250.00"]
