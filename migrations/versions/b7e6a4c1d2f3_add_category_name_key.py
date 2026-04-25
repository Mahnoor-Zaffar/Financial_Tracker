"""Add case-insensitive category name key

Revision ID: b7e6a4c1d2f3
Revises: a3f4c2d8e9b1
Create Date: 2026-04-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "b7e6a4c1d2f3"
down_revision = "a3f4c2d8e9b1"
branch_labels = None
depends_on = None


def _category_name_key(name: str | None) -> str:
    return (name or "").strip().casefold()


def upgrade():
    connection = op.get_bind()
    rows = (
        connection.execute(sa.text("SELECT id, user_id, name, kind FROM categories"))
        .mappings()
        .all()
    )

    seen = {}
    duplicates = []
    for row in rows:
        key = (row["user_id"], row["kind"], _category_name_key(row["name"]))
        if key in seen:
            duplicates.append(
                (seen[key], row["id"], row["user_id"], row["kind"], row["name"])
            )
        else:
            seen[key] = row["id"]

    if duplicates:
        details = ", ".join(
            f"user_id={user_id} kind={kind} category_ids={first_id}/{second_id} name={name!r}"
            for first_id, second_id, user_id, kind, name in duplicates
        )
        raise RuntimeError(
            "Cannot add case-insensitive category name constraint until duplicate "
            f"category names are resolved: {details}"
        )

    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.add_column(sa.Column("name_key", sa.String(length=255), nullable=True))

    for row in rows:
        connection.execute(
            sa.text("UPDATE categories SET name_key = :name_key WHERE id = :id"),
            {"name_key": _category_name_key(row["name"]), "id": row["id"]},
        )

    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.alter_column("name_key", existing_type=sa.String(length=255), nullable=False)
        batch_op.create_unique_constraint(
            "uq_categories_user_name_key_kind", ["user_id", "name_key", "kind"]
        )


def downgrade():
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_constraint("uq_categories_user_name_key_kind", type_="unique")
        batch_op.drop_column("name_key")
