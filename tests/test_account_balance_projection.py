from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import event

from finance_tracker.extensions import db
from finance_tracker.models import Account, Budget, Category, Transaction
from finance_tracker.services import account_balance, account_balance_projection, get_budget_progress_rows


def _seed_balance_scenario(app, user_id: int) -> dict[str, int]:
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
        archived = Account(
            user_id=user_id,
            name="Archived",
            account_type="cash",
            opening_balance=Decimal("20.00"),
        )
        income_category = Category(
            user_id=user_id,
            name="Salary",
            kind="income",
            color="#255a44",
        )
        expense_category = Category(
            user_id=user_id,
            name="Groceries",
            kind="expense",
            color="#873f2d",
        )
        db.session.add_all([checking, savings, archived, income_category, expense_category])
        db.session.flush()

        transactions = [
            Transaction(
                user_id=user_id,
                transaction_type="income",
                amount=Decimal("1000.00"),
                description="Salary",
                occurred_on=date.today(),
                account_id=checking.id,
                category_id=income_category.id,
            ),
            Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("120.00"),
                description="Groceries",
                occurred_on=date.today(),
                account_id=checking.id,
                category_id=expense_category.id,
            ),
            Transaction(
                user_id=user_id,
                transaction_type="transfer",
                amount=Decimal("200.00"),
                description="Move to savings",
                occurred_on=date.today(),
                account_id=checking.id,
                transfer_account_id=savings.id,
            ),
            Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("15.00"),
                description="Archived spend",
                occurred_on=date.today(),
                account_id=archived.id,
                category_id=expense_category.id,
            ),
        ]
        db.session.add_all(transactions)
        db.session.commit()
        archived.is_active = False
        db.session.commit()

        return {
            "checking_id": checking.id,
            "savings_id": savings.id,
            "archived_id": archived.id,
        }


def _capture_query_count(app, callback) -> int:
    count = {"value": 0}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        count["value"] += 1

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", before_cursor_execute)
        try:
            callback()
        finally:
            event.remove(db.engine, "before_cursor_execute", before_cursor_execute)
    return count["value"]


def _seed_budget_progress_scenario(app, user_id: int, budget_count: int = 3) -> dict:
    month_start = date.today().replace(day=1)

    with app.app_context():
        account = Account(
            user_id=user_id,
            name="Budget Checking",
            account_type="checking",
            opening_balance=Decimal("0.00"),
        )
        categories = [
            Category(
                user_id=user_id,
                name=f"Budget Category {index}",
                kind="expense",
                color="#873f2d",
            )
            for index in range(budget_count)
        ]
        db.session.add_all([account, *categories])
        db.session.flush()

        budgets = [
            Budget(
                user_id=user_id,
                category_id=category.id,
                month_start=month_start,
                amount_limit=Decimal("100.00"),
            )
            for category in categories
        ]
        db.session.add_all(budgets)
        db.session.flush()

        transactions = [
            Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("30.00"),
                description="First category spend",
                occurred_on=month_start,
                account_id=account.id,
                category_id=categories[0].id,
            ),
            Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("25.00"),
                description="More first category spend",
                occurred_on=month_start + timedelta(days=1),
                account_id=account.id,
                category_id=categories[0].id,
            ),
            Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("125.00"),
                description="Overspent category",
                occurred_on=month_start + timedelta(days=2),
                account_id=account.id,
                category_id=categories[1].id,
            ),
            Transaction(
                user_id=user_id,
                transaction_type="expense",
                amount=Decimal("99.00"),
                description="Outside month spend",
                occurred_on=(month_start + timedelta(days=32)).replace(day=1),
                account_id=account.id,
                category_id=categories[0].id,
            ),
        ]
        db.session.add_all(transactions)
        db.session.commit()

        return {
            "month_start": month_start,
            "category_ids": [category.id for category in categories],
        }


def test_grouped_balance_projection_preserves_balance_correctness(app, make_user):
    user_id = make_user("balance-projection@example.com")
    ids = _seed_balance_scenario(app, user_id)

    with app.app_context():
        balances = account_balance_projection(user_id)
        assert balances[ids["checking_id"]] == Decimal("780.00")
        assert balances[ids["savings_id"]] == Decimal("250.00")
        assert balances[ids["archived_id"]] == Decimal("5.00")

        assert account_balance(ids["checking_id"], user_id) == Decimal("780.00")
        assert account_balance(ids["savings_id"], user_id) == Decimal("250.00")
        assert account_balance(ids["archived_id"], user_id) == Decimal("5.00")


def test_budget_progress_grouped_query_preserves_row_semantics(app, make_user):
    user_id = make_user("budget-progress-grouped@example.com")
    setup = _seed_budget_progress_scenario(app, user_id)

    with app.app_context():
        rows = get_budget_progress_rows(user_id, setup["month_start"])

    assert [row["budget"].category_id for row in rows] == setup["category_ids"]
    assert [row["spent"] for row in rows] == [
        Decimal("55.00"),
        Decimal("125.00"),
        Decimal("0.00"),
    ]
    assert [row["limit"] for row in rows] == [
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("100.00"),
    ]
    assert [row["remaining"] for row in rows] == [
        Decimal("45.00"),
        Decimal("-25.00"),
        Decimal("100.00"),
    ]
    assert [row["ratio"] for row in rows] == [55.0, 125.0, 0.0]
    assert [row["utilization"] for row in rows] == [55.0, 125.0, 0.0]
    assert [row["is_overspent"] for row in rows] == [False, True, False]


def test_budget_progress_query_count_is_flat_across_budget_rows(app, make_user):
    user_id = make_user("budget-progress-query-count@example.com")
    setup = _seed_budget_progress_scenario(app, user_id, budget_count=5)

    query_count = _capture_query_count(
        app, lambda: get_budget_progress_rows(user_id, setup["month_start"])
    )

    assert query_count == 2


def test_dashboard_query_count_is_capped(app, client, login, make_user):
    user_id = make_user("dashboard-query-count@example.com")
    _seed_balance_scenario(app, user_id)

    with app.app_context():
        for index in range(4):
            db.session.add(
                Account(
                    user_id=user_id,
                    name=f"Extra {index}",
                    account_type="checking",
                    opening_balance=Decimal("10.00"),
                )
            )
        db.session.commit()

    assert login("dashboard-query-count@example.com").status_code == 302

    query_count = _capture_query_count(app, lambda: client.get("/dashboard"))
    assert query_count <= 30


def test_accounts_page_query_count_is_capped(app, client, login, make_user):
    user_id = make_user("accounts-query-count@example.com")
    _seed_balance_scenario(app, user_id)

    with app.app_context():
        for index in range(5):
            db.session.add(
                Account(
                    user_id=user_id,
                    name=f"List {index}",
                    account_type="checking",
                    opening_balance=Decimal("25.00"),
                )
            )
        db.session.commit()

    assert login("accounts-query-count@example.com").status_code == 302

    query_count = _capture_query_count(app, lambda: client.get("/finance/accounts"))
    assert query_count <= 22
