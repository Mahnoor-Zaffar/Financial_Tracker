from datetime import date

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from finance_tracker.extensions import db
from finance_tracker.forms import DeleteForm, TransactionFilterForm, TransactionForm
from finance_tracker.models import Transaction
from finance_tracker.services import (
    TransactionValidationError,
    account_choices,
    apply_sorting,
    build_transaction_query,
    category_choices,
    create_transaction,
    get_owned_or_404,
    pagination_from_request,
    summarize_transactions,
    tag_choices,
    update_transaction,
)

bp = Blueprint("transactions", __name__, url_prefix="/transactions")


def _bind_transaction_form_choices(form: TransactionForm, user_id: int):
    account_opts = account_choices(user_id=user_id, include_inactive=False)
    transaction_type = form.transaction_type.data or "expense"
    category_kind = None if transaction_type == "transfer" else transaction_type
    category_opts = category_choices(user_id=user_id, include_kind=False, kind=category_kind)

    form.account_id.choices = account_opts
    form.to_account_id.choices = [(0, "Select destination")] + account_opts
    if transaction_type == "transfer":
        form.category_id.choices = [(0, "No category")]
    else:
        form.category_id.choices = [(0, "Select category")] + category_opts

    return {
        "expense": category_choices(user_id=user_id, include_kind=False, kind="expense"),
        "income": category_choices(user_id=user_id, include_kind=False, kind="income"),
        "transfer": [],
    }


def _bind_filter_choices(form: TransactionFilterForm, user_id: int):
    form.account_id.choices = [(0, "All accounts")] + account_choices(
        user_id=user_id, include_inactive=True
    )
    form.category_id.choices = [(0, "All categories")] + category_choices(user_id=user_id)
    form.tag_id.choices = [(0, "All tags")] + tag_choices(user_id=user_id)


def _filter_value(field):
    if field.errors:
        return None
    value = field.data
    if value in (None, "", 0):
        return None
    return value


def _query_arg_value(value):
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _apply_transaction_validation_error(form: TransactionForm, exc: TransactionValidationError) -> bool:
    field_errors = getattr(exc, "field_errors", {}) or {}
    attached_any = False
    for field_name, messages in field_errors.items():
        field = getattr(form, field_name, None)
        if field is None:
            continue
        attached_any = True
        if isinstance(messages, str):
            messages = [messages]
        for message in messages:
            if message not in field.errors:
                field.errors.append(message)
    return attached_any


@bp.route("/", methods=["GET"])
@login_required
def index():
    filter_form = TransactionFilterForm(request.args, meta={"csrf": False})
    _bind_filter_choices(filter_form, current_user.id)

    filter_is_valid = filter_form.validate()
    date_range_invalid = bool(
        filter_form.start_date.data
        and filter_form.end_date.data
        and filter_form.end_date.data < filter_form.start_date.data
    )
    if request.args and not filter_is_valid:
        if date_range_invalid:
            flash("Start date must be on or before end date.", "warning")
        else:
            flash("Some filters were invalid and were ignored.", "warning")

    start_date = None if date_range_invalid else _filter_value(filter_form.start_date)
    end_date = None if date_range_invalid else _filter_value(filter_form.end_date)

    query = build_transaction_query(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        transaction_type=_filter_value(filter_form.transaction_type),
        account_id=_filter_value(filter_form.account_id),
        category_id=_filter_value(filter_form.category_id),
        tag_id=_filter_value(filter_form.tag_id),
    )
    summary = summarize_transactions(query)
    sort_key = _filter_value(filter_form.sort) or "date_desc"
    query = apply_sorting(query, sort_key)

    page, per_page = pagination_from_request(
        default_per_page=current_app.config.get("TRANSACTIONS_PER_PAGE", 20),
        max_per_page=current_app.config.get("MAX_TRANSACTIONS_PER_PAGE", 100),
    )
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    query_args = {}
    for key, value in (
        ("start_date", start_date),
        ("end_date", end_date),
        ("transaction_type", _filter_value(filter_form.transaction_type)),
        ("account_id", _filter_value(filter_form.account_id)),
        ("category_id", _filter_value(filter_form.category_id)),
        ("tag_id", _filter_value(filter_form.tag_id)),
        ("sort", sort_key if sort_key != "date_desc" else None),
    ):
        if value is not None:
            query_args[key] = _query_arg_value(value)
    delete_form = DeleteForm()

    return render_template(
        "transactions/index.html",
        filter_form=filter_form,
        delete_form=delete_form,
        transactions=pagination.items,
        pagination=pagination,
        query_args=query_args,
        summary=summary,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = TransactionForm(prefix="new")
    category_options = _bind_transaction_form_choices(form, current_user.id)

    if form.validate_on_submit():
        try:
            create_transaction(
                user_id=current_user.id,
                transaction_type=form.transaction_type.data,
                amount=form.amount.data,
                description=form.description.data,
                occurred_on=form.occurred_on.data,
                account_id=form.account_id.data,
                to_account_id=form.to_account_id.data or None,
                category_id=form.category_id.data or None,
                notes=form.notes.data,
                raw_tags=form.tag_names.data,
            )
            db.session.commit()
            flash("Transaction saved.", "success")
            return redirect(url_for("transactions.index"))
        except TransactionValidationError as exc:
            db.session.rollback()
            if not _apply_transaction_validation_error(form, exc):
                flash(str(exc), "error")

    return render_template("transactions/new.html", form=form, category_options=category_options)


@bp.route("/<int:transaction_id>/edit", methods=["GET", "POST"])
@login_required
def edit(transaction_id: int):
    transaction = get_owned_or_404(Transaction, transaction_id, current_user.id)

    form = TransactionForm(prefix="edit", obj=transaction)
    category_options = _bind_transaction_form_choices(form, current_user.id)

    if request.method == "GET":
        form.to_account_id.data = transaction.transfer_account_id or 0
        form.category_id.data = transaction.category_id or 0
        form.tag_names.data = ", ".join(tag.name for tag in transaction.tags)

    if form.validate_on_submit():
        try:
            update_transaction(
                transaction,
                user_id=current_user.id,
                transaction_type=form.transaction_type.data,
                amount=form.amount.data,
                description=form.description.data,
                occurred_on=form.occurred_on.data,
                account_id=form.account_id.data,
                to_account_id=form.to_account_id.data or None,
                category_id=form.category_id.data or None,
                notes=form.notes.data,
                raw_tags=form.tag_names.data,
            )
            db.session.commit()
            flash("Transaction updated.", "success")
            return redirect(url_for("transactions.index"))
        except TransactionValidationError as exc:
            db.session.rollback()
            if not _apply_transaction_validation_error(form, exc):
                flash(str(exc), "error")

    return render_template(
        "transactions/edit.html",
        form=form,
        transaction=transaction,
        category_options=category_options,
    )


@bp.route("/<int:transaction_id>/delete", methods=["POST"])
@login_required
def delete(transaction_id: int):
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)
    transaction = get_owned_or_404(Transaction, transaction_id, current_user.id)
    db.session.delete(transaction)
    db.session.commit()
    flash("Transaction deleted.", "info")
    return redirect(url_for("transactions.index"))
