from datetime import date
from decimal import Decimal

import click

from finance_tracker.extensions import db
from finance_tracker.models import Account, Budget, Category, Tag, Transaction, User
from finance_tracker.services.transactions import attach_tags


def register_cli(app):
    @app.cli.group("seed")
    def seed_group():
        """Seed development data."""

    @seed_group.command("demo")
    @click.option("--email", default="demo@fintrack.local", show_default=True)
    @click.option("--password", default="ChangeMe123!", show_default=True)
    def seed_demo(email: str, password: str):
        user = User.query.filter_by(email=email.lower().strip()).first()
        if user is None:
            user = User(
                email=email.lower().strip(),
                full_name="Demo User",
                currency_code="USD",
                timezone="UTC",
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            checking = Account(
                user_id=user.id,
                name="Daily Checking",
                account_type="checking",
                institution="Arc Bank",
                opening_balance=Decimal("2400.00"),
            )
            cash = Account(
                user_id=user.id,
                name="Cash Wallet",
                account_type="cash",
                opening_balance=Decimal("120.00"),
            )
            db.session.add_all([checking, cash])
            db.session.flush()

            income_cat = Category(
                user_id=user.id, name="Salary", kind="income", color="#255a44"
            )
            groceries_cat = Category(
                user_id=user.id, name="Groceries", kind="expense", color="#873f2d"
            )
            transit_cat = Category(
                user_id=user.id, name="Transport", kind="expense", color="#3f4e77"
            )
            db.session.add_all([income_cat, groceries_cat, transit_cat])
            db.session.flush()

            budget = Budget(
                user_id=user.id,
                category_id=groceries_cat.id,
                month_start=date.today().replace(day=1),
                amount_limit=Decimal("550.00"),
            )
            db.session.add(budget)
            db.session.flush()

            t1 = Transaction(
                user_id=user.id,
                transaction_type="income",
                amount=Decimal("3200.00"),
                description="Monthly salary",
                occurred_on=date.today().replace(day=2),
                account_id=checking.id,
                category_id=income_cat.id,
            )
            t2 = Transaction(
                user_id=user.id,
                transaction_type="expense",
                amount=Decimal("84.20"),
                description="Weekly groceries",
                occurred_on=date.today().replace(day=4),
                account_id=checking.id,
                category_id=groceries_cat.id,
            )
            t3 = Transaction(
                user_id=user.id,
                transaction_type="expense",
                amount=Decimal("18.50"),
                description="Metro card top-up",
                occurred_on=date.today().replace(day=6),
                account_id=cash.id,
                category_id=transit_cat.id,
            )
            db.session.add_all([t1, t2, t3])
            db.session.flush()
            attach_tags(t2, "home, essentials", user.id)
            attach_tags(t3, "commute", user.id)
            db.session.commit()
            click.echo(f"Seeded demo account for {email}.")
            return

        if not user.accounts:
            click.echo("User exists without accounts. Skipping to avoid overwriting.")
            return

        if not user.transactions:
            groceries_cat = Category.query.filter_by(
                user_id=user.id, kind="expense"
            ).first()
            account = Account.query.filter_by(user_id=user.id).first()
            if groceries_cat and account:
                tx = Transaction(
                    user_id=user.id,
                    transaction_type="expense",
                    amount=Decimal("25.00"),
                    description="Starter transaction",
                    occurred_on=date.today(),
                    account_id=account.id,
                    category_id=groceries_cat.id,
                )
                db.session.add(tx)
                db.session.commit()
                click.echo(f"Added starter transaction to existing user {email}.")
                return

        click.echo("Demo seed skipped: user already has finance data.")
