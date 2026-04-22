from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from finance_tracker.extensions import db
from finance_tracker.models import Account, Category, Tag, Transaction, TransactionTag


class TransactionValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, list[str]] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _validation_error(message: str, **field_errors: str | list[str]) -> TransactionValidationError:
    normalized_errors: dict[str, list[str]] = {}
    for field_name, error_value in field_errors.items():
        if isinstance(error_value, str):
            normalized_errors[field_name] = [error_value]
        else:
            normalized_errors[field_name] = list(error_value)
    return TransactionValidationError(message, normalized_errors)


def as_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def account_choices(user_id: int, include_inactive: bool = False):
    query = Account.query.filter_by(user_id=user_id)
    if not include_inactive:
        query = query.filter_by(is_active=True)
    rows = query.order_by(Account.name.asc()).all()
    return [(row.id, row.name) for row in rows]


def category_choices(user_id: int, include_kind: bool = True, kind: str | None = None):
    query = Category.query.filter_by(user_id=user_id)
    if kind is not None:
        query = query.filter_by(kind=kind)
    rows = query.order_by(Category.kind.asc(), Category.name.asc()).all()
    if include_kind:
        return [(row.id, f"{row.name} ({row.kind})") for row in rows]
    return [(row.id, row.name) for row in rows]


def tag_choices(user_id: int):
    rows = Tag.query.filter_by(user_id=user_id).order_by(Tag.name.asc()).all()
    return [(row.id, row.name) for row in rows]


def validate_account_ownership(
    account_id: int,
    user_id: int,
    *,
    active_only: bool = False,
    field_name: str = "account",
    field_key: str = "account_id",
) -> Account:
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if account is None:
        raise _validation_error(f"Invalid {field_name} selected.", **{field_key: f"Invalid {field_name} selected."})
    if active_only and not account.is_active:
        raise _validation_error(f"Select an active {field_name}.", **{field_key: f"Select an active {field_name}."})
    return account


def validate_category_ownership(category_id: int, user_id: int) -> Category:
    category = Category.query.filter_by(id=category_id, user_id=user_id).first()
    if category is None:
        raise _validation_error("Invalid category selected.", category_id="Invalid category selected.")
    return category


def validate_transaction_payload(
    *,
    user_id: int,
    transaction_type: str,
    account_id: int,
    to_account_id: int | None,
    category_id: int | None,
) -> None:
    validate_account_ownership(
        account_id,
        user_id,
        active_only=True,
        field_name="account",
        field_key="account_id",
    )

    if transaction_type == "transfer":
        if not to_account_id:
            raise _validation_error(
                "Select the destination account for transfers.",
                to_account_id="Select the destination account for transfers.",
            )
        validate_account_ownership(
            to_account_id,
            user_id,
            active_only=True,
            field_name="destination account",
            field_key="to_account_id",
        )
        if account_id == to_account_id:
            raise _validation_error(
                "Transfer source and destination must be different.",
                account_id="Transfer source and destination must be different.",
                to_account_id="Transfer source and destination must be different.",
            )
        if category_id is not None:
            raise _validation_error(
                "Transfers cannot be assigned a category.",
                category_id="Transfers cannot be assigned a category.",
            )
        return

    if to_account_id is not None:
        raise _validation_error(
            "Only transfers can set a destination account.",
            to_account_id="Only transfers can set a destination account.",
        )
    if not category_id:
        raise _validation_error(
            "Select a category for income and expense transactions.",
            category_id="Select a category for income and expense transactions.",
        )
    category = validate_category_ownership(category_id, user_id)
    if category.kind != transaction_type:
        raise _validation_error(
            f"Category type mismatch. Choose a {transaction_type} category.",
            category_id=f"Category type mismatch. Choose a {transaction_type} category.",
        )


def validate_transaction_persistence(transaction: Transaction) -> None:
    user_id = transaction.user_id
    if not user_id:
        raise _validation_error(
            "Transaction must belong to a user before it can be saved.",
            user_id="Transaction must belong to a user before it can be saved.",
        )

    transaction_type = (transaction.transaction_type or "").strip()
    if transaction_type not in {"income", "expense", "transfer"}:
        raise _validation_error(
            "Invalid transaction type selected.",
            transaction_type="Invalid transaction type selected.",
        )

    validate_transaction_payload(
        user_id=user_id,
        transaction_type=transaction_type,
        account_id=transaction.account_id,
        to_account_id=transaction.transfer_account_id,
        category_id=transaction.category_id,
    )


def _load_existing_tags(user_id: int, names: list[str]) -> dict[str, Tag]:
    return {
        tag.name.lower(): tag
        for tag in Tag.query.filter(Tag.user_id == user_id, Tag.name.in_(names)).all()
    }


def _get_or_create_tag(user_id: int, name: str) -> Tag:
    bind = db.session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""

    if dialect_name == "sqlite":
        insert_stmt = sqlite_insert
    elif dialect_name == "postgresql":
        insert_stmt = postgresql_insert
    else:
        tag = Tag.query.filter_by(user_id=user_id, name=name).first()
        if tag is not None:
            return tag
        tag = Tag(user_id=user_id, name=name, color="#8d6f47")
        db.session.add(tag)
        db.session.flush()
        return tag

    db.session.execute(
        insert_stmt(Tag.__table__)
        .values(user_id=user_id, name=name, color="#8d6f47")
        .on_conflict_do_nothing(index_elements=["user_id", "name"])
    )
    return db.session.execute(
        select(Tag).where(Tag.user_id == user_id, Tag.name == name)
    ).scalar_one()


