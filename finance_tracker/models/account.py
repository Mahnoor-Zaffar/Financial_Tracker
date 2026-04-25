from decimal import Decimal

from sqlalchemy import event

from finance_tracker.extensions import db
from finance_tracker.models.base import TimestampMixin, UserOwnedMixin


def account_name_key(name: str | None) -> str:
    return (name or "").strip().casefold()


class Account(UserOwnedMixin, TimestampMixin, db.Model):
    __tablename__ = "accounts"
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_accounts_user_name"),
        db.UniqueConstraint("user_id", "name_key", name="uq_accounts_user_name_key"),
        db.CheckConstraint("opening_balance >= 0", name="ck_accounts_opening_balance"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    name_key = db.Column(db.String(255), nullable=False)
    account_type = db.Column(db.String(32), nullable=False, default="checking")
    institution = db.Column(db.String(120), nullable=True)
    opening_balance = db.Column(
        db.Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    user = db.relationship("User", back_populates="accounts")
    transactions = db.relationship(
        "Transaction",
        back_populates="account",
        foreign_keys="Transaction.account_id",
        lazy="selectin",
    )
    incoming_transfers = db.relationship(
        "Transaction",
        back_populates="transfer_account",
        foreign_keys="Transaction.transfer_account_id",
        lazy="selectin",
    )


@event.listens_for(Account, "before_insert")
@event.listens_for(Account, "before_update")
def _set_account_name_key(_mapper, _connection, target: Account) -> None:
    target.name_key = account_name_key(target.name)
