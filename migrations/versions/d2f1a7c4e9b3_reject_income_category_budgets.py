"""Reject income category budgets

Revision ID: d2f1a7c4e9b3
Revises: 8a1d9c6e4b2f
Create Date: 2026-04-23 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d2f1a7c4e9b3"
down_revision = "8a1d9c6e4b2f"
branch_labels = None
depends_on = None


INVALID_BUDGET_CATEGORY_QUERY = sa.text(
    """
    SELECT
        b.id,
        b.user_id,
        b.category_id,
        b.month_start,
        c.kind AS category_kind
    FROM budgets AS b
    LEFT JOIN categories AS c ON c.id = b.category_id
    WHERE c.id IS NULL OR c.kind != 'expense'
    ORDER BY b.id
    """
)


def find_invalid_budget_categories(connection) -> list[dict]:
    rows = connection.execute(INVALID_BUDGET_CATEGORY_QUERY).mappings().all()
    return [dict(row) for row in rows]


def raise_for_invalid_budget_categories(connection) -> None:
    invalid_rows = find_invalid_budget_categories(connection)
    if not invalid_rows:
        return

    details = "; ".join(
        (
            f"id={row['id']}, user_id={row['user_id']}, "
            f"category_id={row['category_id']}, month_start={row['month_start']}, "
            f"category_kind={row['category_kind']}"
        )
        for row in invalid_rows
    )
    raise RuntimeError(
        "Cannot continue while budgets reference non-expense categories. "
        f"Repair or remove these rows first: {details}"
    )


def upgrade():
    connection = op.get_bind()
    raise_for_invalid_budget_categories(connection)


def downgrade():
    pass
