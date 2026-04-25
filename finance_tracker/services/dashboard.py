from __future__ import annotations

from datetime import date

from finance_tracker.models import Account, Transaction
from finance_tracker.services.dates import user_local_today_for_user
from finance_tracker.services.reporting import get_budget_progress_rows, get_monthly_totals
from finance_tracker.services.transactions import account_balance_projection


def build_dashboard_snapshot(user_id: int, month_start: date | None = None) -> dict:
    month = month_start or user_local_today_for_user(user_id).replace(day=1)
    monthly_totals = get_monthly_totals(user_id=user_id, month_start=month)

    recent_transactions = (
        Transaction.query.filter_by(user_id=user_id)
        .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
        .limit(8)
        .all()
    )

    active_accounts = (
        Account.query.filter_by(user_id=user_id, is_active=True)
        .order_by(Account.name.asc())
        .all()
    )
    balances = account_balance_projection(user_id)
    account_rows = [
        {"account": account, "balance": balances.get(account.id, 0)}
        for account in active_accounts
    ]

    budget_rows = get_budget_progress_rows(user_id=user_id, month_start=month)
    overspent_count = sum(1 for row in budget_rows if row["is_overspent"])

    return {
        "month_start": monthly_totals["month_start"],
        "month_end": monthly_totals["month_end"],
        "income_total": monthly_totals["income"],
        "expense_total": monthly_totals["expense"],
        "transfer_total": monthly_totals["transfer"],
        "net_total": monthly_totals["net"],
        "recent_transactions": recent_transactions,
        "accounts": account_rows,
        "budgets": budget_rows,
        "overspent_count": overspent_count,
        "has_alerts": overspent_count > 0,
    }
