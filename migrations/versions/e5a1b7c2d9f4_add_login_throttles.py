"""Add login throttles

Revision ID: e5a1b7c2d9f4
Revises: d2f1a7c4e9b3
Create Date: 2026-04-23 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e5a1b7c2d9f4"
down_revision = "d2f1a7c4e9b3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_throttles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "key", name="uq_login_throttles_scope_key"),
    )
    with op.batch_alter_table("login_throttles", schema=None) as batch_op:
        batch_op.create_index("ix_login_throttles_blocked_until", ["blocked_until"], unique=False)


def downgrade():
    with op.batch_alter_table("login_throttles", schema=None) as batch_op:
        batch_op.drop_index("ix_login_throttles_blocked_until")
    op.drop_table("login_throttles")
