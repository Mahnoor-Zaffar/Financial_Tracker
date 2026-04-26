from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from finance_tracker import create_app
from finance_tracker.extensions import db


ROOT_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    config = Config(str(ROOT_DIR / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT_DIR / "migrations"))
    return config


def test_sqlite_upgrade_rebuilds_categories_with_existing_references(tmp_path):
    app = create_app("testing")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'migration.db'}",
        SECRET_KEY="test-secret-key",
        TESTING=True,
    )

    with app.app_context():
        command.upgrade(_alembic_config(), "e5a1b7c2d9f4")

        with db.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, email, password_hash, full_name, currency_code,
                        timezone, is_active, created_at, updated_at
                    ) VALUES (
                        1, 'migration-user@example.com', 'hash', 'Migration User',
                        'USD', 'UTC', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO accounts (
                        id, name, account_type, institution, opening_balance,
                        is_active, user_id, created_at, updated_at
                    ) VALUES (
                        1, 'Checking', 'checking', NULL, 0, 1, 1,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO categories (
                        id, name, kind, color, user_id, created_at, updated_at
                    ) VALUES (
                        1, 'Groceries', 'expense', '#873f2d', 1,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO budgets (
                        id, category_id, month_start, amount_limit, user_id,
                        created_at, updated_at
                    ) VALUES (
                        1, 1, '2026-04-01', 100, 1,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO transactions (
                        id, transaction_type, amount, description, notes,
                        occurred_on, account_id, transfer_account_id, category_id,
                        user_id, created_at, updated_at
                    ) VALUES (
                        1, 'expense', 10, 'Groceries', NULL, '2026-04-10',
                        1, NULL, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        command.upgrade(_alembic_config(), "head")

        with db.engine.connect() as connection:
            category_columns = {
                row["name"]
                for row in connection.execute(text("PRAGMA table_info(categories)")).mappings()
            }
            assert "name_key" in category_columns
            assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []

        db.session.remove()
