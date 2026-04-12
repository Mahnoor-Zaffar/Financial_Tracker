from __future__ import annotations

from finance_tracker.services.reporting import build_monthly_summary_series


def build_analytics_snapshot(user_id: int, months: int = 6) -> dict:
    return build_monthly_summary_series(user_id=user_id, months=months)
