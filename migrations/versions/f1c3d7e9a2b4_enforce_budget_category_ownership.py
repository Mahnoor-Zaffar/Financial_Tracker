"""Enforce budget category ownership

Revision ID: f1c3d7e9a2b4
Revises: e5a1b7c2d9f4
Create Date: 2026-04-24 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1c3d7e9a2b4"
down_revision = "e5a1b7c2d9f4"
branch_labels = None
depends_on = None


NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


INVALID_BUDGET_CATEGORY_OWNERSHIP_QUERY = sa.text(
    """
    SELECT
        b.id,
        b.user_id AS budget_user_id,
        b.category_id,
        b.month_start,
        c.user_id AS category_user_id,
        c.kind AS category_kind
    FROM budgets AS b
    LEFT JOIN categories AS c ON c.id = b.category_id
    WHERE c.id IS NULL OR c.user_id != b.user_id OR c.kind != 'expense'
    ORDER BY b.id
    """
)


def find_invalid_budget_category_ownership(connection) -> list[dict]:
    rows = connection.execute(INVALID_BUDGET_CATEGORY_OWNERSHIP_QUERY).mappings().all()
    return [dict(row) for row in rows]


def raise_for_invalid_budget_category_ownership(connection) -> None:
    invalid_rows = find_invalid_budget_category_ownership(connection)
    if not invalid_rows:
        return

    details = "; ".join(
        (
            f"id={row['id']}, budget_user_id={row['budget_user_id']}, "
            f"category_id={row['category_id']}, category_user_id={row['category_user_id']}, "
            f"month_start={row['month_start']}, category_kind={row['category_kind']}"
        )
        for row in invalid_rows
    )
    raise RuntimeError(
        "Cannot enforce budget ownership while budgets reference another user's "
        f"or non-expense category. Repair or remove these rows first: {details}"
    )


def upgrade():
    connection = op.get_bind()
    raise_for_invalid_budget_category_ownership(connection)

    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_categories_id_user", ["id", "user_id"])

    with op.batch_alter_table(
        "budgets",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_budgets_category_id_categories",
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_budgets_category_id_user_id_categories",
            "categories",
            ["category_id", "user_id"],
            ["id", "user_id"],
            ondelete="CASCADE",
        )


def downgrade():
    with op.batch_alter_table(
        "budgets",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_budgets_category_id_user_id_categories",
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_budgets_category_id_categories",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_constraint("uq_categories_id_user", type_="unique")
