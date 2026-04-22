from finance_tracker.extensions import db
from finance_tracker.models.base import TimestampMixin


class LoginThrottle(TimestampMixin, db.Model):
    __tablename__ = "login_throttles"
    __table_args__ = (
        db.UniqueConstraint("scope", "key", name="uq_login_throttles_scope_key"),
        db.Index("ix_login_throttles_blocked_until", "blocked_until"),
    )

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(20), nullable=False)
    key = db.Column(db.String(255), nullable=False)
    failures = db.Column(db.Integer, nullable=False, default=0)
    first_failed_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    blocked_until = db.Column(db.DateTime(timezone=True), nullable=True)
