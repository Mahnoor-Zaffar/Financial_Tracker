from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from finance_tracker.extensions import db, login_manager
from finance_tracker.models.base import TimestampMixin


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False, default="User")
    currency_code = db.Column(db.String(3), nullable=False, default="USD")
    timezone = db.Column(db.String(64), nullable=False, default="UTC")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    accounts = db.relationship(
        "Account", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    categories = db.relationship(
        "Category", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    tags = db.relationship(
        "Tag", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    transactions = db.relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    budgets = db.relationship(
        "Budget", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))
