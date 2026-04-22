"""Block category deletion when referenced

Revision ID: 4f7b9f2de6c1
Revises: c0a8d9f4b1a7
Create Date: 2026-04-23 12:30:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "4f7b9f2de6c1"
down_revision = "c0a8d9f4b1a7"
branch_labels = None
depends_on = None


NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade():
    with op.batch_alter_table(
        "transactions",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_transactions_category_id_categories",
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_transactions_category_id_categories",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade():
    with op.batch_alter_table(
        "transactions",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_transactions_category_id_categories",
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_transactions_category_id_categories",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="SET NULL",
        )
