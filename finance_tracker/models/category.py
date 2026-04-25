from sqlalchemy import event

from finance_tracker.extensions import db
from finance_tracker.models.base import TimestampMixin, UserOwnedMixin


def category_name_key(name: str | None) -> str:
    return (name or "").strip().casefold()


class Category(UserOwnedMixin, TimestampMixin, db.Model):
    __tablename__ = "categories"
    __table_args__ = (
        db.UniqueConstraint("id", "user_id", name="uq_categories_id_user"),
        db.UniqueConstraint("user_id", "name", "kind", name="uq_categories_user_kind"),
        db.UniqueConstraint(
            "user_id", "name_key", "kind", name="uq_categories_user_name_key_kind"
        ),
        db.CheckConstraint(
            "kind IN ('income', 'expense')", name="ck_categories_kind_allowed"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_key = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="expense")
    color = db.Column(db.String(7), nullable=False, default="#4f5669")

    user = db.relationship("User", back_populates="categories")
    transactions = db.relationship("Transaction", back_populates="category", lazy="selectin")
    budgets = db.relationship(
        "Budget",
        back_populates="category",
        lazy="selectin",
        overlaps="user,budgets",
    )


@event.listens_for(Category, "before_insert")
@event.listens_for(Category, "before_update")
def _set_category_name_key(_mapper, _connection, target: Category) -> None:
    target.name_key = category_name_key(target.name)
