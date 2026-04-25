"""Add case-insensitive account name key

Revision ID: a3f4c2d8e9b1
Revises: f1c3d7e9a2b4
Create Date: 2026-04-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a3f4c2d8e9b1"
down_revision = "f1c3d7e9a2b4"
branch_labels = None
depends_on = None


def _account_name_key(name: str | None) -> str:
    return (name or "").strip().casefold()


def upgrade():
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("name_key", sa.String(length=255), nullable=True))

    connection = op.get_bind()
    rows = (
        connection.execute(sa.text("SELECT id, user_id, name FROM accounts"))
        .mappings()
        .all()
    )

    seen = {}
    duplicates = []
    for row in rows:
        key = (row["user_id"], _account_name_key(row["name"]))
        if key in seen:
            duplicates.append((seen[key], row["id"], row["user_id"], row["name"]))
        else:
            seen[key] = row["id"]
        connection.execute(
            sa.text("UPDATE accounts SET name_key = :name_key WHERE id = :id"),
            {"name_key": key[1], "id": row["id"]},
        )

    if duplicates:
        details = ", ".join(
            f"user_id={user_id} account_ids={first_id}/{second_id} name={name!r}"
            for first_id, second_id, user_id, name in duplicates
        )
        raise RuntimeError(
            "Cannot add case-insensitive account name constraint until duplicate "
            f"account names are resolved: {details}"
        )

    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.alter_column("name_key", existing_type=sa.String(length=255), nullable=False)
        batch_op.create_unique_constraint(
            "uq_accounts_user_name_key", ["user_id", "name_key"]
        )


def downgrade():
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.drop_constraint("uq_accounts_user_name_key", type_="unique")
        batch_op.drop_column("name_key")
