from finance_tracker.extensions import db
from finance_tracker.models.base import TimestampMixin, UserOwnedMixin


class Tag(UserOwnedMixin, TimestampMixin, db.Model):
    __tablename__ = "tags"
    __table_args__ = (
        db.UniqueConstraint("id", "user_id", name="uq_tags_id_user"),
        db.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#6a7286")

    user = db.relationship("User", back_populates="tags")
    transaction_links = db.relationship(
        "TransactionTag",
        back_populates="tag",
        cascade="all, delete-orphan",
        lazy="selectin",
        single_parent=True,
        primaryjoin="Tag.id == TransactionTag.tag_id",
        foreign_keys="TransactionTag.tag_id",
    )
