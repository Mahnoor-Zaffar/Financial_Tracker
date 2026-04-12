from datetime import date
from decimal import Decimal

from finance_tracker.extensions import db
from finance_tracker.models.base import TimestampMixin, UserOwnedMixin


class TransactionTag(TimestampMixin, db.Model):
    __tablename__ = "transaction_tags"
    transaction_id = db.Column(
        db.Integer,
        db.ForeignKey("transactions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id = db.Column(
        db.Integer,
        db.ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    transaction = db.relationship("Transaction", back_populates="tag_links")
    tag = db.relationship("Tag", back_populates="transaction_links")


class Transaction(UserOwnedMixin, TimestampMixin, db.Model):
    __tablename__ = "transactions"
    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        db.CheckConstraint(
            "transaction_type IN ('income', 'expense', 'transfer')",
            name="ck_transactions_type_allowed",
        ),
        db.Index("ix_transactions_user_occurred_on", "user_id", "occurred_on"),
    )

    id = db.Column(db.Integer, primary_key=True)
    transaction_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    description = db.Column(db.String(180), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    occurred_on = db.Column(db.Date, nullable=False, default=date.today)

    account_id = db.Column(
        db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    transfer_account_id = db.Column(
        db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )

    user = db.relationship("User", back_populates="transactions")
    account = db.relationship(
        "Account", back_populates="transactions", foreign_keys=[account_id]
    )
    transfer_account = db.relationship(
        "Account", back_populates="incoming_transfers", foreign_keys=[transfer_account_id]
    )
    category = db.relationship("Category", back_populates="transactions")

    tag_links = db.relationship(
        "TransactionTag",
        back_populates="transaction",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tags = db.relationship(
        "Tag",
        secondary="transaction_tags",
        lazy="selectin",
        overlaps="tag_links,transaction_links,transaction,tag,transactions",
    )
