from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import re
import warnings

from finance_tracker.extensions import db
from finance_tracker.models import Account, Budget, Category, Tag, Transaction, TransactionTag
from finance_tracker.services import (
    account_balance,
    build_monthly_summary_series,
    get_budget_progress_rows,
)
from sqlalchemy.exc import SAWarning


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


def _seed_expenses(app, user_id: int, account_id: int, category_id: int):
    with app.app_context():
        for days_ago, description in [
            (10, "Old expense"),
            (5, "Middle expense"),
            (1, "New expense"),
        ]:
            db.session.add(
                Transaction(
                    user_id=user_id,
                    transaction_type="expense",
                    amount=Decimal("10.00"),
                    description=description,
                    occurred_on=date.today() - timedelta(days=days_ago),
                    account_id=account_id,
                    category_id=category_id,
                )
            )
        db.session.commit()


def _delete_transaction_and_capture_warnings(client, tx_id: int):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = client.post(
            f"/transactions/{tx_id}/delete",
            data={"submit": "Delete"},
            follow_redirects=True,
        )
    return response, caught


def _select_inner_html(response, field_name: str) -> str:
    html = response.get_data(as_text=True)
    pattern = rf'<select[^>]*name="{re.escape(field_name)}"[^>]*>(.*?)</select>'
    match = re.search(pattern, html, re.S)
    assert match is not None, f"Could not find select field {field_name!r}"
    return match.group(1)


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


