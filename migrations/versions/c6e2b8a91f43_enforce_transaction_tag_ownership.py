"""Enforce transaction tag ownership

Revision ID: c6e2b8a91f43
Revises: b7e6a4c1d2f3
Create Date: 2026-04-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c6e2b8a91f43"
down_revision = "b7e6a4c1d2f3"
branch_labels = None
depends_on = None


NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


INVALID_TRANSACTION_TAG_OWNERSHIP_QUERY = sa.text(
    """
    SELECT
        tt.transaction_id,
        tx.user_id AS transaction_user_id,
        tt.tag_id,
        tag.user_id AS tag_user_id
    FROM transaction_tags AS tt
    LEFT JOIN transactions AS tx ON tx.id = tt.transaction_id
    LEFT JOIN tags AS tag ON tag.id = tt.tag_id
    WHERE tx.id IS NULL OR tag.id IS NULL OR tx.user_id != tag.user_id
    ORDER BY tt.transaction_id, tt.tag_id
    """
)


def find_invalid_transaction_tag_ownership(connection) -> list[dict]:
    rows = (
        connection.execute(INVALID_TRANSACTION_TAG_OWNERSHIP_QUERY)
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def raise_for_invalid_transaction_tag_ownership(connection) -> None:
    invalid_rows = find_invalid_transaction_tag_ownership(connection)
    if not invalid_rows:
        return

    details = "; ".join(
        (
            f"transaction_id={row['transaction_id']}, "
            f"transaction_user_id={row['transaction_user_id']}, "
            f"tag_id={row['tag_id']}, tag_user_id={row['tag_user_id']}"
        )
        for row in invalid_rows
    )
    raise RuntimeError(
        "Cannot enforce transaction tag ownership while transaction_tags links "
        f"cross users. Repair or remove these rows first: {details}"
    )


def upgrade():
    connection = op.get_bind()
    raise_for_invalid_transaction_tag_ownership(connection)

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_transactions_id_user", ["id", "user_id"]
        )

    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_tags_id_user", ["id", "user_id"])

    with op.batch_alter_table(
        "transaction_tags",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_transaction_tags_transaction_id_transactions",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_transaction_tags_tag_id_tags",
            type_="foreignkey",
        )
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    connection.execute(
        sa.text(
            """
            UPDATE transaction_tags
            SET user_id = (
                SELECT transactions.user_id
                FROM transactions
                WHERE transactions.id = transaction_tags.transaction_id
            )
            """
        )
    )

    with op.batch_alter_table(
        "transaction_tags",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_transaction_tags_transaction_user_transactions",
            "transactions",
            ["transaction_id", "user_id"],
            ["id", "user_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_transaction_tags_tag_user_tags",
            "tags",
            ["tag_id", "user_id"],
            ["id", "user_id"],
            ondelete="CASCADE",
        )


def downgrade():
    with op.batch_alter_table(
        "transaction_tags",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_transaction_tags_tag_user_tags",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_transaction_tags_transaction_user_transactions",
            type_="foreignkey",
        )
        batch_op.drop_column("user_id")
        batch_op.create_foreign_key(
            "fk_transaction_tags_transaction_id_transactions",
            "transactions",
            ["transaction_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_transaction_tags_tag_id_tags",
            "tags",
            ["tag_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.drop_constraint("uq_tags_id_user", type_="unique")

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_transactions_id_user", type_="unique")
