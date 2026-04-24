from decimal import Decimal

from finance_tracker.extensions import db
from finance_tracker.models.base import TimestampMixin, UserOwnedMixin
from sqlalchemy import event, text


class BudgetValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, list[str]] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _budget_validation_error(message: str, **field_errors: str | list[str]) -> BudgetValidationError:
    normalized_errors: dict[str, list[str]] = {}
    for field_name, error_value in field_errors.items():
        if isinstance(error_value, str):
            normalized_errors[field_name] = [error_value]
        else:
            normalized_errors[field_name] = list(error_value)
    return BudgetValidationError(message, normalized_errors)


class Budget(UserOwnedMixin, TimestampMixin, db.Model):
    __tablename__ = "budgets"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["category_id", "user_id"],
            ["categories.id", "categories.user_id"],
            ondelete="CASCADE",
            name="fk_budgets_category_id_user_id_categories",
        ),
        db.UniqueConstraint(
            "user_id", "category_id", "month_start", name="uq_budgets_user_category_month"
        ),
        db.CheckConstraint("amount_limit > 0", name="ck_budgets_amount_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, nullable=False)
    month_start = db.Column(db.Date, nullable=False, index=True)
    amount_limit = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    user = db.relationship("User", back_populates="budgets", overlaps="budgets,category")
    category = db.relationship("Category", back_populates="budgets", overlaps="budgets,user")


@event.listens_for(Budget, "before_insert")
@event.listens_for(Budget, "before_update")
def _normalize_budget_month_start(mapper, connection, target):
    if target.month_start is not None:
        target.month_start = target.month_start.replace(day=1)

    category_row = connection.execute(
        text("SELECT user_id, kind FROM categories WHERE id = :category_id"),
        {"category_id": target.category_id},
    ).mappings().one_or_none()
    if category_row is None:
        return

    if category_row["kind"] != "expense":
        raise _budget_validation_error(
            "Budgets can only be assigned to expense categories.",
            category_id="Budgets can only be assigned to expense categories.",
        )
    if target.user_id is not None and category_row["user_id"] != target.user_id:
        raise _budget_validation_error(
            "Budgets can only be assigned to your expense categories.",
            category_id="Budgets can only be assigned to your expense categories.",
        )
