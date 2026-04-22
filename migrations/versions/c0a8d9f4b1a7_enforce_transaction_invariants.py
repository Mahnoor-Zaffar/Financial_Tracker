"""Enforce transaction invariants

Revision ID: c0a8d9f4b1a7
Revises: 58228b117fe8
Create Date: 2026-04-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c0a8d9f4b1a7"
down_revision = "58228b117fe8"
branch_labels = None
depends_on = None


INVALID_TRANSACTION_QUERY = sa.text(
    """
    SELECT
        t.id,
        t.transaction_type,
        t.account_id,
        t.transfer_account_id,
        t.category_id,
        c.kind AS category_kind
    FROM transactions AS t
    LEFT JOIN categories AS c ON c.id = t.category_id
    WHERE
        (t.transaction_type IN ('income', 'expense') AND t.category_id IS NULL)
        OR (t.transaction_type = 'transfer' AND t.transfer_account_id IS NULL)
        OR (t.transaction_type = 'transfer' AND t.category_id IS NOT NULL)
        OR (t.transfer_account_id IS NOT NULL AND t.account_id = t.transfer_account_id)
        OR (
            t.transaction_type IN ('income', 'expense')
            AND t.category_id IS NOT NULL
            AND (c.id IS NULL OR c.kind != t.transaction_type)
        )
    ORDER BY t.id
    """
)


def find_invalid_transactions(connection) -> list[dict]:
    rows = connection.execute(INVALID_TRANSACTION_QUERY).mappings().all()
    return [dict(row) for row in rows]


def raise_for_invalid_transactions(connection) -> None:
    invalid_rows = find_invalid_transactions(connection)
    if not invalid_rows:
        return

    details = "; ".join(
        (
            f"id={row['id']}, type={row['transaction_type']}, "
            f"account_id={row['account_id']}, "
            f"transfer_account_id={row['transfer_account_id']}, "
            f"category_id={row['category_id']}, "
            f"category_kind={row['category_kind']}"
        )
        for row in invalid_rows
    )
    raise RuntimeError(
        "Cannot apply transaction invariant constraints until invalid transactions "
        f"are repaired. Invalid rows: {details}"
    )


def upgrade():
    connection = op.get_bind()
    raise_for_invalid_transactions(connection)

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_transactions_required_links",
            "("
            "(transaction_type IN ('income', 'expense') "
            "AND category_id IS NOT NULL "
            "AND transfer_account_id IS NULL)"
            " OR "
            "(transaction_type = 'transfer' "
            "AND transfer_account_id IS NOT NULL "
            "AND category_id IS NULL)"
            ")",
        )
        batch_op.create_check_constraint(
            "ck_transactions_distinct_transfer_accounts",
            "transfer_account_id IS NULL OR account_id != transfer_account_id",
        )


def downgrade():
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_transactions_distinct_transfer_accounts", type_="check")
        batch_op.drop_constraint("ck_transactions_required_links", type_="check")