def test_transaction_create_with_active_account_succeeds(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("active-account-create@example.com")
    setup = seed_finance(user_id)
    assert login("active-account-create@example.com").status_code == 302

    response = _create_transaction(
        client,
        {
            "transaction_type": "expense",
            "account_id": setup["checking_id"],
            "category_id": setup["expense_category_id"],
            "amount": "22.00",
            "occurred_on": setup["today"],
            "description": "Active account purchase",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Transaction saved." in response.data

    with app.app_context():
        tx = Transaction.query.filter_by(user_id=user_id, description="Active account purchase").first()
        assert tx is not None
        assert tx.account_id == setup["checking_id"]


def test_transaction_create_rejects_archived_account(app, client, login, make_user, seed_finance):
    user_id = make_user("archived-account-create@example.com")
    setup = seed_finance(user_id)
    assert login("archived-account-create@example.com").status_code == 302

    with app.app_context():
        account = db.session.get(Account, setup["checking_id"])
        account.is_active = False
        db.session.commit()

    response = _create_transaction(
        client,
        {
            "transaction_type": "expense",
            "account_id": setup["checking_id"],
            "category_id": setup["expense_category_id"],
            "amount": "22.00",
            "occurred_on": setup["today"],
            "description": "Archived account purchase",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert _field_error_text(response, "new-account_id") == "Select an active account."

    with app.app_context():
        assert (
            Transaction.query.filter_by(user_id=user_id, description="Archived account purchase").count()
            == 0
        )


def test_transfer_rejects_archived_source_account(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("archived-transfer@example.com")
    setup = seed_finance(user_id)
    assert login("archived-transfer@example.com").status_code == 302

    with app.app_context():
        source = db.session.get(Account, setup["checking_id"])
        destination = db.session.get(Account, setup["cash_id"])
        source.is_active = False
        db.session.commit()

    source_response = _create_transaction(
        client,
        {
            "transaction_type": "transfer",
            "account_id": setup["checking_id"],
            "to_account_id": setup["cash_id"],
            "amount": "15.00",
            "occurred_on": setup["today"],
            "description": "Archived source transfer",
        },
        follow_redirects=True,
    )
    assert source_response.status_code == 200
    assert _field_error_text(source_response, "new-account_id") == "Select an active account."

    with app.app_context():
        assert (
            Transaction.query.filter_by(user_id=user_id, description="Archived source transfer").count()
            == 0
        )


def test_transfer_rejects_archived_destination_account(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("archived-transfer-destination@example.com")
    setup = seed_finance(user_id)
    assert login("archived-transfer-destination@example.com").status_code == 302

    with app.app_context():
        destination = db.session.get(Account, setup["cash_id"])
        destination.is_active = False
        db.session.commit()

    destination_response = _create_transaction(
        client,
        {
            "transaction_type": "transfer",
            "account_id": setup["checking_id"],
            "to_account_id": setup["cash_id"],
            "amount": "15.00",
            "occurred_on": setup["today"],
            "description": "Archived destination transfer",
        },
        follow_redirects=True,
    )
    assert destination_response.status_code == 200
    assert _field_error_text(destination_response, "new-to_account_id") == "Select an active destination account."

    with app.app_context():
        assert (
            Transaction.query.filter_by(user_id=user_id, description="Archived destination transfer").count()
            == 0
        )


def test_income_transaction_requires_category_with_inline_error(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("missing-category@example.com")
    setup = seed_finance(user_id)
    assert login("missing-category@example.com").status_code == 302

    response = _create_transaction(
        client,
        {
            "transaction_type": "income",
            "account_id": setup["checking_id"],
            "category_id": 0,
            "amount": "100.00",
            "occurred_on": setup["today"],
            "description": "Missing category",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert _field_error_text(
        response,
        "new-category_id",
    ) == "Select a category for income and expense transactions."


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
    assert _field_error_text(
        response,
        "new-category_id",
    ) == "Category type mismatch. Choose a expense category."

    with app.app_context():
        assert Transaction.query.filter_by(user_id=user_id).count() == 0


def test_expense_transaction_form_only_shows_expense_categories(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("expense-form@example.com")
    setup = seed_finance(user_id)
    assert login("expense-form@example.com").status_code == 302

    response = client.get("/transactions/new")
    assert response.status_code == 200

    category_html = _select_inner_html(response, "new-category_id")
    assert "Groceries" in category_html
    assert "Salary" not in category_html


def test_income_transaction_form_only_shows_income_categories(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("income-form@example.com")
    setup = seed_finance(user_id)
    assert login("income-form@example.com").status_code == 302

    with app.app_context():
        tx = Transaction(
            user_id=user_id,
            transaction_type="income",
            amount=Decimal("500.00"),
            description="Income form",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            category_id=setup["income_category_id"],
        )
        db.session.add(tx)
        db.session.commit()
        tx_id = tx.id

    response = client.get(f"/transactions/{tx_id}/edit")
    assert response.status_code == 200

    category_html = _select_inner_html(response, "edit-category_id")
    assert "Salary" in category_html
    assert "Groceries" not in category_html


def test_transfer_transaction_form_only_allows_no_category(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("transfer-form@example.com")
    setup = seed_finance(user_id)
    assert login("transfer-form@example.com").status_code == 302

    with app.app_context():
        tx = Transaction(
            user_id=user_id,
            transaction_type="transfer",
            amount=Decimal("40.00"),
            description="Transfer form",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            transfer_account_id=setup["cash_id"],
        )
        db.session.add(tx)
        db.session.commit()
        tx_id = tx.id

    response = client.get(f"/transactions/{tx_id}/edit")
    assert response.status_code == 200

    category_html = _select_inner_html(response, "edit-category_id")
    assert "No category" in category_html
    assert "Salary" not in category_html
    assert "Groceries" not in category_html


def test_transfer_transaction_can_save_without_categories(app, client, login, make_user):
    user_id = make_user("transfer-no-categories@example.com")
    assert login("transfer-no-categories@example.com").status_code == 302

    with app.app_context():
        checking = Account(user_id=user_id, name="Checking", account_type="checking", opening_balance=Decimal("0.00"))
        cash = Account(user_id=user_id, name="Cash", account_type="cash", opening_balance=Decimal("0.00"))
        db.session.add_all([checking, cash])
        db.session.commit()
        checking_id = checking.id
        cash_id = cash.id

    response = _create_transaction(
        client,
        {
            "transaction_type": "transfer",
            "account_id": checking_id,
            "to_account_id": cash_id,
            "category_id": 0,
            "amount": "20.00",
            "occurred_on": date.today().isoformat(),
            "description": "Cash move",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Transaction saved." in response.data

    with app.app_context():
        tx = Transaction.query.filter_by(user_id=user_id, transaction_type="transfer").first()
        assert tx is not None
        assert tx.category_id is None


def test_expense_transaction_with_category_saves(app, client, login, make_user, seed_finance):
    user_id = make_user("expense-category@example.com")
    setup = seed_finance(user_id)
    assert login("expense-category@example.com").status_code == 302

    response = _create_transaction(
        client,
        {
            "transaction_type": "expense",
            "account_id": setup["checking_id"],
            "category_id": setup["expense_category_id"],
            "amount": "34.25",
            "occurred_on": setup["today"],
            "description": "Expense with category",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Transaction saved." in response.data

    with app.app_context():
        tx = Transaction.query.filter_by(user_id=user_id, transaction_type="expense").first()
        assert tx is not None
        assert tx.category_id == setup["expense_category_id"]


def test_no_categories_available_shows_clear_validation_error(app, client, login, make_user):
    user_id = make_user("no-categories@example.com")
    assert login("no-categories@example.com").status_code == 302

    with app.app_context():
        account = Account(
            user_id=user_id,
            name="Checking",
            account_type="checking",
            opening_balance=Decimal("0.00"),
        )
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = _create_transaction(
        client,
        {
            "transaction_type": "expense",
            "account_id": account_id,
            "category_id": 0,
            "amount": "12.00",
            "occurred_on": date.today().isoformat(),
            "description": "No category available",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Create at least one category before saving income or expense transactions." in response.data


def test_invalid_foreign_category_id_is_rejected(app, client, login, make_user):
    owner_id = make_user("foreign-category-owner@example.com")
    attacker_id = make_user("foreign-category-attacker@example.com")

    with app.app_context():
        owner_account = Account(
            user_id=owner_id,
            name="Owner Checking",
            account_type="checking",
            opening_balance=Decimal("0.00"),
        )
        owner_category = Category(
            user_id=owner_id,
            name="Owner Expense",
            kind="expense",
            color="#123456",
        )
        attacker_account = Account(
            user_id=attacker_id,
            name="Attacker Checking",
            account_type="checking",
            opening_balance=Decimal("0.00"),
        )
        attacker_category = Category(
            user_id=attacker_id,
            name="Attacker Expense",
            kind="expense",
            color="#654321",
        )
        db.session.add_all([owner_account, owner_category, attacker_account, attacker_category])
        db.session.commit()
        owner_account_id = owner_account.id
        foreign_category_id = attacker_category.id

    assert login("foreign-category-owner@example.com").status_code == 302

    response = _create_transaction(
        client,
            {
                "transaction_type": "expense",
                "account_id": owner_account_id,
                "category_id": foreign_category_id,
                "amount": "18.00",
                "occurred_on": date.today().isoformat(),
                "description": "Foreign category attempt",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert _field_error_text(response, "new-category_id") == "Invalid category selected."

    with app.app_context():
        assert Transaction.query.filter_by(user_id=owner_id).count() == 0


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


def test_pagination_preserves_per_page_selection(app, client, login, make_user, seed_finance):
    user_id = make_user("per-page@example.com")
    setup = seed_finance(user_id)
    assert login("per-page@example.com").status_code == 302

    with app.app_context():
        for idx in range(75):
            tx = Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("1.00"),
                description=f"Rows {idx:02d}",
                occurred_on=date.today(),
                account_id=setup["checking_id"],
                category_id=setup["expense_category_id"],
            )
            db.session.add(tx)
        db.session.commit()

    response = client.get("/transactions/?per_page=50&page=1", follow_redirects=True)
    assert response.status_code == 200
    assert b"Page 1 of 2" in response.data
    assert b"per_page=50" in response.data


def test_pagination_preserves_per_page_with_filters(app, client, login, make_user, seed_finance):
    user_id = make_user("per-page-filter@example.com")
    setup = seed_finance(user_id)
    assert login("per-page-filter@example.com").status_code == 302

    with app.app_context():
        for idx in range(75):
            tx = Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("1.00"),
                description=f"Filtered {idx:02d}",
                occurred_on=date.today(),
                account_id=setup["checking_id"],
                category_id=setup["expense_category_id"],
            )
            db.session.add(tx)
        db.session.commit()

    response = client.get(
        f"/transactions/?transaction_type=expense&account_id={setup['checking_id']}&per_page=50&page=2",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Page 2 of 2" in response.data
    assert b"transaction_type=expense" in response.data
    assert b"account_id=" in response.data
    assert b"per_page=50" in response.data


def test_pagination_default_without_per_page_param(app, client, login, make_user, seed_finance):
    user_id = make_user("per-page-default@example.com")
    setup = seed_finance(user_id)
    assert login("per-page-default@example.com").status_code == 302

    with app.app_context():
        for idx in range(35):
            tx = Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("1.00"),
                description=f"Default {idx:02d}",
                occurred_on=date.today(),
                account_id=setup["checking_id"],
                category_id=setup["expense_category_id"],
            )
            db.session.add(tx)
        db.session.commit()

    response = client.get("/transactions/?page=2", follow_redirects=True)
    assert response.status_code == 200
    assert b"Page 2 of 2" in response.data
    assert b"per_page=" not in response.data


def test_invalid_date_range_filters_are_ignored(app, client, login, make_user, seed_finance):
    user_id = make_user("filter-range@example.com")
    setup = seed_finance(user_id)
    assert login("filter-range@example.com").status_code == 302

    _seed_expenses(app, user_id, setup["checking_id"], setup["expense_category_id"])

    response = client.get(
        f"/transactions/?start_date={date.today().isoformat()}&end_date={(date.today() - timedelta(days=6)).isoformat()}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Start date must be on or before end date." in response.data
    assert b"Old expense" in response.data
    assert b"Middle expense" in response.data
    assert b"New expense" in response.data


def test_valid_start_date_filter_limits_results(app, client, login, make_user, seed_finance):
    user_id = make_user("filter-start@example.com")
    setup = seed_finance(user_id)
    assert login("filter-start@example.com").status_code == 302

    _seed_expenses(app, user_id, setup["checking_id"], setup["expense_category_id"])

    response = client.get(
        f"/transactions/?start_date={(date.today() - timedelta(days=6)).isoformat()}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Old expense" not in response.data
    assert b"Middle expense" in response.data
    assert b"New expense" in response.data


def test_valid_end_date_filter_limits_results(app, client, login, make_user, seed_finance):
    user_id = make_user("filter-end@example.com")
    setup = seed_finance(user_id)
    assert login("filter-end@example.com").status_code == 302

    _seed_expenses(app, user_id, setup["checking_id"], setup["expense_category_id"])

    response = client.get(
        f"/transactions/?end_date={(date.today() - timedelta(days=6)).isoformat()}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Old expense" in response.data
    assert b"Middle expense" not in response.data
    assert b"New expense" not in response.data


def test_valid_date_range_filter_limits_results(app, client, login, make_user, seed_finance):
    user_id = make_user("filter-range-valid@example.com")
    setup = seed_finance(user_id)
    assert login("filter-range-valid@example.com").status_code == 302

    _seed_expenses(app, user_id, setup["checking_id"], setup["expense_category_id"])

    response = client.get(
        f"/transactions/?start_date={(date.today() - timedelta(days=6)).isoformat()}&end_date={(date.today() - timedelta(days=1)).isoformat()}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Old expense" not in response.data
    assert b"Middle expense" in response.data
    assert b"New expense" in response.data


def test_invalid_start_date_is_ignored_without_hiding_valid_rows(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("filter-invalid-start@example.com")
    setup = seed_finance(user_id)
    assert login("filter-invalid-start@example.com").status_code == 302

    _seed_expenses(app, user_id, setup["checking_id"], setup["expense_category_id"])

    response = client.get(
        f"/transactions/?start_date=not-a-date&end_date={(date.today() - timedelta(days=6)).isoformat()}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Some filters were invalid and were ignored." in response.data
    assert b"Old expense" in response.data
    assert b"Middle expense" not in response.data
    assert b"New expense" not in response.data


def test_invalid_end_date_is_ignored_without_hiding_valid_rows(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("filter-invalid-end@example.com")
    setup = seed_finance(user_id)
    assert login("filter-invalid-end@example.com").status_code == 302

    _seed_expenses(app, user_id, setup["checking_id"], setup["expense_category_id"])

    response = client.get(
        f"/transactions/?start_date={(date.today() - timedelta(days=6)).isoformat()}&end_date=not-a-date",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Some filters were invalid and were ignored." in response.data
    assert b"Old expense" not in response.data
    assert b"Middle expense" in response.data
    assert b"New expense" in response.data


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


def test_account_opening_balance_zero_is_accepted(app, client, login, make_user):
    make_user("account-zero@example.com")
    assert login("account-zero@example.com").status_code == 302

    response = client.post(
        "/finance/accounts",
        data={
            "create-name": "Zero Balance",
            "create-account_type": "checking",
            "create-institution": "",
            "create-opening_balance": "0.00",
            "create-submit": "Add account",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Account created." in response.data

    with app.app_context():
        account = Account.query.filter_by(name="Zero Balance").first()
        assert account is not None
        assert account.opening_balance == Decimal("0.00")


def test_account_edit_to_zero_balance_is_accepted(app, client, login, make_user):
    user_id = make_user("account-edit-zero@example.com")
    assert login("account-edit-zero@example.com").status_code == 302

    with app.app_context():
        account = Account(
            user_id=user_id,
            name="Savings",
            account_type="savings",
            opening_balance=Decimal("125.50"),
        )
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = client.post(
        f"/finance/accounts/{account_id}/edit",
        data={
            "edit-name": "Savings",
            "edit-account_type": "savings",
            "edit-institution": "",
            "edit-opening_balance": "0.00",
            "edit-submit": "Add account",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Account updated." in response.data

    with app.app_context():
        account = db.session.get(Account, account_id)
        assert account is not None
        assert account.opening_balance == Decimal("0.00")


def test_account_opening_balance_blank_fails_when_required(app, client, login, make_user):
    make_user("account-blank@example.com")
    assert login("account-blank@example.com").status_code == 302

    response = client.post(
        "/finance/accounts",
        data={
            "create-name": "Blank Balance",
            "create-account_type": "checking",
            "create-institution": "",
            "create-opening_balance": "",
            "create-submit": "Add account",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"This field is required." in response.data

    with app.app_context():
        assert Account.query.filter_by(name="Blank Balance").count() == 0


def test_account_opening_balance_invalid_text_fails_cleanly(app, client, login, make_user):
    make_user("account-invalid@example.com")
    assert login("account-invalid@example.com").status_code == 302

    response = client.post(
        "/finance/accounts",
        data={
            "create-name": "Invalid Balance",
            "create-account_type": "checking",
            "create-institution": "",
            "create-opening_balance": "abc",
            "create-submit": "Add account",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Not a valid decimal value." in response.data

    with app.app_context():
        assert Account.query.filter_by(name="Invalid Balance").count() == 0


def test_budget_form_can_create_a_monthly_budget(app, client, login, make_user, seed_finance):
    user_id = make_user("budget-create@example.com")
    setup = seed_finance(user_id)
    assert login("budget-create@example.com").status_code == 302

    month_start = date.today().replace(day=1).isoformat()
    response = client.post(
        "/budgets/",
        data={
            "create-category_id": str(setup["expense_category_id"]),
            "create-month_start": month_start,
            "create-amount_limit": "250.00",
            "create-submit": "Save budget",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Budget saved." in response.data

    with app.app_context():
        budget = Budget.query.filter_by(
            user_id=user_id,
            category_id=setup["expense_category_id"],
            month_start=date.today().replace(day=1),
        ).first()
        assert budget is not None
        assert budget.amount_limit == Decimal("250.00")


def test_budget_edit_updates_existing_budget(app, client, login, make_user, seed_finance):
    user_id = make_user("budget-update@example.com")
    setup = seed_finance(user_id)
    assert login("budget-update@example.com").status_code == 302

    with app.app_context():
        budget = Budget(
            user_id=user_id,
            category_id=setup["expense_category_id"],
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("100.00"),
        )
        db.session.add(budget)
        db.session.commit()
        budget_id = budget.id

    response = client.post(
        f"/budgets/{budget_id}/edit",
        data={
            "edit-category_id": str(setup["expense_category_id"]),
            "edit-month_start": date.today().replace(day=1).isoformat(),
            "edit-amount_limit": "180.00",
            "edit-submit": "Save budget",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Budget updated." in response.data

    with app.app_context():
        budget = db.session.get(Budget, budget_id)
        assert budget is not None
        assert budget.amount_limit == Decimal("180.00")


def _month_input_value(response) -> str:
    html = response.get_data(as_text=True)
    marker = 'id="month"'
    idx = html.find(marker)
    assert idx != -1, "Could not find month input"
    value_idx = html.find('value="', idx)
    assert value_idx != -1, "Could not find month input value"
    value_start = value_idx + len('value="')
    value_end = html.find('"', value_start)
    assert value_end != -1, "Could not parse month input value"
    return html[value_start:value_end]


def test_budget_month_query_valid(app, client, login, make_user, seed_finance):
    user_id = make_user("budget-month-valid@example.com")
    seed_finance(user_id)
    assert login("budget-month-valid@example.com").status_code == 302

    response = client.get("/budgets/?month=2024-02", follow_redirects=True)
    assert response.status_code == 200
    assert _month_input_value(response) == "2024-02"


def test_budget_month_query_invalid_shows_warning(app, client, login, make_user, seed_finance):
    user_id = make_user("budget-month-invalid@example.com")
    seed_finance(user_id)
    assert login("budget-month-invalid@example.com").status_code == 302

    response = client.get("/budgets/?month=2024-13", follow_redirects=True)
    assert response.status_code == 200
    assert b"Invalid month selected. Showing the current month instead." in response.data
    assert _month_input_value(response) == date.today().strftime("%Y-%m")


def test_budget_month_query_missing_defaults(app, client, login, make_user, seed_finance):
    user_id = make_user("budget-month-missing@example.com")
    seed_finance(user_id)
    assert login("budget-month-missing@example.com").status_code == 302

    response = client.get("/budgets/", follow_redirects=True)
    assert response.status_code == 200
    assert _month_input_value(response) == date.today().strftime("%Y-%m")


def test_edit_unused_category_kind_succeeds(app, client, login, make_user):
    user_id = make_user("category-kind-unused@example.com")
    assert login("category-kind-unused@example.com").status_code == 302

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
        f"/finance/categories/{category_id}/edit",
        data={
            "edit-name": "Side Projects",
            "edit-kind": "income",
            "edit-color": "#123456",
            "edit-submit": "Add category",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Category updated." in response.data

    with app.app_context():
        category = db.session.get(Category, category_id)
        assert category is not None
        assert category.kind == "income"


def test_edit_category_kind_linked_to_transactions_is_blocked(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("category-kind-transactions@example.com")
    setup = seed_finance(user_id)
    assert login("category-kind-transactions@example.com").status_code == 302

    with app.app_context():
        tx = Transaction(
            user_id=user_id,
            transaction_type="expense",
            amount=Decimal("25.00"),
            description="Linked transaction",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            category_id=setup["expense_category_id"],
        )
        db.session.add(tx)
        db.session.commit()
        category_id = setup["expense_category_id"]
        transaction_id = tx.id

    response = client.post(
        f"/finance/categories/{category_id}/edit",
        data={
            "edit-name": "Groceries",
            "edit-kind": "income",
            "edit-color": "#123456",
            "edit-submit": "Add category",
        },
        follow_redirects=True,
    )

    assert response.status_code == 409
    assert b"Category type cannot be changed after it is used by budgets or transactions." in response.data

    with app.app_context():
        category = db.session.get(Category, category_id)
        assert category is not None
        assert category.kind == "expense"
        tx = db.session.get(Transaction, transaction_id)
        assert tx is not None
        assert tx.category_id == category_id

    transaction_edit = client.post(
        f"/transactions/{transaction_id}/edit",
        data={
            "edit-transaction_type": "expense",
            "edit-account_id": str(setup["checking_id"]),
            "edit-to_account_id": "0",
            "edit-category_id": str(category_id),
            "edit-amount": "30.00",
            "edit-occurred_on": date.today().isoformat(),
            "edit-description": "Still valid",
            "edit-notes": "",
            "edit-tag_names": "",
            "edit-submit": "Save transaction",
        },
        follow_redirects=True,
    )
    assert transaction_edit.status_code == 200
    assert b"Transaction updated." in transaction_edit.data


def test_edit_category_kind_linked_to_budgets_is_blocked(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("category-kind-budgets@example.com")
    setup = seed_finance(user_id)
    assert login("category-kind-budgets@example.com").status_code == 302

    with app.app_context():
        budget = Budget(
            user_id=user_id,
            category_id=setup["expense_category_id"],
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("200.00"),
        )
        db.session.add(budget)
        db.session.commit()
        category_id = setup["expense_category_id"]

    response = client.post(
        f"/finance/categories/{category_id}/edit",
        data={
            "edit-name": "Groceries",
            "edit-kind": "income",
            "edit-color": "#123456",
            "edit-submit": "Add category",
        },
        follow_redirects=True,
    )

    assert response.status_code == 409
    assert b"Category type cannot be changed after it is used by budgets or transactions." in response.data

    with app.app_context():
        category = db.session.get(Category, category_id)
        assert category is not None
        assert category.kind == "expense"
        rows = get_budget_progress_rows(user_id, date.today().replace(day=1))
        assert len(rows) == 1
        assert rows[0]["budget"].category_id == category_id


def test_delete_category_without_budgets_succeeds(app, client, login, make_user):
    user_id = make_user("category-delete-empty@example.com")
    assert login("category-delete-empty@example.com").status_code == 302

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


def test_delete_category_with_budgets_is_blocked(app, client, login, make_user):
    user_id = make_user("category-delete-budgeted@example.com")
    assert login("category-delete-budgeted@example.com").status_code == 302

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


def test_transaction_edit_and_delete_flow(app, client, login, make_user, seed_finance):
    user_id = make_user("transaction-crud@example.com")
    setup = seed_finance(user_id)
    assert login("transaction-crud@example.com").status_code == 302

    with app.app_context():
        tx = Transaction(
            user_id=user_id,
            transaction_type="expense",
            amount=Decimal("30.00"),
            description="Initial expense",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            category_id=setup["expense_category_id"],
        )
        db.session.add(tx)
        db.session.commit()
        tx_id = tx.id

    edit_get = client.get(f"/transactions/{tx_id}/edit")
    assert edit_get.status_code == 200

    edit_post = client.post(
        f"/transactions/{tx_id}/edit",
        data={
            "edit-transaction_type": "expense",
            "edit-account_id": str(setup["checking_id"]),
            "edit-to_account_id": "0",
            "edit-category_id": str(setup["expense_category_id"]),
            "edit-amount": "45.00",
            "edit-occurred_on": date.today().isoformat(),
            "edit-description": "Updated expense",
            "edit-notes": "Adjusted after review",
            "edit-tag_names": "reviewed, updated",
            "edit-submit": "Save transaction",
        },
        follow_redirects=True,
    )
    assert edit_post.status_code == 200
    assert b"Transaction updated." in edit_post.data

    with app.app_context():
        tx = db.session.get(Transaction, tx_id)
        assert tx is not None
        assert tx.amount == Decimal("45.00")
        assert tx.description == "Updated expense"
        assert tx.notes == "Adjusted after review"
        assert {tag.name for tag in tx.tags} == {"reviewed", "updated"}

    delete_post = client.post(
        f"/transactions/{tx_id}/delete",
        data={"submit": "Delete"},
        follow_redirects=True,
    )
    assert delete_post.status_code == 200
    assert b"Transaction deleted." in delete_post.data

    with app.app_context():
        assert db.session.get(Transaction, tx_id) is None


def test_transaction_edit_rejects_archived_account(app, client, login, make_user, seed_finance):
    user_id = make_user("edit-archived-account@example.com")
    setup = seed_finance(user_id)
    assert login("edit-archived-account@example.com").status_code == 302

    with app.app_context():
        archived_account = Account(
            user_id=user_id,
            name="Archived Cash",
            account_type="cash",
            opening_balance=Decimal("0.00"),
            is_active=False,
        )
        tx = Transaction(
            user_id=user_id,
            transaction_type="expense",
            amount=Decimal("30.00"),
            description="Editable expense",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            category_id=setup["expense_category_id"],
        )
        db.session.add_all([archived_account, tx])
        db.session.commit()
        tx_id = tx.id
        archived_account_id = archived_account.id

    response = client.post(
        f"/transactions/{tx_id}/edit",
        data={
            "edit-transaction_type": "expense",
            "edit-account_id": str(archived_account_id),
            "edit-to_account_id": "0",
            "edit-category_id": str(setup["expense_category_id"]),
            "edit-amount": "35.00",
            "edit-occurred_on": date.today().isoformat(),
            "edit-description": "Editable expense",
            "edit-notes": "",
            "edit-tag_names": "",
            "edit-submit": "Save transaction",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert _field_error_text(response, "edit-account_id") == "Select an active account."

    with app.app_context():
        tx = db.session.get(Transaction, tx_id)
        assert tx is not None
        assert tx.account_id == setup["checking_id"]


def test_transaction_edit_renders_current_archived_transfer_accounts(app, client, login, make_user):
    user_id = make_user("edit-archived-transfer-render@example.com")
    assert login("edit-archived-transfer-render@example.com").status_code == 302

    with app.app_context():
        checking = Account(
            user_id=user_id,
            name="Checking",
            account_type="checking",
            opening_balance=Decimal("100.00"),
        )
        savings = Account(
            user_id=user_id,
            name="Savings",
            account_type="savings",
            opening_balance=Decimal("50.00"),
        )
        db.session.add_all([checking, savings])
        db.session.commit()

        tx = Transaction(
            user_id=user_id,
            transaction_type="transfer",
            amount=Decimal("30.00"),
            description="Archived transfer",
            occurred_on=date.today(),
            account_id=checking.id,
            transfer_account_id=savings.id,
        )
        db.session.add(tx)
        db.session.commit()

        checking.is_active = False
        savings.is_active = False
        db.session.commit()
        tx_id = tx.id
        checking_id = checking.id
        savings_id = savings.id

    response = client.get(f"/transactions/{tx_id}/edit")
    assert response.status_code == 200

    account_html = _select_inner_html(response, "edit-account_id")
    destination_html = _select_inner_html(response, "edit-to_account_id")
    assert f'value="{checking_id}"' in account_html
    assert "Checking (archived)" in account_html
    assert f'value="{savings_id}"' in destination_html
    assert "Savings (archived)" in destination_html


def test_transaction_edit_round_trips_archived_transfer_accounts_without_mutation(
    app, client, login, make_user
):
    user_id = make_user("edit-archived-transfer-roundtrip@example.com")
    assert login("edit-archived-transfer-roundtrip@example.com").status_code == 302

    with app.app_context():
        checking = Account(
            user_id=user_id,
            name="Checking",
            account_type="checking",
            opening_balance=Decimal("100.00"),
        )
        savings = Account(
            user_id=user_id,
            name="Savings",
            account_type="savings",
            opening_balance=Decimal("50.00"),
        )
        expense_category = Category(
            user_id=user_id,
            name="Groceries",
            kind="expense",
            color="#873f2d",
        )
        db.session.add_all([checking, savings, expense_category])
        db.session.commit()

        tx = Transaction(
            user_id=user_id,
            transaction_type="transfer",
            amount=Decimal("30.00"),
            description="Archived transfer",
            occurred_on=date.today(),
            account_id=checking.id,
            transfer_account_id=savings.id,
        )
        db.session.add(tx)
        db.session.commit()

        checking.is_active = False
        savings.is_active = False
        db.session.commit()
        tx_id = tx.id
        checking_id = checking.id
        savings_id = savings.id

    response = client.post(
        f"/transactions/{tx_id}/edit",
        data={
            "edit-transaction_type": "transfer",
            "edit-account_id": str(checking_id),
            "edit-to_account_id": str(savings_id),
            "edit-category_id": "0",
            "edit-amount": "30.00",
            "edit-occurred_on": date.today().isoformat(),
            "edit-description": "Archived transfer updated",
            "edit-notes": "changed notes only",
            "edit-tag_names": "",
            "edit-submit": "Save transaction",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Transaction updated." in response.data

    with app.app_context():
        tx = db.session.get(Transaction, tx_id)
        assert tx is not None
        assert tx.account_id == checking_id
        assert tx.transfer_account_id == savings_id
        assert tx.description == "Archived transfer updated"
        assert tx.notes == "changed notes only"


def test_delete_transaction_without_tags_does_not_warn(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("delete-no-tags@example.com")
    setup = seed_finance(user_id)
    assert login("delete-no-tags@example.com").status_code == 302

    with app.app_context():
        tx = Transaction(
            user_id=user_id,
            transaction_type="expense",
            amount=Decimal("30.00"),
            description="No tag expense",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            category_id=setup["expense_category_id"],
        )
        db.session.add(tx)
        db.session.commit()
        tx_id = tx.id

    response, caught = _delete_transaction_and_capture_warnings(client, tx_id)
    assert response.status_code == 200
    assert not any(issubclass(item.category, SAWarning) for item in caught)

    with app.app_context():
        assert db.session.get(Transaction, tx_id) is None
        assert db.session.query(TransactionTag).count() == 0
        assert db.session.query(Tag).filter_by(user_id=user_id).count() == 0


def test_delete_transaction_with_one_tag_cleans_association_rows(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("delete-one-tag@example.com")
    setup = seed_finance(user_id)
    assert login("delete-one-tag@example.com").status_code == 302

    with app.app_context():
        tag = Tag(user_id=user_id, name="commute", color="#123456")
        tx = Transaction(
            user_id=user_id,
            transaction_type="expense",
            amount=Decimal("30.00"),
            description="One tag expense",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            category_id=setup["expense_category_id"],
        )
        db.session.add_all([tag, tx])
        db.session.flush()
        tx.tags.append(tag)
        db.session.commit()
        tx_id = tx.id
        tag_id = tag.id

    response, caught = _delete_transaction_and_capture_warnings(client, tx_id)
    assert response.status_code == 200
    assert not any(issubclass(item.category, SAWarning) for item in caught)

    with app.app_context():
        assert db.session.get(Transaction, tx_id) is None
        assert db.session.query(TransactionTag).count() == 0
        remaining_tag = db.session.get(Tag, tag_id)
        assert remaining_tag is not None
        assert remaining_tag.user_id == user_id


def test_delete_transaction_with_multiple_tags_cleans_association_rows(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("delete-multi-tag@example.com")
    setup = seed_finance(user_id)
    assert login("delete-multi-tag@example.com").status_code == 302

    with app.app_context():
        tags = [
            Tag(user_id=user_id, name="work", color="#123456"),
            Tag(user_id=user_id, name="lunch", color="#654321"),
        ]
        tx = Transaction(
            user_id=user_id,
            transaction_type="expense",
            amount=Decimal("42.00"),
            description="Multiple tag expense",
            occurred_on=date.today(),
            account_id=setup["checking_id"],
            category_id=setup["expense_category_id"],
        )
        db.session.add_all(tags + [tx])
        db.session.flush()
        for tag in tags:
            tx.tags.append(tag)
        db.session.commit()
        tx_id = tx.id
        tag_ids = [tag.id for tag in tags]

    response, caught = _delete_transaction_and_capture_warnings(client, tx_id)
    assert response.status_code == 200
    assert not any(issubclass(item.category, SAWarning) for item in caught)

    with app.app_context():
        assert db.session.get(Transaction, tx_id) is None
        assert db.session.query(TransactionTag).count() == 0
        surviving_tags = db.session.query(Tag).filter(Tag.id.in_(tag_ids)).all()
        assert len(surviving_tags) == 2
        assert {tag.user_id for tag in surviving_tags} == {user_id}


def test_analytics_page_loads_without_data(app, client, login, make_user):
    make_user("analytics-empty@example.com")
    assert login("analytics-empty@example.com").status_code == 302

    response = client.get("/analytics/")
    assert response.status_code == 200
    assert b"Analytics" in response.data
    assert b"Not enough data" in response.data
    assert b"flowChart" in response.data
    assert response.data.count(b"chart-shell") == 2


def test_analytics_page_loads_with_seeded_transaction_data(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("analytics-seeded@example.com")
    setup = seed_finance(user_id)
    assert login("analytics-seeded@example.com").status_code == 302

    with app.app_context():
        db.session.add_all(
            [
                Transaction(
                    user_id=user_id,
                    transaction_type="income",
                    amount=Decimal("500.00"),
                    description="Seeded income",
                    occurred_on=date.today(),
                    account_id=setup["checking_id"],
                    category_id=setup["income_category_id"],
                ),
                Transaction(
                    user_id=user_id,
                    transaction_type="expense",
                    amount=Decimal("125.00"),
                    description="Seeded expense",
                    occurred_on=date.today(),
                    account_id=setup["checking_id"],
                    category_id=setup["expense_category_id"],
                ),
            ]
        )
        db.session.commit()

    response = client.get("/analytics/")
    assert response.status_code == 200
    assert b"Income vs Expense" in response.data
    assert b"Spend by Category" in response.data
    assert b"categoryChart" in response.data
    assert b"Not enough data" not in response.data
    assert response.data.count(b"chart-shell") == 2


def test_analytics_page_loads_after_saving_a_transaction(app, client, login, make_user, seed_finance):
    user_id = make_user("analytics-after-save@example.com")
    setup = seed_finance(user_id)
    assert login("analytics-after-save@example.com").status_code == 302

    save_response = _create_transaction(
        client,
        {
            "transaction_type": "expense",
            "account_id": setup["checking_id"],
            "category_id": setup["expense_category_id"],
            "amount": "77.00",
            "occurred_on": setup["today"],
            "description": "Analytics seed",
        },
        follow_redirects=True,
    )
    assert save_response.status_code == 200
    assert b"Transaction saved." in save_response.data

    response = client.get("/analytics/")
    assert response.status_code == 200
    assert b"Income vs Expense" in response.data
    assert b"Spend by Category" in response.data


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
