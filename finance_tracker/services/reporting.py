from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from finance_tracker.extensions import db
from finance_tracker.models import Budget, Category, Transaction
from finance_tracker.services.transactions import as_decimal


def month_bounds(reference: date | None = None) -> tuple[date, date]:
    today = reference or date.today()
    month_start = today.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1)
    return month_start, month_end


def normalize_month_start(value: date) -> date:
    return value.replace(day=1)


def get_budget_progress_rows(user_id: int, month_start: date) -> list[dict]:
    month_start = normalize_month_start(month_start)
    month_end = (month_start + timedelta(days=32)).replace(day=1)

    budgets = (
        Budget.query.filter_by(user_id=user_id, month_start=month_start)
        .join(Budget.category)
        .order_by(Category.name.asc())
        .all()
    )

    rows: list[dict] = []
    for budget in budgets:
        spent = (
            db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))
            .filter(
                Transaction.user_id == user_id,
                Transaction.transaction_type == "expense",
                Transaction.category_id == budget.category_id,
                Transaction.occurred_on >= month_start,
                Transaction.occurred_on < month_end,
            )
            .scalar()
        )

        spent_amount = as_decimal(spent)
        limit_amount = as_decimal(budget.amount_limit)
        ratio = float((spent_amount / limit_amount) * 100) if limit_amount > 0 else 0.0
        rows.append(
            {
                "budget": budget,
                "spent": spent_amount,
                "limit": limit_amount,
                "remaining": limit_amount - spent_amount,
                "utilization": min(ratio, 170),
                "ratio": min(ratio, 170),
                "is_overspent": spent_amount > limit_amount,
            }
        )
    return rows


def get_monthly_totals(user_id: int, month_start: date) -> dict:
    month_start = normalize_month_start(month_start)
    month_end = (month_start + timedelta(days=32)).replace(day=1)

    total_income = (
        db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "income",
            Transaction.occurred_on >= month_start,
            Transaction.occurred_on < month_end,
        )
        .scalar()
    )
    total_expense = (
        db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "expense",
            Transaction.occurred_on >= month_start,
            Transaction.occurred_on < month_end,
        )
        .scalar()
    )
    total_transfer = (
        db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "transfer",
            Transaction.occurred_on >= month_start,
            Transaction.occurred_on < month_end,
        )
        .scalar()
    )

    income = as_decimal(total_income)
    expense = as_decimal(total_expense)
    transfer = as_decimal(total_transfer)
    return {
        "month_start": month_start,
        "month_end": month_end - timedelta(days=1),
        "income": income,
        "expense": expense,
        "transfer": transfer,
        "net": income - expense,
    }


def build_monthly_summary_series(user_id: int, months: int = 6) -> dict:
    today = date.today().replace(day=1)
    keys = []
    month = today.month
    year = today.year
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month < 1:
            month = 12
            year -= 1
    labels = list(reversed(keys))
    earliest = date(int(labels[0][:4]), int(labels[0][5:7]), 1)
    reporting_window_end = (today + timedelta(days=32)).replace(day=1)

    rows = (
        Transaction.query.filter(
            Transaction.user_id == user_id,
            Transaction.occurred_on >= earliest,
            Transaction.occurred_on < reporting_window_end,
        )
        .order_by(Transaction.occurred_on.asc())
        .all()
    )

    income_by_month = defaultdict(lambda: Decimal("0.00"))
    expense_by_month = defaultdict(lambda: Decimal("0.00"))
    category_spend = defaultdict(lambda: Decimal("0.00"))

    for tx in rows:
        key = tx.occurred_on.strftime("%Y-%m")
        amount = as_decimal(tx.amount)
        if tx.transaction_type == "income":
            income_by_month[key] += amount
        elif tx.transaction_type == "expense":
            expense_by_month[key] += amount
            category_name = tx.category.name if tx.category else "Uncategorized"
            category_spend[category_name] += amount

    income_points = [str(income_by_month[key]) for key in labels]
    expense_points = [str(expense_by_month[key]) for key in labels]

    sorted_categories = sorted(category_spend.items(), key=lambda item: item[1], reverse=True)[:8]
    category_labels = [name for name, _ in sorted_categories]
    category_points = [str(total) for _, total in sorted_categories]

    return {
        "flow_labels": labels,
        "income_points": income_points,
        "expense_points": expense_points,
        "category_labels": category_labels,
        "category_points": category_points,
    }
