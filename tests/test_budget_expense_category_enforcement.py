from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finance_tracker.extensions import db
from finance_tracker.models import Budget, BudgetValidationError
from finance_tracker.services.dashboard import build_dashboard_snapshot
from finance_tracker.services.reporting import get_budget_progress_rows


def test_forged_budget_request_using_income_category_is_rejected(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("budget-income-request@example.com")
    setup = seed_finance(user_id)
    assert login("budget-income-request@example.com").status_code == 302

    response = client.post(
        "/budgets/",
        data={
            "create-category_id": str(setup["income_category_id"]),
            "create-month_start": date.today().replace(day=1).isoformat(),
            "create-amount_limit": "250.00",
            "create-submit": "Save budget",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Budgets can only be assigned to expense categories." in response.data

    with app.app_context():
        assert Budget.query.filter_by(user_id=user_id).count() == 0


def test_direct_budget_write_using_income_category_is_rejected(app, make_user, seed_finance):
    user_id = make_user("budget-income-direct@example.com")
    setup = seed_finance(user_id)

    with app.app_context():
        budget = Budget(
            user_id=user_id,
            category_id=setup["income_category_id"],
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("150.00"),
        )
        db.session.add(budget)

        with pytest.raises(BudgetValidationError, match="expense categories"):
            db.session.commit()

        db.session.rollback()
        assert Budget.query.filter_by(user_id=user_id).count() == 0


def test_direct_budget_write_using_foreign_user_category_is_rejected(
    app, make_user, seed_finance
):
    owner_id = make_user("budget-foreign-owner@example.com")
    other_user_id = make_user("budget-foreign-category@example.com")
    owner_setup = seed_finance(owner_id)
    other_setup = seed_finance(other_user_id)
    month_start = date.today().replace(day=1)

    with app.app_context():
        foreign_budget = Budget(
            user_id=owner_id,
            category_id=other_setup["expense_category_id"],
            month_start=month_start,
            amount_limit=Decimal("150.00"),
        )
        db.session.add(foreign_budget)

        with pytest.raises(BudgetValidationError, match="your expense categories"):
            db.session.commit()

        db.session.rollback()
        assert Budget.query.filter_by(user_id=owner_id).count() == 0

        valid_budget = Budget(
            user_id=owner_id,
            category_id=owner_setup["expense_category_id"],
            month_start=month_start,
            amount_limit=Decimal("180.00"),
        )
        db.session.add(valid_budget)
        db.session.commit()
        budget_id = valid_budget.id

        valid_budget.category_id = other_setup["expense_category_id"]
        with pytest.raises(BudgetValidationError, match="your expense categories"):
            db.session.commit()

        db.session.rollback()
        saved = db.session.get(Budget, budget_id)
        assert saved is not None
        assert saved.category_id == owner_setup["expense_category_id"]


def test_valid_expense_category_budget_still_succeeds(app, make_user, seed_finance):
    user_id = make_user("budget-expense-direct@example.com")
    setup = seed_finance(user_id)

    with app.app_context():
        budget = Budget(
            user_id=user_id,
            category_id=setup["expense_category_id"],
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("180.00"),
        )
        db.session.add(budget)
        db.session.commit()

        saved = db.session.get(Budget, budget.id)
        assert saved is not None
        assert saved.category_id == setup["expense_category_id"]


def test_budget_edit_with_same_user_expense_category_still_succeeds(
    app, client, login, make_user, seed_finance
):
    user_id = make_user("budget-expense-route-update@example.com")
    setup = seed_finance(user_id)
    assert login("budget-expense-route-update@example.com").status_code == 302

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
        assert budget.category_id == setup["expense_category_id"]
        assert budget.amount_limit == Decimal("180.00")


def test_reporting_and_dashboard_only_surface_valid_expense_budgets(
    app, make_user, seed_finance
):
    user_id = make_user("budget-expense-reporting@example.com")
    setup = seed_finance(user_id)

    with app.app_context():
        valid_budget = Budget(
            user_id=user_id,
            category_id=setup["expense_category_id"],
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("220.00"),
        )
        db.session.add(valid_budget)
        db.session.commit()

        invalid_budget = Budget(
            user_id=user_id,
            category_id=setup["income_category_id"],
            month_start=date.today().replace(day=1),
            amount_limit=Decimal("300.00"),
        )
        db.session.add(invalid_budget)
        with pytest.raises(BudgetValidationError):
            db.session.commit()
        db.session.rollback()

        budget_rows = get_budget_progress_rows(user_id, date.today().replace(day=1))
        snapshot = build_dashboard_snapshot(user_id, month_start=date.today().replace(day=1))

        assert len(budget_rows) == 1
        assert budget_rows[0]["budget"].category.kind == "expense"
        assert len(snapshot["budgets"]) == 1
        assert snapshot["budgets"][0]["budget"].category.kind == "expense"
