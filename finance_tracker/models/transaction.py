from datetime import date
from decimal import Decimal

from finance_tracker.extensions import db
from finance_tracker.models.base import TimestampMixin, UserOwnedMixin
from sqlalchemy import event
from sqlalchemy.ext.associationproxy import association_proxy


class TransactionTag(TimestampMixin, db.Model):
    __tablename__ = "transaction_tags"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            ondelete="CASCADE",
            name="fk_transaction_tags_transaction_user_transactions",
        ),
        db.ForeignKeyConstraint(
            ["tag_id", "user_id"],
            ["tags.id", "tags.user_id"],
            ondelete="CASCADE",
            name="fk_transaction_tags_tag_user_tags",
        ),
    )
    transaction_id = db.Column(
        db.Integer,
        primary_key=True,
    )
    tag_id = db.Column(
        db.Integer,
        primary_key=True,
    )
    user_id = db.Column(db.Integer, nullable=False)

    transaction = db.relationship(
        "Transaction",
        back_populates="tag_links",
        primaryjoin="TransactionTag.transaction_id == Transaction.id",
        foreign_keys=[transaction_id],
    )
    tag = db.relationship(
        "Tag",
        back_populates="transaction_links",
        primaryjoin="TransactionTag.tag_id == Tag.id",
        foreign_keys=[tag_id],
    )


class Transaction(UserOwnedMixin, TimestampMixin, db.Model):
    __tablename__ = "transactions"
    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        db.CheckConstraint(
            "transaction_type IN ('income', 'expense', 'transfer')",
            name="ck_transactions_type_allowed",
        ),
        db.CheckConstraint(
            "("
            "(transaction_type IN ('income', 'expense') "
            "AND category_id IS NOT NULL "
            "AND transfer_account_id IS NULL)"
            " OR "
            "(transaction_type = 'transfer' "
            "AND transfer_account_id IS NOT NULL "
            "AND category_id IS NULL)"
            ")",
            name="ck_transactions_required_links",
        ),
        db.CheckConstraint(
            "transfer_account_id IS NULL OR account_id != transfer_account_id",
            name="ck_transactions_distinct_transfer_accounts",
        ),
        db.UniqueConstraint("id", "user_id", name="uq_transactions_id_user"),
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
        db.Integer, db.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
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
        single_parent=True,
        primaryjoin="Transaction.id == TransactionTag.transaction_id",
        foreign_keys="TransactionTag.transaction_id",
    )
    tags = association_proxy("tag_links", "tag", creator=lambda tag: TransactionTag(tag=tag))


@event.listens_for(Transaction.tag_links, "append")
def _set_transaction_tag_user_id(
    transaction: Transaction, link: TransactionTag, _initiator
) -> None:
    if transaction.user_id is not None:
        link.user_id = transaction.user_id