def attach_tags(transaction: Transaction, raw_tags: str | None, user_id: int) -> None:
    transaction.tags.clear()
    if not raw_tags:
        return

    normalized = []
    seen = set()
    for part in raw_tags.split(","):
        name = part.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name[:60])

    if not normalized:
        return

    existing_tags = _load_existing_tags(user_id, normalized)
    for name in normalized:
        tag = existing_tags.get(name)
        if tag is None:
            tag = _get_or_create_tag(user_id, name)
            existing_tags[name] = tag
        transaction.tags.append(tag)


def create_transaction(
    *,
    user_id: int,
    transaction_type: str,
    amount: Decimal,
    description: str,
    occurred_on: date,
    account_id: int,
    to_account_id: int | None = None,
    category_id: int | None = None,
    notes: str | None = None,
    raw_tags: str | None = None,
) -> Transaction:
    transaction = Transaction(
        user_id=user_id,
        transaction_type=transaction_type,
        amount=amount,
        description=description.strip(),
        occurred_on=occurred_on,
        notes=(notes or "").strip() or None,
        account_id=account_id,
        transfer_account_id=to_account_id if transaction_type == "transfer" else None,
        category_id=category_id if transaction_type != "transfer" else None,
    )
    validate_transaction_persistence(transaction)
    db.session.add(transaction)
    db.session.flush()
    attach_tags(transaction, raw_tags, user_id)
    return transaction


def update_transaction(
    transaction: Transaction,
    *,
    user_id: int,
    transaction_type: str,
    amount: Decimal,
    description: str,
    occurred_on: date,
    account_id: int,
    to_account_id: int | None = None,
    category_id: int | None = None,
    notes: str | None = None,
    raw_tags: str | None = None,
) -> Transaction:
    transaction.transaction_type = transaction_type
    transaction.amount = amount
    transaction.description = description.strip()
    transaction.occurred_on = occurred_on
    transaction.notes = (notes or "").strip() or None
    transaction.account_id = account_id
    transaction.transfer_account_id = to_account_id if transaction_type == "transfer" else None
    transaction.category_id = category_id if transaction_type != "transfer" else None
    validate_transaction_persistence(transaction)
    attach_tags(transaction, raw_tags, user_id)
    return transaction


def build_transaction_query(
    *,
    user_id: int,
    start_date=None,
    end_date=None,
    transaction_type: str | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tag_id: int | None = None,
):
    query = Transaction.query.filter_by(user_id=user_id)
    if start_date:
        query = query.filter(Transaction.occurred_on >= start_date)
    if end_date:
        query = query.filter(Transaction.occurred_on <= end_date)
    if transaction_type:
        query = query.filter(Transaction.transaction_type == transaction_type)

    if account_id:
        query = query.filter(
            or_(
                Transaction.account_id == int(account_id),
                Transaction.transfer_account_id == int(account_id),
            )
        )
    if category_id:
        query = query.filter(Transaction.category_id == int(category_id))
    if tag_id:
        query = query.join(Transaction.tag_links).filter(TransactionTag.tag_id == int(tag_id))
    return query


def apply_sorting(query, sort_key: str):
    sort_map = {
        "date_desc": [Transaction.occurred_on.desc(), Transaction.id.desc()],
        "date_asc": [Transaction.occurred_on.asc(), Transaction.id.asc()],
        "amount_desc": [Transaction.amount.desc(), Transaction.id.desc()],
        "amount_asc": [Transaction.amount.asc(), Transaction.id.asc()],
    }
    ordering = sort_map.get(sort_key, sort_map["date_desc"])
    return query.order_by(*ordering)


def summarize_transactions(query) -> dict:
    income = query.filter(Transaction.transaction_type == "income").with_entities(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).scalar()
    expense = query.filter(Transaction.transaction_type == "expense").with_entities(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).scalar()
    transfer = query.filter(Transaction.transaction_type == "transfer").with_entities(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).scalar()
    count = query.with_entities(func.count(Transaction.id)).scalar() or 0
    return {
        "count": int(count),
        "income": as_decimal(income),
        "expense": as_decimal(expense),
        "transfer": as_decimal(transfer),
        "net": as_decimal(income) - as_decimal(expense),
    }


def account_balance_projection(user_id: int) -> dict[int, Decimal]:
    opening_rows = select(
        Account.id.label("account_id"),
        Account.opening_balance.label("delta"),
    ).where(Account.user_id == user_id)

    source_transaction_rows = select(
        Transaction.account_id.label("account_id"),
        (
            Transaction.amount
            * (
                (Transaction.transaction_type == "income").cast(db.Integer)
                - (
                    (Transaction.transaction_type == "expense")
                    | (Transaction.transaction_type == "transfer")
                ).cast(db.Integer)
            )
        ).label("delta"),
    ).where(Transaction.user_id == user_id)

    transfer_in_rows = select(
        Transaction.transfer_account_id.label("account_id"),
        Transaction.amount.label("delta"),
    ).where(
        Transaction.user_id == user_id,
        Transaction.transaction_type == "transfer",
        Transaction.transfer_account_id.isnot(None),
    )

    balance_rows = union_all(
        opening_rows,
        source_transaction_rows,
        transfer_in_rows,
    ).subquery()

    rows = (
        db.session.query(
            balance_rows.c.account_id,
            func.coalesce(func.sum(balance_rows.c.delta), literal(0)).label("balance"),
        )
        .group_by(balance_rows.c.account_id)
        .all()
    )
    return {
        int(account_id): as_decimal(balance)
        for account_id, balance in rows
        if account_id is not None
    }


def account_balance(account_id: int, user_id: int) -> Decimal:
    balances = account_balance_projection(user_id)
    if account_id in balances:
        return balances[account_id]
    account_exists = (
        db.session.query(Account.id)
        .filter(Account.id == account_id, Account.user_id == user_id)
        .scalar()
    )
    if account_exists is None:
        return Decimal("0.00")
    return Decimal("0.00")
