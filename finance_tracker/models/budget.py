from decimal import Decimal

from finance_tracker.extensions import db
from finance_tracker.models.base import TimestampMixin, UserOwnedMixin
from sqlalchemy import event


class Budget(UserOwnedMixin, TimestampMixin, db.Model):
    __tablename__ = "budgets"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "category_id", "month_start", name="uq_budgets_user_category_month"
        ),
        db.CheckConstraint("amount_limit > 0", name="ck_budgets_amount_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    month_start = db.Column(db.Date, nullable=False, index=True)
    amount_limit = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    user = db.relationship("User", back_populates="budgets")
    category = db.relationship("Category", back_populates="budgets")


@event.listens_for(Budget, "before_insert")
@event.listens_for(Budget, "before_update")
def _normalize_budget_month_start(mapper, connection, target):
    if target.month_start is not None:
        target.month_start = target.month_start.replace(day=1)
