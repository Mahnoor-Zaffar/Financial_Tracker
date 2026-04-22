"""Normalize budget months

Revision ID: 8a1d9c6e4b2f
Revises: 4f7b9f2de6c1
Create Date: 2026-04-23 13:15:00.000000

"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8a1d9c6e4b2f"
down_revision = "4f7b9f2de6c1"
branch_labels = None
depends_on = None


def _as_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise TypeError(f"Unsupported date value: {value!r}")


def _as_datetime(value) -> datetime:
    if value is None:
        return datetime.min
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.fromisoformat(normalized[:19])
    raise TypeError(f"Unsupported datetime value: {value!r}")


def _normalized_month(value) -> date:
    return _as_date(value).replace(day=1)


def find_budget_month_conflicts(connection) -> dict:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                id,
                user_id,
                category_id,
                month_start,
                amount_limit,
                created_at,
                updated_at
            FROM budgets
            ORDER BY id
            """
        )
    ).mappings().all()

    normalized_rows = []
    non_normalized_ids = []
    groups: dict[tuple[int, int, date], list[dict]] = defaultdict(list)

    for raw_row in rows:
        row = dict(raw_row)
        normalized_month = _normalized_month(row["month_start"])
        row["normalized_month_start"] = normalized_month
        normalized_rows.append(row)
        groups[(row["user_id"], row["category_id"], normalized_month)].append(row)
        if _as_date(row["month_start"]) != normalized_month:
            non_normalized_ids.append(row["id"])

    duplicate_groups = []
    for (user_id, category_id, month_start), group_rows in groups.items():
        if len(group_rows) > 1:
            duplicate_groups.append(
                {
                    "user_id": user_id,
                    "category_id": category_id,
                    "month_start": month_start,
                    "budget_ids": [row["id"] for row in group_rows],
                }
            )

    return {
        "rows": normalized_rows,
        "non_normalized_ids": non_normalized_ids,
        "duplicate_groups": duplicate_groups,
    }


def normalize_and_deduplicate_budgets(connection) -> dict:
    conflicts = find_budget_month_conflicts(connection)
    rows = conflicts["rows"]

    groups: dict[tuple[int, int, date], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["user_id"], row["category_id"], row["normalized_month_start"])].append(row)

    updated_ids: list[int] = []
    deleted_ids: list[int] = []

    for (_user_id, _category_id, normalized_month), group_rows in groups.items():
        ordered = sorted(
            group_rows,
            key=lambda row: (
                _as_datetime(row["updated_at"]),
                _as_datetime(row["created_at"]),
                row["id"],
            ),
            reverse=True,
        )
        keep = ordered[0]
        if _as_date(keep["month_start"]) != normalized_month:
            connection.execute(
                sa.text(
                    """
                    UPDATE budgets
                    SET month_start = :month_start
                    WHERE id = :budget_id
                    """
                ),
                {"month_start": normalized_month.isoformat(), "budget_id": keep["id"]},
            )
            updated_ids.append(keep["id"])

        for duplicate in ordered[1:]:
            connection.execute(
                sa.text("DELETE FROM budgets WHERE id = :budget_id"),
                {"budget_id": duplicate["id"]},
            )
            deleted_ids.append(duplicate["id"])

    return {
        "non_normalized_ids": conflicts["non_normalized_ids"],
        "duplicate_groups": conflicts["duplicate_groups"],
        "updated_ids": updated_ids,
        "deleted_ids": deleted_ids,
    }


def upgrade():
    connection = op.get_bind()
    normalize_and_deduplicate_budgets(connection)


def downgrade():
    pass
